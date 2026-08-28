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
from config.settings import (  # noqa: E402
    ENTRY_TOLERANCE_ATR_MULT,
    MIN_PLANNED_RR,
    PRIMARY_INTERVAL,
    SWING_LOOKBACK,
)
from data.factory import get_provider  # noqa: E402
from smc.market_structure import current_structure_state, detect_structure_events  # noqa: E402
from smc.signal import compute_planned_rr, generate_signals  # noqa: E402
from smc.structure import detect_swings  # noqa: E402
from smc.types import StructureState  # noqa: E402
from smc.zones import compute_atr, detect_fvgs, detect_order_blocks  # noqa: E402

# Loyihaning o'z 2-10 kunlik swing gorizontiga mos — shundan eski setup "faol" emas,
# tarixiy kontekst sifatida ko'rsatiladi.
ACTIVE_SETUP_LOOKBACK_BARS: int = 10

# Setup lookback ichida bo'lsa ham QUYIDAGI hollarda "bekor bo'lgan" deb belgilanadi
# (HAS_ACTIVE_SETUP=False, lekin SETUP_INVALIDATED=True — ro'yxatda alohida ko'rinadi):
#   stop_close       — entry'dan keyin biror bar boshlang'ich stop'dan PAST yopilgan
#   structure_bearish — joriy struktura holati BEARISH'ga o'tgan
_INVALIDATION_STOP_CLOSE = "stop_close"
_INVALIDATION_STRUCTURE_BEARISH = "structure_bearish"

