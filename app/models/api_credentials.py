"""
API kimlik bilgileri modeli.

Her borsa/sağlayıcı için bir satır. Hassas alanlar Fernet ile
şifrelenmiş halde `_enc` sütunlarında saklanır. DB dışarı sızsa
bile master key olmadan çözülemez.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.security import get_crypto


class ApiCredentials(Base):
    __tablename__ = "api_credentials"
    __table_args__ = (UniqueConstraint("provider", "label", name="uq_provider_label"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    label: Mapped[str] = mapped_column(String(64), default="default", nullable=False)

    # Şifreli alanlar
    api_key_enc: Mapped[str] = mapped_column(String, nullable=False)
    api_secret_enc: Mapped[str] = mapped_column(String, nullable=False)
    passphrase_enc: Mapped[str] = mapped_column(String, default="", nullable=False)

    # Meta
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    sandbox: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # ------------------------------------------------------------------
    # Yardımcı metotlar
    # ------------------------------------------------------------------

    @classmethod
    def from_plaintext(
        cls,
        provider: str,
        api_key: str,
        api_secret: str,
        passphrase: str = "",
        label: str = "default",
        sandbox: bool = False,
    ) -> "ApiCredentials":
        """Açık metin kimlik bilgileriyle bir kayıt üretir (şifreleme burada)."""
        crypto = get_crypto()
        return cls(
            provider=provider,
            label=label,
            api_key_enc=crypto.encrypt(api_key),
            api_secret_enc=crypto.encrypt(api_secret),
            passphrase_enc=crypto.encrypt(passphrase),
            sandbox=sandbox,
        )

    def decrypt(self) -> dict[str, str]:
        """Saklanan şifreli alanları açık metne çevirir.

        Döndürülen dict ccxt'ye doğrudan verilebilir:
            ccxt.bitget({**creds, 'options': {...}})
        """
        crypto = get_crypto()
        return {
            "apiKey": crypto.decrypt(self.api_key_enc),
            "secret": crypto.decrypt(self.api_secret_enc),
            "password": crypto.decrypt(self.passphrase_enc),
        }

    def mask_preview(self) -> dict[str, str]:
        """Panelde göstermek için maskelenmiş önizleme (tam key ifşa etmez)."""
        creds = self.decrypt()
        return {
            "apiKey": _mask(creds["apiKey"]),
            "secret": _mask(creds["secret"]),
            "password": "***" if creds["password"] else "",
        }


def _mask(value: str) -> str:
    """İlk 4 ve son 4 karakteri göster, arası ***"""
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"
