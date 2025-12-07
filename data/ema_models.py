# data/ema_models.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional

Side = Literal["LONG", "SHORT"]
TradeResultType = Literal["WIN", "LOSS", "BREAKEVEN", "OPEN"]


@dataclass
class Candle:
    """Nến chuẩn hóa cho backtest EMA pullback lab."""
    open_time_utc: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass
class CandleWithInd(Candle):
    """Candle + indicator (EMA/ATR)."""
    ema_fast: Optional[float] = None
    ema_slow: Optional[float] = None
    atr: Optional[float] = None


@dataclass
class EntrySignal:
    """Tín hiệu vào lệnh."""
    idx: int
    side: Side
    entry_price: float
    sl: float
    tp: float
    risk_pts: float
    planned_rr: float

    entry_time_utc: datetime
    entry_time_ny: datetime
    entry_time_vn: datetime


@dataclass
class TradeResult:
    """Kết quả 1 lệnh sau backtest."""
    entry: EntrySignal
    result_type: TradeResultType
    rr: float
    exit_price: Optional[float]
    exit_idx: Optional[int]
    exit_time_utc: Optional[datetime]
    exit_time_ny: Optional[datetime]
    exit_time_vn: Optional[datetime]
    exit_reason: Optional[str] = None  # "TP", "SL", "TIMEOUT", ...


@dataclass
class BacktestSummary:
    """Tổng kết backtest."""
    total_entries: int
    closed_trades: int
    win_trades: int
    loss_trades: int
    breakeven_trades: int
    winrate: float
    avg_rr: float
    avg_rr_win: float
    avg_rr_loss: float
