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
    """Bir xil setup (symbol+setup_type+entry_ts+mode) qayta skan qilinganda AYNAN
    bir xil ID chiqishi kerak."""
    id_1 = compute_signal_id(symbol="AMD", setup_type="FVG", entry_ts="2026-08-20", mode="trailing")
    id_2 = compute_signal_id(symbol="AMD", setup_type="FVG", entry_ts="2026-08-20", mode="trailing")
    assert id_1 == id_2


def test_signal_id_for_row_idempotent_across_rescans() -> None:
    """Ikkita mustaqil build_scan_row-uslubidagi qator (bir xil setup, alohida
    dict instansiyalari) bir xil signal_id berishi kerak."""
    row_a = _row()
    row_b = _row()  # yangi dict, lekin bir xil qiymatlar — qayta skan simulyatsiyasi

    assert signal_id_for_row(row_a, mode="trailing") == signal_id_for_row(row_b, mode="trailing")


def test_signal_id_differs_by_symbol() -> None:
    id_amd = compute_signal_id(symbol="AMD", setup_type="FVG", entry_ts="2026-08-20", mode="trailing")
    id_aapl = compute_signal_id(symbol="AAPL", setup_type="FVG", entry_ts="2026-08-20", mode="trailing")
    assert id_amd != id_aapl


def test_signal_id_same_despite_different_entry_price() -> None:
    """TZ: entry_price ID kalitiga ATAYLAB kirmaydi — bir symbol/bir kun/bir setup
    turi uchun bir nechta nomzod (turli narxli candidate zonalar) bo'lsa ham, hammasi
    BITTA signal_id oladi (qaysi nomzod ko'rsatilishi — eng yuqori score'lisi —
    telegram_bot/handlers.py::_dedup_filter_new_payloads'da hal qilinadi)."""
    id_1 = compute_signal_id(symbol="AMD", setup_type="FVG", entry_ts="2026-08-20", mode="trailing")
    id_2 = compute_signal_id(symbol="AMD", setup_type="FVG", entry_ts="2026-08-20", mode="trailing")
    assert id_1 == id_2


def test_signal_id_differs_by_mode() -> None:
    """Bir xil setup, lekin fixed vs trailing — chiqish/target boshqacha bo'lishi
    mumkin, shuning uchun alohida ID (aks holda cooldown ikki rejimni aralashtirib
    yuboradi)."""
    id_fixed = compute_signal_id(symbol="AMD", setup_type="FVG", entry_ts="2026-08-20", mode="fixed")
    id_trailing = compute_signal_id(symbol="AMD", setup_type="FVG", entry_ts="2026-08-20", mode="trailing")
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


def test_signal_id_for_payload_matches_compute_signal_id() -> None:
    """signal_id_for_payload compute_signal_id'ni to'g'ridan-to'g'ri qayta ishlatadi --
    entry_zone/entry_price ID'ga umuman KIRMAYDI."""
    payload = _payload()

    expected = compute_signal_id(
        symbol="AMD", setup_type="fvg", entry_ts="2026-08-20", mode="SWING",
    )
    assert signal_id_for_payload(payload) == expected


def test_signal_id_for_payload_same_despite_different_entry_zone() -> None:
    """TZ (bug fix): bitta symbolning bir kunidagi bir setup turi uchun bir nechta
    nomzod (masalan ikki candidate zona, turli narx) bo'lsa ham -- BITTA signal_id.
    Aks holda dedup ikkalasini ham "yangi" deb o'tkazadi (haqiqiy production bug edi:
    $183-187 va $189-193 ikki xil ID olib, AAPL ikki marta chiqqan edi)."""
    id_1 = signal_id_for_payload(_payload(entry_zone=(148.0, 152.0)))
    id_2 = signal_id_for_payload(_payload(entry_zone=(158.0, 162.0)))
    assert id_1 == id_2


def test_signal_id_for_payload_differs_by_symbol() -> None:
    id_amd = signal_id_for_payload(_payload(symbol="AMD"))
    id_aapl = signal_id_for_payload(_payload(symbol="AAPL"))
    assert id_amd != id_aapl


def test_signal_id_for_payload_differs_by_setup_type() -> None:
    id_fvg = signal_id_for_payload(_payload(setup_type="fvg"))
    id_breakout = signal_id_for_payload(_payload(setup_type="breakout_retest"))
    assert id_fvg != id_breakout


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


# ======================================================================
# /scan (signal_id_for_row) vs /signals (signal_id_for_payload) izchilligi
# ======================================================================


def test_signal_id_matches_between_row_and_payload_for_equivalent_setup() -> None:
    """Ikki mustaqil oqim (eski row-dict /scan va yangi SignalPayload /signals) BIR
    XIL compute_signal_id formulasiga tayanadi -- bir xil symbol/setup_type/sana/mode
    berilsa, ikkalasi ANIQ bir xil signal_id chiqarishi kerak (umumiy DedupStore
    ma'noli bo'lishi uchun shart)."""
    row = {
        "SYMBOL": "AAPL", "SETUP_REASON": "breakout_retest",
        "SETUP_ENTRY_DATE": "2026-01-05", "SETUP_ENTRY": 185.0,
    }
    payload = _payload(
        symbol="AAPL", setup_type="breakout_retest", entry_ts=date(2026, 1, 5),
        mode=SignalMode.SWING,
    )

    row_id = signal_id_for_row(row, mode="SWING")
    payload_id = signal_id_for_payload(payload)

    assert row_id is not None
    assert row_id == payload_id
