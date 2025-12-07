# data/kline.py
from dataclasses import dataclass
from datetime import datetime

@dataclass
class Kline:
    symbol: str
    interval: str

    open_time: datetime
    close_time: datetime

    open: float
    high: float
    low: float
    close: float
    volume: float

    trades: int
    quote_volume: float
    taker_buy_volume: float
    taker_buy_quote_volume: float

    raw: list  # giữ lại raw data nếu cần debug


    # -----------------------------
    #  STRING REPRESENTATION
    # -----------------------------
    def __str__(self):
        return (
            f"Kline[{self.symbol} {self.interval}] "
            f"{self.open_time.isoformat()} → {self.close_time.isoformat()} | "
            f"Open={self.open}, High={self.high}, Low={self.low}, Close={self.close}, Volume={self.volume}"
        )

    def __repr__(self):
        return (
            f"Kline(symbol={self.symbol}, interval={self.interval}, "
            f"open_time={self.open_time}, close_time={self.close_time}, "
            f"open={self.open}, high={self.high}, low={self.low}, close={self.close}, "
            f"volume={self.volume}, trades={self.trades})"
        )