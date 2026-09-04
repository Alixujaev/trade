"""scripts/list_experiments.py uchun testlar (tarmoqsiz, tmp_path'dagi sun'iy experiments/)."""

from __future__ import annotations

import json

from scripts.list_experiments import build_table, filter_table, load_experiments


def _write(tmp_path, exp_id: str, *, exit_model: str, sharpe: float, verdict: str, trade_count: int = 40) -> None:
    payload = {
        "exit_model": exit_model,
        "oos_metrics": {
            "total_return_pct": 10.0, "sharpe": sharpe, "max_dd_pct": -5.0, "trade_count": trade_count,
        },
        "verdict": verdict,
    }
    (tmp_path / f"{exp_id}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_list_experiments_reads_experiments_dir(tmp_path) -> None:
    _write(tmp_path, "20260101_000000_fixed_sl_tp_abc123", exit_model="fixed_sl_tp", sharpe=0.5, verdict="NO EDGE")
    _write(tmp_path, "20260102_000000_structure_break_def456", exit_model="structure_break", sharpe=1.2, verdict="ALPHA: exit value qo'shdi")

    experiments = load_experiments(tmp_path)
    assert len(experiments) == 2

    table = build_table(experiments)
    assert list(table.columns) == ["ID", "Exit", "OOS_Return", "OOS_Sharpe", "DD", "Trades", "Verdict"]
    assert len(table) == 2
    assert set(table["Exit"]) == {"fixed_sl_tp", "structure_break"}


def test_list_experiments_skips_corrupt_file(tmp_path, capsys) -> None:
    _write(tmp_path, "20260101_000000_fixed_sl_tp_abc123", exit_model="fixed_sl_tp", sharpe=0.5, verdict="NO EDGE")
    (tmp_path / "broken.json").write_text("{not valid json", encoding="utf-8")

    experiments = load_experiments(tmp_path)
    assert len(experiments) == 1
    err = capsys.readouterr().err
    assert "broken.json" in err


def test_list_experiments_empty_dir_returns_empty_list(tmp_path) -> None:
    assert load_experiments(tmp_path / "does_not_exist") == []


def test_list_experiments_filter_by_model_and_verdict(tmp_path) -> None:
    _write(tmp_path, "20260101_000000_fixed_sl_tp_abc123", exit_model="fixed_sl_tp", sharpe=0.5, verdict="NO EDGE")
    _write(tmp_path, "20260102_000000_structure_break_def456", exit_model="structure_break", sharpe=1.2, verdict="ALPHA: exit value qo'shdi")

    table = build_table(load_experiments(tmp_path))
    filtered = filter_table(table, model="structure_break", verdict=None, sort_by=None)
    assert len(filtered) == 1
    assert filtered.iloc[0]["Exit"] == "structure_break"

    filtered2 = filter_table(table, model=None, verdict="ALPHA", sort_by=None)
    assert len(filtered2) == 1
    assert filtered2.iloc[0]["Exit"] == "structure_break"


def test_list_experiments_sort_by_sharpe_descending() -> None:
    # sort_by="sharpe" -> eng yaxshi (yuqori) Sharpe birinchi (ixtiyoriy, MVP uchun majburiy emas).
    import pandas as pd

    df = pd.DataFrame(
        {"ID": ["a", "b"], "Exit": ["x", "y"], "OOS_Return": [1, 2], "OOS_Sharpe": [0.1, 0.9],
         "DD": [-1, -2], "Trades": [10, 20], "Verdict": ["NO EDGE", "NO EDGE"]}
    )
    out = filter_table(df, model=None, verdict=None, sort_by="sharpe")
    assert list(out["OOS_Sharpe"]) == [0.9, 0.1]
