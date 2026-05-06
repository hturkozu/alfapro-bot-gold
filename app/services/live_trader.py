"""
Canlı işlem motoru (Bitget üzerinden).

Paper ile aynı interface'i sunar, farklı olarak ccxt ile gerçek emir gönderir.
Kaldıraç ve margin modu ilk açılışta ayarlanır.

GÜVENLİK:
    - Sadece aktif API credentials varsa kullanılır
    - Her pozisyon için SL/TP otomatik reduce-only stop/take emirleri yerleştirilir
    - Açma başarısız olursa pozisyon DB'ye yazılmaz (tutarsızlık önleme)
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import ccxt
from loguru import logger
from sqlalchemy.orm import Session

from app.models.api_credentials import ApiCredentials
from app.models.position import Position
from app.models.trade import Trade
from app.schemas.trading import SignalCore
from app.services.bitget_client import BitgetClient, get_bitget_client


class LiveTraderError(Exception):
    """Borsa ile iletişim/emir hatası."""


class LiveTrader:
    """Gerçek işlemler için Bitget ccxt sarmalayıcısı."""

    def __init__(self, db: Session, credentials: ApiCredentials) -> None:
        if credentials is None:
            raise LiveTraderError(
                "Canlı mod için önce Ayarlar'dan Bitget API anahtarı eklemelisin."
            )
        self.db = db
        self.credentials = credentials
        self.client: BitgetClient = get_bitget_client(credentials)

    # ------------------------------------------------------------------
    # Borsa yardımcıları
    # ------------------------------------------------------------------

    def _prepare_market(self, symbol: str, leverage: int) -> None:
        """Kaldıraç ve margin modunu ayarla."""
        ex = self.client.exchange
        try:
            ex.set_margin_mode("isolated", symbol, params={"productType": "USDT-FUTURES"})
        except ccxt.ExchangeError as e:
            logger.warning("Margin modu ayarı atlandı ({}): {}", symbol, e)
        try:
            ex.set_leverage(leverage, symbol, params={"productType": "USDT-FUTURES"})
        except ccxt.ExchangeError as e:
            logger.warning("Kaldıraç ayarı atlandı ({}): {}", symbol, e)

    # ------------------------------------------------------------------
    # Açma / kapama
    # ------------------------------------------------------------------

    def open_from_signal(
        self,
        signal: SignalCore,
        size_usdt: float,
        leverage: int,
        signal_db_id: int | None = None,
    ) -> Position:
        return self._open(
            symbol=signal.symbol,
            side=signal.side,
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
        size_usdt: float,
        leverage: int,
        stop_loss: float,
        take_profit: float,
    ) -> Position:
        return self._open(
            symbol=symbol, side=side, size_usdt=size_usdt, leverage=leverage,
            stop_loss=stop_loss, take_profit=take_profit,
            strategy_id="manual", signal_id=None,
        )

    def _open(
        self,
        symbol: str,
        side: str,
        size_usdt: float,
        leverage: int,
        stop_loss: float,
        take_profit: float,
        strategy_id: str,
        signal_id: int | None,
    ) -> Position:
        self._prepare_market(symbol, leverage)

        ex = self.client.exchange
        notional = size_usdt * leverage

        # Giriş için mevcut piyasa fiyatı
        ticker = ex.fetch_ticker(symbol)
        last_price = float(ticker.get("last") or 0.0)
        if last_price <= 0:
            raise LiveTraderError(f"Fiyat alınamadı: {symbol}")

        amount = notional / last_price
        # Borsa precision'a yuvarla
        amount = float(ex.amount_to_precision(symbol, amount))

        ccxt_side = "buy" if side == "long" else "sell"

        try:
            order = ex.create_order(
                symbol=symbol,
                type="market",
                side=ccxt_side,
                amount=amount,
                params={"marginMode": "isolated"},
            )
        except ccxt.BaseError as e:
            raise LiveTraderError(f"Emir gönderilemedi: {e}") from e

        fill_price = float(order.get("average") or order.get("price") or last_price)
        order_id = str(order.get("id", ""))

        pos = Position(
            signal_id=signal_id,
            mode="live",
            strategy_id=strategy_id,
            symbol=symbol,
            side=side,
            entry_price=fill_price,
            size_usdt=size_usdt,
            size_base=amount,
            leverage=leverage,
            stop_loss=stop_loss,
            take_profit=take_profit,
            status="open",
            opened_at=datetime.utcnow(),
            exchange_order_id=order_id,
        )
        self.db.add(pos)
        self.db.commit()
        self.db.refresh(pos)

        self.db.add(
            Trade(
                position_id=pos.id, action="open", symbol=symbol, side=side,
                mode="live", price=fill_price, size_base=amount, fee_usdt=0.0,
                note=f"Live açıldı, kaldıraç {leverage}x", exchange_ref=order_id,
            )
        )
        self.db.commit()

        # SL/TP reduce-only stop emirleri
        self._place_protective_orders(pos)

        logger.bind(trade=True).info(
            "LIVE OPEN {} {} amt={} lev={}x entry={:.6f} SL={:.6f} TP={:.6f} order={}",
            symbol, side.upper(), amount, leverage, fill_price, stop_loss, take_profit, order_id,
        )
        return pos

    def _place_protective_orders(self, pos: Position) -> None:
        """Pozisyon için SL ve TP reduce-only emirleri."""
        ex = self.client.exchange
        close_side = "sell" if pos.side == "long" else "buy"

        # Stop-market (SL)
        try:
            ex.create_order(
                symbol=pos.symbol, type="market", side=close_side,
                amount=pos.size_base,
                params={
                    "stopPrice": pos.stop_loss,
                    "reduceOnly": True,
                    "marginMode": "isolated",
                    "triggerType": "mark_price",
                },
            )
        except ccxt.BaseError as e:
            logger.warning("SL emri yerleştirilemedi: {}", e)

        # Take-profit (limit, reduce-only)
        try:
            ex.create_order(
                symbol=pos.symbol, type="limit", side=close_side,
                amount=pos.size_base, price=pos.take_profit,
                params={"reduceOnly": True, "marginMode": "isolated"},
            )
        except ccxt.BaseError as e:
            logger.warning("TP emri yerleştirilemedi: {}", e)

    def close_position(
        self,
        position: Position,
        reason: str = "closed_manual",
    ) -> Position:
        """Piyasa emriyle pozisyonu kapat."""
        ex = self.client.exchange
        close_side = "sell" if position.side == "long" else "buy"

        try:
            order = ex.create_order(
                symbol=position.symbol, type="market", side=close_side,
                amount=position.size_base,
                params={"reduceOnly": True, "marginMode": "isolated"},
            )
        except ccxt.BaseError as e:
            raise LiveTraderError(f"Kapama emri gönderilemedi: {e}") from e

        close_price = float(order.get("average") or order.get("price") or 0.0)
        if close_price <= 0:
            # Fallback: son ticker fiyatı
            tk = ex.fetch_ticker(position.symbol)
            close_price = float(tk.get("last", 0.0))

        position.close(close_price, reason=reason)
        self.db.add(
            Trade(
                position_id=position.id, action=reason, symbol=position.symbol,
                side=position.side, mode="live", price=close_price,
                size_base=position.size_base, fee_usdt=0.0,
                note=f"Live kapandı, PnL={position.pnl_usdt:.4f} USDT",
                exchange_ref=str(order.get("id", "")),
            )
        )
        self.db.commit()

        logger.bind(trade=True).info(
            "LIVE CLOSE {} {} reason={} close={:.6f} PnL={:.4f}USDT",
            position.symbol, position.side.upper(), reason, close_price, position.pnl_usdt,
        )
        return position


def get_live_trader(db: Session) -> LiveTrader:
    """DB'den aktif Bitget credential'ı al, LiveTrader döndür."""
    cred = (
        db.query(ApiCredentials)
        .filter_by(provider="bitget", is_active=True)
        .order_by(ApiCredentials.id.desc())
        .first()
    )
    if cred is None:
        raise LiveTraderError("Aktif Bitget API anahtarı yok.")
    return LiveTrader(db, cred)
