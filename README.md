# 备份计划时间求值库

纯 Python 库（仅标准库），由上层直接调用，不做接口层；计划保存在进程内。
只计算触发时间，不执行备份。

## 功能

- 五字段 cron（分 时 日 月 星期），支持数字、`*`、逗号列表、升序闭区间、
  星号或区间后的正整数步长；星期 0-6 表示周日至周六。
- 日/星期规则：仅整个字段为单独 `*` 才算无限制；两者都受限时满足任一即可，
  仅一个受限时必须满足该项；分、时、月始终必须匹配。
- 每日当地时间窗口：含开始、不含结束；开始晚于结束表示跨午夜；两者相等表示全天；
  窗口外的触发直接丢弃，不顺延；跨午夜按触发瞬间的当地日期匹配 cron。
- 夏令时：不存在的时间跳过；回拨产生的同名当地时刻只取 UTC 较早一次，
  即使查询起点已越过较早一次也不补出较晚一次；支持非整小时偏移变化
  （如 Australia/Lord_Howe 的 30 分钟）。
- 查询起点为任意 UTC 瞬时，结果严格晚于起点；搜索截止点为起点 + 2928 天
  （每天 86400 秒），不含截止点。
- 合并查询返回所有计划的最近 10 次触发，按 (UTC 时间, 计划标识字典序) 排序；
  同一计划可贡献多次，不同计划同时触发各占一项。

## 用法

```python
from datetime import datetime, timezone
from backup_schedule import BackupSchedule, CronSchedule, ScheduleEngine
from backup_schedule.schedule import TimeWindow

engine = ScheduleEngine()
engine.add(BackupSchedule(
    schedule_id="nightly-us",
    cron=CronSchedule("30 2 * * *"),          # 每天当地 02:30
    timezone="America/New_York",              # IANA 时区
    window=TimeWindow(22 * 60, 4 * 60),       # 22:00-04:00 跨午夜窗口
))

start = datetime(2026, 3, 7, 12, 0, tzinfo=timezone.utc)
engine.next_after("nightly-us", start)  # 单条计划下一次触发（UTC 或 None）
engine.upcoming(start)                  # 全部计划合并的最近 10 次 [(UTC, id), ...]
```

- `TimeWindow(start_minute, end_minute)`：当日 0 点起的分钟数；`TimeWindow(0, 0)` 表示全天。
- 查询起点传 naive datetime 时按 UTC 处理；所有结果均为带 `timezone.utc` 的确定瞬时，
  不受运行机器默认时区影响。
- `ScheduleEngine.add/remove` 可增删计划；本次不考虑并发修改与持久化恢复。

## 运行测试

```bash
python3 -m pytest tests/ -q
```

测试覆盖：
- `tests/test_dst.py`：纽约春跳/回拨、两次同名当地时刻之间起查、Lord Howe 半小时偏移、
  结果不依赖机器本地时区。
- `tests/test_window_union.py`：日/星期并集 + 跨午夜窗口与独立逐分钟枚举完全一致、
  窗口结束时刻不触发、跨午夜不沿用前一日星期、完整范围日字段不等同于 `*`。
- `tests/test_scale.py`：5000 条混合计划（每分钟/跨午夜/仅闰日/2 月 30 日无解）
  合并最近 10 次 < 5 秒、无解终止、跨 2100 年闰日（2100 非闰年）、
  同时触发不漏不重且排序稳定、结果严格晚于起点。
