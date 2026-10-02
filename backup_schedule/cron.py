"""五字段 cron 表达式的解析与匹配。

字段顺序：分 时 日 月 星期。星期 0-6 表示周日至周六。
支持：数字、星号、逗号列表、升序闭区间 a-b、星号或区间后的正整数步长。
步长从字段最小值或区间起点计数。不支持名称、秒字段等扩展语法。
"""

from __future__ import annotations

from datetime import date

# (最小值, 最大值)
_FIELD_RANGES = {
    "minute": (0, 59),
    "hour": (0, 23),
    "day_of_month": (1, 31),
    "month": (1, 12),
    "day_of_week": (0, 6),
}


def _parse_field(text: str, lo: int, hi: int) -> frozenset[int]:
    values: set[int] = set()
    for item in text.split(","):
        if "/" in item:
            base, step_text = item.split("/", 1)
            step = int(step_text)
        else:
            base, step = item, 1
        if base == "*":
            start, end = lo, hi
        elif "-" in base:
            start_text, end_text = base.split("-", 1)
            start, end = int(start_text), int(end_text)
        else:
            start = end = int(base)
        values.update(range(start, end + 1, step))
    return frozenset(values)


class CronSchedule:
    """解析后的五字段 cron（分 时 日 月 星期）。"""

    def __init__(self, expression: str) -> None:
        self.expression = expression
        minute_text, hour_text, dom_text, month_text, dow_text = expression.split()
        self.minutes = _parse_field(minute_text, *_FIELD_RANGES["minute"])
        self.hours = _parse_field(hour_text, *_FIELD_RANGES["hour"])
        self.days_of_month = _parse_field(dom_text, *_FIELD_RANGES["day_of_month"])
        self.months = _parse_field(month_text, *_FIELD_RANGES["month"])
        self.days_of_week = _parse_field(dow_text, *_FIELD_RANGES["day_of_week"])
        # 只有整个字段为单独星号才算无限制；完整范围（如 1-31）不算。
        self.dom_unrestricted = dom_text == "*"
        self.dow_unrestricted = dow_text == "*"

    def matches(self, minute: int, hour: int, day: int, month: int, weekday: int) -> bool:
        """判断某当地日期时间是否匹配。weekday 用 0=周日 … 6=周六。"""
        if minute not in self.minutes or hour not in self.hours or month not in self.months:
            return False
        if self.dom_unrestricted and self.dow_unrestricted:
            return True
        if self.dom_unrestricted:
            return weekday in self.days_of_week
        if self.dow_unrestricted:
            return day in self.days_of_month
        return day in self.days_of_month or weekday in self.days_of_week

    def matches_date(self, d: "date") -> bool:
        """只按 日/月/星期 判断某当地日期是否匹配。"""
        if d.month not in self.months:
            return False
        if self.dom_unrestricted and self.dow_unrestricted:
            return True
        if self.dom_unrestricted:
            return _weekday_sun0(d) in self.days_of_week
        if self.dow_unrestricted:
            return d.day in self.days_of_month
        return d.day in self.days_of_month or _weekday_sun0(d) in self.days_of_week



def _weekday_sun0(d: "date") -> int:
    """0=周日 … 6=周六。"""
    return d.toordinal() % 7
