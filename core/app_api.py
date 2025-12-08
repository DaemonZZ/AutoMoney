"""
core/app_api.py

API nội bộ chính để UI / app gọi.

- Quản lý:
    + môi trường (testnet / real, futures / spot)
    + cấu hình strategy & filter
    + chạy backtest cho 1 hoặc nhiều symbol

- Không đụng tới HTTP, chỉ là Python API.

- Phụ thuộc:
    + core.runtime_config
    + logic.backtest_service_v4_pro (EMA Pullback V4 Pro)
    + logic.strategies.ema_pullback_v4_pro (EmaPullbackParams)
    + (tương lai) trading engine, thống kê realtime, lịch sử lệnh thực tế
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, List, Dict, Any
from datetime import datetime

from core.runtime_config import runtime_config
from logic.backtest_service_v4_pro import (
    run_backtest_ema_v4_pro,
    run_backtest_ema_v4_pro_multi,
    BacktestResultV4Pro,
    BacktestSummary,
)
from logic.strategies.v4_pro_params import EmaPullbackParams


# Nếu cần dùng optimizer trực tiếp cho UI:
# from logic.optimizers.optimizer_v4_pro import optimize_v4_pro_for_symbol


# ============================================================
# MÔI TRƯỜNG & STRATEGY
# ============================================================

class Network(str, Enum):
    TESTNET = "test"
    REAL = "real"


class Market(str, Enum):
    FUTURES = "futures"
    SPOT = "spot"


class StrategyId(str, Enum):
    EMA_PULLBACK_V4_PRO = "ema_pullback_v4_pro"
    # sau này thêm:
    # EMA_BREAKOUT_V1 = "ema_breakout_v1"
    # RSI_MEAN_REVERT_V1 = "rsi_mean_revert_v1"
    # ...


@dataclass
class UserCredentials:
    api_key: str
    api_secret: str


@dataclass
class StrategyOptions:
    """
    Các option mà user có thể bật/tắt:
    - use_optimizer: cho phép optimizer tự chọn tham số theo coin
    - strict_filters: áp dụng filter chặt hơn (tùy implementation bên strategy)
    - extra_flags: chỗ để nhét mấy option khác về sau
    """
    use_optimizer: bool = False
    strict_filters: bool = False
    extra_flags: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategyConfig:
    """
    Cấu hình chung cho 1 strategy trên UI.
    Hiện tại chỉ hỗ trợ EMA Pullback V4 Pro,
    nên params chính là EmaPullbackParams.
    """
    strategy_id: StrategyId
    params: Optional[EmaPullbackParams] = None  # None = dùng default/optimizer
    options: StrategyOptions = field(default_factory=StrategyOptions)


@dataclass
class SessionConfig:
    """
    Struct mô tả "session" hiện tại của user:
    - môi trường (market, net)
    - API key
    - symbol / interval default
    - strategy đang chọn
    """
    credentials: UserCredentials
    market: Market = Market.FUTURES
    network: Network = Network.TESTNET

    default_symbol: str = "BTCUSDT"
    default_interval: str = "5m"

    strategy_config: StrategyConfig = field(
        default_factory=lambda: StrategyConfig(
            strategy_id=StrategyId.EMA_PULLBACK_V4_PRO,
        )
    )


# ============================================================
# DTO CHO BACKTEST UI
# ============================================================

@dataclass
class BacktestRequest:
    symbol: Optional[str] = None
    interval: Optional[str] = None
    days: int = 30


@dataclass
class BacktestSummaryDTO:
    """
    Version "phẳng" (dict-friendly) của BacktestSummary
    để UI dễ serialize, không cần biết dataclass gốc.
    """
    symbol: str
    interval: str
    days: int
    trades: int
    wins: int
    loss: int
    be: int
    winrate: float
    avg_r_win: float
    avg_r_loss: float
    expectancy_r: float

    @classmethod
    def from_summary(cls, s: BacktestSummary) -> "BacktestSummaryDTO":
        return cls(
            symbol=s.symbol,
            interval=s.interval,
            days=s.days,
            trades=s.n_trades,
            wins=s.wins,
            loss=s.loss,
            be=s.be,
            winrate=s.winrate,
            avg_r_win=s.avg_r_win,
            avg_r_loss=s.avg_r_loss,
            expectancy_r=s.expectancy_r,
        )


@dataclass
class BacktestResultDTO:
    """
    Để UI hiển thị:
    - summary: số lệnh, winrate, expectancy...
    - params_used: tham số EMA/ATR/... thực tế đã dùng
    - trades_sample: lấy N lệnh gần nhất / tiêu biểu để show (không bắt buộc full)
    - raw_result_id: nếu sau này anh cache kết quả trong DB/memory,
      có thể trả ID để UI request chi tiết thêm.
    """
    symbol: str
    interval: str
    days: int

    strategy_id: StrategyId
    params_used: Dict[str, Any]

    summary: BacktestSummaryDTO
    trades_count: int
    trades_sample: List[Dict[str, Any]] = field(default_factory=list)

    raw_result: Optional[BacktestResultV4Pro] = None  # tùy anh có trả về hay không


# ============================================================
# DTO CHO LIVE-TRADING / TRẠNG THÁI TOOL (SKELETON)
# ============================================================

class OrderStatus(str, Enum):
    OPEN = "OPEN"
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


@dataclass
class LiveOrderDTO:
    """
    Order / position đang chạy để UI hiển thị.
    (Hiện tại skeleton, chưa nối Binance.)
    """
    order_id: str
    symbol: str
    side: str  # "LONG" / "SHORT" hoặc "BUY" / "SELL"
    qty: float
    entry_price: float
    sl: Optional[float]
    tp: Optional[float]
    status: OrderStatus
    opened_at: datetime
    updated_at: datetime

    strategy_id: StrategyId = StrategyId.EMA_PULLBACK_V4_PRO
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolStatusDTO:
    """
    Trạng thái tổng thể của tool / bot để show trên UI:
    - running_mode: "BACKTEST" / "LIVE" / "IDLE"
    - is_running: bot đang bật hay tắt
    - last_action: string log gần nhất
    - last_error: nếu có lỗi
    """
    running_mode: str  # "BACKTEST", "LIVE", "IDLE"
    is_running: bool
    current_symbol: Optional[str] = None
    current_strategy: Optional[StrategyId] = None
    started_at: Optional[datetime] = None
    last_action: Optional[str] = None
    last_error: Optional[str] = None


@dataclass
class LiveStatsDTO:
    """
    Thống kê winrate thực tế, PnL… (dựa trên lệnh thật).
    Skeleton: chưa nối Binance / DB.
    """
    total_trades: int = 0
    wins: int = 0
    loss: int = 0
    be: int = 0

    winrate: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0

    # có thể thêm: max_drawdown, sharpe, vv.


# ============================================================
# HÀM APPLY MÔI TRƯỜNG → runtime_config
# ============================================================

def apply_session_environment(session: SessionConfig) -> None:
    """
    Ánh xạ SessionConfig.market / network vào runtime_config
    để binance_client dùng đúng mode.

    NOTE:
    - Tùy cấu trúc core.runtime_config mà anh sửa lại cho đúng.
    """
    runtime_config.market = session.market.value     # "futures" / "spot"
    runtime_config.net = session.network.value       # "test" / "real"
    # nếu runtime_config có các flag khác (is_futures, is_testnet, ...)
    # thì cập nhật thêm ở đây.


# ============================================================
# API: BACKTEST CHO 1 SYMBOL
# ============================================================

def run_backtest(
    session: SessionConfig,
    req: BacktestRequest,
) -> BacktestResultDTO:
    """
    UI sẽ gọi hàm này khi user bấm "Backtest".

    - Đọc config môi trường + strategy từ session.
    - Apply vào runtime_config.
    - Gọi xuống backtest_service_v4_pro.
    """

    apply_session_environment(session)

    symbol = req.symbol or session.default_symbol
    interval = req.interval or session.default_interval
    days = req.days

    strat_cfg = session.strategy_config

    if strat_cfg.strategy_id != StrategyId.EMA_PULLBACK_V4_PRO:
        # Hiện tại mới hỗ trợ 1 strategy.
        # Sau này switch-case theo strategy_id tại đây.
        raise ValueError(f"Strategy {strat_cfg.strategy_id} chưa được hỗ trợ.")

    # Decide params & optimizer flag
    params = strat_cfg.params
    use_optimizer = strat_cfg.options.use_optimizer

    # strict_filters, extra_flags: anh xử lý bên trong EmaPullbackParams hoặc strategy
    # Ví dụ: nếu strict_filters=True thì chỉnh số min_trend_strength lớn hơn...
    if params is None:
        params = EmaPullbackParams()
    if strat_cfg.options.strict_filters:
        # tuỳ anh muốn chỉnh thế nào, ví dụ:
        params = EmaPullbackParams(
            ema_fast=params.ema_fast,
            ema_slow=params.ema_slow,
            atr_period=params.atr_period,
            r_multiple=params.r_multiple,
            min_trend_strength=params.min_trend_strength * 1.5,
            max_pullback_ratio=params.max_pullback_ratio * 0.8,
        )

    # Gọi service thật
    core_result: BacktestResultV4Pro = run_backtest_ema_v4_pro(
        symbol=symbol,
        interval=interval,
        days=days,
        params=params,
        use_optimizer=use_optimizer,
    )

    # Build summary DTO
    summary_dto = BacktestSummaryDTO.from_summary(core_result.summary)

    # Sampling 1 phần trades để show UI, tránh trả về list siêu dài
    sample_size = min(50, len(core_result.trades))
    trades_sample = []
    for t in core_result.trades[-sample_size:]:
        trades_sample.append(
            {
                "index": t.index,
                "side": t.side,
                "entry_time": t.entry_time.isoformat(),
                "exit_time": t.exit_time.isoformat(),
                "entry": t.entry,
                "sl": t.sl,
                "tp": t.tp,
                "exit_price": t.exit_price,
                "result_r": t.result_r,
                "atr": t.atr,
            }
        )

    return BacktestResultDTO(
        symbol=symbol,
        interval=interval,
        days=days,
        strategy_id=strat_cfg.strategy_id,
        params_used=asdict(core_result.params_used),
        summary=summary_dto,
        trades_count=len(core_result.trades),
        trades_sample=trades_sample,
        raw_result=core_result,  # nếu UI không cần full, anh có thể None chỗ này
    )


# ============================================================
# API: BACKTEST NHIỀU SYMBOL (TỔNG KẾT BẢNG 12 COIN)
# ============================================================

def run_backtest_multi(
    session: SessionConfig,
    symbols: List[str],
    req: BacktestRequest,
    share_params_across_symbols: bool = False,
) -> List[BacktestResultDTO]:
    """
    Chạy backtest cho nhiều symbol bằng V4 Pro (chiến dịch hiện tại).

    share_params_across_symbols:
        - True  => tất cả dùng chung 1 bộ params (session.strategy_config.params)
        - False => mỗi symbol có thể tự optimize / dùng default
    """
    apply_session_environment(session)

    strat_cfg = session.strategy_config
    if strat_cfg.strategy_id != StrategyId.EMA_PULLBACK_V4_PRO:
        raise ValueError(f"Strategy {strat_cfg.strategy_id} chưa hỗ trợ multi.")

    interval = req.interval or session.default_interval
    days = req.days

    if share_params_across_symbols:
        shared_params = strat_cfg.params or EmaPullbackParams()
    else:
        shared_params = None  # mỗi symbol tự xử lý (default / optimizer)

    res_list = run_backtest_ema_v4_pro_multi(
        symbols=symbols,
        interval=interval,
        days=days,
        use_optimizer=strat_cfg.options.use_optimizer,
        shared_params=shared_params,
    )

    out: List[BacktestResultDTO] = []
    for core_result in res_list:
        s_dto = BacktestSummaryDTO.from_summary(core_result.summary)
        out.append(
            BacktestResultDTO(
                symbol=core_result.symbol,
                interval=core_result.interval,
                days=core_result.days,
                strategy_id=strat_cfg.strategy_id,
                params_used=asdict(core_result.params_used),
                summary=s_dto,
                trades_count=len(core_result.trades),
                trades_sample=[],      # multi-view thường chỉ cần summary
                raw_result=None,       # có thể bỏ None để tiết kiệm RAM
            )
        )

    return out


# ============================================================
# API: TRẠNG THÁI TOOL / LỆNH LIVE / STATS (SKELETON)
# ============================================================

def get_tool_status(session: SessionConfig) -> ToolStatusDTO:
    """
    Skeleton: tạm thời trả cứng, sau này nối với trading-engine.
    UI có thể gọi API này định kỳ để cập nhật trạng thái tool.
    """
    # TODO: nối với engine thật: engine.get_status()
    return ToolStatusDTO(
        running_mode="IDLE",
        is_running=False,
        current_symbol=None,
        current_strategy=session.strategy_config.strategy_id,
        started_at=None,
        last_action="Tool is idle (skeleton).",
        last_error=None,
    )


def get_live_orders(session: SessionConfig) -> List[LiveOrderDTO]:
    """
    Skeleton: sau này lấy từ Binance hoặc DB.
    """
    # TODO: implement thực tế
    return []


def get_live_stats(session: SessionConfig) -> LiveStatsDTO:
    """
    Skeleton: sau này tính từ lịch sử lệnh thực tế.
    """
    # TODO: implement thực tế
    return LiveStatsDTO()
