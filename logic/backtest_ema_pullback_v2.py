# logic/backtest_ema_pullback_v2.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, time
from typing import List, Optional, Tuple

from zoneinfo import ZoneInfo

from data.kline import Kline
from logic.indicators import ema, atr


# ============================================================
#  PARAMS & DATA CLASSES
# ============================================================

@dataclass
class EmaPullbackParams:
    ema_fast_period: int = 21
    ema_slow_period: int = 200
    atr_period: int = 14
    atr_mult: float = 1.0        # SL = entry +/- ATR * atr_mult
    rr: float = 2.0              # TP = entry +/- ATR * rr * atr_mult

    # filter thêm
    min_bars_after_cross: int = 50  # số nến tối thiểu sau khi fast & slow cắt nhau mới cho trade
    max_hold_bars: int = 12         # số nến tối đa giữ lệnh (nếu chưa TP/SL thì thoát theo giá close)

    # giờ trade theo New York
    trade_session_ny_start: time = time(4, 0)   # 04:00
    trade_session_ny_end: time = time(20, 0)    # 20:00


@dataclass
class EntrySignal:
    index: int
    side: str             # "LONG" hoặc "SHORT"
    entry_price: float
    sl: float
    tp: float
    ema_fast: float
    ema_slow: float
    atr: float


@dataclass
class TradeResult:
    signal: EntrySignal
    exit_price: float
    exit_index: int
    exit_time: datetime
    result_r: float
    is_win: bool


# ============================================================
#  FORMAT HỖ TRỢ IN GIÁ / ATR / R
# ============================================================

def fmt_price(p: Optional[float]) -> str:
    """Format giá đa dụng cho Futures:
       - BTC/ETH giá lớn → 2 decimal
       - Altcoin vừa     → 4 decimal
       - Meme coin nhỏ   → 6 decimal
    """
    if p is None:
        return "N/A"

    abs_p = abs(p)

    if abs_p >= 1:
        return f"{p:.2f}"
    elif abs_p >= 0.01:
        return f"{p:.4f}"
    else:
        return f"{p:.6f}"


def fmt_r(r: Optional[float]) -> str:
    if r is None:
        return "N/A"
    return f"{r:.2f}"


def fmt_atr(a: Optional[float]) -> str:
    return fmt_price(a)


# ============================================================
#  HÀM HỖ TRỢ
# ============================================================

TZ_NY = ZoneInfo("America/New_York")
TZ_UTC = ZoneInfo("UTC")


def is_in_session_ny(
    dt_utc,
    start_hour: int | None,
    end_hour: int | None,
) -> bool:
    """
    Kiểm tra nến (UTC) có nằm trong phiên New York không (theo giờ *nguyên*).
    - start_hour, end_hour: kiểu int, 0–23. Ví dụ: 4 -> 4h, 20 -> 20h.
    - Nếu 1 trong 2 là None -> không lọc, luôn True.
    - Hỗ trợ cả phiên qua đêm (ví dụ 20 -> 4).
    """
    # Nếu không cấu hình phiên => luôn trade
    if start_hour is None or end_hour is None:
        return True

    ny_dt = dt_utc.astimezone(TZ_NY)
    h = ny_dt.hour  # 0–23

    if start_hour == end_hour:
        # Nếu cấu hình 4–4 thì hiểu là không lọc (cả ngày)
        return True

    if start_hour < end_hour:
        # Phiên trong cùng 1 ngày, ví dụ 4 -> 20
        return start_hour <= h < end_hour
    else:
        # Phiên qua đêm, ví dụ 20 -> 4
        return h >= start_hour or h < end_hour


def build_indicators(
    candles: List[Kline],
    params: EmaPullbackParams,
) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    closes = [c.close for c in candles]

    ema_fast_list = ema(closes, params.ema_fast_period)
    ema_slow_list = ema(closes, params.ema_slow_period)
    atr_list = atr(candles, params.atr_period)

    return ema_fast_list, ema_slow_list, atr_list


