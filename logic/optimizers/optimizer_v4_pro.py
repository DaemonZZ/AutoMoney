# logic/optimizers/optimizer_v4_pro.py
"""
Dummy optimizer cho V4 Pro.
Sau này muốn tối ưu thật (grid search / genetic / bayes) thì code tiếp vào đây.
"""

from __future__ import annotations
from typing import Optional
from dataclasses import dataclass

from logic.strategies.v4_pro_params import EmaPullbackParams


# ======================================================
# Tạm thời trả về preset hợp lý (placeholder optimizer)
# ======================================================
def optimize_v4_pro_for_symbol(symbol: str) -> EmaPullbackParams:
    """
    Optimizer dummy:
      - Sau này sẽ chạy grid-search, genetic algorithm hoặc bayes search
      - Hiện tại chỉ trả về thông số "ổn định" (preset) cho từng coin

    Mục đích:
      - Tránh ứng dụng báo lỗi khi user chọn use_optimizer = True
      - Cho phép UI hoạt động bình thường
    """

    s = symbol.upper()

    # Có thể custom theo từng coin (preset từ kết quả test anh gửi)
    if s == "BTCUSDT":
        return EmaPullbackParams(
            ema_fast=18,
            ema_slow=200,
            atr_period=10,
            r_multiple=2.2,
            min_trend_strength=0.0,
            max_pullback_ratio=0.5,
        )

    if s == "ETHUSDT":
        return EmaPullbackParams(
            ema_fast=14,
            ema_slow=200,
            atr_period=18,
            r_multiple=2.2,
            min_trend_strength=20.0,
            max_pullback_ratio=0.5,
        )

    if s == "BNBUSDT":
        return EmaPullbackParams(
            ema_fast=14,
            ema_slow=150,
            atr_period=10,
            r_multiple=2.0,
            min_trend_strength=0.0,
            max_pullback_ratio=0.5,
        )

    # Default fallback cho các coin khác
    return EmaPullbackParams(
        ema_fast=21,
        ema_slow=200,
        atr_period=14,
        r_multiple=2.2,
        min_trend_strength=0.0,
        max_pullback_ratio=0.5,
    )
