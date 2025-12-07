# logic/ema_pullback_v2.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Literal


Side = Literal["LONG", "SHORT"]
Outcome = Literal["WIN", "LOSS", "OPEN"]


@dataclass
class EmaPullbackParams:
    """
    Tham số cho chiến lược EMA_PULLBACK_V2
    """
    ema_fast_period: int = 21
    ema_slow_period: int = 200
    atr_period: int = 14

    # dùng ATR để đặt SL/TP
    atr_mult_sl: float = 1.0        # khoảng cách SL = atr_mult_sl * ATR
    rr: float = 2.0                 # R:R = rr:1  (TP = entry + rr * risk)

    # giờ trade theo múi giờ New York (int 0..23)
    session_start_hour_ny: int = 4
    session_end_hour_ny: int = 20   # inclusive: 4h -> 20h


@dataclass
class Candle:
    """
    Candle đơn giản dùng cho backtest.
    open_time luôn hiểu là UTC.
    """
    open_time: datetime
    open: float
    high: float
    low: float
    close: float


@dataclass
class EmaPullbackEntry:
    """
    Thông tin entry (chưa tính kết quả TP/SL).
    """
    symbol: str
    index: int
    side: Side
    entry_time: datetime          # UTC
    entry_price: float
    sl: float
    tp: float
    risk_pts: float              # |entry - SL|
    planned_rr: float            # thường = params.rr

    ema_fast: float
    ema_slow: float
    atr: float


@dataclass
class BacktestTrade:
    """
    Kết quả 1 lệnh sau khi backtest.
    """
    entry: EmaPullbackEntry
    outcome: Outcome    # WIN / LOSS / OPEN (chưa hit TP/SL)
    r: float            # TP full: +rr, SL full: -1, OPEN: 0
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None  # "TP"/"SL"/"OPEN"


def _is_trend_up(ema_fast: float, ema_slow: float) -> bool:
    return ema_fast > ema_slow


def _is_trend_down(ema_fast: float, ema_slow: float) -> bool:
    return ema_fast < ema_slow


def find_ema_pullback_entry(
    symbol: str,
    candles: list[Candle],
    i: int,
    ema_fast_list: list[Optional[float]],
    ema_slow_list: list[Optional[float]],
    atr_list: list[Optional[float]],
    params: EmaPullbackParams,
) -> Optional[EmaPullbackEntry]:
    """
    Tìm tín hiệu entry tại index i.
    Logic đơn giản, rõ ràng, dễ debug:

    - Xu hướng UP: EMA_FAST > EMA_SLOW
        LONG khi:
            + giá đóng cửa C[i] > EMA_FAST[i]
            + giá đóng cửa nến trước C[i-1] <= EMA_FAST[i-1]
            + C[i] > EMA_SLOW[i]  (tránh long khi giá dưới ema200)

    - Xu hướng DOWN: EMA_FAST < EMA_SLOW
        SHORT khi:
            + C[i] < EMA_FAST[i]
            + C[i-1] >= EMA_FAST[i-1]
            + C[i] < EMA_SLOW[i]

    SL = entry ± atr_mult_sl * ATR
    TP = entry ± rr * (entry - SL)
    """
    if i == 0:
        return None

    ema_fast = ema_fast_list[i]
    ema_slow = ema_slow_list[i]
    atr = atr_list[i]

    prev_ema_fast = ema_fast_list[i - 1]
    prev_ema_slow = ema_slow_list[i - 1]
    prev_atr = atr_list[i - 1]

    # phải đủ dữ liệu indicator
    if (
        ema_fast is None or ema_slow is None or atr is None or
        prev_ema_fast is None or prev_ema_slow is None or prev_atr is None
    ):
        return None

    c = candles[i]
    prev_c = candles[i - 1]

    side: Optional[Side] = None

    # ===== LONG setup =====
    if _is_trend_up(ema_fast, ema_slow):
        if prev_c.close <= prev_ema_fast and c.close > ema_fast and c.close > ema_slow:
            side = "LONG"

    # ===== SHORT setup =====
    elif _is_trend_down(ema_fast, ema_slow):
        if prev_c.close >= prev_ema_fast and c.close < ema_fast and c.close < ema_slow:
            side = "SHORT"

    if side is None:
        return None

    if side == "LONG":
        sl = c.close - params.atr_mult_sl * atr
        risk_pts = c.close - sl
        tp = c.close + params.rr * risk_pts
    else:  # SHORT
        sl = c.close + params.atr_mult_sl * atr
        risk_pts = sl - c.close
        tp = c.close - params.rr * risk_pts

    return EmaPullbackEntry(
        symbol=symbol,
        index=i,
        side=side,
        entry_time=c.open_time,
        entry_price=c.close,
        sl=sl,
        tp=tp,
        risk_pts=risk_pts,
        planned_rr=params.rr,
        ema_fast=ema_fast,
        ema_slow=ema_slow,
        atr=atr,
    )
