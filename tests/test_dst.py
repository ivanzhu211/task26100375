"""夏令时切换相关行为：不存在时间跳过、重复时间只取较早一次、半小时偏移。"""

from datetime import datetime, timezone

from backup_scheduler import Schedule, Scheduler


def test_spring_forward_nonexistent_time_skipped():
    # 2026-03-08 纽约 02:00→03:00，02:30 不存在，应跳过到次日 02:30 (EDT, UTC-4)
    s = Schedule("ny-spring", "30 2 * * *", "America/New_York", ("00:00", "00:00"))
    got = s.next_after(datetime(2026, 3, 8, 0, 0, tzinfo=timezone.utc))
    assert got == datetime(2026, 3, 9, 6, 30, tzinfo=timezone.utc)


def test_fall_back_ambiguous_time_takes_earlier():
    # 2026-11-01 纽约 02:00→01:00，01:30 出现两次，取较早一次 (EDT, UTC-4) => 05:30 UTC
    s = Schedule("ny-fall", "30 1 * * *", "America/New_York", ("00:00", "00:00"))
    got = s.next_after(datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc))
    assert got == datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc)


def test_query_between_two_occurrences_does_not_return_second():
    # 查询起点 06:00 UTC 已越过较早一次 (05:30 UTC)，不得补出较晚一次 (06:30 UTC)
    s = Schedule("ny-fall", "30 1 * * *", "America/New_York", ("00:00", "00:00"))
    got = s.next_after(datetime(2026, 11, 1, 6, 0, tzinfo=timezone.utc))
    assert got == datetime(2026, 11, 2, 6, 30, tzinfo=timezone.utc)


def test_fall_back_day_has_single_trigger_per_minute():
    # 回拨当天每分钟 cron：01:30 只出现一次，全天触发数 = 1440 - 60（重复小时只算一次）
    s = Schedule("ny-minute", "* * * * *", "America/New_York", ("00:00", "00:00"))
    scheduler = Scheduler()
    scheduler.add_schedule(s)
    after = datetime(2026, 11, 1, 3, 0, tzinfo=timezone.utc)  # 当地 23:00 (前一天)
    times = [when for when, _ in scheduler.upcoming(after, limit=10)]
    assert len(times) == 10
    assert len(set(times)) == 10  # 无重复
    # 覆盖整个回拨日，统计 01:30 当地墙钟对应的触发次数
    after = datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc)
    count = 0
    cursor = after
    while True:
        nxt = s.next_after(cursor)
        if nxt is None or nxt >= datetime(2026, 11, 3, 0, 0, tzinfo=timezone.utc):
            break
        local = nxt.astimezone(s._tz)
        if local.date().isoformat() == "2026-11-01" and (local.hour, local.minute) == (1, 30):
            count += 1
        cursor = nxt
    assert count == 1


def test_lord_howe_half_hour_spring_forward():
    # 2026-10-04 Lord Howe 02:00→02:30（+10:30→+11:00），02:15 不存在
    s = Schedule("lh-spring", "15 2 * * *", "Australia/Lord_Howe", ("00:00", "00:00"))
    got = s.next_after(datetime(2026, 10, 3, 0, 0, tzinfo=timezone.utc))
    # 次日 02:15 处于夏令时 +11:00 => 2026-10-04 15:15 UTC
    assert got == datetime(2026, 10, 4, 15, 15, tzinfo=timezone.utc)


def test_lord_howe_half_hour_fall_back():
    # 2026-04-05 Lord Howe 02:00(+11)→01:30(+10:30)，01:45 出现两次，取较早一次 +11:00
    s = Schedule("lh-fall", "45 1 * * *", "Australia/Lord_Howe", ("00:00", "00:00"))
    got = s.next_after(datetime(2026, 4, 4, 0, 0, tzinfo=timezone.utc))
    assert got == datetime(2026, 4, 4, 14, 45, tzinfo=timezone.utc)
    # 从两次 01:45 之间查询（较早一次 14:45 UTC、较晚一次 15:15 UTC），不得补出第二次
    # 下一次为 2026-04-06 01:45 (+10:30) => 2026-04-05 15:15 UTC
    got2 = s.next_after(datetime(2026, 4, 4, 14, 50, tzinfo=timezone.utc))
    assert got2 == datetime(2026, 4, 5, 15, 15, tzinfo=timezone.utc)
