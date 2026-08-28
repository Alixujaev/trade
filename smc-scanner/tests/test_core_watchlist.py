"""config/core_watchlist.py uchun testlar (fayl tizimi tmp_path bilan izolyatsiya qilingan)."""

from __future__ import annotations

import json

import pytest

from config.core_watchlist import (
    CORE_WATCHLIST,
    PLACEHOLDER_HALAL_SOURCE,
    add_to_core_watchlist,
    get_core_watchlist,
    remove_from_core_watchlist,
)


def test_get_core_watchlist_returns_expected_entries(tmp_path) -> None:
    # tmp_path'dagi mavjud bo'lmagan fayl -> seed'ga tushadi; haqiqiy loyiha
    # faylidan (foydalanuvchi runtime'da o'zgartirgan bo'lishi mumkin) izolyatsiya.
    path = tmp_path / "core_watchlist.json"
    watchlist = get_core_watchlist(path=path)

    tickers = [h.ticker for h in watchlist]
    assert "SPUS" in tickers
    assert "HLAL" in tickers
    assert "AAPL" in tickers
    assert "AMD" in tickers
    assert "AVGO" in tickers
    assert "FSLR" in tickers

    by_ticker = {h.ticker: h for h in watchlist}
    assert by_ticker["SPUS"].category == "etf"
    assert by_ticker["HLAL"].category == "etf"
    assert by_ticker["AAPL"].category == "stock"


def test_seed_includes_full_hlal_holdings_for_deploy(tmp_path) -> None:
    """core_watchlist.json gitignore'da — Railway'da bo'lmaydi. Shuning uchun
    HLAL tarkibiy qismlari (config/tactical_watchlist.py, git'da) seed'ga
    kirishi SHART, aks holda deploy'da /watchlist yana 6 talik stub'ga tushadi."""
    from config.tactical_watchlist import HLAL_HOLDINGS

    path = tmp_path / "core_watchlist.json"
    seed_tickers = {h.ticker for h in get_core_watchlist(path=path)}

    assert len(HLAL_HOLDINGS) > 200
    missing = {t for t, _ in HLAL_HOLDINGS} - seed_tickers
    assert not missing, f"seed'da yo'q HLAL belgilari: {sorted(missing)[:10]}"
    assert len(seed_tickers) > 200


def test_seed_entries_have_no_fabricated_review_date(tmp_path) -> None:
    """Hech qanday seed yozuv soxta 'tekshirilgan' sanaga ega bo'lmasligi kerak —
    bu asbob halal statusni o'zi hisoblamaydi, shuning uchun 'tasdiqlangan' degan
    taassurot soxta sana bilan berilmasligi kerak."""
    path = tmp_path / "core_watchlist.json"
    for holding in get_core_watchlist(path=path):
        assert holding.last_reviewed is None


def test_get_core_watchlist_returns_independent_copy(tmp_path) -> None:
    path = tmp_path / "core_watchlist.json"
    first_call = get_core_watchlist(path=path)
    first_call.clear()

    second_call = get_core_watchlist(path=path)

    assert len(second_call) > 0


def test_get_core_watchlist_returns_seed_when_file_absent(tmp_path) -> None:
    path = tmp_path / "core_watchlist.json"

    watchlist = get_core_watchlist(path=path)

    assert not path.exists()  # default o'qish fayl yaratmasligi kerak
    assert any(h.ticker == "AAPL" for h in watchlist)


# Sintetik ticker: HLAL seed'ida (config/tactical_watchlist.py, 200+ real belgi)
# bo'lmagan nom kerak — aks holda "yangi qo'shish" testlari dedup'ga urilib qoladi.
_SYNTHETIC = "ZZTEST"
_SYNTHETIC_NAME = "Zztest Holdings Inc"


def test_add_to_core_watchlist_without_halal_source_uses_placeholder(tmp_path) -> None:
    path = tmp_path / "core_watchlist.json"

    holding = add_to_core_watchlist(_SYNTHETIC.lower(), _SYNTHETIC_NAME, "stock", path=path)

    assert holding.ticker == _SYNTHETIC
    assert holding.halal_source == PLACEHOLDER_HALAL_SOURCE
    assert holding.last_reviewed is None

    reloaded = get_core_watchlist(path=path)
    assert any(h.ticker == _SYNTHETIC for h in reloaded)


def test_add_to_core_watchlist_with_halal_source_sets_review_date(tmp_path) -> None:
    path = tmp_path / "core_watchlist.json"

    holding = add_to_core_watchlist(
        "ZZACME", "Zzacme Corp.", "stock", halal_source="Musaffa", path=path
    )

    assert holding.halal_source == "Musaffa"
    assert holding.last_reviewed is not None


def test_add_to_core_watchlist_persists_seed_plus_new_entry(tmp_path) -> None:
    path = tmp_path / "core_watchlist.json"

    add_to_core_watchlist(_SYNTHETIC, _SYNTHETIC_NAME, "stock", path=path)
    reloaded = get_core_watchlist(path=path)

    tickers = {h.ticker for h in reloaded}
    assert _SYNTHETIC in tickers
    assert "AAPL" in tickers  # seed entries carried over into the new file


