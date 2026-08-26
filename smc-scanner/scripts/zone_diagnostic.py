"""Zone kalibratsiya diagnostikasi: qaysi instrument/timeframe/mult chegarasi
mazmunli (juda kam yoki juda ko'p bo'lmagan) zona berishini ko'rish uchun skript.

Signal engine hali qurilmagan — bu FAQAT diagnostika: har (symbol, mult) juftligi
uchun FVG/OB sonlarini jadval qilib chiqaradi, shu orqali DISPLACEMENT_ATR_MULT'ni
tanlashda yordam beradi.

Ishlatish:
    python scripts/zone_diagnostic.py [SYMBOLS...] [--interval 1d|4h|1h|1wk]
        [--provider yfinance|alpaca] [--mults "1.0,1.25,1.5"]

Masalan: python scripts/zone_diagnostic.py --interval 4h --provider alpaca
         python scripts/zone_diagnostic.py SPUS HLAL --interval 4h --provider alpaca --mults "0.75,1.0,1.5"

SYMBOLS berilmasa — config/watchlist.py'dagi halal ETF ro'yxati ishlatiladi.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

# Skript qayerdan ishga tushirilishidan qat'iy nazar paketlar topilishi uchun
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import PRIMARY_INTERVAL  # noqa: E402
from config.watchlist import get_watchlist  # noqa: E402
from data.factory import get_provider  # noqa: E402
from smc.types import StructureState  # noqa: E402
from smc.zones import detect_fvgs, detect_order_blocks  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Zone kalibratsiya diagnostikasi")
    parser.add_argument(
        "symbols", nargs="*", help="Masalan: SPUS HLAL. Bo'sh bo'lsa watchlist ishlatiladi"
    )
    parser.add_argument("--interval", default=PRIMARY_INTERVAL, help="Masalan: 1d, 4h")
    parser.add_argument(
        "--provider", default=None, help="yfinance yoki alpaca (default: settings.DATA_PROVIDER)"
    )
    parser.add_argument(
        "--mults", default="1.0,1.25,1.5", help="Vergul bilan ajratilgan mult qiymatlari"
    )
    return parser.parse_args()


def _count_row(symbol: str, mult: float, bars: int, fvgs: list, obs: list) -> dict:
    """Bitta (symbol, mult) juftligi uchun jadval qatorini hisoblaydi."""
    open_fvgs = [z for z in fvgs if not z.filled]
    open_obs = [z for z in obs if not z.filled]
    open_zones = open_fvgs + open_obs

    bull_open = sum(1 for z in open_zones if z.direction is StructureState.BULLISH)
    bear_open = sum(1 for z in open_zones if z.direction is StructureState.BEARISH)

    return {
        "SYMBOL": symbol,
        "MULT": f"{mult:.2f}",
        "BARS": bars,
        "FVG(open/tot)": f"{len(open_fvgs)}/{len(fvgs)}",
        "OB(open/tot)": f"{len(open_obs)}/{len(obs)}",
        "bull_open": bull_open,
        "bear_open": bear_open,
    }


def main() -> None:
    args = parse_args()
    symbols = args.symbols if args.symbols else get_watchlist()
    mults = [float(m.strip()) for m in args.mults.split(",")]

    provider = get_provider(args.provider)
    rows: list[dict] = []

    for symbol in symbols:
        try:
            df = provider.get_ohlcv(symbol, args.interval)
        except Exception as exc:
            print(f"{symbol}: xato - {exc}")
            continue

        # df bitta marta olinadi, har mult uchun qayta ishlatiladi (keraksiz tarmoq/kesh chaqiruvi yo'q)
        for mult in mults:
            fvgs = detect_fvgs(df, mult=mult)
            obs = detect_order_blocks(df, mult=mult)
            rows.append(_count_row(symbol, mult, len(df), fvgs, obs))

    if not rows:
        print("Hech qanday natija yo'q — barcha symbol'lar xato berdi.")
        return

    result = pd.DataFrame(rows)
    print(result.to_string(index=False))


if __name__ == "__main__":
    main()
