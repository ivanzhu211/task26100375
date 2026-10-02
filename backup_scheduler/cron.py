"""五字段 cron 表达式解析（分 时 日 月 星期）。"""

from __future__ import annotations

_FIELD_RANGES = {
    "minute": (0, 59),
    "hour": (0, 23),
    "dom": (1, 31),
    "month": (1, 12),
    "dow": (0, 6),
}


def _parse_field(text: str, low: int, high: int) -> frozenset[int]:
    """解析单个字段为取值集合。

    支持：数字、*、逗号列表、升序闭区间 a-b、以及 * 或区间后的正整数步长 /n。
    步长从字段最小值（* 时）或区间起点计数。
    """
    values: set[int] = set()
    for item in text.split(","):
        if "/" in item:
            base, step_text = item.split("/", 1)
            step = int(step_text)
        else:
            base, step = item, None
        if base == "*":
            start, end = low, high
        elif "-" in base:
            start_text, end_text = base.split("-", 1)
            start, end = int(start_text), int(end_text)
        else:
            start = end = int(base)
        if step is None:
            values.update(range(start, end + 1))
        else:
            values.update(range(start, end + 1, step))
    return frozenset(values)


class CronExpression:
    """解析后的五字段 cron 表达式。

    字段顺序：分(0-59) 时(0-23) 日(1-31) 月(1-12) 星期(0-6，0=周日)。
    仅当整个字段为单独星号时视为无限制（用于 日/星期 的组合规则）。
    """

    def __init__(self, expression: str) -> None:
        fields = expression.split()
        if len(fields) != 5:
            raise ValueError(f"cron 表达式必须有 5 个字段: {expression!r}")
        minute_text, hour_text, dom_text, month_text, dow_text = fields
        self.minutes = _parse_field(minute_text, *_FIELD_RANGES["minute"])
        self.hours = _parse_field(hour_text, *_FIELD_RANGES["hour"])
        self.days_of_month = _parse_field(dom_text, *_FIELD_RANGES["dom"])
        self.months = _parse_field(month_text, *_FIELD_RANGES["month"])
        self.days_of_week = _parse_field(dow_text, *_FIELD_RANGES["dow"])
        self.dom_unrestricted = dom_text == "*"
        self.dow_unrestricted = dow_text == "*"

    def date_matches(self, year: int, month: int, day: int, weekday_sun0: int) -> bool:
        """判断公历日期是否满足 月/日/星期 规则。weekday_sun0: 周日=0。"""
        if month not in self.months:
            return False
        if self.dom_unrestricted and self.dow_unrestricted:
            return True
        dom_ok = day in self.days_of_month
        dow_ok = weekday_sun0 in self.days_of_week
        if self.dom_unrestricted:
            return dow_ok
        if self.dow_unrestricted:
            return dom_ok
        return dom_ok or dow_ok