def test_add_to_core_watchlist_rejects_duplicate_ticker(tmp_path) -> None:
    path = tmp_path / "core_watchlist.json"
    add_to_core_watchlist(_SYNTHETIC, _SYNTHETIC_NAME, "stock", path=path)

    with pytest.raises(ValueError):
        add_to_core_watchlist(_SYNTHETIC.lower(), "Zztest again", "stock", path=path)


def test_add_to_core_watchlist_rejects_invalid_category(tmp_path) -> None:
    path = tmp_path / "core_watchlist.json"

    with pytest.raises(ValueError):
        add_to_core_watchlist("TSLA", "Tesla, Inc.", "bond", path=path)


def test_remove_from_core_watchlist_removes_existing(tmp_path) -> None:
    path = tmp_path / "core_watchlist.json"
    add_to_core_watchlist(_SYNTHETIC, _SYNTHETIC_NAME, "stock", path=path)

    removed = remove_from_core_watchlist(_SYNTHETIC.lower(), path=path)

    assert removed is True
    assert not any(h.ticker == _SYNTHETIC for h in get_core_watchlist(path=path))


def test_remove_from_core_watchlist_missing_ticker_returns_false(tmp_path) -> None:
    path = tmp_path / "core_watchlist.json"

    removed = remove_from_core_watchlist("NOPE", path=path)

    assert removed is False
    assert not path.exists()  # hech narsa o'zgarmagani uchun fayl yaratilmaydi


# ---- overlay (delta) semantikasi + orqaga moslik --------------------------------


def _legacy_snapshot_rows(holdings) -> list[dict]:
    return [
        {
            "ticker": h.ticker, "name": h.name, "category": h.category,
            "halal_source": h.halal_source,
            "last_reviewed": h.last_reviewed.isoformat() if h.last_reviewed else None,
            "note": h.note,
        }
        for h in holdings
    ]


def test_legacy_full_snapshot_of_seed_does_not_shadow_seed(tmp_path) -> None:
    """Railway bug: eskirgan to'liq-snapshot core_watchlist.json (faqat 6 ta eski
    seed yozuvi) yangi 200+ talik kod seed'ini "yashirib" qo'yardi. Endi bunday
    fayl faqat qo'shimchalarni beradi — seed'dagi ticker'lar e'tiborsiz qoladi."""
    path = tmp_path / "core_watchlist.json"
    old_six = [h for h in CORE_WATCHLIST if h.ticker in {"SPUS", "HLAL", "AAPL", "AMD", "AVGO", "FSLR"}]
    path.write_text(json.dumps(_legacy_snapshot_rows(old_six), ensure_ascii=False))

    watchlist = get_core_watchlist(path=path)

    assert len(watchlist) == len(CORE_WATCHLIST) > 200
    assert {h.ticker for h in watchlist} == {h.ticker for h in CORE_WATCHLIST}


def test_legacy_snapshot_keeps_non_seed_entries_as_additions(tmp_path) -> None:
    path = tmp_path / "core_watchlist.json"
    rows = _legacy_snapshot_rows(CORE_WATCHLIST[:3]) + [
        {"ticker": "ZMANUAL", "name": "Z Manual Co", "category": "stock",
         "halal_source": "Musaffa", "last_reviewed": "2026-08-01", "note": "qo'lda"}
    ]
    path.write_text(json.dumps(rows, ensure_ascii=False))

    tickers = {h.ticker for h in get_core_watchlist(path=path)}

    assert "ZMANUAL" in tickers  # seed'da yo'q -> qo'shimcha sifatida saqlanadi
    assert {h.ticker for h in CORE_WATCHLIST} <= tickers  # seed to'liq turadi


def test_remove_of_seed_ticker_persists_as_overlay(tmp_path) -> None:
    path = tmp_path / "core_watchlist.json"
    seed_ticker = CORE_WATCHLIST[10].ticker

    assert remove_from_core_watchlist(seed_ticker, path=path) is True
    assert seed_ticker not in {h.ticker for h in get_core_watchlist(path=path)}

    overlay = json.loads(path.read_text())
    assert overlay["removed"] == [seed_ticker]
    # boshqa hamma narsa joyida
    assert len(get_core_watchlist(path=path)) == len(CORE_WATCHLIST) - 1


def test_readd_after_remove_restores_seed_ticker(tmp_path) -> None:
    path = tmp_path / "core_watchlist.json"
    seed_ticker = CORE_WATCHLIST[10].ticker

    remove_from_core_watchlist(seed_ticker, path=path)
    add_to_core_watchlist(seed_ticker, "Re-added Co", "stock", path=path)

    tickers = {h.ticker for h in get_core_watchlist(path=path)}
    assert seed_ticker in tickers
    overlay = json.loads(path.read_text())
    assert seed_ticker not in overlay["removed"]


def test_new_overlay_schema_round_trips(tmp_path) -> None:
    path = tmp_path / "core_watchlist.json"

    add_to_core_watchlist(_SYNTHETIC, _SYNTHETIC_NAME, "stock", path=path)
    overlay = json.loads(path.read_text())

    assert isinstance(overlay, dict)
    assert [r["ticker"] for r in overlay["added"]] == [_SYNTHETIC]
    assert overlay["removed"] == []
