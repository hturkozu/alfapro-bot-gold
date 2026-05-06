"""
WebSocket endpoint — gerçek zamanlı panel güncellemeleri.

Her bağlı client'a 3 saniyede bir JSON push:
  { positions, signals, scheduler_enabled, trading_mode }

Bağlantı koparsa client exponential backoff ile yeniden bağlanır.
"""
from __future__ import annotations

import asyncio
import json  # send_text için
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from app.core.database import SessionLocal
from app.models.app_state import AppState
from app.models.position import Position
from app.models.signal import Signal

router = APIRouter(tags=["ws"])

PUSH_INTERVAL = 3  # saniye


def _snapshot() -> dict:
    """DB'den anlık durum yükle."""
    with SessionLocal() as db:
        state: AppState | None = db.get(AppState, 1)

        positions = (
            db.query(Position)
            .filter(Position.status == "open")
            .order_by(Position.id.desc())
            .limit(50)
            .all()
        )
        signals = (
            db.query(Signal)
            .order_by(Signal.id.desc())
            .limit(20)
            .all()
        )

        def _pos(p: Position) -> dict:
            return {
                "id": p.id,
                "symbol": p.symbol,
                "side": p.side,
                "mode": p.mode,
                "status": p.status,
                "entry_price": p.entry_price,
                "stop_loss": p.stop_loss,
                "take_profit": p.take_profit,
                "size_usdt": p.size_usdt,
                "leverage": p.leverage,
                "pnl_usdt": p.pnl_usdt,
                "strategy_id": p.strategy_id,
                "opened_at": p.opened_at.isoformat() if p.opened_at else None,
            }

        def _sig(s: Signal) -> dict:
            return {
                "id": s.id,
                "strategy_id": s.strategy_id,
                "symbol": s.symbol,
                "timeframe": s.timeframe,
                "side": s.side,
                "entry_price": s.entry_price,
                "stop_loss": s.stop_loss,
                "take_profit": s.take_profit,
                "confidence": s.confidence,
                "executed": s.executed,
                "ai_approved": s.ai_approved,
                "ai_confidence": s.ai_confidence,
                "reasoning": [r.strip() for r in (s.reasoning or "").split("|") if r.strip()],
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }

        return {
            "type": "snapshot",
            "ts": datetime.utcnow().isoformat(),
            "trading_mode": state.trading_mode if state else "paper",
            "scheduler_enabled": state.scheduler_enabled if state else False,
            "positions": [_pos(p) for p in positions],
            "signals": [_sig(s) for s in signals],
        }


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    client = ws.client.host if ws.client else "unknown"
    logger.info("WS bağlantı kuruldu: {}", client)

    try:
        while True:
            try:
                data = await asyncio.get_event_loop().run_in_executor(None, _snapshot)
                await ws.send_text(json.dumps(data))
            except Exception as e:  # noqa: BLE001
                logger.warning("WS snapshot hatası: {}", e)

            # PUSH_INTERVAL kadar bekle ama client mesaj gönderirse de oku
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=PUSH_INTERVAL)
            except asyncio.TimeoutError:
                pass  # Normal: push interval doldu
            except WebSocketDisconnect:
                break

    except WebSocketDisconnect:
        pass
    finally:
        logger.info("WS bağlantı kapandı: {}", client)
