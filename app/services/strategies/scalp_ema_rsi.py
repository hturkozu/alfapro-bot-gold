"""
Geliştirilmiş Scalp Stratejisi: EMA kesişimi + çoklu filtre.

Uygun timeframe: 1m, 5m

── GİRİŞ KOŞULLARI (hepsi zorunlu) ─────────────────────────────────────
1. EMA 9/21 kesişimi  : EMA9 önceki barda EMA21'in altında/üstündeydi,
                        şimdi geçti (gerçek kesişim, gürültü değil)
2. Volume onayı       : Son mum hacmi son 20 mumun ortalamasının
                        min_vol_ratio (varsayılan 1.2x) katı üstünde
3. VWAP filtresi      : Long → fiyat > VWAP; Short → fiyat < VWAP
4. Trend filtresi     : SMC trendi sinyal yönüyle çelişmiyorsa devam
                        (neutral → tamam, ters trend → red)

── CONFIDENCE SKORLAMASI ────────────────────────────────────────────────
  Base        : 45
  + EMA ayrışma genişliği (geniş → daha güçlü):          maks +10
  + RSI sweet-spot (long:45-60 / short:40-55):            +10
  + MACD histogram sinyal yönüyle uyumlu:                  +15
  + Stochastic RSI K > D (long) / K < D (short):          +10
  + Stoch RSI aşırı bölgeden dönüş (long:<30 / short:>70):+10
  + Son 3 mumun çoğunluğu sinyal yönünde kapanmış:        +10
  (max 100'e clamp)

── SL / TP ─────────────────────────────────────────────────────────────
  SL = 1.0× ATR  |  TP = 2.0× ATR  →  R:R = 2.0
  Min R:R 1.5 altındaysa sinyal iptal.
"""
from __future__ import annotations

from typing import Any

from app.schemas.trading import SignalCore
from app.services.strategies.base import BaseStrategy, StrategyContext


