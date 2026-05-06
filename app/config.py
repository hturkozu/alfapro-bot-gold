"""
Ortam değişkenlerinden uygulama ayarlarını yükler.

`.env` dosyası varsa otomatik okunur. Her ayar `ALFAPRO_` ön eki veya
doğrudan isimle tanımlanabilir; bkz. `.env.example`.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Uygulama genel ayarları."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Şifreleme ---
    alfapro_master_key: str = Field(
        ...,
        description="Fernet master key. `scripts/generate_master_key.py` ile üretilir.",
    )

    # --- Uygulama ---
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_debug: bool = True

    # --- Veritabanı ---
    database_url: str = f"sqlite:///{PROJECT_ROOT / 'data' / 'alfapro.db'}"

    # --- Log ---
    log_level: str = "INFO"
    log_dir: Path = PROJECT_ROOT / "logs"

    # --- Bitget (.env'de girilirse ilk kurulumda yüklenir) ---
    bitget_api_key: str = ""
    bitget_api_secret: str = ""
    bitget_passphrase: str = ""
    bitget_sandbox: bool = False

    # --- AI (Faz 4) ---
    anthropic_api_key: str = ""

    # --- Paper trading komisyonu (Bitget USDT-M default taker = %0.06) ---
    # Yüzde cinsinden; 0.06 → notional'ın binde 0.6'sı kadar fee.
    paper_taker_fee_pct: float = 0.06

    # --- Break-even & trailing stop (paper) ---
    # Fiyat TP mesafesinin bu yüzdesine ulaştığında SL entry'ye taşınır.
    # 0 → kapalı. Tipik: 50 (yarı yola ulaşınca BE).
    paper_breakeven_trigger_pct: float = 0.0
    # BE'ye taşınırken entry üstü/altı offset (fee tamponu, fiyat yüzdesi).
    paper_breakeven_offset_pct: float = 0.06
    # Yüzde tabanlı trailing stop. 0 → kapalı.
    # Long: SL = max(SL, peak × (1 - x/100)); short: tersi.
    paper_trailing_pct: float = 0.0

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def has_bitget_env_creds(self) -> bool:
        """.env üzerinden Bitget kimlik bilgisi sağlanmış mı?"""
        return bool(
            self.bitget_api_key
            and self.bitget_api_secret
            and self.bitget_passphrase
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Tek sefer yüklenip cache'lenen ayar nesnesi."""
    return Settings()
