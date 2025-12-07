# logic/backtest_ema_pullback_v4_pro.py

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Tuple
from datetime import datetime, timezone


# ===========================
# Cấu trúc Kline chuẩn
# ===========================
@dataclass
class SimpleKline:
    open_time: datetime
    close_time: datetime
    open: float
    high: float
    low: float
    close: float


# ===========================
# Kết quả mô phỏng
# ===========================
@dataclass
class TradeResult:
    index: int
    side: str
    entry_time: datetime
    exit_time: datetime
    entry: float
    sl: float
    tp: float
    exit_price: float
    result_r: float   # R-multiple
    atr: float


# ===========================
# PARAMS V4 PRO
# ===========================
@dataclass
class BacktestParamsV4Pro:
    ema_fast: int = 21
    ema_slow: int = 200
    atr_period: int = 14
    r_multiple: float = 2.0

    # Các filter bổ sung:
    min_trend_strength: float = 0.0
    max_pullback_ratio: float = 0.5


# ===========================
# EMA tính nhanh
# ===========================
def ema(values: List[float], period: int) -> List[float]:
    if len(values) == 0:
        return []

    alpha = 2 / (period + 1)
    out = [values[0]]

    for v in values[1:]:
        out.append(out[-1] + alpha * (v - out[-1]))
    return out


# ===========================
# ATR tính nhanh
# ===========================
def compute_atr(kl: List[SimpleKline], length: int) -> List[float]:
    out = [0.0] * len(kl)
    if len(kl) < 2:
        return out

    trs = []
    for i in range(1, len(kl)):
        high = kl[i].high
        low = kl[i].low
        prev_close = kl[i - 1].close
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)

    # Smooth ATR exponential
    atr = []
    alpha = 1 / length
    atr.append(trs[0])
    for t in trs[1:]:
        atr.append(atr[-1] + alpha * (t - atr[-1]))

    out[1:] = atr
    return out


# ===========================
# ✨ EMA Pullback V4 Pro ✨
# ===========================
def detect_entry_v4(
    i: int,
    candles: List[SimpleKline],
    ema_fast: List[float],
    ema_slow: List[float],
    atr_list: List[float],
    params: BacktestParamsV4Pro,
) -> Optional[Tuple[str, float, float]]:
    """
    Return: (side, sl, tp)
    """

    c = candles[i]
    ef = ema_fast[i]
    es = ema_slow[i]

    # Trend filter
    trend_strength = abs(ef - es)
    if trend_strength < params.min_trend_strength:
        return None

    # Trend up
    if ef > es:
        # pullback = giá chạm EMA nhanh rồi bật lên
        if candles[i - 1].close < ef and c.close > ef:
            sl = c.close - atr_list[i]
            tp = c.close + params.r_multiple * atr_list[i]
            return ("LONG", sl, tp)

    # Trend down
    if ef < es:
        if candles[i - 1].close > ef and c.close < ef:
            sl = c.close + atr_list[i]
            tp = c.close - params.r_multiple * atr_list[i]
            return ("SHORT", sl, tp)

    return None


# ===========================
# TRADE SIMULATION
# ===========================
def simulate_trade(
    i: int,
    side: str,
    sl: float,
    tp: float,
    candles: List[SimpleKline],
    params: BacktestParamsV4Pro
) -> TradeResult:

    entry = candles[i].close
    entry_time = candles[i].close_time

    for j in range(i + 1, len(candles)):
        c = candles[j]

        if side == "LONG":
            hit_sl = c.low <= sl
            hit_tp = c.high >= tp
        else:
            hit_sl = c.high >= sl
            hit_tp = c.low <= tp

        if hit_sl:
            return TradeResult(
                index=i,
                side=side,
                entry_time=entry_time,
                exit_time=c.close_time,
                entry=entry,
                sl=sl,
                tp=tp,
                exit_price=sl,
                result_r=-1.0,
                atr=0,
            )

        if hit_tp:
            return TradeResult(
                index=i,
                side=side,
                entry_time=entry_time,
                exit_time=c.close_time,
                entry=entry,
                sl=sl,
                tp=tp,
                exit_price=tp,
                result_r=params.r_multiple,
                atr=0,
            )

    # nếu không hit SL/TP
    last_c = candles[-1]
    return TradeResult(
        index=i,
        side=side,
        entry_time=entry_time,
        exit_time=last_c.close_time,
        entry=entry,
        sl=sl,
        tp=tp,
        exit_price=last_c.close,
        result_r=0.0,
        atr=0,
    )


# ===========================
# BACKTEST MAIN
# ===========================
def backtest_ema_pullback_v4_pro(
    klines,
    params: BacktestParamsV4Pro,
    symbol: str = "",
    interval: str = "",
):

    # Convert data Binance → SimpleKline
    candles: List[SimpleKline] = [
        SimpleKline(
            open_time=k.open_time,
            close_time=k.close_time,
            open=k.open,
            high=k.high,
            low=k.low,
            close=k.close
        )
        for k in klines
    ]

    closes = [c.close for c in candles]

    ema_fast = ema(closes, params.ema_fast)
    ema_slow = ema(closes, params.ema_slow)
    atr_list = compute_atr(candles, params.atr_period)

    trades: List[TradeResult] = []

    for i in range(2, len(candles)):
        sig = detect_entry_v4(
            i, candles, ema_fast, ema_slow, atr_list, params
        )
        if sig is None:
            continue

        side, sl, tp = sig

        trade = simulate_trade(
            i, side, sl, tp, candles, params
        )
        trade.atr = atr_list[i]
        trades.append(trade)

    return trades, candles, ema_fast, ema_slow, atr_list
