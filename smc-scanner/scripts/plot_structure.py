"""Swing struktura'ni ko'z bilan tekshirish uchun vizual skript.

Ishlatish:
    python scripts/plot_structure.py [SYMBOL] [LOOKBACK] [--interval 1d|4h|1h|1wk] [--provider yfinance|alpaca]

Masalan: python scripts/plot_structure.py SPUS 2
         python scripts/plot_structure.py SPUS --interval 4h --provider alpaca
Chiqish: chart.png (close narx chizig'i + swing HIGH/LOW marker, BOS/CHoCH chiziqlari).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # Displaysiz (headless) muhitda ham ishlashi uchun
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

# Skript qayerdan ishga tushirilishidan qat'iy nazar paketlar topilishi uchun
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import PRIMARY_INTERVAL, SWING_LOOKBACK  # noqa: E402
from data.factory import get_provider  # noqa: E402
from smc.market_structure import detect_structure_events  # noqa: E402
from smc.structure import detect_swings  # noqa: E402
from smc.types import StructureEventType, StructureState, SwingKind  # noqa: E402
from smc.zones import detect_fvgs, detect_order_blocks  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Swing struktura vizual tekshiruvi")
    parser.add_argument("symbol", nargs="?", default="SPUS", help="Masalan: SPUS")
    parser.add_argument("lookback", nargs="?", type=int, default=SWING_LOOKBACK)
    parser.add_argument("--interval", default=PRIMARY_INTERVAL, help="Masalan: 1d, 4h")
    parser.add_argument(
        "--provider", default=None, help="yfinance yoki alpaca (default: settings.DATA_PROVIDER)"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    provider = get_provider(args.provider)
    df = provider.get_ohlcv(args.symbol, args.interval)
    df = df.tail(200)  # oxirgi ~200 bar ko'z bilan tekshirish uchun yetarli

    swings = detect_swings(df, lookback=args.lookback)
    events = detect_structure_events(df, swings)
    open_fvgs = [z for z in detect_fvgs(df) if not z.filled]
    open_obs = [z for z in detect_order_blocks(df) if not z.filled]

    fig, ax = plt.subplots(figsize=(14, 7))

    # Ochiq FVG/OB zonalari — pastki qatlamda (zorder=1), boshqa hamma narsa ustidan chiziladi.
    # Faqat ochiq (unfilled) zonalar ko'rsatiladi — chart ifloslanmasin. Bearish zonalar
    # xiraroq (past alpha) — tizim LONG-ONLY, ular faqat kontekst/kelajakdagi exit-filtr uchun.
    for zone, color, alpha in [
        *[(z, "mediumseagreen", 0.15) for z in open_fvgs if z.direction is StructureState.BULLISH],
        *[(z, "darkgreen", 0.12) for z in open_obs if z.direction is StructureState.BULLISH],
        *[(z, "lightcoral", 0.10) for z in open_fvgs if z.direction is StructureState.BEARISH],
        *[(z, "firebrick", 0.08) for z in open_obs if z.direction is StructureState.BEARISH],
    ]:
        ax.fill_between(
            [zone.created_ts, df.index[-1]], zone.bottom, zone.top, color=color, alpha=alpha, zorder=1
        )

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

    # BOS/CHoCH: buzilgan swing'dan break candle'gacha gorizontal chiziq.
    # Rang = yo'nalish (bullish/bearish), chiziq turi = event turi (BOS/CHoCH).
    for event in events:
        color = "royalblue" if event.direction is StructureState.BULLISH else "darkorange"
        linestyle = "-" if event.event_type is StructureEventType.BOS else "--"
        ax.hlines(
            event.broken_level,
            xmin=event.broken_swing_ts,
            xmax=event.timestamp,
            color=color,
            linestyle=linestyle,
            linewidth=1.5,
            zorder=4,
        )
        ax.annotate(
            event.event_type.name,
            (event.timestamp, event.broken_level),
            textcoords="offset points",
            xytext=(4, 4),
            fontsize=8,
            color=color,
            fontweight="bold",
        )

    ax.set_title(f"{args.symbol} — swing struktura ({args.interval}, lookback={args.lookback})")

    # Legend'ga BOS/CHoCH rang-chiziq sxemasini tushuntiruvchi proxy'lar qo'shamiz
    # (har bir event uchun alohida label bermaymiz — legend'da takrorlanish bo'lmasin)
    legend_handles, legend_labels = ax.get_legend_handles_labels()
    legend_handles += [
        Line2D([0], [0], color="royalblue", lw=1.5, label="bullish BOS"),
        Line2D([0], [0], color="royalblue", lw=1.5, linestyle="--", label="bullish CHoCH"),
        Line2D([0], [0], color="darkorange", lw=1.5, label="bearish BOS"),
        Line2D([0], [0], color="darkorange", lw=1.5, linestyle="--", label="bearish CHoCH"),
        Patch(facecolor="mediumseagreen", alpha=0.3, label="ochiq bullish FVG"),
        Patch(facecolor="darkgreen", alpha=0.3, label="ochiq bullish OB"),
        Patch(facecolor="lightcoral", alpha=0.3, label="ochiq bearish FVG"),
        Patch(facecolor="firebrick", alpha=0.3, label="ochiq bearish OB"),
    ]
    ax.legend(handles=legend_handles, fontsize=8)
    fig.tight_layout()

    out_path = Path("chart.png")
    fig.savefig(out_path, dpi=150)
    print(f"Chart saqlandi: {out_path.resolve()}")
    print(f"Topilgan swing'lar soni: {len(swings)}")
    print(f"BOS/CHoCH event'lar soni: {len(events)}")
    print(f"Ochiq FVG: {len(open_fvgs)}, Ochiq OB: {len(open_obs)}")


if __name__ == "__main__":
    main()
