# api/market_data_futures.py

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from binance.client import Client

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
