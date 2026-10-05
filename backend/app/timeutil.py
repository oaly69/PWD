"""全站统一使用 UTC+8（北京时间）。

数据库内一律存 UTC；对外输出时转换为带 +08:00 偏移的 ISO 字符串；
按「天 / 月」统计的边界（配额重置、每日趋势）也按 UTC+8 计算。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

TZ = timezone(timedelta(hours=8), "Asia/Shanghai")
# SQLite 的 date() 修饰符：把 UTC 时间换算到 UTC+8 后再取日期
SQLITE_OFFSET = "+8 hours"


def now() -> datetime:
    return datetime.now(TZ)


def iso(dt: datetime | None) -> str | None:
    """输出带时区偏移的 ISO 时间；数据库读出的无时区时间视为 UTC。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TZ).isoformat(timespec="seconds")


def day_start(days_ago: int = 0) -> datetime:
    """UTC+8 当天 0 点（可往前推若干天），返回 UTC 时间。"""
    d = now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_ago)
    return d.astimezone(timezone.utc)


def month_start() -> datetime:
    return now().replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
