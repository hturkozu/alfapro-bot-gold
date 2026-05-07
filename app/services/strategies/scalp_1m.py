"""
Scalp 1M Engine — Pro Level

Giriş modeli (intra-candle):
  Live candle (mevcut/incomplete bar) üzerinde ANINDA tespit.
  Mum kapanması beklenmez — canlı fiyat üzerinden giriş.

Koşullar:
  1. TREND    : EMA9 > EMA21 (long) | EMA9 < EMA21 (short)
  2. RSI      : > 50 (long) | < 50 (short)
  3. SWEEP    : live_low  < swing_low  × (1 - tol)  → tolerance ile sweep tespiti
                live_high > swing_high × (1 + tol)
  4. RECOVERY : live close swing_low üstünde (long) | swing_high altında (short)
  5. MOMENTUM : |close - open| ≥ ATR × body_atr_mult  →  güçlü yön mumu

SL = sweep wick + 1.2 × ATR  (min %0.4)
TP = entry ± 1.8 × ATR
R:R ≈ 1.5
"""
from __future__ import annotations

from typing import Any

from app.schemas.trading import SignalCore
from app.services.strategies.base import BaseStrategy, StrategyContext


class Scalp1M(BaseStrategy):
    id = "scalp_1m"
    name = "1M Scalp Engine"
    description = (
        "Intra-candle 1M scalp: EMA9/21 trend + anlık likidite sweep + "
        "ATR-bazlı momentum. SL=1.2×ATR, TP=1.8×ATR. Tek pozisyon."
    )
    default_timeframes: list[str] = ["1m"]
    default_params: dict[str, Any] = {
        "sweep_lookback":    5,       # Kaç barın low/high'ı referans alınır
        "sweep_tolerance":   0.001,   # 0.1% — gevşetildi (önceki: 0.0005)
        "body_atr_mult":     0.15,    # Gevşetildi (önceki: 0.3) — sinyal frekansı artar
        "sl_atr_mult":       1.2,
        "tp_atr_mult":       1.8,
        "min_sl_pct":        0.004,   # Min SL mesafesi %0.4
        "trailing_atr_mult": 0.0,     # 0 = kapalı; >0 → ATR × bu kadar trailing stop
        "vol_lookback":      20,      # Hacim ortalaması için kaç bar bakılacak
        "min_confidence":    55,
    }

    # ------------------------------------------------------------------
    # Ana değerlendirme (intra-candle)
    # ------------------------------------------------------------------

    def evaluate(self, ctx: StrategyContext) -> SignalCore | None:
        p        = self.params
        candles  = ctx.candles
        ind      = ctx.ind_last
        lookback = int(p.get("sweep_lookback", 5))

        # Yeterli bar: referans(lookback) + live bar + warmup
        if len(candles) < lookback + 10:
            return None

        atr  = ind.atr
        ema9 = ind.ema.get("ema_9")
        ema21 = ind.ema.get("ema_21")
        rsi  = ind.rsi

        if not atr or atr <= 0:
            return None
        if ema9 is None or ema21 is None or rsi is None:
            return None

        tolerance  = float(p.get("sweep_tolerance", 0.0005))
        body_mult  = float(p.get("body_atr_mult",   0.3))
        sl_mult    = float(p.get("sl_atr_mult",     1.2))
        tp_mult    = float(p.get("tp_atr_mult",     1.8))
        min_sl_pct = float(p.get("min_sl_pct",      0.004))
        min_conf   = float(p.get("min_confidence",  55))

        # ---- Live (incomplete) candle ----
        live = candles[-1]
        l_o = float(live[1])
        l_h = float(live[2])
        l_l = float(live[3])
        l_c = float(live[4])
        l_body = abs(l_c - l_o)

        # ---- Referans barlar (live candle hariç, önceki lookback bar) ----
        ref        = candles[-(lookback + 1):-1]
        swing_low  = min(float(b[3]) for b in ref)
        swing_high = max(float(b[2]) for b in ref)

        kw = dict(
            ema9=ema9, ema21=ema21, rsi=rsi, atr=atr,
            l_o=l_o, l_h=l_h, l_l=l_l, l_c=l_c, l_body=l_body,
            swing_low=swing_low, swing_high=swing_high,
            tolerance=tolerance, body_mult=body_mult,
            sl_mult=sl_mult, tp_mult=tp_mult,
            min_sl_pct=min_sl_pct, min_conf=min_conf,
            ctx=ctx,
        )
        sig = self._long(**kw)
        if sig is None:
            sig = self._short(**kw)
        return sig

    # ------------------------------------------------------------------
    # LONG
    # ------------------------------------------------------------------

    def _long(
        self, *,
        ema9, ema21, rsi, atr,
        l_o, l_h, l_l, l_c, l_body,
        swing_low, swing_high,
        tolerance, body_mult, sl_mult, tp_mult, min_sl_pct, min_conf,
        ctx,
    ) -> SignalCore | None:

        # 1. TREND
        if ema9 <= ema21:
            return None

        # 2. RSI momentum
        if rsi <= 50:
            return None

        # 3. SWEEP: live bar'ın low'u swing_low'u kırdı (tolerance ile)
        if l_l >= swing_low * (1 - tolerance):
            return None

        # 4. RECOVERY: live bar hâlâ swing_low üstünde kapanıyor
        if l_c <= swing_low:
            return None

        # 5. BULLISH MOMENTUM: close > open + yeterli body
        if l_c <= l_o:
            return None
        if l_body < atr * body_mult:
            return None

        reasoning = [
            f"TREND: EMA9={ema9:.3f} > EMA21={ema21:.3f}",
            f"SWEEP: low={l_l:.3f} < swing_low={swing_low:.3f}×(1-{tolerance*100:.2f}%)",
            f"RECOVERY: close={l_c:.3f} > swing_low",
            f"MOMENTUM: body={l_body:.3f} ≥ {body_mult}×ATR={atr*body_mult:.3f}  RSI={rsi:.1f}",
        ]
        confidence = 65.0

        if rsi > 65:
            confidence += 10
            reasoning.append(f"RSI güçlü: {rsi:.0f}")
        elif rsi > 55:
            confidence += 5

        spread = (ema9 - ema21) / ema21 * 100 if ema21 > 0 else 0
        if spread > 0.03:
            confidence += 5
            reasoning.append(f"EMA spread: {spread:.3f}%")

        depth = (swing_low - l_l) / atr
        if depth >= 0.1:
            confidence += 5
            reasoning.append(f"Sweep derinliği: {depth:.2f}×ATR")

        # Bollinger Band konumu: fiyat alt band yakınındaysa long güçlenir
        bb_lower = ctx.ind_last.bb_lower
        bb_upper = ctx.ind_last.bb_upper
        if bb_lower is not None and bb_upper is not None and bb_upper > bb_lower:
            bb_pos = (l_c - bb_lower) / (bb_upper - bb_lower)
            if bb_pos <= 0.25:
                confidence += 5
                reasoning.append(f"BB alt bölgede (konum: {bb_pos:.2f})")

        # Hacim onayı: son mumun hacmi ortalamadan yüksekse
        vol_lb = int(self.params.get("vol_lookback", 20))
        if len(ctx.candles) >= vol_lb + 1:
            vols = [ctx.candles[i][5] for i in range(-vol_lb - 1, -1)]
            avg_vol = sum(vols) / len(vols) if vols else 0
            if avg_vol > 0 and ctx.candles[-1][5] > avg_vol * 1.2:
                confidence += 5
                reasoning.append("Hacim ortalamanın %20 üstünde")

        confidence = self.clamp_confidence(confidence)
        if confidence < min_conf:
            return None

        entry    = round(l_c, 5)
        raw_sl   = l_l - atr * sl_mult
        min_dist = entry * min_sl_pct
        if (entry - raw_sl) < min_dist:
            raw_sl = entry - min_dist
        sl = round(raw_sl, 5)
        tp = round(entry + atr * tp_mult, 5)

        trailing_mult = float(self.params.get("trailing_atr_mult", 0.0))
        trailing_atr  = round(atr * trailing_mult, 8) if trailing_mult > 0 else 0.0

        return SignalCore(
            strategy_id=self.id,
            symbol=ctx.symbol,
            timeframe=ctx.timeframe,
            side="long",
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            confidence=confidence,
            reasoning=reasoning,
            ts=ctx.last_ts,
            trailing_stop_atr=trailing_atr,
        )

    # ------------------------------------------------------------------
    # SHORT (simetrik)
    # ------------------------------------------------------------------

    def _short(
        self, *,
        ema9, ema21, rsi, atr,
        l_o, l_h, l_l, l_c, l_body,
        swing_low, swing_high,
        tolerance, body_mult, sl_mult, tp_mult, min_sl_pct, min_conf,
        ctx,
    ) -> SignalCore | None:

        # 1. TREND
        if ema9 >= ema21:
            return None

        # 2. RSI momentum
        if rsi >= 50:
            return None

        # 3. SWEEP: live bar'ın high'ı swing_high'ı kırdı (tolerance ile)
        if l_h <= swing_high * (1 + tolerance):
            return None

        # 4. RECOVERY: live bar swing_high altında kapanıyor
        if l_c >= swing_high:
            return None

        # 5. BEARISH MOMENTUM: close < open + yeterli body
        if l_c >= l_o:
            return None
        if l_body < atr * body_mult:
            return None

        reasoning = [
            f"TREND: EMA9={ema9:.3f} < EMA21={ema21:.3f}",
            f"SWEEP: high={l_h:.3f} > swing_high={swing_high:.3f}×(1+{tolerance*100:.2f}%)",
            f"RECOVERY: close={l_c:.3f} < swing_high",
            f"MOMENTUM: body={l_body:.3f} ≥ {body_mult}×ATR={atr*body_mult:.3f}  RSI={rsi:.1f}",
        ]
        confidence = 65.0

        if rsi < 35:
            confidence += 10
            reasoning.append(f"RSI güçlü düşüş: {rsi:.0f}")
        elif rsi < 45:
            confidence += 5

        spread = (ema21 - ema9) / ema21 * 100 if ema21 > 0 else 0
        if spread > 0.03:
            confidence += 5
            reasoning.append(f"EMA spread: {spread:.3f}%")

        depth = (l_h - swing_high) / atr
        if depth >= 0.1:
            confidence += 5
            reasoning.append(f"Sweep derinliği: {depth:.2f}×ATR")

        # Bollinger Band konumu: fiyat üst band yakınındaysa short güçlenir
        bb_lower = ctx.ind_last.bb_lower
        bb_upper = ctx.ind_last.bb_upper
        if bb_lower is not None and bb_upper is not None and bb_upper > bb_lower:
            bb_pos = (l_c - bb_lower) / (bb_upper - bb_lower)
            if bb_pos >= 0.75:
                confidence += 5
                reasoning.append(f"BB üst bölgede (konum: {bb_pos:.2f})")

        # Hacim onayı
        vol_lb = int(self.params.get("vol_lookback", 20))
        if len(ctx.candles) >= vol_lb + 1:
            vols = [ctx.candles[i][5] for i in range(-vol_lb - 1, -1)]
            avg_vol = sum(vols) / len(vols) if vols else 0
            if avg_vol > 0 and ctx.candles[-1][5] > avg_vol * 1.2:
                confidence += 5
                reasoning.append("Hacim ortalamanın %20 üstünde")

        confidence = self.clamp_confidence(confidence)
        if confidence < min_conf:
            return None

        entry    = round(l_c, 5)
        raw_sl   = l_h + atr * sl_mult
        min_dist = entry * min_sl_pct
        if (raw_sl - entry) < min_dist:
            raw_sl = entry + min_dist
        sl = round(raw_sl, 5)
        tp = round(entry - atr * tp_mult, 5)

        trailing_mult = float(self.params.get("trailing_atr_mult", 0.0))
        trailing_atr  = round(atr * trailing_mult, 8) if trailing_mult > 0 else 0.0

        return SignalCore(
            strategy_id=self.id,
            symbol=ctx.symbol,
            timeframe=ctx.timeframe,
            side="short",
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            confidence=confidence,
            reasoning=reasoning,
            ts=ctx.last_ts,
            trailing_stop_atr=trailing_atr,
        )
