"""experiments/*.json ichidagi saqlangan Exit Research natijalarini jadval qilib chiqaradi.

Ishlatish:
    python scripts/list_experiments.py [--model structure_break] [--verdict ALPHA]
        [--sort-by sharpe]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.exit_research import EXPERIMENTS_DIR  # noqa: E402

_TABLE_COLS = ["ID", "Exit", "OOS_Return", "OOS_Sharpe", "DD", "Trades", "Verdict"]
_SORT_KEYS = {
    "sharpe": "OOS_Sharpe", "return": "OOS_Return", "dd": "DD", "trades": "Trades",
    "date": "ID",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Saqlangan Exit Research experimentlarini ro'yxatlaydi")
    parser.add_argument("--model", default=None, help="exit_model bo'yicha filtr (masalan structure_break)")
    parser.add_argument("--verdict", default=None, help="verdict matnida shu substring bo'lsa (masalan ALPHA)")
    parser.add_argument("--sort-by", default=None, choices=sorted(_SORT_KEYS))
    parser.add_argument(
        "--experiments-dir", default=None, help="Default: repo ildizidagi experiments/"
    )
    return parser.parse_args()


def load_experiments(experiments_dir: Path) -> list[dict]:
    """experiments/*.json hammasini o'qiydi. Buzilgan/o'qib bo'lmaydigan fayl -> skip + ogohlantirish."""
    if not experiments_dir.exists():
        return []
    out: list[dict] = []
    for path in sorted(experiments_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["_id"] = path.stem
            out.append(payload)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"OGOHLANTIRISH: {path.name} o'qilmadi ({exc}) -- o'tkazib yuborildi", file=sys.stderr)
    return out


def build_table(experiments: list[dict]) -> pd.DataFrame:
    """Ustunlar: ID, Exit, OOS_Return, OOS_Sharpe, DD, Trades, Verdict."""
    rows = []
    for exp in experiments:
        oos = exp.get("oos_metrics") or {}
        rows.append({
            "ID": exp.get("_id", "?"),
            "Exit": exp.get("exit_model", "?"),
            "OOS_Return": oos.get("total_return_pct"),
            "OOS_Sharpe": oos.get("sharpe"),
            "DD": oos.get("max_dd_pct"),
            "Trades": oos.get("trade_count"),
            "Verdict": exp.get("verdict", "?"),
        })
    return pd.DataFrame(rows, columns=_TABLE_COLS)


def filter_table(
    df: pd.DataFrame, *, model: str | None, verdict: str | None, sort_by: str | None
) -> pd.DataFrame:
    if model:
        df = df[df["Exit"] == model]
    if verdict:
        df = df[df["Verdict"].astype(str).str.contains(verdict, case=False, na=False)]
    if sort_by:
        col = _SORT_KEYS[sort_by]
        df = df.sort_values(col, ascending=(sort_by == "date"))
    return df


def main() -> None:
    args = parse_args()
    experiments_dir = Path(args.experiments_dir) if args.experiments_dir else EXPERIMENTS_DIR
    experiments = load_experiments(experiments_dir)

    if not experiments:
        print(f"Hech qanday experiment topilmadi: {experiments_dir}")
        return

    table = build_table(experiments)
    table = filter_table(table, model=args.model, verdict=args.verdict, sort_by=args.sort_by)
    print(table.to_string(index=False))


if __name__ == "__main__":
    main()
