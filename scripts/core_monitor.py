"""CORE (buy&hold) watchlist monitori: narx, o'zgarish va trend konteksti kuzatuvi.

MUHIM PRINSIP: bu skript halal/harom QARORINI O'ZI HISOBLAMAYDI. Screening —
tashqi, ishonchli manbalar ishi (Musaffa/Zoya/akinda yoki ETF holdings). Bu
skript faqat FOYDALANUVCHI allaqachon tasdiqlagan ro'yxatni (config/core_watchlist.py)
saqlaydi, narx/holatni kuzatadi va qachon qayta tekshiruv kerakligini belgilaydi.

Narx, o'zgarish% va TREND_KONTEKST ustunlari FAQAT AXBOROT uchun — savdo signali
EMAS. TREND_KONTEKST (200-kunlik SMA ustida/ostida) ham xuddi shunday — bu
buy&hold qarorini o'zgartirmaydi, faqat umumiy bozor konteksti.

Ishlatish:
    python scripts/core_monitor.py [--interval 1d] [--provider yfinance] [--review-days 90]
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd

# Skript qayerdan ishga tushirilishidan qat'iy nazar paketlar topilishi uchun
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.core_watchlist import CoreHolding, get_core_watchlist  # noqa: E402
from config.settings import PRIMARY_INTERVAL, REVIEW_INTERVAL_DAYS  # noqa: E402
from data.factory import get_provider  # noqa: E402

_WEEK_BARS = 5  # ~1 savdo haftasi (kalendar kun emas — sodda, yetarli)
_MONTH_BARS = 21  # ~1 savdo oyi
_YEAR_BARS = 252  # ~52 savdo haftasi
_SMA_PERIOD = 200


def needs_review(last_reviewed: date | None, review_interval_days: int, *, today: date | None = None) -> bool:
    """last_reviewed=None -> doim True (hali bu asbob orqali tekshirilmagan)."""
    if last_reviewed is None:
        return True
    today = today if today is not None else date.today()
    return (today - last_reviewed).days >= review_interval_days


def pct_change(current: float, past: float | None) -> float | None:
    """(current-past)/past*100. past None/<=0 bo'lsa None (bo'lish xatosi oldini olish)."""
    if past is None or past <= 0:
        return None
    return (current - past) / past * 100


def pct_below_52w_high(current: float, high_52w: float | None) -> float | None:
    """52 haftalik high'dan necha % pastda. 0 = hozir high'da."""
    if high_52w is None or high_52w <= 0:
        return None
    return (high_52w - current) / high_52w * 100


def trend_context(current_close: float, sma_200: float | None) -> str:
    """"bull"/"bear"/"N/A" — bu KONTEKST, savdo SIGNALI emas."""
    if sma_200 is None:
        return "N/A"
    return "bull" if current_close >= sma_200 else "bear"


def build_row(
    holding: CoreHolding,
    df: pd.DataFrame,
    *,
    review_interval_days: int = REVIEW_INTERVAL_DAYS,
    today: date | None = None,
) -> dict:
    """Bitta ticker uchun jadval qatorini hisoblaydi (barcha metrikalar AXBOROT uchun)."""
    closes = df["close"]
    highs = df["high"]
    current = float(closes.iloc[-1])

    change_1w = pct_change(current, float(closes.iloc[-1 - _WEEK_BARS])) if len(closes) > _WEEK_BARS else None
    change_1m = pct_change(current, float(closes.iloc[-1 - _MONTH_BARS])) if len(closes) > _MONTH_BARS else None

    high_52w = float(highs.tail(_YEAR_BARS).max())
    below_52w = pct_below_52w_high(current, high_52w)

    sma_200 = None
    if len(closes) >= _SMA_PERIOD:
        sma_val = closes.rolling(_SMA_PERIOD).mean().iloc[-1]
        if not pd.isna(sma_val):
            sma_200 = float(sma_val)
    trend = trend_context(current, sma_200)

    return {
        "TICKER": holding.ticker,
        "TOIFA": holding.category,
        "NARX": round(current, 2),
        "O'ZGARISH_1H%": round(change_1w, 2) if change_1w is not None else None,
        "O'ZGARISH_1O%": round(change_1m, 2) if change_1m is not None else None,
        "52W_HIGH_DAN%": round(below_52w, 2) if below_52w is not None else None,
        "TREND_KONTEKST": trend,
        "HALAL_MANBA": holding.halal_source,
        "OXIRGI_TEKSHIRUV": holding.last_reviewed.isoformat() if holding.last_reviewed else "Hech qachon",
        "TEKSHIRUV_KERAKMI": "Ha" if needs_review(holding.last_reviewed, review_interval_days, today=today) else "Yo'q",
        "ERROR": None,
    }


def _error_row(holding: CoreHolding, exc: Exception) -> dict:
    return {
        "TICKER": holding.ticker,
        "TOIFA": holding.category,
        "NARX": None,
        "O'ZGARISH_1H%": None,
        "O'ZGARISH_1O%": None,
        "52W_HIGH_DAN%": None,
        "TREND_KONTEKST": None,
        "HALAL_MANBA": holding.halal_source,
        "OXIRGI_TEKSHIRUV": holding.last_reviewed.isoformat() if holding.last_reviewed else "Hech qachon",
        "TEKSHIRUV_KERAKMI": None,
        "ERROR": str(exc),
    }


def run_monitor(
    watchlist: list[CoreHolding],
    provider_name: str | None,
    interval: str,
    review_interval_days: int,
    *,
    today: date | None = None,
) -> pd.DataFrame:
    """Watchlist bo'ylab yuradi; bitta ticker xato bersa (tarmoq, yetarsiz data va h.k.)
    crash qilmasdan ERROR maydonli qator qaytaradi, qolganlari bilan davom etadi."""
    rows: list[dict] = []
    for holding in watchlist:
        try:
            df = get_provider(provider_name).get_ohlcv(holding.ticker, interval)
            if df.empty:
                raise ValueError("bo'sh ma'lumot qaytdi")
            rows.append(build_row(holding, df, review_interval_days=review_interval_days, today=today))
        except Exception as exc:
            rows.append(_error_row(holding, exc))
    return pd.DataFrame(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Core watchlist monitori — narx/kontekst kuzatuvi (halal QARORI EMAS)"
    )
    parser.add_argument("--interval", default=PRIMARY_INTERVAL, help="Masalan: 1d")
    parser.add_argument(
        "--provider", default=None, help="yfinance yoki alpaca (default: settings.DATA_PROVIDER)"
    )
    parser.add_argument("--review-days", type=int, default=REVIEW_INTERVAL_DAYS)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    watchlist = get_core_watchlist()

    print(
        "ESLATMA: narx, o'zgarish% va TREND_KONTEKST ustunlari FAQAT AXBOROT uchun — "
        "bu savdo signali EMAS, faqat kuzatuv.\n"
    )

    matrix = run_monitor(watchlist, args.provider, args.interval, args.review_days)
    print(matrix.drop(columns=["ERROR"]).to_string(index=False))

    n_errors = matrix["ERROR"].notna().sum()
    if n_errors:
        print(f"\n{n_errors} ticker xato berdi:")
        print(matrix[matrix["ERROR"].notna()][["TICKER", "ERROR"]].to_string(index=False))

    print(
        "\nBu asbob halal statusni HISOBLAMAYDI. Har ticker o'z manbangizda "
        "(Musaffa/Zoya/akinda yoki ETF holdings) davriy qayta tekshirilishi shart. "
        "TEKSHIRUV_KERAKMI=Ha bo'lganlarni qayta ko'ring."
    )


if __name__ == "__main__":
    main()
