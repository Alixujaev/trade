"""config/capital_store.py uchun testlar (fayl tizimi tmp_path bilan izolyatsiya qilingan)."""

from __future__ import annotations

import pytest

from config.capital_store import get_capital, set_capital


def test_get_capital_returns_default_when_file_absent(tmp_path) -> None:
    path = tmp_path / "paper_capital.json"

    assert get_capital(path=path) == pytest.approx(10_000.0)
    assert not path.exists()  # default o'qish fayl yaratmasligi kerak


def test_set_then_get_round_trips(tmp_path) -> None:
    path = tmp_path / "paper_capital.json"

    set_capital(5_000.0, path=path)

    assert get_capital(path=path) == pytest.approx(5_000.0)


def test_set_capital_overwrites_previous_value(tmp_path) -> None:
    path = tmp_path / "paper_capital.json"

    set_capital(5_000.0, path=path)
    set_capital(7_500.0, path=path)

    assert get_capital(path=path) == pytest.approx(7_500.0)