def compute_trend_side(
    idx: int,
    ema_fast_list: List[Optional[float]],
    ema_slow_list: List[Optional[float]],
) -> Optional[str]:
    """Xác định trend tại index: 'UP', 'DOWN', hoặc None (sideway)."""
    ef = ema_fast_list[idx]
    es = ema_slow_list[idx]
    if ef is None or es is None:
        return None

    # cho một chút buffer để tránh nhiễu
    if ef > es * 1.0002:
        return "UP"
    elif ef < es * 0.9998:
        return "DOWN"
    else:
        return None


def find_last_trend_cross_idx(
    idx: int,
    ema_fast_list: List[Optional[float]],
    ema_slow_list: List[Optional[float]],
) -> Optional[int]:
    """
    Tìm index nến gần nhất trong quá khứ mà EMA_FAST và EMA_SLOW vừa cross.
    Dùng để đảm bảo trend đã hình thành đủ lâu.
    """
    curr_side = compute_trend_side(idx, ema_fast_list, ema_slow_list)
    if curr_side is None:
        return None

    i = idx - 1
    while i >= 0:
        side_i = compute_trend_side(i, ema_fast_list, ema_slow_list)
        if side_i != curr_side and side_i is not None:
            # cross xảy ra somewhere giữa i và i+1
            return i + 1
        i -= 1
    return None


def detect_entry_signal(
    idx: int,
    candles: List[Kline],
    ema_fast_list: List[Optional[float]],
    ema_slow_list: List[Optional[float]],
    atr_list: List[Optional[float]],
    params: EmaPullbackParams,
) -> Optional[EntrySignal]:
    """Logic tìm tín hiệu entry tại index idx."""

    c = candles[idx]
    ef = ema_fast_list[idx]
    es = ema_slow_list[idx]
    a = atr_list[idx]

    if ef is None or es is None or a is None:
        return None

    # chỉ trade trong khung giờ NY
    if not is_in_session_ny(c.close_time, params.trade_session_ny_start, params.trade_session_ny_end):
        return None

    # trend
    trend_side = compute_trend_side(idx, ema_fast_list, ema_slow_list)
    if trend_side is None:
        return None

    # đảm bảo trend đã tồn tại đủ lâu
    cross_idx = find_last_trend_cross_idx(idx, ema_fast_list, ema_slow_list)
    if cross_idx is None:
        return None
    if idx - cross_idx < params.min_bars_after_cross:
        return None

    # cần có nến trước để check pullback
    if idx == 0:
        return None

    prev_c = candles[idx - 1]
    close_prev = prev_c.close
    close_curr = c.close

    # ---------------------------
    #  LONG trong uptrend
    # ---------------------------
    if trend_side == "UP":
        # điều kiện cơ bản:
        # - giá luôn ở trên EMA_SLOW (filter dạng trend lớn)
        # - nến trước pullback: close_prev <= ef
        # - nến hiện tại bật lên lại trên EMA_FAST: close_curr > ef
        if c.low < es:
            # chạm mạnh quá xuống dưới slow => bỏ
            return None

        if not (close_prev <= ef and close_curr > ef):
            return None

        side = "LONG"
        entry = close_curr
        sl = entry - params.atr_mult * a
        tp = entry + params.rr * params.atr_mult * a

    # ---------------------------
    #  SHORT trong downtrend
    # ---------------------------
    elif trend_side == "DOWN":
        # - giá dưới EMA_SLOW
        # - nến trước pullback: close_prev >= ef
        # - nến hiện tại breakdown dưới EMA_FAST: close_curr < ef
        if c.high > es:
            # bật quá đầu slow => bỏ
            return None

        if not (close_prev >= ef and close_curr < ef):
            return None

        side = "SHORT"
        entry = close_curr
        sl = entry + params.atr_mult * a
        tp = entry - params.rr * params.atr_mult * a

    else:
        return None

    return EntrySignal(
        index=idx,
        side=side,
        entry_price=entry,
        sl=sl,
        tp=tp,
        ema_fast=ef,
        ema_slow=es,
        atr=a,
    )


