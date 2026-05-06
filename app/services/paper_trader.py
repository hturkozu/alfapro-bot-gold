"""
Paper trading motoru.

Gerçek borsaya dokunmadan sinyalleri DB'ye pozisyon olarak yazar.
Her tick'te açık pozisyonların SL/TP'sini kontrol eder, tetiklenen
pozisyonları kapatır ve PnL'i hesaplar.
"""
from __future__ import annotations

from datetime import datetime

from loguru import logger
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.position import Position
from app.models.signal import Signal
from app.models.trade import Trade
from app.schemas.trading import SignalCore


def _taker_fee_rate() -> float:
    """Settings'teki yüzdeyi orana çevir (0.06% → 0.0006)."""
    return float(get_settings().paper_taker_fee_pct) / 100.0


class PaperTrader:
    """Simülasyonlu işlem motoru."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Pozisyon açma
    # ------------------------------------------------------------------

    def open_from_signal(
        self,
        signal: SignalCore,
        size_usdt: float,
        leverage: int,
        signal_db_id: int | None = None,
    ) -> Position:
        """Bir sinyalden paper pozisyon üretir."""
        return self._open(
            symbol=signal.symbol,
            side=signal.side,
            entry_price=signal.entry_price,
            size_usdt=size_usdt,
            leverage=leverage,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            strategy_id=signal.strategy_id,
            signal_id=signal_db_id,
        )

    def open_manual(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        size_usdt: float,
        leverage: int,
        stop_loss: float,
        take_profit: float,
    ) -> Position:
        """Panel üzerinden manuel pozisyon."""
        return self._open(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            size_usdt=size_usdt,
            leverage=leverage,
            stop_loss=stop_loss,
            take_profit=take_profit,
            strategy_id="manual",
            signal_id=None,
        )

    def _open(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        size_usdt: float,
        leverage: int,
        stop_loss: float,
        take_profit: float,
        strategy_id: str,
        signal_id: int | None,
    ) -> Position:
        # Kaldıraçlı baz miktar
        notional = size_usdt * leverage
        size_base = notional / entry_price if entry_price > 0 else 0.0

        pos = Position(
            signal_id=signal_id,
            mode="paper",
            strategy_id=strategy_id,
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            size_usdt=size_usdt,
            size_base=size_base,
            leverage=leverage,
            stop_loss=stop_loss,
            take_profit=take_profit,
            status="open",
            opened_at=datetime.utcnow(),
        )
        self.db.add(pos)
        self.db.commit()
        self.db.refresh(pos)

        # Açılış komisyonu (taker) — notional üzerinden
        open_fee = entry_price * size_base * _taker_fee_rate()

        self.db.add(
            Trade(
                position_id=pos.id,
                action="open",
                symbol=symbol,
                side=side,
                mode="paper",
                price=entry_price,
                size_base=size_base,
                fee_usdt=open_fee,
                note=f"Paper açıldı, kaldıraç {leverage}x, fee={open_fee:.4f} USDT",
            )
        )
        self.db.commit()

        logger.bind(trade=True).info(
            "PAPER OPEN {} {} size_usdt={:.2f} lev={}x entry={:.6f} SL={:.6f} TP={:.6f} fee={:.4f}",
            symbol, side.upper(), size_usdt, leverage, entry_price, stop_loss, take_profit, open_fee,
        )
        return pos

    # ------------------------------------------------------------------
    # Pozisyon kapatma
    # ------------------------------------------------------------------

    def close_position(
        self,
        position: Position,
        close_price: float,
        reason: str = "closed_manual",
    ) -> Position:
        # Önce gross PnL'i hesapla (Position.close içinde)
        position.close(close_price, reason=reason)

        # Komisyonları çıkar: açılış + kapanış (her ikisi de taker)
        fee_rate = _taker_fee_rate()
        open_fee = position.entry_price * position.size_base * fee_rate
        close_fee = close_price * position.size_base * fee_rate
        total_fee = open_fee + close_fee

        gross_pnl = position.pnl_usdt or 0.0
        net_pnl = gross_pnl - total_fee
        position.pnl_usdt = net_pnl
        position.pnl_pct = (
            (net_pnl / position.size_usdt * 100) if position.size_usdt > 0 else 0.0
        )

        self.db.add(
            Trade(
                position_id=position.id,
                action=reason,
                symbol=position.symbol,
                side=position.side,
                mode=position.mode,
                price=close_price,
                size_base=position.size_base,
                fee_usdt=close_fee,
                note=(
                    f"Paper kapatıldı, gross={gross_pnl:.4f} fee={total_fee:.4f} "
                    f"net={net_pnl:.4f} USDT ({position.pnl_pct:.2f}%)"
                ),
            )
        )
        self.db.commit()

        logger.bind(trade=True).info(
            "PAPER CLOSE {} {} reason={} close={:.6f} gross={:.4f} fee={:.4f} net={:.4f}USDT ({:.2f}%)",
            position.symbol, position.side.upper(), reason,
            close_price, gross_pnl, total_fee, net_pnl, position.pnl_pct,
        )
        return position

    # ------------------------------------------------------------------
    # Tick — SL/TP kontrolü (dış bir servis tetikler)
    # ------------------------------------------------------------------

    def check_sl_tp(
        self,
        position: Position,
        current_price: float,
        bar_high: float | None = None,
        bar_low: float | None = None,
    ) -> str | None:
        """
        SL/TP tetiklendiyse pozisyonu kapatır.

        bar_high/bar_low verilirse (canlı 1m mum'dan) wick'ler de kontrol edilir.
        Tick'ler arası fiyat sıçramalarının kaçırılmasını engeller.
        Aynı barda hem SL hem TP varsa konservatif şekilde SL'e öncelik verilir.

        Döner: 'closed_sl' | 'closed_tp' | None
        """
        if position.status != "open":
            return None

        hi = bar_high if bar_high is not None else current_price
        lo = bar_low if bar_low is not None else current_price
        # current_price'ı da aralığa dahil et — bar verisi gecikmeli olabilir
        hi = max(hi, current_price)
        lo = min(lo, current_price)

        hit: str | None = None
        close_px: float | None = None

        if position.side == "long":
            if lo <= position.stop_loss:
                hit, close_px = "closed_sl", position.stop_loss
            elif hi >= position.take_profit:
                hit, close_px = "closed_tp", position.take_profit
        else:  # short
            if hi >= position.stop_loss:
                hit, close_px = "closed_sl", position.stop_loss
            elif lo <= position.take_profit:
                hit, close_px = "closed_tp", position.take_profit

        if hit is not None and close_px is not None:
            self.close_position(position, close_px, reason=hit)
            return hit
        return None

    # ------------------------------------------------------------------
    # Break-even & trailing stop
    # ------------------------------------------------------------------

    def apply_trailing(
        self,
        position: Position,
        current_price: float,
        bar_high: float | None = None,
        bar_low: float | None = None,
    ) -> bool:
        """
        SL'i lehte yönde sıkılaştırır (asla geriletmez).

        - Break-even: peak, TP mesafesinin trigger_pct'ine ulaştıysa SL'i
          entry ± offset'e taşı.
        - Trailing: SL'i peak × (1 ± trail_pct/100)'a çek (mevcut SL'den
          daha sıkıysa).

        Settings'te her iki parametre de 0 ise no-op.
        Döner: True → SL güncellendi (DB commit edildi)
        """
        if position.status != "open":
            return False

        s = get_settings()
        trigger = float(s.paper_breakeven_trigger_pct)
        offset = float(s.paper_breakeven_offset_pct) / 100.0
        trail = float(s.paper_trailing_pct) / 100.0
        if trigger <= 0 and trail <= 0:
            return False

        hi = bar_high if bar_high is not None else current_price
        lo = bar_low if bar_low is not None else current_price
        hi = max(hi, current_price)
        lo = min(lo, current_price)

        entry = position.entry_price
        sl = position.stop_loss
        tp = position.take_profit
        new_sl = sl

        if position.side == "long":
            peak = hi
            if trigger > 0 and tp > entry:
                be_threshold = entry + (tp - entry) * trigger / 100.0
                if peak >= be_threshold:
                    new_sl = max(new_sl, entry * (1.0 + offset))
            if trail > 0:
                new_sl = max(new_sl, peak * (1.0 - trail))
            # SL'in TP'yi geçmesine izin verme
            if new_sl >= tp:
                new_sl = sl
            if new_sl > sl:
                position.stop_loss = round(new_sl, 8)
                self.db.commit()
                logger.bind(trade=True).info(
                    "PAPER TRAIL {} long SL {:.6f} → {:.6f} peak={:.6f}",
                    position.symbol, sl, new_sl, peak,
                )
                return True
        else:  # short
            trough = lo
            if trigger > 0 and tp < entry:
                be_threshold = entry - (entry - tp) * trigger / 100.0
                if trough <= be_threshold:
                    new_sl = min(new_sl, entry * (1.0 - offset))
            if trail > 0:
                new_sl = min(new_sl, trough * (1.0 + trail))
            if new_sl <= tp:
                new_sl = sl
            if new_sl < sl:
                position.stop_loss = round(new_sl, 8)
                self.db.commit()
                logger.bind(trade=True).info(
                    "PAPER TRAIL {} short SL {:.6f} → {:.6f} trough={:.6f}",
                    position.symbol, sl, new_sl, trough,
                )
                return True

        return False

    # ------------------------------------------------------------------
    # Sinyali işaretle
    # ------------------------------------------------------------------

    def persist_signal(self, signal: SignalCore) -> Signal:
        """SignalCore'u DB'ye kaydet."""
        db_sig = Signal(
            strategy_id=signal.strategy_id,
            symbol=signal.symbol,
            timeframe=signal.timeframe,
            side=signal.side,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            confidence=signal.confidence,
            reasoning=" | ".join(signal.reasoning),
            ts=signal.ts,
        )
        self.db.add(db_sig)
        self.db.commit()
        self.db.refresh(db_sig)
        return db_sig
