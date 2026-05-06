"""
Trading & strateji için pydantic şemaları.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


Side = Literal["long", "short"]
TradingMode = Literal["paper", "live"]
PositionStatus = Literal[
    "open", "closed_tp", "closed_sl", "closed_manual", "closed_reverse"
]


# ----------------------------------------------------------------------
# Signal
# ----------------------------------------------------------------------

class SignalCore(BaseModel):
    """Stratejinin ürettiği saf sinyal yapısı (DB'ye yazılmadan)."""

    strategy_id: str
    symbol: str
    timeframe: str
    side: Side
    entry_price: float
    stop_loss: float
    take_profit: float
    confidence: float = Field(ge=0.0, le=100.0)
    reasoning: list[str] = Field(default_factory=list)
    ts: int


class SignalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    strategy_id: str
    symbol: str
    timeframe: str
    side: str
    entry_price: float
    stop_loss: float
    take_profit: float
    confidence: float
    reasoning: str
    ai_approved: bool | None = None
    ai_notes: str = ""
    executed: bool
    position_id: int | None = None
    ts: int
    created_at: datetime


# ----------------------------------------------------------------------
# Position
# ----------------------------------------------------------------------

class PositionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    signal_id: int | None = None
    mode: str
    strategy_id: str
    symbol: str
    side: str
    entry_price: float
    size_usdt: float
    size_base: float
    leverage: int
    stop_loss: float
    take_profit: float
    status: str
    opened_at: datetime
    closed_at: datetime | None = None
    close_price: float | None = None
    pnl_usdt: float | None = None
    pnl_pct: float | None = None


class OpenPositionRequest(BaseModel):
    """Manuel pozisyon açma isteği."""

    symbol: str
    side: Side
    size_usdt: float = Field(gt=0)
    leverage: int = Field(ge=1, le=125)
    stop_loss: float
    take_profit: float


class ClosePositionRequest(BaseModel):
    """Pozisyon kapatma — piyasa fiyatından."""

    reason: str = "closed_manual"


# ----------------------------------------------------------------------
# Trade log
# ----------------------------------------------------------------------

class TradeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    position_id: int
    action: str
    symbol: str
    side: str
    mode: str
    price: float
    size_base: float
    fee_usdt: float
    note: str
    exchange_ref: str
    created_at: datetime


# ----------------------------------------------------------------------
# Mode
# ----------------------------------------------------------------------

class TradingModeOut(BaseModel):
    mode: TradingMode
    open_paper_positions: int = 0
    open_live_positions: int = 0


class TradingModeUpdate(BaseModel):
    mode: TradingMode
    # Live'a geçerken zorunlu onay — kullanıcı yanlışlıkla geçmesin
    confirm_live: bool = False


# ----------------------------------------------------------------------
# Strategies
# ----------------------------------------------------------------------

class StrategyInfo(BaseModel):
    """Kayıtlı strateji meta bilgisi (registry'den gelir)."""

    id: str
    name: str
    description: str
    default_timeframes: list[str]
    default_params: dict[str, Any]


class StrategyConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    strategy_id: str
    enabled: bool
    symbols: list[str]
    timeframes: list[str]
    params: dict[str, Any]
    size_usdt: float
    leverage: int
    updated_at: datetime


class StrategyConfigUpdate(BaseModel):
    enabled: bool | None = None
    symbols: list[str] | None = None
    timeframes: list[str] | None = None
    params: dict[str, Any] | None = None
    size_usdt: float | None = Field(default=None, gt=0)
    leverage: int | None = Field(default=None, ge=1, le=125)


class StrategyEvaluateResult(BaseModel):
    """On-demand evaluate — sonuç: sinyal var/yok + detay."""

    strategy_id: str
    symbol: str
    timeframe: str
    has_signal: bool
    signal: SignalCore | None = None
    debug: dict[str, Any] = Field(default_factory=dict)
