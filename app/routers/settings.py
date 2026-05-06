"""
Ayarlar endpoint'leri — API kimlik bilgisi yönetimi.

- POST /settings/credentials     : yeni / güncelle
- GET  /settings/credentials     : mevcutları listele (maskeli)
- POST /settings/credentials/test: canlı bağlantı testi
- DELETE /settings/credentials/{id}: sil
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from loguru import logger
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.api_credentials import ApiCredentials
from app.schemas.credentials import (
    ConnectionTestResult,
    CredentialsCreate,
    CredentialsOut,
)
from app.services.bitget_client import BitgetClient, get_bitget_client


router = APIRouter(prefix="/settings", tags=["settings"])


def _to_out(cred: ApiCredentials) -> CredentialsOut:
    """Maskeli DTO."""
    masked = cred.mask_preview()
    return CredentialsOut(
        id=cred.id,
        provider=cred.provider,
        label=cred.label,
        is_active=cred.is_active,
        sandbox=cred.sandbox,
        api_key_masked=masked["apiKey"],
        secret_masked=masked["secret"],
        has_passphrase=bool(masked["password"]),
        created_at=cred.created_at,
        updated_at=cred.updated_at,
    )


@router.get("/credentials", response_model=list[CredentialsOut])
def list_credentials(db: Session = Depends(get_db)) -> list[CredentialsOut]:
    rows = db.query(ApiCredentials).order_by(ApiCredentials.id.desc()).all()
    return [_to_out(r) for r in rows]


@router.post(
    "/credentials",
    response_model=CredentialsOut,
    status_code=status.HTTP_201_CREATED,
)
def upsert_credentials(
    payload: CredentialsCreate,
    db: Session = Depends(get_db),
) -> CredentialsOut:
    """
    Aynı (provider, label) zaten varsa günceller; yoksa ekler.
    """
    existing: ApiCredentials | None = (
        db.query(ApiCredentials)
        .filter_by(provider=payload.provider, label=payload.label)
        .one_or_none()
    )

    new_cred = ApiCredentials.from_plaintext(
        provider=payload.provider,
        api_key=payload.api_key,
        api_secret=payload.api_secret,
        passphrase=payload.passphrase,
        label=payload.label,
        sandbox=payload.sandbox,
    )

    if existing is not None:
        existing.api_key_enc = new_cred.api_key_enc
        existing.api_secret_enc = new_cred.api_secret_enc
        existing.passphrase_enc = new_cred.passphrase_enc
        existing.sandbox = payload.sandbox
        existing.is_active = True
        db.commit()
        db.refresh(existing)
        logger.info(
            "API credentials updated: provider={}, label={}",
            existing.provider,
            existing.label,
        )
        # Singleton client'ı yeni credentials ile yenile
        get_bitget_client(existing)
        return _to_out(existing)

    db.add(new_cred)
    db.commit()
    db.refresh(new_cred)
    logger.info(
        "API credentials created: provider={}, label={}",
        new_cred.provider,
        new_cred.label,
    )
    get_bitget_client(new_cred)
    return _to_out(new_cred)


@router.delete(
    "/credentials/{cred_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_credentials(cred_id: int, db: Session = Depends(get_db)) -> Response:
    cred = db.query(ApiCredentials).filter_by(id=cred_id).one_or_none()
    if cred is None:
        raise HTTPException(status_code=404, detail="Kimlik bilgisi bulunamadı")
    db.delete(cred)
    db.commit()
    logger.info("API credentials deleted: id={}", cred_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/credentials/test", response_model=ConnectionTestResult)
def test_connection(
    cred_id: int | None = None,
    db: Session = Depends(get_db),
) -> ConnectionTestResult:
    """
    Bağlantı testi. cred_id verilmezse aktif ilk Bitget credential kullanılır.
    Hiç credential yoksa sadece public erişim denenir.
    """
    cred: ApiCredentials | None = None
    if cred_id is not None:
        cred = db.query(ApiCredentials).filter_by(id=cred_id).one_or_none()
        if cred is None:
            raise HTTPException(status_code=404, detail="Kimlik bilgisi bulunamadı")
    else:
        cred = (
            db.query(ApiCredentials)
            .filter_by(provider="bitget", is_active=True)
            .order_by(ApiCredentials.id.desc())
            .first()
        )

    client = BitgetClient(cred)  # Tek seferlik, singleton'ı kirletmiyoruz
    result = client.test_connection()
    logger.info(
        "Bitget bağlantı testi: ok={} latency={}ms",
        result.ok,
        result.latency_ms,
    )
    return result
