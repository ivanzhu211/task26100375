"""每日当地时间窗口：包含开始、不包含结束；开始晚于结束表示跨午夜；相等表示全天。"""

from __future__ import annotations


def _parse_hhmm(text: str) -> int:
    parts = text.split(":")
    if len(parts) != 2:
        raise ValueError(f"时间格式应为 HH:MM: {text!r}")
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"非法时间: {text!r}")
    return hour * 60 + minute


class DailyWindow:
    """以“当日分钟数”表示的每日窗口，start/end 均为 0..1439。

    - start < end：start <= t < end
    - start > end：跨午夜，t >= start 或 t < end
    - start == end：全天
    """

    def __init__(self, start: str, end: str) -> None:
        self.start_minute = _parse_hhmm(start)
        self.end_minute = _parse_hhmm(end)

    def contains(self, minute_of_day: int) -> bool:
        """判断某当地分钟是否落在窗口内。"""
        if self.start_minute == self.end_minute:
            return True
        if self.start_minute < self.end_minute:
            return self.start_minute <= minute_of_day < self.end_minute
        return minute_of_day >= self.start_minute or minute_of_day < self.end_minute
