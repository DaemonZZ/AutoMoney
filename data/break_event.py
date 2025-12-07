from dataclasses import dataclass
from data.kline import Kline

@dataclass
class BreakEvent:
    symbol: str
    level_type: str    # "HIGH" hoặc "LOW"
    kind: str          # "EXIT_UP", "EXIT_DOWN", "REENTER_FROM_ABOVE", "REENTER_FROM_BELOW"
    level: float       # giá trị high/low của range 4h
    candle: Kline      # nến 5m gây ra sự kiện

    def __str__(self):
        return (
            f"BreakEvent[{self.symbol}] {self.level_type} {self.kind} "
            f"level={self.level} at {self.candle.open_time.isoformat()} "
            f"O={self.candle.open}, H={self.candle.high}, "
            f"L={self.candle.low}, C={self.candle.close}"
        )

    def toString(self):
        return self.__str__()
