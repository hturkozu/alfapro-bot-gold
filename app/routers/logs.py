"""
Log + İstatistik endpoint'leri (Faz 5).

- GET /logs/files       : Log dosya meta bilgisi
- GET /logs/tail        : Son N satır, filtreli
- GET /stats/summary    : İşlem geçmişi agregat istatistik
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.log_reader import log_files_info, read_tail
from app.services.trade_stats import compute_stats


router = APIRouter(tags=["logs"])


@router.get("/logs/files")
def files_info() -> dict:
    """Log dosyası meta bilgisi (varlık, boyut)."""
    return log_files_info()


@router.get("/logs/tail")
def logs_tail(
    which: str = Query("alfapro", pattern="^(alfapro|trades)$"),
    limit: int = Query(200, ge=1, le=2000),
    level: str | None = Query(None),
    contains: str | None = Query(None),
) -> dict:
    """Son N log satırı, filtreli."""
    lines = read_tail(
        which=which,  # type: ignore[arg-type]
        limit=limit,
        level=level,
        contains=contains,
    )
    return {"count": len(lines), "lines": lines}


@router.get("/stats/summary")
def stats_summary(
    mode: str | None = Query(None, pattern="^(paper|live)$"),
    strategy_id: str | None = Query(None),
    db: Session = Depends(get_db),
) -> dict:
    """İşlem geçmişi agregat istatistik."""
    return compute_stats(db, mode=mode, strategy_id=strategy_id)
