# logic/strategies/ema_pullback_v4_pro.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from logic.models import SimpleKline, TradeResult, Side
from logic.indicators import ema, compute_atr
from .base_types import StrategyUserOptions, RiskProfile


# ===========================
# PARAMS V4 PRO
# ===========================
@dataclass
class EmaPullbackParams:
    ema_fast: int = 18
    ema_slow: int = 200
    atr_period: int = 10
    r_multiple: float = 2.2

    # Các filter mở rộng (hiện tại min_trend_strength mới được dùng)
    min_trend_strength: float = 0.0   # |EMA_fast - EMA_slow| tối thiểu
    max_pullback_ratio: float = 0.5   # để dành, chưa dùng


# Alias cho tương thích code cũ (nếu anh vẫn dùng tên BacktestParamsV4Pro)
BacktestParamsV4Pro = EmaPullbackParams


# ===========================
# DETECT ENTRY – EMA Pullback V4 Pro
# ===========================
def detect_entry_v4_pro(
    i: int,
    candles: Sequence[SimpleKline],
    ema_fast_list: Sequence[float],
    ema_slow_list: Sequence[float],
    atr_list: Sequence[float],
    params: EmaPullbackParams,
) -> Optional[Tuple[Side, float, float]]:
    """
    Trả về: (side, sl, tp) hoặc None nếu không có tín hiệu.
    Logic giữ nguyên như bản V4 Pro anh đang chạy.
    """
    c = candles[i]
    ef = ema_fast_list[i]
    es = ema_slow_list[i]
    atr = atr_list[i]

    # Trend filter
    trend_strength = abs(ef - es)
    if trend_strength < params.min_trend_strength:
        return None

    # Uptrend: EMA nhanh > EMA chậm, giá pullback chạm EMA nhanh rồi bật lên
    if ef > es:
        if candles[i - 1].close < ef <= c.close:
            sl = c.close - atr
            tp = c.close + params.r_multiple * atr
            return Side.LONG, sl, tp

    # Downtrend: EMA nhanh < EMA chậm, giá pullback chạm EMA nhanh rồi rơi xuống
    if ef < es:
        if candles[i - 1].close > ef >= c.close:
            sl = c.close + atr
            tp = c.close - params.r_multiple * atr
            return Side.SHORT, sl, tp

    return None


# ===========================
# SIMULATE 1 LỆNH
# ===========================
def simulate_trade_v4_pro(
    i: int,
    side: Side,
    sl: float,
    tp: float,
    candles: Sequence[SimpleKline],
    params: EmaPullbackParams,
    atr_value: float,
) -> TradeResult:
    entry_candle = candles[i]
    entry = entry_candle.close
    entry_time = entry_candle.close_time

    for j in range(i + 1, len(candles)):
        c = candles[j]

        if side is Side.LONG:
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
                atr=atr_value,
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
                atr=atr_value,
            )

    # Không chạm SL/TP đến cuối data → coi là hoà
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
        atr=atr_value,
    )


# ===========================
# RUN STRATEGY trên SimpleKline (core)
# ===========================
def run_ema_pullback_v4_pro(
    candles: Sequence[SimpleKline],
    params: EmaPullbackParams,
) -> List[TradeResult]:
    candles = list(candles)
    if len(candles) < max(params.ema_fast, params.ema_slow) + 2:
        return []

    closes = [c.close for c in candles]
    ema_fast_list = ema(closes, params.ema_fast)
    ema_slow_list = ema(closes, params.ema_slow)
    atr_list = compute_atr(candles, params.atr_period)

    trades: List[TradeResult] = []

    for i in range(2, len(candles)):
        sig = detect_entry_v4_pro(
            i, candles, ema_fast_list, ema_slow_list, atr_list, params
        )
        if sig is None:
            continue

        side, sl, tp = sig
        trade = simulate_trade_v4_pro(
            i, side, sl, tp, candles, params, atr_list[i]
        )
        trades.append(trade)

    return trades


# ===========================
# BACKTEST WRAPPER (tương thích code cũ)
# ===========================
def backtest_ema_pullback_v4_pro(
    klines,
    params: EmaPullbackParams,
    symbol: str = "",
    interval: str = "",
):
    """
    Wrapper cho style cũ:
    - Input: list Kline (object có thuộc tính open_time, close_time, open, high, low, close)
    - Output: trades, candles(SimpleKline), ema_fast_list, ema_slow_list, atr_list
    """

    candles: List[SimpleKline] = [
        SimpleKline(
            open_time=k.open_time,
            close_time=k.close_time,
            open=float(k.open),
            high=float(k.high),
            low=float(k.low),
            close=float(k.close),
        )
        for k in klines
    ]

    closes = [c.close for c in candles]
    ema_fast_list = ema(closes, params.ema_fast)
    ema_slow_list = ema(closes, params.ema_slow)
    atr_list = compute_atr(candles, params.atr_period)

    trades = run_ema_pullback_v4_pro(candles, params)

    return trades, candles, ema_fast_list, ema_slow_list, atr_list


def build_params_from_user_options(
    symbol: str,
    opts: StrategyUserOptions,
) -> EmaPullbackParams:
    """
    Quyết định EmaPullbackParams cuối cùng cho 1 run
    theo:
      1) override_params nếu có
      2) nếu use_optimizer=True → gọi optimizer
      3) nếu không → dùng preset theo filter_mode + risk_profile
    """

    # 1) User override trực tiếp
    if opts.override_params is not None:
        return opts.override_params

    # 2) Dùng optimizer
    if opts.use_optimizer:
        # TODO: sau này mình plug optimizer_v4_pro ở đây
        from logic.optimizers.optimizer_v4_pro import (
            optimize_v4_pro_for_symbol,
        )
        best_params = optimize_v4_pro_for_symbol(symbol)
        return best_params

    # 3) Dùng preset filter theo mode
    if opts.filter_mode == "none":
        min_trend = 0.0
        max_pb = 0.8
    elif opts.filter_mode == "light":
        min_trend = 0.0
        max_pb = 0.5
    else:  # "pro"
        min_trend = 15.0
        max_pb = 0.4

    # risk_profile map sang R
    if opts.risk_profile == "loose":
        r_multiple = 1.8
    elif opts.risk_profile == "strict":
        r_multiple = 2.5
    else:
        r_multiple = 2.2

    return EmaPullbackParams(
        ema_fast=21,
        ema_slow=200,
        atr_period=14,
        r_multiple=r_multiple,
        min_trend_strength=min_trend,
        max_pullback_ratio=max_pb,
    )
