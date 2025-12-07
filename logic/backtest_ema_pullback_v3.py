from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, time as dtime
from typing import List, Any, Optional
import math


# =========================================================
# Data structures
# =========================================================

@dataclass
class Candle:
    index: int
    open_time: datetime
    close_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class TradeResult:
    index: int           # index candle entry
    side: str            # "LONG" / "SHORT"
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    sl: float
    tp: float
    exit_price: float
    result_r: float      # +R / -1 / 0
    atr: float


@dataclass
class BacktestParamsV3:
    symbol: str
    interval: str

    ema_fast_len: int = 21
    ema_slow_len: int = 200
    atr_len: int = 14
    risk_reward: float = 2.0

    # filter nhẹ (anh có thể chỉnh sau)
    min_atr_multiplier: float = 0.3  # candle range > 0.3 * ATR
    max_pullback_atr: float = 2.5    # không trade khi pullback > 2.5 ATR

    # session filter NY (default: trade cả ngày)
    use_ny_session_filter: bool = False
    trade_session_ny_start: dtime = dtime(0, 0)
    trade_session_ny_end: dtime = dtime(23, 59, 59)

    # timezone offset NY so với UTC (đã tính daylight/ko daylight kiểu fake, anh chỉnh nếu cần)
    ny_utc_offset_hours: int = -5


# =========================================================
# Utils
# =========================================================

def _get_kline_field(k: Any, *names: str) -> Any:
    """
    Lấy field từ kline với nhiều tên fallback:
    - hỗ trợ cả list/tuple, dict, object, dataclass.
    """
    # list / tuple => dùng index nếu names là 'open_time', 'open', ...
    if isinstance(k, (list, tuple)):
        # Binance futures raw:
        # [0] open_time, [1] open, [2] high, [3] low, [4] close, [5] volume, ...
        name = names[0]
        idx_map = {
            "open_time": 0,
            "openTime": 0,
            "t": 0,
            "open": 1,
            "o": 1,
            "high": 2,
            "h": 2,
            "low": 3,
            "l": 3,
            "close": 4,
            "c": 4,
            "volume": 5,
            "v": 5,
            "close_time": 6,
            "closeTime": 6,
        }
        for n in names:
            if n in idx_map and idx_map[n] < len(k):
                return k[idx_map[n]]
        raise AttributeError(f"Cannot extract {names} from kline list")

    # dict-like
    if isinstance(k, dict):
        for n in names:
            if n in k:
                return k[n]

    # object
    for n in names:
        if hasattr(k, n):
            return getattr(k, n)

    raise AttributeError(f"Cannot find fields {names} in kline object {type(k)}")


def _extract_open_time_dt(k: Any) -> datetime:
    """
    Lấy open_time dạng datetime UTC từ 1 kline:
    - hỗ trợ ms, s, hoặc datetime.
    """
    v = _get_kline_field(k, "open_time", "openTime", "t")

    if isinstance(v, datetime):
        # đảm bảo có tz
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)

    # assume ms or seconds
    v_int = int(v)
    # nếu lớn hơn 10^12 => ms, ngược lại => s
    if v_int > 10**11:
        return datetime.fromtimestamp(v_int / 1000.0, tz=timezone.utc)
    else:
        return datetime.fromtimestamp(v_int, tz=timezone.utc)


def _extract_close_time_dt(k: Any, interval: str) -> datetime:
    """
    Lấy close_time; nếu không có thì open_time + tf.
    """
    try:
        v = _get_kline_field(k, "close_time", "closeTime")
        if isinstance(v, datetime):
            return v if v.tzinfo else v.replace(tzinfo=timezone.utc)

        v_int = int(v)
        if v_int > 10**11:
            return datetime.fromtimestamp(v_int / 1000.0, tz=timezone.utc)
        else:
            return datetime.fromtimestamp(v_int, tz=timezone.utc)
    except Exception:
        ot = _extract_open_time_dt(k)
        return ot + interval_to_timedelta(interval)


