# logic/strategies/v4_pro_params.py

from dataclasses import dataclass

@dataclass
class EmaPullbackParams:
    ema_fast: int = 21
    ema_slow: int = 200
    atr_period: int = 14
    r_multiple: float = 2.0

    min_trend_strength: float = 0.0
    max_pullback_ratio: float = 0.5
