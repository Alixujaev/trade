"""Data layer'ni sinaydigan demo entry point: watchlist bo'ylab yuradi va natija chiqaradi."""

from __future__ import annotations

import argparse

from config.settings import PRIMARY_INTERVAL
from config.watchlist import get_watchlist
from data.factory import get_provider


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Watchlist bo'ylab OHLCV ma'lumotini tekshiradi")
    parser.add_argument("--interval", default=PRIMARY_INTERVAL, help="Masalan: 1d, 4h")
    parser.add_argument(
        "--provider", default=None, help="yfinance yoki alpaca (default: settings.DATA_PROVIDER)"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    provider = get_provider(args.provider)
    for symbol in get_watchlist():
        try:
            df = provider.get_ohlcv(symbol, args.interval)
            if df.empty:
                print(f"{symbol}: bo'sh ma'lumot")
                continue
            print(f"{symbol}: {len(df)} bars, last close = {df['close'].iloc[-1]:.2f}")
        except Exception as exc:
            print(f"{symbol}: xato - {exc}")


if __name__ == "__main__":
    main()