# Oxirgi close'ning entry'ga nisbatan joylashuviga qarab setup holati (faqat lookback
# ichidagi, invalidatsiya bo'lmagan setup uchun hisoblanadi). tol = ENTRY_TOLERANCE_ATR_MULT*ATR:
#   active — oxirgi close entry ± tol ichida → HOZIR kirsa bo'ladi (asosiy "Faol" ro'yxat)
#   missed — oxirgi close entry + tol dan YUQORI → poyezd ketdi, kirib bo'lmaydi
#   below  — oxirgi close entry - tol dan PAST (lekin stop'dan yuqori) → zona ichida, momentum kuchsiz
# Bu qiymatlar SETUP_* kalitlar kabi row-sxemasining qismi — oshkora (underscore'siz).
ENTRY_STATE_ACTIVE = "active"
ENTRY_STATE_MISSED = "missed"
ENTRY_STATE_BELOW = "below"

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
        # Bot qaysi barni ko'rayotgani aniq ko'rinsin — TradingView bilan solishtirish
        # va kesh eskirganini o'z vaqtida sezish uchun (kunlik bot 1 bar orqada bo'lishi
        # normal, lekin undan ko'p bo'lsa — kesh muammosi).
        "LAST_BAR_DATE": df.index[-1].date().isoformat() if n else None,
        "LAST_CLOSE": round(float(df["close"].iloc[-1]), 2) if n else None,
        "STRUCTURE_STATE": state.name if state is not None else "N/A",
        "LAST_EVENT_TYPE": last_event.event_type.name if last_event else None,
        "LAST_EVENT_DIRECTION": last_event.direction.name if last_event else None,
        "LAST_EVENT_DATE": last_event.timestamp.date().isoformat() if last_event else None,
        "OPEN_BULLISH_ZONES": len(open_zones),
        "SETUP_REASON": None,
        "SETUP_ENTRY_DATE": None,
        "SETUP_BARS_AGO": None,
        "HAS_ACTIVE_SETUP": False,
        "SETUP_INVALIDATED": False,
        "SETUP_INVALIDATED_REASON": None,
        "SETUP_ENTRY_STATE": None,
        "SETUP_ENTRY_TOLERANCE": None,
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
        within_lookback = bars_ago <= ACTIVE_SETUP_LOOKBACK_BARS

        last_close = float(df["close"].iloc[-1])

        # Entry'dan keyingi barlarda invalidatsiya: narx boshlang'ich stop'dan past
        # yopilganmi, yoki struktura bearish'ga o'tganmi. (Faqat lookback ichidagi
        # setup uchun ma'noli — undan eskisi allaqachon "tarixiy kontekst".)
        invalidated_reason: str | None = None
        after_entry = df.iloc[last_signal.entry_index_pos + 1 :]
        if len(after_entry) and bool((after_entry["close"] < last_signal.stop_price).any()):
            invalidated_reason = _INVALIDATION_STOP_CLOSE
        elif state is StructureState.BEARISH:
            invalidated_reason = _INVALIDATION_STRUCTURE_BEARISH

        # Entry holati — oxirgi close entry'ga nisbatan qayerda? (faqat "tirik" setup uchun).
        # tol = ENTRY_TOLERANCE_ATR_MULT * ATR — har ticker uchun moslashuvchan (qat'iy % emas).
        # Oxirgi close stop'dan ham past bo'lsa "below" chiqadi (stop-close invalidatsiyasi
        # yuqorida entry'dan keyingi barlar bo'yicha allaqachon tekshirilgan).
        entry_state: str | None = None
        entry_tol: float | None = None
        if within_lookback and invalidated_reason is None:
            atr_series = compute_atr(df)
            atr_now = atr_series.iloc[-1]
            if pd.isna(atr_now):
                atr_now = atr_series.iloc[last_signal.entry_index_pos]
            if pd.isna(atr_now):
                atr_now = last_signal.entry_price * 0.01  # ATR aniqlanmasa — oxirgi chora
            entry_tol = ENTRY_TOLERANCE_ATR_MULT * float(atr_now)
            entry = last_signal.entry_price
            if last_close > entry + entry_tol:
                entry_state = ENTRY_STATE_MISSED
            elif last_close < entry - entry_tol:
                entry_state = ENTRY_STATE_BELOW
            else:
                entry_state = ENTRY_STATE_ACTIVE

        row["SETUP_REASON"] = last_signal.reason
        row["SETUP_ENTRY_DATE"] = last_signal.entry_ts.date().isoformat()
        row["SETUP_BARS_AGO"] = bars_ago
        row["SETUP_INVALIDATED"] = within_lookback and invalidated_reason is not None
        row["SETUP_INVALIDATED_REASON"] = invalidated_reason if row["SETUP_INVALIDATED"] else None
        row["SETUP_ENTRY_STATE"] = entry_state
        row["SETUP_ENTRY_TOLERANCE"] = round(entry_tol, 2) if entry_tol is not None else None
        # "Faol" endi = narx AYNAN entry oynasida (hozir kirsa bo'ladi). Oyna tashqarisidagi
        # (missed/below) yoki invalidatsiya bo'lgan setup'lar asosiy ro'yxatga tushmaydi.
        row["HAS_ACTIVE_SETUP"] = entry_state == ENTRY_STATE_ACTIVE
        row["SETUP_ENTRY"] = round(last_signal.entry_price, 2)
        row["SETUP_STOP"] = round(last_signal.stop_price, 2)

        # Reference target: smc.signal.generate_signals allaqachon hisoblagan target_price —
        # exit_mode'dan qat'iy nazar HAR DOIM mavjud (swing-high yoki R-multiple fallback).
        row["SETUP_REFERENCE_TARGET"] = round(last_signal.target_price, 2)
        planned_rr = compute_planned_rr(last_signal)
        if planned_rr is not None:
            row["SETUP_PLANNED_RR"] = round(planned_rr, 2)
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


def filter_quality_setups(
    rows: list[dict], *, min_rr: float = MIN_PLANNED_RR, show_all: bool = False,
) -> tuple[list[dict], list[dict]]:
    """Faol setup'larni (HAS_ACTIVE_SETUP=True) sifat bo'yicha ikkiga ajratadi:
    (ko'rsatiladigan, past R:R sababli yashiriladigan). Faol bo'lmagan/xato
    qatorlar bu funksiyaga kirmaydi — ular boshqa joyda (mavjudidek) ko'rsatiladi.
    show_all=True bo'lsa hech narsa yashirilmaydi. planned_rr=None (risk<=0,
    amalda deyarli uchramaydi) "past sifat" deb hisoblanmaydi — SETUP_LOW_RR_WARNING
    bilan bir xil konvensiya (haqiqatan hisoblab bo'lmagan holat chalkashtirilmaydi)."""
    active = [r for r in rows if r.get("HAS_ACTIVE_SETUP")]
    if show_all:
        return active, []
    visible, hidden = [], []
    for r in active:
        rr = r.get("SETUP_PLANNED_RR")
        (hidden if rr is not None and rr < min_rr else visible).append(r)
    return visible, hidden


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


