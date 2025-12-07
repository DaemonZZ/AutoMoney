# logic/backtest_ema_pullback_v2.py

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, date
from typing import List
from zoneinfo import ZoneInfo

from api.market_data import get_klines
from binance.client import Client

from logic.ema_pullback_v2 import (
    CandleWithInd,
    EntrySignal,
    EmaPullbackParams,
    find_ema_pullback_entries_v2,
)


# ===========================
#   KẾT QUẢ 1 NGÀY
# ===========================

@dataclass
class DayResult:
    ny_date: date
    candles: List[CandleWithInd]
    entries: List[EntrySignal]


# ===========================
#   EMA / ATR UTILS
# ===========================

def calc_ema(values: List[float], period: int) -> List[float]:
    if period <= 0 or len(values) == 0:
        return [None] * len(values)

    ema = [None] * len(values)
    alpha = 2 / (period + 1)

    if len(values) < period:
        return [None] * len(values)

    sma = sum(values[:period]) / period
    ema[period - 1] = sma

    for i in range(period, len(values)):
        ema[i] = alpha * values[i] + (1 - alpha) * ema[i - 1]

    return ema


def calc_atr(highs, lows, closes, period: int):
    n = len(highs)
    trs = [0.0] * n

    for i in range(n):
        if i == 0:
            trs[i] = highs[i] - lows[i]
        else:
            tr1 = highs[i] - lows[i]
            tr2 = abs(highs[i] - closes[i - 1])
            tr3 = abs(lows[i] - closes[i - 1])
            trs[i] = max(tr1, tr2, tr3)

    return calc_ema(trs, period)


# ===========================
#   BUILD CANDLE WITH IND
# ===========================

def build_candles_with_ind(klines, params: EmaPullbackParams):
    closes = [k.close for k in klines]
    highs  = [k.high  for k in klines]
    lows   = [k.low   for k in klines]

    ema_fast = calc_ema(closes, params.ema_fast_period)
    ema_slow = calc_ema(closes, params.ema_slow_period)
    atr      = calc_atr(highs, lows, closes, params.atr_period)

    out = []

    for i, k in enumerate(klines):
        if ema_fast[i] is None or ema_slow[i] is None or atr[i] is None:
            continue

        out.append(
            CandleWithInd(
                open_time=k.open_time,
                open=k.open,
                high=k.high,
                low=k.low,
                close=k.close,
                ema_fast=ema_fast[i],
                ema_slow=ema_slow[i],
                atr=atr[i],
            )
        )

    return out


# ===========================
#   LỌC GIỜ TRADE NY
# ===========================

def is_in_trading_session(dt_utc: datetime, tz_ny: ZoneInfo):
    ny = dt_utc.astimezone(tz_ny)
    return 4 <= ny.hour < 20


# ===========================
#   FETCH 5M CHO 1 NGÀY NY
# ===========================

def fetch_5m_klines_for_day(symbol: str, ny_date: date, tz_ny: ZoneInfo):
    start_ny = datetime(ny_date.year, ny_date.month, ny_date.day, 0, 0, tzinfo=tz_ny)
    end_ny = start_ny + timedelta(days=1) - timedelta(milliseconds=1)

    start_utc = start_ny.astimezone(timezone.utc)
    end_utc   = end_ny.astimezone(timezone.utc)

    return get_klines(
        symbol,
        Client.KLINE_INTERVAL_5MINUTE,
        limit=1000,
        start_time=start_utc,
        end_time=end_utc,
    )


# ===========================
#   BACKTEST CHÍNH
# ===========================

def backtest_ema_pullback_v2(
    symbol: str,
    interval: str,
    lookback_days: int,
    params: EmaPullbackParams,
    tz_ny: ZoneInfo,
    tz_vn: ZoneInfo,
) -> List[DayResult]:

    results = []
    today_ny = datetime.now(timezone.utc).astimezone(tz_ny).date()

    for i in range(lookback_days):
        day = today_ny - timedelta(days=i)

        # fetch
        klines = fetch_5m_klines_for_day(symbol, day, tz_ny)
        if not klines:
            results.append(DayResult(day, [], []))
            continue

        candles = build_candles_with_ind(klines, params)
        if not candles:
            results.append(DayResult(day, [], []))
            continue

        # find entries
        entries = find_ema_pullback_entries_v2(candles, params)

        filtered = []
        for sig in entries:
            c = candles[sig.index]

            if is_in_trading_session(c.open_time, tz_ny):
                sig.time_utc = c.open_time
                sig.time_ny  = c.open_time.astimezone(tz_ny)
                sig.time_vn  = c.open_time.astimezone(tz_vn)

                # attach indicator for printing
                sig.ema_fast = c.ema_fast
                sig.ema_slow = c.ema_slow
                sig.atr      = c.atr

                filtered.append(sig)

        results.append(DayResult(day, candles, filtered))

    return results
