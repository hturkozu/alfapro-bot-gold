"""
AlfaPro Bot — FastAPI uygulaması.

Başlangıçta yapılanlar:
1. Loguru kurulur.
2. DB tabloları oluşturulur (idempotent).
3. Router'lar bağlanır.
4. Frontend `frontend/index.html` dosyası statik olarak servis edilir.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from app import __version__
from app.config import get_settings
from app.core.database import init_db
from app.core.logger import setup_logging
from app.routers import (
    health,
    logs as logs_router,
    market,
    risk as risk_router,
    settings as settings_router,
    strategies as strategies_router,
    trading as trading_router,
)
from app.routers import backtest as backtest_router
from app.routers import ws as ws_router
from app.services.scheduler import get_scheduler


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Uygulama yaşam döngüsü — startup / shutdown."""
    setup_logging()
    logger.info("AlfaPro Bot v{} başlatılıyor...", __version__)

    init_db()
    logger.info("Veritabanı hazır.")

    cfg = get_settings()
    logger.info("Ortam: {}, debug: {}", cfg.app_env, cfg.app_debug)

    # Faz 4: arka plan scheduler
    sched = get_scheduler()
    sched.start()

    yield

    # Shutdown
    await sched.stop()
    logger.info("AlfaPro Bot kapanıyor.")


def create_app() -> FastAPI:
    cfg = get_settings()

    app = FastAPI(
        title="AlfaPro Bot",
        description="Bitget futures için otomatik al-sat robotu.",
        version=__version__,
        lifespan=lifespan,
        debug=cfg.app_debug,
    )

    # Geliştirme ortamında panel ile API farklı port'ta olabilir
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if cfg.app_debug else [],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---- Router'lar ----
    app.include_router(health.router, prefix="/api")
    app.include_router(settings_router.router, prefix="/api")
    app.include_router(market.router, prefix="/api")
    app.include_router(strategies_router.router, prefix="/api")
    app.include_router(trading_router.router, prefix="/api")
    app.include_router(risk_router.router, prefix="/api")
    app.include_router(logs_router.router, prefix="/api")
    app.include_router(ws_router.router, prefix="/api")

    # ---- Frontend ----
    if FRONTEND_DIR.exists():
        # Kök → index.html
        @app.get("/", include_in_schema=False)
        def index() -> FileResponse:
            return FileResponse(FRONTEND_DIR / "index.html")

        # Diğer statik dosyalar (ileride CSS/JS için)
        app.mount(
            "/static",
            StaticFiles(directory=FRONTEND_DIR),
            name="static",
        )

    return app


app = create_app()


# `python -m app.main` ile doğrudan çalıştırılabilir
if __name__ == "__main__":
    import uvicorn

    cfg = get_settings()
    uvicorn.run(
        "app.main:app",
        host=cfg.app_host,
        port=cfg.app_port,
        reload=cfg.app_debug,
    )
