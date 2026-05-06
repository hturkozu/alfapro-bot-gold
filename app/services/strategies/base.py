"""
Strateji taban sınıfı.

Her strateji `BaseStrategy`'den türer ve `evaluate()` metodunu override eder.
Context: mumlar + indikatörler + fib + smc + market meta.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.schemas.market import (
    FibonacciLevels,
    IndicatorSeries,
    IndicatorValues,
    SmcAnalysis,
)
from app.schemas.trading import SignalCore


@dataclass
class StrategyContext:
    """Strateji için tam bağlam — tek bir değerlendirme anında."""

    symbol: str
    timeframe: str
    candles: list[list[float]]  # [ts, o, h, l, c, v]
    ind_last: IndicatorValues
    ind_series: IndicatorSeries
    fib: FibonacciLevels | None
    smc: SmcAnalysis
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def last_price(self) -> float:
        if not self.candles:
            return 0.0
        return float(self.candles[-1][4])

    @property
    def last_ts(self) -> int:
        if not self.candles:
            return 0
        return int(self.candles[-1][0])


class BaseStrategy(ABC):
    """Tüm stratejilerin ortak arayüzü."""

    # Alt sınıflar override edecek
    id: str = "base"
    name: str = "Base Strategy"
    description: str = ""
    default_timeframes: list[str] = ["15m"]
    default_params: dict[str, Any] = {}

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        # Parametreleri default ile birleştir
        merged = {**self.default_params}
        if params:
            merged.update(params)
        self.params = merged

    @abstractmethod
    def evaluate(self, ctx: StrategyContext) -> SignalCore | None:
        """Bağlamı değerlendir ve sinyal üret (yoksa None)."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Ortak yardımcılar — confidence scoring
    # ------------------------------------------------------------------

    @staticmethod
    def clamp_confidence(value: float) -> float:
        return max(0.0, min(100.0, value))

    @staticmethod
    def atr_based_sl_tp(
        entry: float,
        atr: float,
        side: str,
        sl_mult: float = 1.5,
        tp_mult: float = 2.5,
    ) -> tuple[float, float]:
        """ATR tabanlı Stop Loss / Take Profit hesapla."""
        if side == "long":
            sl = entry - atr * sl_mult
            tp = entry + atr * tp_mult
        else:
            sl = entry + atr * sl_mult
            tp = entry - atr * tp_mult
        return round(sl, 8), round(tp, 8)

    @staticmethod
    def risk_reward(entry: float, sl: float, tp: float) -> float:
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        if risk == 0:
            return 0.0
        return reward / risk
