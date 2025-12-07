# logic/optimizer_v4_pro.py

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple, Optional

from logic.backtest_ema_pullback_v4_pro import (
    BacktestParamsV4Pro,
    backtest_ema_pullback_v4_pro,
)


@dataclass
class ParamSearchSpaceV4Pro:
    ema_fast_list: List[int]
    ema_slow_list: List[int]
    atr_period_list: List[int]
    r_multiple_list: List[float]
    min_trend_strength_list: List[float]
    max_pullback_ratio_list: List[float]


@dataclass
class OptimizationResultV4Pro:
    best_params: BacktestParamsV4Pro
    trades: int
    wins: int
    loss: int
    be: int
    winrate: float
    exp_r: float


def _evaluate_once(
    klines,
    params: BacktestParamsV4Pro,
    symbol: str,
    interval: str,
):
    trades, *_ = backtest_ema_pullback_v4_pro(
        klines, params, symbol=symbol, interval=interval
    )

    n = len(trades)
    if n == 0:
        return 0, 0, 0, 0, 0.0, 0.0

    wins = sum(1 for t in trades if t.result_r > 0)
    loss = sum(1 for t in trades if t.result_r < 0)
    be = sum(1 for t in trades if t.result_r == 0)
    total_r = sum(t.result_r for t in trades)

    wr = wins / n * 100.0
    exp_r = total_r / n

    return n, wins, loss, be, wr, exp_r


def auto_optimize_params_v4_pro(
    klines,
    symbol: str,
    interval: str,
    space: ParamSearchSpaceV4Pro,
    min_trades: int = 200,
) -> Optional[OptimizationResultV4Pro]:
    """
    Chạy grid-search nhẹ quanh param space, chọn bộ có ExpR tốt nhất
    và số trade >= min_trades. Nếu không có bộ nào đủ trade, sẽ chọn
    bộ có ExpR cao nhất bất kể min_trades (nhưng in cảnh báo).
    """

    best_score = -1e9
    best_result: Optional[OptimizationResultV4Pro] = None

    fallback_best: Optional[OptimizationResultV4Pro] = None
    fallback_best_score = -1e9

    total_comb = (
        len(space.ema_fast_list)
        * len(space.ema_slow_list)
        * len(space.atr_period_list)
        * len(space.r_multiple_list)
        * len(space.min_trend_strength_list)
        * len(space.max_pullback_ratio_list)
    )

    comb_idx = 0
    print(f"[OPT] {symbol}: tổng số combination = {total_comb}")

    for ef in space.ema_fast_list:
        for es in space.ema_slow_list:
            for atr_p in space.atr_period_list:
                for r in space.r_multiple_list:
                    for ts in space.min_trend_strength_list:
                        for pb in space.max_pullback_ratio_list:
                            comb_idx += 1
                            params = BacktestParamsV4Pro(
                                ema_fast=ef,
                                ema_slow=es,
                                atr_period=atr_p,
                                r_multiple=r,
                                min_trend_strength=ts,
                                max_pullback_ratio=pb,
                            )
                            print(
                                f"[OPT] {symbol} ({comb_idx}/{total_comb}) "
                                f"EF={ef}, ES={es}, ATR={atr_p}, R={r}, "
                                f"TS={ts}, PB={pb}"
                            )

                            n, wins, loss, be, wr, exp_r = _evaluate_once(
                                klines, params, symbol, interval
                            )

                            # không có lệnh -> bỏ qua
                            if n == 0:
                                continue

                            # score chính = ExpR, bonus nhẹ theo số trade
                            score = exp_r + 0.0001 * n

                            # Lưu vào fallback (không quan tâm min_trades)
                            if score > fallback_best_score:
                                fallback_best_score = score
                                fallback_best = OptimizationResultV4Pro(
                                    best_params=params,
                                    trades=n,
                                    wins=wins,
                                    loss=loss,
                                    be=be,
                                    winrate=wr,
                                    exp_r=exp_r,
                                )

                            # Áp điều kiện min_trades
                            if n < min_trades:
                                continue

                            if score > best_score:
                                best_score = score
                                best_result = OptimizationResultV4Pro(
                                    best_params=params,
                                    trades=n,
                                    wins=wins,
                                    loss=loss,
                                    be=be,
                                    winrate=wr,
                                    exp_r=exp_r,
                                )

    if best_result is not None:
        return best_result

    # fallback nếu không có combo nào đủ min_trades
    if fallback_best is not None:
        print(
            f"[OPT][WARN] {symbol}: Không có combo nào đủ min_trades={min_trades}. "
            f"Dùng combo tốt nhất theo ExpR nhưng trade ít hơn."
        )
        return fallback_best

    print(f"[OPT][ERROR] {symbol}: Không tối ưu được param (không có lệnh nào).")
    return None
