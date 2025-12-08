# test_compare_optimizer_v4_pro.py
"""
So sánh hiệu quả EMA_PULLBACK_V4_PRO:
- Mode 1: Dùng params default (không optimizer)
- Mode 2: Chạy Auto Optimizer rồi dùng bộ params tốt nhất

In bảng:
Symbol, Trades_base, WR_base, ExpR_base, Trades_opt, WR_opt, ExpR_opt, ΔExpR
"""

from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import List, Any, Dict

from api.market_data_futures import get_futures_klines
from logic.strategies.backtest_ema_pullback_v4_pro import (
    EmaPullbackParams,
    TradeResult,
    backtest_ema_pullback_v4_pro,
)
from logic.optimizer_v4_pro import optimize_v4_pro_for_symbol


# ==============================
# CONFIG
# ==============================
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
DAYS = 20
LIMIT_PER_CALL = 1000  # Binance max 1500/1000 tuỳ loại, 1000 cho an toàn

# Default params V4 Pro (không optimizer)
DEFAULT_PARAMS = EmaPullbackParams(
    ema_fast=21,
    ema_slow=200,
    atr_period=14,
    r_multiple=2.0,
    min_trend_strength=0.0,
    max_pullback_ratio=0.5,
)


# ==============================
# Helpers
# ==============================
def _interval_to_minutes(interval: str) -> int:
    """Chuyển '5m', '15m'... -> số phút. Hiện tại chủ yếu dùng 5m."""
    unit = interval[-1]
    val = int(interval[:-1])
    if unit == "m":
        return val
    elif unit == "h":
        return val * 60
    elif unit == "d":
        return val * 60 * 24
    else:
        raise ValueError(f"Unsupported interval: {interval}")


def fetch_recent_futures_klines_by_days(
    symbol: str,
    interval: str,
    days: int,
    limit_per_call: int = LIMIT_PER_CALL,
):
    """
    Lấy nhiều ngày dữ liệu futures kline bằng cách gọi get_futures_klines nhiều lần.
    Giả định get_futures_klines trả về list các object có:
      - open_time: datetime (UTC)
      - close_time: datetime
      - open, high, low, close: float
    """
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    all_klines: List[Any] = []
    current_start = start
    step_minutes = _interval_to_minutes(interval)

    print(
        f"[INFO] Fetching klines (multi-days) {symbol} {interval}, "
        f"from {start.isoformat()} to {end.isoformat()}"
    )

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

        # Lấy open_time của cây nến cuối, tăng thêm 1 interval để tránh trùng
        last_open = batch[-1].open_time
        if last_open.tzinfo is None:
            last_open = last_open.replace(tzinfo=timezone.utc)

        current_start = last_open + timedelta(minutes=step_minutes)
        if current_start >= end:
            break

        # Nếu số nến đã đủ về mặt lý thuyết thì thôi (optional)
        # expected = days * 24 * 60 // step_minutes
        # if len(all_klines) >= expected:
        #     break

    print(f"[INFO] {symbol}: tổng số nến lấy được: {len(all_klines)}")
    return all_klines


def calc_stats_from_trades(trades: List[TradeResult]) -> Dict[str, float]:
    n = len(trades)
    if n == 0:
        return {
            "trades": 0,
            "wins": 0,
            "loss": 0,
            "be": 0,
            "wr": 0.0,
            "exp_r": -999.0,
        }

    wins = sum(1 for t in trades if t.result_r > 0)
    loss = sum(1 for t in trades if t.result_r < 0)
    be = n - wins - loss

    wr = wins / n * 100.0
    total_r = sum(t.result_r for t in trades)
    exp_r = total_r / n

    return {
        "trades": n,
        "wins": wins,
        "loss": loss,
        "be": be,
        "wr": wr,
        "exp_r": exp_r,
    }


# ==============================
# MAIN TEST
# ==============================
def main():
    rows = []

    for idx, sym in enumerate(SYMBOLS, start=1):
        print(f"\n================ {idx}/{len(SYMBOLS)} - {sym} ================")

        try:
            klines = fetch_recent_futures_klines_by_days(sym, INTERVAL, DAYS)
            if len(klines) < 100:
                print(f"[WARN] {sym}: Dữ liệu quá ít, bỏ qua.")
                continue

            # --------- 1. Backtest với params default (không optimizer) ---------
            print(f"[BASE] Running backtest V4 Pro (NO optimizer) for {sym}...")
            trades_base, *_ = backtest_ema_pullback_v4_pro(
                klines=klines,
                params=DEFAULT_PARAMS,
                symbol=sym,
                interval=INTERVAL,
            )
            stats_base = calc_stats_from_trades(trades_base)
            print(
                f"[BASE] {sym}: trades={stats_base['trades']}, "
                f"WR={stats_base['wr']:.2f}%, ExpR={stats_base['exp_r']:.3f}"
            )

            # --------- 2. Optimizer ON: tìm best params ---------
            print(f"[OPT] Running optimizer V4 Pro for {sym}...")
            opt_result = optimize_v4_pro_for_symbol(
                klines=klines,
                symbol=sym,
                interval=INTERVAL,
                base_params=DEFAULT_PARAMS,
                min_trades=200,
            )

            stats_opt = {
                "trades": opt_result.trades,
                "wins": opt_result.wins,
                "loss": opt_result.loss,
                "be": opt_result.be,
                "wr": opt_result.winrate,
                "exp_r": opt_result.exp_r,
            }

            print(
                f"[OPT] {sym}: trades={stats_opt['trades']}, "
                f"WR={stats_opt['wr']:.2f}%, ExpR={stats_opt['exp_r']:.3f}"
            )

            rows.append(
                {
                    "symbol": sym,
                    "base_trades": stats_base["trades"],
                    "base_wr": stats_base["wr"],
                    "base_expr": stats_base["exp_r"],
                    "opt_trades": stats_opt["trades"],
                    "opt_wr": stats_opt["wr"],
                    "opt_expr": stats_opt["exp_r"],
                    "delta_expr": stats_opt["exp_r"] - stats_base["exp_r"],
                }
            )

        except Exception as e:
            print(f"[ERROR] Lỗi khi xử lý {sym}: {e}")

    # =========================
    # IN BẢNG SO SÁNH
    # =========================
    print("\n================================================")
    print("        SO SÁNH V4 PRO: BASE vs OPTIMIZER       ")
    print("================================================")
    header = (
        "Symbol   "
        "BaseTrd  BaseWR%  BaseExpR   "
        "OptTrd   OptWR%   OptExpR   ΔExpR"
    )
    print(header)
    print("-" * len(header))

    for r in rows:
        print(
            f"{r['symbol']:<8} "
            f"{r['base_trades']:>7}  "
            f"{r['base_wr']:>7.2f}  "
            f"{r['base_expr']:>8.3f}   "
            f"{r['opt_trades']:>7}  "
            f"{r['opt_wr']:>7.2f}  "
            f"{r['opt_expr']:>8.3f}  "
            f"{r['delta_expr']:>6.3f}"
        )


if __name__ == "__main__":
    main()
