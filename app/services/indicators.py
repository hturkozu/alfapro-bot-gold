"""
Teknik indikatör motoru.

pandas-ta-classic kullanır (TA-Lib derlemesi gerekmez).

Girdi: [ts, o, h, l, c, v] satır listesi (ccxt formatı)
Çıktı: IndicatorValues (son nokta) + IndicatorSeries (tam geçmiş)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pandas_ta_classic as ta  # noqa: F401 — df.ta extension kullanılır

from app.schemas.market import (
    IndicatorRequest,
    IndicatorSeries,
    IndicatorValues,
)


def candles_to_df(rows: list[list[float]]) -> pd.DataFrame:
    """ccxt satırlarını pandas DataFrame'e çevirir."""
    if not rows:
        return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume"])

    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = df["ts"].astype("int64")
    df["datetime"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.set_index("datetime")
    return df


def compute_indicators(
    rows: list[list[float]],
    params: IndicatorRequest | None = None,
) -> tuple[IndicatorValues, IndicatorSeries]:
    """
    Tüm indikatörleri hesapla. Hem son nokta değerleri hem de
    grafik için tam seri döner.
    """
    params = params or IndicatorRequest()
    df = candles_to_df(rows)

    if df.empty:
        return IndicatorValues(), IndicatorSeries(ts=[])

    # ---- EMA'lar ----
    ema_series: dict[str, list[float | None]] = {}
    ema_last: dict[str, float | None] = {}
    for period in params.ema_periods:
        col = f"EMA_{period}"
        df[col] = ta.ema(df["close"], length=period)
        ema_series[f"ema_{period}"] = _series_to_list(df[col])
        ema_last[f"ema_{period}"] = _last_float(df[col])

    # ---- RSI ----
    df["RSI"] = ta.rsi(df["close"], length=params.rsi_length)

    # ---- MACD ----
    macd_df = ta.macd(
        df["close"],
        fast=params.macd_fast,
        slow=params.macd_slow,
        signal=params.macd_signal,
    )
    if macd_df is not None and not macd_df.empty:
        df["MACD"] = macd_df.iloc[:, 0]
        df["MACDh"] = macd_df.iloc[:, 1]
        df["MACDs"] = macd_df.iloc[:, 2]
    else:
        df["MACD"] = df["MACDh"] = df["MACDs"] = np.nan

    # ---- ATR ----
    df["ATR"] = ta.atr(
        df["high"], df["low"], df["close"], length=params.atr_length
    )

    # ---- Bollinger ----
    bb = ta.bbands(df["close"], length=params.bb_length, std=params.bb_std)
    if bb is not None and not bb.empty:
        df["BBL"] = bb.iloc[:, 0]
        df["BBM"] = bb.iloc[:, 1]
        df["BBU"] = bb.iloc[:, 2]
    else:
        df["BBL"] = df["BBM"] = df["BBU"] = np.nan

    # ---- VWAP ----
    # pandas-ta vwap'ı tarih-endeksli DF bekler (günlük reset ile)
    try:
        # pandas-ta vwap timezone-aware index'te uyarı üretebiliyor;
        # sadece bu hesap için naive datetime index kullan.
        high = df["high"].copy()
        low = df["low"].copy()
        close = df["close"].copy()
        volume = df["volume"].copy()
        if getattr(high.index, "tz", None) is not None:
            naive_idx = high.index.tz_localize(None)
            high.index = naive_idx
            low.index = naive_idx
            close.index = naive_idx
            volume.index = naive_idx
        df["VWAP"] = ta.vwap(high, low, close, volume)
    except Exception:  # noqa: BLE001 — bazen indeks olmadığında hata verir
        df["VWAP"] = np.nan

    # ---- Stochastic RSI ----
    try:
        stochrsi_df = ta.stochrsi(df["close"], length=14, rsi_length=14, k=3, d=3)
        if stochrsi_df is not None and not stochrsi_df.empty and stochrsi_df.shape[1] >= 2:
            df["STOCH_K"] = stochrsi_df.iloc[:, 0]
            df["STOCH_D"] = stochrsi_df.iloc[:, 1]
        else:
            df["STOCH_K"] = df["STOCH_D"] = np.nan
    except Exception:  # noqa: BLE001
        df["STOCH_K"] = df["STOCH_D"] = np.nan

    # ---- Paketle ----
    last = IndicatorValues(
        ema=ema_last,
        rsi=_last_float(df["RSI"]),
        macd=_last_float(df["MACD"]),
        macd_signal=_last_float(df["MACDs"]),
        macd_hist=_last_float(df["MACDh"]),
        atr=_last_float(df["ATR"]),
        bb_upper=_last_float(df["BBU"]),
        bb_middle=_last_float(df["BBM"]),
        bb_lower=_last_float(df["BBL"]),
        vwap=_last_float(df["VWAP"]),
        stoch_k=_last_float(df["STOCH_K"]),
        stoch_d=_last_float(df["STOCH_D"]),
    )

    series = IndicatorSeries(
        ts=df["ts"].tolist(),
        ema=ema_series,
        rsi=_series_to_list(df["RSI"]),
        macd=_series_to_list(df["MACD"]),
        macd_signal=_series_to_list(df["MACDs"]),
        macd_hist=_series_to_list(df["MACDh"]),
        atr=_series_to_list(df["ATR"]),
        bb_upper=_series_to_list(df["BBU"]),
        bb_middle=_series_to_list(df["BBM"]),
        bb_lower=_series_to_list(df["BBL"]),
        vwap=_series_to_list(df["VWAP"]),
        stoch_k=_series_to_list(df["STOCH_K"]),
        stoch_d=_series_to_list(df["STOCH_D"]),
    )

    return last, series


# ----------------------------------------------------------------------
# Yardımcılar
# ----------------------------------------------------------------------

def _last_float(s: pd.Series) -> float | None:
    """Serinin son geçerli değerini döndür."""
    if s is None or s.empty:
        return None
    val = s.iloc[-1]
    if pd.isna(val):
        return None
    return float(val)


def _series_to_list(s: pd.Series) -> list[float | None]:
    """NaN → None, geri kalan float."""
    if s is None or s.empty:
        return []
    return [None if pd.isna(v) else float(v) for v in s.values]
