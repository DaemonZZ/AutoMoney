# test_app_api.py
"""
Script test cho core/app_api.py

- Chạy backtest cho 1 symbol (BTCUSDT)
- Chạy backtest multi cho 12 symbol
- In kết quả ra console dạng bảng

YÊU CẦU:
- Đã cấu hình BINANCE_API_KEY / BINANCE_API_SECRET trong môi trường
- Đã có các module:
    + core.app_api
    + logic.backtest_service_v4_pro
    + logic/strategies/ema_pullback_v4_pro.py (define EmaPullbackParams)
"""

from __future__ import annotations
import os
from typing import List

from core.app_api import (
    SessionConfig,
    UserCredentials,
    StrategyConfig,
    StrategyOptions,
    StrategyId,
    BacktestRequest,
    run_backtest,
    run_backtest_multi,
    Network,
    Market,
)


# Nếu  muốn set params tay luôn thì import EmaPullbackParams
# (nếu file này đặt ở logic/strategies/ema_pullback_v4_pro.py)
try:
    from logic.strategies.ema_pullback_v4_pro import EmaPullbackParams
except ImportError:
    EmaPullbackParams = None  # để script vẫn chạy nếu anh chưa cần


# ============================================================
# Helper in bảng
# ============================================================

def print_single_backtest(result) -> None:
    s = result.summary

    print()
    print("=" * 60)
    print(f" KẾT QUẢ BACKTEST: {result.symbol} {result.interval} - {result.days} ngày")
    print("=" * 60)
    print(f"Strategy  : {result.strategy_id}")
    print(f"Params    : {result.params_used}")
    print("-" * 60)
    print(f"Trades    : {s.trades}")
    print(f"Wins      : {s.wins}")
    print(f"Loss      : {s.loss}")
    print(f"BE        : {s.be}")
    print(f"Winrate   : {s.winrate:.2f}%")
    print(f"Avg R(win): {s.avg_r_win:.2f}")
    print(f"Avg R(loss): {s.avg_r_loss:.2f}")
    print(f"Expectancy: {s.expectancy_r:.3f} R/trade")
    print("-" * 60)

    # In sample vài lệnh gần nhất
    if result.trades_sample:
        print("Sample trades (gần nhất):")
        print("Idx  Side   Entry time (UTC)           R    Entry     Exit")
        print("-" * 60)
        for t in result.trades_sample:
            print(
                f"{t['index']:4d}  "
                f"{t['side']:<5}  "
                f"{t['entry_time']:<25}  "
                f"{t['result_r']:>4.2f}  "
                f"{t['entry']:>9.4f}  "
                f"{t['exit_price']:>9.4f}"
            )
    print()


def print_multi_backtest(results: List) -> None:
    print()
    print("===============================================")
    print("                 TỔNG KẾT NHIỀU COIN           ")
    print("===============================================")
    print(f"{'Symbol':<10} {'Trades':>7} {'Wins':>7} {'Loss':>7} {'BE':>5} {'WR %':>7} {'ExpR':>7}")
    print("-" * 50)

    for r in results:
        s = r.summary
        print(
            f"{s.symbol:<10}"
            f"{s.trades:7d}"
            f"{s.wins:7d}"
            f"{s.loss:7d}"
            f"{s.be:5d}"
            f"{s.winrate:7.2f}"
            f"{s.expectancy_r:7.3f}"
        )

    print()


# ============================================================
# MAIN
# ============================================================

def main():
    # 1. Tạo session config (API key đọc từ env)
    creds = UserCredentials(
        api_key=os.getenv("BINANCE_API_KEY", ""),
        api_secret=os.getenv("BINANCE_API_SECRET", ""),
    )

    # Ví dụ: Futures Testnet
    session = SessionConfig(
        credentials=creds,
        market=Market.FUTURES,
        network=Network.TESTNET,
        default_symbol="BTCUSDT",
        default_interval="5m",
    )

    # Cấu hình strategy (EMA Pullback V4 Pro)
    # - use_optimizer: dùng auto optimizer theo từng symbol
    # - strict_filters: bật filter chặt hơn
    strat_options = StrategyOptions(
        use_optimizer=False,     # đổi True nếu muốn auto-optimize
        strict_filters=False,    # đổi True nếu muốn phiên bản "thắt" filter
    )

    # Nếu anh muốn set params tay:
    if EmaPullbackParams is not None:
        # ví dụ: chỉ set EMA/ATR/R, để min_trend_strength/max_pullback_ratio dùng default
        custom_params = EmaPullbackParams(
            ema_fast=21,
            ema_slow=200,
            atr_period=14,
            r_multiple=2.0,
        )
    else:
        custom_params = None

    session.strategy_config = StrategyConfig(
        strategy_id=StrategyId.EMA_PULLBACK_V4_PRO,
        params=custom_params,   # hoặc None để cho service quyết định (default / optimizer)
        options=strat_options,
    )

    # 2. BACKTEST 1 SYMBOL (BTCUSDT)
    print("\n========== BACKTEST 1 SYMBOL ==========")
    single_req = BacktestRequest(
        symbol="BTCUSDT",
        interval="5m",
        days=60,        # ví dụ 60 ngày gần nhất
    )

    single_result = run_backtest(session, single_req)
    print_single_backtest(single_result)

    # 3. BACKTEST MULTI SYMBOL (12 COIN)
    print("\n========== BACKTEST NHIỀU SYMBOL ==========")
    symbols_12 = [
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

    multi_req = BacktestRequest(
        symbol=None,        # dùng per-symbol
        interval="5m",
        days=60,
    )

    multi_results = run_backtest_multi(
        session,
        symbols=symbols_12,
        req=multi_req,
        share_params_across_symbols=False,  # True = dùng chung 1 bộ params; False = mỗi coin tự xử lý
    )

    print_multi_backtest(multi_results)


if __name__ == "__main__":
    main()
