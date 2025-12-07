# logic/backtest_ema_pullback_v2_5.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone, timedelta
from typing import List, Optional, Literal, Union

from data.kline import Kline
from logic.indicators import ema, atr


Side = Literal["LONG", "SHORT"]


@dataclass
class EmaPullbackParamsV2_5:
    # EMA / ATR
    ema_fast_period: int = 21
    ema_slow_period: int = 200
    atr_period: int = 14

    # Risk / TP–SL
    r_multiple: float = 2.0

    # Giờ trade theo New York
    trade_session_ny_start: time = time(4, 0)   # 04:00 NY
    trade_session_ny_end: time = time(20, 0)    # 20:00 NY

    # Filter nhẹ thêm cho V2.5
    min_atr_pct: float = 0.001        # ATR / close >= 0.1% (lọc coin quá ì)
    min_ema_distance_pct: float = 0.0015  # |EMA_fast - EMA_slow| / close >= 0.15% (lọc sideway)
    min_body_atr_ratio: float = 0.20  # |close-open| >= 20% ATR (lọc doji)
    max_pullback_bars: int = 5        # pullback tối đa trong 5 nến

    enable_filters: bool = True


@dataclass
class EntrySignal:
    index: int
    side: Side
    entry_price: float
    sl: float
    tp: float
    atr_value: float


@dataclass
class TradeResult:
    signal: EntrySignal
    exit_index: int
    exit_price: float
    result: str          # WIN / LOSS / BE
    result_r: float      # risk multiple
    entry_time_utc: datetime
    exit_time_utc: datetime


RawKline = Union[list, tuple, Kline]


# ==================================================================
# CONVERT Raw Kliness
# ==================================================================

def convert_raw_klines_to_kline_objects(raw_klines: List[RawKline]) -> List[Kline]:
    candles: List[Kline] = []

    for r in raw_klines:
        if isinstance(r, Kline):
            candles.append(r)
            continue

        open_time_ms = int(r[0])
        close_time_ms = int(r[6])

        k = Kline(
            symbol="",
            interval="",
            open_time=datetime.fromtimestamp(open_time_ms / 1000.0, tz=timezone.utc),
            close_time=datetime.fromtimestamp(close_time_ms / 1000.0, tz=timezone.utc),
            open=float(r[1]),
            high=float(r[2]),
            low=float(r[3]),
            close=float(r[4]),
            volume=float(r[5]),
            quote_volume=float(r[7]) if len(r) > 7 else 0.0,
            trades=int(r[8]) if len(r) > 8 else 0,
            taker_buy_volume=float(r[9]) if len(r) > 9 else 0.0,
            taker_buy_quote_volume=float(r[10]) if len(r) > 10 else 0.0,
            raw=list(r),
        )

        candles.append(k)

    return candles


# ==================================================================
# TIME HANDLE (New York session)
# ==================================================================

def to_newyork_time(dt_utc: datetime) -> datetime:
    """
    Chuyển UTC -> giờ New York.
    Dùng offset -5 để đảm bảo chạy dù không có DST.
    """
    return dt_utc + timedelta(hours=-5)


def is_in_session_ny(dt_utc: datetime, start: time, end: time) -> bool:
    ny = to_newyork_time(dt_utc)
    tt = ny.time()
    return start <= tt <= end


# ==================================================================
# ENTRY SIGNAL
# ==================================================================

