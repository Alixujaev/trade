"""tests/test_vwap_momentum.py: DAY-01 — VWAP Momentum strategiyasi uchun deterministik testlar."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from indicators.vwap import compute_vwap
from strategy.day.types import DaySetupStatus, VwapRelation
from strategy.day.vwap_momentum import evaluate_vwap_momentum


def _create_5m_bars(
    start_str: str,
    n_bars: int,
    base_price: float = 100.0,
    price_deltas: list[float] | None = None,
    volumes: list[float] | None = None,
) -> pd.DataFrame:
    """Belgilangan boshlanish vaqti bilan 5m barlar DataFrame'ini yaratadi."""
    idx = pd.date_range(start_str, periods=n_bars, freq="5min", tz="America/New_York")
    closes = []
    curr = base_price
    for i in range(n_bars):
        delta = price_deltas[i] if price_deltas and i < len(price_deltas) else 0.0
        curr += delta
        closes.append(curr)

    vols = volumes if volumes else [1000.0] * n_bars
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    opens = [c - 0.1 for c in closes]

    return pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": vols,
        },
        index=idx,
    )


def test_bullish_vwap_reclaim() -> None:
    """Oldingi bar VWAP ostida, joriy bar VWAP ustida yopilganda VWAP_RECLAIM aniqlanadi."""
    # 20 ta bar: dastlabki 18 bar narx ~ 100 da, VWAP ~ 100
    n = 20
    # Bar 18 (index 17): narx 99.0 ga tushadi (VWAP ostida)
    # Bar 19 (index 18): narx 99.2 da (hali ham VWAP ostida)
    # Bar 20 (index 19): narx 100.8 ga chiqadi (VWAP ustiga o'tadi)
    deltas = [0.0] * 17 + [-1.0, 0.2, 1.6]
    df_5m = _create_5m_bars("2026-01-05 09:30", n, base_price=100.0, price_deltas=deltas)

    setup = evaluate_vwap_momentum("AAPL", df_5m)

    assert setup.symbol == "AAPL"
    assert setup.vwap_relation is VwapRelation.VWAP_RECLAIM
    assert setup.setup_type == "VWAP_RECLAIM"
    assert setup.status in (DaySetupStatus.DETECTED, DaySetupStatus.CONFIRMED)
    assert any("VWAP reclaim" in e for e in setup.evidence)


def test_no_reclaim_when_already_above_vwap() -> None:
    """Narx oldingi barda ham VWAP ustida bo'lib, ancha yuqoriga ketgan bo'lsa, reclaim emas (ABOVE_VWAP/NO_SETUP)."""
    n = 20
    # Narx 100 dan boshlab doimiy o'sib, 105 ga chiqdi (VWAP ~ 102)
    deltas = [0.25] * n
    df_5m = _create_5m_bars("2026-01-05 09:30", n, base_price=100.0, price_deltas=deltas)

    setup = evaluate_vwap_momentum("AAPL", df_5m)

    assert setup.vwap_relation is not VwapRelation.VWAP_RECLAIM
    assert setup.vwap_relation is VwapRelation.ABOVE_VWAP
    assert setup.status is DaySetupStatus.NO_SETUP
    assert any("not a fresh reclaim" in w for w in setup.warnings)


def test_vwap_below_price() -> None:
    """Narx VWAP ostida bo'lsa, setup hosil bo'lmaydi (BELOW_VWAP / NO_SETUP)."""
    n = 20
    # Dastlabki barlar yuqorida, keyin keskin tushib ketgan
    deltas = [0.0] * 10 + [-1.0] * 10
    df_5m = _create_5m_bars("2026-01-05 09:30", n, base_price=100.0, price_deltas=deltas)

    setup = evaluate_vwap_momentum("AAPL", df_5m)

    assert setup.vwap_relation is VwapRelation.BELOW_VWAP
    assert setup.status is DaySetupStatus.NO_SETUP


