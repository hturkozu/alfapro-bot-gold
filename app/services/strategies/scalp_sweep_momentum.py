"""
Scalp Sweep + Momentum Stratejisi.

Giriş mantığı (3 aşama):
  1. EMA trend  : EMA9 / EMA21 yönü belirler (fiyat trendin tarafında mı?)
  2. Sweep      : Son N mumda likidite sweep tespit (wick aşımı + geri dönüş)
  3. RSI filtre : Opsiyonel, dar eşik (long ≥ 52, short ≤ 48)

SL/TP:
  - Yüzde tabanlı öncelikli (sl_pct / tp_pct)
  - use_pct_sl_tp=False ise ATR tabanlı (sl_atr_mult / tp_atr_mult)
  - Min R:R = 1.5 kontrolü

Momentum ve ardışık kayıp koruması scheduler katmanında yapılır.
Bu sınıf saf sinyal mantığından sorumludur.
"""
from __future__ import annotations

from typing import Any

from app.schemas.trading import SignalCore
from app.services.strategies.base import BaseStrategy, StrategyContext


class ScalpSweepMomentum(BaseStrategy):
    id = "scalp_sweep_momentum"
    name = "Scalp Sweep + Momentum"
    description = (
        "1dk: EMA trend + likidite sweep (stop avı) + RSI. "
        "Gerçek zamanlı momentum scheduler'da doğrulanır."
    )
    default_timeframes = ["1m"]
    default_params: dict[str, Any] = {
        # Trend
        "ema_fast": 9,
        "ema_slow": 21,
        # Sweep tespiti
        "sweep_lookback": 5,          # referans swing için bakılacak mum sayısı
        "sweep_tolerance_long": 1.0015,  # long: wick en fazla %0.15 aşağı inebilir
        "sweep_tolerance_short": 0.9985, # short: wick en fazla %0.15 yukarı çıkabilir
        # RSI
        "use_rsi": True,
        "rsi_long_min": 52,
        "rsi_short_max": 48,
        # SL/TP mod: True → yüzde, False → ATR
        "use_pct_sl_tp": True,
        "sl_pct": 0.002,    # %0.20
        "tp_pct": 0.0035,   # %0.35
        "sl_atr_mult": 0.8,
        "tp_atr_mult": 1.2,
        # Risk & koruma
        "max_consecutive_losses": 3,
        "risk_per_trade_pct": 0.8,
        "min_rr": 1.5,
        # Momentum (scheduler'a iletilir, burada sadece saklanır)
        "momentum_window_sec": 3,
        "momentum_threshold_atr": 0.18,
        # Cooldown (scheduler'a iletilir)
        "cooldown_seconds": 12,
    }

    # ------------------------------------------------------------------
    # Ana değerlendirme
    # ------------------------------------------------------------------

    def evaluate(self, ctx: StrategyContext) -> SignalCore | None:
        p = self.params
        ema_fast_key = f"ema_{p['ema_fast']}"
        ema_slow_key = f"ema_{p['ema_slow']}"

        # ── EMA serileri ──────────────────────────────────────────────
        ema_fast_s = ctx.ind_series.ema.get(ema_fast_key)
        ema_slow_s = ctx.ind_series.ema.get(ema_slow_key)
        if not ema_fast_s or not ema_slow_s:
            return None
        if ema_fast_s[-1] is None or ema_slow_s[-1] is None:
            return None

        ema_fast = ema_fast_s[-1]
        ema_slow = ema_slow_s[-1]

        # Trend yönü: fiyat her iki EMA'nın hangi tarafında?
        entry = ctx.last_price
        if ema_fast > ema_slow:
            trend_side = "long"
        else:
            trend_side = "short"

        # ── Likidite sweep tespiti ─────────────────────────────────────
        sweep_side = self._detect_sweep(ctx.candles, p)
        if sweep_side is None:
            return None

        # Sweep trend ile uyuşmuyorsa iptal
        if sweep_side != trend_side:
            return None

        side = sweep_side

        # ── RSI filtresi (opsiyonel) ───────────────────────────────────
        if p["use_rsi"]:
            rsi = ctx.ind_last.rsi
            if rsi is None:
                return None
            if side == "long" and rsi < p["rsi_long_min"]:
                return None
            if side == "short" and rsi > p["rsi_short_max"]:
                return None

        # ── ATR kontrolü ──────────────────────────────────────────────
        atr = ctx.ind_last.atr
        if atr is None or atr <= 0:
            return None

        # ── SL / TP hesapla ───────────────────────────────────────────
        if p["use_pct_sl_tp"]:
            sl_dist = entry * p["sl_pct"]
            tp_dist = entry * p["tp_pct"]
        else:
            sl_dist = atr * p["sl_atr_mult"]
            tp_dist = atr * p["tp_atr_mult"]

        if side == "long":
            sl = round(entry - sl_dist, 8)
            tp = round(entry + tp_dist, 8)
        else:
            sl = round(entry + sl_dist, 8)
            tp = round(entry - tp_dist, 8)

        rr = self.risk_reward(entry, sl, tp)
        if rr < p["min_rr"]:
            return None

        # ── Reasoning ─────────────────────────────────────────────────
        sweep_candle = ctx.candles[-2]  # son tamamlanmış mum
        ref_low, ref_high = self._ref_levels(ctx.candles, p["sweep_lookback"])
        reasoning = [
            f"EMA{p['ema_fast']}={'ust' if trend_side == 'long' else 'alt'} EMA{p['ema_slow']} — trend {'yukselis' if trend_side == 'long' else 'dusus'}",
            f"Sweep {'asagi' if side == 'long' else 'yukari'}: low={sweep_candle[3]:.6f} ref={'_low=' + str(round(ref_low,6)) if side == 'long' else '_high=' + str(round(ref_high,6))}",
        ]
        if p["use_rsi"] and ctx.ind_last.rsi is not None:
            reasoning.append(f"RSI={ctx.ind_last.rsi:.1f} (esik {'>='+str(p['rsi_long_min']) if side=='long' else '<='+str(p['rsi_short_max'])})")
        reasoning.append(f"SL={p['sl_pct']*100:.2f}% TP={p['tp_pct']*100:.2f}% RR={rr:.2f}")

        return SignalCore(
            strategy_id=self.id,
            symbol=ctx.symbol,
            timeframe=ctx.timeframe,
            side=side,  # type: ignore[arg-type]
            entry_price=round(entry, 8),
            stop_loss=sl,
            take_profit=tp,
            confidence=75.0,  # momentum skoru scheduler'dan gelir; sabit başlangıç
            reasoning=reasoning,
            ts=ctx.last_ts,
        )

    # ------------------------------------------------------------------
    # Sweep tespit yardımcıları
    # ------------------------------------------------------------------

    @staticmethod
    def _ref_levels(
        candles: list[list[float]],
        lookback: int,
    ) -> tuple[float, float]:
        """Referans swing low ve swing high (son complete mum hariç lookback mum)."""
        ref = candles[-(lookback + 2):-2]  # son mum + sweep mum hariç
        if not ref:
            return 0.0, float("inf")
        ref_low  = min(r[3] for r in ref)
        ref_high = max(r[2] for r in ref)
        return ref_low, ref_high

    def _detect_sweep(
        self,
        candles: list[list[float]],
        p: dict,
    ) -> str | None:
        """
        Son tamamlanmış mumu incele.
        LONG sweep : wick → ref_low'un altına geçti, kapanış üstte
        SHORT sweep: wick → ref_high'ın üstüne geçti, kapanış altta

        Dönüş: "long" | "short" | None
        """
        lookback = p["sweep_lookback"]
        if len(candles) < lookback + 3:
            return None

        sweep_candle = candles[-2]          # son tamamlanmış (canlı mum hariç)
        s_low  = sweep_candle[3]
        s_high = sweep_candle[2]
        s_close = sweep_candle[4]
        s_open  = sweep_candle[1]

        ref_low, ref_high = self._ref_levels(candles, lookback)

        tol_long  = p["sweep_tolerance_long"]   # 1.0015
        tol_short = p["sweep_tolerance_short"]  # 0.9985

        # LONG sweep: wick aşağı geçti ama close geri döndü
        # Aşım aralığı: ref_low * (2 - tol_long) < s_low < ref_low
        long_sweep = (
            s_low < ref_low
            and s_low >= ref_low * (2.0 - tol_long)   # max 0.15% aşağı
            and s_close > ref_low                       # geri dönüş
        )

        # SHORT sweep: wick yukarı geçti ama close geri döndü
        # Aşım aralığı: ref_high < s_high <= ref_high * (2 - tol_short)
        short_sweep = (
            s_high > ref_high
            and s_high <= ref_high * (2.0 - tol_short)  # max 0.15% yukarı
            and s_close < ref_high                        # geri dönüş
        )

        if long_sweep:
            return "long"
        if short_sweep:
            return "short"
        return None
