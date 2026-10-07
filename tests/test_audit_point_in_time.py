"""tests/test_audit_point_in_time.py: DAY-01 VWAP Momentum uchun qat'iy adversarial anti-lookahead testlar."""

from __future__ import annotations

from datetime import datetime
import pandas as pd
import pytest

from data.bars import filter_closed_bars
from data.provider import DataProvider
from levels.intraday_levels import compute_intraday_levels
from signals.day_scanner import format_day_setup, scan_day
from strategy.day.types import DaySetupStatus, VwapRelation
from strategy.day.vwap_momentum import evaluate_vwap_momentum


class AdversarialMockProvider(DataProvider):
    """Adversarial testlar uchun mock provayder."""

    def __init__(
        self,
        df_5m: pd.DataFrame,
        df_15m: pd.DataFrame | None = None,
        df_ext: pd.DataFrame | None = None,
    ) -> None:
        self.df_5m = df_5m
        self.df_15m = df_15m if df_15m is not None else pd.DataFrame()
        self.df_ext = df_ext if df_ext is not None else pd.DataFrame()

    def get_ohlcv(
        self,
        symbol: str,
        interval: str,
        *,
        include_extended_hours: bool = False,
        closed_only: bool = True,
        as_of: datetime | pd.Timestamp | None = None,
    ) -> pd.DataFrame:
        if include_extended_hours:
            df = self.df_ext
        elif interval == "5m":
            df = self.df_5m
        elif interval == "15m":
            df = self.df_15m
        else:
            df = pd.DataFrame()

        if closed_only and not df.empty:
            df = filter_closed_bars(df, interval, as_of=as_of)
        return df


def _generate_dataset(n_bars: int = 50) -> pd.DataFrame:
    """09:30 dan boshlab 5m barlar to'plamini hosil qiladi."""
    idx = pd.date_range("2026-01-05 09:30", periods=n_bars, freq="5min", tz="America/New_York")
    # Narxlar: dastlabki barlarda reclaim bor (10:00 atrofida)
    # 09:30..09:55 (6 bar): 100 da
    # 10:00 (bar 6): 99.0
    # 10:05 (bar 7): 100.8 (reclaim)
    # qolgan barlar 101.0
    closes = [100.0] * 6 + [99.0, 100.8] + [101.0] * (n_bars - 8)
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    opens = [c - 0.1 for c in closes]
    vols = [1000.0] * n_bars

    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": vols},
        index=idx,
    )


def test_adversarial_a_future_candle_changes_swing() -> None:
    """Test A: 10:10 gacha bo'lgan data (A) va unga kelajak candle'lar qo'shilgan (B).

    10:10 dagi scanner outputi ikkalasida 100% IDENTICAL bo'lishi shart.
    """
    # Dataset A: faqat 10:10 gacha (8 ta bar: 09:30..10:05, bar 10:05 closes at 10:10)
    # Kerakli 15 ta bar bo'lishi uchun 09:00 dan boshlaymiz (yoki yetarli tarix beramiz)
    idx_a = pd.date_range("2026-01-05 08:30", periods=21, freq="5min", tz="America/New_York")
    # 08:30 dan 10:05 gacha (bar 10:05 closes at 10:10)
    # Barlar: 09:30 dan oldingilar premarket, 09:30 dan RTH
    # 09:30..10:00: 100.0, 10:00: 99.0, 10:05: 100.8
    closes_a = [100.0] * 19 + [99.0, 100.8]
    df_a = pd.DataFrame(
        {
            "open": closes_a,
            "high": [c + 0.5 for c in closes_a],
            "low": [c - 0.5 for c in closes_a],
            "close": closes_a,
            "volume": [1000.0] * len(closes_a),
        },
        index=idx_a,
    )

    # Dataset B: df_a + kelajakdagi 30 ta bar (10:10 dan 12:40 gacha)
    idx_b = pd.date_range("2026-01-05 08:30", periods=51, freq="5min", tz="America/New_York")
    # Kelajakda ulkan narx o'zgarishlari va swinglar
    closes_b = list(closes_a) + [110.0 + i * 2.0 for i in range(30)]
    df_b = pd.DataFrame(
        {
            "open": closes_b,
            "high": [c + 1.0 for c in closes_b],
            "low": [c - 1.0 for c in closes_b],
            "close": closes_b,
            "volume": [5000.0] * len(closes_b),
        },
        index=idx_b,
    )

    as_of_t = pd.Timestamp("2026-01-05 10:10", tz="America/New_York")

    prov_a = AdversarialMockProvider(df_5m=df_a)
    prov_b = AdversarialMockProvider(df_5m=df_b)

    setup_a = scan_day("AAPL", provider=prov_a, as_of=as_of_t)
    setup_b = scan_day("AAPL", provider=prov_b, as_of=as_of_t)

    assert setup_a.status == setup_b.status
    assert setup_a.price == setup_b.price
    assert setup_a.vwap == pytest.approx(setup_b.vwap)
    assert setup_a.vwap_relation == setup_b.vwap_relation
    assert setup_a.trigger == setup_b.trigger
    assert setup_a.evidence == setup_b.evidence
    assert setup_a.warnings == setup_b.warnings
    assert format_day_setup(setup_a) == format_day_setup(setup_b)


