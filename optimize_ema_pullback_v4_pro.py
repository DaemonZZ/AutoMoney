# optimize_ema_pullback_v4_pro.py
"""
Auto-optimizer cho EMA_PULLBACK_V4 Pro:
- Lấy data futures multi-day cho từng symbol
- Chạy grid search trên tập tham số (EMA / ATR / R / trend_strength)
- Tính WR, Expectancy (R/trade)
- In ra best params cho từng coin
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any
from datetime import datetime, timedelta, timezone

from api.market_data_futures import get_futures_klines
from logic.backtest_ema_pullback_v4_pro import (
    BacktestParamsV4Pro,
    backtest_ema_pullback_v4_pro,
)

# ================== CẤU HÌNH CHUNG ==================

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
DAYS = 20  # số ngày history để optimize

# Grid tham số
EMA_FAST_LIST = [14, 18, 21]
EMA_SLOW_LIST = [150, 200]
ATR_PERIOD_LIST = [10, 14, 18]
R_MULTIPLES = [1.8, 2.0, 2.2]

# filter thêm của V4 Pro
MIN_TREND_STRENGTH_LIST = [0.0, 20.0, 50.0]  # tuỳ anh chỉnh
MAX_PULLBACK_RATIO_LIST = [0.5]              # tạm thời cố định, sau muốn mở rộng thì thêm

# Ngưỡng combo "chấp nhận được"
MIN_TRADES = 250
MIN_WR = 30.0  # %

# ====================================================
# Helper: convert interval string -> timedelta
# ====================================================

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


# ====================================================
# Helper: fetch multi-day futures klines
# ====================================================

def fetch_recent_futures_klines_by_days(
    symbol: str,
    interval: str,
    days: int,
    limit_per_call: int = 1500,
):
    """
    Lấy toàn bộ klines trong N ngày gần nhất cho 1 symbol futures (UM).
    Dùng get_futures_klines(symbol, interval, start_time, end_time, limit)
    với start_time / end_time là datetime UTC (aware).
    """
    now_utc = datetime.now(timezone.utc)
    end = now_utc
    start = end - timedelta(days=days)

    print(
        f"[INFO] Fetching klines (multi-days) {symbol} {interval}, "
        f"from {start.isoformat()} to {end.isoformat()}"
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

        last_open = batch[-1].open_time  # datetime UTC
        next_start = last_open + interval_delta

        if next_start >= end:
            break

        current_start = next_start

    print(f"[INFO] {symbol}: tổng số nến lấy được: {len(all_klines)}")
    return all_klines


# ====================================================
# Eval
# ====================================================

@dataclass
class BacktestStats:
    trades: int
    wins: int
    loss: int
    be: int
    winrate: float
    total_r: float
    expectancy: float  # R/trade


def evaluate_trades(trades) -> BacktestStats:
    n = len(trades)
    wins = sum(1 for t in trades if t.result_r > 0)
    loss = sum(1 for t in trades if t.result_r < 0)
    be = sum(1 for t in trades if t.result_r == 0)
    total_r = sum(t.result_r for t in trades)
    winrate = (wins / n * 100.0) if n > 0 else 0.0
    expectancy = (total_r / n) if n > 0 else 0.0

    return BacktestStats(
        trades=n,
        wins=wins,
        loss=loss,
        be=be,
        winrate=winrate,
        total_r=total_r,
        expectancy=expectancy,
    )


# ====================================================
# Tạo params V4 Pro
# ====================================================

def make_params(
    ema_fast: int,
    ema_slow: int,
    atr_period: int,
    r_multiple: float,
    min_trend_strength: float,
    max_pullback_ratio: float,
) -> BacktestParamsV4Pro:
    return BacktestParamsV4Pro(
        ema_fast=ema_fast,
        ema_slow=ema_slow,
        atr_period=atr_period,
        r_multiple=r_multiple,
        min_trend_strength=min_trend_strength,
        max_pullback_ratio=max_pullback_ratio,
    )


# ====================================================
# Optimize cho 1 symbol
# ====================================================

def optimize_symbol(symbol: str, klines) -> Dict[str, Any]:
    print(f"\n========== OPTIMIZE {symbol} ==========")

    best_any: Dict[str, Any] | None = None       # best không ràng buộc
    best_filtered: Dict[str, Any] | None = None  # best có ràng buộc

    total_combos = (
        len(EMA_FAST_LIST)
        * len(EMA_SLOW_LIST)
        * len(ATR_PERIOD_LIST)
        * len(R_MULTIPLES)
        * len(MIN_TREND_STRENGTH_LIST)
        * len(MAX_PULLBACK_RATIO_LIST)
    )
    combo_idx = 0

    for ema_fast in EMA_FAST_LIST:
        for ema_slow in EMA_SLOW_LIST:
            # tránh ema_slow quá gần ema_fast
            if ema_slow <= ema_fast + 20:
                continue

            for atr_period in ATR_PERIOD_LIST:
                for r_mult in R_MULTIPLES:
                    for min_ts in MIN_TREND_STRENGTH_LIST:
                        for max_pb in MAX_PULLBACK_RATIO_LIST:

                            combo_idx += 1
                            print(
                                f"[{symbol}] Combo {combo_idx}/{total_combos}: "
                                f"EF={ema_fast}, ES={ema_slow}, ATR={atr_period}, "
                                f"R={r_mult:.2f}, TS>={min_ts}, PB<={max_pb}"
                            )

                            params = make_params(
                                ema_fast=ema_fast,
                                ema_slow=ema_slow,
                                atr_period=atr_period,
                                r_multiple=r_mult,
                                min_trend_strength=min_ts,
                                max_pullback_ratio=max_pb,
                            )

                            try:
                                trades, *_ = backtest_ema_pullback_v4_pro(
                                    klines, params, symbol=symbol, interval=INTERVAL
                                )
                            except Exception as e:
                                print(f"[WARN] Lỗi backtest combo này: {e}")
                                continue

                            stats = evaluate_trades(trades)
                            print(
                                f"    -> trades={stats.trades}, WR={stats.winrate:.2f}%, "
                                f"Exp={stats.expectancy:.3f}R, total_R={stats.total_r:.1f}"
                            )

                            combo_info = {
                                "ema_fast": ema_fast,
                                "ema_slow": ema_slow,
                                "atr_period": atr_period,
                                "r_mult": r_mult,
                                "min_ts": min_ts,
                                "max_pb": max_pb,
                                "stats": stats,
                            }

                            # best_any
                            if (best_any is None) or (
                                stats.expectancy > best_any["stats"].expectancy
                            ):
                                best_any = combo_info

                            # best_filtered (có điều kiện)
                            if (
                                stats.trades >= MIN_TRADES
                                and stats.winrate >= MIN_WR
                            ):
                                if (best_filtered is None) or (
                                    stats.expectancy
                                    > best_filtered["stats"].expectancy
                                ):
                                    best_filtered = combo_info

    print(f"\n----- KẾT QUẢ {symbol} -----")

    if best_filtered is not None:
        s = best_filtered["stats"]
        print("[BEST (filtered)] Ưu tiên ExpR, có MIN_TRADES & MIN_WR:")
        print(
            f"  EF={best_filtered['ema_fast']}, "
            f"ES={best_filtered['ema_slow']}, "
            f"ATR={best_filtered['atr_period']}, "
            f"R={best_filtered['r_mult']:.2f}, "
            f"TS>={best_filtered['min_ts']}, PB<={best_filtered['max_pb']}"
        )
        print(
            f"  Trades={s.trades}, Wins={s.wins}, Loss={s.loss}, BE={s.be}, "
            f"WR={s.winrate:.2f}%, Exp={s.expectancy:.3f}R, total_R={s.total_r:.1f}"
        )
    else:
        print("[BEST (filtered)] Không có combo nào đạt MIN_TRADES & MIN_WR.")

    if best_any is not None:
        s = best_any["stats"]
        print("\n[ BEST (ANY) ] Chỉ tối đa hóa expectancy, không lọc:")
        print(
            f"  EF={best_any['ema_fast']}, "
            f"ES={best_any['ema_slow']}, "
            f"ATR={best_any['atr_period']}, "
            f"R={best_any['r_mult']:.2f}, "
            f"TS>={best_any['min_ts']}, PB<={best_any['max_pb']}"
        )
        print(
            f"  Trades={s.trades}, Wins={s.wins}, Loss={s.loss}, BE={s.be}, "
            f"WR={s.winrate:.2f}%, Exp={s.expectancy:.3f}R, total_R={s.total_r:.1f}"
        )
    else:
        print("[BEST (ANY)] Không backtest được combo nào?!")

    return {
        "symbol": symbol,
        "best_filtered": best_filtered,
        "best_any": best_any,
    }


# ====================================================
# MAIN
# ====================================================

def main():
    print("=== EMA_PULLBACK_V4 Pro - Auto Optimizer ===")
    print(f"Symbols: {', '.join(SYMBOLS)}")
    print(f"Interval: {INTERVAL}, Days: {DAYS}")
    print(
        f"Grid:\n"
        f"  EMA_FAST={EMA_FAST_LIST}\n"
        f"  EMA_SLOW={EMA_SLOW_LIST}\n"
        f"  ATR_PERIOD={ATR_PERIOD_LIST}\n"
        f"  R_MULT={R_MULTIPLES}\n"
        f"  MIN_TREND_STRENGTH={MIN_TREND_STRENGTH_LIST}\n"
        f"  MAX_PULLBACK_RATIO={MAX_PULLBACK_RATIO_LIST}"
    )
    print(
        f"\nFilter: MIN_TRADES={MIN_TRADES}, MIN_WR={MIN_WR:.1f}%\n"
    )

    all_results: List[Dict[str, Any]] = []

    for idx, sym in enumerate(SYMBOLS, start=1):
        print(f"\n================ {idx}/{len(SYMBOLS)} - {sym} ================")
        klines = fetch_recent_futures_klines_by_days(sym, INTERVAL, DAYS)
        if not klines:
            print(f"[WARN] Không có data cho {sym}, bỏ qua.")
            continue

        res = optimize_symbol(sym, klines)
        all_results.append(res)

    # Tổng kết nhanh best_filtered
    print("\n\n===============================================")
    print("         TỔNG KẾT BEST (FILTERED)             ")
    print("===============================================")
    print(
        f"{'Symbol':<8} {'EF':>4} {'ES':>4} {'ATR':>4} "
        f"{'R':>4} {'TS':>5} {'PB':>4} {'Trd':>5} {'WR%':>6} {'ExpR':>7}"
    )
    print("-" * 80)

    for res in all_results:
        sym = res["symbol"]
        bf = res["best_filtered"]
        if bf is None:
            print(
                f"{sym:<8} {'-':>4} {'-':>4} {'-':>4} "
                f"{'-':>4} {'-':>5} {'-':>4} {'-':>5} {'-':>6} {'-':>7}"
            )
            continue

        s = bf["stats"]
        print(
            f"{sym:<8} "
            f"{bf['ema_fast']:>4d} "
            f"{bf['ema_slow']:>4d} "
            f"{bf['atr_period']:>4d} "
            f"{bf['r_mult']:>4.1f} "
            f"{bf['min_ts']:>5.1f} "
            f"{bf['max_pb']:>4.2f} "
            f"{s.trades:>5d} "
            f"{s.winrate:>6.2f} "
            f"{s.expectancy:>7.3f}"
        )

    print("\nHoàn tất tối ưu.")


if __name__ == "__main__":
    main()
