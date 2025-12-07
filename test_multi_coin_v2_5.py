# test_multi_coin_v2_5.py

from __future__ import annotations

from datetime import datetime, timedelta, timezone, time
from typing import List
import time as time_mod

from binance.exceptions import BinanceAPIException

from api.market_data_futures import get_futures_klines
from logic.backtest_ema_pullback_v2_5 import (
    backtest_ema_pullback_v2_5,
    EmaPullbackParamsV2_5,
    TradeResult,
)

# ==========================
# CẤU HÌNH
# ==========================

INTERVAL = "5m"
DAYS = 20

TOP_COINS = [
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
    "ZECUSDT"
]


# ==========================
# HÀM GỌI API AN TOÀN (RETRY KHI -1003)
# ==========================

def safe_get_futures_klines(
    symbol: str,
    interval: str,
    limit: int,
    start_time: datetime,
    end_time: datetime,
    max_retries: int = 5,
):
    """
    Gọi get_futures_klines với retry nếu dính rate limit (-1003).
    """
    for attempt in range(max_retries):
        try:
            batch = get_futures_klines(
                symbol=symbol,
                interval=interval,
                start_time=start_time,
                end_time=end_time,
                limit=limit,
            )
            # nghỉ nhẹ để tránh spam
            time_mod.sleep(0.1)
            return batch
        except BinanceAPIException as e:
            if e.code == -1003:
                wait_sec = 10 + attempt * 5
                print(
                    f"[WARN] Rate limit -1003 cho {symbol}, "
                    f"đợi {wait_sec}s rồi retry (attempt {attempt+1}/{max_retries})..."
                )
                time_mod.sleep(wait_sec)
                continue
            else:
                raise
    # Nếu retry hết vẫn fail -> raise lỗi cuối
    raise RuntimeError(f"safe_get_futures_klines: quá số lần retry cho {symbol}")


# ==========================
# FETCH MULTI-DAYS KLINES
# ==========================

def _interval_to_delta(tf: str) -> timedelta:
    """
    Convert interval string (5m, 15m, 1h, 4h, 1d, ...) -> timedelta
    """
    if tf.endswith("m"):
        return timedelta(minutes=int(tf[:-1]))
    if tf.endswith("h"):
        return timedelta(hours=int(tf[:-1]))
    if tf.endswith("d"):
        return timedelta(days=int(tf[:-1]))
    # fallback: mặc định 5 phút
    return timedelta(minutes=5)


def _get_open_time_dt_from_item(item) -> datetime:
    """
    item có thể là:
      - Kline dataclass có field open_time (datetime)
      - raw list/tuple: [open_time_ms, open, high, low, close, ...]
    """
    # case dataclass Kline
    if hasattr(item, "open_time"):
        return item.open_time

    # case raw list/tuple
    open_ms = int(item[0])
    return datetime.fromtimestamp(open_ms / 1000.0, tz=timezone.utc)


def fetch_recent_futures_klines_by_days(
    symbol: str,
    interval: str,
    days: int,
    limit_per_call: int = 1500,
):
    """
    Lấy dữ liệu futures kline nhiều ngày bằng cách chia nhỏ thành các batch.

    Hỗ trợ cả hai kiểu:
      - get_futures_klines trả về list[Kline]
      - get_futures_klines trả về list[list] raw kline
    """
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    all_klines = []
    bar_delta = _interval_to_delta(interval)
    current_start = start

    print(
        f"[INFO] Fetching klines (multi-days) {symbol} {interval}, "
        f"from {start.isoformat()} to {end.isoformat()}"
    )

    while True:
        batch = safe_get_futures_klines(
            symbol=symbol,
            interval=interval,
            limit=limit_per_call,
            start_time=current_start,
            end_time=end,
        )

        if not batch:
            break

        all_klines.extend(batch)

        first_open_dt = _get_open_time_dt_from_item(batch[0])
        last_open_dt = _get_open_time_dt_from_item(batch[-1])

        # chống vòng lặp vô hạn nếu API trả về dữ liệu trùng
        if last_open_dt <= first_open_dt:
            break

        current_start = last_open_dt + bar_delta

        if current_start >= end:
            break

        # Nếu số lượng nến < limit, có thể đã gần tới end, break luôn
        if len(batch) < limit_per_call:
            break

    print(f"[INFO] {symbol}: tổng số nến lấy được: {len(all_klines)}")
    return all_klines


# ==========================
# FORMAT PRINT
# ==========================

def print_summary_table(results):
    print("===============================================")
    print("                 TỔNG KẾT 20 COIN              ")
    print("===============================================")
    print(f"{'Symbol':<10}  {'Trades':>6}  {'Wins':>5}  {'Loss':>5}  {'BE':>4}  {'WR %':>6}")
    print("--------------------------------------------------")
    for row in results:
        sym = row["symbol"]
        trades = row["trades"]
        wins = row["wins"]
        loss = row["loss"]
        be = row["be"]
        wr = row["winrate"]
        print(f"{sym:<10}  {trades:>6}  {wins:>5}  {loss:>5}  {be:>4}  {wr:>6.2f}")


# ==========================
# MAIN
# ==========================

def main():
    params = EmaPullbackParamsV2_5(
        ema_fast_period=21,
        ema_slow_period=200,
        atr_period=14,
        r_multiple=2.0,
        trade_session_ny_start=time(4, 0),
        trade_session_ny_end=time(20, 0),
        enable_filters=True,
    )

    all_results = []

    for idx, sym in enumerate(TOP_COINS, start=1):
        print(f"\n================ {idx}/{len(TOP_COINS)} - {sym} ================")

        # Lấy multi-day klines với helper có retry
        klines = fetch_recent_futures_klines_by_days(sym, INTERVAL, DAYS)

        if not klines:
            print(f"[WARN] Không có dữ liệu cho {sym}, bỏ qua.")
            all_results.append(
                dict(symbol=sym, trades=0, wins=0, loss=0, be=0, winrate=0.0)
            )
            continue

        # Backtest
        trades, *_ = backtest_ema_pullback_v2_5(klines, params)

        # Thống kê
        wins = len([t for t in trades if t.result == "WIN"])
        loss = len([t for t in trades if t.result == "LOSS"])
        be = len([t for t in trades if t.result == "BE"])
        total = len(trades)
        wr = (wins / total * 100.0) if total > 0 else 0.0

        print(
            f"[RESULT] {sym}: trades={total}, wins={wins}, loss={loss}, "
            f"BE={be}, WR={wr:.2f}%"
        )

        all_results.append(
            dict(
                symbol=sym,
                trades=total,
                wins=wins,
                loss=loss,
                be=be,
                winrate=wr,
            )
        )

        # Nghỉ 0.8s giữa các coin cho chắc ăn vụ rate limit
        time_mod.sleep(0.8)

    print()
    print_summary_table(all_results)


if __name__ == "__main__":
    main()