def test_adversarial_b_future_volume() -> None:
    """Test B: 10:10 dan keyingi hajm 100 barobarga oshirilsa ham 10:10 dagi signal o'zgarmasligi kerak."""
    idx = pd.date_range("2026-01-05 08:30", periods=30, freq="5min", tz="America/New_York")
    closes = [100.0] * 19 + [99.0, 100.8] + [101.0] * 9
    vols_normal = [1000.0] * 30
    vols_extreme = [1000.0] * 21 + [1_000_000.0] * 9  # 10:10 dan keyin 1M volume

    df_normal = pd.DataFrame(
        {"open": closes, "high": [c + 0.5 for c in closes], "low": [c - 0.5 for c in closes], "close": closes, "volume": vols_normal},
        index=idx,
    )
    df_extreme = pd.DataFrame(
        {"open": closes, "high": [c + 0.5 for c in closes], "low": [c - 0.5 for c in closes], "close": closes, "volume": vols_extreme},
        index=idx,
    )

    as_of_t = pd.Timestamp("2026-01-05 10:10", tz="America/New_York")

    setup_normal = scan_day("AAPL", provider=AdversarialMockProvider(df_5m=df_normal), as_of=as_of_t)
    setup_extreme = scan_day("AAPL", provider=AdversarialMockProvider(df_5m=df_extreme), as_of=as_of_t)

    assert setup_normal.vwap == pytest.approx(setup_extreme.vwap)
    assert setup_normal.rvol == pytest.approx(setup_extreme.rvol, nan_ok=True)
    assert setup_normal.status == setup_extreme.status
    assert setup_normal.evidence_score == setup_extreme.evidence_score


def test_adversarial_c_future_price() -> None:
    """Test C: 10:10 dan keyin narx +50% ga sakrab ketsa ham 10:10 dagi setup o'zgarmaydi."""
    idx = pd.date_range("2026-01-05 08:30", periods=30, freq="5min", tz="America/New_York")
    closes_normal = [100.0] * 19 + [99.0, 100.8] + [101.0] * 9
    closes_pump = [100.0] * 19 + [99.0, 100.8] + [200.0] * 9  # +100% crash or pump

    df_norm = pd.DataFrame(
        {"open": closes_normal, "high": [c + 0.5 for c in closes_normal], "low": [c - 0.5 for c in closes_normal], "close": closes_normal, "volume": [1000.0]*30},
        index=idx,
    )
    df_pump = pd.DataFrame(
        {"open": closes_pump, "high": [c + 0.5 for c in closes_pump], "low": [c - 0.5 for c in closes_pump], "close": closes_pump, "volume": [1000.0]*30},
        index=idx,
    )

    as_of_t = pd.Timestamp("2026-01-05 10:10", tz="America/New_York")

    setup_norm = scan_day("AAPL", provider=AdversarialMockProvider(df_5m=df_norm), as_of=as_of_t)
    setup_pump = scan_day("AAPL", provider=AdversarialMockProvider(df_5m=df_pump), as_of=as_of_t)

    assert setup_norm.price == setup_pump.price
    assert setup_norm.rsi == pytest.approx(setup_pump.rsi, nan_ok=True)
    assert setup_norm.vwap == pytest.approx(setup_pump.vwap)
    assert setup_norm.status == setup_pump.status