def simulate_trade(
    signal: EntrySignal,
    candles: List[Kline],
    params: EmaPullbackParams,
) -> TradeResult:
    """
    Mô phỏng diễn biến lệnh sau khi vào:
      - kiểm tra chạm SL / TP bằng high/low
      - nếu hết max_hold_bars mà chưa chạm thì thoát theo close cuối cùng
    """
    idx_entry = signal.index
    entry_price = signal.entry_price
    sl = signal.sl
    tp = signal.tp

    n = len(candles)
    max_exit_idx = min(n - 1, idx_entry + params.max_hold_bars)

    exit_idx = max_exit_idx
    exit_price = candles[max_exit_idx].close
    is_win = False
    result_r = 0.0

    for i in range(idx_entry + 1, max_exit_idx + 1):
        c = candles[i]
        high = c.high
        low = c.low

        if signal.side == "LONG":
            # ưu tiên SL trước TP (conservative)
            if low <= sl:
                exit_idx = i
                exit_price = sl
                is_win = False
                break
            elif high >= tp:
                exit_idx = i
                exit_price = tp
                is_win = True
                break
        else:  # SHORT
            if high >= sl:
                exit_idx = i
                exit_price = sl
                is_win = False
                break
            elif low <= tp:
                exit_idx = i
                exit_price = tp
                is_win = True
                break

    # tính R
    if signal.side == "LONG":
        risk = entry_price - sl
        if risk <= 0:
            result_r = 0.0
        else:
            result_r = (exit_price - entry_price) / risk
    else:  # SHORT
        risk = sl - entry_price
        if risk <= 0:
            result_r = 0.0
        else:
            result_r = (entry_price - exit_price) / risk

    exit_time = candles[exit_idx].close_time

    return TradeResult(
        signal=signal,
        exit_price=exit_price,
        exit_index=exit_idx,
        exit_time=exit_time,
        result_r=result_r,
        is_win=result_r > 0,
    )


# ============================================================
#  HÀM CHÍNH BACKTEST
# ============================================================

def backtest_ema_pullback_v2(
    raw_klines: List[Kline],
    params: EmaPullbackParams,
    symbol: str,
    interval: str,
) -> Tuple[
    List[TradeResult],
    List[Kline],
    List[Optional[float]],
    List[Optional[float]],
    List[Optional[float]],
]:
    """
    raw_klines: list[Kline] đã convert từ API.
    Trả về:
      - trades
      - candles
      - ema_fast_list
      - ema_slow_list
      - atr_list
    Và in ra bảng + tổng kết.
    """
    candles = raw_klines
    ema_fast_list, ema_slow_list, atr_list = build_indicators(candles, params)

    trades: List[TradeResult] = []

    for i in range(len(candles)):
        sig = detect_entry_signal(
            i, candles, ema_fast_list, ema_slow_list, atr_list, params
        )
        if sig is None:
            continue

        trade = simulate_trade(sig, candles, params)
        trades.append(trade)

    # In tổng kết
    print(f"[INFO] Symbol={symbol}, TF={interval}, EMA_FAST={params.ema_fast_period}, "
          f"EMA_SLOW={params.ema_slow_period}, ATR={params.atr_period}, R={params.rr:.2f}")
    print_trade_list(trades)
    print_summary(trades)

    return trades, candles, ema_fast_list, ema_slow_list, atr_list


# ============================================================
#  IN BẢNG DANH SÁCH LỆNH + SUMMARY
# ============================================================

def print_trade_list(trades: List[TradeResult]) -> None:
    print("===== DANH SÁCH LỆNH EMA_PULLBACK_V2 =====")
    print(
        "  #  Idx  Side   Entry time (UTC)            Entry        SL          TP        Exit        R      ATR     KQ"
    )
    print("-" * 93)

    for idx, t in enumerate(trades, start=1):
        s = t.signal
        entry_time = t.signal_index_time_utc if hasattr(t, "signal_index_time_utc") else None
        # nhưng thực tế ta dùng close_time của nến entry
        entry_dt = None
        if hasattr(s, "index"):
            # sẽ set bên dưới với candles trong print_trade_detail, ở đây dùng exit_time - (giả)
            entry_dt = None

        # để tránh phức tạp, ta dùng exit_time - (time delta) cho display
        # nhưng do test.py đã hiển thị chi tiết riêng, ở đây chỉ cần isoformat của nến entry
        # sẽ được override trong test.py nếu cần.

        entry_dt_str = ""  # sẽ fill ở test.py khi in chi tiết
        # ở bảng list anh đã thấy ok, nên ở đây ta chỉ cần dùng exit_time - shift RẤT gần.
        # Để đơn giản: dùng exit_time - (exit_idx - entry_idx)*5m
        # (chủ yếu cho đẹp, không quá quan trọng logic)
        try:
            bars_diff = t.exit_index - s.index
            approx_entry_dt = t.exit_time - timedelta(minutes=5 * bars_diff)
            approx_entry_dt = approx_entry_dt.astimezone(TZ_UTC)
            entry_dt_str = approx_entry_dt.isoformat()
        except Exception:
            entry_dt_str = t.exit_time.astimezone(TZ_UTC).isoformat()

        kq = "WIN " if t.is_win else "LOSS"

        print(
            f"{idx:3d} {s.index:4d} {s.side:5}  {entry_dt_str:>22}  "
            f"{fmt_price(s.entry_price):>10}   {fmt_price(s.sl):>10}   {fmt_price(s.tp):>10}   "
            f"{fmt_price(t.exit_price):>10}  {fmt_r(t.result_r):>5}   {fmt_atr(s.atr):>6}  {kq}"
        )

    print("===== HẾT DANH SÁCH LỆNH =====")


