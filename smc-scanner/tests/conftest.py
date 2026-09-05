"""Global pytest fixture'lar.

signals/dedup.py fayl-asosli persistence ishlatadi (TZ 18) — testlar orasida
signal_id'lar to'qnashib bir-biriga aralashmasin va repo ichiga real fayl
yozilmasin uchun, har test funksiyasida default dedup fayli avtomatik
tmp_path'ga almashtiriladi (DedupStore(path=None) shu default'ni ishlatadi).
"""

from __future__ import annotations

import pytest

from signals import dedup as dedup_module


@pytest.fixture(autouse=True)
def _isolated_dedup_store_path(tmp_path, monkeypatch):
    monkeypatch.setattr(dedup_module, "DEFAULT_DEDUP_PATH", tmp_path / "signal_dedup.json")
