# logic/models.py
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass
class SimpleKline:
    open_time: datetime
    close_time: datetime
    open: float
    high: float
    low: float
    close: float


@dataclass
class TradeResult:
    index: int
    side: Side
    entry_time: datetime
    exit_time: datetime
    entry: float
    sl: float
    tp: float
    exit_price: float
    result_r: float
    atr: float
