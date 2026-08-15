from __future__ import annotations

import pandas as pd

from data.base import DataSource


class YFinanceSource(DataSource):
    def get_history(
        self, symbol: str, lookback_days: int, interval: str = "1d"
    ) -> pd.DataFrame:
        import yfinance as yf

        df = yf.download(
            symbol,
            period=f"{lookback_days}d",
            interval=interval,
            auto_adjust=True,
            progress=False,
        )

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df.columns = [str(c).lower() for c in df.columns]

        return self._validate(df)
