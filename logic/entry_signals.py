from typing import List
from data.kline import Kline
from data.range_4h_ny import Range4HNY
from data.break_event import BreakEvent
from data.entry_signal import EntrySignal


def detect_entry_signals(
    range_4h: Range4HNY,
    candles_5m: List[Kline],
) -> List[EntrySignal]:
    """
    Quét list nến 5m (sau 4h đầu ngày) để tìm các tín hiệu vào lệnh:

    - Nếu giá phá xuống LOW rồi re-entry lên lại vùng -> LONG.
    - Nếu giá phá lên HIGH rồi re-entry xuống lại vùng -> SHORT.

    Entry:
        - Vào ở nến NGAY SAU nến re-entry:
            entry_time  = open_time của nến sau
            entry_price = open của nến sau

    SL:
        - LONG: SL = đáy thấp nhất của đoạn từ EXIT -> REENTRY (min low)
        - SHORT: SL = đỉnh cao nhất của đoạn từ EXIT -> REENTRY (max high)

    TP:
        - TP = entry_price +/- 2 * risk
        - LONG : TP = entry + 2 * (entry - SL)
        - SHORT: TP = entry - 2 * (SL - entry)
    """

    high_level = range_4h.high
    low_level = range_4h.low

    signals: List[EntrySignal] = []

    state = "INSIDE"  # "INSIDE", "OUTSIDE_ABOVE", "OUTSIDE_BELOW"
    current_exit: BreakEvent | None = None
    exit_index: int | None = None  # để biết đoạn EXIT -> REENTRY

    def is_inside(price: float) -> bool:
        return low_level <= price <= high_level

    n = len(candles_5m)

    for i in range(n):
        c = candles_5m[i]
        o = c.open
        cl = c.close

        # ---------------------------
        # 1) EXIT logic
        # ---------------------------
        if state == "INSIDE":
            # EXIT_UP (phá lên HIGH)
            cross_high = (o - high_level) * (cl - high_level) < 0
            if cross_high and cl > high_level:
                current_exit = BreakEvent(
                    symbol=c.symbol,
                    level_type="HIGH",
                    kind="EXIT_UP",
                    level=high_level,
                    candle=c,
                )
                exit_index = i
                state = "OUTSIDE_ABOVE"
                continue

            # EXIT_DOWN (phá xuống LOW)
            cross_low = (o - low_level) * (cl - low_level) < 0
            if cross_low and cl < low_level:
                current_exit = BreakEvent(
                    symbol=c.symbol,
                    level_type="LOW",
                    kind="EXIT_DOWN",
                    level=low_level,
                    candle=c,
                )
                exit_index = i
                state = "OUTSIDE_BELOW"
                continue

        # ---------------------------
        # 2) REENTRY logic
        # ---------------------------
        if (
            state == "OUTSIDE_ABOVE"
            and current_exit is not None
            and current_exit.kind == "EXIT_UP"
            and exit_index is not None
        ):
            cross_high_back = (o - high_level) * (cl - high_level) < 0
            inside_after = is_inside(cl)
            if cross_high_back and inside_after:
                # REENTRY từ phía trên xuống trong vùng
                reentry = BreakEvent(
                    symbol=c.symbol,
                    level_type="HIGH",
                    kind="REENTER_FROM_ABOVE",
                    level=high_level,
                    candle=c,
                )

                # Nến kế tiếp là entry
                if i + 1 < n:
                    next_candle = candles_5m[i + 1]
                    entry_price = next_candle.open

                    # ----- TÍNH SL/TP CHO SHORT -----
                    segment = candles_5m[exit_index : i + 1]  # EXIT -> REENTRY
                    max_high = max(cc.high for cc in segment)
                    sl_price = max_high
                    risk = sl_price - entry_price  # với short, SL > entry

                    if risk > 0:
                        tp_price = entry_price - 2 * risk
                        signals.append(
                            EntrySignal(
                                symbol=c.symbol,
                                side="SHORT",
                                range_side="HIGH",
                                exit_event=current_exit,
                                reentry_event=reentry,
                                entry_time=next_candle.open_time,
                                entry_price=entry_price,
                                sl_price=sl_price,
                                tp_price=tp_price,
                                risk=risk,
                                rr=2.0,
                            )
                        )

                # reset để chờ vòng mới
                state = "INSIDE"
                current_exit = None
                exit_index = None
                continue

        if (
            state == "OUTSIDE_BELOW"
            and current_exit is not None
            and current_exit.kind == "EXIT_DOWN"
            and exit_index is not None
        ):
            cross_low_back = (o - low_level) * (cl - low_level) < 0
            inside_after = is_inside(cl)
            if cross_low_back and inside_after:
                reentry = BreakEvent(
                    symbol=c.symbol,
                    level_type="LOW",
                    kind="REENTER_FROM_BELOW",
                    level=low_level,
                    candle=c,
                )

                if i + 1 < n:
                    next_candle = candles_5m[i + 1]
                    entry_price = next_candle.open

                    # ----- TÍNH SL/TP CHO LONG -----
                    segment = candles_5m[exit_index : i + 1]  # EXIT -> REENTRY
                    min_low = min(cc.low for cc in segment)
                    sl_price = min_low
                    risk = entry_price - sl_price  # với long, entry > SL

                    if risk > 0:
                        tp_price = entry_price + 2 * risk
                        signals.append(
                            EntrySignal(
                                symbol=c.symbol,
                                side="LONG",
                                range_side="LOW",
                                exit_event=current_exit,
                                reentry_event=reentry,
                                entry_time=next_candle.open_time,
                                entry_price=entry_price,
                                sl_price=sl_price,
                                tp_price=tp_price,
                                risk=risk,
                                rr=2.0,
                            )
                        )

                state = "INSIDE"
                current_exit = None
                exit_index = None
                continue

        # ---------------------------
        # 3) Update state đơn giản nếu không có event
        # ---------------------------
        if is_inside(cl):
            if state != "INSIDE":
                state = "INSIDE"
                current_exit = None
                exit_index = None
        else:
            if cl > high_level:
                state = "OUTSIDE_ABOVE"
            elif cl < low_level:
                state = "OUTSIDE_BELOW"

    return signals
