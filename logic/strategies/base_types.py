# logic/strategies/base_types.py

from dataclasses import dataclass
from typing import Literal, Optional

from logic.strategies.ema_pullback_v4_pro import EmaPullbackParams

RiskProfile = Literal["loose", "normal", "strict"]


@dataclass
class StrategyUserOptions:
    # Cho phép bật/tắt optimizer
    use_optimizer: bool = False

    # Chọn preset filter: không / vừa / chặt
    filter_mode: Literal["none", "light", "pro"] = "light"

    # Chọn mức độ rủi ro (sau này map ra R, SL, position sizing...)
    risk_profile: RiskProfile = "normal"

    # Cho phép user override luôn params (bỏ qua optimizer & preset)
    override_params: Optional[EmaPullbackParams] = None
