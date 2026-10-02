"""备份计划：唯一标识 + cron + IANA 时区 + 每日当地时间窗口。"""

from __future__ import annotations

from dataclasses import dataclass

from .cron import CronSchedule


@dataclass(frozen=True)
class TimeWindow:
    """每日当地时间窗口，精确到分钟。

    [start, end)：含开始、不含结束；start > end 表示跨午夜；
    start == end 表示全天。
    """

    start_minute: int  # 当日 0 点起的分钟数，含
    end_minute: int    # 当日 0 点起的分钟数，不含

    def __post_init__(self) -> None:
        for value in (self.start_minute, self.end_minute):
            if not 0 <= value <= 24 * 60:
                raise ValueError(f"窗口边界超出范围: {value}")

    def contains(self, minute_of_day: int) -> bool:
        if self.start_minute == self.end_minute:
            return True
        if self.start_minute < self.end_minute:
            return self.start_minute <= minute_of_day < self.end_minute
        return minute_of_day >= self.start_minute or minute_of_day < self.end_minute


@dataclass(frozen=True)
class BackupSchedule:
    schedule_id: str
    cron: CronSchedule
    timezone: str  # IANA 时区名
    window: TimeWindow
