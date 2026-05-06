"""
Sinyal kaydı modeli.

Her strateji değerlendirmesinde üretilen sinyal buraya yazılır.
İşleme dönüşsün-dönüşmesin audit için saklanır.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = (
        Index("ix_signals_symbol_ts", "symbol", "ts"),
        Index("ix_signals_strategy_ts", "strategy_id", "ts"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Üretim bağlamı
    strategy_id: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False)

    # Sinyal içeriği
    side: Mapped[str] = mapped_column(String(8), nullable=False)  # long | short
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=False)
    take_profit: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Sonraki aşamalarda kullanılacak (AI, vs.)
    ai_approved: Mapped[bool | None] = mapped_column(default=None, nullable=True)
    ai_confidence: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    ai_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # Execution takibi
    executed: Mapped[bool] = mapped_column(default=False, nullable=False)
    position_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    ts: Mapped[int] = mapped_column(Integer, nullable=False)  # ms
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
