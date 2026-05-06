"""
SQLAlchemy 2.0 motoru, session yönetimi ve Base sınıfı.

SQLite için WAL modu aktif edilir (eşzamanlı okuma performansı için).
"""
from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


settings = get_settings()


class Base(DeclarativeBase):
    """Tüm ORM modellerinin temel sınıfı."""


# SQLite için gerekli: aynı connection'ı farklı thread'lerde kullanmaya izin ver
connect_args: dict = {}
if settings.database_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False
    # data/ dizinini oluştur
    db_path = settings.database_url.replace("sqlite:///", "")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)


engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    echo=False,  # Gerekiyorsa settings.app_debug ile aç
    pool_pre_ping=True,
)


@event.listens_for(Engine, "connect")
def _enable_sqlite_wal(dbapi_conn, _connection_record) -> None:  # noqa: ANN001
    """SQLite bağlantısı açıldığında WAL modunu aktif eder."""
    if settings.database_url.startswith("sqlite"):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency — request başına bir DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Tüm tabloları oluşturur (ilk açılışta çağrılır)."""
    # Modellerin yüklenmesini tetikle
    from app.models import (  # noqa: F401
        api_credentials,
        app_state,
        candle,
        position,
        signal,
        strategy_config,
        trade,
    )

    Base.metadata.create_all(bind=engine)

    # Faz 4: eski AppState tablosuna eksik sütunları ekle
    _migrate_app_state()
    _migrate_signals()

    # Tek satırlık app_state kaydını garanti et
    from app.models.app_state import AppState
    with SessionLocal() as db:
        state = db.get(AppState, 1)
        if state is None:
            db.add(AppState(id=1, trading_mode="paper"))
            db.commit()


def _migrate_app_state() -> None:
    """SQLite için basit 'ALTER TABLE ADD COLUMN IF NOT EXISTS' pattern."""
    if not engine.url.get_backend_name().startswith("sqlite"):
        return
    needed_cols = {
        "max_open_positions": "INTEGER NOT NULL DEFAULT 5",
        "daily_loss_limit_usdt": "FLOAT NOT NULL DEFAULT 100.0",
        "circuit_breaker_tripped": "BOOLEAN NOT NULL DEFAULT 0",
        "circuit_breaker_date": "VARCHAR(16) NOT NULL DEFAULT ''",
        "ai_enabled": "BOOLEAN NOT NULL DEFAULT 0",
        "ai_min_confidence": "FLOAT NOT NULL DEFAULT 65.0",
        "anthropic_api_key_enc": "VARCHAR(512) NOT NULL DEFAULT ''",
        "openai_api_key_enc": "VARCHAR(512) NOT NULL DEFAULT ''",
        "scheduler_enabled": "BOOLEAN NOT NULL DEFAULT 0",
        "scheduler_interval_seconds": "INTEGER NOT NULL DEFAULT 60",
        "telegram_enabled": "BOOLEAN NOT NULL DEFAULT 0",
        "telegram_bot_token": "VARCHAR(128) NOT NULL DEFAULT ''",
        "telegram_chat_id": "VARCHAR(64) NOT NULL DEFAULT ''",
        "live_auto_trading_enabled": "BOOLEAN NOT NULL DEFAULT 0",
        # Sweep/Momentum stratejisi koruma alanları
        "paper_balance_usdt": "FLOAT NOT NULL DEFAULT 1000.0",
        "daily_loss_limit_pct": "FLOAT NOT NULL DEFAULT 3.0",
        "kill_switch_drawdown_pct": "FLOAT NOT NULL DEFAULT 5.0",
    }
    from sqlalchemy import text
    with engine.begin() as conn:
        existing = {
            row[1] for row in conn.execute(text("PRAGMA table_info(app_state)"))
        }
        for col, decl in needed_cols.items():
            if col not in existing:
                conn.execute(text(f"ALTER TABLE app_state ADD COLUMN {col} {decl}"))


def _migrate_signals() -> None:
    """Signal tablosuna ai_confidence eklendi (Faz 4)."""
    if not engine.url.get_backend_name().startswith("sqlite"):
        return
    from sqlalchemy import text
    with engine.begin() as conn:
        existing = {
            row[1] for row in conn.execute(text("PRAGMA table_info(signals)"))
        }
        if "ai_confidence" not in existing:
            conn.execute(text("ALTER TABLE signals ADD COLUMN ai_confidence FLOAT"))
