"""Ayiq bozori stress-testi: SMC strategiyani aniq tarixiy ayiq oynalarida sinaydi.

Gipoteza: kam-exposure (signal-driven) strategiya ayiq bozorida buy&hold'dan kam
yo'qotishi (yoki musbat qolishi) mumkin — chunki u ko'p vaqtni naqd holatda o'tkazadi.
Phase 6 shuni ko'rsatdiki, buqa bozorida bu KAMCHILIK (past exposure = yo'qotilgan
foyda); bu skript teskari savolni beradi: pasayishda bu USTUNLIKmi?

Signal engine yoki backtest simulyatsiyasi O'ZGARTIRILMAYDI — faqat mavjud
pipeline (scripts/backtest_matrix.py::run_one_combination) aniq sana oynalarida
qayta ishlatiladi (backtest/window.py orqali, lookahead'siz — u yerdagi izohga qarang).

Interval FAQAT "1d" (yfinance) — Alpaca free tier tarixi atigi ~60 kun
(config.settings.ALPACA_LOOKBACK_DAYS_INTRADAY), 2020/2022 kabi tarixiy oynalarni
umuman qamrab ololmaydi, shuning uchun bu yerda 4h ma'nosiz va taklif qilinmaydi.

MUHIM statistik ogohlik: bu oynalar QISQA (3-12 oy), savdolar SON JIHATDAN KAM
bo'ladi. Natijalarni "isbot" emas, "tendentsiya/signal" sifatida o'qing — LOW_SAMPLE
flag'iga alohida e'tibor bering, ayniqsa covid_2020 (atigi 3 oy) uchun.

Ishlatish:
    python scripts/bear_market_test.py [SYMBOLS...] [--risk-model fixed_pct|atr] [--mult 1.5]

Masalan: python scripts/bear_market_test.py
         python scripts/bear_market_test.py AAPL AMD --risk-model atr --mult 1.0

SYMBOLS berilmasa — DEFAULT_SYMBOLS ishlatiladi (Phase 6'dagi tekshiruv to'plami).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

# Skript qayerdan ishga tushirilishidan qat'iy nazar paketlar topilishi uchun
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import SWING_LOOKBACK  # noqa: E402
from scripts.backtest_matrix import run_one_combination  # noqa: E402

WINDOWS: dict[str, tuple[str, str]] = {
    "covid_2020": ("2020-02-01", "2020-05-01"),
    "bear_2022": ("2022-01-01", "2022-12-31"),
}

DEFAULT_SYMBOLS: list[str] = ["SPUS", "HLAL", "AAPL", "AMD", "AVGO", "FSLR"]

# Bu qisqa oynalarda savdolar tabiiy ravishda kam bo'ladi — Phase 6'dagi 10'dan
# pastroq chegara, aks holda deyarli hamma natija LOW_SAMPLE bo'lib chiqar edi.
LOW_SAMPLE_THRESHOLD: int = 5

_ROW_COLUMNS = ["SYMBOL", "WINDOW", "TRADES", "WIN%", "RETURN%", "MAXDD%", "BUY&HOLD%", "EDGE", "LOW_SAMPLE"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ayiq bozori stress-testi (2020/2022 oynalari)")
    parser.add_argument("symbols", nargs="*", default=DEFAULT_SYMBOLS, help="Bo'sh bo'lsa DEFAULT_SYMBOLS")
    parser.add_argument("--risk-model", default="fixed_pct", choices=["fixed_pct", "atr"])
    parser.add_argument("--mult", type=float, default=None, help="Displacement ATR mult (default: settings)")
    parser.add_argument("--lookback", type=int, default=SWING_LOOKBACK)
    return parser.parse_args()


def run_one_window(
    symbol: str, window_name: str, start_date: str, end_date: str,
    risk_model: str, mult: float | None, lookback: int,
) -> dict:
    """Bitta (symbol, window) juftligi uchun natija qatorini hisoblaydi (Phase 6 runner'ini qayta ishlatib)."""
    full_row = run_one_combination(
        symbol, "1d", "yfinance", risk_model, mult,
        lookback=lookback, low_sample_threshold=LOW_SAMPLE_THRESHOLD,
        start_date=start_date, end_date=end_date,
    )
    row = {
        "SYMBOL": symbol,
        "WINDOW": window_name,
        "TRADES": full_row["TRADES"],
        "WIN%": full_row["WIN%"],
        "RETURN%": full_row["RETURN%"],
        "MAXDD%": full_row["MAXDD%"],
        "BUY&HOLD%": full_row["BUY&HOLD%"],
        "EDGE": full_row["EDGE"],
        "LOW_SAMPLE": full_row["LOW_SAMPLE"],
        "ERROR": full_row["ERROR"],
    }
    return row


def build_matrix(symbols: list[str], risk_model: str, mult: float | None, lookback: int) -> pd.DataFrame:
    rows = [
        run_one_window(symbol, window_name, start, end, risk_model, mult, lookback)
        for symbol in symbols
        for window_name, (start, end) in WINDOWS.items()
    ]
    return pd.DataFrame(rows)


def print_summary(matrix: pd.DataFrame) -> None:
    valid = matrix[matrix["ERROR"].isna()]
    for window_name in WINDOWS:
        window_rows = valid[valid["WINDOW"] == window_name]
        if window_rows.empty:
            continue
        avg_edge = window_rows["EDGE"].mean()
        n_positive = int((window_rows["EDGE"] > 0).sum())
        n_total = len(window_rows)
        n_low_sample = int(window_rows["LOW_SAMPLE"].sum())

        print(f"\n[{window_name}] o'rtacha EDGE={avg_edge:.2f}, "
              f"{n_positive}/{n_total} symbolda musbat EDGE, "
              f"{n_low_sample}/{n_total} LOW_SAMPLE (savdolar < {LOW_SAMPLE_THRESHOLD})")

        bearish_buy_hold = window_rows[window_rows["BUY&HOLD%"] < 0]
        if bearish_buy_hold.empty:
            print("  (bu oynada buy&hold hech qaysi symbol uchun manfiy chiqmadi)")
        else:
            print("  Buy&hold MANFIY bo'lgan holatlar (asosiy qiziqish):")
            print(bearish_buy_hold[_ROW_COLUMNS[:-1]].to_string(index=False))


def main() -> None:
    args = parse_args()

    print(
        "MUHIM: bu oynalar QISQA (3-12 oy) — savdolar soni tabiiy ravishda kam bo'ladi.\n"
        "Natijalarni 'isbot' emas, tendentsiya/signal sifatida o'qing. LOW_SAMPLE=True "
        f"(savdolar < {LOW_SAMPLE_THRESHOLD}) bo'lgan qatorlarga alohida ehtiyot bilan qarang — "
        "bu ayniqsa covid_2020 (eng qisqa oyna) uchun kutilgan holat.\n"
    )

    matrix = build_matrix(args.symbols, args.risk_model, args.mult, args.lookback)

    print(matrix[_ROW_COLUMNS].to_string(index=False))

    n_errors = matrix["ERROR"].notna().sum()
    if n_errors:
        print(f"\n{n_errors} kombinatsiya xato berdi:")
        print(matrix[matrix["ERROR"].notna()][["SYMBOL", "WINDOW", "ERROR"]].to_string(index=False))

    print_summary(matrix)


if __name__ == "__main__":
    main()
