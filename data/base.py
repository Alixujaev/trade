from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from core.models import OHLCV_COLUMNS


class DataSource(ABC):
    @abstractmethod
    def get_history(
        self, symbol: str, lookback_days: int, interval: str = "1d"
    ) -> pd.DataFrame:
        raise NotImplementedError

    @staticmethod
    def _validate(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            raise ValueError("OHLCV data is empty")

        missing = [c for c in OHLCV_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"OHLCV data missing required columns: {missing}")

        df = df[OHLCV_COLUMNS]
        df = df[~df.index.duplicated(keep="first")]
        df = df.sort_index()
        return df
