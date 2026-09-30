"""tests/test_day08_timestamp_semantics.py: DAY-08B — signal timestamp semantikasi (offline, sintetik).

Temporal model (provider bar timestamp = bar OCHILISH vaqti):
    signal bari      : 10:20 → 10:25   (setup_time = 10:20)
    signal_time      : 10:25           (bar to'liq yopilgan, signal kuzatiladigan payt)
    entry            : 10:25 bar OPEN  (o'zgarmagan, next-bar execution)
    H6 index konteksti: faqat index_bar_end <= signal_time barlar.

Barcha testlar tarmoqsiz ishlaydi (Yahoo Finance'ga bog'liq emas).
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from backtest.day_types import DayBacktestTrade, ExecutionConfig
from backtest.execution import simulate_trade_execution
from backtest.index_regime import run_day08_index_regime_experiment, signal_time_for
from strategy.day.index_regime import IndexRegimeDetector
from strategy.day.types import DaySetup, DaySetupStatus

NY = "America/New_York"
_SESSIONS = ("2026-07-06", "2026-07-07")


def _ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz=NY)


def _synthetic_rth(freq_minutes: int, seed: int) -> pd.DataFrame:
    """Deterministik RTH OHLCV (provider kabi UTC index, timestamp = bar open)."""
    rng = np.random.default_rng(seed)
    frames = []
    price = 500.0
    for day in _SESSIONS:
        idx = pd.date_range(f"{day} 09:30", f"{day} 15:59", freq=f"{freq_minutes}min", tz=NY)
        steps = np.sin(np.arange(len(idx)) / 3.0) * 1.5 + rng.normal(0.05, 0.4, len(idx))
        closes = price + np.cumsum(steps)
        opens = np.concatenate([[price], closes[:-1]])
        highs = np.maximum(opens, closes) + rng.uniform(0.05, 0.5, len(idx))
        lows = np.minimum(opens, closes) - rng.uniform(0.05, 0.5, len(idx))
        vols = rng.uniform(1e5, 5e5, len(idx))
        frames.append(
            pd.DataFrame(
                {"open": opens, "high": highs, "low": lows, "close": closes, "volume": vols},
                index=idx.tz_convert("UTC"),
            )
        )
        price = float(closes[-1])
    return pd.concat(frames)


@pytest.fixture(scope="module")
def data():
    return {
        "spy_5m": _synthetic_rth(5, seed=11),
        "spy_15m": _synthetic_rth(15, seed=12),
        "qqq_5m": _synthetic_rth(5, seed=13),
        "qqq_15m": _synthetic_rth(15, seed=14),
    }


def _detector(d: dict[str, pd.DataFrame]) -> IndexRegimeDetector:
    return IndexRegimeDetector(d["spy_5m"], d["spy_15m"], d["qqq_5m"], d["qqq_15m"])


def _with_bar_scaled(d: dict, key: str, bar_open: pd.Timestamp, factor: float) -> dict:
    """Bitta aniq barni (bar_open bo'yicha) narx bo'yicha buzilgan nusxa."""
    out = dict(d)
    df = d[key].copy()
    assert bar_open in df.index
    df.loc[bar_open, ["open", "high", "low", "close"]] *= factor
    out[key] = df
    return out


def _bar_affects_context(d: dict, key: str, bar_open: pd.Timestamp, at: pd.Timestamp) -> bool:
    """Bar ×5 yoki ×0.2 buzilganda `at` dagi kontekst o'zgaradimi (ya'ni bar ishlatiladimi)."""
    clean = _detector(d).get_context_at(at)
    return any(
        _detector(_with_bar_scaled(d, key, bar_open, f)).get_context_at(at) != clean
        for f in (5.0, 0.2)
    )


def _latest_used_bar_open(det_end: pd.DatetimeIndex, df: pd.DataFrame, at: pd.Timestamp) -> pd.Timestamp:
    k = det_end.searchsorted(at, side="right") - 1
    return df.index[k]


# ----------------------------------------------------------------------
# Test 1 — signal timestamp
# ----------------------------------------------------------------------
def test_signal_time_is_bar_end_not_bar_open():
    setup_time = _ts("2026-07-06 10:20")  # bar 10:20–10:25
    assert signal_time_for(setup_time) == _ts("2026-07-06 10:25")
    assert signal_time_for(setup_time) != setup_time


# ----------------------------------------------------------------------
# Test 2 — next-bar entry (execution o'zgarmagan)
# ----------------------------------------------------------------------
def test_entry_remains_next_bar_open_at_signal_time():
    idx = pd.date_range("2026-07-06 10:00", periods=10, freq="5min", tz=NY).tz_convert("UTC")
    opens = np.linspace(100.0, 101.0, len(idx))
    df = pd.DataFrame(
        {
            "open": opens,
            "high": opens + 0.5,
            "low": opens - 0.5,
            "close": opens + 0.1,
            "volume": 1e5,
        },
        index=idx,
    )
    setup_idx = 4  # 10:20 bar
    assert df.index[setup_idx] == _ts("2026-07-06 10:20")

    setup = DaySetup(symbol="TEST", timestamp=df.index[setup_idx], status=DaySetupStatus.CONFIRMED)
    sim = simulate_trade_execution(df, setup_idx, setup, ExecutionConfig())
    assert sim is not None
    trade = sim.trade

    assert trade.setup_time == _ts("2026-07-06 10:20")  # semantika: signal bari OCHILISHI
    assert trade.entry_time == _ts("2026-07-06 10:25")  # 10:25 bar OPEN
    assert trade.entry_time == signal_time_for(trade.setup_time)
    assert trade.entry_price == pytest.approx(float(df["open"].iloc[setup_idx + 1]))


# ----------------------------------------------------------------------
# Test 3 / 5 — 5m index chegarasi (SPY va QQQ)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("prefix", ["spy", "qqq"])
def test_5m_index_boundary_at_signal_time_1025(data, prefix):
    det = _detector(data)
    at = det._normalize_timestamp(_ts("2026-07-07 10:25"))
    end_5m = getattr(det, f"end_5m_{prefix}")
    df_5m = data[f"{prefix}_5m"]

    # 10:20–10:25 ishlatiladi, 10:25–10:30 ishlatilmaydi
    assert _latest_used_bar_open(end_5m, df_5m, at) == _ts("2026-07-07 10:20")
    assert _bar_affects_context(data, f"{prefix}_5m", _ts("2026-07-07 10:20"), at)
    assert not _bar_affects_context(data, f"{prefix}_5m", _ts("2026-07-07 10:25"), at)


# ----------------------------------------------------------------------
# Test 4 / 5 — 15m index chegarasi (SPY va QQQ)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("prefix", ["spy", "qqq"])
def test_15m_index_boundary_at_signal_time_1025(data, prefix):
    det = _detector(data)
    at = det._normalize_timestamp(_ts("2026-07-07 10:25"))
    end_15m = getattr(det, f"end_15m_{prefix}")

    # 10:00–10:15 ishlatiladi, 10:15–10:30 (forming) ishlatilmaydi
    assert _latest_used_bar_open(end_15m, data[f"{prefix}_15m"], at) == _ts("2026-07-07 10:00")
    assert not _bar_affects_context(data, f"{prefix}_15m", _ts("2026-07-07 10:15"), at)


# ----------------------------------------------------------------------
# Test 6 — aniq chegara: 10:30 da 10:15–10:30 15m bar ishlatiladi
# ----------------------------------------------------------------------
@pytest.mark.parametrize("prefix", ["spy", "qqq"])
def test_15m_bar_becomes_usable_exactly_at_its_end(data, prefix):
    det = _detector(data)
    at = det._normalize_timestamp(_ts("2026-07-07 10:30"))
    end_15m = getattr(det, f"end_15m_{prefix}")

    assert _latest_used_bar_open(end_15m, data[f"{prefix}_15m"], at) == _ts("2026-07-07 10:15")
    assert _bar_affects_context(data, f"{prefix}_15m", _ts("2026-07-07 10:15"), at)


# ----------------------------------------------------------------------
# Test 7 — signal_time dan keyingi barcha index data buzilsa — kontekst o'zgarmaydi
# ----------------------------------------------------------------------
@pytest.mark.parametrize("factor", [5.0, 0.2])
@pytest.mark.parametrize("setup_str", ["2026-07-07 10:20", "2026-07-07 10:25", "2026-07-07 13:40"])
def test_future_mutation_after_signal_time(data, setup_str, factor):
    signal_time = signal_time_for(_ts(setup_str))
    minutes = {"spy_5m": 5, "qqq_5m": 5, "spy_15m": 15, "qqq_15m": 15}

    mutated = {}
    for key, df in data.items():
        out = df.copy()
        after = (out.index + pd.Timedelta(minutes=minutes[key])) > signal_time  # bar_end > T
        out.loc[after, ["open", "high", "low", "close"]] *= factor
        out.loc[after, "volume"] *= 1000.0
        mutated[key] = out

    ctx_clean = _detector(data).get_context_at(signal_time)
    assert ctx_clean.data_sufficient
    assert ctx_clean == _detector(mutated).get_context_at(signal_time)


# ----------------------------------------------------------------------
# Test 8 — forming 15m bar buzilsa — kontekst o'zgarmaydi
# ----------------------------------------------------------------------
@pytest.mark.parametrize("prefix", ["spy", "qqq"])
def test_forming_15m_bar_mutation_has_no_effect(data, prefix):
    # setup 10:20 → signal_time 10:25 → 15m 10:15–10:30 shakllanmoqda
    signal_time = signal_time_for(_ts("2026-07-07 10:20"))
    assert not _bar_affects_context(data, f"{prefix}_15m", _ts("2026-07-07 10:15"), signal_time)


# ----------------------------------------------------------------------
# Runner integratsiyasi: run_day08_index_regime_experiment kontekstni signal_time da qidiradi
# ----------------------------------------------------------------------
class _RecordingDetector:
    def __init__(self, inner: IndexRegimeDetector) -> None:
        self.inner = inner
        self.queried: list[pd.Timestamp] = []

    def get_context_at(self, ts: pd.Timestamp):
        self.queried.append(ts)
        return self.inner.get_context_at(ts)


def test_runner_queries_context_at_signal_time_not_setup_time(data):
    setup_time = _ts("2026-07-07 10:20")
    trade = DayBacktestTrade(
        symbol="TEST",
        setup_time=setup_time,
        entry_time=_ts("2026-07-07 10:25"),
        entry_price=100.0,
        exit_time=_ts("2026-07-07 10:40"),
        exit_price=101.0,
        exit_reason="target",
        stop_price=99.5,
        target_price=101.0,
        gross_return=0.01,
        net_return=0.01,
        risk_per_share=0.5,
        r_multiple=2.0,
    )
    multi = SimpleNamespace(
        tested_symbols=["TEST"],
        symbol_results={"TEST": SimpleNamespace(trades=[trade])},
        per_symbol_metrics=[SimpleNamespace(symbol="TEST", buy_hold_return=0.0)],
        study_window_start=_ts("2026-07-06 09:30"),
        study_window_end=_ts("2026-07-07 16:00"),
        total_sessions=2,
    )
    rec = _RecordingDetector(_detector(data))
    result = run_day08_index_regime_experiment(symbols=["TEST"], multi_result=multi, detector=rec)

    assert rec.queried == [_ts("2026-07-07 10:25")]
    assert result.metadata["h6_context_timestamp"].startswith("signal_time")
