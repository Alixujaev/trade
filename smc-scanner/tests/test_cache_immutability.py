"""tests/test_cache_immutability.py: testlar frozen market-data keshini o'zgartira olmasligi.

Regressiya: DAY-08 testlari TTL eskirgan keshni yfinance'dan qayta yuklab, frozen
SPY/QQQ/AAPL_15m fayllarini ustidan yozgan edi. Guard tests/conftest.py da.
"""

from __future__ import annotations

import hashlib
import os

import pandas as pd
import pytest

from config.settings import CACHE_DIR
from data import yfinance_provider as yfp_module
from data.alpaca_provider import AlpacaProvider
from data.yfinance_provider import YFinanceProvider
from tests.conftest import CacheMutationError, NetworkDisabledInTests

FROZEN_SPY_5M = CACHE_DIR / "SPY_5m.parquet"


def _sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tiny_df() -> pd.DataFrame:
    idx = pd.date_range("2024-06-03 13:30", periods=2, freq="5min", tz="UTC")
    return pd.DataFrame(
        {"open": [1.0, 1.0], "high": [1.0, 1.0], "low": [1.0, 1.0], "close": [1.0, 1.0], "volume": [1, 1]},
        index=idx,
    )


def test_yfinance_network_is_blocked_by_default() -> None:
    with pytest.raises(NetworkDisabledInTests):
        yfp_module.yf.download("SPY", period="1d", interval="5m")


def test_alpaca_network_is_blocked_by_default() -> None:
    with pytest.raises(NetworkDisabledInTests):
        AlpacaProvider()._fetch_raw("SPY", "5m", 1)


@pytest.mark.skipif(not FROZEN_SPY_5M.exists(), reason="frozen SPY_5m cache mavjud emas")
def test_ttl_expired_cache_read_does_not_refetch_or_overwrite() -> None:
    """ignore_cache_expiry'siz o'qish (TTL eskirgan) kesh faylini o'zgartirmasdan qaytaradi."""
    sha_before = _sha(FROZEN_SPY_5M)
    mtime_before = FROZEN_SPY_5M.stat().st_mtime_ns
    assert not YFinanceProvider._is_cache_fresh(FROZEN_SPY_5M, interval="5m"), "kesh TTL ichida — test ma'nosiz"

    got = YFinanceProvider().get_ohlcv("SPY", "5m", include_extended_hours=False, closed_only=False)

    pd.testing.assert_frame_equal(got, pd.read_parquet(FROZEN_SPY_5M))
    assert _sha(FROZEN_SPY_5M) == sha_before
    assert FROZEN_SPY_5M.stat().st_mtime_ns == mtime_before


def test_write_into_real_cache_dir_is_rejected() -> None:
    probe = CACHE_DIR / "__guard_probe__.parquet"
    assert not probe.exists()
    with pytest.raises(CacheMutationError):
        YFinanceProvider._write_cache(_tiny_df(), probe)
    with pytest.raises(CacheMutationError):
        AlpacaProvider._write_cache(_tiny_df(), probe)
    assert not probe.exists()


def test_write_into_tmp_cache_dir_still_works(tmp_path) -> None:
    """Sintetik fixture semantikasi saqlanadi: tmp_path keshiga yozish mumkin."""
    target = tmp_path / "X_5m.parquet"
    YFinanceProvider._write_cache(_tiny_df(), target)
    assert target.exists()


def test_uncached_symbol_without_network_fails_loudly(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(yfp_module, "CACHE_DIR", tmp_path)
    with pytest.raises(NetworkDisabledInTests):
        YFinanceProvider().get_ohlcv("ZZZZ", "5m")
    assert os.listdir(tmp_path) == []
