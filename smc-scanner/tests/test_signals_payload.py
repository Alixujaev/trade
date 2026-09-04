"""signals/payload.py uchun testlar — barqaror (idempotent) signal_id (TZ 18)."""

from __future__ import annotations

from signals.payload import compute_signal_id, signal_id_for_row


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
