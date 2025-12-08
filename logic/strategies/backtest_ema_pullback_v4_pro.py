# logic/backtest_ema_pullback_v4_pro.py

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Tuple
from datetime import datetime, timezone

from logic.indicators import ema, compute_atr
from logic.models import SimpleKline, TradeResult
from logic.strategies.v4_pro_params import EmaPullbackParams


# ===========================
# ✨ EMA Pullback V4 Pro ✨
# ===========================
def detect_entry_v4(
    i: int,
    candles: List[SimpleKline],
    ema_fast: List[float],
    ema_slow: List[float],
    atr_list: List[float],
    params: EmaPullbackParams,
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
    params: EmaPullbackParams
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
    params: EmaPullbackParams,
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
