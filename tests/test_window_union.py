"""日/星期并集 + 跨午夜窗口：与独立逐分钟枚举的期望完全一致。"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from backup_schedule import BackupSchedule, CronSchedule, ScheduleEngine
from backup_schedule.schedule import TimeWindow

UTC = timezone.utc


def brute_force(schedule, start_utc, end_utc):
    """独立实现的逐分钟枚举：直接按业务规则逐当地分钟求值。"""
    zone = ZoneInfo(schedule.timezone)
    out = set()
    day = (start_utc - timedelta(days=2)).astimezone(zone).date()
    last = (end_utc + timedelta(days=2)).astimezone(zone).date()
    while day <= last:
        for minute_of_day in range(1440):
            hour, minute = divmod(minute_of_day, 60)
            weekday = day.toordinal() % 7  # 0=周日
            if not schedule.cron.matches(minute, hour, day.day, day.month, weekday):
                continue
            if not schedule.window.contains(minute_of_day):
                continue
            naive = datetime(day.year, day.month, day.day, hour, minute)
            instants = set()
            for fold in (0, 1):
                candidate = naive.replace(tzinfo=zone, fold=fold).astimezone(UTC)
                if candidate.astimezone(zone).replace(tzinfo=None) == naive:
                    instants.add(candidate)
            if not instants:
                continue  # 不存在的当地时间
            earliest = min(instants)  # 同名当地时刻只取 UTC 较早一次
            if start_utc < earliest < end_utc:
                out.add(earliest)
        day += timedelta(days=1)
    return sorted(out)


def engine_triggers(schedule, start_utc, end_utc):
    engine = ScheduleEngine([schedule])
    results = []
    cursor = start_utc
    while True:
        nxt = engine.next_after(schedule.schedule_id, cursor)
        if nxt is None or nxt >= end_utc:
            return results
        results.append(nxt)
        cursor = nxt


def make(expr, tz, window):
    return BackupSchedule("s", CronSchedule(expr), tz, window)


def test_dom_dow_union_with_cross_midnight_window_matches_brute_force():
    # 每月 10 号或周二，22:00-03:00 跨午夜窗口，含 DST 切换的三个月。
    schedule = make("*/20 22,23,0,1,2 10 * 2", "America/New_York", TimeWindow(22 * 60, 3 * 60))
    start = datetime(2026, 2, 15, 0, 0, tzinfo=UTC)
    end = datetime(2026, 5, 15, 0, 0, tzinfo=UTC)
    assert engine_triggers(schedule, start, end) == brute_force(schedule, start, end)


def test_union_matches_brute_force_across_lord_howe_transition():
    schedule = make("*/7 23,0,1 29 2,4,10 0", "Australia/Lord_Howe", TimeWindow(22 * 60, 2 * 60))
    start = datetime(2026, 1, 20, 0, 0, tzinfo=UTC)
    end = datetime(2026, 12, 31, 0, 0, tzinfo=UTC)
    assert engine_triggers(schedule, start, end) == brute_force(schedule, start, end)


def test_window_end_minute_never_triggers():
    # 窗口 22:00-02:00，cron 每天 02:00：结束时刻不含，永远无触发。
    schedule = make("0 2 * * *", "UTC", TimeWindow(22 * 60, 2 * 60))
    engine = ScheduleEngine([schedule])
    assert engine.next_after("s", datetime(2026, 1, 1, tzinfo=UTC)) is None


def test_cross_midnight_uses_trigger_date_not_window_start_date():
    # 仅周二（dow=2）01:30，窗口 22:00-02:00 跨午夜。
    # 周三 01:30 处于"周二开启的窗口"内，但 cron 必须按触发瞬间的当地日期匹配，不得触发。
    schedule = make("30 1 * * 2", "UTC", TimeWindow(22 * 60, 2 * 60))
    start = datetime(2026, 10, 1, 0, 0, tzinfo=UTC)
    end = datetime(2026, 11, 1, 0, 0, tzinfo=UTC)
    triggers = engine_triggers(schedule, start, end)
    # 2026-10-06、13、20、27 均为周二。
    assert triggers == [
        datetime(2026, 10, 6, 1, 30, tzinfo=UTC),
        datetime(2026, 10, 13, 1, 30, tzinfo=UTC),
        datetime(2026, 10, 20, 1, 30, tzinfo=UTC),
        datetime(2026, 10, 27, 1, 30, tzinfo=UTC),
    ]
    # 2026-10-07 是周三 01:30，若错用窗口开始日期（周二）会多出这一项。
    assert datetime(2026, 10, 7, 1, 30, tzinfo=UTC) not in triggers


def test_full_range_dom_is_not_unrestricted():
    # 日字段写完整范围 1-31 不等同于 *：与星期都受限时按并集处理。
    # 2 月没有 30/31 号，"0 0 30-31 2 0" 在 2 月只能靠周日触发；
    # 若把 30-31 误判为无限制，则 2 月只能由星期日字段单独决定（此处恰好相同），
    # 改用 "0 0 1-31 2 5"：1-31 受限与周五并集 → 2 月每天都触发（含非周五）。
    schedule = make("0 12 1-31 2 5", "UTC", TimeWindow(0, 0))
    start = datetime(2026, 2, 1, 0, 0, tzinfo=UTC)
    end = datetime(2026, 3, 1, 0, 0, tzinfo=UTC)
    triggers = engine_triggers(schedule, start, end)
    assert len(triggers) == 28  # 2026 年 2 月每天中午都触发（日或周五并集）
