# logic/ema_pullback_v2_lab/params.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import time


@dataclass
class EmaPullbackParams:
    """Tham số cho EMA_PULLBACK_V2 (lab version)."""
    symbol: str = "BTCUSDT"
    timeframe: str = "5m"

    ema_fast_period: int = 21
    ema_slow_period: int = 200
    atr_period: int = 14
    rr: float = 2.0

    # phiên NY
    ny_start: time = time(4, 0)
    ny_end: time = time(20, 0)

    # chỗ để thêm filter nâng cao nếu cần
    max_bars_in_trade: int | None = None
