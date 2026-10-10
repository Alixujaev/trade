"""Global pytest fixture'lar.

signals/dedup.py fayl-asosli persistence ishlatadi (TZ 18) — testlar orasida
signal_id'lar to'qnashib bir-biriga aralashmasin va repo ichiga real fayl
yozilmasin uchun, har test funksiyasida default dedup fayli avtomatik
tmp_path'ga almashtiriladi (DedupStore(path=None) shu default'ni ishlatadi).

FROZEN MARKET DATA INVARIANTI: testlar mavjud market-data keshini hech qachon
o'zgartirmaydi.
- Real tarmoq (yfinance / Alpaca / tashqi socket) default holatda bloklangan.
  Provider TTL eskirgan keshni yangilashga urinsa, yuklash xato beradi va
  provider keshdagi faylni o'zgartirmasdan qaytaradi.
- Provider'ning `_write_cache` metodi real `data/cache/` ichiga yozishga
  urinsa `CacheMutationError` ko'tariladi (tmp_path'ga yozish ruxsat etilgan).
- Sessiya boshida va oxirida `data/cache/`, `artifacts/day08/`,
  `artifacts/day08b/` SHA-256 xeshlari solishtiriladi; farq bo'lsa sessiya
  FAIL bo'ladi.
Tarmoqni o'zi monkeypatch qiladigan unit testlar (fake yf.download / _fetch_raw)
avvalgidek ishlaydi — ularning patch'i guard'ni test davomida almashtiradi.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import socket

import pytest

from config.settings import CACHE_DIR
from data import alpaca_provider as alpaca_module
from data import yfinance_provider as yfp_module
from signals import dedup as dedup_module

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REAL_CACHE_DIR = CACHE_DIR.resolve()
FROZEN_DIRS = (
    REAL_CACHE_DIR,
    PROJECT_ROOT / "artifacts" / "day08",
    PROJECT_ROOT / "artifacts" / "day08b",
)
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


class NetworkDisabledInTests(RuntimeError):
    """Testlarda real market-data tarmog'iga chiqishga urinish."""


class CacheMutationError(RuntimeError):
    """Testlarda real market-data keshiga yozishga urinish."""


def _is_real_cache_path(path: Path) -> bool:
    return Path(path).resolve().is_relative_to(REAL_CACHE_DIR)


def _guard_write(original):
    def _write(df, path):
        if _is_real_cache_path(path):
            raise CacheMutationError(f"Testlar real market-data keshini o'zgartira olmaydi: {path}")
        return original(df, path)

    return staticmethod(_write)


def _network_disabled(*args, **kwargs):
    raise NetworkDisabledInTests("Testlarda market-data tarmog'i o'chirilgan (frozen cache)")


_real_socket_connect = socket.socket.connect


def _guarded_connect(self, address, *args, **kwargs):
    host = address[0] if isinstance(address, tuple) else address
    if isinstance(host, str) and host not in _LOCAL_HOSTS:
        raise NetworkDisabledInTests(f"Testlarda tashqi tarmoq o'chirilgan: {address!r}")
    return _real_socket_connect(self, address, *args, **kwargs)


def _install_session_market_data_guard() -> None:
    """DAY-26C: session-wide hard guard, installed when this conftest is imported, i.e. before collection and before
    any module- or session-scoped fixture runs. The function-scoped fixture below only starts with each test, so
    module-scoped fixtures (tests/test_day08*..test_day12b*) previously ran unguarded, and on 2026-10-10 they
    downloaded recent yfinance intraday data into data/cache/ (artifacts/day26c/day26c-forward-data-incident.md).
    Tests that install their own fake download through monkeypatch still work; on teardown they restore this guard."""
    yfp_module.yf.download = _network_disabled
    yfp_module.yf.Ticker.history = _network_disabled
    alpaca_module.AlpacaProvider._fetch_raw = _network_disabled
    for cls in (yfp_module.YFinanceProvider, alpaca_module.AlpacaProvider):
        cls._write_cache = _guard_write(cls.__dict__["_write_cache"].__func__)
    socket.socket.connect = _guarded_connect


_install_session_market_data_guard()


@pytest.fixture(autouse=True)
def _isolated_dedup_store_path(tmp_path, monkeypatch):
    monkeypatch.setattr(dedup_module, "DEFAULT_DEDUP_PATH", tmp_path / "signal_dedup.json")


@pytest.fixture(autouse=True)
def _frozen_market_data_guard(monkeypatch):
    monkeypatch.setattr(yfp_module.yf, "download", _network_disabled)
    monkeypatch.setattr(alpaca_module.AlpacaProvider, "_fetch_raw", _network_disabled)
    monkeypatch.setattr(
        yfp_module.YFinanceProvider,
        "_write_cache",
        yfp_module.YFinanceProvider.__dict__["_write_cache"],        # already guarded at import (DAY-26C)
    )
    monkeypatch.setattr(
        alpaca_module.AlpacaProvider,
        "_write_cache",
        alpaca_module.AlpacaProvider.__dict__["_write_cache"],
    )
    monkeypatch.setattr(socket.socket, "connect", _guarded_connect)


# --- Sessiya darajasidagi yaxlitlik tekshiruvi ---

def _snapshot() -> dict[str, str]:
    out: dict[str, str] = {}
    for d in FROZEN_DIRS:
        if not d.is_dir():
            continue
        for p in sorted(d.rglob("*")):
            if p.is_file():
                out[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def pytest_sessionstart(session):
    session.config._frozen_snapshot = _snapshot()


def pytest_sessionfinish(session, exitstatus):
    before = getattr(session.config, "_frozen_snapshot", None)
    if before is None:
        return
    after = _snapshot()
    changed = sorted(
        p for p in before.keys() | after.keys() if before.get(p) != after.get(p)
    )
    if changed:
        tr = session.config.pluginmanager.get_plugin("terminalreporter")
        msg = "FROZEN DATA MUTATED DURING TESTS:\n  " + "\n  ".join(changed)
        if tr is not None:
            tr.write_line(msg, red=True)
        else:
            print(msg)
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
