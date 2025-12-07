# data/range_break_reentry.py
from dataclasses import dataclass
from typing import Optional
from data.kline import Kline
from data.range_4h_ny import Range4HNY

@dataclass
class RangeBreakReentry:
    range_4h: Range4HNY

    up_exit: Optional[Kline] = None            # nến thoát lên HIGH
    up_reentry: Optional[Kline] = None         # nến vào lại từ phía trên

    down_exit: Optional[Kline] = None          # nến thoát xuống LOW
    down_reentry: Optional[Kline] = None       # nến vào lại từ phía dưới

    def __str__(self):
        return (
            f"RangeBreakReentry[{self.range_4h.symbol}] "
            f"high={self.range_4h.high}, low={self.range_4h.low}, "
            f"up_exit={self.up_exit.open_time if self.up_exit else None}, "
            f"up_reentry={self.up_reentry.open_time if self.up_reentry else None}, "
            f"down_exit={self.down_exit.open_time if self.down_exit else None}, "
            f"down_reentry={self.down_reentry.open_time if self.down_reentry else None}"
        )


