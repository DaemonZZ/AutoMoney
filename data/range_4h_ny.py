
from dataclasses import dataclass
from datetime import datetime

@dataclass
class Range4HNY:
    symbol: str

    high: float
    low: float
    count: int

    start_ny: datetime
    end_ny: datetime

    start_utc: datetime
    end_utc: datetime

    start_vn: datetime
    end_vn: datetime

    def __str__(self):
        return (
            f"Range4HNY[{self.symbol}] "
            f"NY({self.start_ny} -> {self.end_ny}) | "
            f"High={self.high}, Low={self.low}, Candles={self.count}"
        )

    def toString(self):
        return self.__str__()
