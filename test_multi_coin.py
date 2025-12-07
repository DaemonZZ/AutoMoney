# test_multi_coin.py

from __future__ import annotations
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import List, Dict, Any

from api.market_data_futures import get_futures_klines
from logic.backtest_ema_pullback_v2 import (
    EmaPullbackParams,
    backtest_ema_pullback_v2,
)
from data.kline import Kline

TZ_UTC = ZoneInfo("UTC")


# ============================================================
#  HỖ TRỢ: CHUYỂN INTERVAL → SỐ PHÚT
# ============================================================

def interval_to_minutes(interval: str) -> int:
    interval = interval.lower()
    if interval.endswith("m"):
        return int(interval[:-1])
    if interval.endswith("h"):
        return int(interval[:-1]) * 60
    if interval.endswith("d"):
        return int(interval[:-1]) * 1440
    return 5


# ============================================================
#  TẢI DỮ LIỆU FUTURES NHIỀU NGÀY
# ============================================================

def fetch_recent_futures_klines_by_days(
    symbol: str,
    interval: str,
    days: int,
    max_per_call: int = 1500,
) -> List[Kline]:
    end_time = datetime.now(TZ_UTC)
    start_time = end_time - timedelta(days=days)

    print(f"[INFO] Fetching {symbol} (multi-days)...")
    print(f"       Time range: {start_time.isoformat()} -> {end_time.isoformat()}")

    all_klines: List[Kline] = []
    cur_start = start_time

    tf_minutes = interval_to_minutes(interval)
    batch_span = timedelta(minutes=tf_minutes * max_per_call)

    while cur_start < end_time:
        batch_end = min(cur_start + batch_span, end_time)

        batch = get_futures_klines(
            symbol=symbol,
            interval=interval,
            start_time=cur_start,
            end_time=batch_end,
            limit=max_per_call,
        )

        if not batch:
            break

        all_klines.extend(batch)

        last_close = batch[-1].close_time
        if last_close <= cur_start:
            break

        cur_start = last_close + timedelta(milliseconds=1)

    print(f"  -> {len(all_klines)} klines")
    return all_klines


# ============================================================
#  MAIN
# ============================================================

def main():
    # 20 coin futures top (anh có thể chỉnh list này)
    symbols = [
        "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
        "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "TRXUSDT", "DOTUSDT",
        "LINKUSDT", "MATICUSDT", "UNIUSDT", "LTCUSDT", "ATOMUSDT",
        "ETCUSDT", "XLMUSDT", "APTUSDT", "ARBUSDT", "OPUSDT", "ZECUSDT"
    ]

    interval = "5m"
    days = 20

    params = EmaPullbackParams(
        ema_fast_period=21,
        ema_slow_period=200,
        atr_period=14,
        atr_mult=1.0,
        rr=2.0,
        min_bars_after_cross=50,
        max_hold_bars=12,
        # nếu class có trade session thì dùng luôn:
        trade_session_ny_start=4,
        trade_session_ny_end=20,
    )

    results: List[Dict[str, Any]] = []

    print("===============================================")
    print("          RUN BACKTEST TOP 20 FUTURES          ")
    print("===============================================\n")

    for sym in symbols:
        print(f"\n========== BACKTEST {sym} ==========")

        klines = fetch_recent_futures_klines_by_days(sym, interval, days)

        if not klines:
            print(f"[WARN] Không có dữ liệu cho {sym}, bỏ qua.")
            continue

        trades, candles, ema_f, ema_s, atr = backtest_ema_pullback_v2(
            klines, params, sym, interval
        )

        total = len(trades)
        # Sửa ở đây: dùng result_r thay vì result
        wins = len([t for t in trades if t.result_r > 0])
        losses = len([t for t in trades if t.result_r < 0])
        breakeven = len([t for t in trades if t.result_r == 0])

        winrate = (wins / total * 100) if total > 0 else 0.0

        results.append({
            "symbol": sym,
            "trades": total,
            "wins": wins,
            "losses": losses,
            "breakeven": breakeven,
            "winrate": winrate,
        })

        print(
            f"[RESULT] {sym}: Trades={total}, Wins={wins}, "
            f"Losses={losses}, BE={breakeven}, WR={winrate:.2f}%"
        )

    # ======================= TỔNG KẾT =======================
    print("\n\n===============================================")
    print("                 TỔNG KẾT 20 COIN              ")
    print("===============================================")

    print(f"{'Symbol':<10} {'Trades':>7} {'Wins':>6} {'Loss':>6} {'BE':>4} {'WR %':>7}")
    print("-" * 50)

    for r in results:
        print(
            f"{r['symbol']:<10} "
            f"{r['trades']:>7} "
            f"{r['wins']:>6} "
            f"{r['losses']:>6} "
            f"{r['breakeven']:>4} "
            f"{r['winrate']:>7.2f}"
        )


if __name__ == "__main__":
    main()
