from datetime import datetime, timedelta, timezone

from api.market_data_futures import get_futures_klines
from logic.backtest_ema_pullback_v3 import (
    EmaPullbackV3Params,
    backtest_ema_pullback_v3,
    print_trades_v3,
    print_summary_v3,
)

def main():
    symbol = "BTCUSDT"
    interval = "5m"
    days = 5

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    klines = get_futures_klines(symbol, interval, start_time=start, end_time=end, limit=1500)

    params = EmaPullbackV3Params(
        ema_fast_len=21,
        ema_slow_len=200,
        atr_period=14,
        atr_mult_sl=1.0,
        r_tp=2.0,
        # anh có thể tinh chỉnh thêm các filter dưới:
        # min_atr_pct=0.0005,
        # max_atr_pct=0.02,
        # min_pullback_atr=0.3,
        # max_pullback_atr=2.0,
    )

    trades, candles, ema_f, ema_s, atr = backtest_ema_pullback_v3(
        klines, params, symbol, interval
    )

    print_trades_v3(trades, candles, ema_f, ema_s, atr, params, symbol, interval)
    print_summary_v3(trades)


if __name__ == "__main__":
    main()
