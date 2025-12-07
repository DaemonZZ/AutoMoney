# strategy/ema_pullback_v2.py

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List
from datetime import datetime


# =========================
#   ENUM & DATA CLASSES
# =========================

class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class TrendSide(str, Enum):
    UP = "UP"
    DOWN = "DOWN"
    NONE = "NONE"


@dataclass
class CandleWithInd:
    """
    1 nến 5m kèm indicator đã tính sẵn:
    - ema_fast: EMA nhanh (VD: 21)
    - ema_slow: EMA chậm (VD: 200)
    - atr     : ATR (VD: 14)
    """
    open_time: datetime
    open: float
    high: float
    low: float
    close: float

    ema_fast: float
    ema_slow: float
    atr: float


@dataclass
class EntrySignal:
    """
    Thông tin 1 lệnh entry được sinh ra bởi strategy.
        - index      : index của candle trong list candles
        - side       : LONG / SHORT
        - trend_side : UP / DOWN
        - entry_price, sl, tp
        - risk_pts   : khoảng cách entry -> SL (dương)
        - rr         : R-multiple mục tiêu (thường 2.0)
    """
    index: int
    side: Side
    trend_side: TrendSide

    entry_price: float
    sl: float
    tp: float
    risk_pts: float
    rr: float


@dataclass
class EmaPullbackParams:
    """
    Tham số tinh chỉnh chiến lược EMA Pullback v2
    """

    # Cấu hình EMA / ATR (để bạn backtest cho đồng nhất)
    ema_fast_period: int = 21
    ema_slow_period: int = 200
    atr_period: int = 14

    # Take profit theo R-multiple (TP = entry ± R * risk)
    r_mult: float = 2.0

    # Dùng ATR buffer cho SL (đẩy SL ra xa thêm chút so với đáy/đỉnh pullback)
    use_atr_buffer: bool = True
    atr_buffer_mult: float = 0.3

    # --- Trend filter ---

    # Khoảng cách tối thiểu giữa EMA nhanh & chậm (tính theo ATR)
    # VD: min_trend_ema_distance_atr = 0.5 nghĩa là:
    #   |ema_fast - ema_slow| >= 0.5 * ATR
    min_trend_ema_distance_atr: float = 0.5

    # Số bar tối thiểu trend phải giữ (UP/DOWN liên tục) trước khi trade
    min_trend_bars: int = 5

    # --- Pullback config ---

    # Số bar pullback tối thiểu & tối đa
    min_pullback_bars: int = 2
    max_pullback_bars: int = 10

    # Độ sâu pullback tính theo ATR:
    #   - Uptrend: depth = (swing_high - pullback_low) / ATR_entry
    #   - Downtrend: depth = (pullback_high - swing_low) / ATR_entry
    # depth phải nằm trong [min_pullback_depth_atr, max_pullback_depth_atr]
    min_pullback_depth_atr: float = 0.5
    max_pullback_depth_atr: float = 2.5

    # Không cho phép entry quá xa EMA nhanh (tránh đu FOMO)
    # Khoảng cách tối đa: max_entry_distance_from_ema_atr * ATR
    max_entry_distance_from_ema_atr: float = 0.7

    # Số pullback tối đa được trade trong 1 trend (0 = không giới hạn)
    max_pullbacks_per_trend: int = 3


# =========================
#   CORE LOGIC
# =========================

def _detect_trend(c: CandleWithInd, params: EmaPullbackParams) -> TrendSide:
    """
    Xác định trend tức thời dựa vào EMA nhanh & chậm + ATR.

    - Trend UP khi:
        ema_fast > ema_slow
        và (ema_fast - ema_slow) >= min_trend_ema_distance_atr * ATR

    - Trend DOWN khi ngược lại.
    - Nếu không đủ “độ dốc” thì trả về NONE.
    """
    if c.atr <= 0:
        return TrendSide.NONE

    diff = c.ema_fast - c.ema_slow
    threshold = params.min_trend_ema_distance_atr * c.atr

    if diff >= threshold:
        return TrendSide.UP
    elif -diff >= threshold:
        return TrendSide.DOWN
    else:
        return TrendSide.NONE


