# logic/backtest_engine.py
from typing import Callable, Sequence, Any
from logic.models import SimpleKline, TradeResult

StrategyRunner = Callable[[Sequence[SimpleKline], Any], list[TradeResult]]

def run_backtest(
    candles: Sequence[SimpleKline],
    strategy_runner: StrategyRunner,
    params: Any,
):
    trades = strategy_runner(candles, params)
    # ở đây có thể build summary chung, expectancy, v.v.
    return trades
