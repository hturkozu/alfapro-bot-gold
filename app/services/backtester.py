"""
Backtesting motoru (Faz 6).

Bir stratejiyi geçmiş OHLCV mumları üzerinde simüle eder:
  1. İndikatörler tüm veri seti üzerinde tek kez hesaplanır (verimlilik).
  2. Her mumda strateji evaluate() çağrılır (sliced seri ile lookahead yok).
  3. Açık pozisyon SL/TP'ye yüksek/düşük değerleriyle kontrol edilir.
  4. Son açık pozisyon son mumun kapanışından çıkarılır (force-close).
  5. Metrikler: win rate, profit factor, max drawdown, Sharpe ratio.
"""
from __future__ import annotations

import statistics
import time
from typing import Any

from loguru import logger

from app.schemas.backtest import (
    BacktestMetrics,
    BacktestRequest,
    BacktestResult,
    BacktestTrade,
)
from app.schemas.market import IndicatorSeries, IndicatorValues
from app.services.fibonacci import compute_fibonacci
from app.services.indicators import compute_indicators
from app.services.smc import compute_smc
from app.services.strategies import get_strategy
from app.services.strategies.base import StrategyContext

_MIN_WINDOW = 50  # indikatör ısınma periyodu (mum)


class Backtester:
    """Strateji simülatörü — gerçek emir göndermez."""

    def run(
        self,
        request: BacktestRequest,
        candles: list[list[float]],
    ) -> BacktestResult:
        t0 = time.time()
        n = len(candles)

        if n < _MIN_WINDOW + 10:
            logger.warning("Backtest: yetersiz mum ({} < {})", n, _MIN_WINDOW + 10)
            return self._empty_result(request, t0)

        # Tüm veri üzerinde bir kez hesapla (O(n) verimlilik)
        _, ind_series_full = compute_indicators(candles)
        smc_full = compute_smc(candles)
        fib_full = compute_fibonacci(candles)

        strat = get_strategy(request.strategy_id, params=request.params)

        trades: list[BacktestTrade] = []
        open_pos: dict[str, Any] | None = None
        signals_generated = 0

        for i in range(_MIN_WINDOW, n):
            c = candles[i]
            c_open = float(c[1])
            c_high = float(c[2])
            c_low  = float(c[3])
            c_close = float(c[4])
            ts = int(c[0])

            # Önce mevcut pozisyonda SL/TP kontrolü
            if open_pos is not None:
                trade = self._check_sl_tp(open_pos, c_open, c_high, c_low, c_close, ts, request)
                if trade is not None:
                    trades.append(trade)
                    open_pos = None
                    continue  # aynı mumda yeni pozisyon açma

            if open_pos is not None:
                continue  # pozisyon açık → sinyal üretme

            # Strateji bağlamını i anında oluştur (lookahead yok)
            ind_at_i = self._ind_at(ind_series_full, i)
            ind_series_sliced = self._series_slice(ind_series_full, i + 1)

            ctx = StrategyContext(
                symbol=request.symbol,
                timeframe=request.timeframe,
                candles=candles[: i + 1],
                ind_last=ind_at_i,
                ind_series=ind_series_sliced,
                fib=fib_full,
                smc=smc_full,
            )

            try:
                signal = strat.evaluate(ctx)
            except Exception as e:  # noqa: BLE001
                logger.debug("Backtest eval hatası i={}: {}", i, e)
                continue

            if signal is None:
                continue

            signals_generated += 1
            open_pos = {
                "side": signal.side,
                "entry_price": signal.entry_price,
                "sl": signal.stop_loss,
                "tp": signal.take_profit,
                "entry_ts": ts,
                "confidence": signal.confidence,
            }

        # Kalan açık pozisyonu kapat (force-close)
        if open_pos is not None and candles:
            last = candles[-1]
            trades.append(
                self._make_trade(open_pos, float(last[4]), int(last[0]), "end", request)
            )

        metrics = self._compute_metrics(trades, request.size_usdt)
        equity = self._equity_curve(trades)
        duration_ms = int((time.time() - t0) * 1000)

        logger.info(
            "Backtest tamamlandı: {} {} {} | {} işlem / {} sinyal | {:.0f}ms",
            request.strategy_id, request.symbol, request.timeframe,
            len(trades), signals_generated, duration_ms,
        )

        return BacktestResult(
            request=request,
            trades=trades,
            metrics=metrics,
            equity_curve=equity,
            candles_analyzed=n - _MIN_WINDOW,
            signals_generated=signals_generated,
            duration_ms=duration_ms,
        )

    # ------------------------------------------------------------------
    # SL / TP simülasyonu
    # ------------------------------------------------------------------

    def _check_sl_tp(
        self,
        pos: dict,
        c_open: float,
        c_high: float,
        c_low: float,
        c_close: float,
        ts: int,
        req: BacktestRequest,
    ) -> BacktestTrade | None:
        side = pos["side"]
        sl   = pos["sl"]
        tp   = pos["tp"]

        if side == "long":
            # Gap-down açılış: SL atlandı
            if c_open <= sl:
                return self._make_trade(pos, c_open, ts, "sl", req)
            if c_open >= tp:
                return self._make_trade(pos, c_open, ts, "tp", req)
            # Mum içi: muhafazakâr sıra — önce SL kontrol et
            if c_low <= sl:
                return self._make_trade(pos, sl, ts, "sl", req)
            if c_high >= tp:
                return self._make_trade(pos, tp, ts, "tp", req)
        else:  # short
            if c_open >= sl:
                return self._make_trade(pos, c_open, ts, "sl", req)
            if c_open <= tp:
                return self._make_trade(pos, c_open, ts, "tp", req)
            if c_high >= sl:
                return self._make_trade(pos, sl, ts, "sl", req)
            if c_low <= tp:
                return self._make_trade(pos, tp, ts, "tp", req)

        return None

    def _make_trade(
        self,
        pos: dict,
        exit_price: float,
        exit_ts: int,
        reason: str,
        req: BacktestRequest,
    ) -> BacktestTrade:
        side  = pos["side"]
        entry = pos["entry_price"]
        lev   = req.leverage

        if side == "long":
            pnl_pct = (exit_price - entry) / entry * 100.0 * lev
        else:
            pnl_pct = (entry - exit_price) / entry * 100.0 * lev

        pnl_usdt = req.size_usdt * pnl_pct / 100.0

        return BacktestTrade(
            side=side,  # type: ignore[arg-type]
            entry_price=round(entry, 8),
            exit_price=round(exit_price, 8),
            entry_ts=pos["entry_ts"],
            exit_ts=exit_ts,
            pnl_usdt=round(pnl_usdt, 4),
            pnl_pct=round(pnl_pct, 4),
            exit_reason=reason,  # type: ignore[arg-type]
            confidence=round(pos["confidence"], 2),
        )

    # ------------------------------------------------------------------
    # İndikatör yardımcıları
    # ------------------------------------------------------------------

    @staticmethod
    def _safe(lst: list, idx: int):
        if not lst or idx >= len(lst):
            return None
        return lst[idx]

    def _ind_at(self, series: IndicatorSeries, i: int) -> IndicatorValues:
        g = self._safe
        return IndicatorValues(
            ema={k: g(v, i) for k, v in series.ema.items()},
            rsi=g(series.rsi, i),
            macd=g(series.macd, i),
            macd_signal=g(series.macd_signal, i),
            macd_hist=g(series.macd_hist, i),
            atr=g(series.atr, i),
            bb_upper=g(series.bb_upper, i),
            bb_middle=g(series.bb_middle, i),
            bb_lower=g(series.bb_lower, i),
            vwap=g(series.vwap, i),
        )

    @staticmethod
    def _series_slice(series: IndicatorSeries, end: int) -> IndicatorSeries:
        return IndicatorSeries(
            ts=series.ts[:end],
            ema={k: v[:end] for k, v in series.ema.items()},
            rsi=series.rsi[:end],
            macd=series.macd[:end],
            macd_signal=series.macd_signal[:end],
            macd_hist=series.macd_hist[:end],
            atr=series.atr[:end],
            bb_upper=series.bb_upper[:end],
            bb_middle=series.bb_middle[:end],
            bb_lower=series.bb_lower[:end],
            vwap=series.vwap[:end],
        )

    # ------------------------------------------------------------------
    # Metrik hesaplama
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_metrics(
        trades: list[BacktestTrade],
        size_usdt: float,
    ) -> BacktestMetrics:
        empty = BacktestMetrics(
            total_trades=0, win_trades=0, loss_trades=0,
            win_rate=0.0, total_pnl_usdt=0.0, total_pnl_pct=0.0,
            profit_factor=0.0, max_drawdown_pct=0.0, sharpe_ratio=0.0,
            avg_trade_pnl_usdt=0.0, best_trade_pnl_usdt=0.0,
            worst_trade_pnl_usdt=0.0,
        )
        if not trades:
            return empty

        wins   = [t for t in trades if t.pnl_usdt > 0]
        losses = [t for t in trades if t.pnl_usdt <= 0]

        total_pnl    = sum(t.pnl_usdt for t in trades)
        gross_profit = sum(t.pnl_usdt for t in wins)   if wins   else 0.0
        gross_loss   = abs(sum(t.pnl_usdt for t in losses)) if losses else 0.0
        pf = (gross_profit / gross_loss) if gross_loss > 0 else 999.0

        # Max drawdown (peak-to-trough)
        equity: list[float] = [size_usdt]
        for t in trades:
            equity.append(equity[-1] + t.pnl_usdt)
        peak   = equity[0]
        max_dd = 0.0
        for e in equity:
            if e > peak:
                peak = e
            if peak > 0:
                dd = (peak - e) / peak * 100.0
                if dd > max_dd:
                    max_dd = dd

        # Sharpe ratio (trade PnL % serisi bazlı)
        returns = [t.pnl_pct for t in trades]
        if len(returns) > 1:
            avg_r = statistics.mean(returns)
            std_r = statistics.stdev(returns)
            sharpe = (avg_r / std_r) * (len(returns) ** 0.5) if std_r > 0 else 0.0
        else:
            sharpe = 0.0

        return BacktestMetrics(
            total_trades=len(trades),
            win_trades=len(wins),
            loss_trades=len(losses),
            win_rate=round(len(wins) / len(trades) * 100, 2),
            total_pnl_usdt=round(total_pnl, 4),
            total_pnl_pct=round(total_pnl / size_usdt * 100, 4),
            profit_factor=round(min(pf, 999.0), 4),
            max_drawdown_pct=round(max_dd, 4),
            sharpe_ratio=round(sharpe, 4),
            avg_trade_pnl_usdt=round(total_pnl / len(trades), 4),
            best_trade_pnl_usdt=round(max(t.pnl_usdt for t in trades), 4),
            worst_trade_pnl_usdt=round(min(t.pnl_usdt for t in trades), 4),
        )

    @staticmethod
    def _equity_curve(trades: list[BacktestTrade]) -> list[float]:
        curve = [0.0]
        for t in trades:
            curve.append(round(curve[-1] + t.pnl_usdt, 4))
        return curve

    # ------------------------------------------------------------------
    # Boş sonuç yardımcısı
    # ------------------------------------------------------------------

    @staticmethod
    def _empty_result(req: BacktestRequest, t0: float) -> BacktestResult:
        return BacktestResult(
            request=req,
            trades=[],
            metrics=BacktestMetrics(
                total_trades=0, win_trades=0, loss_trades=0,
                win_rate=0.0, total_pnl_usdt=0.0, total_pnl_pct=0.0,
                profit_factor=0.0, max_drawdown_pct=0.0, sharpe_ratio=0.0,
                avg_trade_pnl_usdt=0.0, best_trade_pnl_usdt=0.0,
                worst_trade_pnl_usdt=0.0,
            ),
            equity_curve=[0.0],
            candles_analyzed=0,
            signals_generated=0,
            duration_ms=int((time.time() - t0) * 1000),
        )
