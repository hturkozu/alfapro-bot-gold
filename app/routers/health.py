"""
Sağlık kontrolü endpoint'leri.
"""
from __future__ import annotations

from fastapi import APIRouter

from app import version_info

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict:
    """Basit hayatta olma kontrolü."""
    info = version_info()
    return {
        "ok": True,
        "service": "alfapro-bot",
        **info,
    }


@router.get("/version")
def version() -> dict:
    """Tam sürüm bilgisi — serial, kod adı, faz."""
    return version_info()
