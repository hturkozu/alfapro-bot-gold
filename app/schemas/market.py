"""
Market data için request/response şemaları.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


Timeframe = Literal["1m", "5m", "15m", "1h", "4h", "1d"]


class CandleOut(BaseModel):
    """Tek mum — grafik için düz yapı."""

    ts: int = Field(description="Unix epoch milliseconds")
    open: float
    high: float
    low: float
    close: float
    volume: float


class CandlesResponse(BaseModel):
    symbol: str
    timeframe: str
    count: int
    candles: list[CandleOut]


class SymbolInfo(BaseModel):
    symbol: str = Field(description="ccxt sembol, ör: BTC/USDT:USDT")
    base: str
    quote: str
    type: str = Field(description="spot / swap / future")
    active: bool


class IndicatorRequest(BaseModel):
    """İndikatör hesaplama parametreleri — query string'den parse edilir."""

    ema_periods: list[int] = Field(default_factory=lambda: [9, 21, 50, 200])
    rsi_length: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    atr_length: int = 14
    bb_length: int = 20
    bb_std: float = 2.0


class IndicatorValues(BaseModel):
    """Hesaplanan indikatörlerin SON değerleri (dashboard kartları için)."""

    ema: dict[str, float | None] = Field(default_factory=dict)  # "ema_9": 65000.1, ...
    rsi: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_hist: float | None = None
    atr: float | None = None
    bb_upper: float | None = None
    bb_middle: float | None = None
    bb_lower: float | None = None
    vwap: float | None = None
    stoch_k: float | None = None   # Stochastic RSI %K
    stoch_d: float | None = None   # Stochastic RSI %D


class IndicatorSeries(BaseModel):
    """Grafik için tüm seri verisi (overlay/subplot çizmek için)."""

    ts: list[int]
    ema: dict[str, list[float | None]] = Field(default_factory=dict)
    rsi: list[float | None] = Field(default_factory=list)
    macd: list[float | None] = Field(default_factory=list)
    macd_signal: list[float | None] = Field(default_factory=list)
    macd_hist: list[float | None] = Field(default_factory=list)
    atr: list[float | None] = Field(default_factory=list)
    bb_upper: list[float | None] = Field(default_factory=list)
    bb_middle: list[float | None] = Field(default_factory=list)
    bb_lower: list[float | None] = Field(default_factory=list)
    vwap: list[float | None] = Field(default_factory=list)
    stoch_k: list[float | None] = Field(default_factory=list)
    stoch_d: list[float | None] = Field(default_factory=list)


class FibonacciLevels(BaseModel):
    """Son N mumdan otomatik tespit edilen swing'e göre Fib."""

    swing_high: float
    swing_low: float
    direction: Literal["up", "down"] = Field(description="Trend yönü")
    retracement: dict[str, float] = Field(
        description="0.236, 0.382, 0.5, 0.618, 0.786"
    )
    extension: dict[str, float] = Field(
        description="1.272, 1.414, 1.618, 2.0, 2.618"
    )


class SmcBos(BaseModel):
    """Break of Structure — trend devam sinyali."""

    ts: int
    price: float
    direction: Literal["bullish", "bearish"]


class SmcChoch(BaseModel):
    """Change of Character — trend değişim sinyali."""

    ts: int
    price: float
    direction: Literal["bullish", "bearish"]


class SmcOrderBlock(BaseModel):
    """Order Block — güçlü hareket öncesi son ters mum."""

    ts: int
    high: float
    low: float
    direction: Literal["bullish", "bearish"]


class SmcAnalysis(BaseModel):
    bos: list[SmcBos] = Field(default_factory=list)
    choch: list[SmcChoch] = Field(default_factory=list)
    order_blocks: list[SmcOrderBlock] = Field(default_factory=list)
    current_trend: Literal["bullish", "bearish", "neutral"] = "neutral"


class MarketAnalysis(BaseModel):
    """Ana sayfadaki hepsi-bir-arada durum bilgisi."""

    symbol: str
    timeframe: str
    last_price: float
    change_24h_pct: float | None = None
    volume_24h: float | None = None
    candles: list[CandleOut]
    indicators_last: IndicatorValues
    indicators_series: IndicatorSeries
    fibonacci: FibonacciLevels | None = None
    smc: SmcAnalysis
