"""signals/payload.py uchun testlar — barqaror (idempotent) signal_id (TZ 18)."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd

from signals.payload import (
    HistoricalContext,
    SignalContext,
    SignalMode,
    SignalPayload,
    compute_signal_id,
    signal_id_for_payload,
    signal_id_for_row,
)


def _row(**overrides) -> dict:
    row = {
        "SYMBOL": "AMD",
        "SETUP_REASON": "FVG",
        "SETUP_ENTRY_DATE": "2026-08-20",
        "SETUP_ENTRY": 150.0,
        "HAS_ACTIVE_SETUP": True,
    }
    row.update(overrides)
    return row


def test_signal_id_idempotent() -> None:
    """Bir xil setup (symbol+setup_type+entry_ts+entry_price+mode) qayta skan
    qilinganda AYNAN bir xil ID chiqishi kerak."""
    id_1 = compute_signal_id(
        symbol="AMD", setup_type="FVG", entry_ts="2026-08-20", entry_price=150.0, mode="trailing",
    )
    id_2 = compute_signal_id(
        symbol="AMD", setup_type="FVG", entry_ts="2026-08-20", entry_price=150.0, mode="trailing",
    )
    assert id_1 == id_2


def test_signal_id_for_row_idempotent_across_rescans() -> None:
    """Ikkita mustaqil build_scan_row-uslubidagi qator (bir xil setup, alohida
    dict instansiyalari) bir xil signal_id berishi kerak."""
    row_a = _row()
    row_b = _row()  # yangi dict, lekin bir xil qiymatlar — qayta skan simulyatsiyasi

    assert signal_id_for_row(row_a, mode="trailing") == signal_id_for_row(row_b, mode="trailing")


def test_signal_id_differs_by_symbol() -> None:
    id_amd = compute_signal_id(
        symbol="AMD", setup_type="FVG", entry_ts="2026-08-20", entry_price=150.0, mode="trailing",
    )
    id_aapl = compute_signal_id(
        symbol="AAPL", setup_type="FVG", entry_ts="2026-08-20", entry_price=150.0, mode="trailing",
    )
    assert id_amd != id_aapl


def test_signal_id_differs_by_entry_price() -> None:
    id_1 = compute_signal_id(
        symbol="AMD", setup_type="FVG", entry_ts="2026-08-20", entry_price=150.0, mode="trailing",
    )
    id_2 = compute_signal_id(
        symbol="AMD", setup_type="FVG", entry_ts="2026-08-20", entry_price=151.0, mode="trailing",
    )
    assert id_1 != id_2


def test_signal_id_differs_by_mode() -> None:
    """Bir xil setup, lekin fixed vs trailing — chiqish/target boshqacha bo'lishi
    mumkin, shuning uchun alohida ID (aks holda cooldown ikki rejimni aralashtirib
    yuboradi)."""
    id_fixed = compute_signal_id(
        symbol="AMD", setup_type="FVG", entry_ts="2026-08-20", entry_price=150.0, mode="fixed",
    )
    id_trailing = compute_signal_id(
        symbol="AMD", setup_type="FVG", entry_ts="2026-08-20", entry_price=150.0, mode="trailing",
    )
    assert id_fixed != id_trailing


def test_signal_id_for_row_none_when_no_active_setup() -> None:
    """Faol setup yo'q qator (SETUP_ENTRY_DATE/SETUP_ENTRY yo'q) -> None, dedup
    bunday qatorni o'tkazib yuboradi (filtrlamaydi)."""
    row = {"SYMBOL": "AAPL", "HAS_ACTIVE_SETUP": False, "ERROR": None}
    assert signal_id_for_row(row, mode="trailing") is None


# ======================================================================
# signal_id_for_payload — /signals (SignalPayload, non-directive oqim) uchun
# ======================================================================


def _payload(**overrides) -> SignalPayload:
    fields = dict(
        symbol="AMD", mode=SignalMode.SWING, setup_type="fvg", score=80.0,
        score_label="SETUP", direction=None, entry_zone=(148.0, 152.0),
        invalidation=140.0, potential_target=170.0, risk_reward=2.0,
        context=SignalContext(trend="BULLISH", structure="BOS", volume_confirmed=True),
        historical_context=HistoricalContext(expectancy_r=0.6, win_rate_pct=52.8, period_label="2020-2026"),
        generated_at=datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc), timeframe="1d",
        data_freshness=date(2026, 8, 20), entry_ts=date(2026, 8, 20),
    )
    fields.update(overrides)
    if fields["direction"] is None:
        from smc.types import StructureState
        fields["direction"] = StructureState.BULLISH
    return SignalPayload(**fields)