class ScalpEmaRsi(BaseStrategy):
    id = "scalp_ema_rsi"
    name = "Scalp EMA/RSI+"
    description = (
        "1dk/5dk için EMA 9/21 + Volume + VWAP + StochRSI + Trend filtresi. "
        "Çok katmanlı onay ile gürültüyü azaltır."
    )
    default_timeframes = ["1m", "5m"]
    default_params: dict[str, Any] = {
        "ema_fast": 9,
        "ema_slow": 21,
        # Volume: son mumun hacmi bu çarpanın üstünde olmalı
        "min_vol_ratio": 1.2,
        # RSI filtreleri
        "rsi_long_min": 40,
        "rsi_long_max": 70,
        "rsi_short_min": 30,
        "rsi_short_max": 60,
        # SL/TP ATR çarpanları
        "sl_atr_mult": 1.0,
        "tp_atr_mult": 2.0,
        # Minimum confidence eşiği
        "min_confidence": 60,
        # Minimum R:R oranı
        "min_rr": 1.5,
        # SMC ters trend işlemde açma
        "block_counter_trend": True,
        # Ardışık kayıp koruması (0 = devre dışı)
        "max_consecutive_losses": 0,
        # Cooldown (saniye, 0 = devre dışı)
        "cooldown_seconds": 0,
    }

    def evaluate(self, ctx: StrategyContext) -> SignalCore | None:
        p = self.params
        ema_fast_key = f"ema_{p['ema_fast']}"
        ema_slow_key = f"ema_{p['ema_slow']}"

        # ── EMA serileri ──────────────────────────────────────────────
        ema_fast_s = ctx.ind_series.ema.get(ema_fast_key)
        ema_slow_s = ctx.ind_series.ema.get(ema_slow_key)

        if not ema_fast_s or not ema_slow_s:
            return None
        if len(ema_fast_s) < 3:
            return None
        if any(v is None for v in (ema_fast_s[-1], ema_fast_s[-2],
                                    ema_slow_s[-1], ema_slow_s[-2])):
            return None

        fast_now,  fast_prev  = ema_fast_s[-1], ema_fast_s[-2]
        slow_now,  slow_prev  = ema_slow_s[-1], ema_slow_s[-2]

        # Gerçek kesişim: önceki barda karşı tarafta, şimdi bu tarafta
        bull_cross = fast_prev <= slow_prev and fast_now > slow_now
        bear_cross = fast_prev >= slow_prev and fast_now < slow_now

        if not bull_cross and not bear_cross:
            return None

        # ── Temel indikatörler ────────────────────────────────────────
        rsi = ctx.ind_last.rsi
        atr = ctx.ind_last.atr
        if rsi is None or atr is None or atr <= 0:
            return None

        # ── RSI aralık filtresi ───────────────────────────────────────
        if bull_cross and not (p["rsi_long_min"] <= rsi <= p["rsi_long_max"]):
            return None
        if bear_cross and not (p["rsi_short_min"] <= rsi <= p["rsi_short_max"]):
            return None

        side = "long" if bull_cross else "short"

        # ── ZORUNLU: Volume onayı ─────────────────────────────────────
        if len(ctx.candles) < 21:
            return None
        vol_window = [r[5] for r in ctx.candles[-21:-1]]  # son 20 tamamlanmış mum
        avg_vol = sum(vol_window) / len(vol_window) if vol_window else 0.0
        last_vol = ctx.candles[-1][5]
        if avg_vol <= 0 or last_vol < avg_vol * p["min_vol_ratio"]:
            return None

        # ── ZORUNLU: VWAP filtresi ────────────────────────────────────
        vwap = ctx.ind_last.vwap
        entry = ctx.last_price
        if vwap is not None and vwap > 0:
            if side == "long"  and entry <= vwap:
                return None
            if side == "short" and entry >= vwap:
                return None

        # ── ZORUNLU: SMC trend filtresi ───────────────────────────────
        trend = ctx.smc.current_trend
        if p["block_counter_trend"]:
            if side == "long"  and trend == "bearish":
                return None
            if side == "short" and trend == "bullish":
                return None

        # ── SL / TP hesapla ───────────────────────────────────────────
        sl, tp = self.atr_based_sl_tp(
            entry, atr, side,
            sl_mult=p["sl_atr_mult"],
            tp_mult=p["tp_atr_mult"],
        )

        rr = self.risk_reward(entry, sl, tp)
        if rr < p["min_rr"]:
            return None

        # ── CONFIDENCE SKORLAMASI ─────────────────────────────────────
        confidence = 45.0
        reasoning: list[str] = []

        reasoning.append(
            f"EMA{p['ema_fast']}/EMA{p['ema_slow']} "
            f"{'yükseliş' if side == 'long' else 'düşüş'} kesişimi"
        )

        # EMA ayrışma genişliği (ne kadar kararlı kesişti)
        ema_spread = abs(fast_now - slow_now)
        ema_spread_pct = ema_spread / slow_now * 100 if slow_now else 0
        if ema_spread_pct >= 0.05:
            confidence += 10
            reasoning.append(f"EMA ayrışması güçlü ({ema_spread_pct:.3f}%)")
        elif ema_spread_pct >= 0.02:
            confidence += 5

        # RSI sweet-spot
        rsi_sweet = (45 <= rsi <= 60) if side == "long" else (40 <= rsi <= 55)
        if rsi_sweet:
            confidence += 10
            reasoning.append(f"RSI momentum bölgesinde ({rsi:.1f})")

        # MACD histogram uyumu
        macd_h = ctx.ind_last.macd_hist
        if macd_h is not None:
            if (side == "long" and macd_h > 0) or (side == "short" and macd_h < 0):
                confidence += 15
                reasoning.append(
                    f"MACD histogramı uyumlu ({macd_h:+.6f})"
                )

        # Stochastic RSI K/D uyumu
        stoch_k = ctx.ind_last.stoch_k
        stoch_d = ctx.ind_last.stoch_d
        if stoch_k is not None and stoch_d is not None:
            stoch_cross_ok = (
                (side == "long"  and stoch_k > stoch_d) or
                (side == "short" and stoch_k < stoch_d)
            )
            if stoch_cross_ok:
                confidence += 10
                reasoning.append(
                    f"StochRSI K{'>'if side=='long' else '<'}D ({stoch_k:.1f}/{stoch_d:.1f})"
                )

            # Aşırı bölgeden dönüş
            oversold_recovery  = side == "long"  and stoch_k < 30
            overbought_recovery = side == "short" and stoch_k > 70
            if oversold_recovery or overbought_recovery:
                confidence += 10
                reasoning.append(
                    f"StochRSI aşırı{'alım' if overbought_recovery else 'satım'} "
                    f"bölgesinden dönüş ({stoch_k:.1f})"
                )

        # Son 3 mum momentum onayı
        if len(ctx.candles) >= 4:
            last3 = ctx.candles[-4:-1]  # önceki 3 tamamlanmış mum
            bull_candles = sum(1 for c in last3 if c[4] > c[1])  # close > open
            bear_candles = 3 - bull_candles
            momentum_ok = (
                (side == "long"  and bull_candles >= 2) or
                (side == "short" and bear_candles >= 2)
            )
            if momentum_ok:
                confidence += 10
                reasoning.append(
                    f"Son 3 mumun {'yükseliş' if side=='long' else 'düşüş'} momentumu"
                )

        # SMC trend ekstra bonus (ters değil ama aynı yönde)
        if (side == "long" and trend == "bullish") or (side == "short" and trend == "bearish"):
            reasoning.append(f"SMC trendi uyumlu ({trend})")

        # Volume onayını reasoning'e ekle
        reasoning.append(
            f"Hacim ortalamanın {last_vol / avg_vol:.1f}x üstünde"
        )

        confidence = self.clamp_confidence(confidence)

        if confidence < p["min_confidence"]:
            return None

        return SignalCore(
            strategy_id=self.id,
            symbol=ctx.symbol,
            timeframe=ctx.timeframe,
            side=side,  # type: ignore[arg-type]
            entry_price=round(entry, 8),
            stop_loss=sl,
            take_profit=tp,
            confidence=confidence,
            reasoning=reasoning,
            ts=ctx.last_ts,
        )
