"""
Risk + AI + Scheduler + Telegram için şemalar.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ----------------------------------------------------------------------
# App state (tek endpoint, tüm Faz 4 ayarları burada)
# ----------------------------------------------------------------------

class AppStateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    trading_mode: str

    max_open_positions: int
    daily_loss_limit_usdt: float
    circuit_breaker_tripped: bool
    circuit_breaker_date: str

    ai_enabled: bool
    ai_min_confidence: float
    anthropic_api_key_masked: str = ""
    openai_api_key_masked: str = ""

    scheduler_enabled: bool
    scheduler_interval_seconds: int
    live_auto_trading_enabled: bool = False

    telegram_enabled: bool
    telegram_bot_token_masked: str = ""
    telegram_chat_id: str

    updated_at: datetime


class AppStateUpdate(BaseModel):
    """Tüm alanlar opsiyonel — patch semantik."""

    max_open_positions: int | None = Field(default=None, ge=1, le=100)
    daily_loss_limit_usdt: float | None = Field(default=None, gt=0)

    ai_enabled: bool | None = None
    ai_min_confidence: float | None = Field(default=None, ge=0, le=100)
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    scheduler_enabled: bool | None = None
    scheduler_interval_seconds: int | None = Field(default=None, ge=15, le=3600)
    live_auto_trading_enabled: bool | None = None

    telegram_enabled: bool | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None


class RiskStatusOut(BaseModel):
    """Anlık risk durumu."""

    trading_mode: str
    daily_pnl_usdt: float
    daily_loss_limit_usdt: float
    circuit_breaker_tripped: bool
    circuit_breaker_date: str
    open_positions_count: int
    max_open_positions: int
    bitget_connected: bool = False


class TelegramTestResult(BaseModel):
    ok: bool
    message: str


class AiTestRequest(BaseModel):
    """Manuel AI testi — dummy sinyalle."""

    symbol: str = "BTC/USDT:USDT"
    side: str = "long"


class AiTestResult(BaseModel):
    ok: bool
    confidence: float | None = None
    notes: str
    error: str | None = None


class AiConnectionTestResult(BaseModel):
    ok: bool
    message: str
    latency_ms: int | None = None
    error: str | None = None
