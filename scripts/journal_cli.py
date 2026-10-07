"""Savdo jurnali CLI: haqiqiy (paper/live) savdolarni qo'lda qo'shish, yopish, ko'rish, tahlil qilish.

Ishlatish:
    python scripts/journal_cli.py add --symbol AAPL --entry-date 2026-08-26 --entry 230.5 \\
        --stop 220.0 --target 250.0 --exit-mode fixed --reason FVG --notes "..."
    python scripts/journal_cli.py close --id 3 --exit-date 2026-08-30 --exit-price 245.0
    python scripts/journal_cli.py list
    python scripts/journal_cli.py stats

--journal-path bilan CSV joyini o'zgartirish mumkin (default: trade_journal.csv, loyiha ildizida).

stats: raqamlarni ko'rsatadi, sharh/xulosa CHIQARMAYDI — masalan rejalashtirilgan
R:R (avg_rr_planned) yuqori-yu, expectancy_r past/manfiy bo'lishi mumkin; buni
ko'rish va xulosa qilish FOYDALANUVCHI ishi.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd

# Skript qayerdan ishga tushirilishidan qat'iy nazar paketlar topilishi uchun
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from journal.trade_journal import DEFAULT_JOURNAL_PATH, TradeJournal  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Savdo jurnali CLI")
    parser.add_argument("--journal-path", default=DEFAULT_JOURNAL_PATH)
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="Yangi savdo yozuvini qo'shadi")
    add_parser.add_argument("--symbol", required=True)
    add_parser.add_argument("--entry-date", required=True, help="YYYY-MM-DD")
    add_parser.add_argument("--entry", type=float, required=True, dest="entry_price")
    add_parser.add_argument("--stop", type=float, required=True, dest="stop_price")
    add_parser.add_argument("--target", type=float, default=None, dest="target_price")
    add_parser.add_argument("--exit-mode", default="fixed", choices=["fixed", "trailing"])
    add_parser.add_argument("--reason", default="")
    add_parser.add_argument("--notes", default="")

    close_parser = subparsers.add_parser("close", help="Mavjud yozuvni yopadi")
    close_parser.add_argument("--id", type=int, required=True, dest="entry_id")
    close_parser.add_argument("--exit-date", required=True, help="YYYY-MM-DD")
    close_parser.add_argument("--exit-price", type=float, required=True)
    close_parser.add_argument("--notes", default=None)

    subparsers.add_parser("list", help="Barcha yozuvlarni jadval qilib chiqaradi")
    subparsers.add_parser("stats", help="R:R (rejalashtirilgan) vs expectancy (amalga oshgan) tahlili")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    journal = TradeJournal(csv_path=args.journal_path)

    if args.command == "add":
        entry = journal.add_entry(
            symbol=args.symbol.upper(),
            entry_date=date.fromisoformat(args.entry_date),
            entry_price=args.entry_price,
            stop_price=args.stop_price,
            target_price=args.target_price,
            exit_mode=args.exit_mode,
            reason=args.reason,
            notes=args.notes,
        )
        print(f"Qo'shildi: entry_id={entry.entry_id}, {entry.symbol}, rr_planned={entry.rr_planned}")

    elif args.command == "close":
        entry = journal.close_entry(
            entry_id=args.entry_id,
            exit_date=date.fromisoformat(args.exit_date),
            exit_price=args.exit_price,
            notes=args.notes,
        )
        print(f"Yopildi: entry_id={entry.entry_id}, r_multiple={entry.r_multiple}")

    elif args.command == "list":
        if not journal.entries:
            print("Jurnal bo'sh.")
        else:
            df = pd.DataFrame([e.__dict__ for e in journal.entries])
            print(df.to_string(index=False))

    elif args.command == "stats":
        stats = journal.stats()
        print(pd.Series(stats).to_string())


if __name__ == "__main__":
    main()
