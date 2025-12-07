# logic/trading_engine.py

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Set, Optional

from config import TRADING_TIMEZONE, VN_TZ, DEFAULT_SYMBOL
from data.kline import Kline
from data.range_4h_ny import Range4HNY
from data.trade import Trade
from data.entry_signal import EntrySignal

# dùng futures data
from api.market_data_futures import (
    get_first_4h_high_low_newyork_futures,
    get_5m_candles_from_4h_to_now_newyork_futures,
    get_latest_5m_candle_futures,
)

from logic.entry_signals import detect_entry_signals


class TradingEngine:
    """
    Engine:
      - Nhận nến 5m mới (Kline)
      - Mỗi ngày: dùng range 4h đầu theo giờ New York
      - Tạo entry khi có breakout + re-entry
      - Track SL/TP cho 1 trade tại 1 thời điểm
      - Không mở trade mới trong khung 00:00 → 04:00 (NY)
    """

    def __init__(self, symbol: str = DEFAULT_SYMBOL):
        self.symbol = symbol

        self.current_range: Optional[Range4HNY] = None
        self.current_range_day: Optional[datetime.date] = None

        # lưu các nến 5m từ 4h NY → hiện tại (trong ngày hiện tại)
        self.candles_from_4h: List[Kline] = []

        # track trade
        self.active_trade: Optional[Trade] = None
        self.trade_counter: int = 0

        # để tránh xử lý 1 entry signal nhiều lần
        self.seen_entry_times: Set[datetime] = set()

    # =========================
    #   HÀM PUBLIC
    # =========================
    def on_new_candle(self, candle: Kline):
        """
        Hàm này được gọi mỗi khi có NẾN 5M MỚI ĐÓNG XONG.
        Engine xử lý tất cả logic tại đây.
        """
        if candle.symbol != self.symbol:
            return

        ny_time = candle.open_time.astimezone(TRADING_TIMEZONE)
        ny_date = ny_time.date()
        ny_hour = ny_time.hour

        print(f"\n[Engine] New 5m candle: {candle.symbol} {candle.interval} "
              f"NY={ny_time} O={candle.open} H={candle.high} L={candle.low} C={candle.close}")

        # 1) Nếu sang ngày mới → reset range, list candles, signals
        if self.current_range_day is None or ny_date != self.current_range_day:
            print(f"[Engine] New trading day (NY date={ny_date}), reset range & history.")
            self.current_range = None
            self.current_range_day = ny_date
            self.candles_from_4h = []
            self.seen_entry_times.clear()

        # 2) Luôn update trade đang mở (nếu có) để check SL/TP
        if self.active_trade is not None:
            self._update_active_trade_with_candle(candle)

        # 3) Nếu trong khung 00:00 → 04:00 NY → KHÔNG mở trade mới, chỉ quản lý trade cũ
        if 0 <= ny_hour < 4:
            print("[Engine] NY time in [00:00, 04:00) → không tạo trade mới.")
            return

        # 4) Đảm bảo range 4h đã sẵn sàng (nếu chưa, tạo)
        if self.current_range is None:
            self._init_range_and_history(candle)
            # sau khi khởi tạo xong, không xử lý entry cho cây hiện tại nữa, đợi cây sau
            return

        # 5) Thêm candle vào history 4h→now
        self.candles_from_4h.append(candle)

        # 6) Nếu đang có trade mở → không tạo trade mới
        if self.active_trade is not None and self.active_trade.is_open():
            print("[Engine] Đang có trade mở → không tạo trade mới.")
            return

        # 7) Tìm entry signal với toàn bộ lịch sử 5m hiện tại
        signals = detect_entry_signals(self.current_range, self.candles_from_4h)

        # lọc những signal có entry_time == candle.open_time (entry trên cây hiện tại)
        # và chưa bị xử lý trước đó
        new_signals = [
            s for s in signals
            if s.entry_time == candle.open_time and s.entry_time not in self.seen_entry_times
        ]

        if not new_signals:
            print("[Engine] Không có entry signal mới trên cây hiện tại.")
            return

        # đánh dấu đã dùng
        for s in new_signals:
            self.seen_entry_times.add(s.entry_time)

        # chọn signal mới nhất (nếu có nhiều)
        signal = new_signals[-1]
        self._open_trade_from_signal(signal)

    # =========================
    #   INTERNAL HELPERS
    # =========================
    def _init_range_and_history(self, latest_candle: Kline):
        """
        Tạo range 4h đầu ngày + nến 5m history từ 4h NY → latest.
        Chỉ gọi khi NY đã >= 4h.
        """
        ny_time = latest_candle.open_time.astimezone(TRADING_TIMEZONE)
        ny_hour = ny_time.hour

        if ny_hour < 4:
            print("[Engine] _init_range_and_history được gọi nhưng NY < 4h (bỏ qua).")
            return

        print("[Engine] Khởi tạo range 4h đầu ngày (NY) & history 5m từ 4h → hiện tại...")

        rng = get_first_4h_high_low_newyork_futures(self.symbol)
        if rng is None:
            print("[Engine] Không lấy được range 4h (có thể chưa đủ 4h dữ liệu).")
            return

        self.current_range = rng
        print(f"[Engine] Range 4h NY: HIGH={rng.high}, LOW={rng.low}, "
              f"NY({rng.start_ny} → {rng.end_ny})")

        # load history 5m từ 4h NY → hiện tại
        history = get_5m_candles_from_4h_to_now_newyork_futures(self.symbol)
        if history is None:
            print("[Engine] NY < 4h trong _init_range_and_history (lạ).")
            history = []
        self.candles_from_4h = history

        print(f"[Engine] Loaded {len(self.candles_from_4h)} candles 5m từ 4h NY → now.")

        # tạo list signals để "đánh dấu bỏ qua" các đợt entry đã qua
        if self.candles_from_4h:
            past_signals = detect_entry_signals(self.current_range, self.candles_from_4h)
            for s in past_signals:
                # vì engine được bật sau, các entry này đã "qua rồi" → skip
                self.seen_entry_times.add(s.entry_time)

            if past_signals:
                print(f"[Engine] Phát hiện {len(past_signals)} entry signals trong quá khứ, "
                      f"sẽ bỏ qua & chờ đợt mới.")

    def _open_trade_from_signal(self, signal: EntrySignal):
        """
        Tạo một Trade object từ EntrySignal, chỉ in ra thông tin.
        """
        self.trade_counter += 1
        t = Trade(
            id=self.trade_counter,
            symbol=signal.symbol,
            side=signal.side,
            entry_time=signal.entry_time,
            entry_price=signal.entry_price,
            sl_price=signal.sl_price,
            tp_price=signal.tp_price,
            opened_from_signal=signal,
        )
        self.active_trade = t

        ny_time = t.entry_time.astimezone(TRADING_TIMEZONE)
        vn_time = t.entry_time.astimezone(VN_TZ)

        print("\n=== OPEN TRADE ===")
        print(f"ID         : {t.id}")
        print(f"Symbol     : {t.symbol}")
        print(f"Side       : {t.side} (LONG=break từ LOW, SHORT=break từ HIGH)")
        print(f"Entry time : UTC={t.entry_time}, NY={ny_time}, VN={vn_time}")
        print(f"Entry      : {t.entry_price}")
        print(f"SL         : {t.sl_price}")
        print(f"TP         : {t.tp_price}")
        print("===================\n")

    def _update_active_trade_with_candle(self, candle: Kline):
        """
        Kiểm tra nến mới có cán SL/TP của trade đang mở không.
        Ưu tiên SL trước, sau đó TP (bảo thủ).
        """
        t = self.active_trade
        if t is None or not t.is_open():
            return

        high = candle.high
        low = candle.low

        sl_hit = False
        tp_hit = False

        if t.side == "LONG":
            # SL nếu giá xuống dưới đáy
            if low <= t.sl_price:
                sl_hit = True
            # TP nếu giá lên tới target
            elif high >= t.tp_price:
                tp_hit = True
        elif t.side == "SHORT":
            # SL nếu giá lên trên đỉnh
            if high >= t.sl_price:
                sl_hit = True
            # TP nếu giá xuống tới target
            elif low <= t.tp_price:
                tp_hit = True

        if not sl_hit and not tp_hit:
            return

        # đóng lệnh
        t.closed_at = candle.close_time
        if sl_hit:
            t.result = "SL"
            t.close_price = t.sl_price
        else:
            t.result = "TP"
            t.close_price = t.tp_price

        # tính P/L theo "points" và RR
        if t.side == "LONG":
            risk = t.entry_price - t.sl_price
            pl = t.close_price - t.entry_price
        else:  # SHORT
            risk = t.sl_price - t.entry_price
            pl = t.entry_price - t.close_price

        t.pl_points = pl
        t.rr = pl / risk if risk != 0 else None

        ny_time = t.closed_at.astimezone(TRADING_TIMEZONE)
        vn_time = t.closed_at.astimezone(VN_TZ)

        print("\n=== CLOSE TRADE ===")
        print(f"ID          : {t.id}")
        print(f"Symbol      : {t.symbol}")
        print(f"Side        : {t.side}")
        print(f"Result      : {t.result}")
        print(f"Entry       : {t.entry_price}")
        print(f"Exit price  : {t.close_price}")
        print(f"Opened at   : {t.entry_time}")
        print(f"Closed at   : UTC={t.closed_at}, NY={ny_time}, VN={vn_time}")
        print(f"P/L points  : {t.pl_points}")
        print(f"RR          : {t.rr}")
        print("====================\n")

        # Sau khi đóng lệnh, cho phép lệnh mới
        self.active_trade = None
