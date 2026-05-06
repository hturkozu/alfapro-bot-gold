"""
Telegram bildirim servisi.

`AppState.telegram_enabled=False` veya token/chat_id boşsa no-op.
httpx ile senkron POST — bot açıksa bildirim gider, yoksa sessizce atlanır.

Bildirim türleri:
- signal_generated : Yeni sinyal
- position_opened  : Pozisyon açıldı
- position_closed  : Pozisyon kapandı (PnL dahil)
- circuit_breaker  : Günlük zarar kilidi tetiklendi
"""
from __future__ import annotations

import httpx
from loguru import logger

from app.models.app_state import AppState
from app.models.position import Position
from app.schemas.trading import SignalCore


class TelegramNotifier:
    """İnce httpx sarmalayıcısı."""

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send(self, text: str) -> bool:
        """Markdown formatlı mesaj gönder."""
        if not self.bot_token or not self.chat_id:
            return False
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        try:
            resp = httpx.post(
                url,
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                },
                timeout=5.0,
            )
            if resp.status_code != 200:
                logger.warning(
                    "Telegram gönderim hatası: {} {}",
                    resp.status_code, resp.text[:120],
                )
                return False
            return True
        except httpx.HTTPError as e:
            logger.warning("Telegram ağ hatası: {}", e)
            return False

    # ------------------------------------------------------------------
    # Yüksek seviye yardımcılar
    # ------------------------------------------------------------------

    def notify_signal(self, signal: SignalCore, ai_conf: float | None = None) -> bool:
        side_emoji = "🟢" if signal.side == "long" else "🔴"
        msg = (
            f"{side_emoji} *YENİ SİNYAL*\n"
            f"Strateji: `{signal.strategy_id}`\n"
            f"Sembol: `{signal.symbol}` ({signal.timeframe})\n"
            f"Yön: *{signal.side.upper()}*\n"
            f"Entry: `{signal.entry_price}`\n"
            f"SL: `{signal.stop_loss}` · TP: `{signal.take_profit}`\n"
            f"Güven: *{signal.confidence:.1f}/100*"
        )
        if ai_conf is not None:
            msg += f"\nAI skoru: *{ai_conf:.1f}/100*"
        if signal.reasoning:
            msg += "\n_" + " · ".join(signal.reasoning[:3]) + "_"
        return self.send(msg)

    def notify_position_opened(self, pos: Position) -> bool:
        mode_tag = "📝 PAPER" if pos.mode == "paper" else "🔴 LIVE"
        side_emoji = "🟢" if pos.side == "long" else "🔴"
        return self.send(
            f"{mode_tag} {side_emoji} *Pozisyon açıldı*\n"
            f"`{pos.symbol}` {pos.side.upper()} @ `{pos.entry_price}`\n"
            f"Size: `{pos.size_usdt:.2f}$` × `{pos.leverage}x`\n"
            f"SL: `{pos.stop_loss}` · TP: `{pos.take_profit}`"
        )

    def notify_position_closed(self, pos: Position) -> bool:
        if pos.pnl_usdt is None:
            return False
        emoji = "✅" if pos.pnl_usdt >= 0 else "❌"
        mode_tag = "📝 PAPER" if pos.mode == "paper" else "🔴 LIVE"
        return self.send(
            f"{emoji} {mode_tag} *Pozisyon kapandı* ({pos.status})\n"
            f"`{pos.symbol}` {pos.side.upper()}\n"
            f"Entry: `{pos.entry_price}` → Close: `{pos.close_price}`\n"
            f"*PnL: {pos.pnl_usdt:+.2f} USDT ({pos.pnl_pct:+.2f}%)*"
        )

    def notify_circuit_breaker(self, daily_pnl: float, limit: float) -> bool:
        return self.send(
            f"⛔ *CIRCUIT BREAKER*\n"
            f"Günlük zarar limiti aşıldı.\n"
            f"PnL: `{daily_pnl:.2f} USDT` · Limit: `{-abs(limit):.2f} USDT`\n"
            "Yeni pozisyon açma kilitlendi. Panelden manuel reset yap."
        )


def get_notifier_from_state(state: AppState) -> TelegramNotifier | None:
    """AppState'den Telegram notifier üret. Disabled ise None."""
    if not state.telegram_enabled:
        return None
    if not state.telegram_bot_token or not state.telegram_chat_id:
        return None
    return TelegramNotifier(state.telegram_bot_token, state.telegram_chat_id)
