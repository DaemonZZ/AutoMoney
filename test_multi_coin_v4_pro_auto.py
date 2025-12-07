"""
Test skeleton cho EMA_PULLBACK_V4_PRO
- Load data
- Chạy backtest
- In kết quả
- Optional: chạy optimizer trước khi backtest
"""

from datetime import datetime, timedelta, timezone
from typing import List

from api.market_data_futures import get_futures_klines
from logic.strategies.v4_pro_params import EmaPullbackParams
from logic.strategies.backtest_ema_pullback_v4_pro import backtest_ema_pullback_v4_pro
from logic.optimizers.optimizer_v4_pro import optimize_v4_pro_for_symbol


# ==========================================
# CONFIG
# ==========================================
SYMBOL = "BTCUSDT"
INTERVAL = "5m"
DAYS = 20
USE_OPTIMIZER = False     # bật/tắt tùy ý


# ==========================================
# TẢI DATA
# ==========================================
def fetch_klines_multi_days(symbol: str, interval: str, days: int):
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    print(f"[INFO] Fetching klines: {symbol}, {interval}, {days} days")
    print(f"       From {start.isoformat()} To {end.isoformat()}")

    data = get_futures_klines(
        symbol=symbol,
        interval=interval,
        start_time=start,
        end_time=end,
        limit=1500
    )

    print(f"[INFO] Total candles loaded: {len(data)}")
    return data


# ==========================================
# PRINT TRADE SUMMARY
# ==========================================
def summarize_trades(trades):
    wins = [t for t in trades if t.result_r > 0]
    loss = [t for t in trades if t.result_r < 0]
    be = [t for t in trades if t.result_r == 0]

    total = len(trades)
    wr = (len(wins) / total * 100) if total > 0 else 0

    print("\n============== SUMMARY ==============")
    print(f"Total trades   : {total}")
    print(f"  Wins         : {len(wins)}")
    print(f"  Loss         : {len(loss)}")
    print(f"  BE (0R)      : {len(be)}")
    print(f"Winrate        : {wr:.2f}%")
    print("====================================\n")


# ==========================================
# MAIN RUN
# ==========================================
def main():
    print("\n=========== EMA_PULLBACK_V4_PRO TEST ===========")

    # Step 1: load data
    klines = fetch_klines_multi_days(SYMBOL, INTERVAL, DAYS)

    # Step 2: load params (optimize hoặc default)
    if USE_OPTIMIZER:
        print(f"[INFO] Optimizing parameters for: {SYMBOL}")
        params = optimize_v4_pro_for_symbol(SYMBOL)
    else:
        params = EmaPullbackParams()

    print("\n=== PARAMETERS USED ===")
    print(params)

    # Step 3: run backtest
    print("\n[INFO] Running backtest...")
    trades, candles, ema_fast, ema_slow, atr = backtest_ema_pullback_v4_pro(
        klines,
        params,
        symbol=SYMBOL,
        interval=INTERVAL,
    )

    # Step 4: summary
    summarize_trades(trades)

    # Step 5: optional print first few trades
    print("=== SAMPLE TRADES ===")
    for t in trades[:5]:
        print(t)

    print("\n[TEST COMPLETED]")


if __name__ == "__main__":
    main()
