# logic/indicators.py
from __future__ import annotations

from typing import List, Sequence

from .models import SimpleKline


def ema(values: Sequence[float], period: int) -> List[float]:
    """
    Tính EMA đơn giản, trả về list cùng length với input.
    """
    values = list(values)
    if not values:
        return []

    if period <= 1:
        # EMA(1) = giá trị gốc
        return values.copy()

    alpha = 2.0 / (period + 1.0)
    out: List[float] = [values[0]]

    for v in values[1:]:
        prev = out[-1]
        out.append(prev + alpha * (v - prev))

    return out


def compute_atr(candles: Sequence[SimpleKline], length: int) -> List[float]:
    """
    ATR dạng EMA (smoothed)
    """
    candles = list(candles)
    n = len(candles)
    if n == 0:
        return []

    if n == 1 or length <= 0:
        return [0.0] * n

    trs: List[float] = []
    for i in range(1, n):
        high = candles[i].high
        low = candles[i].low
        prev_close = candles[i - 1].close
        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close),
        )
        trs.append(tr)

    # ATR smoothing (EMA kiểu đơn giản)
    atr: List[float] = []
    alpha = 1.0 / float(length)
    atr.append(trs[0])
    for t in trs[1:]:
        prev = atr[-1]
        atr.append(prev + alpha * (t - prev))

    out = [0.0] * n
    out[1:] = atr
    return out
