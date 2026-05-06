"""
Backtest istek / yanıt şemaları (Faz 6).
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class BacktestRequest(BaseModel):
    strategy_id: str = Field(description="Strateji kimliği, ör: scalp_ema_rsi")
    symbol: str = Field(description="ccxt sembol, ör: BTC/USDT:USDT")
    timeframe: str = Field(default="15m", description="Zaman dilimi")
    candle_limit: int = Field(default=500, ge=100, le=1000, description="Geçmiş mum sayısı")
    size_usdt: float = Field(default=100.0, ge=1.0, description="İşlem başı USDT büyüklüğü")
    leverage: int = Field(default=1, ge=1, le=125, description="Kaldıraç")
    params: dict[str, Any] | None = Field(
        default=None, description="Strateji parametre override'ları"
    )


class BacktestTrade(BaseModel):
    side: Literal["long", "short"]
    entry_price: float
    exit_price: float
    entry_ts: int = Field(description="Giriş zaman damgası (ms)")
    exit_ts: int = Field(description="Çıkış zaman damgası (ms)")
    pnl_usdt: float = Field(description="Net PnL (USDT, kaldıraçlı)")
    pnl_pct: float = Field(description="Net PnL % (kaldıraçlı)")
    exit_reason: Literal["sl", "tp", "end"]
    confidence: float = Field(description="Strateji güven skoru (0-100)")


class BacktestMetrics(BaseModel):
    total_trades: int
    win_trades: int
    loss_trades: int
    win_rate: float = Field(description="Kazanma oranı %")
    total_pnl_usdt: float
    total_pnl_pct: float = Field(description="Toplam getiri % (başlangıç sermayesine göre)")
    profit_factor: float = Field(description="Brüt kâr / Brüt zarar")
    max_drawdown_pct: float = Field(description="Maksimum düşüş %")
    sharpe_ratio: float
    avg_trade_pnl_usdt: float
    best_trade_pnl_usdt: float
    worst_trade_pnl_usdt: float


class BacktestResult(BaseModel):
    request: BacktestRequest
    trades: list[BacktestTrade]
    metrics: BacktestMetrics
    equity_curve: list[float] = Field(
        description="Kümülatif PnL serisi (0'dan başlar)"
    )
    candles_analyzed: int = Field(description="İşlenen mum sayısı (warm-up hariç)")
    signals_generated: int = Field(description="Üretilen toplam sinyal sayısı")
    duration_ms: int = Field(description="Hesaplama süresi (ms)")
