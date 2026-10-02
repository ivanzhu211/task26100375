# task26100375

备份计划时间求值库（纯 Python，仅标准库，进程内保存计划）。只计算触发时间，不执行备份。

## 环境要求

- Python 3.9+（依赖标准库 `zoneinfo`；本库在 Python 3.14 上验证通过）
- 系统需有 IANA 时区数据（macOS/Linux 自带；Windows 需 `pip install tzdata`）
- 运行测试需 `pytest`

## 使用方式

```python
from datetime import datetime, timezone
from backup_scheduler import Schedule, Scheduler

scheduler = Scheduler()
scheduler.add_schedule(Schedule(
    schedule_id="nightly-us",
    cron="30 2 * * *",                 # 分 时 日 月 星期（星期 0=周日）
    timezone="America/New_York",       # IANA 时区
    window=("22:00", "06:00"),         # 每日当地窗口：含开始、不含结束；开始>结束为跨午夜；相等为全天
))

# 单条计划下一次触发（严格晚于起点；2928 天内无则返回 None）
scheduler.next_run("nightly-us", datetime(2026, 10, 3, tzinfo=timezone.utc))

# 所有计划合并后的最近 10 次触发，按 (UTC 时间, 计划标识字典序) 排序
scheduler.upcoming(datetime(2026, 10, 3, tzinfo=timezone.utc), limit=10)
```

- 所有返回结果均为带 `timezone.utc` 时区的 `datetime`，与运行机器默认时区无关。
- cron 支持数字、`*`、逗号列表、升序闭区间 `a-b`、以及 `*` 或区间后的步长 `/n`。
- 日与星期：两者均为单独 `*` 时不限日期；仅一个受限时必须满足该项；都受限时满足任一即可。
- 夏令时：前进造成的不存在时间直接跳过；回拨造成的重复时间只取 UTC 较早的一次。
- 窗口外的触发直接丢弃，不顺延。

## 运行测试

```bash
python3 -m pytest tests/ -q
```

## 代码结构

- `backup_scheduler/cron.py` — 五字段 cron 解析与日期匹配规则
- `backup_scheduler/window.py` — 每日时间窗口（含跨午夜）
- `backup_scheduler/schedule.py` — 单条计划的下一次触发求值（DST 解析、2928 天搜索界）
- `backup_scheduler/scheduler.py` — 进程内注册表与多计划合并查询（堆合并）
- `tests/` — DST、日/星期并集与跨午夜窗口对照逐分钟枚举、规模与边界测试
