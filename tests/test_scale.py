"""规模与边界：5000 条混合计划的性能、无解终止、跨世纪闰日、同时触发排序。"""

import time
from datetime import datetime, timezone

from backup_schedule import BackupSchedule, CronSchedule, ScheduleEngine
from backup_schedule.schedule import TimeWindow

UTC = timezone.utc
ALL_DAY = TimeWindow(0, 0)
TIMEZONES = ["UTC", "America/New_York", "Australia/Lord_Howe", "Asia/Shanghai", "Europe/Berlin"]


def make(schedule_id, expr, tz, window=ALL_DAY):
    return BackupSchedule(schedule_id, CronSchedule(expr), tz, window)


def build_mixed_fleet():
    schedules = []
    for i in range(2000):  # 每分钟触发
        schedules.append(make(f"per-minute-{i:04}", "* * * * *", TIMEZONES[i % len(TIMEZONES)]))
    for i in range(1000):  # 跨午夜窗口
        schedules.append(make(f"cross-midnight-{i:04}", "*/13 20-23,0-3 * * *",
                              TIMEZONES[i % len(TIMEZONES)], TimeWindow(20 * 60, 4 * 60)))
    for i in range(1000):  # 仅闰日
        schedules.append(make(f"leap-day-{i:04}", "0 0 29 2 *", TIMEZONES[i % len(TIMEZONES)]))
    for i in range(1000):  # 2 月 30 日且星期无限制：无解
        schedules.append(make(f"impossible-{i:04}", "0 0 30 2 *", TIMEZONES[i % len(TIMEZONES)]))
    return schedules


def test_merged_top10_with_5000_schedules_within_5_seconds():
    engine = ScheduleEngine(build_mixed_fleet())
    start = datetime(2099, 6, 1, 0, 0, tzinfo=UTC)  # 查询范围跨越 2100 年
    t0 = time.perf_counter()
    results = engine.upcoming(start)
    elapsed = time.perf_counter() - t0
    assert elapsed < 5.0, f"合并查询耗时 {elapsed:.2f}s"
    assert len(results) == 10
    assert results == sorted(results)  # 按 (UTC, 计划标识) 排序
    assert all(instant > start for instant, _ in results)


def test_impossible_schedules_terminate_with_none():
    engine = ScheduleEngine([
        make("feb30", "0 0 30 2 *", "UTC"),
        make("feb31", "0 0 31 2 *", "UTC"),
        make("apr31", "0 0 31 4 *", "UTC"),
    ])
    start = datetime(2026, 1, 1, tzinfo=UTC)
    assert engine.next_after("feb30", start) is None
    assert engine.next_after("feb31", start) is None
    assert engine.next_after("apr31", start) is None
    assert engine.upcoming(start) == []


def test_leap_day_across_year_2100():
    # 2100 年不是闰年：2099 年查询应跳到 2104-02-29。
    engine = ScheduleEngine([make("leap", "30 12 29 2 *", "UTC")])
    assert engine.next_after("leap", datetime(2099, 1, 1, tzinfo=UTC)) == datetime(2104, 2, 29, 12, 30, tzinfo=UTC)
    assert engine.next_after("leap", datetime(2095, 6, 1, tzinfo=UTC)) == datetime(2096, 2, 29, 12, 30, tzinfo=UTC)


def test_simultaneous_triggers_each_get_an_entry():
    # 12 条计划同一时刻触发：最近 10 次必须各占一项、不漏不重、按标识字典序。
    schedules = [make(f"s{i:02}", "0 12 * * *", "UTC") for i in range(12)]
    engine = ScheduleEngine(schedules)
    results = engine.upcoming(datetime(2026, 1, 1, 0, 0, tzinfo=UTC))
    assert len(results) == 10
    assert all(instant == datetime(2026, 1, 1, 12, 0, tzinfo=UTC) for instant, _ in results)
    assert [sid for _, sid in results] == [f"s{i:02}" for i in range(10)]


def test_same_schedule_contributes_multiple_entries():
    engine = ScheduleEngine([make("m", "* * * * *", "UTC")])
    results = engine.upcoming(datetime(2026, 1, 1, 0, 0, 30, tzinfo=UTC))
    assert len(results) == 10
    assert [sid for _, sid in results] == ["m"] * 10
    minutes = [instant.minute for instant, _ in results]
    assert minutes == list(range(1, 11))  # 严格晚于起点，从 00:01 开始连续 10 分钟


def test_result_strictly_after_start():
    engine = ScheduleEngine([make("a", "0 0 * * *", "UTC")])
    exactly = datetime(2026, 3, 3, 0, 0, tzinfo=UTC)
    assert engine.next_after("a", exactly) == datetime(2026, 3, 4, 0, 0, tzinfo=UTC)
