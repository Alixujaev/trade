"""acquisition/provider_adapter.py: thin yfinance adapter for raw OOS bars.

No filtering, deduplication or NaN dropping happens here: what the provider returns is what gets
validated and stored, so integrity problems stay visible instead of being silently cleaned.
"""

from __future__ import annotations

from datetime import datetime, timezone
from importlib import metadata
from typing import Any

import pandas as pd
import yfinance as yf

from acquisition.contract import STORED_COLUMNS, ProviderConfig, validate_interval

_RENAME = {"open": "open", "high": "high", "low": "low", "close": "close", "adj close": "adj_close", "volume": "volume"}


def provider_version() -> str:
    try:
        return metadata.version("yfinance")
    except metadata.PackageNotFoundError:
        return "unknown"


def normalize_frame(raw: pd.DataFrame) -> pd.DataFrame:
    """Lower-case/rename columns and convert the index to tz-aware UTC. Rows are left untouched."""
    df = raw.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [_RENAME.get(str(c).strip().lower(), str(c).strip().lower()) for c in df.columns]
    missing = [c for c in STORED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"provider frame missing columns: {missing}")
    df = df[list(STORED_COLUMNS)]
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("provider frame index is not a DatetimeIndex")
    if df.index.tz is None:
        # yfinance intraday returns exchange-tz-aware timestamps (ignore_tz=False); a naive index is ambiguous.
        raise ValueError("provider returned a tz-naive index; refusing to guess its timezone")
    df.index = df.index.tz_convert("UTC")
    df.index.name = "datetime"
    return df


class YFinanceAdapter:
    def __init__(self, config: ProviderConfig | None = None) -> None:
        self.config = config or ProviderConfig()

    def fetch(self, symbol: str, interval: str, start: datetime, end: datetime) -> tuple[pd.DataFrame, dict[str, Any]]:
        """Download [start, end) for one symbol/interval with every provider option explicit."""
        validate_interval(interval)
        kwargs = self.config.download_kwargs()
        request = {
            "symbol": symbol,
            "interval": interval,
            "requested_start": pd.Timestamp(start).isoformat(),
            "requested_end": pd.Timestamp(end).isoformat(),
            "provider": self.config.provider,
            "provider_version": provider_version(),
            "provider_config": kwargs,
            "request_utc": datetime.now(timezone.utc).isoformat(),
        }
        raw = yf.download(symbol, start=start, end=end, interval=interval, **kwargs)
        if raw is None or raw.empty:
            raise ValueError(f"provider returned no rows for {symbol} {interval}")
        return normalize_frame(raw), request
