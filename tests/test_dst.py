"""夏令时与偏移变化测试：America/New_York 与 Australia/Lord_Howe。"""

from datetime import datetime, timedelta, timezone

from backup_schedule import BackupSchedule, CronSchedule, ScheduleEngine
from backup_schedule.schedule import TimeWindow

UTC = timezone.utc
ALL_DAY = TimeWindow(0, 0)


def make(schedule_id, expr, tz):
    return BackupSchedule(schedule_id, CronSchedule(expr), tz, ALL_DAY)


def test_new_york_spring_forward_skips_nonexistent_0230():
    # 2026-03-08 纽约 02:00→03:00，02:30 不存在，应直接跳到 3 月 9 日。
    engine = ScheduleEngine([make("ny", "30 2 * * *", "America/New_York")])
    start = datetime(2026, 3, 7, 12, 0, tzinfo=UTC)
    assert engine.next_after("ny", start) == datetime(2026, 3, 9, 6, 30, tzinfo=UTC)


def test_new_york_fall_back_takes_earlier_occurrence_only():
    # 2026-11-01 纽约 02:00→01:00，01:30 出现两次：UTC 05:30(EDT) 与 06:30(EST)。
    engine = ScheduleEngine([make("ny", "30 1 * * *", "America/New_York")])
    start = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
    first = engine.next_after("ny", start)
    assert first == datetime(2026, 11, 1, 5, 30, tzinfo=UTC)
    # 较早一次之后应直接到次日，不能补出 06:30 的第二次。
    second = engine.next_after("ny", first)
    assert second == datetime(2026, 11, 2, 6, 30, tzinfo=UTC)


def test_new_york_query_starting_between_duplicate_local_times():
    # 查询起点落在两次 01:30 之间（UTC 06:00），不得返回较晚的 06:30 那次。
    engine = ScheduleEngine([make("ny", "30 1 * * *", "America/New_York")])
    between = datetime(2026, 11, 1, 6, 0, tzinfo=UTC)
    assert engine.next_after("ny", between) == datetime(2026, 11, 2, 6, 30, tzinfo=UTC)
    # 恰好落在较早一次上也必须严格晚于起点。
    exactly = datetime(2026, 11, 1, 5, 30, tzinfo=UTC)
    assert engine.next_after("ny", exactly) == datetime(2026, 11, 2, 6, 30, tzinfo=UTC)


def test_lord_howe_half_hour_fall_back():
    # 2026-04-05 Lord Howe 02:00→01:30（+11→+10:30），当地 01:30-01:59 出现两次。
    # 01:45 对应 UTC 04-04 14:45(+11) 与 04-04 15:15(+10:30)，只取较早一次。
    engine = ScheduleEngine([make("lh", "45 1 * * *", "Australia/Lord_Howe")])
    start = datetime(2026, 4, 4, 12, 0, tzinfo=UTC)
    first = engine.next_after("lh", start)
    assert first == datetime(2026, 4, 4, 14, 45, tzinfo=UTC)
    # 起点落在两次之间也不得补出第二次。
    between = datetime(2026, 4, 4, 15, 0, tzinfo=UTC)
    # 下一次是 04-06 01:45(+10:30)，即 UTC 04-05 15:15。
    assert engine.next_after("lh", between) == datetime(2026, 4, 5, 15, 15, tzinfo=UTC)


def test_lord_howe_half_hour_spring_forward():
    # 2026-10-04 Lord Howe 02:00→02:30（+10:30→+11），当地 02:00-02:29 不存在。
    engine = ScheduleEngine([make("lh", "15 2 * * *", "Australia/Lord_Howe")])
    start = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
    # 10-04 的 02:15 被跳过；次日 02:15(+11) 即 UTC 10-04 15:15。
    assert engine.next_after("lh", start) == datetime(2026, 10, 4, 15, 15, tzinfo=UTC)


def test_results_do_not_depend_on_machine_local_timezone(monkeypatch):
    import os
    import time

    monkeypatch.setenv("TZ", "Pacific/Kiritimati")
    time.tzset()
    engine = ScheduleEngine([make("ny", "30 1 * * *", "America/New_York")])
    start = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
    assert engine.next_after("ny", start) == datetime(2026, 11, 1, 5, 30, tzinfo=UTC)
