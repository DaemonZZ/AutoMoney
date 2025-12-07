# api/market_data.py (chỉ phần liên quan, giả sử các hàm _to_ms, _parse_kline, get_klines đã có)

from datetime import timedelta, timezone
from binance.client import Client

from data.kline import Kline
from data.kline_parser import parse_kline
from data.range_4h_ny import Range4HNY
from .binance_client import get_client
from core.time_utils import trading_midnight, to_utc
from config import DEFAULT_SYMBOL, VN_TZ
from config import TRADING_TIMEZONE
from datetime import datetime, timedelta, timezone

_client = get_client()

def get_klines(symbol, interval, limit=500, start_time=None, end_time=None):
    params = {"symbol": symbol, "interval": interval, "limit": limit}

    if start_time:
        params["startTime"] = int(start_time.timestamp() * 1000)
    if end_time:
        params["endTime"] = int(end_time.timestamp() * 1000)

    raw = _client.get_klines(**params)
    return [parse_kline(symbol, interval, k) for k in raw]

def trading_range_4h() -> tuple[datetime, datetime]:
    """
    Khoảng 4h đầu ngày theo giờ New York:
        NY 00:00 → NY 04:00
    Trả về (start_utc, end_utc)
    """
    start_ny = trading_midnight()
    end_ny = start_ny + timedelta(hours=4)

    return (
        start_ny.astimezone(timezone.utc),
        end_ny.astimezone(timezone.utc),
    )


def get_first_4h_candle_newyork(symbol=DEFAULT_SYMBOL):
    start_utc, end_utc = trading_range_4h()

    raw = _client.get_klines(
        symbol=symbol,
        interval=Client.KLINE_INTERVAL_4HOUR,
        startTime=int(start_utc.timestamp() * 1000),
        endTime=int(end_utc.timestamp() * 1000),
        limit=1
    )

    if not raw:
        return None

    return parse_kline(symbol, Client.KLINE_INTERVAL_4HOUR, raw[0])

# -----------------------------
#  LẤY NẾN 5M MỚI NHẤT
# -----------------------------
def get_latest_5m_candle(symbol: str = DEFAULT_SYMBOL):
    kl = get_klines(symbol, Client.KLINE_INTERVAL_5MINUTE, limit=1)
    return kl[0] if kl else None

def get_first_4h_high_low_newyork(
    symbol: str = DEFAULT_SYMBOL,
    interval: str = Client.KLINE_INTERVAL_5MINUTE,
):
    """
    Lấy giá cao nhất và thấp nhất trong 4 giờ đầu ngày theo giờ New York.
    Đồng thời trả về thời gian theo:
    - New York
    - UTC
    - Việt Nam
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

    start_ms = int(start_utc.timestamp() * 1000)
    end_ms = int(end_utc.timestamp() * 1000)

    # 3) Lấy dữ liệu 5m trong 4 giờ đầu
    raw_klines = _client.get_klines(
        symbol=symbol,
        interval=interval,
        startTime=start_ms,
        endTime=end_ms,
        limit=500,
    )

    if not raw_klines:
        return None

    highs = [float(k[2]) for k in raw_klines]
    lows = [float(k[3]) for k in raw_klines]

    # 4) Build response
    return Range4HNY(
        symbol=symbol,
        high=max(highs),
        low=min(lows),
        count=len(raw_klines),

        start_ny=ny_midnight,
        end_ny=ny_end,

        start_utc=start_utc,
        end_utc=end_utc,

        start_vn=start_utc.astimezone(VN_TZ),
        end_vn=end_utc.astimezone(VN_TZ),
    )


def get_5m_candles_from_4h_to_now_newyork(
        symbol: str = DEFAULT_SYMBOL,
) -> list[Kline] | None:
    """
    Lấy tất cả nến 5m từ 04:00 sáng (giờ New York) hôm nay
    đến thời điểm hiện tại.

    - Nếu hiện tại (New York) < 04:00 -> return None (bỏ qua bước này).
    - Ngược lại -> trả về list[Kline] 5m (đã parse thành object).
    """

    # 1) Giờ hiện tại theo NY
    now_utc = datetime.now(timezone.utc)
    now_ny = now_utc.astimezone(TRADING_TIMEZONE)

    # 2) Xác định mốc 04:00 sáng hôm nay theo NY
    ny_four_am = datetime(
        year=now_ny.year,
        month=now_ny.month,
        day=now_ny.day,
        hour=4,
        minute=0,
        second=0,
        tzinfo=TRADING_TIMEZONE,
    )

    # 3) Nếu hiện tại < 04:00 NY -> bỏ qua
    if now_ny < ny_four_am:
        # Chưa đủ 4h đầu ngày, không lấy gì cả
        return None

    # 4) Convert 4:00 NY và now_NY sang UTC để gọi Binance
    start_utc = ny_four_am.astimezone(timezone.utc)
    end_utc = now_ny.astimezone(timezone.utc)

    start_ms = int(start_utc.timestamp() * 1000)
    end_ms = int(end_utc.timestamp() * 1000)

    # 5) Lấy toàn bộ nến 5m trong khoảng (4h NY -> now)
    # 4h -> 24h sau là 20h, 20h * 12 (5m) = 240 nến -> < 1000, 1 request là đủ
    raw_klines = _client.get_klines(
        symbol=symbol,
        interval=Client.KLINE_INTERVAL_5MINUTE,
        startTime=start_ms,
        endTime=end_ms,
        limit=1000,
    )

    if not raw_klines:
        return []

    # 6) Parse thành list Kline 5m
    candles: list[Kline] = [
        parse_kline(symbol, Client.KLINE_INTERVAL_5MINUTE, k)
        for k in raw_klines
    ]

    # (Optional) Lọc lại chắc chắn theo mở nến trong [4h NY, now NY)
    filtered: list[Kline] = []
    for c in candles:
        ot_ny = c.open_time.astimezone(TRADING_TIMEZONE)
        if ny_four_am <= ot_ny <= now_ny:
            filtered.append(c)

    return filtered

