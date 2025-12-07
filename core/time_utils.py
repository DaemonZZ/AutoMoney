# core/time_utils.py
from __future__ import annotations

from datetime import datetime, timedelta, date, timezone
from zoneinfo import ZoneInfo

from config import TRADING_TIMEZONE


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_trading_tz() -> datetime:
    """Giờ hiện tại theo timezone giao dịch (New York)."""
    return now_utc().astimezone(TRADING_TIMEZONE)


def trading_midnight(dt_utc: datetime | None = None) -> datetime:
    """
    Lấy 00:00 (midnight) theo giờ New York cho ngày hiện tại (hoặc cho dt_utc).
    Trả về datetime có tzinfo = TRADING_TIMEZONE.
    """
    if dt_utc is None:
        dt_utc = now_utc()

    dt_trading = dt_utc.astimezone(TRADING_TIMEZONE)
    return datetime(
        year=dt_trading.year,
        month=dt_trading.month,
        day=dt_trading.day,
        hour=0,
        minute=0,
        second=0,
        tzinfo=TRADING_TIMEZONE,
    )


def trading_day_bounds(dt_utc: datetime | None = None) -> tuple[datetime, datetime]:
    """
    Lấy khoảng [00:00, 24:00) của 1 ngày giao dịch theo giờ New York.
    Trả về (start_trading_tz, end_trading_tz) – cả hai đều ở TRADING_TIMEZONE.
    """
    start = trading_midnight(dt_utc)
    end = start + timedelta(days=1)
    return start, end


def to_utc(dt) -> datetime:
    """
    Chuyển bất kỳ datetime có tzinfo về UTC.
    Nếu dt không có tzinfo, coi như đã là UTC.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_trading_tz(dt) -> datetime:
    """
    Chuyển bất kỳ datetime UTC sang trading timezone (New York).
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TRADING_TIMEZONE)
