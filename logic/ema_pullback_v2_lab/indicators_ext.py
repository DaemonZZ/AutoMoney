# logic/ema_pullback_v2_lab/indicators_ext.py
from __future__ import annotations

from typing import Sequence, List, Optional
import numpy as np

# nếu muốn dùng lại hàm từ logic/indicators.py:
# from logic.indicators import ema as old_ema, atr as old_atr


def calc_ema(values: Sequence[float], period: int) -> List[Optional[float]]:
    """
    Skeleton EMA – sau sẽ implement dựa trên code cũ
    (hoặc gọi lại hàm cũ trong logic/indicators.py).
    """
    # TODO: implement: dùng code cũ / pandas / numpy
    return [None] * len(values)


def calc_atr(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int,
) -> List[Optional[float]]:
    """
    Skeleton ATR – sẽ port từ code cũ.
    """
    # TODO: implement
    return [None] * len(closes)