def find_ema_pullback_entries_v2(
    candles: List[CandleWithInd],
    params: EmaPullbackParams,
) -> List[EntrySignal]:
    """
    Chiến lược EMA Pullback v2:

    1) Xác định trend bằng EMA21 vs EMA200 + ATR:
        - UP  : ema_fast > ema_slow & cách nhau >= min_trend_ema_distance_atr * ATR
        - DOWN: ema_fast < ema_slow & cách nhau >= min_trend_ema_distance_atr * ATR

    2) Chỉ trade khi trend giữ được ít nhất min_trend_bars.

    3) Trong trend:
        - Uptrend:
            * Theo dõi swing_high (đỉnh mới nhất của sóng tăng).
            * Pullback bắt đầu khi nến đóng dưới EMA nhanh (close < ema_fast).
            * Trong pullback, theo dõi:
                - pb_low  : đáy thấp nhất của pullback
                - pb_high : đỉnh cao nhất (để tham chiếu)
                - pb_bars : số nến pullback
            * Điều kiện entry:
                - pb_bars ∈ [min_pullback_bars, max_pullback_bars]
                - Độ sâu pullback (swing_high - pb_low)/ATR trong
                  [min_pullback_depth_atr, max_pullback_depth_atr]
                - Nến tín hiệu đóng lại phía trên EMA nhanh
                  (close > ema_fast, và low <= ema_fast để đảm bảo có chạm/tiếp cận EMA)
                - Entry không cách EMA nhanh quá max_entry_distance_from_ema_atr * ATR
                - SL = pb_low - buffer (buffer = atr_buffer_mult * ATR nếu bật)
                - TP = entry + R * (entry - SL)

        - Downtrend: mirror logic ngược lại.

    4) Sau khi tạo 1 entry, pullback kết thúc; chờ Sóng mới (swing mới) & pullback tiếp theo.
    """

    n = len(candles)
    if n == 0:
        return []

    signals: List[EntrySignal] = []

    current_trend: TrendSide = TrendSide.NONE
    trend_bars: int = 0
    swing_high_price: float | None = None
    swing_low_price: float | None = None

    # pullback state
    pullback_active: bool = False
    pullback_start_index: int | None = None
    pullback_high: float | None = None
    pullback_low: float | None = None
    pullback_bars: int = 0
    pullback_count_in_trend: int = 0

    def reset_pullback():
        nonlocal pullback_active, pullback_start_index, pullback_high, pullback_low, pullback_bars
        pullback_active = False
        pullback_start_index = None
        pullback_high = None
        pullback_low = None
        pullback_bars = 0

    for i, c in enumerate(candles):
        # 1) xác định trend hiện tại
        bar_trend = _detect_trend(c, params)

        if bar_trend != current_trend:
            # trend đổi (hoặc từ NONE sang UP/DOWN)
            current_trend = bar_trend
            if current_trend == TrendSide.NONE:
                trend_bars = 0
                swing_high_price = None
                swing_low_price = None
                pullback_count_in_trend = 0
                reset_pullback()
            else:
                trend_bars = 1
                swing_high_price = c.high
                swing_low_price = c.low
                pullback_count_in_trend = 0
                reset_pullback()
            # sang bar tiếp theo
            continue
        else:
            # trend giữ nguyên
            if current_trend == TrendSide.NONE:
                # chưa có trend, bỏ qua
                continue
            trend_bars += 1

        # 2) Chỉ bắt đầu logic pullback nếu trend đã đủ "chín"
        if trend_bars < params.min_trend_bars:
            # trong giai đoạn early trend, vẫn cập nhật swing cho đẹp
            if current_trend == TrendSide.UP:
                swing_high_price = max(swing_high_price, c.high) if swing_high_price is not None else c.high
                swing_low_price = min(swing_low_price, c.low) if swing_low_price is not None else c.low
            elif current_trend == TrendSide.DOWN:
                swing_low_price = min(swing_low_price, c.low) if swing_low_price is not None else c.low
                swing_high_price = max(swing_high_price, c.high) if swing_high_price is not None else c.high
            continue

        # Nếu giới hạn số pullback mỗi trend
        if params.max_pullbacks_per_trend > 0 and pullback_count_in_trend >= params.max_pullbacks_per_trend:
            # Không nhận thêm tín hiệu mới trong trend này
            # nhưng vẫn cập nhật swing cho có
            if current_trend == TrendSide.UP:
                swing_high_price = max(swing_high_price, c.high) if swing_high_price is not None else c.high
            else:
                swing_low_price = min(swing_low_price, c.low) if swing_low_price is not None else c.low
            continue

        # =====================
        #   UP TREND LOGIC
        # =====================
        if current_trend == TrendSide.UP:
            # Cập nhật swing high khi chưa có pullback
            if not pullback_active:
                if swing_high_price is None or c.high > swing_high_price:
                    swing_high_price = c.high

                # điều kiện bắt đầu pullback: nến đóng dưới EMA nhanh
                if c.close < c.ema_fast:
                    pullback_active = True
                    pullback_start_index = i
                    pullback_high = c.high
                    pullback_low = c.low
                    pullback_bars = 1
                continue

            # Đang trong pullback
            pullback_bars += 1
            pullback_high = max(pullback_high, c.high) if pullback_high is not None else c.high
            pullback_low = min(pullback_low, c.low) if pullback_low is not None else c.low

            # Nếu pullback quá dài -> bỏ, reset
            if pullback_bars > params.max_pullback_bars:
                reset_pullback()
                continue

            # Cần swing_high để đo độ sâu
            if swing_high_price is None or c.atr <= 0:
                continue

            depth_atr = (swing_high_price - pullback_low) / c.atr  # luôn >= 0

            # Nếu pullback quá sâu (deep correction) -> coi như trend yếu, bỏ
            if depth_atr > params.max_pullback_depth_atr:
                reset_pullback()
                continue

            # Điều kiện entry: nến đóng lại phía trên EMA nhanh
            # và có dấu hiệu “quét qua” EMA (low <= ema_fast)
            if (
                c.close > c.ema_fast
                and c.low <= c.ema_fast
                and pullback_bars >= params.min_pullback_bars
                and depth_atr >= params.min_pullback_depth_atr
            ):
                # Không cho entry quá xa EMA nhanh
                dist_from_ema = abs(c.close - c.ema_fast)
                if dist_from_ema > params.max_entry_distance_from_ema_atr * c.atr:
                    # nến đóng quá xa EMA -> bỏ, reset pullback (coi như đã chạy rồi)
                    reset_pullback()
                    # cập nhật swing high mới từ nến breakout
                    swing_high_price = c.high
                    continue

                entry_price = c.close
                atr_here = c.atr
                buffer = params.atr_buffer_mult * atr_here if params.use_atr_buffer else 0.0

                # SL dưới đáy pullback (pb_low) trừ thêm buffer
                sl = pullback_low - buffer
                if sl >= entry_price:
                    # trường hợp ATR quá nhỏ gây SL >= entry -> bỏ
                    reset_pullback()
                    swing_high_price = c.high
                    continue

                risk = entry_price - sl
                tp = entry_price + params.r_mult * risk

                signals.append(
                    EntrySignal(
                        index=i,
                        side=Side.LONG,
                        trend_side=TrendSide.UP,
                        entry_price=entry_price,
                        sl=sl,
                        tp=tp,
                        risk_pts=risk,
                        rr=params.r_mult,
                    )
                )

                pullback_count_in_trend += 1
                # Sau khi breakout, coi nến hiện tại là swing high mới để đo pullback tiếp theo
                swing_high_price = c.high
                reset_pullback()
                continue

        # =====================
        #   DOWN TREND LOGIC
        # =====================
        elif current_trend == TrendSide.DOWN:
            # Cập nhật swing low khi chưa có pullback
            if not pullback_active:
                if swing_low_price is None or c.low < swing_low_price:
                    swing_low_price = c.low

                # Bắt đầu pullback khi nến đóng trên EMA nhanh (giá hồi lên)
                if c.close > c.ema_fast:
                    pullback_active = True
                    pullback_start_index = i
                    pullback_high = c.high
                    pullback_low = c.low
                    pullback_bars = 1
                continue

            # Đang trong pullback
            pullback_bars += 1
            pullback_high = max(pullback_high, c.high) if pullback_high is not None else c.high
            pullback_low = min(pullback_low, c.low) if pullback_low is not None else c.low

            if pullback_bars > params.max_pullback_bars:
                reset_pullback()
                continue

            if swing_low_price is None or c.atr <= 0:
                continue

            depth_atr = (pullback_high - swing_low_price) / c.atr  # >= 0

            if depth_atr > params.max_pullback_depth_atr:
                reset_pullback()
                continue

            # Entry SHORT khi nến đóng lại dưới EMA nhanh & high >= ema_fast
            if (
                c.close < c.ema_fast
                and c.high >= c.ema_fast
                and pullback_bars >= params.min_pullback_bars
                and depth_atr >= params.min_pullback_depth_atr
            ):
                dist_from_ema = abs(c.close - c.ema_fast)
                if dist_from_ema > params.max_entry_distance_from_ema_atr * c.atr:
                    # breakout quá xa EMA -> bỏ
                    reset_pullback()
                    swing_low_price = c.low
                    continue

                entry_price = c.close
                atr_here = c.atr
                buffer = params.atr_buffer_mult * atr_here if params.use_atr_buffer else 0.0

                # SL trên đỉnh pullback + buffer
                sl = pullback_high + buffer
                if sl <= entry_price:
                    reset_pullback()
                    swing_low_price = c.low
                    continue

                risk = sl - entry_price
                tp = entry_price - params.r_mult * risk

                signals.append(
                    EntrySignal(
                        index=i,
                        side=Side.SHORT,
                        trend_side=TrendSide.DOWN,
                        entry_price=entry_price,
                        sl=sl,
                        tp=tp,
                        risk_pts=risk,
                        rr=params.r_mult,
                    )
                )

                pullback_count_in_trend += 1
                swing_low_price = c.low
                reset_pullback()
                continue

    return signals
