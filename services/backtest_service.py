# logic/services/backtest_service.py

from typing import Dict, Any, List
from logic.api_schemas import BacktestRequest
from logic.strategies.ema_pullback_v4_pro import (
    backtest_ema_pullback_v4_pro,
    build_params_from_user_options,
)
from api.market_data_futures import get_futures_klines
from logic.models import TradeResult, SimpleKline  # giả sử vậy

def run_backtest(req: BacktestRequest) -> Dict[str, Any]:
    # 1. Lấy data
    klines_raw = get_futures_klines(
        symbol=req.symbol,
        interval=req.interval,
        # start/end tính theo days giống script multi-coin
    )

    # 2. Build params từ lựa chọn user
    params = build_params_from_user_options(req.symbol, req.options)

    # 3. Chạy backtest
    trades, candles, ema_fast, ema_slow, atr_list = backtest_ema_pullback_v4_pro(
        klines_raw,
        params,
        symbol=req.symbol,
        interval=req.interval,
    )

    # 4. Tổng hợp result cho UI
    wins = sum(1 for t in trades if t.result_r > 0)
    loss = sum(1 for t in trades if t.result_r < 0)
    be   = len(trades) - wins - loss
    wr   = 0.0 if not trades else wins / len(trades) * 100

    return {
        "symbol": req.symbol,
        "interval": req.interval,
        "strategy": req.strategy,
        "params": params.__dict__,
        "options": req.options.__dict__,
        "stats": {
            "trades": len(trades),
            "wins": wins,
            "loss": loss,
            "be": be,
            "winrate": wr,
        },
        # UI có thể request thêm detail trades/candles nếu cần
        "trades": [t.__dict__ for t in trades],
    }
