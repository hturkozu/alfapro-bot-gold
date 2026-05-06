"""
Piyasa verisi servisi.

- Bitget'ten OHLCV çeker
- SQLite'ta cache'ler (son N mum, timeframe başına)
- Sembol listesi ve ticker sağlar

Strateji: Her `get_candles` çağrısında en güncel N mum çekilir (Bitget'in
son mumu zaten güncellenebilir olduğu için), eski mumların zaten cache'te
olmasına güvenilir.
"""
from __future__ import annotations

from typing import Any

from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models.api_credentials import ApiCredentials
from app.models.candle import Candle
from app.services.bitget_client import BitgetClient, get_bitget_client


# timeframe → milisaniye
TF_MS: dict[str, int] = {
    "1m":  60_000,
    "5m":  300_000,
    "15m": 900_000,
    "1h":  3_600_000,
    "4h":  14_400_000,
    "1d":  86_400_000,
}

# Cache'te timeframe başına tutulacak max mum sayısı
MAX_CACHED_CANDLES = 1000


class MarketDataService:
    def __init__(self, db: Session, client: BitgetClient | None = None) -> None:
        self.db = db
        self.client = client or get_bitget_client()
        self._markets_cache: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Semboller
    # ------------------------------------------------------------------

    def list_usdt_swap_symbols(self, limit: int = 200) -> list[dict[str, Any]]:
        """USDT-M perpetual sembollerini döner."""
        markets = self.client.exchange.load_markets()
        result: list[dict[str, Any]] = []
        for symbol, m in markets.items():
            if not m.get("active"):
                continue
            if m.get("type") != "swap":
                continue
            if m.get("quote") != "USDT":
                continue
            result.append(
                {
                    "symbol": symbol,
                    "base": m.get("base", ""),
                    "quote": m.get("quote", ""),
                    "type": m.get("type", ""),
                    "active": bool(m.get("active")),
                }
            )
            if len(result) >= limit:
                break
        return result

    # ------------------------------------------------------------------
    # Mumlar
    # ------------------------------------------------------------------

    def get_candles(
        self,
        symbol: str,
        timeframe: str = "1m",
        limit: int = 300,
        use_cache: bool = True,
    ) -> list[list[float]]:
        """
        Son `limit` mumu döndürür (artan ts sırasıyla).

        Öncelik: Bitget'ten her zaman son `limit` mum çekilir,
        cache'e merge edilir. Bu sayede son (açık) mum daima taze olur.
        """
        if timeframe not in TF_MS:
            raise ValueError(f"Geçersiz timeframe: {timeframe}")

        symbol = self._resolve_symbol(symbol)

        # 1) Borsa'dan çek
        rows = self._fetch_from_exchange(symbol, timeframe, limit)

        # 2) Cache'e yaz (varsa güncelle)
        if use_cache and rows:
            self._upsert_candles(symbol, timeframe, rows)
            self._trim_cache(symbol, timeframe)

        return rows

    def get_cached_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 300,
    ) -> list[list[float]]:
        """Sadece cache'ten oku. (Debug/offline senaryo)."""
        q = (
            self.db.query(Candle)
            .filter(Candle.symbol == symbol, Candle.timeframe == timeframe)
            .order_by(Candle.ts.desc())
            .limit(limit)
        )
        return [c.to_row() for c in reversed(q.all())]

    # ------------------------------------------------------------------
    # Ticker
    # ------------------------------------------------------------------

    def get_ticker_summary(self, symbol: str) -> dict[str, float | None]:
        """Son fiyat + 24 saatlik değişim."""
        try:
            symbol = self._resolve_symbol(symbol)
            t = self.client.fetch_ticker(symbol)
            return {
                "last": _f(t.get("last")),
                "percentage": _f(t.get("percentage")),
                "baseVolume": _f(t.get("baseVolume")),
                "quoteVolume": _f(t.get("quoteVolume")),
                "high": _f(t.get("high")),
                "low": _f(t.get("low")),
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("Ticker alınamadı ({}): {}", symbol, e)
            return {
                "last": None,
                "percentage": None,
                "baseVolume": None,
                "quoteVolume": None,
                "high": None,
                "low": None,
            }

    # ------------------------------------------------------------------
    # İç yardımcılar
    # ------------------------------------------------------------------

    def _load_markets_cached(self) -> dict[str, Any]:
        if self._markets_cache is None:
            self._markets_cache = self.client.exchange.load_markets()
        return self._markets_cache

    def _resolve_symbol(self, symbol: str) -> str:
        """
        Kullanıcı/konfig'den gelen sembolü CCXT'in beklediği formatta normalize eder.

        Örn:
        - doge  -> DOGE/USDT:USDT (swap)
        - xlm   -> XLM/USDT:USDT
        - btc/usdt:usdt -> BTC/USDT:USDT
        """
        raw = (symbol or "").strip()
        if not raw:
            return raw

        markets = self._load_markets_cached()
        if raw in markets:
            return raw

        # Case-normalize dene
        if "/" in raw:
            parts = raw.split("/")
            base = parts[0].strip().upper()
            rest = "/".join(parts[1:]).strip().upper()
            cand = f"{base}/{rest}"
            if cand in markets:
                return cand

        # Kısa sembol (doge, xlm, btc...) → USDT swap varsay
        if "/" not in raw:
            base = raw.upper()
            candidates = [
                f"{base}/USDT:USDT",  # Bitget linear swap (ccxt)
                f"{base}/USDT",       # bazı borsalar
            ]
            for cand in candidates:
                if cand in markets:
                    return cand

        return raw

    def _fetch_from_exchange(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
    ) -> list[list[float]]:
        """Bitget'ten ham OHLCV çeker."""
        try:
            rows = self.client.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            logger.debug(
                "Fetched {} candles: {} {}", len(rows), symbol, timeframe
            )
            return rows
        except Exception as e:  # noqa: BLE001
            logger.error("OHLCV fetch hatası {} {}: {}", symbol, timeframe, e)
            # Borsa erişilemezse cache'e düş
            cached = self.get_cached_candles(symbol, timeframe, limit)
            if cached:
                logger.info("Cache'ten {} mum dönüldü", len(cached))
                return cached
            raise

    def _upsert_candles(
        self,
        symbol: str,
        timeframe: str,
        rows: list[list[float]],
    ) -> None:
        """
        ccxt satırlarını [ts,o,h,l,c,v] cache'e yazar.
        Aynı (symbol,tf,ts) varsa günceller.
        """
        if not rows:
            return

        records = [
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "ts": int(r[0]),
                "open": float(r[1]),
                "high": float(r[2]),
                "low": float(r[3]),
                "close": float(r[4]),
                "volume": float(r[5]),
            }
            for r in rows
        ]

        stmt = sqlite_insert(Candle).values(records)
        stmt = stmt.on_conflict_do_update(
            index_elements=["symbol", "timeframe", "ts"],
            set_={
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
            },
        )
        self.db.execute(stmt)
        self.db.commit()

    def _trim_cache(self, symbol: str, timeframe: str) -> None:
        """Her timeframe için en eski mumları budar."""
        subq = (
            self.db.query(Candle.id)
            .filter(Candle.symbol == symbol, Candle.timeframe == timeframe)
            .order_by(Candle.ts.desc())
            .offset(MAX_CACHED_CANDLES)
            .subquery()
        )
        self.db.execute(delete(Candle).where(Candle.id.in_(select(subq.c.id))))
        self.db.commit()


def _f(v: Any) -> float | None:
    """None-safe float dönüştürücü."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def get_market_service(
    db: Session,
    credentials: ApiCredentials | None = None,
) -> MarketDataService:
    """Router dependency yardımcısı."""
    client = get_bitget_client(credentials)
    return MarketDataService(db, client)
