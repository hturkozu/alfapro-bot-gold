"""
Arka plan zamanlayıcı (scheduler).

Her tick'te:
  1. AppState.scheduler_enabled kontrolü
  2. Real-time fiyat geçmişi güncelleme (momentum için)
  3. Açık paper pozisyonlarda SL/TP kontrolü
  4. Aktif stratejilerin değerlendirilmesi
     - Duplicate / cooldown / ardışık kayıp / kill switch korumaları
     - Sinyal → AI → Risk → Pozisyon aç
"""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from datetime import datetime, timedelta

from loguru import logger

from app.core.database import SessionLocal
from app.core.security import get_crypto
from app.models.api_credentials import ApiCredentials
from app.models.app_state import AppState
from app.models.position import Position
from app.models.strategy_config import StrategyConfig
from app.services.ai_validator import AiValidator
from app.services.fibonacci import compute_fibonacci
from app.services.indicators import compute_indicators
from app.services.market_data import MarketDataService, get_market_service
from app.services.paper_trader import PaperTrader
from app.services.risk_manager import RiskManager
from app.services.smc import compute_smc
from app.services.strategies import get_strategy
from app.services.strategies.base import StrategyContext
from app.services.telegram_notifier import get_notifier_from_state


class Scheduler:
    """Tek sefer başlatılan arka plan döngüsü."""

    # Varsayılan cooldown — strateji parametresinden override edilir
    DEFAULT_COOLDOWN_SECONDS = 300

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

        # Real-time fiyat geçmişi: {symbol: [(monotonic_ts, price), ...]}
        # Momentum hesabı için son 30 saniye tutulur
        self._price_history: dict[str, list[tuple[float, float]]] = defaultdict(list)

        # Kill switch: günlük kayıp eşiği aşıldıysa tüm girişleri durdur
        # Key: mod ("paper"|"live"), value: True = aktif
        self._kill_switch: dict[str, bool] = {}
        self._kill_switch_date: str = ""

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="alfapro-scheduler")
        logger.info("Scheduler task baslatildi.")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=3.0)
            except asyncio.TimeoutError:
                self._task.cancel()
        logger.info("Scheduler durduruldu.")

    # ------------------------------------------------------------------
    # Ana döngü
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        while not self._stop.is_set():
            interval = 60
            try:
                interval = await asyncio.get_event_loop().run_in_executor(
                    None, self._tick
                )
            except Exception as e:  # noqa: BLE001
                logger.error("Scheduler tick hatasi: {}", e)
                interval = 15

            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    def _tick(self) -> int:
        with SessionLocal() as db:
            state = db.get(AppState, 1)
            if state is None:
                return 30

            if not state.scheduler_enabled:
                return 10

            logger.info("Scheduler tick -- {}", datetime.utcnow().isoformat())

            # Kill switch günlük sıfırlama
            self._reset_kill_switch_if_new_day()

            # Paper pozisyonlarda SL/TP kontrolü
            self._check_paper_positions(db)

            # Aktif stratejileri değerlendir
            self._evaluate_active_strategies(db, state)

            interval = max(2, int(state.scheduler_interval_seconds))
            return interval

    # ------------------------------------------------------------------
    # Kill switch
    # ------------------------------------------------------------------

    def _reset_kill_switch_if_new_day(self) -> None:
        today = datetime.utcnow().date().isoformat()
        if self._kill_switch_date != today:
            self._kill_switch.clear()
            self._kill_switch_date = today
            logger.debug("Kill switch gunu sifirlandi: {}", today)

    def _check_kill_switch(
        self,
        db,
        mode: str,
        drawdown_pct: float,
        ref_balance: float,
    ) -> bool:
        """
        Günlük kayıp ref_balance'ın drawdown_pct yüzdesini aştıysa True döner.
        True → yeni pozisyon açma!
        """
        if self._kill_switch.get(mode, False):
            return True
        if ref_balance <= 0 or drawdown_pct <= 0:
            return False
        risk = RiskManager(db)
        daily_pnl = risk.daily_realized_pnl(mode)
        threshold = -(ref_balance * drawdown_pct / 100.0)
        if daily_pnl < threshold:
            self._kill_switch[mode] = True
            logger.warning(
                "KILL SWITCH aktif! Gunluk PnL={:.2f} < esik={:.2f} USDT (mod={})",
                daily_pnl, threshold, mode,
            )
            return True
        return False

    # ------------------------------------------------------------------
    # Real-time fiyat geçmişi
    # ------------------------------------------------------------------

    def _update_price_history(self, symbol: str, price: float) -> None:
        now = time.monotonic()
        history = self._price_history[symbol]
        history.append((now, price))
        # Son 30 saniyeyi tut
        cutoff = now - 30.0
        self._price_history[symbol] = [(t, p) for t, p in history if t >= cutoff]

    def _check_momentum(
        self,
        symbol: str,
        side: str,
        atr: float,
        threshold: float,
        window_sec: float,
    ) -> bool:
        """
        Fiyat son `window_sec` saniyede `threshold * ATR` kadar
        sinyal yönünde hareket etti mi?
        """
        history = self._price_history.get(symbol, [])
        if not history:
            return True  # Geçmiş yok → geç (ilk tick'te engelleme)

        now = time.monotonic()
        cutoff = now - window_sec

        # window_sec öncesindeki en yakın fiyat
        past_entries = [(t, p) for t, p in history if t <= cutoff]
        if past_entries:
            past_price = past_entries[-1][1]
        elif len(history) >= 2:
            past_price = history[-2][1]  # yeterli geçmiş yok, önceki tick kullan
        else:
            return True  # yetersiz veri → geç

        current_price = history[-1][1]
        min_move = threshold * atr
        delta = current_price - past_price

        if side == "long":
            ok = delta >= min_move
        else:
            ok = delta <= -min_move

        if not ok:
            logger.debug(
                "Momentum yok: {} {} delta={:.6f} gerekli={:.6f}",
                symbol, side, delta, min_move if side == "long" else -min_move,
            )
        return ok

    # ------------------------------------------------------------------
    # Ardışık kayıp kontrolü
    # ------------------------------------------------------------------

    @staticmethod
    def _count_consecutive_losses(
        db,
        strategy_id: str,
        symbol: str,
        mode: str,
    ) -> int:
        """Son kapanan pozisyonlarda ardışık kayıp sayısını döndürür."""
        recent = (
            db.query(Position)
            .filter(
                Position.strategy_id == strategy_id,
                Position.symbol == symbol,
                Position.mode == mode,
                Position.status != "open",
                Position.closed_at.isnot(None),
            )
            .order_by(Position.closed_at.desc())
            .limit(10)
            .all()
        )
        count = 0
        for pos in recent:
            if pos.pnl_usdt is not None and pos.pnl_usdt < 0:
                count += 1
            else:
                break
        return count

    # ------------------------------------------------------------------
    # Canlı (incomplete) 1m mum çekme — wick-bazlı SL/TP için
    # ------------------------------------------------------------------

    @staticmethod
    def _fetch_live_bar(
        svc: MarketDataService,
        symbol: str,
    ) -> tuple[float | None, float | None]:
        """
        Sembolün son 1m mumunun (high, low) değerlerini döner.
        Tick'ler arası wick'lerin SL/TP'yi vurup vurmadığını anlamak için.
        Hata olursa (None, None) — caller mevcut fiyatla yetinir.
        """
        try:
            rows = svc.get_candles(symbol, timeframe="1m", limit=2)
            if not rows:
                return None, None
            # Son satır canlı (henüz kapanmamış) bar olabilir; yine de en güncel
            # high/low onda. Kapanmış bar varsa tek başına yeterli.
            last = rows[-1]
            return float(last[2]), float(last[3])  # [ts, o, h, l, c, v]
        except Exception as e:  # noqa: BLE001
            logger.debug("Canli bar cekilemedi {}: {}", symbol, e)
            return None, None

    # ------------------------------------------------------------------
    # Paper pozisyon SL/TP kontrolü
    # ------------------------------------------------------------------

    def _check_paper_positions(self, db) -> None:
        open_positions = (
            db.query(Position)
            .filter(Position.mode == "paper", Position.status == "open")
            .all()
        )
        if not open_positions:
            return

        cred = (
            db.query(ApiCredentials)
            .filter_by(provider="bitget", is_active=True).first()
        )
        svc = get_market_service(db, credentials=cred)
        trader = PaperTrader(db)

        price_cache: dict[str, float] = {}
        # Sembol başına canlı 1m mumun (high, low)'u — wick-bazlı SL/TP için
        bar_cache: dict[str, tuple[float | None, float | None]] = {}
        for pos in open_positions:
            try:
                if pos.symbol not in price_cache:
                    tk = svc.get_ticker_summary(pos.symbol)
                    last = tk.get("last")
                    if last is None:
                        continue
                    price_cache[pos.symbol] = float(last)
                    # Fiyat geçmişini güncelle
                    self._update_price_history(pos.symbol, float(last))

                if pos.symbol not in bar_cache:
                    bar_cache[pos.symbol] = self._fetch_live_bar(svc, pos.symbol)

                bar_high, bar_low = bar_cache[pos.symbol]

                # Önce trailing/BE — SL sıkıştır, sonra tetik kontrolü
                trader.apply_trailing(
                    pos,
                    price_cache[pos.symbol],
                    bar_high=bar_high,
                    bar_low=bar_low,
                )

                result = trader.check_sl_tp(
                    pos,
                    price_cache[pos.symbol],
                    bar_high=bar_high,
                    bar_low=bar_low,
                )
                if result is not None:
                    state = db.get(AppState, 1)
                    notifier = get_notifier_from_state(state) if state else None
                    if notifier:
                        db.refresh(pos)
                        notifier.notify_position_closed(pos)
            except Exception as e:  # noqa: BLE001
                logger.warning("Paper pos tick hatasi ({}): {}", pos.symbol, e)

    # ------------------------------------------------------------------
    # Strateji değerlendirme
    # ------------------------------------------------------------------

    def _evaluate_active_strategies(self, db, state: AppState) -> None:
        active_cfgs = (
            db.query(StrategyConfig)
            .filter(StrategyConfig.enabled == True)  # noqa: E712
            .all()
        )
        if not active_cfgs:
            logger.debug("Aktif strateji yok.")
            return

        cred = (
            db.query(ApiCredentials)
            .filter_by(provider="bitget", is_active=True).first()
        )
        svc = get_market_service(db, credentials=cred)
        risk = RiskManager(db)

        api_key = ""
        try:
            api_key = get_crypto().decrypt(getattr(state, "anthropic_api_key_enc", ""))
        except Exception:  # noqa: BLE001
            api_key = ""
        ai = AiValidator(
            api_key=api_key or None,
            enabled=state.ai_enabled,
            min_confidence=state.ai_min_confidence,
        )

        notifier = get_notifier_from_state(state)

        for cfg in active_cfgs:
            symbols  = cfg.symbols_list
            timeframes = cfg.timeframes_list
            if not symbols or not timeframes:
                continue

            for symbol in symbols:
                for tf in timeframes:
                    try:
                        self._evaluate_one(
                            db=db, svc=svc, cfg=cfg, symbol=symbol, tf=tf,
                            risk=risk, ai=ai, notifier=notifier, state=state,
                        )
                    except Exception as e:  # noqa: BLE001
                        logger.warning(
                            "Eval hatasi {} {} {}: {}",
                            cfg.strategy_id, symbol, tf, e,
                        )

    def _evaluate_one(
        self,
        *,
        db,
        svc: MarketDataService,
        cfg: StrategyConfig,
        symbol: str,
        tf: str,
        risk: RiskManager,
        ai: AiValidator,
        notifier,
        state: AppState,
    ) -> None:
        mode = state.trading_mode
        # Strategy default_params + DB'deki kullanıcı override'ları (DB öncelikli)
        try:
            from app.services.strategies.registry import _STRATEGIES
            _cls = _STRATEGIES.get(cfg.strategy_id)
            _defaults = dict(_cls.default_params) if _cls else {}
            params = {**_defaults, **(cfg.params or {})}
        except Exception:
            params = cfg.params or {}

        # ── Kill switch kontrolü ──────────────────────────────────────
        ks_drawdown = float(getattr(state, "kill_switch_drawdown_pct", 5.0))
        ks_balance  = float(getattr(state, "paper_balance_usdt", 1000.0))
        if self._check_kill_switch(db, mode, ks_drawdown, ks_balance):
            logger.info("Kill switch aktif — {} {} pas geciliyor", cfg.strategy_id, symbol)
            return

        # ── Ardışık kayıp kontrolü ───────────────────────────────────
        max_consec = int(params.get("max_consecutive_losses", 0))
        if max_consec > 0:
            consec = self._count_consecutive_losses(db, cfg.strategy_id, symbol, mode)
            if consec >= max_consec:
                logger.info(
                    "Ardisik kayip kesici: {} {} consec={}/{}",
                    cfg.strategy_id, symbol, consec, max_consec,
                )
                return

        # ── Açık pozisyon duplicate koruması ─────────────────────────
        existing = (
            db.query(Position)
            .filter(
                Position.symbol == symbol,
                Position.strategy_id == cfg.strategy_id,
                Position.status == "open",
                Position.mode == mode,
            )
            .first()
        )
        if existing is not None:
            logger.info(
                "Duplicate engellendi: {} {} acik poz id={}",
                cfg.strategy_id, symbol, existing.id,
            )
            return

        # ── Cooldown kontrolü ─────────────────────────────────────────
        cooldown_sec = int(params.get("cooldown_seconds", 0))
        if cooldown_sec > 0:
            cooldown_cutoff = datetime.utcnow() - timedelta(seconds=cooldown_sec)
            recent_closed = (
                db.query(Position)
                .filter(
                    Position.symbol == symbol,
                    Position.strategy_id == cfg.strategy_id,
                    Position.mode == mode,
                    Position.status != "open",
                    Position.closed_at > cooldown_cutoff,
                )
                .first()
            )
            if recent_closed is not None:
                elapsed = int((datetime.utcnow() - recent_closed.closed_at).total_seconds())
                logger.info(
                    "Cooldown aktif: {} {} {}s/{} s gecti",
                    cfg.strategy_id, symbol, elapsed, cooldown_sec,
                )
                return

        # ── Mum verisi ve indikatörler ────────────────────────────────
        rows = svc.get_candles(symbol, timeframe=tf, limit=300)
        if not rows:
            return

        ind_last, ind_series = compute_indicators(rows)
        fib = compute_fibonacci(rows)
        smc = compute_smc(rows)

        # Real-time fiyatı al ve geçmişe ekle
        ticker = svc.get_ticker_summary(symbol)
        rt_price = ticker.get("last")
        if rt_price is not None:
            self._update_price_history(symbol, float(rt_price))

        ctx = StrategyContext(
            symbol=symbol, timeframe=tf, candles=rows,
            ind_last=ind_last, ind_series=ind_series, fib=fib, smc=smc,
        )

        # ── Sinyal üret ───────────────────────────────────────────────
        strat = get_strategy(cfg.strategy_id, params=cfg.params)
        signal = strat.evaluate(ctx)
        if signal is None:
            logger.info(
                "Sinyal yok: {} {} {} (fiyat={:.6f})",
                cfg.strategy_id, symbol, tf, ctx.last_price,
            )
            return

        # ── Momentum doğrulaması (sweep stratejisi için) ───────────────
        momentum_threshold = float(params.get("momentum_threshold_atr", 0.0))
        momentum_window    = float(params.get("momentum_window_sec", 3.0))
        if momentum_threshold > 0 and ind_last.atr is not None:
            if not self._check_momentum(
                symbol, signal.side, ind_last.atr,
                momentum_threshold, momentum_window,
            ):
                logger.info(
                    "Momentum esigi karsılanmadi: {} {} esik={}xATR",
                    cfg.strategy_id, symbol, momentum_threshold,
                )
                return

        # ── AI doğrulama ──────────────────────────────────────────────
        verdict = ai.validate(signal, ind_last, smc, recent_candles=rows)

        trader = PaperTrader(db)
        db_sig = trader.persist_signal(signal)
        db_sig.ai_approved = verdict.approved
        db_sig.ai_confidence = verdict.confidence
        db_sig.ai_notes = verdict.notes
        db.commit()

        if not verdict.approved:
            logger.info(
                "Sinyal AI tarafından reddedildi: {} {} (ai_conf={})",
                signal.strategy_id, signal.symbol, verdict.confidence,
            )
            return

        # ── Risk kapısı ───────────────────────────────────────────────
        decision = risk.evaluate_open(
            requested_size_usdt=cfg.size_usdt,
            requested_leverage=cfg.leverage,
            mode=mode,
        )
        if not decision.allowed:
            logger.info("Risk kapisi: {}", decision.reason)
            if notifier and "limit" in decision.reason.lower():
                notifier.notify_circuit_breaker(
                    risk.daily_realized_pnl(mode),
                    state.daily_loss_limit_usdt,
                )
            return

        # ── Pozisyon aç ───────────────────────────────────────────────
        use_live = (
            mode == "live"
            and getattr(state, "live_auto_trading_enabled", False)
        )

        if use_live:
            try:
                from app.services.live_trader import get_live_trader
                live = get_live_trader(db)
                pos = live.open_from_signal(
                    signal,
                    size_usdt=decision.size_usdt,
                    leverage=decision.leverage,
                    signal_db_id=db_sig.id,
                )
            except Exception as e:  # noqa: BLE001
                logger.error("LIVE auto-trade hatasi: {}", e)
                if notifier:
                    notifier.send(
                        f"LIVE hata: {signal.symbol} {signal.side} — {e}"
                    )
                return
        elif mode == "live":
            logger.info(
                "LIVE mod, auto-trading kapali — sinyal kaydedildi, poz ACILMADI: {} {}",
                signal.strategy_id, signal.symbol,
            )
            if notifier:
                notifier.notify_signal(signal, ai_conf=verdict.confidence)
            return
        else:
            pos = trader.open_from_signal(
                signal,
                size_usdt=decision.size_usdt,
                leverage=decision.leverage,
                signal_db_id=db_sig.id,
            )

        db_sig.executed = True
        db_sig.position_id = pos.id
        db.commit()

        if notifier:
            notifier.notify_signal(signal, ai_conf=verdict.confidence)
            notifier.notify_position_opened(pos)

        logger.info(
            "Poz acildi: {} {} {} entry={:.6f} SL={:.6f} TP={:.6f}",
            cfg.strategy_id, symbol, signal.side,
            pos.entry_price, pos.stop_loss, pos.take_profit,
        )


# ----------------------------------------------------------------------
# Singleton
# ----------------------------------------------------------------------

_scheduler: Scheduler | None = None


def get_scheduler() -> Scheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = Scheduler()
    return _scheduler
