# test_multi_coin_v3.py

from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import List, Any
import time

from api.market_data_futures import get_futures_klines
from logic.backtest_ema_pullback_v3 import (
    backtest_ema_pullback_v3,
    BacktestParamsV3,
)


# =============== Config ===============

INTERVAL = "5m"
DAYS = 20

SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "ADAUSDT",
    "DOGEUSDT",
    "AVAXUSDT",
    "TRXUSDT",
    "DOTUSDT",
    "LINKUSDT",
    "ZECUSDT",
]


# =============== Helpers ===============

def _extract_open_time_dt(k: Any) -> datetime:
    """
    Trích datetime open_time từ 1 kline:
    - Nếu là list/tuple kiểu raw Binance => k[0] là ms
    - Nếu là object có .open_time (datetime hoặc ms)
    - Nếu là object có .openTime
    """
    # raw list / tuple: [open_time_ms, open, high, low, close, ...]
    if isinstance(k, (list, tuple)):
        ms = int(k[0])
        return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)

    # object with .open_time
    if hasattr(k, "open_time"):
        v = getattr(k, "open_time")
        if isinstance(v, datetime):
            # đảm bảo có tz
            return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        # nếu là int/float => assume ms
        if isinstance(v, (int, float, str)):
            ms = int(v)
            return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)

    # object with .openTime
    if hasattr(k, "openTime"):
        v = getattr(k, "openTime")
        if isinstance(v, datetime):
            return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        if isinstance(v, (int, float, str)):
            ms = int(v)
            return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)

    raise TypeError(f"Unknown kline type for open_time: {type(k)}")


def fetch_recent_futures_klines_by_days(
    symbol: str,
    interval: str,
    days: int,
    limit_per_call: int = 1000,
) -> List[Any]:
    """
    Lấy nhiều ngày dữ liệu futures klines bằng cách loop nhiều lần.

    Quan trọng:
    - `get_futures_klines` EXPECT start_time/end_time là datetime,
      nên ở đây dùng datetime để gọi.
    """
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=days)

    print(
        f"[INFO] Fetching klines (multi-days) {symbol} {interval}, "
        f"from {start_dt.isoformat()} to {end_dt.isoformat()}"
    )

    all_klines: List[Any] = []
    cur_start_dt = start_dt

    while cur_start_dt < end_dt:
        batch = get_futures_klines(
            symbol=symbol,
            interval=interval,
            start_time=cur_start_dt,  # datetime
            end_time=end_dt,          # datetime
            limit=limit_per_call,
        )

        if not batch:
            break

        all_klines.extend(batch)

        # lấy open_time datetime của kline cuối
        last_dt = _extract_open_time_dt(batch[-1])

        # nếu không tiến thêm được thì break để tránh loop vô hạn
        if last_dt <= cur_start_dt:
            break

        # next start
        cur_start_dt = last_dt + timedelta(milliseconds=1)

        # tránh -1003 Too many requests
        time.sleep(0.25)

    print(f"[INFO] {symbol}: tổng số nến lấy được: {len(all_klines)}")
    return all_klines


def _print_symbol_result(symbol: str, trades) -> tuple[int, int, int, int, float]:
    total = len(trades)
    wins = sum(1 for t in trades if t.result_r > 0)
    loss = sum(1 for t in trades if t.result_r < 0)
    be = total - wins - loss
    wr = (wins / total * 100) if total > 0 else 0.0

    print(
        f"[RESULT] {symbol}: trades={total}, wins={wins}, loss={loss}, BE={be}, WR={wr:.2f}%"
    )
    return total, wins, loss, be, wr


# =============== MAIN ===============

def main():
    summary = []

    for idx, sym in enumerate(SYMBOLS, start=1):
        print(f"\n================ {idx}/{len(SYMBOLS)} - {sym} ================")

        klines = fetch_recent_futures_klines_by_days(sym, INTERVAL, DAYS)

        if not klines:
            print(f"[WARN] Không có dữ liệu cho {sym}")
            continue

        params = BacktestParamsV3(
            symbol=sym,
            interval=INTERVAL,
            ema_fast_len=21,
            ema_slow_len=200,
            atr_len=14,
            risk_reward=2.0,
        )

        try:
            trades, *_ = backtest_ema_pullback_v3(klines, params)
            total, wins, loss, be, wr = _print_symbol_result(sym, trades)
            summary.append((sym, total, wins, loss, be, wr))
        except Exception as e:
            print(f"[ERROR] Lỗi khi backtest {sym}: {e}")

    # ===== Tổng kết =====
    print("\n===============================================")
    print("                 TỔNG KẾT 12 COIN              ")
    print("===============================================")
    if not summary:
        print("Không có kết quả nào.")
        return

    print(f"{'Symbol':<10} {'Trades':>7} {'Wins':>7} {'Loss':>7} {'BE':>5} {'WR %':>7}")
    print("-" * 50)
    for sym, total, wins, loss, be, wr in summary:
        print(
            f"{sym:<10} {total:>7} {wins:>7} {loss:>7} {be:>5} {wr:>7.2f}"
        )


if __name__ == "__main__":
    main()
