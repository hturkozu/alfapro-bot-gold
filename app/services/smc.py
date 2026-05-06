"""
Smart Money Concepts (SMC) analiz modülü.

Üç temel yapı tespit edilir:
- BOS (Break of Structure): Bir önceki swing high/low'un kırılması → trend devamı
- CHoCH (Change of Character): İlk ters yöne swing kırılması → trend değişimi
- Order Block: Güçlü hareketten ÖNCEKİ son ters-renkli mum

Basit ama kullanışlı bir implementasyon. Swing detection için
fractal yöntemi kullanır (sol/sağ N mumdan yüksek/düşük).
"""
from __future__ import annotations

from typing import Literal

from app.schemas.market import (
    SmcAnalysis,
    SmcBos,
    SmcChoch,
    SmcOrderBlock,
)


SwingType = Literal["high", "low"]


def _find_swings(
    rows: list[list[float]],
    left: int = 2,
    right: int = 2,
) -> list[tuple[int, int, float, SwingType]]:
    """
    Fractal swing high/low tespit.

    Bir mum [i], çevresindeki `left` ve `right` kadar mumların tümünden
    daha yüksekse swing_high, daha düşükse swing_low sayılır.

    Döner: [(index, ts, price, 'high'|'low'), ...]
    """
    swings: list[tuple[int, int, float, SwingType]] = []
    n = len(rows)
    for i in range(left, n - right):
        high_i = rows[i][2]
        low_i = rows[i][3]
        is_high = all(rows[i][2] > rows[j][2] for j in range(i - left, i + right + 1) if j != i)
        is_low = all(rows[i][3] < rows[j][3] for j in range(i - left, i + right + 1) if j != i)
        if is_high:
            swings.append((i, int(rows[i][0]), float(high_i), "high"))
        if is_low:
            swings.append((i, int(rows[i][0]), float(low_i), "low"))
    return swings


def compute_smc(
    rows: list[list[float]],
    left: int = 2,
    right: int = 2,
    max_order_blocks: int = 5,
) -> SmcAnalysis:
    """
    BOS, CHoCH ve Order Block tespit eder.
    """
    if not rows or len(rows) < (left + right + 4):
        return SmcAnalysis()

    swings = _find_swings(rows, left, right)
    if len(swings) < 3:
        return SmcAnalysis()

    bos_list: list[SmcBos] = []
    choch_list: list[SmcChoch] = []

    # Trend state: "bullish" | "bearish" | "neutral"
    trend: str = "neutral"

    # Son bilinen kırılması takip edilecek swing'ler
    last_high: tuple[int, int, float] | None = None   # (idx, ts, price)
    last_low: tuple[int, int, float] | None = None

    for idx, ts, price, stype in swings:
        if stype == "high":
            if last_high is not None and price > last_high[2]:
                # Yeni yüksek yüksek
                if trend == "bearish":
                    # CHoCH (düşüşten yükselişe)
                    choch_list.append(SmcChoch(ts=ts, price=price, direction="bullish"))
                    trend = "bullish"
                elif trend == "bullish":
                    # BOS (trend devam)
                    bos_list.append(SmcBos(ts=ts, price=price, direction="bullish"))
                else:
                    trend = "bullish"
            last_high = (idx, ts, price)
        else:  # low
            if last_low is not None and price < last_low[2]:
                if trend == "bullish":
                    choch_list.append(SmcChoch(ts=ts, price=price, direction="bearish"))
                    trend = "bearish"
                elif trend == "bearish":
                    bos_list.append(SmcBos(ts=ts, price=price, direction="bearish"))
                else:
                    trend = "bearish"
            last_low = (idx, ts, price)

    # ---- Order Blocks ----
    # Her BOS öncesi son ters-renkli mumu kaydet
    order_blocks: list[SmcOrderBlock] = []
    for bos in bos_list:
        # BOS ts'sine denk gelen mumu bul
        bos_idx = next((i for i, r in enumerate(rows) if int(r[0]) == bos.ts), None)
        if bos_idx is None or bos_idx < 1:
            continue

        if bos.direction == "bullish":
            # Geriye doğru git, kırmızı (close < open) ilk mumu bul
            for j in range(bos_idx - 1, max(0, bos_idx - 15), -1):
                o = rows[j][1]
                c = rows[j][4]
                if c < o:
                    order_blocks.append(
                        SmcOrderBlock(
                            ts=int(rows[j][0]),
                            high=float(rows[j][2]),
                            low=float(rows[j][3]),
                            direction="bullish",
                        )
                    )
                    break
        else:
            for j in range(bos_idx - 1, max(0, bos_idx - 15), -1):
                o = rows[j][1]
                c = rows[j][4]
                if c > o:
                    order_blocks.append(
                        SmcOrderBlock(
                            ts=int(rows[j][0]),
                            high=float(rows[j][2]),
                            low=float(rows[j][3]),
                            direction="bearish",
                        )
                    )
                    break

    # Son N order block'u tut
    order_blocks = order_blocks[-max_order_blocks:]

    current_trend: Literal["bullish", "bearish", "neutral"]
    if trend == "bullish":
        current_trend = "bullish"
    elif trend == "bearish":
        current_trend = "bearish"
    else:
        current_trend = "neutral"

    return SmcAnalysis(
        bos=bos_list[-10:],
        choch=choch_list[-5:],
        order_blocks=order_blocks,
        current_trend=current_trend,
    )
