# logic/smc_engine.py

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Set

from config import TRADING_TIMEZONE, VN_TZ, DEFAULT_SYMBOL
from data.kline import Kline
from data.range_4h_ny import Range4HNY
from data.trade import Trade
from data.entry_signal import EntrySignal

from api.market_data_futures import (
    get_first_4h_high_low_newyork_futures,
    get_5m_candles_from_4h_to_now_newyork_futures,
    get_latest_5m_candle_futures,
)

from logic.entry_signals import detect_entry_signals
from logic.indicators import ema, atr


class SmcBreakoutEngine:
    """
    Engine SMC:
      - Range 4h đầu ngày (NY)
      - Liquidity sweep (break HIGH/LOW) + re-entry
      - Filter trend bằng EMA200
      - Filter volatility bằng ATR
      - Không trade 00:00 → 04:00 NY
      - Không mở lệnh mới khi lệnh cũ chưa đóng
    """

    EMA_PERIOD = 200
    ATR_PERIOD = 14
    ATR_MIN_MULTIPLIER = 0.8  # ATR phải > 0.8 * ATR trung bình gần đây

    def __init__(self, symbol: str = DEFAULT_SYMBOL):
        self.symbol = symbol

        self.current_range: Optional[Range4HNY] = None
        self.current_range_day: Optional[datetime.date] = None

        # lịch sử 5m từ 4h NY → now (trong ngày hiện tại)
        self.candles_from_4h: List[Kline] = []

        # indicators trên candles_from_4h
        self.ema200_values: List[Optional[float]] = []
        self.atr_values: List[Optional[float]] = []

        self.active_trade: Optional[Trade] = None
        self.trade_counter: int = 0

        # để tránh xử lý trùng 1 entry_time
        self.seen_entry_times: Set[datetime] = set()

    # =========================
    #   PUBLIC API
    # =========================
    def on_new_candle(self, candle: Kline):
        """
        Gọi hàm này mỗi khi có NẾN 5M MỚI (đã đóng).
        """
        if candle.symbol != self.symbol:
            return

        ny_time = candle.open_time.astimezone(TRADING_TIMEZONE)
        ny_date = ny_time.date()
        ny_hour = ny_time.hour

        print(
            f"\n[SMC] New 5m candle: {candle.symbol} {candle.interval} "
            f"NY={ny_time} O={candle.open} H={candle.high} L={candle.low} C={candle.close}"
        )

        # 1) New day (NY) → reset range & history
        if self.current_range_day is None or ny_date != self.current_range_day:
            print(f"[SMC] New NY day={ny_date}, reset range & history.")
            self.current_range_day = ny_date
            self.current_range = None
            self.candles_from_4h = []
            self.ema200_values = []
            self.atr_values = []
            self.seen_entry_times.clear()
            # active_trade có thể giữ (nếu muốn đóng dở), hoặc bạn có thể đóng tay

        # 2) Luôn update trade đang mở với nến mới
        if self.active_trade is not None:
            self._update_active_trade_with_candle(candle)

        # 3) Nếu 00:00 → 04:00 NY → không tạo trade mới
        if 0 <= ny_hour < 4:
            print("[SMC] NY in [00:00, 04:00) → không tạo trade mới.")
            return

        # 4) Nếu chưa có range 4h → khởi tạo + load history & indicators
        if self.current_range is None:
            self._init_range_and_history(candle)
            # đợi cây tiếp theo rồi mới xem entry
            return

        # 5) Thêm candle vào history + update indicators
        self.candles_from_4h.append(candle)
        self._recalc_indicators()  # đơn giản: recalc toàn bộ, sau này có thể tối ưu increment

        # 6) Nếu đang có trade mở → không mở thêm
        if self.active_trade is not None and self.active_trade.is_open():
            print("[SMC] Đang có trade mở → không tạo trade mới.")
            return

        # 7) Tìm entry signal theo breakout + re-entry
        signals = detect_entry_signals(self.current_range, self.candles_from_4h)

        # chỉ lấy signal có entry_time = candle.open_time (entry trên cây hiện tại)
        candidate_signals = [
            s
            for s in signals
            if s.entry_time == candle.open_time and s.entry_time not in self.seen_entry_times
        ]

        if not candidate_signals:
            print("[SMC] Không có entry signal mới trên cây hiện tại.")
            return

        # đánh dấu đã thấy entry_time này
        for s in candidate_signals:
            self.seen_entry_times.add(s.entry_time)

        # 8) Áp dụng EMA/ATR filter
        filtered_signals = []
        for s in candidate_signals:
            if self._pass_filters(s):
                filtered_signals.append(s)

        if not filtered_signals:
            print("[SMC] Có signal breakout + re-entry nhưng KHÔNG qua EMA/ATR filter.")
            return

        # chọn signal cuối (nếu nhiều)
        signal = filtered_signals[-1]
        self._open_trade_from_signal(signal)

    # =========================
    #   INTERNAL METHODS
    # =========================
    def _init_range_and_history(self, latest_candle: Kline):
        ny_time = latest_candle.open_time.astimezone(TRADING_TIMEZONE)
        if ny_time.hour < 4:
            print("[SMC] _init_range_and_history gọi khi NY < 4h (bỏ).")
            return

        print("[SMC] Khởi tạo range 4h đầu ngày (NY) + history 5m & indicators...")

        rng = get_first_4h_high_low_newyork_futures(self.symbol)
        if rng is None:
            print("[SMC] Không lấy được range 4h.")
            return

        self.current_range = rng
        print(
            f"[SMC] Range 4H NY: HIGH={rng.high}, LOW={rng.low}, "
            f"NY({rng.start_ny} → {rng.end_ny})"
        )

        history = get_5m_candles_from_4h_to_now_newyork_futures(self.symbol)
        if history is None:
            history = []
        self.candles_from_4h = history

        print(f"[SMC] Loaded {len(self.candles_from_4h)} candles 5m từ 4h NY → now.")

        # tính indicators trên history
        self._recalc_indicators()

        # đánh dấu entry đã xảy ra trong quá khứ để skip
        past_signals = detect_entry_signals(self.current_range, self.candles_from_4h)
        for s in past_signals:
            self.seen_entry_times.add(s.entry_time)
        if past_signals:
            print(
                f"[SMC] Có {len(past_signals)} entry signals trong quá khứ, "
                f"sẽ skip, chờ đợt mới."
            )

    def _recalc_indicators(self):
        closes = [c.close for c in self.candles_from_4h]
        self.ema200_values = ema(closes, self.EMA_PERIOD)
        self.atr_values = atr(self.candles_from_4h, self.ATR_PERIOD)

    def _pass_filters(self, signal: EntrySignal) -> bool:
        """
        EMA filter + ATR filter tại thời điểm entry của signal.
        """
        # tìm index của entry_time trong candles_from_4h
        idx = None
        for i, c in enumerate(self.candles_from_4h):
            if c.open_time == signal.entry_time:
                idx = i
                break
        if idx is None:
            print("[SMC] _pass_filters: không tìm được index cho entry_time.")
            return False

        ema_val = self.ema200_values[idx] if idx < len(self.ema200_values) else None
        atr_val = self.atr_values[idx] if idx < len(self.atr_values) else None

        # cần đủ dữ liệu
        if ema_val is None or atr_val is None:
            print("[SMC] EMA/ATR chưa đủ dữ liệu, skip.")
            return False

        # ATR filter: ATR hiện tại phải >= 0.8 * ATR trung bình gần đây
        recent_atrs = [x for x in self.atr_values[max(0, idx - 30):idx + 1] if x is not None]
        if not recent_atrs:
            print("[SMC] Không có ATR recent để so sánh, skip.")
            return False

        avg_atr_recent = sum(recent_atrs) / len(recent_atrs)
        if atr_val < self.ATR_MIN_MULTIPLIER * avg_atr_recent:
            print(
                f"[SMC] ATR filter fail: atr_val={atr_val:.4f} "
                f"< {self.ATR_MIN_MULTIPLIER} * avg_recent={avg_atr_recent:.4f}"
            )
            return False

        entry_price = signal.entry_price

        # EMA200 trend filter
        # LONG: entry > EMA200
        # SHORT: entry < EMA200
        if signal.side == "LONG" and entry_price < ema_val:
            print(
                f"[SMC] EMA filter fail LONG: entry={entry_price:.2f} < EMA200={ema_val:.2f}"
            )
            return False

        if signal.side == "SHORT" and entry_price > ema_val:
            print(
                f"[SMC] EMA filter fail SHORT: entry={entry_price:.2f} > EMA200={ema_val:.2f}"
            )
            return False

        return True

    def _open_trade_from_signal(self, signal: EntrySignal):
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

        print("\n=== [SMC] OPEN TRADE ===")
        print(f"ID         : {t.id}")
        print(f"Symbol     : {t.symbol}")
        print(f"Side       : {t.side} (LONG=break từ LOW, SHORT=break từ HIGH)")
        print(f"Entry time : UTC={t.entry_time}, NY={ny_time}, VN={vn_time}")
        print(f"Entry      : {t.entry_price}")
        print(f"SL         : {t.sl_price}")
        print(f"TP         : {t.tp_price}")
        print("=========================\n")

    def _update_active_trade_with_candle(self, candle: Kline):
        t = self.active_trade
        if t is None or not t.is_open():
            return

        high = candle.high
        low = candle.low

        sl_hit = False
        tp_hit = False

        if t.side == "LONG":
            if low <= t.sl_price:
                sl_hit = True
            elif high >= t.tp_price:
                tp_hit = True
        else:  # SHORT
            if high >= t.sl_price:
                sl_hit = True
            elif low <= t.tp_price:
                tp_hit = True

        if not sl_hit and not tp_hit:
            return

        t.closed_at = candle.close_time
        if sl_hit:
            t.result = "SL"
            t.close_price = t.sl_price
        else:
            t.result = "TP"
            t.close_price = t.tp_price

        # tính P/L & RR
        if t.side == "LONG":
            risk = t.entry_price - t.sl_price
            pl = t.close_price - t.entry_price
        else:
            risk = t.sl_price - t.entry_price
            pl = t.entry_price - t.close_price

        t.pl_points = pl
        t.rr = pl / risk if risk != 0 else None

        ny_time = t.closed_at.astimezone(TRADING_TIMEZONE)
        vn_time = t.closed_at.astimezone(VN_TZ)

        print("\n=== [SMC] CLOSE TRADE ===")
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
        print("==========================\n")

        self.active_trade = None
