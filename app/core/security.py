"""
Simetrik şifreleme servisi (Fernet).

API anahtarları, passphrase gibi hassas alanlar DB'ye yazılmadan
önce burada şifrelenir, okunurken de burada çözülür.
"""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


class EncryptionError(Exception):
    """Şifreleme/çözme başarısız."""


class CryptoService:
    """Fernet sarmalayıcı — şifrele / çöz."""

    def __init__(self, master_key: str) -> None:
        if not master_key:
            raise EncryptionError(
                "ALFAPRO_MASTER_KEY boş. "
                "`python scripts/generate_master_key.py` çalıştır ve .env'e ekle."
            )
        try:
            self._fernet = Fernet(master_key.encode())
        except (ValueError, TypeError) as e:
            raise EncryptionError(
                f"Geçersiz master key formatı: {e}. "
                "Key Fernet formatında olmalı (base64, 44 karakter)."
            ) from e

    def encrypt(self, plaintext: str) -> str:
        """Açık metin → şifreli string (base64)."""
        if plaintext is None:
            return ""
        token = self._fernet.encrypt(plaintext.encode("utf-8"))
        return token.decode("utf-8")

    def decrypt(self, token: str) -> str:
        """Şifreli string → açık metin."""
        if not token:
            return ""
        try:
            return self._fernet.decrypt(token.encode("utf-8")).decode("utf-8")
        except InvalidToken as e:
            raise EncryptionError(
                "Şifre çözülemedi. Master key değişmiş olabilir."
            ) from e


_crypto_singleton: CryptoService | None = None


def get_crypto() -> CryptoService:
    """Uygulama boyunca paylaşılan CryptoService örneği."""
    global _crypto_singleton
    if _crypto_singleton is None:
        settings = get_settings()
        _crypto_singleton = CryptoService(settings.alfapro_master_key)
    return _crypto_singleton
