"""进程内计划注册表：单条查询与多计划合并查询。"""

from __future__ import annotations

import heapq
from datetime import datetime

from backup_scheduler.schedule import Schedule


class Scheduler:
    """保存全部计划，提供下一次触发与合并最近 N 次触发查询。"""

    def __init__(self) -> None:
        self._schedules: dict[str, Schedule] = {}

    def add_schedule(self, schedule: Schedule) -> None:
        self._schedules[schedule.schedule_id] = schedule

    def remove_schedule(self, schedule_id: str) -> None:
        self._schedules.pop(schedule_id, None)

    def next_run(self, schedule_id: str, after: datetime) -> datetime | None:
        """单条计划的下一次触发 UTC 时刻（严格晚于 after）。"""
        schedule = self._schedules.get(schedule_id)
        if schedule is None:
            raise KeyError(f"未知计划: {schedule_id!r}")
        return schedule.next_after(after)

    def upcoming(self, after: datetime, limit: int = 10) -> list[tuple[datetime, str]]:
        """所有计划合并后的最近 limit 次触发，按 (UTC 时间, 计划标识字典序) 排序。

        同一计划可贡献多次；不同计划同时触发各占一项。
        """
        if limit <= 0:
            return []
        heap: list[tuple[datetime, str]] = []
        for schedule_id, schedule in self._schedules.items():
            first = schedule.next_after(after)
            if first is not None:
                heap.append((first, schedule_id))
        heapq.heapify(heap)

        results: list[tuple[datetime, str]] = []
        while heap and len(results) < limit:
            when, schedule_id = heapq.heappop(heap)
            results.append((when, schedule_id))
            nxt = self._schedules[schedule_id].next_after(when)
            if nxt is not None:
                heapq.heappush(heap, (nxt, schedule_id))
        return results
