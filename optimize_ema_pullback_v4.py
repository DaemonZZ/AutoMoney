# optimize_ema_pullback_v4.py
"""
Auto-optimizer cho EMA_PULLBACK_V4 Pro:
- Lấy data futures multi-day cho từng symbol
- Chạy grid search trên tập tham số (EMA / ATR / R)
- Tính WR, Expectancy (R/trade)
- In ra best params cho từng coin (và top 3 nếu muốn mở rộng)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any
from datetime import datetime, timedelta, timezone

from api.market_data_futures import get_futures_klines  # dùng bản đang chạy OK với multi-coin
from logic.strategies import (
    ema_pullback_v4_pro,
    BacktestParamsV4Pro,  # nếu tên class khác, đổi lại ở đây
)


# ================== CẤU HÌNH CHUNG ==================

# List coin cần optimize
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
DAYS = 20  # số ngày history để optimize (20 ngày ~ 5760 nến 5m)

# Grid tham số (anh có thể chỉnh cho rộng/hẹp hơn)
EMA_FAST_LIST = [14, 18, 21]
EMA_SLOW_LIST = [150, 200]
ATR_LEN_LIST = [10, 14, 18]
R_MULTIPLES = [1.8, 2.0, 2.2]

# Ngưỡng lọc combo "chấp nhận được"
MIN_TRADES = 250
MIN_WR = 30.0  # %

# ====================================================
# Helper: convert interval string -> timedelta
# ====================================================

def _interval_to_timedelta(interval: str) -> timedelta:
    """Chuyển chuỗi interval Binance ('5m','15m','1h','4h','1d',...) sang timedelta."""
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

    # fallback: coi như phút
    return timedelta(minutes=value)


# ====================================================
# Helper: fetch multi-day futures klines (dùng datetime aware, không ms)
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
    với start_time/end_time là datetime UTC.
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

        # Nếu batch chưa đầy limit => hết data
        if len(batch) < limit_per_call:
            break

        # Lấy open_time của cây cuối cùng, cộng thêm 1 interval để tránh overlap
        last_open = batch[-1].open_time  # giả định Kline có field open_time: datetime
        next_start = last_open + interval_delta

        if next_start >= end:
            break

        current_start = next_start

    print(f"[INFO] {symbol}: tổng số nến lấy được: {len(all_klines)}")
    return all_klines


# ====================================================
# Helper: đánh giá 1 bộ tham số
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
# Helper: tạo params V4 Pro
# ====================================================

def make_params(
    ema_fast_len: int,
    ema_slow_len: int,
    atr_len: int,
    r_multiple: float,
) -> BacktestParamsV4Pro:
    """
    Chỉ override những field anh muốn grid search.
    Các field khác dùng default trong EmaPullbackParams V4 Pro.
    Nếu V4 Pro của anh yêu cầu field bắt buộc khác, thêm vào đây.
    """
    return BacktestParamsV4Pro(
        ema_fast_len=ema_fast_len,
        ema_slow_len=ema_slow_len,
        atr_len=atr_len,
        r_multiple=r_multiple,
        # ví dụ nếu V4 Pro có thêm:
        # min_trend_slope=0.05,
        # min_body_factor=0.25,
        # max_wick_ratio=0.6,
        # ...
    )


# ====================================================
# Optimize cho 1 symbol
# ====================================================

def optimize_symbol(symbol: str, klines) -> Dict[str, Any]:
    """
    Chạy grid search trên bộ tham số, trả về best combo cho 1 symbol.
    """
    print(f"\n========== OPTIMIZE {symbol} ==========")

    best_any: Dict[str, Any] | None = None   # best không ràng buộc
    best_filtered: Dict[str, Any] | None = None  # best có ràng buộc (MIN_TRADES, MIN_WR)

    total_combos = (
        len(EMA_FAST_LIST) * len(EMA_SLOW_LIST) *
        len(ATR_LEN_LIST) * len(R_MULTIPLES)
    )
    combo_idx = 0

    for ema_fast in EMA_FAST_LIST:
        for ema_slow in EMA_SLOW_LIST:
            # tránh EMA chồng quá gần
            if ema_slow <= ema_fast + 20:
                continue

            for atr_len in ATR_LEN_LIST:
                for r_mult in R_MULTIPLES:
                    combo_idx += 1
                    print(
                        f"[{symbol}] Combo {combo_idx}/{total_combos}: "
                        f"EMA_FAST={ema_fast}, EMA_SLOW={ema_slow}, "
                        f"ATR={atr_len}, R={r_mult:.2f}"
                    )

                    params = make_params(
                        ema_fast_len=ema_fast,
                        ema_slow_len=ema_slow,
                        atr_len=atr_len,
                        r_multiple=r_mult,
                    )

                    try:
                        trades, *_ = backtest_ema_pullback_v4_pro(klines, params)
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
                        "atr_len": atr_len,
                        "r_mult": r_mult,
                        "stats": stats,
                    }

                    # Cập nhật best_any (không filter)
                    if (best_any is None) or (
                        stats.expectancy > best_any["stats"].expectancy
                    ):
                        best_any = combo_info

                    # Áp điều kiện lọc combo "hợp lý"
                    if (
                        stats.trades >= MIN_TRADES
                        and stats.winrate >= MIN_WR
                    ):
                        if (best_filtered is None) or (
                            stats.expectancy > best_filtered["stats"].expectancy
                        ):
                            best_filtered = combo_info

    print(f"\n----- KẾT QUẢ {symbol} -----")

    if best_filtered is not None:
        s = best_filtered["stats"]
        print("[BEST (filtered)] Ưu tiên ExpR, có MIN_TRADES & MIN_WR:")
        print(
            f"  EMA_FAST={best_filtered['ema_fast']}, "
            f"EMA_SLOW={best_filtered['ema_slow']}, "
            f"ATR={best_filtered['atr_len']}, "
            f"R={best_filtered['r_mult']:.2f}"
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
            f"  EMA_FAST={best_any['ema_fast']}, "
            f"EMA_SLOW={best_any['ema_slow']}, "
            f"ATR={best_any['atr_len']}, "
            f"R={best_any['r_mult']:.2f}"
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
        f"Grid: EMA_FAST={EMA_FAST_LIST}, EMA_SLOW={EMA_SLOW_LIST}, "
        f"ATR_LEN={ATR_LEN_LIST}, R_MULT={R_MULTIPLES}"
    )
    print(
        f"Filter: MIN_TRADES={MIN_TRADES}, MIN_WR={MIN_WR:.1f}%\n"
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

    # Tổng kết nhanh best_filtered cho tất cả
    print("\n\n===============================================")
    print("         TỔNG KẾT BEST (FILTERED)             ")
    print("===============================================")
    print(
        f"{'Symbol':<8} {'Efast':>5} {'Eslow':>5} {'ATR':>4} "
        f"{'R':>4} {'Trd':>5} {'WR%':>6} {'ExpR':>7}"
    )
    print("-" * 60)

    for res in all_results:
        sym = res["symbol"]
        bf = res["best_filtered"]
        if bf is None:
            print(f"{sym:<8} {'-':>5} {'-':>5} {'-':>4} {'-':>4} {'-':>5} {'-':>6} {'-':>7}")
            continue

        s = bf["stats"]
        print(
            f"{sym:<8} "
            f"{bf['ema_fast']:>5d} "
            f"{bf['ema_slow']:>5d} "
            f"{bf['atr_len']:>4d} "
            f"{bf['r_mult']:>4.1f} "
            f"{s.trades:>5d} "
            f"{s.winrate:>6.2f} "
            f"{s.expectancy:>7.3f}"
        )

    print("\nHoàn tất tối ưu.")


if __name__ == "__main__":
    main()
