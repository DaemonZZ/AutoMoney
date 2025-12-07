# api/market_data_futures.py

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from .binance_client import client_futures
from binance.client import Client
import time
from data.kline import Kline
from data.kline_parser import parse_kline
from data.range_4h_ny import Range4HNY
from .binance_client import get_client
from config import DEFAULT_SYMBOL, VN_TZ, TRADING_TIMEZONE

_client = get_client()


# ============================================================
#   FUTURES KLINES (UM)
# ============================================================

def get_futures_klines(
    symbol: str,
    interval: str,
    limit: int = 500,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
) -> list[Kline]:
    """
    Lấy klines từ Binance Futures (UM).
    Dùng client.futures_klines thay vì get_klines (Spot).
    """
    params = {"symbol": symbol, "interval": interval, "limit": limit}

    if start_time:
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        else:
            start_time = start_time.astimezone(timezone.utc)
        params["startTime"] = int(start_time.timestamp() * 1000)

    if end_time:
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)
        else:
            end_time = end_time.astimezone(timezone.utc)
        params["endTime"] = int(end_time.timestamp() * 1000)

    # ⚠️ KHÁC SPOT: dùng futures_klines
    raw = _client.futures_klines(**params)
    return [parse_kline(symbol, interval, k) for k in raw]


# ============================================================
#   NẾN 5M MỚI NHẤT (FUTURES)
# ============================================================

def get_latest_5m_candle_futures(symbol: str = DEFAULT_SYMBOL) -> Optional[Kline]:
    kl = get_futures_klines(symbol, Client.KLINE_INTERVAL_5MINUTE, limit=1)
    return kl[0] if kl else None


# ============================================================
#   RANGE 4H ĐẦU NGÀY (NY) – TỪ FUTURES
# ============================================================

def get_first_4h_high_low_newyork_futures(
    symbol: str = DEFAULT_SYMBOL,
    interval: str = Client.KLINE_INTERVAL_5MINUTE,
) -> Optional[Range4HNY]:
    """
    Lấy giá cao nhất / thấp nhất trong 4h đầu ngày (00:00 → 04:00 New York)
    từ dữ liệu FUTURES (UM), dùng nến 5m.
    """

    # 1) 00:00 hôm nay theo giờ New York
    now_utc = datetime.now(timezone.utc)
    now_ny = now_utc.astimezone(TRADING_TIMEZONE)

    ny_midnight = datetime(
        year=now_ny.year,
        month=now_ny.month,
        day=now_ny.day,
        hour=0,
        minute=0,
        second=0,
        tzinfo=TRADING_TIMEZONE,
    )

    ny_end = ny_midnight + timedelta(hours=4)

    # 2) Convert sang UTC
    start_utc = ny_midnight.astimezone(timezone.utc)
    end_utc = ny_end.astimezone(timezone.utc)

    # 3) Lấy dữ liệu 5m FUTURES trong 4h đầu
    klines = get_futures_klines(
        symbol=symbol,
        interval=interval,
        start_time=start_utc,
        end_time=end_utc,
        limit=500,
    )

    if not klines:
        return None

    highs = [c.high for c in klines]
    lows = [c.low for c in klines]

    # 4) Gói vào Range4HNY object
    return Range4HNY(
        symbol=symbol,
        high=max(highs),
        low=min(lows),
        count=len(klines),

        start_ny=ny_midnight,
        end_ny=ny_end,

        start_utc=start_utc,
        end_utc=end_utc,

        start_vn=start_utc.astimezone(VN_TZ),
        end_vn=end_utc.astimezone(VN_TZ),
    )


# ============================================================
#   LẤY TẤT CẢ NẾN 5M TỪ 4H NY → HIỆN TẠI (FUTURES)
# ============================================================

def get_5m_candles_from_4h_to_now_newyork_futures(
    symbol: str = DEFAULT_SYMBOL,
) -> list[Kline] | None:
    """
    Lấy tất cả nến 5m FUTURES từ 04:00 sáng (New York) hôm nay tới thời điểm hiện tại.

    - Nếu giờ New York hiện tại < 04:00 → return None (bỏ qua bước này).
    - Ngược lại → trả về list[Kline] 5m (đã parse).
    """

    # 1) Giờ hiện tại theo NY
    now_utc = datetime.now(timezone.utc)
    now_ny = now_utc.astimezone(TRADING_TIMEZONE)

    # 2) Mốc 04:00 NY hôm nay
    ny_four_am = datetime(
        year=now_ny.year,
        month=now_ny.month,
        day=now_ny.day,
        hour=4,
        minute=0,
        second=0,
        tzinfo=TRADING_TIMEZONE,
    )

    # 3) Nếu hiện tại < 04:00 → bỏ qua
    if now_ny < ny_four_am:
        return None

    # 4) Convert sang UTC
    start_utc = ny_four_am.astimezone(timezone.utc)
    end_utc = now_ny.astimezone(timezone.utc)

    # 5) Lấy 5m FUTURES trong khoảng này
    candles = get_futures_klines(
        symbol=symbol,
        interval=Client.KLINE_INTERVAL_5MINUTE,
        start_time=start_utc,
        end_time=end_utc,
        limit=1000,
    )

    if not candles:
        return []

    # 6) Optional: lọc lại theo NY cho chắc
    filtered: list[Kline] = []
    for c in candles:
        ot_ny = c.open_time.astimezone(TRADING_TIMEZONE)
        if ny_four_am <= ot_ny <= now_ny:
            filtered.append(c)

    return filtered

def fetch_recent_futures_klines_by_days(symbol: str, interval: str, days: int):
    """
    Fetch lịch sử futures nhiều ngày, theo batch để tránh lỗi limit.
    Mỗi batch tối đa 1500 nến.

    Trả về list raw klines.
    """

    limit = 1500  # Binance max limit
    ms_per_candle = interval_to_ms(interval)

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)

    all_klines = []

    while start_ms < end_ms:
        params = {
            "symbol": symbol.upper(),
            "interval": interval,
            "startTime": start_ms,
            "endTime": end_ms,
            "limit": limit
        }

        # CALL API
        try:
            chunk = client_futures.futures_klines(**params)
        except Exception as e:
            print(f"[ERROR] fetch {symbol}: {e}")
            break

        if not chunk:
            break

        all_klines.extend(chunk)

        # next start = last candle close time + 1ms
        last_close = chunk[-1][6]  # closeTime
        start_ms = last_close + 1

        time.sleep(0.25)  # tránh bị ban

    return all_klines


# ---------------------------------------------------------
# Helper: convert interval (e.g. "5m") -> milliseconds
# ---------------------------------------------------------
def interval_to_ms(interval: str) -> int:
    unit = interval[-1]
    num = int(interval[:-1])

    if unit == "m":
        return num * 60 * 1000
    if unit == "h":
        return num * 60 * 60 * 1000
    if unit == "d":
        return num * 24 * 60 * 60 * 1000

    raise ValueError(f"Interval not supported: {interval}")