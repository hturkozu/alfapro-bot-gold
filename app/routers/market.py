"""
Market data endpoint'leri.

- GET /market/symbols         : USDT-M perpetual semboller
- GET /market/candles/{sym}   : OHLCV (grafik için)
- GET /market/ticker/{sym}    : Son fiyat / 24h değişim
- GET /market/indicators/{sym}: İndikatör serileri
- GET /market/analysis/{sym}  : Hepsi bir arada (panel dashboard için)
"""
from __future__ import annotations

from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.api_credentials import ApiCredentials
from app.schemas.market import (
    CandleOut,
    CandlesResponse,
    IndicatorRequest,
    MarketAnalysis,
    SymbolInfo,
)
from app.services.fibonacci import compute_fibonacci
from app.services.indicators import compute_indicators
from app.services.market_data import MarketDataService, get_market_service
from app.services.smc import compute_smc


router = APIRouter(prefix="/market", tags=["market"])


# ----------------------------------------------------------------------
# Dependency
# ----------------------------------------------------------------------

def _get_service(db: Session = Depends(get_db)) -> MarketDataService:
    """Aktif bir Bitget credential varsa onu al, yoksa public client ile dön."""
    active = (
        db.query(ApiCredentials)
        .filter_by(provider="bitget", is_active=True)
        .order_by(ApiCredentials.id.desc())
        .first()
    )
    return get_market_service(db, credentials=active)


def _decode_symbol(symbol: str) -> str:
    """URL-encoded sembolü çöz (BTC%2FUSDT%3AUSDT → BTC/USDT:USDT)."""
    return unquote(symbol)


# ----------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------

@router.get("/symbols", response_model=list[SymbolInfo])
def list_symbols(
    limit: int = Query(200, ge=1, le=1000),
    service: MarketDataService = Depends(_get_service),
) -> list[SymbolInfo]:
    """USDT-M perpetual sembolleri."""
    try:
        items = service.list_usdt_swap_symbols(limit=limit)
        return [SymbolInfo(**it) for it in items]
    except Exception as e:  # noqa: BLE001
        logger.error("Sembol listesi alınamadı: {}", e)
        raise HTTPException(status_code=503, detail=f"Bitget erişilemez: {e}") from e


@router.get("/symbols/grouped")
def list_symbols_grouped(
    service: MarketDataService = Depends(_get_service),
) -> dict[str, list[dict]]:
    """
    Sembolleri kategoriye göre grupla: crypto / metal / energy / index / stock.
    Emtia (altın/gümüş/petrol) sekmesi için kullanılır.
    """
    from app.services.commodity_catalog import group_markets
    try:
        markets = service.client.exchange.load_markets()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Bitget erişilemez: {e}") from e
    return group_markets(markets)


@router.get("/ticker/{symbol:path}")
def ticker(
    symbol: str,
    service: MarketDataService = Depends(_get_service),
) -> dict:
    return service.get_ticker_summary(_decode_symbol(symbol))


@router.get("/candles/{symbol:path}", response_model=CandlesResponse)
def candles(
    symbol: str,
    tf: str = Query("1m", description="1m|5m|15m|1h|4h|1d"),
    limit: int = Query(300, ge=10, le=1000),
    service: MarketDataService = Depends(_get_service),
) -> CandlesResponse:
    sym = _decode_symbol(symbol)
    try:
        rows = service.get_candles(sym, timeframe=tf, limit=limit)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Mum çekilemedi: {e}") from e

    return CandlesResponse(
        symbol=sym,
        timeframe=tf,
        count=len(rows),
        candles=[_row_to_candle(r) for r in rows],
    )


@router.get("/analysis/{symbol:path}", response_model=MarketAnalysis)
def analysis(
    symbol: str,
    tf: str = Query("15m"),
    limit: int = Query(300, ge=50, le=1000),
    ema_periods: str = Query("9,21,50,200", description="Virgülle ayrılmış"),
    service: MarketDataService = Depends(_get_service),
) -> MarketAnalysis:
    """
    Dashboard için hepsi-bir-arada analiz:
    mumlar + indikatörler + fibonacci + SMC + ticker özeti.
    """
    sym = _decode_symbol(symbol)

    # Mumlar
    try:
        rows = service.get_candles(sym, timeframe=tf, limit=limit)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Mum çekilemedi: {e}") from e

    if not rows:
        raise HTTPException(status_code=404, detail="Mum verisi boş")

    # Parametreler
    try:
        periods = [int(p.strip()) for p in ema_periods.split(",") if p.strip()]
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail=f"Geçersiz ema_periods: {e}"
        ) from e

    params = IndicatorRequest(ema_periods=periods)

    # İndikatörler
    ind_last, ind_series = compute_indicators(rows, params)

    # Fibonacci
    fib = compute_fibonacci(rows, lookback=min(limit, 100))

    # SMC
    smc = compute_smc(rows)

    # Ticker özeti
    ticker_info = service.get_ticker_summary(sym)
    last_price = ticker_info.get("last") or float(rows[-1][4])
    change_24h = ticker_info.get("percentage")
    vol_24h = ticker_info.get("quoteVolume")

    return MarketAnalysis(
        symbol=sym,
        timeframe=tf,
        last_price=last_price,
        change_24h_pct=change_24h,
        volume_24h=vol_24h,
        candles=[_row_to_candle(r) for r in rows],
        indicators_last=ind_last,
        indicators_series=ind_series,
        fibonacci=fib,
        smc=smc,
    )


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _row_to_candle(r: list[float]) -> CandleOut:
    return CandleOut(
        ts=int(r[0]),
        open=float(r[1]),
        high=float(r[2]),
        low=float(r[3]),
        close=float(r[4]),
        volume=float(r[5]),
    )
