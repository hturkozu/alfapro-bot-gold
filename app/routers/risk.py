"""
Risk + AI + Scheduler + Telegram endpoint'leri.

- GET  /risk/state              : AppState özet (ayarlar)
- POST /risk/state              : AppState patch
- GET  /risk/status             : Canlı risk durumu (günlük PnL, açık poz vs.)
- POST /risk/circuit-breaker/reset : Manuel reset
- POST /risk/telegram/test      : Test mesajı
- POST /risk/ai/test             : Dummy sinyal ile AI testi
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_crypto
from app.models.app_state import AppState
from app.models.position import Position
from app.schemas.risk import (
    AiConnectionTestResult,
    AiTestRequest,
    AiTestResult,
    AppStateOut,
    AppStateUpdate,
    RiskStatusOut,
    TelegramTestResult,
)
from app.schemas.market import IndicatorValues, SmcAnalysis
from app.schemas.trading import SignalCore
from app.services.ai_validator import AiValidator
from app.services.risk_manager import RiskManager
from app.services.telegram_notifier import TelegramNotifier, get_notifier_from_state


router = APIRouter(prefix="/risk", tags=["risk"])


# ----------------------------------------------------------------------
# Yardımcılar
# ----------------------------------------------------------------------

def _get_state(db: Session) -> AppState:
    state = db.get(AppState, 1)
    if state is None:
        state = AppState(id=1)
        db.add(state)
        db.commit()
        db.refresh(state)
    return state


def _mask_token(token: str) -> str:
    if not token:
        return ""
    if len(token) <= 10:
        return "*" * len(token)
    return f"{token[:4]}...{token[-4:]}"


def _decrypt_if_needed(token: str) -> str:
    if not token:
        return ""
    return get_crypto().decrypt(token)


def _encrypt_if_needed(plaintext: str) -> str:
    if not plaintext:
        return ""
    return get_crypto().encrypt(plaintext)


def _state_to_out(state: AppState) -> AppStateOut:
    anthropic_plain = ""
    openai_plain = ""
    try:
        anthropic_plain = _decrypt_if_needed(getattr(state, "anthropic_api_key_enc", ""))
    except Exception:  # noqa: BLE001
        anthropic_plain = ""
    try:
        openai_plain = _decrypt_if_needed(getattr(state, "openai_api_key_enc", ""))
    except Exception:  # noqa: BLE001
        openai_plain = ""
    return AppStateOut(
        trading_mode=state.trading_mode,
        max_open_positions=state.max_open_positions,
        daily_loss_limit_usdt=state.daily_loss_limit_usdt,
        circuit_breaker_tripped=state.circuit_breaker_tripped,
        circuit_breaker_date=state.circuit_breaker_date,
        ai_enabled=state.ai_enabled,
        ai_min_confidence=state.ai_min_confidence,
        anthropic_api_key_masked=_mask_token(anthropic_plain),
        openai_api_key_masked=_mask_token(openai_plain),
        scheduler_enabled=state.scheduler_enabled,
        scheduler_interval_seconds=state.scheduler_interval_seconds,
        live_auto_trading_enabled=getattr(state, "live_auto_trading_enabled", False),
        telegram_enabled=state.telegram_enabled,
        telegram_bot_token_masked=_mask_token(state.telegram_bot_token),
        telegram_chat_id=state.telegram_chat_id,
        updated_at=state.updated_at,
    )


# ----------------------------------------------------------------------
# State
# ----------------------------------------------------------------------

@router.get("/state", response_model=AppStateOut)
def get_risk_state(db: Session = Depends(get_db)) -> AppStateOut:
    return _state_to_out(_get_state(db))


@router.post("/state", response_model=AppStateOut)
def update_risk_state(
    payload: AppStateUpdate,
    db: Session = Depends(get_db),
) -> AppStateOut:
    state = _get_state(db)
    changed: list[str] = []

    for field in (
        "max_open_positions", "daily_loss_limit_usdt",
        "ai_enabled", "ai_min_confidence",
        "scheduler_enabled", "scheduler_interval_seconds",
        "live_auto_trading_enabled",
        "telegram_enabled", "telegram_chat_id",
    ):
        val = getattr(payload, field)
        if val is not None:
            setattr(state, field, val)
            changed.append(field)

    # Token özel işlem — boşsa atla, "***" gönderilirse koruyucu
    if payload.telegram_bot_token is not None:
        if payload.telegram_bot_token and "..." not in payload.telegram_bot_token:
            state.telegram_bot_token = payload.telegram_bot_token
            changed.append("telegram_bot_token")
        elif payload.telegram_bot_token == "":
            state.telegram_bot_token = ""
            changed.append("telegram_bot_token_cleared")

    # Anthropic API key — şifreli saklanır
    if payload.anthropic_api_key is not None:
        if payload.anthropic_api_key and "..." not in payload.anthropic_api_key:
            state.anthropic_api_key_enc = _encrypt_if_needed(payload.anthropic_api_key)
            changed.append("anthropic_api_key_set")
        elif payload.anthropic_api_key == "":
            state.anthropic_api_key_enc = ""
            changed.append("anthropic_api_key_cleared")

    # OpenAI API key — şifreli saklanır
    if payload.openai_api_key is not None:
        if payload.openai_api_key and "..." not in payload.openai_api_key:
            state.openai_api_key_enc = _encrypt_if_needed(payload.openai_api_key)
            changed.append("openai_api_key_set")
        elif payload.openai_api_key == "":
            state.openai_api_key_enc = ""
            changed.append("openai_api_key_cleared")

    db.commit()
    db.refresh(state)
    logger.info("AppState güncellendi: {}", changed)
    return _state_to_out(state)


# ----------------------------------------------------------------------
# Status (canlı)
# ----------------------------------------------------------------------

@router.get("/status", response_model=RiskStatusOut)
def get_risk_status(db: Session = Depends(get_db)) -> RiskStatusOut:
    state = _get_state(db)
    risk = RiskManager(db)
    risk.refresh_circuit_breaker(state, state.trading_mode)
    db.refresh(state)

    pnl = risk.daily_realized_pnl(state.trading_mode)
    open_count = (
        db.query(Position)
        .filter(
            Position.mode == state.trading_mode,
            Position.status == "open",
        )
        .count()
    )

    from app.models.api_credentials import ApiCredentials
    bitget_ok = (
        db.query(ApiCredentials)
        .filter_by(provider="bitget", is_active=True)
        .first()
    ) is not None

    return RiskStatusOut(
        trading_mode=state.trading_mode,
        daily_pnl_usdt=round(pnl, 4),
        daily_loss_limit_usdt=state.daily_loss_limit_usdt,
        circuit_breaker_tripped=state.circuit_breaker_tripped,
        circuit_breaker_date=state.circuit_breaker_date,
        open_positions_count=open_count,
        max_open_positions=state.max_open_positions,
        bitget_connected=bitget_ok,
    )


@router.post("/circuit-breaker/reset", response_model=RiskStatusOut)
def reset_circuit_breaker(db: Session = Depends(get_db)) -> RiskStatusOut:
    risk = RiskManager(db)
    risk.reset_circuit_breaker()
    return get_risk_status(db)


# ----------------------------------------------------------------------
# Telegram test
# ----------------------------------------------------------------------

@router.post("/telegram/test", response_model=TelegramTestResult)
def test_telegram(db: Session = Depends(get_db)) -> TelegramTestResult:
    state = _get_state(db)
    if not state.telegram_bot_token or not state.telegram_chat_id:
        return TelegramTestResult(
            ok=False, message="Bot token ve chat ID girilmemiş."
        )
    notifier = TelegramNotifier(state.telegram_bot_token, state.telegram_chat_id)
    ok = notifier.send(
        "🤖 *AlfaPro Bot test mesajı*\nBağlantı başarılı."
    )
    return TelegramTestResult(
        ok=ok,
        message="Mesaj gönderildi." if ok else "Mesaj gönderilemedi — loglara bak.",
    )


# ----------------------------------------------------------------------
# AI test
# ----------------------------------------------------------------------

@router.post("/ai/test", response_model=AiTestResult)
def test_ai(
    payload: AiTestRequest,
    db: Session = Depends(get_db),
) -> AiTestResult:
    """
    Dummy sinyal üret, Claude'a gönder, yanıtı döndür.
    Gerçek market verisi olmadan prompt'un çalışıp çalışmadığını test eder.
    """
    state = _get_state(db)
    if not state.ai_enabled:
        return AiTestResult(
            ok=False, notes="AI devre dışı (risk/state'ten aç)",
            error="ai_enabled=false",
        )

    validator = AiValidator(
        enabled=True,
        min_confidence=state.ai_min_confidence,
    )

    # Öncelik: DB (panelden girilen) → env
    try:
        db_key = _decrypt_if_needed(getattr(state, "anthropic_api_key_enc", ""))
    except Exception:  # noqa: BLE001
        db_key = ""
    if db_key:
        validator = AiValidator(
            api_key=db_key,
            enabled=True,
            min_confidence=state.ai_min_confidence,
        )
    if not validator.api_key:
        return AiTestResult(
            ok=False,
            notes="Anthropic API key yok (Risk & AI sekmesinden gir veya .env ANTHROPIC_API_KEY).",
            error="no_api_key",
        )

    # Dummy sinyal
    dummy = SignalCore(
        strategy_id="test",
        symbol=payload.symbol,
        timeframe="15m",
        side=payload.side,  # type: ignore[arg-type]
        entry_price=65000.0 if payload.side == "long" else 65000.0,
        stop_loss=64000.0 if payload.side == "long" else 66000.0,
        take_profit=67000.0 if payload.side == "long" else 63000.0,
        confidence=70.0,
        reasoning=["Test amaçlı dummy sinyal"],
        ts=0,
    )
    dummy_ind = IndicatorValues(rsi=55.0, macd_hist=10.0, atr=500.0)
    dummy_smc = SmcAnalysis(current_trend="bullish" if payload.side == "long" else "bearish")

    try:
        verdict = validator.validate(dummy, dummy_ind, dummy_smc)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"AI hatası: {e}") from e

    return AiTestResult(
        ok=verdict.confidence is not None,
        confidence=verdict.confidence,
        notes=verdict.notes,
    )


@router.post("/ai/connection-test", response_model=AiConnectionTestResult)
def test_ai_connection(db: Session = Depends(get_db)) -> AiConnectionTestResult:
    """
    AI bağlantı testi (key + Anthropic erişimi).
    Bu test ai_enabled bayrağından bağımsızdır.
    """
    state = _get_state(db)

    # Öncelik: DB (panelde kaydedilen) → env
    db_key = ""
    try:
        db_key = _decrypt_if_needed(getattr(state, "anthropic_api_key_enc", ""))
    except Exception:  # noqa: BLE001
        db_key = ""

    validator = AiValidator(api_key=db_key or None, enabled=True)
    if not validator.api_key:
        return AiConnectionTestResult(
            ok=False,
            message="Anthropic API key yok. Ayarlar sekmesinden kaydet veya .env kullan.",
            error="no_api_key",
        )

    ok, msg, latency = validator.test_connection()
    if ok:
        err_code = None
    else:
        msg_l = msg.lower()
        if "credit balance is too low" in msg_l or "purchase credits" in msg_l:
            err_code = "insufficient_credits"
        elif "authentication_error" in msg_l or "invalid x-api-key" in msg_l:
            err_code = "auth_failed"
        else:
            err_code = "connection_failed"
    return AiConnectionTestResult(
        ok=ok,
        message=msg,
        latency_ms=latency,
        error=err_code,
    )


@router.post("/openai/connection-test", response_model=AiConnectionTestResult)
def test_openai_connection(db: Session = Depends(get_db)) -> AiConnectionTestResult:
    """
    OpenAI bağlantı testi (key + API erişimi).
    """
    state = _get_state(db)
    db_key = ""
    try:
        db_key = _decrypt_if_needed(getattr(state, "openai_api_key_enc", ""))
    except Exception:  # noqa: BLE001
        db_key = ""

    if not db_key:
        return AiConnectionTestResult(
            ok=False,
            message="OpenAI API key yok. Ayarlar sekmesinden kaydet.",
            error="no_api_key",
        )

    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {db_key}"},
            )
        if r.status_code == 200:
            return AiConnectionTestResult(
                ok=True,
                message="OpenAI bağlantısı başarılı.",
            )
        body = r.text[:300]
        msg_l = body.lower()
        if "insufficient_quota" in msg_l or "billing" in msg_l:
            err = "insufficient_credits"
        elif "invalid_api_key" in msg_l or r.status_code == 401:
            err = "auth_failed"
        else:
            err = "connection_failed"
        return AiConnectionTestResult(
            ok=False,
            message=f"OpenAI bağlantı hatası (HTTP {r.status_code}): {body}",
            error=err,
        )
    except Exception as e:  # noqa: BLE001
        return AiConnectionTestResult(
            ok=False,
            message=f"OpenAI bağlantı hatası: {e}",
            error="connection_failed",
        )
