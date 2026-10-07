"""indicators/rvol.py uchun to'liq testlar to'plami.

Time-of-day Relative Volume (RVOL) bo'yicha no-lookahead,
savdo kunlari ketma-ketligi, dam olish kunlari va baseline hisoblari sinovi.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from indicators.rvol import compute_rvol


def _create_multi_day_intraday(
    dates: list[str],
    day_patterns: list[list[tuple[str, float]]],
) -> pd.DataFrame:
    """dates: ['2024-06-03', '2024-06-04', ...].

    day_patterns: har bir kun uchun [(time_utc, volume), ...].
    """
    rows = []
    for d, pattern in zip(dates, day_patterns):
        for time_str, vol in pattern:
            dt_str = f"{d} {time_str}"
            rows.append((dt_str, 100.0, 100.0, 100.0, 100.0, vol))

    timestamps, opens, highs, lows, closes, volumes = zip(*rows)
    idx = pd.to_datetime(timestamps).tz_localize("UTC")
    df = pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=idx,
    )
    return df


def test_rvol_hand_verified_example_from_course() -> None:
    """Prompt talabi:

    Agar oldingi 20 ta sessiyaning 09:35 dagi hajmi 100, 100, ... bo'lib,
    bugungi 09:35 hajmi 200 bo'lsa, RVOL = 2.0 bo'lishi kerak.
    """
    # 21 ta savdo kuni (har kuni 13:30 da [09:30 EDT] va 13:35 da [09:35 EDT] barlar)
    # 2024-06-03 dan boshlab 21 ta ish kuni (Monday-Friday)
    business_dates = pd.date_range("2024-06-03", periods=21, freq="B").strftime("%Y-%m-%d").tolist()

    # Dastlabki 20 kunda 09:30 da hajm 50, 09:35 da hajm 100
    patterns = []
    for i in range(20):
        patterns.append([("13:30:00", 50.0), ("13:35:00", 100.0)])

    # 21-kunda (Day 21) 09:30 da hajm 50, 09:35 da hajm 200
    patterns.append([("13:30:00", 50.0), ("13:35:00", 200.0)])

    df = _create_multi_day_intraday(business_dates, patterns)
    rvol = compute_rvol(df, lookback_sessions=20)

    assert rvol.name == "rvol"
    assert len(rvol) == 42  # 21 kun * 2 bar

    # Dastlabki 20 kunda (yetarli 20 ta o'tgan kun yo'qligi sababli) RVOL NaN bo'lishi kerak
    assert rvol.iloc[:40].isna().all()

    # 21-kunda:
    # 09:30 da: bugun 50 / o'rtacha 50 = 1.0
    # 09:35 da: bugun 200 / o'rtacha 100 = 2.0
    rvol_day21_0930 = rvol.iloc[40]
    rvol_day21_0935 = rvol.iloc[41]

    assert rvol_day21_0930 == pytest.approx(1.0)
    assert rvol_day21_0935 == pytest.approx(2.0)


def test_rvol_current_session_excluded_from_baseline() -> None:
    """Joriy sessiya o'z baseline'iga kirmasligi shart.

    Agar Day 1..5 hajmi 100 bo'lsa va Day 6 da hajm 10,000 bo'lsa,
    Day 6 ning baseline'i faqat Day 1..5 dagi 100 dan tuziladi (10,000 baseline'ni buzmaydi).
    """
    dates = pd.date_range("2024-06-03", periods=6, freq="B").strftime("%Y-%m-%d").tolist()
    patterns = [[("13:30:00", 100.0)] for _ in range(5)]
    patterns.append([("13:30:00", 10000.0)])  # Day 6

    df = _create_multi_day_intraday(dates, patterns)
    rvol = compute_rvol(df, lookback_sessions=5)

    # Day 6 da: bugungi hajm 10000, o'tgan 5 kunning o'rtachasi 100 -> RVOL = 100.0
    assert rvol.iloc[5] == pytest.approx(100.0)


def test_rvol_weekend_gaps_do_not_disrupt_sessions() -> None:
    """Juma va Dushanba oraliq bo'shliqlariga qaramay ketma-ket savdo kunlari sifatida hisoblanadi."""
    # 2024-06-07 (Juma), 2024-06-10 (Dushanba), 2024-06-11 (Seshanba)
    dates = ["2024-06-07", "2024-06-10", "2024-06-11"]
    patterns = [
        [("13:30:00", 100.0)],
        [("13:30:00", 100.0)],
        [("13:30:00", 150.0)],
    ]
    df = _create_multi_day_intraday(dates, patterns)
    rvol = compute_rvol(df, lookback_sessions=2, min_sessions=2)

    # Day 1 va Day 2 da yetarli 2 kunlik baseline yo'q -> NaN
    assert np.isnan(rvol.iloc[0])
    assert np.isnan(rvol.iloc[1])

    # Day 3 (Seshanba): oldingi 2 ta ish kuni (Juma va Dushanba) o'rtachasi = 100.0
    # Bugun 150.0 -> RVOL = 1.5
    assert rvol.iloc[2] == pytest.approx(1.5)


def test_rvol_missing_time_of_day_bar() -> None:
    """Agar o'tgan biror sessiyada ayni shu vaqtdagi bar bo'lmasa, mavjud barlar bilan to'g'ri hisoblanadi."""
    dates = ["2024-06-03", "2024-06-04", "2024-06-05"]
    patterns = [
        [("13:30:00", 100.0)],  # 13:35 bari yo'q
        [("13:30:00", 100.0), ("13:35:00", 200.0)],  # 13:35 bari bor
        [("13:30:00", 100.0), ("13:35:00", 300.0)],
    ]
    df = _create_multi_day_intraday(dates, patterns)

    # min_sessions=1 bilan
    rvol = compute_rvol(df, lookback_sessions=2, min_sessions=1)

    # Day 3 da 13:35 bari uchun faqat Day 2 dagi 13:35 bari (200.0) mavjud
    # 300 / 200 = 1.5
    # oxirgi bar Day 3 13:35
    assert rvol.iloc[-1] == pytest.approx(1.5)


def test_rvol_no_future_leakage() -> None:
    """Joriy kunning kelajak barlari joriy vaqtdagi RVOL ga ta'sir qilmaydi."""
    dates = ["2024-06-03", "2024-06-04"]
    patterns_short = [
        [("13:30:00", 100.0)],
        [("13:30:00", 150.0)],
    ]
    patterns_long = [
        [("13:30:00", 100.0)],
        [("13:30:00", 150.0), ("13:35:00", 999999.0)],  # kelajakda katta hajm keldi
    ]
    df_short = _create_multi_day_intraday(dates, patterns_short)
    df_long = _create_multi_day_intraday(dates, patterns_long)

    rvol_short = compute_rvol(df_short, lookback_sessions=1, min_sessions=1)
    rvol_long = compute_rvol(df_long, lookback_sessions=1, min_sessions=1)

    # Day 2 13:30 dagi RVOL ikkala holatda ham 1.5 bo'lishi shart
    assert rvol_short.iloc[1] == pytest.approx(1.5)
    assert rvol_long.iloc[1] == pytest.approx(1.5)
