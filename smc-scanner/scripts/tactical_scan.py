"""Taktik SMC skaner: har watchlist ticker uchun ENG OXIRGI struktura/zona/setup holatini ko'rsatadi.

O'quv/paper-savdo qatlami uchun asbob — bu skript YANGI aniqlash mantig'i QO'SHMAYDI,
faqat mavjud, allaqachon sinalgan pipeline'ni (detect_swings, detect_structure_events,
detect_fvgs/detect_order_blocks, generate_signals) chaqirib, oxirgi holatni o'qiladigan
qilib chiqaradi.

"Faol setup" ta'rifi: eng oxirgi signal'ning entry_index_pos'i oxirgi
ACTIVE_SETUP_LOOKBACK_BARS bar ichida bo'lsa — loyihaning o'z 2-10 kunlik swing
gorizontiga mos (bar oldingi setup'lar tarixiy kontekst sifatida ko'rsatiladi, "faol" emas).

exit_mode="trailing" uchun skript FAQAT boshlang'ich (invalidatsiya) stop darajasini
ko'rsatadi — bugungi holatdagi "joriy trailing stop"ni QAYTA HISOBLAMAYDI (bu
backtest/engine.py::_simulate_trailing_exit mantig'ini ikkinchi joyda takrorlashni
talab qilardi — ortiqcha murakkablik). Aniq joriy daraja kerak bo'lsa, exit_comparison.py
yoki run_backtest orqali simulyatsiya qiling.

Ishlatish:
    python scripts/tactical_scan.py [SYMBOLS...] [--interval 1d] [--mult 1.5] [--exit-mode fixed|trailing]

SYMBOLS berilmasa — config/core_watchlist.py'dagi tickerlar ishlatiladi.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

# Skript qayerdan ishga tushirilishidan qat'iy nazar paketlar topilishi uchun
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.core_watchlist import get_core_watchlist  # noqa: E402
from config.settings import MIN_PLANNED_RR, PRIMARY_INTERVAL, SWING_LOOKBACK  # noqa: E402
from data.factory import get_provider  # noqa: E402
from smc.market_structure import current_structure_state, detect_structure_events  # noqa: E402
from smc.signal import generate_signals  # noqa: E402
from smc.structure import detect_swings  # noqa: E402
from smc.types import StructureState  # noqa: E402
from smc.zones import detect_fvgs, detect_order_blocks  # noqa: E402

# Loyihaning o'z 2-10 kunlik swing gorizontiga mos — shundan eski setup "faol" emas,
# tarixiy kontekst sifatida ko'rsatiladi.
ACTIVE_SETUP_LOOKBACK_BARS: int = 10

# Default "trailing" — Stage 1'ning (scripts/exit_comparison.py) haqiqiy o'lchovi
# asosida: 6 ta default symbol bo'yicha trailing o'rtacha EDGE'da (+4.88) va
# expectancy'da (0.558R vs 0.201R) fixed'dan ustun chiqdi, 4/6 symbolda RETURN% ham
# yuqoriroq edi. Agar kelajakda qayta o'lchov boshqacha ko'rsatsa, shu default'ni yangilang.
DEFAULT_EXIT_MODE: str = "trailing"

BANNER = (
    "Bu taktik/paper qatlam. Backtest: bu signal buy&hold'dan past return beradi "
    "(trailing biroz yaxshilaydi, lekin buy&hold'ni buqada yengmaydi). Kapitalingizning "
    "katta qismi CORE (buy&hold)da bo'lsin. Bu setup'lar o'rganish va paper savdo uchun."
)


def build_scan_row(
    symbol: str,
    df: pd.DataFrame,
    *,
    mult: float | None = None,
    lookback: int = SWING_LOOKBACK,
    exit_mode: str = DEFAULT_EXIT_MODE,
) -> dict:
    """Bitta symbol uchun oxirgi struktura/zona/setup holatini hisoblaydi (sof, tarmoqsiz)."""
    swings = detect_swings(df, lookback=lookback)
    events = detect_structure_events(df, swings)
    state = current_structure_state(df, swings)
    last_event = events[-1] if events else None

    bullish_zones = [
        z for z in detect_fvgs(df, mult=mult) + detect_order_blocks(df, mult=mult)
        if z.direction is StructureState.BULLISH
    ]
    open_zones = [z for z in bullish_zones if not z.filled]

    signals = generate_signals(df, lookback=lookback, mult=mult)
    last_signal = signals[-1] if signals else None

    n = len(df)
    row: dict = {
        "SYMBOL": symbol,
        "STRUCTURE_STATE": state.name if state is not None else "N/A",
        "LAST_EVENT_TYPE": last_event.event_type.name if last_event else None,
        "LAST_EVENT_DIRECTION": last_event.direction.name if last_event else None,
        "LAST_EVENT_DATE": last_event.timestamp.date().isoformat() if last_event else None,
        "OPEN_BULLISH_ZONES": len(open_zones),
        "SETUP_REASON": None,
        "SETUP_ENTRY_DATE": None,
        "SETUP_BARS_AGO": None,
        "HAS_ACTIVE_SETUP": False,
        "SETUP_ENTRY": None,
        "SETUP_STOP": None,
        "SETUP_TARGET": None,
        "SETUP_RR": None,
        "SETUP_REFERENCE_TARGET": None,
        "SETUP_PLANNED_RR": None,
        "SETUP_LOW_RR_WARNING": False,
        "SETUP_INVALIDATION": None,
        "ERROR": None,
    }

    if last_signal is not None:
        bars_ago = (n - 1) - last_signal.entry_index_pos
        row["SETUP_REASON"] = last_signal.reason
        row["SETUP_ENTRY_DATE"] = last_signal.entry_ts.date().isoformat()
        row["SETUP_BARS_AGO"] = bars_ago
        row["HAS_ACTIVE_SETUP"] = bars_ago <= ACTIVE_SETUP_LOOKBACK_BARS
        row["SETUP_ENTRY"] = round(last_signal.entry_price, 2)
        row["SETUP_STOP"] = round(last_signal.stop_price, 2)

        # Reference target: smc.signal.generate_signals allaqachon hisoblagan target_price —
        # exit_mode'dan qat'iy nazar HAR DOIM mavjud (swing-high yoki R-multiple fallback).
        row["SETUP_REFERENCE_TARGET"] = round(last_signal.target_price, 2)
        risk = last_signal.entry_price - last_signal.stop_price
        if risk > 0:
            row["SETUP_PLANNED_RR"] = round(
                (last_signal.target_price - last_signal.entry_price) / risk, 2
            )
        row["SETUP_LOW_RR_WARNING"] = (
            row["SETUP_PLANNED_RR"] is not None and row["SETUP_PLANNED_RR"] < MIN_PLANNED_RR
        )

        if exit_mode == "fixed":
            # fixed-mode'da SETUP_TARGET/SETUP_RR = haqiqiy tradeable target — aynan
            # SETUP_REFERENCE_TARGET/SETUP_PLANNED_RR bilan bir xil qiymat (bitta manba).
            row["SETUP_TARGET"] = row["SETUP_REFERENCE_TARGET"]
            row["SETUP_RR"] = row["SETUP_PLANNED_RR"]
        else:
            row["SETUP_RR"] = "N/A (trailing — maqsad yo'q)"

        row["SETUP_INVALIDATION"] = (
            f"Narx {last_signal.stop_price:.2f} dan pastga yopilsa (boshlang'ich stop) "
            "yoki yangi bearish CHoCH sodir bo'lsa, bu struktura bekor bo'ladi."
        )

    return row


def scan_one_symbol(
    symbol: str,
    interval: str,
    provider_name: str | None,
    *,
    mult: float | None = None,
    lookback: int = SWING_LOOKBACK,
    exit_mode: str = DEFAULT_EXIT_MODE,
) -> dict:
    """build_scan_row'ni chaqirishdan oldin data'ni oladi."""
    df = get_provider(provider_name).get_ohlcv(symbol, interval)
    if df.empty:
        raise ValueError("bo'sh ma'lumot qaytdi")
    return build_scan_row(symbol, df, mult=mult, lookback=lookback, exit_mode=exit_mode)


def run_scan(
    symbols: list[str],
    interval: str,
    provider_name: str | None,
    *,
    mult: float | None = None,
    lookback: int = SWING_LOOKBACK,
    exit_mode: str = DEFAULT_EXIT_MODE,
) -> list[dict]:
    """Watchlist bo'ylab yuradi; bitta symbol xato bersa crash qilmasdan ERROR maydonli
    qator qaytaradi, qolganlari bilan davom etadi."""
    rows = []
    for symbol in symbols:
        try:
            rows.append(scan_one_symbol(symbol, interval, provider_name, mult=mult, lookback=lookback, exit_mode=exit_mode))
        except Exception as exc:
            rows.append({"SYMBOL": symbol, "ERROR": str(exc)})
    return rows


def _reference_rr_text(row: dict) -> str:
    """"Ref.Target | Planned R:R" matni — fixed va trailing ikkalasida ham bir xil
    manbadan (SETUP_REFERENCE_TARGET/SETUP_PLANNED_RR). Signal umuman topilmagan
    yoki risk<=0 chekka holatlarida "N/A" o'rniga qisqa sababi ko'rsatiladi."""
    ref_target = row.get("SETUP_REFERENCE_TARGET")
    if ref_target is None:
        return "Ref.Target: N/A (signal topilmadi)"
    planned_rr = row.get("SETUP_PLANNED_RR")
    rr_text = f"{planned_rr}" if planned_rr is not None else "N/A (risk<=0)"
    return f"Ref.Target: {ref_target} | Planned R:R: {rr_text}"


def _exit_text(row: dict) -> str:
    """Haqiqiy chiqish qanday bo'lishini aniq ko'rsatadi — Ref.Target FAQAT baholash
    uchun, chalkashtirmaslik uchun har doim eslatiladi."""
    if row["SETUP_TARGET"] is None:
        return "Exit: trailing stop (real chiqish trailing bilan)"
    return f"Exit: fixed target {row['SETUP_TARGET']}"


def format_scan_block(row: dict) -> str:
    """Bitta symbol uchun o'qiladigan matn blokini yasaydi (jadval EMAS — o'quv fokusi)."""
    if row.get("ERROR"):
        return f"=== {row['SYMBOL']} ===\nXato: {row['ERROR']}"

    lines = [f"=== {row['SYMBOL']} ==="]

    structure_line = f"Joriy struktura: {row['STRUCTURE_STATE']}"
    if row["LAST_EVENT_TYPE"]:
        structure_line += (
            f" (oxirgi {row['LAST_EVENT_TYPE']}: {row['LAST_EVENT_DATE']}, "
            f"yo'nalish={row['LAST_EVENT_DIRECTION']})"
        )
    lines.append(structure_line)
    lines.append(f"Ochiq bullish zonalar: {row['OPEN_BULLISH_ZONES']} ta")

    if row["SETUP_REASON"] is None:
        lines.append("Faol setup: hozircha faol setup yo'q")
    else:
        active_str = "HA" if row["HAS_ACTIVE_SETUP"] else "YO'Q (eski, tarixiy kontekst)"
        lines.append(f"Faol setup: {active_str} ({row['SETUP_BARS_AGO']} bar oldin, {row['SETUP_ENTRY_DATE']})")
        lines.append(f"  Turi: {row['SETUP_REASON']} retest")
        lines.append(f"  Entry: {row['SETUP_ENTRY']}")
        lines.append(f"  Stop: {row['SETUP_STOP']}")
        lines.append(f"  {_reference_rr_text(row)}")
        if row.get("SETUP_LOW_RR_WARNING"):
            lines.append("  ⚠️ Past R:R — ehtiyot")
        lines.append(f"  Nega: {row['SETUP_REASON']} zonasi {row['SETUP_ENTRY_DATE']}'da retest qilindi")
        lines.append(f"  Invalidatsiya: {row['SETUP_INVALIDATION']}")
        lines.append(f"  {_exit_text(row)}")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Taktik SMC skaner (o'quv/paper qatlam)")
    parser.add_argument("symbols", nargs="*", help="Bo'sh bo'lsa core_watchlist tickerlari")
    parser.add_argument("--interval", default=PRIMARY_INTERVAL, help="Masalan: 1d")
    parser.add_argument("--provider", default=None, help="yfinance yoki alpaca (default: settings.DATA_PROVIDER)")
    parser.add_argument("--mult", type=float, default=None, help="Displacement ATR mult (default: settings)")
    parser.add_argument("--lookback", type=int, default=SWING_LOOKBACK)
    parser.add_argument("--exit-mode", default=DEFAULT_EXIT_MODE, choices=["fixed", "trailing"])
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    symbols = args.symbols if args.symbols else [h.ticker for h in get_core_watchlist()]

    print(BANNER)
    print()

    rows = run_scan(symbols, args.interval, args.provider, mult=args.mult, lookback=args.lookback, exit_mode=args.exit_mode)
    for row in rows:
        print(format_scan_block(row))
        print()


if __name__ == "__main__":
    main()
