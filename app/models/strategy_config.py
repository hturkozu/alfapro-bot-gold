"""
Strateji konfigürasyon modeli.

Her strateji için parametreler JSON olarak saklanır.
Panelden düzenlenir, strateji çalışırken okunur.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StrategyConfig(Base):
    __tablename__ = "strategy_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    strategy_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    symbols: Mapped[str] = mapped_column(Text, default="[]", nullable=False)  # JSON list
    timeframes: Mapped[str] = mapped_column(Text, default="[]", nullable=False)  # JSON list
    params_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    # Pozisyon boyutu
    size_usdt: Mapped[float] = mapped_column(default=10.0, nullable=False)
    leverage: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # ------------------------------------------------------------------
    # Yardımcılar — JSON alanlarını otomatik çöz
    # ------------------------------------------------------------------

    @property
    def params(self) -> dict[str, Any]:
        try:
            return json.loads(self.params_json or "{}")
        except (json.JSONDecodeError, TypeError):
            return {}

    @params.setter
    def params(self, value: dict[str, Any]) -> None:
        self.params_json = json.dumps(value or {})

    @property
    def symbols_list(self) -> list[str]:
        try:
            return json.loads(self.symbols or "[]")
        except (json.JSONDecodeError, TypeError):
            return []

    @symbols_list.setter
    def symbols_list(self, value: list[str]) -> None:
        self.symbols = json.dumps(value or [])

    @property
    def timeframes_list(self) -> list[str]:
        try:
            return json.loads(self.timeframes or "[]")
        except (json.JSONDecodeError, TypeError):
            return []

    @timeframes_list.setter
    def timeframes_list(self, value: list[str]) -> None:
        self.timeframes = json.dumps(value or [])
