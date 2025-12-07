# data/trade.py
from dataclasses import dataclass
from datetime import datetime
from data.entry_signal import EntrySignal

@dataclass
class Trade:
    id: int
    symbol: str
    side: str          # "LONG" hoặc "SHORT"

    entry_time: datetime
    entry_price: float

    sl_price: float
    tp_price: float

    opened_from_signal: EntrySignal

    closed_at: datetime | None = None
    close_price: float | None = None
    result: str | None = None   # "TP" | "SL"
    rr: float | None = None
    pl_points: float | None = None

    def is_open(self) -> bool:
        return self.closed_at is None
