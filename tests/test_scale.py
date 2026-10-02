"""规模与边界：5000 条计划性能、无解终止、跨世纪闰日、并发触发排序稳定性。"""

import os
import time
from datetime import datetime, timedelta, timezone

from backup_scheduler import Schedule, Scheduler

UTC = timezone.utc

TIMEZONES = [
    "UTC",
    "America/New_York",
    "Australia/Lord_Howe",
    "Asia/Shanghai",
    "Europe/Berlin",
    "Pacific/Chatham",
]


def build_scheduler(count: int) -> Scheduler:
    scheduler = Scheduler()
    for i in range(count):
        kind = i % 4
        tz = TIMEZONES[i % len(TIMEZONES)]
        if kind == 0:
            # 每分钟触发，全天窗口
            schedule = Schedule(f"every-minute-{i:04d}", "* * * * *", tz, ("00:00", "00:00"))
        elif kind == 1:
            # 跨午夜窗口
            schedule = Schedule(f"overnight-{i:04d}", "*/13 * * * *", tz, ("21:45", "03:20"))
        elif kind == 2:
            # 仅闰日触发
            schedule = Schedule(f"leap-{i:04d}", "0 0 29 2 *", tz, ("00:00", "00:00"))
        else:
            # 无解：2 月 30 日且星期无限制
            schedule = Schedule(f"impossible-{i:04d}", "0 0 30 2 *", tz, ("00:00", "00:00"))
        scheduler.add_schedule(schedule)
    return scheduler


def test_5000_schedules_merged_query_within_5_seconds():
    scheduler = build_scheduler(5000)
    after = datetime(2026, 10, 3, 0, 0, tzinfo=UTC)
    start = time.perf_counter()
    results = scheduler.upcoming(after, limit=10)
    elapsed = time.perf_counter() - start
    assert elapsed < 5.0, f"合并查询耗时 {elapsed:.2f}s，超过 5s"
    assert len(results) == 10
    assert results == sorted(results, key=lambda item: (item[0], item[1]))


def test_impossible_schedule_terminates_with_none():
    scheduler = build_scheduler(5000)
    after = datetime(2026, 10, 3, 0, 0, tzinfo=UTC)
    start = time.perf_counter()
    assert scheduler.next_run("impossible-0003", after) is None
    assert scheduler.next_run("impossible-4999", after) is None
    elapsed = time.perf_counter() - start
    assert elapsed < 5.0, f"无解计划判定耗时 {elapsed:.2f}s"


def test_leap_day_across_year_2100():
    # 2100 年不是闰年：2096-02-29 之后应为 2104-02-29
    schedule = Schedule("leap-century", "30 6 29 2 *", "UTC", ("00:00", "00:00"))
    got = schedule.next_after(datetime(2096, 3, 1, 0, 0, tzinfo=UTC))
    assert got == datetime(2104, 2, 29, 6, 30, tzinfo=UTC)


def test_search_horizon_2928_days_exclusive(monkeypatch):
    # 截止点 = 起点 + 2928*86400 秒（不包含）。通过缩小窗口直接验证边界语义：
    # 触发点恰好在截止点上时被排除，早 1 秒则被包含。
    import backup_scheduler.schedule as schedule_module

    schedule = Schedule("horizon", "0 0 1 1 *", "UTC", ("00:00", "00:00"))
    monkeypatch.setattr(schedule_module, "SEARCH_DAYS", 365)
    after = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    target = datetime(2027, 1, 1, 0, 0, tzinfo=UTC)  # 恰好 365 天后 = 截止点
    assert schedule.next_after(after) is None  # 截止点不包含
    # 起点晚 1 秒：截止点越过 target，target 被包含
    assert schedule.next_after(after + timedelta(seconds=1)) == target


def test_simultaneous_triggers_top10_complete_and_stable():
    scheduler = Scheduler()
    # 12 条计划完全相同的触发时刻，字典序逆序加入
    for i in range(12):
        scheduler.add_schedule(Schedule(f"sim-{11 - i:02d}", "0 * * * *", "UTC", ("00:00", "00:00")))
    after = datetime(2026, 10, 3, 0, 30, tzinfo=UTC)
    results = scheduler.upcoming(after, limit=10)
    # 最近 10 次：01:00 时刻 12 条计划中的字典序前 10 条，不漏不重
    assert len(results) == 10
    expected_ids = sorted(f"sim-{i:02d}" for i in range(12))[:10]
    assert [sid for _, sid in results] == expected_ids
    assert all(when == datetime(2026, 10, 3, 1, 0, tzinfo=UTC) for when, _ in results)
    assert len({(when, sid) for when, sid in results}) == 10
    # 再查一次结果一致（排序稳定、确定）
    assert scheduler.upcoming(after, limit=10) == results


def test_results_independent_of_machine_timezone(monkeypatch):
    monkeypatch.setenv("TZ", "Pacific/Kiritimati")
    time.tzset()
    scheduler = Scheduler()
    scheduler.add_schedule(Schedule("tz-indep", "15 4 * * *", "America/New_York", ("00:00", "00:00")))
    got = scheduler.next_run("tz-indep", datetime(2026, 10, 3, 0, 0, tzinfo=UTC))
    assert got == datetime(2026, 10, 3, 8, 15, tzinfo=UTC)
    monkeypatch.undo()
    time.tzset()
