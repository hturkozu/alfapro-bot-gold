"""
Emtia (commodity) sembol yardımcıları.

Bitget USDT-M perpetual evreninde "klasik" kripto dışı kontratları
kategorilere ayırır:
    - Metals:    XAU, XAG, PAXG, XAUT (altın/gümüş)
    - Energy:    WTI, BRENT, CRUDE, OIL (petrol)
    - Indices:   US500, NAS100, SPX gibi TradFi endeksler (varsa)
    - Stocks:    NVDA, AAPL, TSLA gibi hisse perpetual'ları (varsa)

Kategoriler symbol string'inin base kısmına bakılarak atanır.
`fetch_markets()` çıktısı kullanıcının API erişimine bağlı olduğundan
dinamik — liste sabit değil.
"""
from __future__ import annotations

from typing import Any

from loguru import logger


# Kategori → baz sembol prefix/ifadeleri (hepsi büyük harf eşleştirilir)
METAL_BASES = {"XAU", "XAG", "PAXG", "XAUT"}
ENERGY_KEYWORDS = {"OIL", "WTI", "BRENT", "CRUDE", "NATGAS"}
INDEX_KEYWORDS = {"SPX", "NAS100", "NAS", "US500", "US30", "DAX", "UK100"}
# Hisseler için geniş bir tanınmış set (eksik kalabilir; fallback var)
STOCK_BASES = {
    "AAPL", "NVDA", "TSLA", "MSFT", "GOOG", "GOOGL", "AMZN", "META",
    "NFLX", "COIN", "MSTR", "AMD", "INTC", "PLTR", "UBER",
}


def categorize_symbol(base: str, symbol_id: str = "") -> str:
    """
    Tek sembol için kategori ataması döndürür.
    Kategori: "crypto" | "metal" | "energy" | "index" | "stock"
    """
    b = (base or "").upper()
    s = (symbol_id or "").upper()

    if b in METAL_BASES:
        return "metal"
    if any(k in b or k in s for k in ENERGY_KEYWORDS):
        return "energy"
    if b in INDEX_KEYWORDS or any(k in s for k in INDEX_KEYWORDS):
        return "index"
    if b in STOCK_BASES:
        return "stock"
    return "crypto"


def group_markets(markets: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """
    ccxt markets dict'ini al, kategoriye göre grupla.

    Dönüş: {"crypto": [...], "metal": [...], "energy": [...], ...}
    Her eleman: {symbol, base, quote, category, active, raw_id}
    """
    groups: dict[str, list[dict[str, Any]]] = {
        "crypto": [], "metal": [], "energy": [],
        "index": [], "stock": [],
    }

    for ccxt_symbol, m in markets.items():
        if not m.get("active"):
            continue
        if m.get("type") != "swap":
            continue
        if m.get("quote") != "USDT":
            continue

        base = m.get("base", "") or ""
        raw_id = m.get("id", "") or ""
        cat = categorize_symbol(base, raw_id)

        groups[cat].append({
            "symbol": ccxt_symbol,
            "base": base,
            "quote": m.get("quote", ""),
            "category": cat,
            "active": True,
            "raw_id": raw_id,
        })

    for cat in groups:
        groups[cat].sort(key=lambda x: x["base"])

    logger.debug(
        "Market grouping: crypto={}, metal={}, energy={}, index={}, stock={}",
        len(groups["crypto"]), len(groups["metal"]),
        len(groups["energy"]), len(groups["index"]),
        len(groups["stock"]),
    )
    return groups
