"""求值引擎：计算下一次触发与合并后的最近 10 次触发。

关键规则：
- 触发点对齐当地分钟零秒；不存在的时间跳过；同名当地时刻只取 UTC 较早一次。
- 窗口按触发瞬间的当地时间判断，含开始、不含结束；窗口外直接丢弃。
- 结果严格晚于查询起点；搜索截止点为起点 + 2928 天（每天 86400 秒），不含截止点。

性能要点：
- 窗口过滤是纯当地时间比较，在做任何时区换算前完成。
- 无偏移变化的当地日期（通过 0 点 / 正午 / 次日 0 点三处偏移判断）直接按
  固定偏移做算术换算，避免逐候选的 round-trip 验证。
- 真实时区偏移绝对值不超过 15 小时，据此裁剪必不可能晚于起点的候选与日期。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from heapq import heappop, heappush
from typing import Iterable, Iterator
from zoneinfo import ZoneInfo

from .schedule import BackupSchedule

MAX_SEARCH_DAYS = 2928
MAX_MERGED_RESULTS = 10

_UTC = timezone.utc
_DAY = timedelta(days=1)
# 真实 IANA 时区偏移绝对值不超过 14 小时，留 1 小时余量。
_MAX_OFFSET = timedelta(hours=15)
# 触发点的当地时间 = UTC + 偏移 >= 起点 - 15h，故日期余量 1 天足够。
_MARGIN = _DAY


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=_UTC)
    return value.astimezone(_UTC)


def _resolve_local(zone: ZoneInfo, naive: datetime) -> datetime | None:
    """当地分钟对应的最早 UTC 瞬时；该当地时间不存在时返回 None。"""
    best: datetime | None = None
    for fold in (0, 1):
        candidate = naive.replace(tzinfo=zone, fold=fold).astimezone(_UTC)
        if candidate.astimezone(zone).replace(tzinfo=None) != naive:
            continue  # 该 fold 下当地时间不存在
        if best is None or candidate < best:
            best = candidate
    return best


class _Prepared:
    """按计划预计算的查询结构：时区对象与窗口内的 (时, 分) 候选。"""

    __slots__ = ("schedule", "zone", "candidates")

    def __init__(self, schedule: BackupSchedule) -> None:
        self.schedule = schedule
        self.zone = ZoneInfo(schedule.timezone)
        cron = schedule.cron
        self.candidates = tuple(
            (hour, minute)
            for hour in sorted(cron.hours)
            for minute in sorted(cron.minutes)
            if schedule.window.contains(hour * 60 + minute)
        )


def _iter_triggers(prepared: _Prepared, start_utc: datetime, end_utc: datetime) -> Iterator[datetime]:
    """按 UTC 递增顺序产生 (start_utc, end_utc) 内的触发点。"""
    candidates = prepared.candidates
    if not candidates:
        return
    zone = prepared.zone
    cron = prepared.schedule.cron
    # 当地 naive <= 起点 - 15h 的候选，其 UTC 必然 <= 起点，无需换算。
    skip_before = (start_utc - _MAX_OFFSET).replace(tzinfo=None)
    day = (start_utc - _MARGIN).astimezone(zone).date()
    last_day = (end_utc + _MARGIN).astimezone(zone).date()
    while day <= last_day:
        if day.month not in cron.months:
            # 整月不匹配，直接跳到下个月 1 号。
            day = day.replace(year=day.year + 1, month=1, day=1) if day.month == 12 else day.replace(month=day.month + 1, day=1)
            continue
        if cron.matches_date(day):
            year, month, dom = day.year, day.month, day.day
            midnight = datetime(year, month, dom)
            off0 = midnight.replace(tzinfo=zone).utcoffset()
            off1 = (midnight + timedelta(hours=12)).replace(tzinfo=zone).utcoffset()
            off2 = (midnight + _DAY).replace(tzinfo=zone).utcoffset()
            constant_offset = off0 == off1 == off2
            for hour, minute in candidates:
                naive = datetime(year, month, dom, hour, minute)
                if naive <= skip_before:
                    continue
                if constant_offset:
                    instant = (naive - off0).replace(tzinfo=_UTC)
                else:
                    resolved = _resolve_local(zone, naive)
                    if resolved is None:
                        continue  # 夏令时前进造成的不存在时间，跳过
                    instant = resolved
                if instant <= start_utc:
                    continue  # 含回拨时已被消费的较早一次
                if instant >= end_utc:
                    return
                yield instant
        day += _DAY


class ScheduleEngine:
    """进程内保存计划集合，提供触发时间查询。"""

    def __init__(self, schedules: Iterable[BackupSchedule] = ()) -> None:
        self._prepared: dict[str, _Prepared] = {}
        for schedule in schedules:
            self.add(schedule)

    def add(self, schedule: BackupSchedule) -> None:
        self._prepared[schedule.schedule_id] = _Prepared(schedule)

    def remove(self, schedule_id: str) -> None:
        self._prepared.pop(schedule_id, None)

    def next_after(self, schedule_id: str, start_utc: datetime) -> datetime | None:
        """单条计划在 start_utc 之后严格晚于起点的下一次触发（UTC）。"""
        start = _as_utc(start_utc)
        end = start + timedelta(days=MAX_SEARCH_DAYS)
        return next(_iter_triggers(self._prepared[schedule_id], start, end), None)

    def upcoming(self, start_utc: datetime, limit: int = MAX_MERGED_RESULTS) -> list[tuple[datetime, str]]:
        """所有计划合并后的最近 limit 次触发，按 (UTC 时间, 计划标识) 排序。"""
        start = _as_utc(start_utc)
        end = start + timedelta(days=MAX_SEARCH_DAYS)
        heap: list[tuple[datetime, str, Iterator[datetime]]] = []
        for schedule_id, prepared in self._prepared.items():
            gen = _iter_triggers(prepared, start, end)
            first = next(gen, None)
            if first is not None:
                heappush(heap, (first, schedule_id, gen))
        results: list[tuple[datetime, str]] = []
        while heap and len(results) < limit:
            instant, schedule_id, gen = heappop(heap)
            results.append((instant, schedule_id))
            following = next(gen, None)
            if following is not None:
                heappush(heap, (following, schedule_id, gen))
        return results
