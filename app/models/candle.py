"""
OHLCV mum verisi cache modeli.

Bitget'ten çekilen mumlar SQLite'a yazılır. Aynı mumu tekrar çekmemek
için (symbol, timeframe, timestamp) unique kombinasyonu tutulur.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Candle(Base):
    """Tek bir OHLCV mumu. Tek satır = tek mum."""

    __tablename__ = "candles"
    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "ts", name="uq_symbol_tf_ts"),
        Index("ix_symbol_tf_ts", "symbol", "timeframe", "ts"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Piyasa kimliği
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False)  # 1m, 5m, 15m, 1h...

    # Mum zamanı (milisaniye, Unix epoch)
    ts: Mapped[int] = mapped_column(Integer, nullable=False)

    # OHLCV
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    def to_row(self) -> list[float]:
        """ccxt benzeri satır formatı: [ts, o, h, l, c, v]"""
        return [self.ts, self.open, self.high, self.low, self.close, self.volume]
