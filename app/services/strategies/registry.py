"""
Strateji kayıt defteri.

Yeni bir strateji eklemek için:
    1. Yeni bir dosya oluştur (ör. `my_strategy.py`)
    2. `BaseStrategy`'den türeyen sınıf tanımla
    3. `_STRATEGIES` dict'ine ekle
"""
from __future__ import annotations

from typing import Any

from app.schemas.trading import StrategyInfo
from app.services.strategies.base import BaseStrategy
from app.services.strategies.scalp_1m import Scalp1M
from app.services.strategies.scalp_ema_rsi import ScalpEmaRsi
from app.services.strategies.scalp_sweep_momentum import ScalpSweepMomentum
from app.services.strategies.swing_smc_fib import SwingSmcFib


_STRATEGIES: dict[str, type[BaseStrategy]] = {
    Scalp1M.id: Scalp1M,
    ScalpEmaRsi.id: ScalpEmaRsi,
    ScalpSweepMomentum.id: ScalpSweepMomentum,
    SwingSmcFib.id: SwingSmcFib,
}


def list_strategies() -> list[type[BaseStrategy]]:
    """Kayıtlı tüm strateji sınıflarını döndürür."""
    return list(_STRATEGIES.values())


def get_strategy(strategy_id: str, params: dict[str, Any] | None = None) -> BaseStrategy:
    """İstenen stratejinin örneğini üretir."""
    cls = _STRATEGIES.get(strategy_id)
    if cls is None:
        raise KeyError(f"Bilinmeyen strateji: {strategy_id}")
    return cls(params=params)


def strategy_info(cls: type[BaseStrategy]) -> StrategyInfo:
    """Strateji sınıfından meta bilgi çıkarır (panel için)."""
    return StrategyInfo(
        id=cls.id,
        name=cls.name,
        description=cls.description,
        default_timeframes=list(cls.default_timeframes),
        default_params=dict(cls.default_params),
    )
