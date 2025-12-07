# logic/ema_pullback_v2_lab/signal.py
from __future__ import annotations

from typing import List

from data.ema_models import CandleWithInd, EntrySignal
from logic.ema_pullback_v2_lab.params import EmaPullbackParams
from logic.ema_pullback_v2_lab.indicators_ext import calc_ema, calc_atr


def build_candles_with_ind(
    candles: List[CandleWithInd],
    params: EmaPullbackParams,
) -> List[CandleWithInd]:
    """
    Tính EMA_fast, EMA_slow, ATR cho list candles.
    Tạm thời chỉ là skeleton, sau sẽ copy logic cũ sang.
    """
    closes = [c.close for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]

    ema_fast = calc_ema(closes, params.ema_fast_period)
    ema_slow = calc_ema(closes, params.ema_slow_period)
    atr = calc_atr(highs, lows, closes, params.atr_period)

    for i, c in enumerate(candles):
        c.ema_fast = ema_fast[i]
        c.ema_slow = ema_slow[i]
        c.atr = atr[i]

    return candles


def generate_ema_pullback_v2_entries(
    candles: List[CandleWithInd],
    params: EmaPullbackParams,
) -> List[EntrySignal]:
    """
    Logic tạo EntrySignal – sẽ port từ ema_pullback_v2.py cũ.

    Skeleton: trả về list rỗng để đảm bảo import chạy được.
    """
    # TODO: implement: port full logic entry từ file cũ
    return []
