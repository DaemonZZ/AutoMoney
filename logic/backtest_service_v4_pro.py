"""
Backtest Service cho EMA_PULLBACK_V4_PRO

Mục tiêu:
- Cung cấp API nội bộ, rõ ràng, để UI / app gọi.
- Ẩn bớt chi tiết: fetch data, convert Kline, gọi strategy, tính summary.
- Dễ mở rộng sau này (thêm strategy khác, thêm optimizer, thêm filter mode...).
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from api.market_data_futures import get_futures_klines
from logic.strategies.ema_pullback_v4_pro import (
    backtest_ema_pullback_v4_pro,
    SimpleKline,
    TradeResult,
)
from logic.optimizers.optimizer_v4_pro import optimize_v4_pro_for_symbol
from logic.strategies.v4_pro_params import EmaPullbackParams


# =====================================================
# Định nghĩa struct kết quả để app/UI dùng
# =====================================================

@dataclass
class BacktestSummary:
    symbol: str
    interval: str
    days: int

    n_trades: int
    wins: int
    loss: int
    be: int
    winrate: float
    avg_r_win: float
    avg_r_loss: float
    expectancy_r: float    # kỳ vọng R-multiple / trade


@dataclass
class BacktestResultV4Pro:
    symbol: str
    interval: str
    days: int

    params_used: EmaPullbackParams
    summary: BacktestSummary

    trades: List[TradeResult]
    candles: List[SimpleKline]
    ema_fast: List[float]
    ema_slow: List[float]
    atr_list: List[float]


# =====================================================
# Helper: fetch Kline nhiều ngày
# =====================================================

def fetch_klines_multi_days(
    symbol: str,
    interval: str,
    days: int,
    limit_per_call: int = 1500,
):
    """
    Load dữ liệu futures Kline trong N ngày gần nhất.

    Trả về:
        - raw klines (whatever format get_futures_klines trả – ở V4 Pro em convert sau)
    """
    end: datetime = datetime.now(timezone.utc)
    start: datetime = end - timedelta(days=days)

    print(f"[BacktestService] Fetching {symbol} {interval} for {days} days")
    print(f"    From {start.isoformat()} To {end.isoformat()}")

    data = get_futures_klines(
        symbol=symbol,
        interval=interval,
        start_time=start,
        end_time=end,
        limit=limit_per_call,
    )

    print(f"[BacktestService] Loaded candles: {len(data)}")
    return data


# =====================================================
# Helper: build summary
# =====================================================

def _build_summary(
    symbol: str,
    interval: str,
    days: int,
    trades: List[TradeResult],
) -> BacktestSummary:
    wins = [t for t in trades if t.result_r > 0]
    loss = [t for t in trades if t.result_r < 0]
    be = [t for t in trades if t.result_r == 0]

    n = len(trades)
    winrate = (len(wins) / n * 100.0) if n > 0 else 0.0

    avg_r_win = sum(t.result_r for t in wins) / len(wins) if wins else 0.0
    avg_r_loss = sum(t.result_r for t in loss) / len(loss) if loss else 0.0

    p_win = len(wins) / n if n > 0 else 0.0
    p_loss = len(loss) / n if n > 0 else 0.0
    expectancy_r = p_win * avg_r_win + p_loss * avg_r_loss

    return BacktestSummary(
        symbol=symbol,
        interval=interval,
        days=days,
        n_trades=n,
        wins=len(wins),
        loss=len(loss),
        be=len(be),
        winrate=winrate,
        avg_r_win=avg_r_win,
        avg_r_loss=avg_r_loss,
        expectancy_r=expectancy_r,
    )


# =====================================================
# API NỘI BỘ CHÍNH: chạy V4 Pro cho 1 symbol
# =====================================================

def run_backtest_ema_v4_pro(
    symbol: str,
    interval: str = "5m",
    days: int = 30,
    params: Optional[EmaPullbackParams] = None,
    use_optimizer: bool = False,
) -> BacktestResultV4Pro:
    """
    API nội bộ cho app/UI:

    - symbol, interval, days: define dataset
    - params:
        - None + use_optimizer=False  => dùng default EmaPullbackParams()
        - None + use_optimizer=True   => gọi optimizer_v4_pro_for_symbol(symbol)
        - không None                  => dùng params truyền vào (ignore optimizer)

    Trả về:
        BacktestResultV4Pro:
            - summary: số trade, winrate, expectancy...
            - params_used: param thực tế đã dùng
            - trades, candles, ema_fast, ema_slow, atr_list: cho UI vẽ chart, table,...
    """

    # 1. Fetch data
    klines = fetch_klines_multi_days(symbol, interval, days)

    if not klines:
        raise ValueError(f"Không có dữ liệu Kline cho {symbol}")

    # 2. Decide params_used
    if params is not None:
        params_used = params
        print(f"[BacktestService] Using CUSTOM params for {symbol}")
    elif use_optimizer:
        print(f"[BacktestService] Using OPTIMIZER params for {symbol}")
        params_used = optimize_v4_pro_for_symbol(symbol)
    else:
        print(f"[BacktestService] Using DEFAULT params for {symbol}")
        params_used = EmaPullbackParams()  # default config

    # 3. Run strategy
    trades, candles, ema_fast, ema_slow, atr_list = backtest_ema_pullback_v4_pro(
        klines,
        params_used,
        symbol=symbol,
        interval=interval,
    )

    # 4. Build summary
    summary = _build_summary(symbol, interval, days, trades)

    # 5. Wrap lại cho app
    return BacktestResultV4Pro(
        symbol=symbol,
        interval=interval,
        days=days,
        params_used=params_used,
        summary=summary,
        trades=trades,
        candles=candles,
        ema_fast=ema_fast,
        ema_slow=ema_slow,
        atr_list=atr_list,
    )


# =====================================================
# API NỘI BỘ: multi-symbol (cho screen tổng hợp)
# =====================================================

def run_backtest_ema_v4_pro_multi(
    symbols: List[str],
    interval: str = "5m",
    days: int = 30,
    use_optimizer: bool = False,
    shared_params: Optional[EmaPullbackParams] = None,
) -> List[BacktestResultV4Pro]:
    """
    Chạy V4 Pro cho nhiều symbol.

    Mode:
    - shared_params != None: dùng chung 1 bộ params cho tất cả symbol.
    - shared_params == None + use_optimizer=True:
        => mỗi symbol tự optimize.
    - shared_params == None + use_optimizer=False:
        => mỗi symbol dùng default EmaPullbackParams().
    """

    results: List[BacktestResultV4Pro] = []

    for sym in symbols:
        print(f"\n================ {sym} ================")

        # nếu có shared_params thì luôn dùng; nếu không → theo use_optimizer flag
        if shared_params is not None:
            params = shared_params
            use_opt_flag = False
        else:
            params = None
            use_opt_flag = use_optimizer

        try:
            res = run_backtest_ema_v4_pro(
                symbol=sym,
                interval=interval,
                days=days,
                params=params,
                use_optimizer=use_opt_flag,
            )
            results.append(res)
        except Exception as e:
            print(f"[BacktestService] Lỗi khi backtest {sym}: {e}")

    return results
