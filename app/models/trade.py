"""
İşlem günlüğü.

Her pozisyon açma/kapama/güncelleme buraya bir satır yazar.
Loguru'dan ayrı olarak yapılandırılmış veri için kullanılır.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (Index("ix_trades_pos_ts", "position_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    position_id: Mapped[int] = mapped_column(Integer, nullable=False)

    action: Mapped[str] = mapped_column(String(24), nullable=False)
    # open | close_tp | close_sl | close_manual | update_sl | update_tp

    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    mode: Mapped[str] = mapped_column(String(8), nullable=False)

    price: Mapped[float] = mapped_column(Float, nullable=False)
    size_base: Mapped[float] = mapped_column(Float, nullable=False)
    fee_usdt: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    exchange_ref: Mapped[str] = mapped_column(String(64), default="", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
