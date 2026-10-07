"""signals/dedup.py uchun testlar — DedupStore is_new/mark_shown/cleanup (TZ 18)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from signals.dedup import DedupStore

_NOW = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)


def test_dedup_blocks_repeat(tmp_path) -> None:
    """Bir marta mark_shown qilingan signal darhol qayta so'ralganda is_new=False."""
    store = DedupStore(path=tmp_path / "dedup.json")
    store.mark_shown("sig-1", timestamp=_NOW)

    assert store.is_new("sig-1", cooldown_hours=24.0, now=_NOW) is False


def test_dedup_allows_unseen_signal(tmp_path) -> None:
    """Hech qachon ko'rilmagan signal_id har doim yangi."""
    store = DedupStore(path=tmp_path / "dedup.json")

    assert store.is_new("sig-never-seen", cooldown_hours=24.0, now=_NOW) is True


def test_cooldown_allows_after_expiry(tmp_path) -> None:
    """Cooldown muddati o'tgach xuddi shu signal qayta "yangi" deb hisoblanadi."""
    store = DedupStore(path=tmp_path / "dedup.json")
    store.mark_shown("sig-1", timestamp=_NOW)

    still_cooling = _NOW + timedelta(hours=23)
    assert store.is_new("sig-1", cooldown_hours=24.0, now=still_cooling) is False

    expired = _NOW + timedelta(hours=24, minutes=1)
    assert store.is_new("sig-1", cooldown_hours=24.0, now=expired) is True


def test_dedup_store_persists(tmp_path) -> None:
    """Fayl-asosli store qayta o'qishда (yangi DedupStore instansiyasi, bir xil
    fayl yo'li) saqlangan yozuvlarni yo'qotmasligi kerak."""
    path = tmp_path / "dedup.json"
    store_1 = DedupStore(path=path)
    store_1.mark_shown("sig-1", timestamp=_NOW)

    store_2 = DedupStore(path=path)  # xuddi shu faylni qaytadan o'qiydi

    assert store_2.is_new("sig-1", cooldown_hours=24.0, now=_NOW) is False


def test_dedup_cleanup_removes_stale_entries(tmp_path) -> None:
    """cleanup() older_than_hours'dan eski yozuvlarni o'chiradi, yangilarini
    saqlab qoladi — fayl cheksiz o'smasin."""
    store = DedupStore(path=tmp_path / "dedup.json")
    old_time = _NOW - timedelta(hours=100)
    store.mark_shown("stale-sig", timestamp=old_time)
    store.mark_shown("fresh-sig", timestamp=_NOW)

    removed = store.cleanup(older_than_hours=48.0, now=_NOW)

    assert removed == 1
    assert store.is_new("stale-sig", cooldown_hours=24.0, now=_NOW) is True  # o'chirilgan -> "yangi"
    assert store.is_new("fresh-sig", cooldown_hours=24.0, now=_NOW) is False  # hali bor


def test_dedup_cleanup_persists_after_reload(tmp_path) -> None:
    """cleanup fayldan ham o'chirishi kerak (faqat xotiradagi dict emas)."""
    path = tmp_path / "dedup.json"
    store_1 = DedupStore(path=path)
    store_1.mark_shown("stale-sig", timestamp=_NOW - timedelta(hours=100))
    store_1.cleanup(older_than_hours=48.0, now=_NOW)

    store_2 = DedupStore(path=path)
    assert store_2.is_new("stale-sig", cooldown_hours=24.0, now=_NOW) is True


def test_dedup_store_empty_file_treated_as_no_history(tmp_path) -> None:
    """Fayl mavjud emas (birinchi ishga tushirish) -> xato bermaydi, hamma narsa yangi."""
    store = DedupStore(path=tmp_path / "does_not_exist_yet.json")
    assert store.is_new("sig-x", cooldown_hours=24.0, now=_NOW) is True