def test_signal_id_for_payload_idempotent_across_rescans() -> None:
    """Ikkita mustaqil SignalPayload (bir xil setup, alohida instansiyalar) bir xil
    signal_id berishi kerak — signal_id_for_row bilan bir xil idempotentlik."""
    payload_a = _payload()
    payload_b = _payload()  # yangi instans, bir xil qiymatlar — qayta skan simulyatsiyasi

    assert signal_id_for_payload(payload_a) == signal_id_for_payload(payload_b)


def test_signal_id_for_payload_matches_compute_signal_id_with_recovered_entry_price() -> None:
    """entry_price entry_zone'dan (low+high)/2 sifatida tiklanadi -- _entry_zone
    (signals/scanner.py) doim entry_price atrofida simmetrik kengaytirgani uchun ANIQ."""
    payload = _payload(entry_zone=(148.0, 152.0))  # (low+high)/2 = 150.0

    expected = compute_signal_id(
        symbol="AMD", setup_type="fvg", entry_ts="2026-08-20", entry_price=150.0, mode="SWING",
    )
    assert signal_id_for_payload(payload) == expected


def test_signal_id_for_payload_degenerate_entry_zone_recovers_exact_price() -> None:
    """ATR yo'q (warmup) holatida entry_zone=(entry_price, entry_price) -- (low+high)/2
    baribir ANIQ entry_price'ga teng."""
    payload = _payload(entry_zone=(150.0, 150.0))

    expected = compute_signal_id(
        symbol="AMD", setup_type="fvg", entry_ts="2026-08-20", entry_price=150.0, mode="SWING",
    )
    assert signal_id_for_payload(payload) == expected


def test_signal_id_for_payload_differs_by_symbol() -> None:
    id_amd = signal_id_for_payload(_payload(symbol="AMD"))
    id_aapl = signal_id_for_payload(_payload(symbol="AAPL"))
    assert id_amd != id_aapl


def test_signal_id_for_payload_differs_by_setup_type() -> None:
    id_fvg = signal_id_for_payload(_payload(setup_type="fvg"))
    id_breakout = signal_id_for_payload(_payload(setup_type="breakout_retest"))
    assert id_fvg != id_breakout


def test_signal_id_for_payload_differs_by_entry_price() -> None:
    id_1 = signal_id_for_payload(_payload(entry_zone=(148.0, 152.0)))  # entry=150.0
    id_2 = signal_id_for_payload(_payload(entry_zone=(158.0, 162.0)))  # entry=160.0
    assert id_1 != id_2


def test_signal_id_for_payload_differs_by_entry_ts() -> None:
    """Bir xil symbol/setup_type/narx, lekin BOSHQA entry bar (masalan yangi setup
    eski setup invalidatsiya bo'lgandan keyin) -- alohida ID."""
    id_1 = signal_id_for_payload(_payload(entry_ts=date(2026, 8, 20)))
    id_2 = signal_id_for_payload(_payload(entry_ts=date(2026, 9, 1)))
    assert id_1 != id_2


def test_signal_id_for_payload_none_when_entry_ts_missing() -> None:
    """entry_ts=None (masalan eski/test payload) -> None, dedup'siz o'tkaziladi
    (signal_id_for_row'ning None-fallback konvensiyasi bilan bir xil)."""
    payload = _payload(entry_ts=None)
    assert signal_id_for_payload(payload) is None


def test_signal_id_for_payload_populated_by_payload_from_setup() -> None:
    """payload_from_setup haqiqatan ham entry_ts'ni setup.entry_ts'dan to'ldiradi --
    signals/scanner.py hech narsa o'zgartirmasdan, dedup ishlashi uchun shart."""
    from signals.payload import payload_from_setup
    from smc.types import StructureState, TradeSetup

    setup = TradeSetup(
        entry_ts=pd.Timestamp("2026-08-20", tz="UTC"), entry_price=150.0, stop_price=140.0,
        target_price=170.0, direction=StructureState.BULLISH, entry_index_pos=10, reason="FVG",
        score=80.0,
    )
    payload = payload_from_setup(
        setup, symbol="AMD", trend="BULLISH", structure="BOS", volume_confirmed=True,
        historical_expectancy_r=0.6, historical_win_rate_pct=52.8, historical_period_label="2020-2026",
        data_freshness=date(2026, 8, 20),
    )

    assert payload.entry_ts == date(2026, 8, 20)
    assert signal_id_for_payload(payload) is not None
