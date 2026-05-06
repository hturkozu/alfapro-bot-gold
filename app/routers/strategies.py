"""
Strateji endpoint'leri:

- GET  /strategies              : Kayıtlı stratejileri listele (meta + mevcut config)
- GET  /strategies/{id}/config  : Tek strateji konfigürasyonu
- POST /strategies/{id}/config  : Konfigürasyonu güncelle
- POST /strategies/{id}/evaluate/{symbol}?tf=15m : Tek sefer değerlendir, sinyal var mı?
"""
from __future__ import annotations

from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.api_credentials import ApiCredentials
from app.models.strategy_config import StrategyConfig
from app.schemas.trading import (
    StrategyConfigOut,
    StrategyConfigUpdate,
    StrategyEvaluateResult,
    StrategyInfo,
)
from app.services.fibonacci import compute_fibonacci
from app.services.indicators import compute_indicators
from app.services.market_data import get_market_service
from app.services.smc import compute_smc
from app.services.strategies import get_strategy, list_strategies, strategy_info
from app.services.strategies.base import StrategyContext


router = APIRouter(prefix="/strategies", tags=["strategies"])


# ----------------------------------------------------------------------
# Yardımcı
# ----------------------------------------------------------------------

def _get_or_create_config(db: Session, strategy_id: str) -> StrategyConfig:
    """Konfigürasyon yoksa default ile oluştur."""
    cfg = db.query(StrategyConfig).filter_by(strategy_id=strategy_id).one_or_none()
    if cfg is not None:
        return cfg

    # Yeni: strateji meta bilgisini al
    strat_cls = next((s for s in list_strategies() if s.id == strategy_id), None)
    if strat_cls is None:
        raise HTTPException(status_code=404, detail=f"Strateji bulunamadı: {strategy_id}")

    cfg = StrategyConfig(
        strategy_id=strategy_id,
        enabled=False,
        size_usdt=10.0,
        leverage=5,
    )
    cfg.symbols_list = []
    cfg.timeframes_list = list(strat_cls.default_timeframes)
    cfg.params = dict(strat_cls.default_params)
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return cfg


def _cfg_to_out(cfg: StrategyConfig) -> StrategyConfigOut:
    return StrategyConfigOut(
        strategy_id=cfg.strategy_id,
        enabled=cfg.enabled,
        symbols=cfg.symbols_list,
        timeframes=cfg.timeframes_list,
        params=cfg.params,
        size_usdt=cfg.size_usdt,
        leverage=cfg.leverage,
        updated_at=cfg.updated_at,
    )


# ----------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------

@router.get("", response_model=list[StrategyInfo])
def list_strategy_info() -> list[StrategyInfo]:
    """Kayıtlı tüm strateji sınıflarının meta bilgisi."""
    return [strategy_info(cls) for cls in list_strategies()]


@router.get("/{strategy_id}/config", response_model=StrategyConfigOut)
def get_config(
    strategy_id: str,
    db: Session = Depends(get_db),
) -> StrategyConfigOut:
    cfg = _get_or_create_config(db, strategy_id)
    return _cfg_to_out(cfg)


@router.post("/{strategy_id}/config", response_model=StrategyConfigOut)
def update_config(
    strategy_id: str,
    payload: StrategyConfigUpdate,
    db: Session = Depends(get_db),
) -> StrategyConfigOut:
    cfg = _get_or_create_config(db, strategy_id)

    if payload.enabled is not None:
        cfg.enabled = payload.enabled
    if payload.symbols is not None:
        cfg.symbols_list = payload.symbols
    if payload.timeframes is not None:
        cfg.timeframes_list = payload.timeframes
    if payload.params is not None:
        # Parametreleri merge: varsayılanı koru, gelenleri üzerine yaz
        merged = dict(cfg.params)
        merged.update(payload.params)
        cfg.params = merged
    if payload.size_usdt is not None:
        cfg.size_usdt = payload.size_usdt
    if payload.leverage is not None:
        cfg.leverage = payload.leverage

    db.commit()
    db.refresh(cfg)
    return _cfg_to_out(cfg)


@router.post("/{strategy_id}/evaluate/{symbol:path}", response_model=StrategyEvaluateResult)
def evaluate_once(
    strategy_id: str,
    symbol: str,
    tf: str = Query("15m"),
    limit: int = Query(300, ge=50, le=1000),
    db: Session = Depends(get_db),
) -> StrategyEvaluateResult:
    """
    Tek sefer değerlendirme — sinyal gelir mi görmek için.
    İşlem açmaz, sadece strateji motorunu çalıştırır.
    """
    sym = unquote(symbol)

    cred = (
        db.query(ApiCredentials).filter_by(provider="bitget", is_active=True)
        .order_by(ApiCredentials.id.desc()).first()
    )
    svc = get_market_service(db, credentials=cred)

    try:
        rows = svc.get_candles(sym, timeframe=tf, limit=limit)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Mum çekilemedi: {e}") from e

    if not rows:
        raise HTTPException(status_code=404, detail="Mum verisi boş")

    # Stratejinin parametrelerini DB'den yükle (varsa)
    cfg = db.query(StrategyConfig).filter_by(strategy_id=strategy_id).one_or_none()
    params = cfg.params if cfg else None

    try:
        strat = get_strategy(strategy_id, params=params)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    ind_last, ind_series = compute_indicators(rows)
    fib = compute_fibonacci(rows)
    smc = compute_smc(rows)

    ctx = StrategyContext(
        symbol=sym, timeframe=tf, candles=rows,
        ind_last=ind_last, ind_series=ind_series,
        fib=fib, smc=smc,
    )

    signal = strat.evaluate(ctx)

    return StrategyEvaluateResult(
        strategy_id=strategy_id,
        symbol=sym,
        timeframe=tf,
        has_signal=signal is not None,
        signal=signal,
        debug={
            "last_price": ctx.last_price,
            "trend_smc": smc.current_trend,
            "rsi": ind_last.rsi,
            "macd_hist": ind_last.macd_hist,
            "atr": ind_last.atr,
            "has_fib": fib is not None,
        },
    )
