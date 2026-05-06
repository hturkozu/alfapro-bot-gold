"""
Fibonacci retracement ve extension hesaplayıcısı.

Son N mumdan otomatik swing high/low tespit eder, ona göre seviyeleri üretir.
"""
from __future__ import annotations

from app.schemas.market import FibonacciLevels


RETRACEMENT_RATIOS = {
    "0.236": 0.236,
    "0.382": 0.382,
    "0.5":   0.5,
    "0.618": 0.618,
    "0.786": 0.786,
}

EXTENSION_RATIOS = {
    "1.272": 1.272,
    "1.414": 1.414,
    "1.618": 1.618,
    "2.0":   2.0,
    "2.618": 2.618,
}


def compute_fibonacci(
    rows: list[list[float]],
    lookback: int = 100,
) -> FibonacciLevels | None:
    """
    Son `lookback` mumdan en yüksek ve en düşük fiyatı swing olarak alır.
    Swing yüksek önce mi geldi yoksa swing düşük mü → trend yönünü belirler.
    """
    if not rows or len(rows) < 10:
        return None

    recent = rows[-lookback:] if len(rows) > lookback else rows

    # Her mum: [ts, o, h, l, c, v]
    highs = [(r[0], r[2]) for r in recent]
    lows = [(r[0], r[3]) for r in recent]

    swing_high_ts, swing_high = max(highs, key=lambda x: x[1])
    swing_low_ts, swing_low = min(lows, key=lambda x: x[1])

    if swing_high <= swing_low:
        return None

    # Yön: düşük önce olursa yukarı trend, tersi düşüş
    direction = "up" if swing_low_ts < swing_high_ts else "down"

    diff = swing_high - swing_low

    if direction == "up":
        # Yukarı trendde retracement = high'tan geriye doğru düşüş seviyeleri
        retracement = {
            label: round(swing_high - diff * r, 6)
            for label, r in RETRACEMENT_RATIOS.items()
        }
        extension = {
            label: round(swing_high + diff * (r - 1), 6)
            for label, r in EXTENSION_RATIOS.items()
        }
    else:
        # Aşağı trendde retracement = low'dan geri yukarı seviyeler
        retracement = {
            label: round(swing_low + diff * r, 6)
            for label, r in RETRACEMENT_RATIOS.items()
        }
        extension = {
            label: round(swing_low - diff * (r - 1), 6)
            for label, r in EXTENSION_RATIOS.items()
        }

    return FibonacciLevels(
        swing_high=round(swing_high, 6),
        swing_low=round(swing_low, 6),
        direction=direction,
        retracement=retracement,
        extension=extension,
    )
