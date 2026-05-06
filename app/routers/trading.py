"""
Trading endpoint'leri:

- GET    /trading/mode                : paper | live
- POST   /trading/mode                : mode değiştir (live için onay zorunlu)
- GET    /trading/positions           : pozisyonlar (filtreli)
- POST   /trading/positions           : manuel pozisyon aç
- POST   /trading/positions/{id}/close: pozisyonu kapat
- POST   /trading/positions/tick      : tüm açık paper pozisyonlarda SL/TP kontrolü
- GET    /trading/signals             : son N sinyal
- GET    /trading/trades              : işlem günlüğü
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.api_credentials import ApiCredentials
from app.models.app_state import AppState
from app.models.position import Position
from app.models.signal import Signal
from app.models.trade import Trade
from app.schemas.trading import (
    ClosePositionRequest,
    OpenPositionRequest,
    PositionOut,
    SignalOut,
    TradeOut,
    TradingModeOut,
    TradingModeUpdate,
)
from app.services.live_trader import LiveTrader, LiveTraderError, get_live_trader
from app.services.market_data import get_market_service
from app.services.paper_trader import PaperTrader


router = APIRouter(prefix="/trading", tags=["trading"])


# ----------------------------------------------------------------------
# Mode
# ----------------------------------------------------------------------

def _get_state(db: Session) -> AppState:
    state = db.get(AppState, 1)
    if state is None:
        state = AppState(id=1, trading_mode="paper")
        db.add(state)
        db.commit()
        db.refresh(state)
    return state


@router.get("/mode", response_model=TradingModeOut)
def get_mode(db: Session = Depends(get_db)) -> TradingModeOut:
    state = _get_state(db)
    open_paper = (
        db.query(Position).filter_by(status="open", mode="paper").count()
    )
    open_live = (
        db.query(Position).filter_by(status="open", mode="live").count()
    )
    return TradingModeOut(
        mode=state.trading_mode,  # type: ignore[arg-type]
        open_paper_positions=open_paper,
        open_live_positions=open_live,
    )


@router.post("/mode", response_model=TradingModeOut)
def set_mode(
    payload: TradingModeUpdate,
    db: Session = Depends(get_db),
) -> TradingModeOut:
    state = _get_state(db)

    if payload.mode == "live" and not payload.confirm_live:
        raise HTTPException(
            status_code=400,
            detail="Canlı mod tehlikelidir. İsteğe `confirm_live: true` ekle.",
        )

    if payload.mode == "live":
        # Live'a geçmeden önce aktif credential olmalı
        cred = (
            db.query(ApiCredentials)
            .filter_by(provider="bitget", is_active=True).first()
        )
        if cred is None:
            raise HTTPException(
                status_code=400,
                detail="Aktif Bitget API anahtarı yok. Önce Ayarlar'dan ekle.",
            )

    state.trading_mode = payload.mode
    db.commit()
    logger.warning("Trading modu değişti: → {}", payload.mode)
    return get_mode(db)


# ----------------------------------------------------------------------
# Positions
# ----------------------------------------------------------------------

@router.get("/positions", response_model=list[PositionOut])
def list_positions(
    mode: str | None = Query(None, pattern="^(paper|live)$"),
    status: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[PositionOut]:
    q = db.query(Position)
    if mode:
        q = q.filter(Position.mode == mode)
    if status:
        q = q.filter(Position.status == status)
    rows = q.order_by(Position.id.desc()).limit(limit).all()
    return [PositionOut.model_validate(r) for r in rows]


@router.post("/positions", response_model=PositionOut, status_code=201)
def open_position(
    payload: OpenPositionRequest,
    db: Session = Depends(get_db),
) -> PositionOut:
    state = _get_state(db)
    mode = state.trading_mode

    try:
        if mode == "paper":
            # Paper'da giriş fiyatı ticker'dan alınır
            cred = (
                db.query(ApiCredentials)
                .filter_by(provider="bitget", is_active=True).first()
            )
            svc = get_market_service(db, credentials=cred)
            tk = svc.get_ticker_summary(payload.symbol)
            last = tk.get("last") or payload.stop_loss  # fallback
            if last is None or last <= 0:
                raise HTTPException(status_code=503, detail="Fiyat alınamadı")

            trader = PaperTrader(db)
            pos = trader.open_manual(
                symbol=payload.symbol,
                side=payload.side,
                entry_price=last,
                size_usdt=payload.size_usdt,
                leverage=payload.leverage,
                stop_loss=payload.stop_loss,
                take_profit=payload.take_profit,
            )
            return PositionOut.model_validate(pos)

        # LIVE
        trader = get_live_trader(db)
        pos = trader.open_manual(
            symbol=payload.symbol, side=payload.side,
            size_usdt=payload.size_usdt, leverage=payload.leverage,
            stop_loss=payload.stop_loss, take_profit=payload.take_profit,
        )
        return PositionOut.model_validate(pos)

    except LiveTraderError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/positions/{pos_id}/close", response_model=PositionOut)
def close_position(
    pos_id: int,
    payload: ClosePositionRequest,
    db: Session = Depends(get_db),
) -> PositionOut:
    pos = db.get(Position, pos_id)
    if pos is None:
        raise HTTPException(status_code=404, detail="Pozisyon bulunamadı")
    if pos.status != "open":
        raise HTTPException(status_code=400, detail=f"Pozisyon zaten {pos.status}")

    try:
        if pos.mode == "paper":
            # Son piyasa fiyatından kapat
            cred = (
                db.query(ApiCredentials)
                .filter_by(provider="bitget", is_active=True).first()
            )
            svc = get_market_service(db, credentials=cred)
            tk = svc.get_ticker_summary(pos.symbol)
            last = tk.get("last")
            if not last:
                raise HTTPException(status_code=503, detail="Fiyat alınamadı")

            trader = PaperTrader(db)
            trader.close_position(pos, float(last), reason=payload.reason)
        else:
            trader = get_live_trader(db)
            trader.close_position(pos, reason=payload.reason)
    except LiveTraderError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    db.refresh(pos)
    return PositionOut.model_validate(pos)


@router.post("/positions/tick")
def paper_tick(db: Session = Depends(get_db)) -> dict:
    """
    Açık paper pozisyonlarda SL/TP kontrolü yap.
    Bu endpoint şimdilik manuel tetikli; Faz 4'te otomatik scheduler eklenecek.
    """
    trader = PaperTrader(db)
    cred = (
        db.query(ApiCredentials)
        .filter_by(provider="bitget", is_active=True).first()
    )
    svc = get_market_service(db, credentials=cred)

    open_positions = db.query(Position).filter_by(status="open", mode="paper").all()
    closed_count = 0
    checked_count = 0

    # Sembol bazlı fiyat cache (aynı sembolü iki kere çekme)
    price_cache: dict[str, float] = {}

    for pos in open_positions:
        checked_count += 1
        if pos.symbol not in price_cache:
            tk = svc.get_ticker_summary(pos.symbol)
            last = tk.get("last")
            if last is None:
                continue
            price_cache[pos.symbol] = float(last)

        current = price_cache[pos.symbol]
        result = trader.check_sl_tp(pos, current)
        if result is not None:
            closed_count += 1

    return {
        "checked": checked_count,
        "closed": closed_count,
        "mode": "paper",
    }


# ----------------------------------------------------------------------
# Signals
# ----------------------------------------------------------------------

@router.get("/signals", response_model=list[SignalOut])
def list_signals(
    symbol: str | None = None,
    strategy_id: str | None = None,
    executed: bool | None = None,
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[SignalOut]:
    q = db.query(Signal)
    if symbol:
        q = q.filter(Signal.symbol == symbol)
    if strategy_id:
        q = q.filter(Signal.strategy_id == strategy_id)
    if executed is not None:
        q = q.filter(Signal.executed == executed)
    rows = q.order_by(Signal.id.desc()).limit(limit).all()
    return [SignalOut.model_validate(r) for r in rows]


# ----------------------------------------------------------------------
# Trade log
# ----------------------------------------------------------------------

@router.get("/trades", response_model=list[TradeOut])
def list_trades(
    position_id: int | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[TradeOut]:
    q = db.query(Trade)
    if position_id:
        q = q.filter(Trade.position_id == position_id)
    rows = q.order_by(Trade.id.desc()).limit(limit).all()
    return [TradeOut.model_validate(r) for r in rows]