def test_vwap_session_reset() -> None:
    """Kun almashganda 09:30 ET da VWAP to'liq nollanadi."""
    # 1-kun: narx 500
    df_day1 = _create_5m_bars("2026-01-05 09:30", 10, base_price=500.0)
    # 2-kun: narx 100
    df_day2 = _create_5m_bars("2026-01-06 09:30", 10, base_price=100.0)
    df_combined = pd.concat([df_day1, df_day2])

    vwap = compute_vwap(df_combined, rth_only=True)

    # 2-kun birinchi bari VWAP'i 500 emas, ~100 bo'lishi shart
    day2_first_vwap = float(vwap.loc[df_day2.index[0]])
    assert day2_first_vwap == pytest.approx(100.0, abs=1.0)


def test_rvol_confirmation() -> None:
    """RVOL >= 2.0 bo'lganda volume confirmation dalili beriladi."""
    # 21 kunlik data: dastlabki 20 kun oddiy hajm 1000, 21-kun hajm 3000 (RVOL ~ 3.0)
    days = pd.date_range("2026-01-01", periods=25, freq="B")  # business days
    dfs = []
    for d in days[:21]:
        d_str = d.strftime("%Y-%m-%d")
        vols = [1000.0] * 18
        if d == days[20]:  # oxirgi kun
            vols = [1000.0] * 15 + [1000.0, 1000.0, 3000.0]  # oxirgi barda 3x hajm
        deltas = [0.0] * 16 + [-1.0, 1.5]  # reclaim
        df_d = _create_5m_bars(f"{d_str} 09:30", 18, base_price=100.0, price_deltas=deltas, volumes=vols)
        dfs.append(df_d)

    df_all = pd.concat(dfs)
    setup = evaluate_vwap_momentum("AAPL", df_all)

    assert setup.rvol >= 2.0
    assert any("RVOL elevated" in e for e in setup.evidence)


def test_rvol_not_confirmed() -> None:
    """RVOL < 2.0 bo'lsa setup invalid bo'lmaydi, shunchaki volume tasdiqlanmagan ogohlantirish beriladi."""
    # Bir kunlik data (RVOL hisoblash uchun oldingi kunlar yo'q yoki past hajm)
    n = 20
    deltas = [0.0] * 17 + [-1.0, 0.2, 1.6]
    df_5m = _create_5m_bars("2026-01-05 09:30", n, base_price=100.0, price_deltas=deltas, volumes=[100.0]*n)

    setup = evaluate_vwap_momentum("AAPL", df_5m)

    # Setup DETECTED bo'lishi mumkin (avtomatik ravishda bekor qilinmaydi)
    assert setup.status is DaySetupStatus.DETECTED
    assert any("Volume not confirmed" in w or "RVOL baseline not available" in w for w in setup.warnings)


def test_only_closed_15m_candle_is_used() -> None:
    """10:25 ET dagi 5m bar uchun 10:15-10:30 oralig'idagi 15m candle hali yopilmagan, faqat 10:00-10:15 ishlatiladi."""
    # 5m barlar: 09:30 dan 10:20 gacha (oxirgi bar 10:20 da ochilib, 10:25 da yopiladi)
    df_5m = _create_5m_bars("2026-01-05 09:30", 11)  # 11 ta 5m bar = 09:30..10:20

    # 15m barlar: 09:30, 09:45, 10:00, 10:15 (10:15 bar 10:30 da yopiladi!)
    idx_15m = pd.date_range("2026-01-05 09:30", periods=4, freq="15min", tz="America/New_York")
    df_15m = pd.DataFrame(
        {
            "open": [100.0] * 4,
            "high": [101.0] * 4,
            "low": [99.0] * 4,
            "close": [100.0] * 4,
            "volume": [3000.0] * 4,
        },
        index=idx_15m,
    )

    # 5m oxirgi bar 10:20 (end = 10:25). filter_closed_bars tekshiruvi:
    from data.bars import filter_closed_bars
    closed_15m = filter_closed_bars(df_15m, "15m", as_of=pd.Timestamp("2026-01-05 10:25", tz="America/New_York"))

    # 10:15 dagi 15m bar 10:30 da yopiladi, demak 10:25 da u yopilmagan!
    # Faqat 09:30, 09:45, 10:00 (end: 10:15) yopilgan.
    assert len(closed_15m) == 3
    assert pd.Timestamp("2026-01-05 10:15", tz="America/New_York") not in closed_15m.index


