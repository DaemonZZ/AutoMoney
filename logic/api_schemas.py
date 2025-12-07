# logic/api_schemas.py

from dataclasses import dataclass
from typing import Literal, Optional, List
from .strategies.base_types import StrategyUserOptions

@dataclass
class BacktestRequest:
    symbol: str
    interval: str
    days: int

    strategy: Literal["ema_pullback_v4_pro"] = "ema_pullback_v4_pro"

    options: StrategyUserOptions = StrategyUserOptions()
