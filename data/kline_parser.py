# data/kline_parser.py
from datetime import datetime, timezone
from data.kline import Kline


def parse_kline(symbol: str, interval: str, k: list) -> Kline:
    """
    Parse mảng kline raw từ Binance thành đối tượng Kline.
    """
    return Kline(
        symbol=symbol,
        interval=interval,

        open_time=datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc),
        open=float(k[1]),
        high=float(k[2]),
        low=float(k[3]),
        close=float(k[4]),
        volume=float(k[5]),
        close_time=datetime.fromtimestamp(k[6] / 1000, tz=timezone.utc),

        quote_volume=float(k[7]),
        trades=int(k[8]),
        taker_buy_volume=float(k[9]),
        taker_buy_quote_volume=float(k[10]),

        raw=k
    )
