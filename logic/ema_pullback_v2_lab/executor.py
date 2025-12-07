# logic/ema_pullback_v2_lab/executor.py
from __future__ import annotations

from typing import List

from data.ema_models import (
    CandleWithInd,
    EntrySignal,
    TradeResult,
    BacktestSummary,
)
from logic.ema_pullback_v2_lab.params import EmaPullbackParams


def simulate_trade(
    entry: EntrySignal,
    candles: List[CandleWithInd],
    params: EmaPullbackParams,
) -> TradeResult:
    """
    Mô phỏng 1 lệnh từ entry -> TP/SL (skeleton).
    Sau sẽ copy logic từ trading_engine/backtest cũ.
    """
    # TODO: implement
    raise NotImplementedError("simulate_trade() chưa implement")


def summarize_results(trades: List[TradeResult]) -> BacktestSummary:
    """Tính winrate, avg R,..."""
    # TODO: implement
    raise NotImplementedError("summarize_results() chưa implement")
