"""Setup scanner — decision-support, DIREKTIV EMAS: "BUY" demaydi, faqat setup ma'lumotini beradi.

Bot endi trading robot emas ("research phase" natijasi: market/selection/exit edge topilmadi) —
sifatli setuplarni topib, to'liq kontekst bilan ko'rsatadigan skaner. Yakuniy qarorni ODAM qiladi.

Ishlatish:
    python scripts/scan.py [SYMBOLS...] [--interval 1d] [--mode SWING] [--min-score 60]
        [--provider yfinance] [--no-require-trend]

SYMBOLS bo'sh -> config/core_watchlist.py'dagi tickerlar.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Skript qayerdan ishga tushirilishidan qat'iy nazar paketlar topilishi uchun
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.core_watchlist import get_core_watchlist  # noqa: E402
from config.settings import PRIMARY_INTERVAL  # noqa: E402
from data.factory import get_provider  # noqa: E402
from signals.payload import SignalMode, format_payload  # noqa: E402
from signals.scanner import scan_universe  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Setup scanner — decision-support (direktiv emas)")
    parser.add_argument("symbols", nargs="*", help="Bo'sh bo'lsa core_watchlist tickerlari")
    parser.add_argument("--interval", default=PRIMARY_INTERVAL, help="Masalan: 1d")
    parser.add_argument("--mode", default="SWING", choices=["SWING"])
    parser.add_argument("--min-score", type=float, default=None, help="0-100 ball chegarasi")
    parser.add_argument("--provider", default=None, help="yfinance yoki alpaca")
    parser.add_argument("--require-trend", dest="require_trend", action="store_true", default=True)
    parser.add_argument("--no-require-trend", dest="require_trend", action="store_false")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    symbols = args.symbols if args.symbols else [h.ticker for h in get_core_watchlist()]
    provider = get_provider(args.provider)
    mode = SignalMode[args.mode]

    results, skipped = scan_universe(
        symbols, provider, interval=args.interval, mode=mode, min_score=args.min_score,
        require_trend=args.require_trend,
    )

    for payloads in results.values():
        for payload in payloads:
            print(format_payload(payload))
            print()

    if not results:
        print(f"Hech qanday setup topilmadi (min-score {args.min_score}).")
        print()

    scanned = len(symbols)
    found = len(results)
    skip_count = len(skipped)
    no_setup = scanned - found - skip_count
    print(
        f"Skan qilindi: {scanned} symbol | Setup topilgan: {found} symbol | "
        f"Setup yo'q: {no_setup} symbol | Skip: {skip_count} symbol"
    )
    for row in skipped:
        print(f"  SKIP {row['symbol']}: {row['reason']}")


if __name__ == "__main__":
    main()
