"""
Backtest endpoint'leri (Faz 6).

- GET  /backtest/strategies  : Backtest için mevcut stratejiler
- POST /backtest/run         : Backtest çalıştır
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.api_credentials import ApiCredentials
from app.schemas.backtest import BacktestRequest, BacktestResult
from app.services.backtester import Backtester
from app.services.market_data import get_market_service
from app.services.strategies.registry import list_strategies, strategy_info


router = APIRouter(tags=["backtest"])


@router.get("/backtest/strategies")
def backtest_strategies() -> list[dict]:
    """Backteste uygun tüm stratejilerin listesi."""
    return [
        {
            "id": cls.id,
            "name": cls.name,
            "description": cls.description,
            "default_timeframes": cls.default_timeframes,
        }
        for cls in list_strategies()
    ]


@router.post("/backtest/run", response_model=BacktestResult)
def run_backtest(
    req: BacktestRequest,
    db: Session = Depends(get_db),
) -> BacktestResult:
    """
    Stratejiyi geçmiş mum verisi üzerinde simüle et.

    - Bitget API anahtarı yoksa hata döner (mum verisine erişim gerekir).
    - `candle_limit` kadar geçmiş mum çekilir; ısınma periyodu için
      ilk 50 mum sinyal üretiminde kullanılmaz.
    """
    cred = (
        db.query(ApiCredentials)
        .filter_by(provider="bitget", is_active=True)
        .first()
    )
    svc = get_market_service(db, credentials=cred)

    try:
        candles = svc.get_candles(
            req.symbol, timeframe=req.timeframe, limit=req.candle_limit
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Mum verisi alınamadı: {e}")

    if not candles:
        raise HTTPException(
            status_code=400,
            detail="Mum verisi boş — sembolü ve zaman dilimini kontrol et.",
        )

    bt = Backtester()
    return bt.run(req, candles)