def print_summary(trades: List[TradeResult]) -> None:
    total = len(trades)
    wins = sum(1 for t in trades if t.result_r > 0)
    losses = sum(1 for t in trades if t.result_r < 0)

    avg_win = sum(t.result_r for t in trades if t.result_r > 0) / wins if wins > 0 else 0.0
    avg_loss = sum(t.result_r for t in trades if t.result_r < 0) / losses if losses > 0 else 0.0
    winrate = (wins / total * 100) if total > 0 else 0.0

    print("===== TỔNG KẾT EMA_PULLBACK_V2 =====")
    print(f"  Tổng tín hiệu entry          : {total}")
    print(f"  Tổng lệnh đã mô phỏng        : {total}")
    print(f"    - Thắng: {wins}")
    print(f"    - Thua : {losses}")
    print(f"  Winrate: {winrate:.2f}%")
    print(f"  R TB lệnh thắng: {avg_win:.2f}")
    print(f"  R TB lệnh thua : {avg_loss:.2f}")
    print("====================================")


# ============================================================
#  IN CHI TIẾT 1 LỆNH
# ============================================================

def print_trade_detail(
    trade: TradeResult,
    candles: List[Kline],
    ema_fast_list: List[Optional[float]],
    ema_slow_list: List[Optional[float]],
    atr_list: List[Optional[float]],
    context_bars: int = 5,
) -> None:
    s = trade.signal
    idx = s.index
    c_entry = candles[idx]

    entry_time = c_entry.close_time.astimezone(TZ_UTC)
    exit_time = trade.exit_time.astimezone(TZ_UTC)

    print("\n===== CHI TIẾT LỆNH =====")
    print(f"Index nến      : {idx}")
    print(f"Side           : {s.side}")
    print(f"Entry time UTC : {entry_time.isoformat()}")
    print(f"Exit  time UTC : {exit_time.isoformat()}")
    print(f"Entry price    : {fmt_price(s.entry_price)}")
    print(f"SL             : {fmt_price(s.sl)}")
    print(f"TP             : {fmt_price(s.tp)}")
    print(f"Exit price     : {fmt_price(trade.exit_price)}")
    print(f"Kết quả        : {'WIN' if trade.is_win else 'LOSS'}")
    print(f"R              : {fmt_r(trade.result_r)}")
    print(f"EMA_FAST       : {fmt_price(ema_fast_list[idx])}")
    print(f"EMA_SLOW       : {fmt_price(ema_slow_list[idx])}")
    print(f"ATR            : {fmt_atr(atr_list[idx])}")

    print("----- Context candles (UTC, O/H/L/C) -----")
    start = max(0, idx - context_bars)
    end = min(len(candles) - 1, idx + context_bars)

    for i in range(start, end + 1):
        c = candles[i]
        mark = "<- ENTRY" if i == idx else ""
        t_utc = c.close_time.astimezone(TZ_UTC).isoformat()
        print(
            f"{i:4d}  {t_utc}  "
            f"O={fmt_price(c.open)} H={fmt_price(c.high)} "
            f"L={fmt_price(c.low)} C={fmt_price(c.close)}  {mark}"
        )

    print("===== HẾT CHI TIẾT LỆNH =====\n")
