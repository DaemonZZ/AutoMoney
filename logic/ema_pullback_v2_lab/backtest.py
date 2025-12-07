# logic/ema_pullback_v2_lab/backtest.py
from __future__ import annotations

from typing import List

from data.ema_models import (
    Candle,
    CandleWithInd,
    EntrySignal,
    TradeResult,
    BacktestSummary,
)
from logic.ema_pullback_v2_lab.params import EmaPullbackParams
from logic.ema_pullback_v2_lab.signal import (
    build_candles_with_ind,
    generate_ema_pullback_v2_entries,
)
from logic.ema_pullback_v2_lab.executor import (
    simulate_trade,
    summarize_results,
)


def backtest_ema_pullback_v2_lab(
    raw_candles: List[Candle],
    params: EmaPullbackParams,
) -> tuple[List[TradeResult], BacktestSummary]:
    """
    Hàm backtest chính cho EMA_PULLBACK_V2 (lab version).
    """
    candles_with_ind: List[CandleWithInd] = [
        CandleWithInd(
            open_time_utc=c.open_time_utc,
            open=c.open,
            high=c.high,
            low=c.low,
            close=c.close,
            volume=c.volume,
        )
        for c in raw_candles
    ]

    candles_with_ind = build_candles_with_ind(candles_with_ind, params)
    entries: List[EntrySignal] = generate_ema_pullback_v2_entries(
        candles_with_ind, params
    )

    trades: List[TradeResult] = []
    for entry in entries:
        tr = simulate_trade(entry, candles_with_ind, params)
        trades.append(tr)

    summary = summarize_results(trades)
    return trades, summary
