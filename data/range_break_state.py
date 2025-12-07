from dataclasses import dataclass
from typing import Optional
from data.range_4h_ny import Range4HNY
from data.break_event import BreakEvent

@dataclass
class RangeBreakState:
    range_4h: Range4HNY

    current_state: str           # "INSIDE", "OUTSIDE_ABOVE", "OUTSIDE_BELOW"
    last_exit: Optional[BreakEvent] = None
    last_reentry: Optional[BreakEvent] = None

    @property
    def waiting_for_breakout(self) -> bool:
        """
        Đang ở trong vùng, chưa có breakout "mở" nào.
        """
        if self.current_state == "INSIDE":
            if self.last_exit is None:
                return True
            # nếu lần reentry mới nhất xảy ra SAU lần exit → vòng đó đã kết thúc
            if self.last_reentry and self.last_reentry.candle.open_time >= self.last_exit.candle.open_time:
                return True
        return False

    @property
    def waiting_for_reentry(self) -> bool:
        """
        Đã có exit gần nhất, nhưng CHƯA có reentry sau nó → đang chờ vào lại.
        """
        if self.last_exit is None:
            return False
        if self.last_reentry is None:
            return True
        # nếu exit xảy ra sau reentry → đang chờ reentry cho lần exit mới
        return self.last_exit.candle.open_time > self.last_reentry.candle.open_time
