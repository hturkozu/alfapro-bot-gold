"""
API kimlik bilgisi için request/response şemaları.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


Provider = Literal["bitget"]  # İleride: "binance", "bybit" eklenebilir


class CredentialsCreate(BaseModel):
    """Yeni API anahtarı ekleme / güncelleme gövdesi."""

    provider: Provider = "bitget"
    label: str = Field(default="default", max_length=64)
    api_key: str = Field(min_length=8, max_length=256)
    api_secret: str = Field(min_length=8, max_length=256)
    passphrase: str = Field(default="", max_length=256)
    sandbox: bool = False


class CredentialsOut(BaseModel):
    """Panele gönderilen güvenli gösterim — maskelenmiş."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: str
    label: str
    is_active: bool
    sandbox: bool
    api_key_masked: str
    secret_masked: str
    has_passphrase: bool
    created_at: datetime
    updated_at: datetime


class ConnectionTestResult(BaseModel):
    """Borsa bağlantı testi sonucu."""

    ok: bool
    provider: str
    message: str
    server_time_ms: int | None = None
    balances: dict[str, float] | None = None
    latency_ms: int | None = None