def interval_to_timedelta(interval: str) -> timedelta:
    """
    Convert "5m", "15m", "1h" ... -> timedelta.
    Chỉ cần 5m cho case hiện tại nhưng viết chung luôn.
    """
    unit = interval[-1]
    num = int(interval[:-1])

    if unit == "m":
        return timedelta(minutes=num)
    if unit == "h":
        return timedelta(hours=num)
    if unit == "d":
        return timedelta(days=num)
    if unit == "w":
        return timedelta(weeks=num)

    # fallback: assume minutes
    return timedelta(minutes=num)


def klines_to_candles(klines: List[Any], interval: str) -> List[Candle]:
    candles: List[Candle] = []
    tf = interval_to_timedelta(interval)

    for i, k in enumerate(klines):
        ot = _extract_open_time_dt(k)
        try:
            ct = _extract_close_time_dt(k, interval)
        except Exception:
            ct = ot + tf - timedelta(milliseconds=1)

        o = float(_get_kline_field(k, "open", "o"))
        h = float(_get_kline_field(k, "high", "h"))
        l = float(_get_kline_field(k, "low", "l"))
        c = float(_get_kline_field(k, "close", "c"))
        v = float(_get_kline_field(k, "volume", "v"))

        candles.append(
            Candle(
                index=i,
                open_time=ot,
                close_time=ct,
                open=o,
                high=h,
                low=l,
                close=c,
                volume=v,
            )
        )

    return candles


# =========================================================
# Indicators
# =========================================================

def ema_list(values: List[float], length: int) -> List[Optional[float]]:
    if length <= 0 or len(values) == 0:
        return [None] * len(values)

    k = 2 / (length + 1)
    out: List[Optional[float]] = [None] * len(values)

    # SMA init
    if len(values) < length:
        return out

    sma = sum(values[:length]) / length
    out[length - 1] = sma
    prev = sma

    for i in range(length, len(values)):
        val = values[i]
        ema = (val - prev) * k + prev
        out[i] = ema
        prev = ema

    return out


def true_range(c_prev: Candle, c: Candle) -> float:
    return max(
        c.high - c.low,
        abs(c.high - c_prev.close),
        abs(c.low - c_prev.close),
    )


def atr_list(candles: List[Candle], length: int) -> List[Optional[float]]:
    n = len(candles)
    if n == 0 or length <= 0:
        return [None] * n
    if n < length + 1:
        return [None] * n

    trs: List[float] = []
    for i in range(1, n):
        trs.append(true_range(candles[i - 1], candles[i]))

    # ATR kiểu Wilder
    out: List[Optional[float]] = [None] * n
    first_atr = sum(trs[:length]) / length
    out[length] = first_atr
    prev_atr = first_atr

    for i in range(length + 1, n):
        tr = trs[i - 1]
        atr = (prev_atr * (length - 1) + tr) / length
        out[i] = atr
        prev_atr = atr

    return out


# =========================================================
# Session / timezone helpers
# =========================================================

def to_newyork_time(dt_utc: datetime, offset_hours: int) -> datetime:
    """
    Chuyển từ UTC -> "New York giả định" bằng offset cố định.
    (đủ để filter session, không cần chính xác DST).
    """
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    return dt_utc + timedelta(hours=offset_hours)


def is_in_session_ny(
    dt_utc: datetime,
    start: dtime,
    end: dtime,
    offset_hours: int,
) -> bool:
    """
    Kiểm tra dt_utc (UTC) có nằm trong phiên NY (start, end) không.
    """
    ny_dt = to_newyork_time(dt_utc, offset_hours)
    tt = ny_dt.time()
    if start <= end:
        return start <= tt <= end
    # case qua nửa đêm
    return tt >= start or tt <= end


# =========================================================
# Entry logic V3 (pullback + filter nhẹ)
# =========================================================

@dataclass
class EntrySignal:
    index: int
    side: str       # "LONG" / "SHORT"
    ema_fast: float
    ema_slow: float
    atr: float