def test_no_lookahead() -> None:
    """Kelajak barlari as_of vaqtidagi signalga mutlaqo ta'sir qilmaydi."""
    df_base = _create_5m_bars("2026-01-05 09:30", 20, base_price=100.0)
    as_of_ts = df_base.index[-1] + pd.Timedelta(minutes=5)

    setup_base = evaluate_vwap_momentum("AAPL", df_base, as_of=as_of_ts)

    # Kelajakka yana 10 ta bar qo'shamiz
    df_future = _create_5m_bars("2026-01-05 09:30", 30, base_price=100.0)
    # Lekin as_of_ts gacha filtrlangan
    from data.bars import filter_closed_bars
    df_filtered = filter_closed_bars(df_future, "5m", as_of=as_of_ts)

    setup_filtered = evaluate_vwap_momentum("AAPL", df_filtered, as_of=as_of_ts)

    assert setup_base.status == setup_filtered.status
    assert setup_base.price == setup_filtered.price
    assert setup_base.vwap == pytest.approx(setup_filtered.vwap)
    assert setup_base.evidence_score == setup_filtered.evidence_score


def test_bullish_choch_trigger() -> None:
    """Oldingi LH ustidan buzib o'tganda bullish CHoCH triggeri ishlaydi."""
    # Downtrend then break above previous swing high
    prices = [95.0, 100.0, 105.0, 103.0, 98.0, 92.0, 90.0, 92.0, 95.0, 98.0, 97.0, 93.0, 87.0, 85.0, 87.0, 92.0, 99.0, 102.0]
    idx = pd.date_range("2026-01-05 09:30", periods=len(prices), freq="5min", tz="America/New_York")
    df_5m = pd.DataFrame(
        {
            "open": prices,
            "high": [p + 0.5 for p in prices],
            "low": [p - 0.5 for p in prices],
            "close": prices,
            "volume": [1000.0] * len(prices),
        },
        index=idx,
    )
    setup = evaluate_vwap_momentum("AAPL", df_5m)
    assert setup.trigger == "bullish CHoCH"
    assert any("5m bullish trigger: bullish CHoCH" in e for e in setup.evidence)


def test_previous_high_break_trigger() -> None:
    """Oldingi candle high qiymatini buzib yopilganda previous candle high break triggeri ishlaydi."""
    n = 20
    # Bar 18 high = 100.5, Bar 19 close = 101.2 > 100.5
    deltas = [0.0] * 17 + [-0.5, 0.0, 1.5]
    df_5m = _create_5m_bars("2026-01-05 09:30", n, base_price=100.0, price_deltas=deltas)

    setup = evaluate_vwap_momentum("AAPL", df_5m)

    assert setup.trigger == "previous candle high break"
    assert any("5m bullish trigger: previous candle high break" in e for e in setup.evidence)


def test_15m_bearish_conflict() -> None:
    """15m MTF tuzilmasi BEARISH bo'lsa, 5m reclaim paydo bo'lganda ham status CONFLICT bo'ladi."""
    n = 20
    deltas = [0.0] * 17 + [-1.0, 0.2, 1.6]  # 5m reclaim
    df_5m = _create_5m_bars("2026-01-05 09:30", n, base_price=100.0, price_deltas=deltas)

    # 15m da pastga yo'naltirilgan aniq LL/LH trend (BEARISH)
    prices_15m = [100, 105, 110, 108, 102, 95, 90, 94, 98, 96, 92, 85, 82, 86, 80, 75, 70, 75, 68, 65]
    idx_15m = pd.date_range("2026-01-05 06:00", periods=len(prices_15m), freq="15min", tz="America/New_York")
    df_15m = pd.DataFrame(
        {
            "open": prices_15m,
            "high": [p + 1.0 for p in prices_15m],
            "low": [p - 1.0 for p in prices_15m],
            "close": prices_15m,
            "volume": [2000.0] * len(prices_15m),
        },
        index=idx_15m,
    )

    setup = evaluate_vwap_momentum("AAPL", df_5m, df_15m=df_15m)

    # 15m bearish kontekst bo'lgani sababli status CONFLICT bo'lishi kerak!
    assert setup.status is DaySetupStatus.CONFLICT
    assert any("15m structure is BEARISH" in w for w in setup.warnings)
