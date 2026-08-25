"""Swing struktura'ni ko'z bilan tekshirish uchun vizual skript.

Ishlatish:
    python scripts/plot_structure.py [SYMBOL] [LOOKBACK]

Masalan: python scripts/plot_structure.py SPUS 2
Chiqish: chart.png (close narx chizig'i + swing HIGH/LOW marker va label'lari).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # Displaysiz (headless) muhitda ham ishlashi uchun
import matplotlib.pyplot as plt

# Skript qayerdan ishga tushirilishidan qat'iy nazar paketlar topilishi uchun
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import PRIMARY_INTERVAL, SWING_LOOKBACK  # noqa: E402
from data.yfinance_provider import YFinanceProvider  # noqa: E402
from smc.structure import detect_swings  # noqa: E402
from smc.types import SwingKind  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Swing struktura vizual tekshiruvi")
    parser.add_argument("symbol", nargs="?", default="SPUS", help="Masalan: SPUS")
    parser.add_argument("lookback", nargs="?", type=int, default=SWING_LOOKBACK)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    provider = YFinanceProvider()
    df = provider.get_ohlcv(args.symbol, PRIMARY_INTERVAL)
    df = df.tail(200)  # oxirgi ~200 bar ko'z bilan tekshirish uchun yetarli

    swings = detect_swings(df, lookback=args.lookback)

    fig, ax = plt.subplots(figsize=(14, 7))
    ax.plot(df.index, df["close"], color="steelblue", linewidth=1, label="close")

    # Marker'larni narxdan biroz uzoqlashtirish uchun offset (chart o'lchamiga mos)
    price_range = float(df["high"].max() - df["low"].min())
    offset = price_range * 0.03 if price_range > 0 else 1.0

    for swing in swings:
        label_text = swing.label.name if swing.label is not None else "?"
        if swing.kind is SwingKind.HIGH:
            marker_y = swing.price + offset
            ax.scatter(swing.timestamp, marker_y, marker="v", color="crimson", s=60, zorder=5)
            ax.annotate(
                label_text,
                (swing.timestamp, marker_y),
                textcoords="offset points",
                xytext=(0, 4),
                ha="center",
                fontsize=8,
                color="crimson",
            )
        else:
            marker_y = swing.price - offset
            ax.scatter(swing.timestamp, marker_y, marker="^", color="seagreen", s=60, zorder=5)
            ax.annotate(
                label_text,
                (swing.timestamp, marker_y),
                textcoords="offset points",
                xytext=(0, -12),
                ha="center",
                fontsize=8,
                color="seagreen",
            )

    ax.set_title(f"{args.symbol} — swing struktura (lookback={args.lookback})")
    ax.legend()
    fig.tight_layout()

    out_path = Path("chart.png")
    fig.savefig(out_path, dpi=150)
    print(f"Chart saqlandi: {out_path.resolve()}")
    print(f"Topilgan swing'lar soni: {len(swings)}")


if __name__ == "__main__":
    main()
