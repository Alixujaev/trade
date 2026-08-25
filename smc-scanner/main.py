"""Data layer'ni sinaydigan demo entry point: watchlist bo'ylab yuradi va natija chiqaradi."""

from __future__ import annotations

from config.settings import PRIMARY_INTERVAL
from config.watchlist import get_watchlist
from data.yfinance_provider import YFinanceProvider


def main() -> None:
    provider = YFinanceProvider()
    for symbol in get_watchlist():
        try:
            df = provider.get_ohlcv(symbol, PRIMARY_INTERVAL)
            if df.empty:
                print(f"{symbol}: bo'sh ma'lumot")
                continue
            print(f"{symbol}: {len(df)} bars, last close = {df['close'].iloc[-1]:.2f}")
        except Exception as exc:
            print(f"{symbol}: xato - {exc}")


if __name__ == "__main__":
    main()
