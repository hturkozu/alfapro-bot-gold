"""
Pozisyon modeli.

Hem paper (simülasyon) hem de live (gerçek borsa) pozisyonları aynı tabloda.
`mode` sütunu ayrımı yapar. PnL hesaplaması her iki modda aynı formülle.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (
        Index("ix_positions_status", "status"),
        Index("ix_positions_mode_symbol", "mode", "symbol"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Bağlam
    signal_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mode: Mapped[str] = mapped_column(String(8), nullable=False)  # paper | live
    strategy_id: Mapped[str] = mapped_column(String(64), default="manual", nullable=False)

    # Enstrüman
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)  # long | short

    # Giriş
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    size_usdt: Mapped[float] = mapped_column(Float, nullable=False)  # kullanılan marjin
    size_base: Mapped[float] = mapped_column(Float, nullable=False)  # base coin adedi
    leverage: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=False)
    take_profit: Mapped[float] = mapped_column(Float, nullable=False)

    # Yaşam döngüsü
    status: Mapped[str] = mapped_column(String(24), default="open", nullable=False)
    # "open" | "closed_tp" | "closed_sl" | "closed_manual" | "closed_reverse"
    opened_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    close_price: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Sonuç
    pnl_usdt: Mapped[float | None] = mapped_column(Float, nullable=True)
    pnl_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Borsa referansı (live modunda)
    exchange_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # ------------------------------------------------------------------
    # Yardımcılar
    # ------------------------------------------------------------------

    def unrealized_pnl(self, mark_price: float) -> tuple[float, float]:
        """Açık pozisyonun anlık kâr/zararı (USDT ve yüzde)."""
        if self.side == "long":
            pnl_per_unit = mark_price - self.entry_price
        else:
            pnl_per_unit = self.entry_price - mark_price
        pnl_usdt = pnl_per_unit * self.size_base
        # Yüzde, kullanılan marjine oranla (kaldıraçlı)
        pnl_pct = (pnl_usdt / self.size_usdt * 100) if self.size_usdt > 0 else 0.0
        return pnl_usdt, pnl_pct

    def close(self, close_price: float, reason: str = "closed_manual") -> None:
        """Pozisyonu kapat ve final PnL'i hesapla."""
        pnl_usdt, pnl_pct = self.unrealized_pnl(close_price)
        self.close_price = close_price
        self.closed_at = datetime.utcnow()
        self.status = reason
        self.pnl_usdt = pnl_usdt
        self.pnl_pct = pnl_pct