_INVALIDATION_LABELS: dict[str, str] = {
    _INVALIDATION_STOP_CLOSE: "narx boshlang'ich stop'dan past yopildi",
    _INVALIDATION_STRUCTURE_BEARISH: "struktura bearish'ga o'tdi",
}


def invalidation_text(row: dict) -> str:
    """SETUP_INVALIDATED_REASON'ni o'qiladigan o'zbekcha izohga aylantiradi."""
    return _INVALIDATION_LABELS.get(row.get("SETUP_INVALIDATED_REASON"), "bekor bo'ldi")


def format_scan_block(row: dict, *, hidden: bool = False) -> str:
    """Bitta symbol uchun o'qiladigan matn blokini yasaydi (jadval EMAS — o'quv fokusi).
    O'ZI FILTRLAMAYDI — `hidden` chaqiruvchi (main()) tomonidan filter_quality_setups()
    natijasiga qarab beriladi."""
    if row.get("ERROR"):
        return f"=== {row['SYMBOL']} ===\nXato: {row['ERROR']}"

    lines = [f"=== {row['SYMBOL']} ==="]

    if row.get("LAST_BAR_DATE"):
        lines.append(f"Oxirgi bar: {row['LAST_BAR_DATE']} (close {row['LAST_CLOSE']})")

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
    elif row.get("SETUP_INVALIDATED"):
        lines.append(
            f"Faol setup: BEKOR BO'LGAN — {invalidation_text(row)} "
            f"(setup {row['SETUP_ENTRY_DATE']}, entry {row['SETUP_ENTRY']}, stop {row['SETUP_STOP']})"
        )
    elif row.get("SETUP_ENTRY_STATE") == ENTRY_STATE_MISSED:
        lines.append(
            f"Faol setup: 🚂 O'TIB KETGAN — narx entry {row['SETUP_ENTRY']}'dan yuqori, "
            f"kirib bo'lmaydi (oxirgi close {row['LAST_CLOSE']}, setup {row['SETUP_ENTRY_DATE']})"
        )
    elif row.get("SETUP_ENTRY_STATE") == ENTRY_STATE_BELOW:
        lines.append(
            f"Faol setup: ⚠️ ZONA ICHIDA — narx entry {row['SETUP_ENTRY']}'dan past, momentum "
            f"kuchsiz (stop {row['SETUP_STOP']}, oxirgi close {row['LAST_CLOSE']}, "
            f"setup {row['SETUP_ENTRY_DATE']})"
        )
    elif hidden:
        lines.append(
            "Faol setup: YASHIRILDI (Planned R:R past — --show-all yoki "
            "--min-rr bilan ko'rsatish mumkin)"
        )
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
    parser.add_argument("--show-all", action="store_true", help="Past R:R setup'larni ham ko'rsatish")
    parser.add_argument(
        "--min-rr", type=float, default=None, help="Sifat chegarasi (default: MIN_PLANNED_RR)"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    symbols = args.symbols if args.symbols else [h.ticker for h in get_core_watchlist()]
    min_rr = args.min_rr if args.min_rr is not None else MIN_PLANNED_RR

    print(BANNER)
    print()

    rows = run_scan(symbols, args.interval, args.provider, mult=args.mult, lookback=args.lookback, exit_mode=args.exit_mode)
    _, hidden_rows = filter_quality_setups(rows, min_rr=min_rr, show_all=args.show_all)
    hidden_symbols = {r["SYMBOL"] for r in hidden_rows}
    for row in rows:
        print(format_scan_block(row, hidden=row["SYMBOL"] in hidden_symbols))
        print()
    if hidden_rows:
        print(
            f"{len(hidden_rows)} ta setup past R:R (< {min_rr}) sababli yashirildi. "
            "--show-all yoki --min-rr bilan ko'rsatish mumkin."
        )


if __name__ == "__main__":
    main()
