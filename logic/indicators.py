# logic/indicators.py

from __future__ import annotations
from typing import List, Optional
from data.kline import Kline


def ema(values: List[float], period: int) -> List[Optional[float]]:
    """
    Tính EMA cho list giá.
    Trả về list cùng chiều, những phần tử đầu chưa đủ period sẽ là None.
    """
    if not values or period <= 0:
        return [None] * len(values)

    ema_values: List[Optional[float]] = [None] * len(values)

    # khởi tạo bằng SMA
    if len(values) < period:
        return ema_values

    sma = sum(values[:period]) / period
    ema_values[period - 1] = sma

    k = 2 / (period + 1)

    prev = sma
    for i in range(period, len(values)):
        price = values[i]
        prev = price * k + prev * (1 - k)
        ema_values[i] = prev

    return ema_values


def atr(candles: List[Kline], period: int) -> List[Optional[float]]:
    """
    Tính ATR (Average True Range) cho list Kline.
    Trả về list cùng chiều, những phần tử đầu chưa đủ period sẽ là None.
    True Range = max(
        high - low,
        abs(high - prev_close),
        abs(low - prev_close)
    )
    """
    n = len(candles)
    if n == 0 or period <= 0:
        return [None] * n

    trs: List[float] = [0.0] * n

    for i, c in enumerate(candles):
        high = c.high
        low = c.low
        if i == 0:
            trs[i] = high - low
        else:
            prev_close = candles[i - 1].close
            trs[i] = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close),
            )

    atr_values: List[Optional[float]] = [None] * n

    if n < period:
        return atr_values

    first_atr = sum(trs[:period]) / period
    atr_values[period - 1] = first_atr

    for i in range(period, n):
        prev = atr_values[i - 1]
        tr = trs[i]
        # ATR kiểu Wilder
        curr = (prev * (period - 1) + tr) / period
        atr_values[i] = curr

    return atr_values
