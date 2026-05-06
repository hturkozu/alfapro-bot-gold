"""
Merkezi log yapılandırması (loguru).

- Konsola renkli log
- `logs/alfapro.log` dosyasına günlük rotasyon, 30 gün saklama
- `logs/trades.log` işlem-özel logları için ayrı dosya
"""
from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from app.config import get_settings


_configured = False


def setup_logging() -> None:
    """Log handler'larını kur. Birden fazla çağrıda no-op."""
    global _configured
    if _configured:
        return

    settings = get_settings()
    log_dir: Path = settings.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    # Varsayılan handler'ı kaldır
    logger.remove()

    # Konsol
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}:{function}:{line}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
        backtrace=False,
        diagnose=settings.app_debug,
    )

    # Genel log dosyası
    logger.add(
        log_dir / "alfapro.log",
        level=settings.log_level,
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
            "{name}:{function}:{line} | {message}"
        ),
        rotation="00:00",       # Her gece yeni dosya
        retention="30 days",    # 30 gün sakla
        compression="zip",
        enqueue=True,           # Multi-thread güvenli
        backtrace=True,
        diagnose=False,         # Prod'da stack'te değer göstermek sızıntı riski
    )

    # İşlemlere özel log — filtreli ikinci dosya
    logger.add(
        log_dir / "trades.log",
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {message}",
        rotation="00:00",
        retention="180 days",
        compression="zip",
        enqueue=True,
        filter=lambda record: record["extra"].get("trade") is True,
    )

    _configured = True
    logger.info("Loglama kuruldu. Seviye: {}", settings.log_level)


def get_trade_logger():
    """İşlem logları için: `trade_log.info("OPEN BTCUSDT long @ 65000")`"""
    return logger.bind(trade=True)
