from dataclasses import dataclass
from datetime import datetime
from data.break_event import BreakEvent

@dataclass
class EntrySignal:
    symbol: str
    side: str              # "LONG" hoặc "SHORT"
    range_side: str        # "LOW" hoặc "HIGH" (phá từ phía nào)
    exit_event: BreakEvent
    reentry_event: BreakEvent
    entry_time: datetime
    entry_price: float

    sl_price: float        # giá stop loss
    tp_price: float        # giá take profit
    risk: float            # khoảng risk (entry - SL hoặc SL - entry)
    rr: float              # risk:reward (ở đây = 2.0)

    def __str__(self):
        return (
            f"EntrySignal[{self.symbol}] side={self.side} range_side={self.range_side} "
            f"entry_time={self.entry_time.isoformat()} entry_price={self.entry_price} "
            f"SL={self.sl_price} TP={self.tp_price} R={self.risk} RR={self.rr} "
            f"(exit={self.exit_event.kind} at {self.exit_event.candle.open_time.isoformat()}, "
            f"reentry={self.reentry_event.kind} at {self.reentry_event.candle.open_time.isoformat()})"
        )

    def toString(self):
        return self.__str__()
