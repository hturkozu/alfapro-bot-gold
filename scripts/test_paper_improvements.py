"""
Paper trading geliştirmelerini doğrulayan test scripti.

Test edilenler:
  1. Fee modeli — gross vs net PnL, açılış+kapanış fee'leri
  2. Wick-bazlı SL/TP — bar high/low ile tetikleme
  3. Break-even — TP'nin yarısına ulaşınca SL entry'ye taşınır
  4. Trailing stop — peak takibi ile SL sıkışır

In-memory SQLite kullanır; prod DB'ye dokunmaz.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.core.database import Base
# Modellerin import'u Base.metadata'ya tabloları kaydeder
from app.models import api_credentials, app_state, candle, position, signal, strategy_config, trade  # noqa: F401
from app.models.position import Position
from app.services.paper_trader import PaperTrader


GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"

PASSED = 0
FAILED = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASSED, FAILED
    mark = f"{GREEN}✓{RESET}" if condition else f"{RED}✗{RESET}"
    print(f"  {mark} {label}" + (f"  — {detail}" if detail else ""))
    if condition:
        PASSED += 1
    else:
        FAILED += 1


def fresh_db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False)
    return Session()


def make_position(db, side="long", entry=100.0, sl=98.0, tp=104.0, size_usdt=100.0, lev=10):
    trader = PaperTrader(db)
    pos = trader.open_manual(
        symbol="BTCUSDT",
        side=side,
        entry_price=entry,
        size_usdt=size_usdt,
        leverage=lev,
        stop_loss=sl,
        take_profit=tp,
    )
    return trader, pos


# ──────────────────────────────────────────────────────────────────────
# 0. Settings .env'den okunuyor mu?
# ──────────────────────────────────────────────────────────────────────
def test_settings():
    print(f"\n{YELLOW}[0] Settings .env yuklemesi{RESET}")
    s = get_settings()
    check("paper_taker_fee_pct yüklendi", s.paper_taker_fee_pct == 0.06,
          f"fee={s.paper_taker_fee_pct}")
    check("paper_breakeven_trigger_pct yüklendi", s.paper_breakeven_trigger_pct == 50.0,
          f"trigger={s.paper_breakeven_trigger_pct}")
    check("paper_breakeven_offset_pct yüklendi", s.paper_breakeven_offset_pct == 0.06,
          f"offset={s.paper_breakeven_offset_pct}")
    check("paper_trailing_pct yüklendi", s.paper_trailing_pct == 0.4,
          f"trail={s.paper_trailing_pct}")


# ──────────────────────────────────────────────────────────────────────
# 1. Fee modeli
# ──────────────────────────────────────────────────────────────────────
def test_fees():
    print(f"\n{YELLOW}[1] Fee modeli{RESET}")
    db = fresh_db()
    # entry=100, lev=10, size=100 → notional=1000, size_base=10
    # TP=104 → gross PnL = (104-100)*10 = 40 USDT
    # taker=0.06% → open_fee = 100*10*0.0006 = 0.6
    #               close_fee = 104*10*0.0006 = 0.624
    # net = 40 - 1.224 = 38.776
    trader, pos = make_position(db, side="long", entry=100, sl=98, tp=104, size_usdt=100, lev=10)
    trader.close_position(pos, 104.0, reason="closed_tp")
    db.refresh(pos)

    expected_net = 40.0 - (100*10*0.0006 + 104*10*0.0006)
    check("Long TP'de net PnL fee düşülmüş", abs(pos.pnl_usdt - expected_net) < 1e-6,
          f"pnl={pos.pnl_usdt:.4f} beklenen={expected_net:.4f}")
    expected_pct = expected_net / 100.0 * 100
    check("Long pnl_pct net üzerinden", abs(pos.pnl_pct - expected_pct) < 1e-6,
          f"pct={pos.pnl_pct:.4f} beklenen={expected_pct:.4f}")

    # Short: entry=100, TP=96 → gross=(100-96)*10=40
    # fee = 100*10*0.0006 + 96*10*0.0006 = 0.6 + 0.576 = 1.176
    # net = 38.824
    db = fresh_db()
    trader, pos = make_position(db, side="short", entry=100, sl=102, tp=96, size_usdt=100, lev=10)
    trader.close_position(pos, 96.0, reason="closed_tp")
    db.refresh(pos)
    expected_net = 40.0 - (100*10*0.0006 + 96*10*0.0006)
    check("Short TP'de net PnL fee düşülmüş", abs(pos.pnl_usdt - expected_net) < 1e-6,
          f"pnl={pos.pnl_usdt:.4f} beklenen={expected_net:.4f}")

    # Trade kayıtları fee'leri içeriyor mu?
    from app.models.trade import Trade
    trades = db.query(Trade).order_by(Trade.id).all()
    check("Open trade fee_usdt > 0", trades[0].fee_usdt > 0,
          f"open_fee={trades[0].fee_usdt:.6f}")
    check("Close trade fee_usdt > 0", trades[1].fee_usdt > 0,
          f"close_fee={trades[1].fee_usdt:.6f}")


# ──────────────────────────────────────────────────────────────────────
# 2. Wick-bazlı SL/TP
# ──────────────────────────────────────────────────────────────────────
def test_wick():
    print(f"\n{YELLOW}[2] Wick-bazlı SL/TP{RESET}")

    # Senaryo A: tick 102'de ama bar_low 97 → long SL=98 vurmalı
    db = fresh_db()
    trader, pos = make_position(db, side="long", entry=100, sl=98, tp=104)
    result = trader.check_sl_tp(pos, current_price=102.0, bar_high=102.5, bar_low=97.0)
    check("Long: bar_low=97 SL=98 → wick SL tetikledi", result == "closed_sl",
          f"result={result}")
    db.refresh(pos)
    check("Kapanış fiyatı SL seviyesinde", pos.close_price == 98.0,
          f"close_price={pos.close_price}")

    # Senaryo B: tick 99'da ama bar_high 105 → long TP=104 vurmalı
    db = fresh_db()
    trader, pos = make_position(db, side="long", entry=100, sl=98, tp=104)
    result = trader.check_sl_tp(pos, current_price=99.0, bar_high=105.0, bar_low=99.0)
    check("Long: bar_high=105 TP=104 → wick TP tetikledi", result == "closed_tp",
          f"result={result}")

    # Senaryo C: aynı barda hem SL hem TP → konservatif (SL öncelikli)
    db = fresh_db()
    trader, pos = make_position(db, side="long", entry=100, sl=98, tp=104)
    result = trader.check_sl_tp(pos, current_price=100.0, bar_high=105.0, bar_low=97.0)
    check("Long: aynı barda SL+TP → SL öncelikli", result == "closed_sl",
          f"result={result}")

    # Senaryo D: bar verisi yok, sadece tick → eski mantık
    db = fresh_db()
    trader, pos = make_position(db, side="long", entry=100, sl=98, tp=104)
    result = trader.check_sl_tp(pos, current_price=99.5)
    check("Bar yok, fiyat aralıkta → tetik yok", result is None, f"result={result}")
    result = trader.check_sl_tp(pos, current_price=97.0)
    check("Bar yok, tick SL altı → SL tetikledi", result == "closed_sl",
          f"result={result}")

    # Short wick
    db = fresh_db()
    trader, pos = make_position(db, side="short", entry=100, sl=102, tp=96)
    result = trader.check_sl_tp(pos, current_price=99.0, bar_high=103.0, bar_low=98.5)
    check("Short: bar_high=103 SL=102 → wick SL tetikledi", result == "closed_sl",
          f"result={result}")


# ──────────────────────────────────────────────────────────────────────
# 3. Break-even
# ──────────────────────────────────────────────────────────────────────
def test_breakeven():
    print(f"\n{YELLOW}[3] Break-even{RESET}")
    s = get_settings()
    print(f"  (trigger={s.paper_breakeven_trigger_pct}% offset={s.paper_breakeven_offset_pct}%)")

    # .env: trigger=50, offset=0.06, trail=0.4 — BOTH active, en sıkı kazanır.
    # Long: entry=100 TP=104 → BE eşiği 102; BE_sl=100*(1+0.0006)=100.06
    # Trailing her tick'te aktif: trail_sl = peak * (1-0.004)
    db = fresh_db()
    trader, pos = make_position(db, side="long", entry=100, sl=98, tp=104)

    # peak=101: BE henüz tetiklenmedi (101<102). Trail_sl = 101*0.996 = 100.596
    # Bu 98'den büyük → SL 100.596'ya çekilir (sadece trailing).
    trader.apply_trailing(pos, 101.0, bar_high=101.0, bar_low=100.5)
    db.refresh(pos)
    check("Long: peak=101 → trailing devrede, SL 100.596",
          abs(pos.stop_loss - 100.596) < 1e-4,
          f"sl={pos.stop_loss}")

    # peak=102: BE tetiklendi (BE_sl=100.06) ama trail_sl=101.592 daha sıkı
    trader.apply_trailing(pos, 102.0, bar_high=102.0, bar_low=101.5)
    db.refresh(pos)
    check("Long: peak=102 → max(BE=100.06, Trail=101.592)=101.592",
          abs(pos.stop_loss - 101.592) < 1e-4,
          f"sl={pos.stop_loss}")

    # SL'in geri gitmediğini doğrula
    prev_sl = pos.stop_loss
    trader.apply_trailing(pos, 101.0, bar_high=101.0, bar_low=100.8)
    db.refresh(pos)
    check("Long: fiyat geri çekildi → SL geri gitmedi", pos.stop_loss == prev_sl,
          f"sl={pos.stop_loss} (önceki={prev_sl})")

    # Short: entry=100 TP=96 → BE eşiği 98; BE_sl=100*0.9994=99.94
    db = fresh_db()
    trader, pos = make_position(db, side="short", entry=100, sl=102, tp=96)

    # trough=99: trail_sl = 99*1.004 = 99.396 — SL 102'den 99.396'ya iner
    trader.apply_trailing(pos, 99.0, bar_high=99.5, bar_low=99.0)
    db.refresh(pos)
    check("Short: trough=99 → trailing SL=99.396",
          abs(pos.stop_loss - 99.396) < 1e-4,
          f"sl={pos.stop_loss}")

    # trough=98: BE tetik (BE_sl=99.94) ama trail_sl=98*1.004=98.392 daha sıkı
    trader.apply_trailing(pos, 98.0, bar_high=98.5, bar_low=98.0)
    db.refresh(pos)
    check("Short: trough=98 → min(BE=99.94, Trail=98.392)=98.392",
          abs(pos.stop_loss - 98.392) < 1e-4,
          f"sl={pos.stop_loss}")


# ──────────────────────────────────────────────────────────────────────
# 4. Trailing-only davranış (BE kapalı varsayım)
# ──────────────────────────────────────────────────────────────────────
def test_trailing_isolated():
    print(f"\n{YELLOW}[4] Trailing izole davranış{RESET}")
    # paper_trader modülü `from app.config import get_settings` ile yerel
    # binding aldığı için doğrudan modül attribute'unu yamalıyoruz.
    from app.services import paper_trader as pt
    original = get_settings()

    class _Tmp:
        paper_taker_fee_pct = original.paper_taker_fee_pct
        paper_breakeven_trigger_pct = 0.0  # kapalı
        paper_breakeven_offset_pct = 0.06
        paper_trailing_pct = 0.5  # %0.5 trail

    real_get_settings = pt.get_settings
    pt.get_settings = lambda: _Tmp()  # type: ignore[assignment]

    try:
        # Long: entry=100, sl=98, tp=110 — hiç BE yok, sadece trail
        db = fresh_db()
        trader, pos = make_position(db, side="long", entry=100, sl=98, tp=110)

        # peak=105 → trail_sl = 105*(1-0.005) = 104.475
        trader.apply_trailing(pos, 105.0, bar_high=105.0, bar_low=103.0)
        db.refresh(pos)
        check("Long trail: peak=105 → SL=104.475",
              abs(pos.stop_loss - 104.475) < 1e-3,
              f"sl={pos.stop_loss}")

        # peak=108 → 108*0.995 = 107.46
        trader.apply_trailing(pos, 108.0, bar_high=108.0, bar_low=106.0)
        db.refresh(pos)
        check("Long trail: peak=108 → SL=107.46",
              abs(pos.stop_loss - 107.46) < 1e-3,
              f"sl={pos.stop_loss}")

        # SL TP'yi aşamaz — peak=200 olsa bile SL TP-altında kalmalı
        trader.apply_trailing(pos, 200.0, bar_high=200.0, bar_low=199.0)
        db.refresh(pos)
        check("Long trail: SL TP'yi geçemez", pos.stop_loss < 110.0,
              f"sl={pos.stop_loss} tp=110")
    finally:
        pt.get_settings = real_get_settings


# ──────────────────────────────────────────────────────────────────────
def main():
    print(f"\n{YELLOW}{'=' * 60}{RESET}")
    print(f"{YELLOW}  PAPER TRADING GELIŞTIRME TESTLERİ{RESET}")
    print(f"{YELLOW}{'=' * 60}{RESET}")

    test_settings()
    test_fees()
    test_wick()
    test_breakeven()
    test_trailing_isolated()

    print(f"\n{YELLOW}{'=' * 60}{RESET}")
    total = PASSED + FAILED
    color = GREEN if FAILED == 0 else RED
    print(f"{color}  Sonuç: {PASSED}/{total} geçti ({FAILED} başarısız){RESET}")
    print(f"{YELLOW}{'=' * 60}{RESET}\n")
    sys.exit(0 if FAILED == 0 else 1)


if __name__ == "__main__":
    main()
