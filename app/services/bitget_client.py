"""
Bitget borsa istemcisi — ccxt üzerinden sarmalayıcı.

Faz 1: sadece bağlantı testi ve temel market verisi.
Faz 3+ : emir gönderme, pozisyon takibi buraya eklenecek.
"""
from __future__ import annotations

import time
from typing import Any

import ccxt
from loguru import logger

from app.models.api_credentials import ApiCredentials
from app.schemas.credentials import ConnectionTestResult


class BitgetClient:
    """
    ccxt.bitget sarmalayıcısı.

    Her çağrıda yeni bir ccxt instance oluşturmak yerine, lazy
    olarak bir kez kurulur ve yeniden kullanılır. Credentials
    değişirse `refresh()` çağrılır.
    """

    def __init__(self, credentials: ApiCredentials | None = None) -> None:
        self._creds = credentials
        self._exchange: ccxt.bitget | None = None

    # ------------------------------------------------------------------
    # Yaşam döngüsü
    # ------------------------------------------------------------------

    def _build_exchange(self) -> ccxt.bitget:
        """ccxt.bitget örneği kur. Credentials varsa private erişim açılır."""
        config: dict[str, Any] = {
            "enableRateLimit": True,
            "options": {
                # USDT-M perpetual futures varsayılan
                "defaultType": "swap",
                "defaultSubType": "linear",
            },
            "timeout": 20_000,
        }

        if self._creds is not None:
            plain = self._creds.decrypt()
            config.update(
                {
                    "apiKey": plain["apiKey"],
                    "secret": plain["secret"],
                    "password": plain["password"],
                }
            )
            if self._creds.sandbox:
                # Bitget'te resmi testnet kullanımı sınırlı;
                # True iken ccxt sandbox moduna alınır.
                config["options"]["sandboxMode"] = True

        exchange = ccxt.bitget(config)
        if self._creds is not None and self._creds.sandbox:
            try:
                exchange.set_sandbox_mode(True)
            except Exception as e:  # noqa: BLE001
                logger.warning("Sandbox modu açılamadı: {}", e)
        return exchange

    @property
    def exchange(self) -> ccxt.bitget:
        if self._exchange is None:
            self._exchange = self._build_exchange()
        return self._exchange

    def refresh(self, credentials: ApiCredentials | None) -> None:
        """Kimlik bilgisi değiştiyse instance'ı sıfırla."""
        self._creds = credentials
        self._exchange = None

    # ------------------------------------------------------------------
    # Yüksek seviye işlemler
    # ------------------------------------------------------------------

    def test_connection(self) -> ConnectionTestResult:
        """
        Hem public (sunucu saati) hem — credentials varsa — private
        (bakiye) uç noktayı dener. Detaylı rapor döner.
        """
        start = time.monotonic()
        try:
            # Public: sunucu saati
            server_time_ms = self.exchange.fetch_time()
            public_ok = True
        except Exception as e:  # noqa: BLE001
            logger.error("Bitget public bağlantı testi başarısız: {}", e)
            return ConnectionTestResult(
                ok=False,
                provider="bitget",
                message=f"Public erişim başarısız: {e}",
            )

        balances: dict[str, float] | None = None
        if self._creds is not None:
            try:
                # Private: USDT-M futures bakiyesi
                bal = self.exchange.fetch_balance(params={"type": "swap"})
                balances = {
                    "USDT_total": float(bal.get("USDT", {}).get("total", 0) or 0),
                    "USDT_free": float(bal.get("USDT", {}).get("free", 0) or 0),
                    "USDT_used": float(bal.get("USDT", {}).get("used", 0) or 0),
                }
            except ccxt.AuthenticationError as e:
                return ConnectionTestResult(
                    ok=False,
                    provider="bitget",
                    message=(
                        "Kimlik doğrulama başarısız. API key / secret / "
                        f"passphrase'i kontrol et. Detay: {e}"
                    ),
                    server_time_ms=server_time_ms,
                )
            except ccxt.PermissionDenied as e:
                return ConnectionTestResult(
                    ok=False,
                    provider="bitget",
                    message=(
                        "Yetki hatası. API anahtarında 'Futures Trade' "
                        f"yetkisinin açık olduğundan emin ol. Detay: {e}"
                    ),
                    server_time_ms=server_time_ms,
                )
            except Exception as e:  # noqa: BLE001
                return ConnectionTestResult(
                    ok=False,
                    provider="bitget",
                    message=f"Bakiye alınamadı: {e}",
                    server_time_ms=server_time_ms,
                )

        latency_ms = int((time.monotonic() - start) * 1000)
        msg = (
            "Hem public hem private uç noktalar çalışıyor."
            if balances is not None
            else "Public erişim OK. Kimlik bilgisi girilmediği için private test atlandı."
        )
        return ConnectionTestResult(
            ok=True,
            provider="bitget",
            message=msg,
            server_time_ms=server_time_ms,
            balances=balances,
            latency_ms=latency_ms,
        )

    def fetch_ticker(self, symbol: str) -> dict[str, Any]:
        """Tek sembol için son fiyat/hacim bilgisi (Faz 2'de kullanılacak)."""
        return self.exchange.fetch_ticker(symbol)

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1m",
        limit: int = 200,
    ) -> list[list[float]]:
        """OHLCV mum verisi (Faz 2'de kullanılacak)."""
        return self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)


# ----------------------------------------------------------------------
# Singleton erişim
# ----------------------------------------------------------------------

_client_singleton: BitgetClient | None = None


def get_bitget_client(credentials: ApiCredentials | None = None) -> BitgetClient:
    """
    Paylaşılan BitgetClient. Credentials parametresi geçilirse
    mevcut instance yenilenir.
    """
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = BitgetClient(credentials)
    elif credentials is not None:
        _client_singleton.refresh(credentials)
    return _client_singleton
