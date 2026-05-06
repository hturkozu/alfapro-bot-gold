"""
İşlem geçmişi istatistikleri.

Kapanmış pozisyonlar üzerinden:
    - Toplam işlem, kazanan, kaybeden
    - Win rate, average win, average loss
    - Net PnL, largest win, largest loss
    - Profit factor (kazanç toplamı / kayıp toplamı)
    - Strateji bazında breakdown
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.position import Position


def compute_stats(
    db: Session,
    mode: str | None = None,
    strategy_id: str | None = None,
) -> dict[str, Any]:
    """Kapalı pozisyonlar için agregat istatistik."""
    q = db.query(Position).filter(Position.status != "open")
    if mode:
        q = q.filter(Position.mode == mode)
    if strategy_id:
        q = q.filter(Position.strategy_id == strategy_id)

    closed = q.all()

    total = len(closed)
    if total == 0:
        return {
            "total": 0, "wins": 0, "losses": 0, "breakeven": 0,
            "win_rate": 0.0, "net_pnl": 0.0,
            "avg_win": 0.0, "avg_loss": 0.0,
            "largest_win": 0.0, "largest_loss": 0.0,
            "profit_factor": 0.0, "expectancy": 0.0,
            "by_strategy": {},
        }

    wins = [p for p in closed if (p.pnl_usdt or 0) > 0]
    losses = [p for p in closed if (p.pnl_usdt or 0) < 0]
    breakeven = total - len(wins) - len(losses)

    total_win_pnl = sum(p.pnl_usdt or 0 for p in wins)
    total_loss_pnl = sum(p.pnl_usdt or 0 for p in losses)
    net_pnl = sum(p.pnl_usdt or 0 for p in closed)

    avg_win = (total_win_pnl / len(wins)) if wins else 0.0
    avg_loss = (total_loss_pnl / len(losses)) if losses else 0.0

    largest_win = max((p.pnl_usdt or 0 for p in wins), default=0.0)
    largest_loss = min((p.pnl_usdt or 0 for p in losses), default=0.0)

    win_rate = (len(wins) / total * 100) if total > 0 else 0.0
    # Profit factor = gross wins / gross losses (loss mutlak)
    profit_factor = (
        (total_win_pnl / abs(total_loss_pnl))
        if total_loss_pnl < 0 else 0.0
    )
    # Expectancy = (wr * avg_win) + ((1-wr) * avg_loss), yüzde cinsinden wr
    wr_frac = win_rate / 100
    expectancy = wr_frac * avg_win + (1 - wr_frac) * avg_loss

    # Strateji breakdown'u
    by_strategy: dict[str, dict[str, Any]] = {}
    for p in closed:
        sid = p.strategy_id or "unknown"
        bucket = by_strategy.setdefault(
            sid, {"total": 0, "wins": 0, "losses": 0, "net_pnl": 0.0}
        )
        bucket["total"] += 1
        pnl = p.pnl_usdt or 0
        if pnl > 0:
            bucket["wins"] += 1
        elif pnl < 0:
            bucket["losses"] += 1
        bucket["net_pnl"] += pnl

    for sid, b in by_strategy.items():
        b["net_pnl"] = round(b["net_pnl"], 4)
        b["win_rate"] = (
            round(b["wins"] / b["total"] * 100, 2) if b["total"] else 0.0
        )

    return {
        "total": total,
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": breakeven,
        "win_rate": round(win_rate, 2),
        "net_pnl": round(net_pnl, 4),
        "avg_win": round(avg_win, 4),
        "avg_loss": round(avg_loss, 4),
        "largest_win": round(largest_win, 4),
        "largest_loss": round(largest_loss, 4),
        "profit_factor": round(profit_factor, 3),
        "expectancy": round(expectancy, 4),
        "by_strategy": by_strategy,
    }
