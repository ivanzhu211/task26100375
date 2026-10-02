"""单条备份计划：cron + IANA 时区 + 每日窗口，求下一次触发 UTC 时刻。"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from backup_scheduler.cron import CronExpression
from backup_scheduler.window import DailyWindow

SEARCH_DAYS = 2928  # 搜索截止：起点 + 2928*86400 秒（不含）

_MINUTES_PER_DAY = 1440


def _resolve_local(naive: datetime, tz: ZoneInfo) -> datetime | None:
    """把当地墙钟时间解析为 UTC 时刻。

    不存在的时间（夏令时前进）返回 None；重复出现的时间（回拨）取 UTC 较早的一次。
    """
    for fold in (0, 1):
        aware = naive.replace(tzinfo=tz, fold=fold)
        utc = aware.astimezone(timezone.utc)
        if utc.astimezone(tz).replace(tzinfo=None) == naive:
            return utc
    return None


def _weekday_sun0(d: date) -> int:
    """Python weekday()（周一=0）转换为周日=0。"""
    return (d.weekday() + 1) % 7


class Schedule:
    """一条备份计划：唯一标识 + 五字段 cron + IANA 时区 + 每日当地窗口。"""

    def __init__(self, schedule_id: str, cron: str, timezone: str, window: tuple[str, str]) -> None:
        self.schedule_id = schedule_id
        self.cron = CronExpression(cron)
        self.timezone_name = timezone
        self._tz = ZoneInfo(timezone)
        self.window = DailyWindow(*window)
        # 预计算一天内同时满足 cron 分/时 与窗口的触发分钟（当地墙钟），升序。
        self._daily_times: list[int] = sorted(
            hour * 60 + minute
            for hour in self.cron.hours
            for minute in self.cron.minutes
            if self.window.contains(hour * 60 + minute)
        )

    def next_after(self, after: datetime) -> datetime | None:
        """返回严格晚于 after 的下一次触发 UTC 时刻；2928 天内（不含截止点）无则返回 None。"""
        if not self._daily_times:
            return None
        if after.tzinfo is None:
            after = after.replace(tzinfo=timezone.utc)
        after_utc = after.astimezone(timezone.utc)
        deadline = after_utc + timedelta(days=SEARCH_DAYS)

        tz = self._tz
        local_after = after_utc.astimezone(tz)
        first_minute = local_after.hour * 60 + local_after.minute + 1
        current = local_after.date()
        if first_minute >= _MINUTES_PER_DAY:
            first_minute = 0
            current += timedelta(days=1)

        last_date = deadline.astimezone(tz).date()
        one_day = timedelta(days=1)
        months = self.cron.months
        cron = self.cron

        while current <= last_date:
            if current.month not in months:
                # 整月不匹配，直接跳到下个月 1 日
                if current.month == 12:
                    current = date(current.year + 1, 1, 1)
                else:
                    current = date(current.year, current.month + 1, 1)
                continue
            if cron.date_matches(current.year, current.month, current.day, _weekday_sun0(current)):
                for minute_of_day in self._daily_times:
                    if current == local_after.date() and minute_of_day < first_minute:
                        continue
                    naive = datetime(
                        current.year, current.month, current.day,
                        minute_of_day // 60, minute_of_day % 60,
                    )
                    utc = _resolve_local(naive, tz)
                    if utc is not None and after_utc < utc < deadline:
                        return utc
            current += one_day
        return None
