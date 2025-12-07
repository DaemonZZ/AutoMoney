from typing import List
from zoneinfo import ZoneInfo

from data.kline import Kline
from data.range_4h_ny import Range4HNY
from data.break_event import BreakEvent
from data.range_break_state import RangeBreakState
from config import TRADING_TIMEZONE

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def analyze_range_break_state(
    range_4h: Range4HNY,
    candles_5m: List[Kline],
) -> RangeBreakState:
    """
    Phân tích các nến 5m để:
      - Tìm LẦN PHÁ RANGE GẦN NHẤT (last_exit)
      - Tìm LẦN VÀO LẠI gần nhất (last_reentry)
      - Xác định current_state: INSIDE / OUTSIDE_ABOVE / OUTSIDE_BELOW

    Quy tắc:
      - EXIT_UP (thoát lên HIGH):
          thân cắt qua high & close > high
      - EXIT_DOWN (thoát xuống LOW):
          thân cắt qua low & close < low
      - REENTER_FROM_ABOVE:
          sau 1 EXIT_UP, thân nến cắt high & close nằm trong [low, high]
      - REENTER_FROM_BELOW:
          sau 1 EXIT_DOWN, thân nến cắt low & close nằm trong [low, high]

    Kết quả:
      - RangeBreakState chứa last_exit, last_reentry, current_state,
        và các property: waiting_for_breakout, waiting_for_reentry.
    """

    high_level = range_4h.high
    low_level = range_4h.low

    def classify_position(price: float) -> str:
        if price > high_level:
            return "OUTSIDE_ABOVE"
        if price < low_level:
            return "OUTSIDE_BELOW"
        return "INSIDE"

    last_exit: BreakEvent | None = None
    last_reentry: BreakEvent | None = None

    # state theo close
    current_state = "INSIDE"
    if candles_5m:
        current_state = classify_position(candles_5m[0].close)

    for c in candles_5m:
        o = c.open
        cl = c.close

        # ----- kiểm tra breakout lên HIGH -----
        cross_high = (o - high_level) * (cl - high_level) < 0
        if cross_high and cl > high_level:
            last_exit = BreakEvent(
                symbol=c.symbol,
                level_type="HIGH",
                kind="EXIT_UP",
                level=high_level,
                candle=c,
            )
            current_state = "OUTSIDE_ABOVE"
            # sau khi breakout, không check reentry trên cùng cây
            continue

        # ----- breakout xuống LOW -----
        cross_low = (o - low_level) * (cl - low_level) < 0
        if cross_low and cl < low_level:
            last_exit = BreakEvent(
                symbol=c.symbol,
                level_type="LOW",
                kind="EXIT_DOWN",
                level=low_level,
                candle=c,
            )
            current_state = "OUTSIDE_BELOW"
            continue

        # ----- REENTRY FROM ABOVE -----
        if current_state == "OUTSIDE_ABOVE" and last_exit is not None and last_exit.kind == "EXIT_UP":
            cross_high_back = (o - high_level) * (cl - high_level) < 0
            inside_after = (low_level <= cl <= high_level)
            if cross_high_back and inside_after:
                last_reentry = BreakEvent(
                    symbol=c.symbol,
                    level_type="HIGH",
                    kind="REENTER_FROM_ABOVE",
                    level=high_level,
                    candle=c,
                )
                current_state = "INSIDE"
                # sau khi vào lại, tiếp tục scan để tìm breakout mới hơn

        # ----- REENTRY FROM BELOW -----
        if current_state == "OUTSIDE_BELOW" and last_exit is not None and last_exit.kind == "EXIT_DOWN":
            cross_low_back = (o - low_level) * (cl - low_level) < 0
            inside_after = (low_level <= cl <= high_level)
            if cross_low_back and inside_after:
                last_reentry = BreakEvent(
                    symbol=c.symbol,
                    level_type="LOW",
                    kind="REENTER_FROM_BELOW",
                    level=low_level,
                    candle=c,
                )
                current_state = "INSIDE"

        # nếu không có sự kiện đặc biệt, cập nhật state theo close
        if last_exit is None or (
            last_reentry is not None
            and last_reentry.candle.open_time >= last_exit.candle.open_time
        ):
            # không có exit mở → chỉ theo close
            current_state = classify_position(cl)
        else:
            # nếu đang có exit chưa có reentry, ưu tiên trạng thái OUTSIDE_* theo exit
            if last_exit.kind == "EXIT_UP":
                if low_level <= cl <= high_level:
                    current_state = "INSIDE"
                elif cl > high_level:
                    current_state = "OUTSIDE_ABOVE"
                else:
                    current_state = "OUTSIDE_BELOW"
            else:
                if low_level <= cl <= high_level:
                    current_state = "INSIDE"
                elif cl < low_level:
                    current_state = "OUTSIDE_BELOW"
                else:
                    current_state = "OUTSIDE_ABOVE"

    return RangeBreakState(
        range_4h=range_4h,
        current_state=current_state,
        last_exit=last_exit,
        last_reentry=last_reentry,
    )


def print_range_break_state(state: RangeBreakState):
    print("=== RANGE STATE ===")
    print(f"Symbol        : {state.range_4h.symbol}")
    print(f"Range High    : {state.range_4h.high}")
    print(f"Range Low     : {state.range_4h.low}")
    print(f"Current state : {state.current_state}")
    print(f"Wait breakout : {state.waiting_for_breakout}")
    print(f"Wait reentry  : {state.waiting_for_reentry}")

    def p_event(title: str, ev: BreakEvent | None):
        print(f"\n--- {title} ---")
        if ev is None:
            print("  Không có.")
            return
        k = ev.candle
        t_utc = k.open_time
        t_ny = t_utc.astimezone(TRADING_TIMEZONE)
        t_vn = t_utc.astimezone(VN_TZ)
        print(f"  Kind     : {ev.kind}")
        print(f"  Level    : {ev.level_type} = {ev.level}")
        print(f"  UTC      : {t_utc}")
        print(f"  New York : {t_ny}")
        print(f"  Việt Nam : {t_vn}")
        print(f"  O={k.open}, H={k.high}, L={k.low}, C={k.close}")

    p_event("LAST EXIT (lần phá range gần nhất)", state.last_exit)
    p_event("LAST REENTRY (lần vào lại gần nhất)", state.last_reentry)