def detect_entry_signal(
    i: int,
    candles: List[Candle],
    ema_fast_list: List[Optional[float]],
    ema_slow_list: List[Optional[float]],
    atr_list_vals: List[Optional[float]],
    p: BacktestParamsV3,
) -> Optional[EntrySignal]:
    c = candles[i]
    ema_f = ema_fast_list[i]
    ema_s = ema_slow_list[i]
    atr = atr_list_vals[i]

    if ema_f is None or ema_s is None or atr is None:
        return None

    # session filter (nếu bật)
    if p.use_ny_session_filter:
        if not is_in_session_ny(
            c.close_time,
            p.trade_session_ny_start,
            p.trade_session_ny_end,
            p.ny_utc_offset_hours,
        ):
            return None

    # trend theo EMA
    up_trend = ema_f > ema_s
    down_trend = ema_f < ema_s
    if not (up_trend or down_trend):
        return None

    body = abs(c.close - c.open)
    range_c = c.high - c.low
    if atr <= 0:
        return None

    # filter 1: candle không được quá nhỏ so với ATR
    if range_c < p.min_atr_multiplier * atr:
        return None

    # distance từ EMA đến close (tính bằng ATR)
    dist_ema = abs(c.close - ema_f) / atr

    # filter 2: pullback không quá lớn
    if dist_ema > p.max_pullback_atr:
        return None

    # điều kiện LONG
    if up_trend:
        # pullback chạm/vượt qua EMA rồi đóng xanh trên EMA
        touched_ema = (c.low <= ema_f <= c.high) or dist_ema <= 0.2
        bull_body = c.close > c.open
        close_above_ema = c.close > ema_f

        if touched_ema and bull_body and close_above_ema:
            return EntrySignal(index=i, side="LONG", ema_fast=ema_f, ema_slow=ema_s, atr=atr)

    # điều kiện SHORT
    if down_trend:
        touched_ema = (c.low <= ema_f <= c.high) or dist_ema <= 0.2
        bear_body = c.close < c.open
        close_below_ema = c.close < ema_f

        if touched_ema and bear_body and close_below_ema:
            return EntrySignal(index=i, side="SHORT", ema_fast=ema_f, ema_slow=ema_s, atr=atr)

    return None


# =========================================================
# Backtest core
# =========================================================

def simulate_trade(
    sig: EntrySignal,
    candles: List[Candle],
    atr: float,
    rr: float,
) -> Optional[TradeResult]:
    i = sig.index
    c = candles[i]

    if sig.side == "LONG":
        entry = c.close
        sl = min(c.low, entry - 1.0 * atr)
        if sl >= entry:
            return None
        tp = entry + rr * (entry - sl)
    else:  # SHORT
        entry = c.close
        sl = max(c.high, entry + 1.0 * atr)
        if sl <= entry:
            return None
        tp = entry - rr * (sl - entry)

    # chạy từng candle sau entry để xem khớp SL/TP
    for j in range(i + 1, len(candles)):
        cj = candles[j]

        if sig.side == "LONG":
            # ưu tiên SL trước rồi TP (bảo thủ)
            hit_sl = cj.low <= sl
            hit_tp = cj.high >= tp
            if hit_sl and hit_tp:
                # rất hiếm, tạm coi SL trước
                exit_price = sl
                result_r = -1.0
            elif hit_sl:
                exit_price = sl
                result_r = -1.0
            elif hit_tp:
                exit_price = tp
                result_r = rr
            else:
                continue
        else:  # SHORT
            hit_sl = cj.high >= sl
            hit_tp = cj.low <= tp
            if hit_sl and hit_tp:
                exit_price = sl
                result_r = -1.0
            elif hit_sl:
                exit_price = sl
                result_r = -1.0
            elif hit_tp:
                exit_price = tp
                result_r = rr
            else:
                continue

        return TradeResult(
            index=i,
            side=sig.side,
            entry_time=c.close_time,
            exit_time=cj.close_time,
            entry_price=entry,
            sl=sl,
            tp=tp,
            exit_price=exit_price,
            result_r=result_r,
            atr=atr,
        )

    # không chạm SL/TP -> bỏ qua trade (ko đóng lệnh)
    return None


def _fmt_price(p: float) -> str:
    abs_p = abs(p)
    if abs_p >= 1000:
        return f"{p:,.2f}"
    if abs_p >= 1:
        return f"{p:.2f}"
    if abs_p >= 0.01:
        return f"{p:.4f}"
    return f"{p:.6f}"