def test_adversarial_d_future_15m_structure() -> None:
    """Test D: 10:10 dan keyingi 15m barlarda kelajakdagi katta o'zgarishlar 10:10 dagi 15m MTF kontekstiga ta'sir qilmaydi."""
    idx_5m = pd.date_range("2026-01-05 08:30", periods=25, freq="5min", tz="America/New_York")
    closes_5m = [100.0] * 19 + [99.0, 100.8] + [101.0] * 4
    df_5m = pd.DataFrame(
        {"open": closes_5m, "high": [c + 0.5 for c in closes_5m], "low": [c - 0.5 for c in closes_5m], "close": closes_5m, "volume": [1000.0]*25},
        index=idx_5m,
    )

    # 15m barlar: 07:00 dan 12:00 gacha
    idx_15m = pd.date_range("2026-01-05 07:00", periods=20, freq="15min", tz="America/New_York")
    closes_15m_a = [100.0] * 20
    # 15m B da kelajakda (10:15 dan keyin) dahshatli qulash
    closes_15m_b = [100.0] * 13 + [50.0 - i * 5 for i in range(7)]  # 13-bar is 10:15 (closes 10:30)

    df_15m_a = pd.DataFrame({"open": closes_15m_a, "high": [c+1 for c in closes_15m_a], "low": [c-1 for c in closes_15m_a], "close": closes_15m_a, "volume": [1000.0]*20}, index=idx_15m)
    df_15m_b = pd.DataFrame({"open": closes_15m_b, "high": [c+1 for c in closes_15m_b], "low": [c-1 for c in closes_15m_b], "close": closes_15m_b, "volume": [1000.0]*20}, index=idx_15m)

    as_of_t = pd.Timestamp("2026-01-05 10:10", tz="America/New_York")

    setup_a = scan_day("AAPL", provider=AdversarialMockProvider(df_5m=df_5m, df_15m=df_15m_a), as_of=as_of_t)
    setup_b = scan_day("AAPL", provider=AdversarialMockProvider(df_5m=df_5m, df_15m=df_15m_b), as_of=as_of_t)

    assert setup_a.structure_15m == setup_b.structure_15m
    assert setup_a.status == setup_b.status


def test_adversarial_e_future_hod() -> None:
    """Test E: 10:10 dan keyin narx 999.0 gacha chiqsa ham, 10:10 dagi HOD o'zgarmasligi kerak."""
    idx = pd.date_range("2026-01-05 09:30", periods=20, freq="5min", tz="America/New_York")
    df_norm = pd.DataFrame(
        {"open": [100.0]*20, "high": [101.0]*20, "low": [99.0]*20, "close": [100.0]*20, "volume": [1000.0]*20},
        index=idx,
    )
    df_spike = pd.DataFrame(
        {"open": [100.0]*20, "high": [101.0]*15 + [999.0]*5, "low": [99.0]*20, "close": [100.0]*20, "volume": [1000.0]*20},
        index=idx,
    )

    levels_norm = compute_intraday_levels(df_norm)
    levels_spike = compute_intraday_levels(df_spike)

    # 10:10 da (bar index 8: 09:30..10:10) HOD ikkalasida ham 101.0 bo'lishi shart
    t_1010 = pd.Timestamp("2026-01-05 10:10", tz="America/New_York")
    assert levels_norm.loc[t_1010, "hod"] == 101.0
    assert levels_spike.loc[t_1010, "hod"] == 101.0
