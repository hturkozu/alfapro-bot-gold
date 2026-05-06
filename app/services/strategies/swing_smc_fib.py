"""
Swing stratejisi: SMC trend + Fibonacci zone + MACD onayı.

Uygun timeframe: 15m, 1h
Mantık:
    LONG  : SMC trend bullish VE fiyat 0.5-0.618 Fib retracement'ında
            VE MACD histogramı sıfırın üstüne dönüyor
    SHORT : SMC trend bearish VE fiyat 0.5-0.618 Fib retracement'ında
            VE MACD histogramı sıfırın altına dönüyor
    SL    : Son swing low/high'ın az ötesi (ATR tamponuyla)
    TP    : 1.618 extension veya 2R (hangisi önce)

Confidence skorlaması:
    Başlangıç: 40
    + Yakın zamanda CHoCH teyit edildiyse (son 20 mum): +25
    + Fib bölgesinde hassas (0.5-0.618 arasında): +15
    + MACD histogram dönüşü güçlüyse (|h| > son 20'nin |h| ortalaması): +10
    + BOS sayısı son 10 mumda artmışsa: +10
"""
from __future__ import annotations

from typing import Any

from app.schemas.trading import SignalCore
from app.services.strategies.base import BaseStrategy, StrategyContext


class SwingSmcFib(BaseStrategy):
    id = "swing_smc_fib"
    name = "Swing SMC + Fibonacci"
    description = (
        "15dk/1sa için SMC trend + Fibonacci retracement (0.5-0.618) "
        "+ MACD histogram dönüşü. Orta-vadeli setup."
    )
    default_timeframes = ["15m", "1h"]
    default_params: dict[str, Any] = {
        "fib_zone_low": 0.5,
        "fib_zone_high": 0.618,
        "fib_zone_tolerance_pct": 0.5,  # %0.5 tampon
        "sl_atr_buffer": 0.5,           # swing'in ötesine ATR'ın 0.5 katı kadar
        "tp_rr_ratio": 2.0,             # min 1:2 R:R
        "min_confidence": 60,
        "choch_lookback_bars": 20,
    }

    def evaluate(self, ctx: StrategyContext) -> SignalCore | None:
        p = self.params

        if ctx.fib is None:
            return None

        # SMC trend var olmalı
        trend = ctx.smc.current_trend
        if trend not in ("bullish", "bearish"):
            return None

        atr = ctx.ind_last.atr
        if atr is None or atr <= 0:
            return None

        price = ctx.last_price
        macd_h = ctx.ind_last.macd_hist
        if macd_h is None:
            return None

        # ---- Fibonacci bölge kontrolü ----
        # retracement dict: {"0.5": 12345.6, "0.618": 12300.0, ...}
        fib_05 = ctx.fib.retracement.get("0.5")
        fib_0618 = ctx.fib.retracement.get("0.618")
        if fib_05 is None or fib_0618 is None:
            return None

        zone_low = min(fib_05, fib_0618)
        zone_high = max(fib_05, fib_0618)
        tol = (zone_high - zone_low) * (p["fib_zone_tolerance_pct"] / 100)
        in_zone = (zone_low - tol) <= price <= (zone_high + tol)
        if not in_zone:
            return None

        # ---- MACD histogram dönüşü ----
        macd_hist_series = ctx.ind_series.macd_hist or []
        if len(macd_hist_series) < 3:
            return None

        # Son iki mumda histogramın işaret değiştirmiş olması lazım
        h_prev = macd_hist_series[-2]
        h_now = macd_hist_series[-1]
        if h_prev is None or h_now is None:
            return None

        flipping_up = h_prev <= 0 and h_now > 0
        flipping_down = h_prev >= 0 and h_now < 0

        side: str | None = None
        reasoning: list[str] = []

        if trend == "bullish" and flipping_up:
            side = "long"
            reasoning.append("SMC trendi bullish")
            reasoning.append(f"Fiyat 0.5-0.618 Fib retracement'ında ({price:.4f})")
            reasoning.append("MACD histogramı sıfırın üstüne döndü")
        elif trend == "bearish" and flipping_down:
            side = "short"
            reasoning.append("SMC trendi bearish")
            reasoning.append(f"Fiyat 0.5-0.618 Fib retracement'ında ({price:.4f})")
            reasoning.append("MACD histogramı sıfırın altına döndü")
        else:
            return None

        # ---- SL/TP ----
        entry = price
        if side == "long":
            sl = ctx.fib.swing_low - atr * p["sl_atr_buffer"]
            risk = entry - sl
            tp_by_rr = entry + risk * p["tp_rr_ratio"]
            tp_by_ext = ctx.fib.extension.get("1.618", tp_by_rr)
            tp = min(tp_by_rr, tp_by_ext) if tp_by_ext > entry else tp_by_rr
        else:
            sl = ctx.fib.swing_high + atr * p["sl_atr_buffer"]
            risk = sl - entry
            tp_by_rr = entry - risk * p["tp_rr_ratio"]
            tp_by_ext = ctx.fib.extension.get("1.618", tp_by_rr)
            tp = max(tp_by_rr, tp_by_ext) if tp_by_ext < entry else tp_by_rr

        # Sağlık kontrolü — SL yanlış tarafta olmamalı
        if side == "long" and (sl >= entry or tp <= entry):
            return None
        if side == "short" and (sl <= entry or tp >= entry):
            return None

        # ---- Confidence skorlaması ----
        confidence = 40.0

        # Son N mumda CHoCH var mı?
        if ctx.smc.choch:
            last_choch_ts = ctx.smc.choch[-1].ts
            lookback_ms = p["choch_lookback_bars"] * (ctx.last_ts - ctx.candles[0][0]) / max(1, len(ctx.candles))
            if ctx.last_ts - last_choch_ts <= lookback_ms:
                confidence += 25
                reasoning.append("Yakın zamanda CHoCH teyit edildi")

        # Fib bölge dar mı (hassas mı)
        if zone_low <= price <= zone_high:
            confidence += 15
            reasoning.append("Fib 0.5-0.618 içinde (hassas)")

        # MACD histogram dönüşünün gücü
        recent_hist = [abs(h) for h in macd_hist_series[-20:] if h is not None]
        if recent_hist:
            avg_abs = sum(recent_hist) / len(recent_hist)
            if abs(h_now) > avg_abs:
                confidence += 10
                reasoning.append("MACD histogram dönüşü güçlü")

        # BOS akışı
        if len(ctx.smc.bos) >= 2:
            confidence += 10
            reasoning.append(f"BOS akışı mevcut ({len(ctx.smc.bos)} adet)")

        confidence = self.clamp_confidence(confidence)
        if confidence < p["min_confidence"]:
            return None

        return SignalCore(
            strategy_id=self.id,
            symbol=ctx.symbol,
            timeframe=ctx.timeframe,
            side=side,  # type: ignore[arg-type]
            entry_price=round(entry, 8),
            stop_loss=round(sl, 8),
            take_profit=round(tp, 8),
            confidence=confidence,
            reasoning=reasoning,
            ts=ctx.last_ts,
        )
