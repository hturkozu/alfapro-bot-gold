"""
AI sinyal doğrulama servisi (Anthropic Claude).

Bir sinyal üretildikten sonra:
    1. Son N mum + indikatör özeti + SMC + sinyal detayları Claude'a gönderilir
    2. Claude 0-100 arası bir confidence skoru ve kısa açıklama döndürür
    3. Skor AppState.ai_min_confidence'ın altındaysa sinyal REDDedilir

API key yok / ai_enabled=false ise doğrulayıcı no-op çalışır (approve=True).
Bu sayede Faz 4'te eklenen AI katmanı opsiyonel kalır.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from loguru import logger

from app.config import get_settings
from app.schemas.market import IndicatorValues, SmcAnalysis
from app.schemas.trading import SignalCore


@dataclass
class AiVerdict:
    approved: bool
    confidence: float | None  # 0-100 AI skorıu, None ise çalıştırılmadı
    notes: str


class AiValidator:
    """Claude ile sinyal doğrulama."""

    def __init__(
        self,
        api_key: str | None = None,
        min_confidence: float = 65.0,
        model: str = "claude-haiku-4-5-20251001",
        enabled: bool = True,
    ) -> None:
        self.min_confidence = float(min_confidence)
        self.enabled = enabled
        # Anahtar önceliği: verilen > env
        self.api_key = api_key or get_settings().anthropic_api_key or ""
        self.model = model
        self._client = None

    def _lazy_client(self):
        """Anthropic client lazy init — paket yoksa/anahtar yoksa None."""
        if self._client is not None:
            return self._client
        if not self.api_key:
            return None
        try:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.api_key)
            return self._client
        except ImportError:
            logger.warning("anthropic paketi yüklü değil. AI atlanıyor.")
            return None

    # ------------------------------------------------------------------
    # Ana metot
    # ------------------------------------------------------------------

    def validate(
        self,
        signal: SignalCore,
        ind_last: IndicatorValues,
        smc: SmcAnalysis,
        recent_candles: list[list[float]] | None = None,
    ) -> AiVerdict:
        """Sinyali doğrula. Devre dışıysa her zaman onay verir."""
        if not self.enabled:
            return AiVerdict(approved=True, confidence=None, notes="AI devre dışı")

        client = self._lazy_client()
        if client is None:
            return AiVerdict(
                approved=True,
                confidence=None,
                notes="AI atlandı (key yok veya paket eksik)",
            )

        prompt = self._build_prompt(signal, ind_last, smc, recent_candles)

        try:
            msg = client.messages.create(
                model=self.model,
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.content[0].text if msg.content else ""
        except Exception as e:  # noqa: BLE001
            logger.warning("AI çağrısı başarısız: {}", e)
            return AiVerdict(
                approved=True,
                confidence=None,
                notes=f"AI hata ({e}) — varsayılan onay",
            )

        # JSON çıktıyı ayrıştır
        verdict = self._parse_response(raw)
        if verdict.confidence is None:
            return verdict

        approved = verdict.confidence >= self.min_confidence
        logger.info(
            "AI {}: strategy={} sym={} side={} strat_conf={:.1f} ai_conf={:.1f} → {}",
            "APPROVE" if approved else "REJECT",
            signal.strategy_id, signal.symbol, signal.side,
            signal.confidence, verdict.confidence,
            "✓" if approved else "✗",
        )
        return AiVerdict(
            approved=approved,
            confidence=verdict.confidence,
            notes=verdict.notes,
        )

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        signal: SignalCore,
        ind_last: IndicatorValues,
        smc: SmcAnalysis,
        recent_candles: list[list[float]] | None,
    ) -> str:
        """Claude için kompakt JSON girdi — deterministik yanıt için."""
        # Son 10 mumu özetle
        tail: list[dict[str, float]] = []
        if recent_candles:
            for r in recent_candles[-10:]:
                tail.append({
                    "o": round(r[1], 6),
                    "h": round(r[2], 6),
                    "l": round(r[3], 6),
                    "c": round(r[4], 6),
                    "v": round(r[5], 2),
                })

        context = {
            "signal": {
                "strategy": signal.strategy_id,
                "symbol": signal.symbol,
                "tf": signal.timeframe,
                "side": signal.side,
                "entry": signal.entry_price,
                "sl": signal.stop_loss,
                "tp": signal.take_profit,
                "strategy_confidence": signal.confidence,
                "reasoning": signal.reasoning,
            },
            "indicators": {
                "rsi": ind_last.rsi,
                "macd_hist": ind_last.macd_hist,
                "atr": ind_last.atr,
                "bb_upper": ind_last.bb_upper,
                "bb_middle": ind_last.bb_middle,
                "bb_lower": ind_last.bb_lower,
                "ema": ind_last.ema,
            },
            "smc": {
                "trend": smc.current_trend,
                "bos_count": len(smc.bos),
                "choch_count": len(smc.choch),
                "order_blocks": len(smc.order_blocks),
            },
            "recent_candles": tail,
        }

        return (
            "Sen bir kripto futures risk analistisin. Bir teknik strateji sinyali ürettim. "
            "Aşağıdaki veriye bakarak bu sinyalin işlenmesi KONUSUNDA bir görüş ver.\n\n"
            "KESİNLİKLE sadece şu JSON formatında yanıt ver (ekstra metin, kod bloğu YOK):\n"
            '{"confidence": <0-100 arası int>, "approved": <true|false>, '
            '"notes": "<tek cümlelik sebep>"}\n\n'
            "Değerlendirme kriterleri:\n"
            "- Trend yönü ve sinyal yönü çelişiyor mu?\n"
            "- RSI aşırı alım/aşırı satım bölgesinde mi?\n"
            "- Risk/reward oranı mantıklı mı (min 1:1.5)?\n"
            "- Son mumlarda sinyale ters güçlü hareket var mı?\n\n"
            f"VERİ:\n{json.dumps(context, indent=2, default=str)}\n\n"
            "Sadece JSON döndür."
        )

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response(raw: str) -> AiVerdict:
        """Claude yanıtından JSON çek."""
        if not raw:
            return AiVerdict(approved=True, confidence=None, notes="Boş yanıt")

        # İlk {'den son }'ye kadar kısmı al
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end < 0:
            return AiVerdict(
                approved=True, confidence=None,
                notes=f"JSON parse edilemedi: {raw[:80]}",
            )
        blob = raw[start : end + 1]

        try:
            data: dict[str, Any] = json.loads(blob)
        except json.JSONDecodeError:
            return AiVerdict(
                approved=True, confidence=None,
                notes=f"Geçersiz JSON: {blob[:80]}",
            )

        try:
            conf = float(data.get("confidence", 0))
        except (TypeError, ValueError):
            conf = 0.0
        conf = max(0.0, min(100.0, conf))

        notes = str(data.get("notes", ""))[:200]
        return AiVerdict(approved=True, confidence=conf, notes=notes)

    def test_connection(self) -> tuple[bool, str, int | None]:
        """
        Anthropic API bağlantısını minimal bir istekle doğrular.

        Returns:
            (ok, message, latency_ms)
        """
        start = time.monotonic()
        client = self._lazy_client()
        if client is None:
            return False, "Anthropic client başlatılamadı (key/paket eksik).", None

        try:
            msg = client.messages.create(
                model=self.model,
                max_tokens=8,
                messages=[{"role": "user", "content": "Reply with OK"}],
            )
            text = msg.content[0].text if msg.content else ""
            latency_ms = int((time.monotonic() - start) * 1000)
            if not text:
                return False, "API boş yanıt döndürdü.", latency_ms
            return True, f"Anthropic bağlantısı başarılı. Yanıt: {text[:80]}", latency_ms
        except Exception as e:  # noqa: BLE001
            latency_ms = int((time.monotonic() - start) * 1000)
            return False, f"Anthropic bağlantı hatası: {e}", latency_ms


def get_ai_validator_from_state(state_dict: dict[str, Any]) -> AiValidator:
    """AppState verisinden AiValidator üret."""
    return AiValidator(
        enabled=bool(state_dict.get("ai_enabled", False)),
        min_confidence=float(state_dict.get("ai_min_confidence", 65.0)),
    )