def print_trades_and_summary_v3(
    trades: List[TradeResult],
    candles: List[Candle],
    ema_fast_list: List[Optional[float]],
    ema_slow_list: List[Optional[float]],
    atr_list_vals: List[Optional[float]],
    params: BacktestParamsV3,
) -> None:
    print(
        f"[INFO] Symbol={params.symbol}, TF={params.interval}, "
        f"EMA_FAST={params.ema_fast_len}, EMA_SLOW={params.ema_slow_len}, "
        f"ATR={params.atr_len}, R={params.risk_reward:.2f}"
    )

    if not trades:
        print("Không có lệnh nào.")
        return

    print("===== DANH SÁCH LỆNH EMA_PULLBACK_V3 =====")
    print(
        "  #  Idx  Side   Entry time (UTC)            Entry        SL          TP        Exit        R      ATR     KQ"
    )
    print("-" * 93)

    for idx, t in enumerate(trades, start=1):
        c = candles[t.index]
        atr = t.atr
        r = t.result_r
        kq = "WIN " if r > 0 else ("LOSS" if r < 0 else "BE  ")

        print(
            f"{idx:3d}  {t.index:4d} {t.side:<5}  {t.entry_time.isoformat():23s}  "
            f"{_fmt_price(t.entry_price):>10}   {_fmt_price(t.sl):>10}   {_fmt_price(t.tp):>10}   "
            f"{_fmt_price(t.exit_price):>10}  {r:5.2f}  {atr:7.2f}  {kq}"
        )

    print("===== HẾT DANH SÁCH LỆNH =====")

    total = len(trades)
    wins = sum(1 for t in trades if t.result_r > 0)
    loss = sum(1 for t in trades if t.result_r < 0)
    be = total - wins - loss
    wr = (wins / total * 100) if total > 0 else 0.0

    avg_r_win = (
        sum(t.result_r for t in trades if t.result_r > 0) / wins if wins > 0 else 0.0
    )
    avg_r_loss = (
        sum(t.result_r for t in trades if t.result_r < 0) / loss if loss > 0 else 0.0
    )

    print("===== TỔNG KẾT EMA_PULLBACK_V3 =====")
    print(f"  Tổng tín hiệu entry          : {total}")
    print(f"  Tổng lệnh đã mô phỏng        : {total}")
    print(f"    - Thắng: {wins}")
    print(f"    - Thua : {loss}")
    print(f"    - Hòa  : {be}")
    print(f"  Winrate: {wr:.2f}%")
    print(f"  R TB lệnh thắng: {avg_r_win:.2f}")
    print(f"  R TB lệnh thua : {avg_r_loss:.2f}")
    print("====================================")


# =========================================================
# Public API
# =========================================================

def backtest_ema_pullback_v3(
    klines: List[Any],
    params: BacktestParamsV3,
) -> tuple[
    List[TradeResult],
    List[Candle],
    List[Optional[float]],
    List[Optional[float]],
    List[Optional[float]],
]:
    """
    Hàm chính V3:
    - Input: klines (list raw hoặc list Kline object), params
    - Output: trades + lists indicator + tự in log
    """
    candles = klines_to_candles(klines, params.interval)

    closes = [c.close for c in candles]
    ema_fast_list = ema_list(closes, params.ema_fast_len)
    ema_slow_list = ema_list(closes, params.ema_slow_len)
    atr_list_vals = atr_list(candles, params.atr_len)

    trades: List[TradeResult] = []
    in_position = False

    start_i = max(params.ema_slow_len, params.atr_len) + 1

    for i in range(start_i, len(candles)):
        if in_position:
            # đơn giản: chỉ trade 1 lệnh tại 1 thời điểm,
            # nên bỏ qua signal mới cho đến khi lệnh hiện tại kết thúc.
            # (Ở đây simulation theo từng signal độc lập, nên bỏ flag cũng được)
            pass

        sig = detect_entry_signal(
            i, candles, ema_fast_list, ema_slow_list, atr_list_vals, params
        )
        if sig is None:
            continue

        tr = simulate_trade(sig, candles, sig.atr, params.risk_reward)
        if tr is None:
            continue

        trades.append(tr)

    # In chi tiết và tổng kết
    print_trades_and_summary_v3(
        trades, candles, ema_fast_list, ema_slow_list, atr_list_vals, params
    )

    return trades, candles, ema_fast_list, ema_slow_list, atr_list_vals
