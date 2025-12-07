# logic/candle_watcher_5m.py

import time
from typing import Callable, Optional

from api.market_data import get_latest_5m_candle
from data.kline import Kline
from config import DEFAULT_SYMBOL, TRADING_TIMEZONE


class CandleWatcher5m:
    """
    Chạy vòng lặp, liên tục lấy nến 5m mới nhất cho 1 symbol.
    - Khi có nến 5m mới (open_time thay đổi) -> gọi callback on_new_candle
    - Khi nến hiện tại đang chạy (giá thay đổi) -> gọi on_update_current (optional)
    """

    def __init__(
        self,
        symbol: str = DEFAULT_SYMBOL,
        poll_interval: float = 2.0,   # giây, nên 2-5s là hợp lý
        on_new_candle: Optional[Callable[[Kline], None]] = None,
        on_update_current: Optional[Callable[[Kline], None]] = None,
    ):
        self.symbol = symbol
        self.poll_interval = poll_interval

        self.on_new_candle = on_new_candle
        self.on_update_current = on_update_current

        self._running = False
        self._last_open_time = None  # lưu open_time nến 5m gần nhất

    def start(self):
        """
        Bắt đầu vòng lặp blocking. Thường sẽ chạy trong thread riêng
        (Engine, hoặc QThread trong UI).
        """
        self._running = True
        print(f"[CandleWatcher5m] Start watching {self.symbol} (5m)")

        while self._running:
            try:
                kline = get_latest_5m_candle(self.symbol)  # trả về Kline hoặc None
                if kline is None:
                    time.sleep(self.poll_interval)
                    continue

                open_time = kline.open_time

                if self._last_open_time is None:
                    # Lần đầu chạy: coi như "nến hiện tại"
                    self._last_open_time = open_time
                    self._handle_new_candle(kline)  # hoặc _handle_update_current
                else:
                    if open_time != self._last_open_time:
                        # -> CÓ NẾN 5M MỚI
                        self._last_open_time = open_time
                        self._handle_new_candle(kline)
                    else:
                        # -> NẾN HIỆN TẠI ĐANG CHẠY (cập nhật giá)
                        self._handle_update_current(kline)

            except Exception as e:
                print(f"[CandleWatcher5m] Error: {e}")

            time.sleep(self.poll_interval)

        print(f"[CandleWatcher5m] Stopped watching {self.symbol}")

    def stop(self):
        """Dừng vòng lặp."""
        self._running = False

    # ====== internal handlers ======
    def _handle_new_candle(self, kline: Kline):
        if self.on_new_candle:
            self.on_new_candle(kline)
        else:
            # default log nếu không có callback
            self._print_kline("NEW 5m", kline)

    def _handle_update_current(self, kline: Kline):
        if self.on_update_current:
            self.on_update_current(kline)
        else:
            # có thể comment đi nếu không muốn spam log
            self._print_kline("UPDATE 5m", kline)

    @staticmethod
    def _print_kline(prefix: str, kline: Kline):
        # In UTC + giờ VN/NY cho dễ nhìn
        ny_time = kline.open_time.astimezone(TRADING_TIMEZONE)
        from zoneinfo import ZoneInfo
        vn_tz = ZoneInfo("Asia/Ho_Chi_Minh")
        vn_time = kline.open_time.astimezone(vn_tz)

        print(
            f"[{prefix}] {kline.symbol} {kline.interval} | "
            f"UTC: {kline.open_time} | "
            f"NY: {ny_time} | VN: {vn_time} | "
            f"O={kline.open} H={kline.high} L={kline.low} C={kline.close}"
        )
