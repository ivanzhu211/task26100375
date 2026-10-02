"""日/星期并集 + 跨午夜窗口：与有限区间内独立逐分钟枚举的期望完全一致。"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from backup_scheduler import Schedule, Scheduler

UTC = timezone.utc


def brute_force(schedule: Schedule, after: datetime, limit: int) -> list[datetime]:
    """独立的逐分钟枚举参考实现：逐个 UTC 分钟检查当地 cron 与窗口。

    同一当地日期+分钟只取 UTC 较早的一次（后一次直接跳过）。
    """
    tz = ZoneInfo(schedule.timezone_name)
    cron = schedule.cron
    deadline = after + timedelta(days=2928)
    cursor = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
    seen_local: set[tuple] = set()
    out: list[datetime] = []
    while cursor < deadline and len(out) < limit:
        local = cursor.astimezone(tz)
        key = (local.year, local.month, local.day, local.hour, local.minute)
        if key not in seen_local:
            seen_local.add(key)
            weekday_sun0 = (local.weekday() + 1) % 7
            if (
                local.minute in cron.minutes
                and local.hour in cron.hours
                and cron.date_matches(local.year, local.month, local.day, weekday_sun0)
                and schedule.window.contains(local.hour * 60 + local.minute)
            ):
                out.append(cursor)
        cursor += timedelta(minutes=1)
    return out


def collect(schedule: Schedule, after: datetime, limit: int) -> list[datetime]:
    out: list[datetime] = []
    cursor = after
    for _ in range(limit):
        nxt = schedule.next_after(cursor)
        assert nxt is not None, "期望在 2928 天内仍有触发"
        out.append(nxt)
        cursor = nxt
    return out


def test_matches_brute_force_with_union_and_overnight_window():
    # 日/星期并集：每月 5、20 日 或 周一/周四；跨午夜窗口 20:30-04:15；跨夏令时区间
    schedule = Schedule(
        "union-overnight", "*/7 3,22 5,20 * 1,4", "America/New_York", ("20:30", "04:15")
    )
    after = datetime(2026, 2, 20, 12, 34, 56, tzinfo=UTC)
    expected = brute_force(schedule, after, 40)
    got = collect(schedule, after, 40)
    assert got == expected
    assert len(got) == 40


def test_matches_brute_force_full_range_day_is_restricted():
    # 日填完整范围 1-31 不等同于单独星号：与星期取并集后几乎每天触发
    schedule = Schedule(
        "full-dom", "0 6 1-31 * 6", "Asia/Shanghai", ("00:00", "00:00")
    )
    after = datetime(2026, 3, 1, 0, 0, tzinfo=UTC)
    expected = brute_force(schedule, after, 30)
    assert collect(schedule, after, 30) == expected


def test_window_end_minute_does_not_trigger():
    # 窗口 22:00-02:00：22:00（开始，包含）可触发，02:00（结束，不包含）不触发
    schedule = Schedule("end-exclusive", "0 2,22 * * *", "UTC", ("22:00", "02:00"))
    after = datetime(2026, 5, 1, 0, 0, tzinfo=UTC)
    got = schedule.next_after(after)
    assert got == datetime(2026, 5, 1, 22, 0, tzinfo=UTC)
    # 连续取 5 次，确认每天只触发 22:00，永不落在 02:00
    times = collect(schedule, after, 5)
    assert all(t.hour == 22 for t in times)
    assert len(times) == 5


def test_overnight_window_uses_trigger_date_weekday_not_window_start():
    # 仅周日触发 + 跨午夜窗口 23:00-02:00：
    # 周日 23:xx 与 周日 01:xx 可触发；周一 01:xx（窗口跨自周日）不得触发。
    schedule = Schedule("sun-only", "0,30 1,23 * * 0", "UTC", ("23:00", "02:00"))
    after = datetime(2026, 10, 4, 0, 0, tzinfo=UTC)  # 2026-10-04 是周日
    times = collect(schedule, after, 6)
    assert times == [
        datetime(2026, 10, 4, 1, 0, tzinfo=UTC),
        datetime(2026, 10, 4, 1, 30, tzinfo=UTC),
        datetime(2026, 10, 4, 23, 0, tzinfo=UTC),
        datetime(2026, 10, 4, 23, 30, tzinfo=UTC),
        datetime(2026, 10, 11, 1, 0, tzinfo=UTC),
        datetime(2026, 10, 11, 1, 30, tzinfo=UTC),
    ]
    assert all(t.weekday() != 0 or t.hour != 1 for t in times)  # 周一 01 点不出现


def test_outside_window_discarded_not_postponed():
    # 08:00 在窗口外被丢弃（不顺延到 09:00），当天 10:00 触发
    schedule = Schedule("discard", "0 8,10 * * *", "UTC", ("09:00", "17:00"))
    got = schedule.next_after(datetime(2026, 5, 1, 0, 0, tzinfo=UTC))
    assert got == datetime(2026, 5, 1, 10, 0, tzinfo=UTC)


def test_result_strictly_after_start():
    schedule = Schedule("strict", "0 12 * * *", "UTC", ("00:00", "00:00"))
    got = schedule.next_after(datetime(2026, 5, 1, 12, 0, tzinfo=UTC))
    assert got == datetime(2026, 5, 2, 12, 0, tzinfo=UTC)


def test_merged_upcoming_matches_single_plan_sequence():
    scheduler = Scheduler()
    schedule = Schedule("solo", "*/3 1-5 2,15 * 2,5", "Europe/Berlin", ("23:15", "05:45"))
    scheduler.add_schedule(schedule)
    after = datetime(2026, 1, 15, 8, 0, tzinfo=UTC)
    merged = [when for when, _ in scheduler.upcoming(after, limit=10)]
    assert merged == brute_force(schedule, after, 10)
