"""
Risk yönetimi servisi.

Bir sinyal pozisyona dönüştürülmeden önce burada süzgeçten geçer:
    1. Circuit breaker (günlük zarar kilidi)
    2. Max açık pozisyon limiti
    3. Pozisyon büyüklüğü hesaplama (sabit USDT / Kelly Criterion)
    4. ATR tabanlı SL/TP override (isteğe bağlı)

Tüm kararlar DB'deki AppState'den okunur. Değiştirilmek istenirse panel üzerinden.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from loguru import logger
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.app_state import AppState
from app.models.position import Position


@dataclass
class RiskDecision:
    """Açma öncesi risk kontrolü sonucu."""

    allowed: bool
    reason: str = ""
    # Onaylanmışsa uygulanacak
    size_usdt: float = 0.0
    leverage: int = 1


class RiskManager:
    """Risk limitlerini değerlendiren karar motoru."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Günlük PnL & circuit breaker
    # ------------------------------------------------------------------

    def daily_realized_pnl(self, mode: str) -> float:
        """Bugün kapanan pozisyonların toplam PnL'i (USDT)."""
        today = date.today()
        start_of_day = datetime.combine(today, datetime.min.time())

        result = (
            self.db.query(func.coalesce(func.sum(Position.pnl_usdt), 0.0))
            .filter(
                Position.mode == mode,
                Position.status != "open",
                Position.closed_at >= start_of_day,
            )
            .scalar()
        )
        return float(result or 0.0)

    def refresh_circuit_breaker(self, state: AppState, mode: str) -> None:
        """
        Her çağrıda günü kontrol et. Gün değiştiyse breaker'ı sıfırla.
        Bugünkü zarar limiti aştıysa breaker'ı TRİP'le.
        """
        today_str = date.today().isoformat()

        # Yeni gün — reset
        if state.circuit_breaker_date != today_str:
            state.circuit_breaker_date = today_str
            state.circuit_breaker_tripped = False
            self.db.commit()

        # Limit aşıldı mı?
        pnl = self.daily_realized_pnl(mode)
        if pnl <= -abs(state.daily_loss_limit_usdt):
            if not state.circuit_breaker_tripped:
                state.circuit_breaker_tripped = True
                self.db.commit()
                logger.warning(
                    "CIRCUIT BREAKER TRIPPED: günlük PnL={:.2f} USDT < limit={:.2f}",
                    pnl, -abs(state.daily_loss_limit_usdt),
                )

    def reset_circuit_breaker(self) -> None:
        """Manuel reset (panelden)."""
        state = self.db.get(AppState, 1)
        if state is not None:
            state.circuit_breaker_tripped = False
            state.circuit_breaker_date = date.today().isoformat()
            self.db.commit()
            logger.info("Circuit breaker manuel olarak resetlendi.")

    # ------------------------------------------------------------------
    # Pozisyon boyutu hesaplama
    # ------------------------------------------------------------------

    @staticmethod
    def kelly_size(
        balance_usdt: float,
        win_rate: float,
        avg_win_pct: float,
        avg_loss_pct: float,
        kelly_fraction: float = 0.5,
    ) -> float:
        """
        Kelly Criterion — yarı Kelly (full Kelly agresif).
        f* = W - (1 - W) / R   where W = win_rate, R = avg_win/avg_loss
        """
        if avg_loss_pct <= 0 or win_rate <= 0:
            return 0.0
        R = avg_win_pct / avg_loss_pct
        if R <= 0:
            return 0.0
        kelly = win_rate - (1 - win_rate) / R
        kelly = max(0.0, kelly) * kelly_fraction
        return balance_usdt * kelly

    # ------------------------------------------------------------------
    # Ana karar verici
    # ------------------------------------------------------------------

    def evaluate_open(
        self,
        *,
        requested_size_usdt: float,
        requested_leverage: int,
        mode: str,
    ) -> RiskDecision:
        """
        Pozisyon açılmadan ÖNCE çağrılır. Limitleri kontrol eder.
        İzin verirse önerilen size/leverage döner.
        """
        state = self.db.get(AppState, 1)
        if state is None:
            return RiskDecision(
                allowed=False, reason="AppState initialize edilmemiş."
            )

        # 1) Circuit breaker
        self.refresh_circuit_breaker(state, mode)
        if state.circuit_breaker_tripped:
            return RiskDecision(
                allowed=False,
                reason=(
                    f"Günlük zarar limiti aşıldı "
                    f"({-abs(state.daily_loss_limit_usdt):.2f} USDT). "
                    "Yeni pozisyon açma kilitlendi. "
                    "Manuel reset gerekli."
                ),
            )

        # 2) Max açık pozisyon
        open_count = (
            self.db.query(Position)
            .filter(Position.mode == mode, Position.status == "open")
            .count()
        )
        if open_count >= state.max_open_positions:
            return RiskDecision(
                allowed=False,
                reason=(
                    f"Açık pozisyon limiti dolu "
                    f"({open_count}/{state.max_open_positions})"
                ),
            )

        # 3) Boyut sanity
        size = float(requested_size_usdt)
        lev = int(requested_leverage)
        if size <= 0:
            return RiskDecision(allowed=False, reason="Size_usdt > 0 olmalı")
        if lev < 1 or lev > 125:
            return RiskDecision(
                allowed=False, reason=f"Kaldıraç 1-125 aralığında olmalı (gelen: {lev})"
            )

        return RiskDecision(allowed=True, size_usdt=size, leverage=lev)