def detect_entry_signal(
    idx: int,
    candles: List[Kline],
    ema_fast_list: List[Optional[float]],
    ema_slow_list: List[Optional[float]],
    atr_list: List[Optional[float]],
    params: EmaPullbackParamsV2_5,
) -> Optional[EntrySignal]:

    c = candles[idx]
    ema_f = ema_fast_list[idx]
    ema_s = ema_slow_list[idx]
    atr_v = atr_list[idx]

    if ema_f is None or ema_s is None or atr_v is None:
        return None

    # Filter session
    if not is_in_session_ny(c.close_time, params.trade_session_ny_start, params.trade_session_ny_end):
        return None

    close = c.close
    body = abs(c.close - c.open)

    # FILTER V2.5
    if params.enable_filters:
        if close > 0:
            if (atr_v / close) < params.min_atr_pct:
                return None
            if abs(ema_f - ema_s) / close < params.min_ema_distance_pct:
                return None

        if atr_v > 0 and (body / atr_v) < params.min_body_atr_ratio:
            return None

    trend_up = ema_f > ema_s
    trend_down = ema_f < ema_s

    low = c.low
    high = c.high

    side = None
    entry_price = None

    # LONG SETUP
    if trend_up:
        if low <= ema_f <= high:
            if c.close > c.open and c.close > ema_f:
                side = "LONG"
                entry_price = c.close

    # SHORT SETUP
    if trend_down and side is None:
        if low <= ema_f <= high:
            if c.close < c.open and c.close < ema_f:
                side = "SHORT"
                entry_price = c.close

    if side is None:
        return None

    if side == "LONG":
        sl = entry_price - atr_v
        tp = entry_price + params.r_multiple * atr_v
    else:
        sl = entry_price + atr_v
        tp = entry_price - params.r_multiple * atr_v

    return EntrySignal(
        index=idx,
        side=side,
        entry_price=entry_price,
        sl=sl,
        tp=tp,
        atr_value=atr_v,
    )


# ==================================================================
# EXIT SIMULATION
# ==================================================================

def simulate_trade_exit(
    sig: EntrySignal,
    candles: List[Kline],
    params: EmaPullbackParamsV2_5,
) -> TradeResult:

    entry_idx = sig.index
    entry_price = sig.entry_price
    risk = abs(entry_price - sig.sl)
    if risk == 0:
        risk = 1e-9

    exit_index = len(candles) - 1
    exit_price = candles[-1].close
    result = "BE"
    result_r = 0.0

    if sig.side == "LONG":
        for i in range(entry_idx + 1, len(candles)):
            c = candles[i]
            if c.low <= sig.sl:
                result, result_r = "LOSS", -1.0
                exit_index, exit_price = i, sig.sl
                break
            if c.high >= sig.tp:
                result, result_r = "WIN", params.r_multiple
                exit_index, exit_price = i, sig.tp
                break
        else:
            exit_price = candles[-1].close
            pnl = exit_price - entry_price
            result_r = pnl / risk
            result = "WIN" if pnl > 0 else ("LOSS" if pnl < 0 else "BE")

    else:
        for i in range(entry_idx + 1, len(candles)):
            c = candles[i]
            if c.high >= sig.sl:
                result, result_r = "LOSS", -1.0
                exit_index, exit_price = i, sig.sl
                break
            if c.low <= sig.tp:
                result, result_r = "WIN", params.r_multiple
                exit_index, exit_price = i, sig.tp
                break
        else:
            exit_price = candles[-1].close
            pnl = entry_price - exit_price
            result_r = pnl / risk
            result = "WIN" if pnl > 0 else ("LOSS" if pnl < 0 else "BE")

    return TradeResult(
        signal=sig,
        exit_index=exit_index,
        exit_price=exit_price,
        result=result,
        result_r=result_r,
        entry_time_utc=candles[entry_idx].close_time,
        exit_time_utc=candles[exit_index].close_time,
    )


# ==================================================================
# MAIN BACKTEST
# ==================================================================

def backtest_ema_pullback_v2_5(
    raw_klines: List[RawKline],
    params: EmaPullbackParamsV2_5,
):
    candles = convert_raw_klines_to_kline_objects(raw_klines)
    if not candles:
        return [], candles, [], [], []

    closes = [c.close for c in candles]

    ema_fast_list = ema(closes, params.ema_fast_period)
    ema_slow_list = ema(closes, params.ema_slow_period)
    atr_list = atr(candles, params.atr_period)

    trades = []

    for i in range(len(candles)):
        sig = detect_entry_signal(i, candles, ema_fast_list, ema_slow_list, atr_list, params)
        if sig:
            trades.append(simulate_trade_exit(sig, candles, params))

    return trades, candles, ema_fast_list, ema_slow_list, atr_list
