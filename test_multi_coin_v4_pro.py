# test_multi_coin_v4_pro.py
# Multi-coin backtest cho EMA_PULLBACK_V4_PRO
# - Chạy lần lượt nhiều coin
# - Hỗ trợ dịch cửa sổ thời gian (SHIFT_DAYS) để test quá khứ

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List

from api.market_data_futures import get_futures_klines
from logic.models import TradeResult
from logic.strategies.ema_pullback_v4_pro import EmaPullbackParams, backtest_ema_pullback_v4_pro

# ================= CẤU HÌNH BACKTEST =================

INTERVAL = "5m"

# Độ dài window (bao nhiêu ngày dữ liệu)
DAYS = 60

# Dịch lùi bao nhiêu ngày so với hiện tại
# - 0  : 60 ngày gần nhất
# - 60 : 60 ngày kết thúc cách đây 60 ngày (tức dữ liệu 2–4 tháng trước)
SHIFT_DAYS = 0

# Danh sách coin cần test (12 coin top)
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

# Tham số chiến lược V4 Pro – dùng chung cho tất cả coin
DEFAULT_PARAMS = EmaPullbackParams(
    ema_fast=21,
    ema_slow=200,
    atr_period=14,
    r_multiple=2.0,
    # các field khác nếu có, để mặc định bên trong EmaPullbackParams
)


# ================= HÀM HỖ TRỢ LẤY DATA =================


def fetch_futures_klines_window(
    symbol: str,
    interval: str,
    days: int,
    shift_days: int = 0,
):
    """
    Lấy dữ liệu futures trong 1 window dài `days`, cách hiện tại `shift_days`.

    - shift_days = 0:
        window [now - days, now]  (60 ngày gần nhất)
    - shift_days = 60:
        window [now - (days + 60), now - 60] (cách đây 2–4 tháng nếu days=60)
    """
    end = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=shift_days)
    start = end - timedelta(days=days)

    print(
        f"[INFO] Fetching klines (multi-days) {symbol} {interval}, "
        f"from {start.isoformat()} to {end.isoformat()}"
    )

    if interval != "5m":
        raise ValueError("Hàm demo này chỉ support interval=5m.")

    all_klines = []

    interval_ms = 5 * 60 * 1000
    limit_per_call = 1500

    current_start = start

    while True:
        span_ms = limit_per_call * interval_ms
        current_end = current_start + timedelta(milliseconds=span_ms)
        if current_end > end:
            current_end = end

        batch = get_futures_klines(
            symbol=symbol,
            interval=interval,
            start_time=current_start,
            end_time=current_end,
            limit=limit_per_call,
        )

        if not batch:
            break

        all_klines.extend(batch)

        # Nếu batch chưa đầy hoặc đã tới cuối window thì dừng
        if len(batch) < limit_per_call or current_end >= end:
            break

        # Lùi tiếp từ cuối batch
        last_open = batch[-1].open_time  # Kline.open_time = datetime
        current_start = last_open + timedelta(milliseconds=interval_ms)

    print(f"[INFO] {symbol}: tổng số nến lấy được: {len(all_klines)}")
    return all_klines


# ================= HÀM THỐNG KÊ & IN BẢNG =================


@dataclass
class SymbolStats:
    symbol: str
    trades: int
    wins: int
    loss: int
    be: int
    winrate: float


def summarize_trades(symbol: str, trades: List[TradeResult]) -> SymbolStats:
    wins = 0
    loss = 0
    be = 0

    for t in trades:
        r = t.result_r
        if r > 0:
            wins += 1
        elif r < 0:
            loss += 1
        else:
            be += 1

    total = wins + loss + be
    wr = (wins / (wins + loss) * 100.0) if (wins + loss) > 0 else 0.0

    return SymbolStats(
        symbol=symbol,
        trades=total,
        wins=wins,
        loss=loss,
        be=be,
        winrate=wr,
    )


def print_summary_table(stats_list: List[SymbolStats]):
    print("\n===============================================")
    print("                 TỔNG KẾT 12 COIN              ")
    print("===============================================")
    print(f"{'Symbol':<10}  {'Trades':>7}  {'Wins':>7}  {'Loss':>7}  {'BE':>5}  {'WR %':>6}")
    print("--------------------------------------------------")

    for s in stats_list:
        print(
            f"{s.symbol:<10}  "
            f"{s.trades:>7}  "
            f"{s.wins:>7}  "
            f"{s.loss:>7}  "
            f"{s.be:>5}  "
            f"{s.winrate:>6.2f}"
        )


# ================= MAIN =================


def main():
    all_stats: List[SymbolStats] = []

    for idx, sym in enumerate(SYMBOLS, start=1):
        print(f"\n================ {idx}/{len(SYMBOLS)} - {sym} ================")

        try:
            klines = fetch_futures_klines_window(sym, INTERVAL, DAYS, shift_days=SHIFT_DAYS)
        except Exception as e:
            print(f"[ERROR] Lỗi fetch data {sym}: {e}")
            continue

        if len(klines) == 0:
            print(f"[WARN] Không có dữ liệu cho {sym}, bỏ qua.")
            continue

        try:
            trades, *_ = backtest_ema_pullback_v4_pro(klines, DEFAULT_PARAMS)
        except Exception as e:
            print(f"[ERROR] Lỗi khi backtest {sym}: {e}")
            continue

        stats = summarize_trades(sym, trades)
        all_stats.append(stats)

        print(
            f"[RESULT] {sym}: trades={stats.trades}, "
            f"wins={stats.wins}, loss={stats.loss}, BE={stats.be}, "
            f"WR={stats.winrate:.2f}%"
        )

    # In bảng tổng kết chung
    if all_stats:
        print_summary_table(all_stats)
    else:
        print("\n===============================================")
        print("                 TỔNG KẾT 12 COIN              ")
        print("===============================================")
        print("Không có kết quả nào.")


if __name__ == "__main__":
    main()
