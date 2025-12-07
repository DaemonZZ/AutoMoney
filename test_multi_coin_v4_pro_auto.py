# test_multi_coin_v4_pro_auto.py

from datetime import datetime, timedelta, timezone

from api.market_data_futures import get_futures_klines
from logic.backtest_ema_pullback_v4_pro import backtest_ema_pullback_v4_pro
from logic.optimizer_v4_pro import (
    ParamSearchSpaceV4Pro,
    auto_optimize_params_v4_pro,
)


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

INTERVAL = "5m"
DAYS = 60          # anh có thể đổi 20 / 30 / 90 tuỳ ý
MIN_TRADES = 200   # tránh overfit kiểu 30-40 lệnh


def _interval_to_timedelta(interval: str) -> timedelta:
    unit = interval[-1]
    value = int(interval[:-1])
    if unit == "m":
        return timedelta(minutes=value)
    if unit == "h":
        return timedelta(hours=value)
    if unit == "d":
        return timedelta(days=value)
    if unit == "w":
        return timedelta(weeks=value)
    return timedelta(minutes=value)


def fetch_recent_futures_klines_by_days(
    symbol: str,
    interval: str,
    days: int,
    limit_per_call: int = 1500,
):
    now_utc = datetime.now(timezone.utc)
    end = now_utc
    start = end - timedelta(days=days)
    print(
        f"[INFO] Fetching klines (multi-days) {symbol} {interval}, "
        f"from {start} to {end}"
    )

    all_klines = []
    current_start = start
    interval_delta = _interval_to_timedelta(interval)

    while True:
        batch = get_futures_klines(
            symbol=symbol,
            interval=interval,
            start_time=current_start,
            end_time=end,
            limit=limit_per_call,
        )
        if not batch:
            break

        all_klines.extend(batch)

        if len(batch) < limit_per_call:
            break

        last_open = batch[-1].open_time
        next_start = last_open + interval_delta
        if next_start >= end:
            break
        current_start = next_start

    print(f"[INFO] {symbol}: tổng số nến lấy được: {len(all_klines)}")
    return all_klines


def build_default_search_space() -> ParamSearchSpaceV4Pro:
    """
    Search space nhỏ, an toàn – anh có thể chỉnh lại sau khi xem performance.
    """
    return ParamSearchSpaceV4Pro(
        ema_fast_list=[14, 18, 21],
        ema_slow_list=[150, 200],
        atr_period_list=[10, 14],
        r_multiple_list=[1.8, 2.0, 2.2],
        min_trend_strength_list=[0.0],   # có thể thêm [0.0, 50.0] để test
        max_pullback_ratio_list=[0.5],   # để nguyên 0.5 như V4 Pro
    )


def main():
    print("=== EMA_PULLBACK_V4 Pro - Multi-coin Auto Optimizer ===")

    space = build_default_search_space()
    summary = []

    for idx, sym in enumerate(SYMBOLS, start=1):
        print(f"\n================ {idx}/{len(SYMBOLS)} - {sym} ================")

        klines = fetch_recent_futures_klines_by_days(sym, INTERVAL, DAYS)
        if not klines:
            print(f"[WARN] Không có data cho {sym}, bỏ qua.")
            continue

        opt = auto_optimize_params_v4_pro(
            klines,
            symbol=sym,
            interval=INTERVAL,
            space=space,
            min_trades=MIN_TRADES,
        )
        if opt is None:
            print(f"[WARN] Không tìm được param phù hợp cho {sym}, bỏ qua.")
            continue

        p = opt.best_params
        print(
            f"[OPT-RESULT] {sym}: EF={p.ema_fast}, ES={p.ema_slow}, "
            f"ATR={p.atr_period}, R={p.r_multiple}, "
            f"TS={p.min_trend_strength}, PB={p.max_pullback_ratio}"
        )
        print(
            f"[OPT-RESULT] {sym}: Trades={opt.trades}, Wins={opt.wins}, "
            f"Loss={opt.loss}, BE={opt.be}, WR={opt.winrate:.2f}%, "
            f"ExpR={opt.exp_r:.3f}"
        )

        # Nếu anh muốn, có thể backtest lại 1 lần nữa với best_params,
        # nhưng thực ra opt đã chạy backtest rồi, nên thường không cần.
        summary.append(
            (
                sym,
                opt.trades,
                opt.wins,
                opt.loss,
                opt.be,
                opt.winrate,
                opt.exp_r,
                p,
            )
        )

    # In tổng kết
    print("\n===============================================")
    print("                 TỔNG KẾT 12 COIN             ")
    print("===============================================")
    print(f"{'Symbol':<8} {'Trades':>7} {'Wins':>7} {'Loss':>7} {'BE':>5} {'WR %':>7} {'ExpR':>7}")
    print("-" * 65)
    for sym, n, wins, loss, be, wr, exp_r, p in summary:
        print(
            f"{sym:<8} {n:>7} {wins:>7} {loss:>7} {be:>5} "
            f"{wr:>7.2f} {exp_r:>7.3f}"
        )


if __name__ == "__main__":
    main()
