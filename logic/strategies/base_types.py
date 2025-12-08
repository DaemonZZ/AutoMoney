# logic/strategies/base_types.py

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any


class RiskProfile(str, Enum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


@dataclass
class StrategyUserOptions:
    """
    Các option chung mà user có thể bật/tắt cho MỌI strategy.
    Strategy cụ thể (như EMA Pullback V4 Pro) sẽ nhận object này
    và tự diễn giải theo kiểu của nó.
    """
    use_optimizer: bool = False      # bật/tắt auto-optimizer theo symbol
    strict_filters: bool = False     # bật/tắt filter chặt chẽ
    risk_profile: RiskProfile = RiskProfile.MODERATE

    # chỗ này để dành mở rộng sau:
    extra: Optional[Dict[str, Any]] = None
