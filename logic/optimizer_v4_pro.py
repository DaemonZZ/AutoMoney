# logic/optimizer_v4_pro.py

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple, Dict, Any, Optional

from logic.strategies.backtest_ema_pullback_v4_pro import (
    EmaPullbackParams,
    TradeResult,
    backtest_ema_pullback_v4_pro,
)


@dataclass
class OptimizeResultV4Pro:
    symbol: str
    interval: str
    best_params: EmaPullbackParams
    trades: int
    wins: int
    loss: int
    be: int
    winrate: float
    exp_r: float        # Expectancy (R/trade)
    raw_stats: Dict[str, Any]


def _calc_stats_from_trades(trades: List[TradeResult]) -> Dict[str, Any]:
    n = len(trades)
    if n == 0:
        return {
            "trades": 0,
            "wins": 0,
            "loss": 0,
            "be": 0,
            "wr": 0.0,
            "exp_r": -999.0,  # coi như rất tệ
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


def _score_candidate(stats: Dict[str, Any], min_trades: int) -> float:
    """
    Hàm chấm điểm bộ tham số.
    - Ưu tiên ExpR cao
    - Nếu số lệnh quá ít (< min_trades) thì phạt nặng để tránh overfit.
    """
    trades = stats["trades"]
    exp_r = stats["exp_r"]

    if trades < min_trades:
        # phạt nặng nếu ít lệnh
        return exp_r - 1.0

    # có thể thêm penalty khác (VD: quá nhiều lệnh, WR quá thấp,...)
    return exp_r


def optimize_v4_pro_for_symbol(
    klines: List[Any],
    symbol: str,
    interval: str,
    base_params: Optional[EmaPullbackParams] = None,
    min_trades: int = 200,
) -> OptimizeResultV4Pro:
    """
    Chạy grid-search đơn giản trên V4 Pro để tìm bộ tham số tốt nhất
    cho 1 symbol, trong khoảng data (klines) cho trước.

    - klines: list Kline từ Binance (có thuộc tính open_time, close_time, open, high, low, close)
    - symbol, interval: chỉ để log / lưu meta
    - base_params: nếu có, dùng làm “tâm” để tạo grid xung quanh.
    - min_trades: số lệnh tối thiểu để coi là chấp nhận được (tránh overfit).
    """

    # ------- 1. Define search space -------
    if base_params is None:
        # default grid "an toàn" cho nhiều coin
        ema_fast_candidates = [14, 18, 21]
        ema_slow_candidates = [150, 200]
        atr_period_candidates = [10, 14, 18]
        r_multiple_candidates = [1.8, 2.0, 2.2]
        min_trend_strength_candidates = [0.0, 10.0, 20.0]
        max_pullback_ratio_candidates = [0.5]  # tạm chưa dùng sâu
    else:
        # tạo grid xoay quanh base_params (nhỏ hơn, ít tổ hợp hơn)
        def around(x: int | float, candidates: List[int | float]):
            s = sorted(set(candidates + [x]))
            return s

        ema_fast_candidates = around(
            base_params.ema_fast,
            [max(5, base_params.ema_fast - 3), base_params.ema_fast + 3],
        )
        ema_slow_candidates = around(
            base_params.ema_slow,
            [max(50, base_params.ema_slow - 50), base_params.ema_slow + 50],
        )
        atr_period_candidates = around(
            base_params.atr_period,
            [max(5, base_params.atr_period - 4), base_params.atr_period + 4],
        )
        r_multiple_candidates = around(
            base_params.r_multiple,
            [max(1.0, base_params.r_multiple - 0.2), base_params.r_multiple + 0.2],
        )
        min_trend_strength_candidates = around(
            base_params.min_trend_strength,
            [0.0, base_params.min_trend_strength + 10.0],
        )
        max_pullback_ratio_candidates = around(
            base_params.max_pullback_ratio,
            [0.4, 0.6],
        )

    best_score = -1e9
    best_stats: Dict[str, Any] = {
        "trades": 0,
        "wins": 0,
        "loss": 0,
        "be": 0,
        "wr": 0.0,
        "exp_r": -999.0,
    }
    best_params = base_params or EmaPullbackParams()

    total_candidates = (
        len(ema_fast_candidates)
        * len(ema_slow_candidates)
        * len(atr_period_candidates)
        * len(r_multiple_candidates)
        * len(min_trend_strength_candidates)
        * len(max_pullback_ratio_candidates)
    )

    print(f"[OPTIMIZER] {symbol} {interval} - tổng tổ hợp cần test: {total_candidates}")

    idx = 0

    for ef in ema_fast_candidates:
        for es in ema_slow_candidates:
            if ef >= es:
                # EMA nhanh phải < EMA chậm mới có ý nghĩa
                continue

            for atr_p in atr_period_candidates:
                for r in r_multiple_candidates:
                    for ts in min_trend_strength_candidates:
                        for pb in max_pullback_ratio_candidates:
                            idx += 1
                            params = EmaPullbackParams(
                                ema_fast=ef,
                                ema_slow=es,
                                atr_period=atr_p,
                                r_multiple=r,
                                min_trend_strength=ts,
                                max_pullback_ratio=pb,
                            )

                            print(
                                f"[OPTIMIZER] Testing {symbol} "
                                f"({idx}/{total_candidates}): "
                                f"EF={ef}, ES={es}, ATR={atr_p}, R={r:.2f}, TS={ts}, PB={pb}"
                            )

                            trades, *_ = backtest_ema_pullback_v4_pro(
                                klines=klines,
                                params=params,
                                symbol=symbol,
                                interval=interval,
                            )

                            stats = _calc_stats_from_trades(trades)
                            score = _score_candidate(stats, min_trades=min_trades)

                            print(
                                f"[OPTIMIZER] Result -> trades={stats['trades']}, "
                                f"WR={stats['wr']:.2f}%, ExpR={stats['exp_r']:.3f}, score={score:.3f}"
                            )

                            if score > best_score:
                                best_score = score
                                best_stats = stats
                                best_params = params

    print(
        f"[OPTIMIZER] DONE {symbol} {interval}. "
        f"Best -> EF={best_params.ema_fast}, ES={best_params.ema_slow}, "
        f"ATR={best_params.atr_period}, R={best_params.r_multiple:.2f}, "
        f"TS={best_params.min_trend_strength}, PB={best_params.max_pullback_ratio}, "
        f"Trades={best_stats['trades']}, WR={best_stats['wr']:.2f}%, ExpR={best_stats['exp_r']:.3f}"
    )

    return OptimizeResultV4Pro(
        symbol=symbol,
        interval=interval,
        best_params=best_params,
        trades=best_stats["trades"],
        wins=best_stats["wins"],
        loss=best_stats["loss"],
        be=best_stats["be"],
        winrate=best_stats["wr"],
        exp_r=best_stats["exp_r"],
        raw_stats=best_stats,
    )
