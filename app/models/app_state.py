"""
Uygulama genel ayarları (tek satır).

- `trading_mode`: "paper" veya "live"
- Risk limitleri: günlük zarar kilidi, max açık pozisyon
- AI kullanımı: aç/kapat, onay eşiği
- Scheduler: otomatik strateji çalıştırma aç/kapat + periyot
- Telegram: bildirim aç/kapat + token/chat
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AppState(Base):
    __tablename__ = "app_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)

    # ---- Trading modu ----
    trading_mode: Mapped[str] = mapped_column(String(8), default="paper", nullable=False)
    # paper | live

    # ---- Risk yönetimi ----
    max_open_positions: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    daily_loss_limit_usdt: Mapped[float] = mapped_column(
        Float, default=100.0, nullable=False
    )
    # Günlük kümülatif PnL bu eksinin altına inerse YENİ açma yasak
    circuit_breaker_tripped: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    circuit_breaker_date: Mapped[str] = mapped_column(
        String(16), default="", nullable=False
    )
    # YYYY-MM-DD — her gün sıfırlanır

    # ---- AI doğrulama ----
    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ai_min_confidence: Mapped[float] = mapped_column(
        Float, default=65.0, nullable=False
    )
    # Anthropic API key (Faz 4) — DB'de şifreli tutulur.
    anthropic_api_key_enc: Mapped[str] = mapped_column(
        String(512), default="", nullable=False
    )
    # OpenAI API key (opsiyonel) — DB'de şifreli tutulur.
    openai_api_key_enc: Mapped[str] = mapped_column(
        String(512), default="", nullable=False
    )
    # AI skoru < bu değer ise sinyal reddedilir

    # ---- Scheduler (otomasyon) ----
    scheduler_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    scheduler_interval_seconds: Mapped[int] = mapped_column(
        Integer, default=60, nullable=False
    )
    # Faz 5: Live mode auto-trading için ekstra güvenlik — default kapalı.
    # Sadece bu flag VE scheduler_enabled VE trading_mode=="live" üçü de
    # true ise scheduler gerçek emir gönderir.
    live_auto_trading_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # ---- Telegram ----
    telegram_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    telegram_bot_token: Mapped[str] = mapped_column(
        String(128), default="", nullable=False
    )
    telegram_chat_id: Mapped[str] = mapped_column(
        String(64), default="", nullable=False
    )

    # ---- Sweep / Momentum stratejisi koruma ----
    # Paper hesap referans bakiyesi (kill switch hesabı için)
    paper_balance_usdt: Mapped[float] = mapped_column(
        Float, default=1000.0, nullable=False
    )
    # Günlük kayıp limiti (yüzde) — circuit_breaker'a ek, bilgilendirme amaçlı
    daily_loss_limit_pct: Mapped[float] = mapped_column(
        Float, default=3.0, nullable=False
    )
    # Bu yüzde aşılırsa tüm yeni girişler durdurulur (intraday reset)
    kill_switch_drawdown_pct: Mapped[float] = mapped_column(
        Float, default=5.0, nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
