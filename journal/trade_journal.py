"""Haqiqiy (paper/live) savdo jurnali — CSV asosida saqlanadi, foydalanuvchi qo'lda boshqaradi.

MUHIM: bu backtest/engine.py'ning simulyatsiyasi EMAS — foydalanuvchi o'zi HAQIQATDA
(yoki paper) olgan savdolarni yozib boradi. stats() faqat RAQAMLARNI ko'rsatadi
(masalan "rejalashtirilgan R:R yuqori-yu, expectancy manfiy") — hech qanday
sharh/xulosa CHIQARMAYDI, foydalanuvchi o'zi ko'rib xulosa qiladi (Phase 7'dagi
"halal qarorni o'zi hisoblama" printsipi bilan bir oilada: bu yerda "strategiya
yaxshi/yomon" degan qarorni ham kod o'zi chiqarmaydi).
"""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from datetime import date
from pathlib import Path

import pandas as pd

from data.provider import DataProvider
from journal.benchmark import outperformed_benchmark
from journal.benchmark_provider import benchmark_result_for_entry
from journal.types import JournalEntry

DEFAULT_JOURNAL_PATH: Path = Path(__file__).resolve().parent.parent / "trade_journal.csv"

_COLUMNS = [
    "entry_id", "symbol", "entry_date", "entry_price", "stop_price", "target_price",
    "reference_target_price", "exit_mode", "reason", "rr_planned", "notes", "exit_date",
    "exit_price", "r_multiple",
    # Setup snapshot (TZ) — barchasi eski CSV'larda YO'Q bo'lishi mumkin, _load
    # har birini "col" in df.columns bilan tekshiradi (reference_target_price
    # konvensiyasi bilan bir xil, backward-compat).
    "setup_type", "score", "score_label", "trend", "structure", "volume_confirmed",
    "entry_zone_low", "entry_zone_high", "invalidation", "target", "risk_reward",
    "target_source", "status", "score_reasons",
]


def _none_if_nan(value: object) -> float | None:
    """CSV'dan o'qilgan bo'sh katak (NaN) qiymatini None'ga aylantiradi."""
    if pd.isna(value):
        return None
    return float(value)


def _float_col(df: pd.DataFrame, row: pd.Series, col: str) -> float | None:
    """Ustun eski CSV'da umuman yo'q (backward-compat) yoki katak NaN -> None."""
    if col not in df.columns:
        return None
    return _none_if_nan(row[col])


def _str_col(df: pd.DataFrame, row: pd.Series, col: str) -> str | None:
    if col not in df.columns or pd.isna(row[col]):
        return None
    return str(row[col])


def _bool_col(df: pd.DataFrame, row: pd.Series, col: str) -> bool | None:
    """CSV yozgan "True"/"False" matnini (yoki pandas allaqachon bool'ga
    parslagan bo'lsa o'sha qiymatni) qayta bool'ga aylantiradi."""
    if col not in df.columns or pd.isna(row[col]):
        return None
    value = row[col]
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


def _score_reasons_col(df: pd.DataFrame, row: pd.Series, col: str = "score_reasons") -> tuple[str, ...]:
    """JSON-string sifatida saqlangan score_reasons'ni tuple'ga qaytaradi. Ustun
    yo'q/katak bo'sh -> () (bo'sh, direktiv EMAS default)."""
    if col not in df.columns or pd.isna(row[col]):
        return ()
    return tuple(json.loads(row[col]))


class TradeJournal:
    """Foydalanuvchi qo'lda boshqaradigan haqiqiy savdo yozuvlari ro'yxati — CSV'da saqlanadi."""

    def __init__(self, csv_path: Path | str = DEFAULT_JOURNAL_PATH) -> None:
        self.csv_path = Path(csv_path)
        self.entries: list[JournalEntry] = self._load()

    def add_entry(
        self,
        symbol: str,
        entry_date: date,
        entry_price: float,
        stop_price: float,
        target_price: float | None,
        exit_mode: str,
        reason: str,
        notes: str = "",
        reference_target_price: float | None = None,
        # Setup snapshot (TZ) — barchasi ixtiyoriy, default None/(). Qo'lda /add
        # oqimida (payload yo'q) berilmaydi, quickadd-from-signal oqimida
        # journal/snapshot.py::snapshot_kwargs_from_payload orqali to'ldiriladi.
        setup_type: str | None = None,
        score: float | None = None,
        score_label: str | None = None,
        trend: str | None = None,
        structure: str | None = None,
        volume_confirmed: bool | None = None,
        entry_zone_low: float | None = None,
        entry_zone_high: float | None = None,
        invalidation: float | None = None,
        target: float | None = None,
        risk_reward: float | None = None,
        target_source: str | None = None,
        status: str | None = None,
        score_reasons: tuple[str, ...] = (),
    ) -> JournalEntry:
        """Yangi savdo yozuvini qo'shadi va CSV'ga saqlaydi. rr_planned avtomatik hisoblanadi:
        avval target_price (mavjud, fixed-mode uchun), target_price=None bo'lsa
        reference_target_price (trailing uchun, faqat baholash maqsadida); ikkalasi ham
        None yoki risk<=0 bo'lsa rr_planned=None."""
        rr_target = target_price if target_price is not None else reference_target_price
        rr_planned = None
        if rr_target is not None:
            risk = entry_price - stop_price
            if risk > 0:
                rr_planned = (rr_target - entry_price) / risk

        next_id = max((e.entry_id for e in self.entries), default=0) + 1
        entry = JournalEntry(
            entry_id=next_id,
            symbol=symbol,
            entry_date=entry_date,
            entry_price=entry_price,
            stop_price=stop_price,
            target_price=target_price,
            reference_target_price=reference_target_price,
            exit_mode=exit_mode,
            reason=reason,
            rr_planned=rr_planned,
            notes=notes,
            setup_type=setup_type,
            score=score,
            score_label=score_label,
            trend=trend,
            structure=structure,
            volume_confirmed=volume_confirmed,
            entry_zone_low=entry_zone_low,
            entry_zone_high=entry_zone_high,
            invalidation=invalidation,
            target=target,
            risk_reward=risk_reward,
            target_source=target_source,
            status=status,
            score_reasons=tuple(score_reasons) if score_reasons else (),
        )
        self.entries.append(entry)
        self._save()
        return entry

    def close_entry(
        self, entry_id: int, exit_date: date, exit_price: float, notes: str | None = None,
    ) -> JournalEntry:
        """entry_id bo'yicha yozuvni yopadi (r_multiple hisoblanadi) va saqlaydi.

        Yozuv frozen dataclass bo'lgani uchun MUTATSIYA emas — dataclasses.replace
        bilan yangi (yopilgan) nusxa yaratilib, ro'yxatdagi eskisi bilan almashtiriladi
        (loyihaning boshqa barcha data modellari — SwingPoint, Zone, TradeSetup,
        TradeResult — ham frozen, shu konvensiyaga mos).
        """
        for i, entry in enumerate(self.entries):
            if entry.entry_id == entry_id:
                risk = entry.entry_price - entry.stop_price
                r_multiple = (exit_price - entry.entry_price) / risk if risk > 0 else None
                updated = replace(
                    entry,
                    exit_date=exit_date,
                    exit_price=exit_price,
                    r_multiple=r_multiple,
                    notes=notes if notes is not None else entry.notes,
                )
                self.entries[i] = updated
                self._save()
                return updated
        raise ValueError(f"entry_id={entry_id} topilmadi")

    def open_entries(self) -> list[JournalEntry]:
        """Hali yopilmagan (exit_price=None) yozuvlar."""
        return [e for e in self.entries if e.exit_price is None]

    def recent_entries(self, n: int = 10) -> list[JournalEntry]:
        """Oxirgi N yozuv, qo'shilgan tartibida (eskisi oldin)."""
        return self.entries[-n:]

    def stats(
        self, *, include_benchmark: bool = False, provider: DataProvider | None = None,
    ) -> dict:
        """Rejalashtirilgan R:R vs amalga oshgan expectancy — raqamlar, sharh emas.

        avg_rr_planned barcha (ochiq+yopiq) rr_planned NOT None yozuvlar bo'yicha —
        bu REJALASHTIRILGAN qiymat, natijani bilish shart emas. Qolgan hammasi
        FAQAT yopilgan yozuvlar bo'yicha (hali natija yo'q ochiq savdolar
        statistikaga kiritilmaydi).

        include_benchmark=True bo'lsa, natijaga "benchmark" kaliti qo'shiladi —
        discretionary metriklardan ALOHIDA blok (journal/benchmark.py::BenchmarkResult
        asosida, journal/benchmark_provider.py orqali HAQIQIY narx bilan hisoblangan;
        default False — provider chaqiruvi (tarmoq/IO) faqat aniq so'ralganda amalga
        oshadi, mavjud chaqiruvchilar o'zgarishsiz qoladi). Framing: "discretionary
        performance vs market benchmark" — "robotni baholash" EMAS; bu yerda ham
        (asosiy tamoyil bilan bir xil) hech qanday "yaxshi/yomon" xulosa CHIQARILMAYDI,
        faqat raqamlar.
        """
        closed = [e for e in self.entries if e.exit_price is not None]
        rr_values = [e.rr_planned for e in self.entries if e.rr_planned is not None]
        avg_rr_planned = sum(rr_values) / len(rr_values) if rr_values else None

        if not closed:
            result = {
                "num_entries": len(self.entries),
                "num_open": len(self.entries),
                "num_closed": 0,
                "avg_rr_planned": avg_rr_planned,
                "avg_r_realized": None,
                "win_rate": 0.0,
                "avg_win_r": None,
                "avg_loss_r": None,
                "expectancy_r": 0.0,
                "profit_factor": None,
            }
        else:
            r_values = [e.r_multiple for e in closed]
            wins = [r for r in r_values if r > 0]
            losses = [r for r in r_values if r <= 0]

            win_rate = len(wins) / len(closed)
            avg_win_r = sum(wins) / len(wins) if wins else None
            avg_loss_r = sum(losses) / len(losses) if losses else None

            # expectancy_r = win_rate*avg_win_r + loss_rate*avg_loss_r — backtest/metrics.py::
            # expectancy_r bilan BIR XIL dekompozitsiya formulasi, shu yerda JournalEntry ustida.
            win_component = win_rate * (avg_win_r or 0.0)
            loss_component = (len(losses) / len(closed)) * (avg_loss_r or 0.0)
            expectancy_r = win_component + loss_component

            # profit_factor = yutuqlar yig'indisi / mag'lubiyatlar yig'indisining moduli.
            # Mag'lubiyat bo'lmasa (bo'lish nolga) — None (cheksizlik emas, "hali ma'lumot yo'q").
            loss_sum = abs(sum(losses))
            profit_factor = sum(wins) / loss_sum if loss_sum > 0 else None

            result = {
                "num_entries": len(self.entries),
                "num_open": len(self.entries) - len(closed),
                "num_closed": len(closed),
                "avg_rr_planned": avg_rr_planned,
                "avg_r_realized": sum(r_values) / len(r_values),
                "win_rate": win_rate,
                "avg_win_r": avg_win_r,
                "avg_loss_r": avg_loss_r,
                "expectancy_r": expectancy_r,
                "profit_factor": profit_factor,
            }

        if include_benchmark:
            result["benchmark"] = self._benchmark_stats(closed, provider=provider)
        return result

    def _benchmark_stats(
        self, closed: list[JournalEntry], *, provider: DataProvider | None,
    ) -> dict:
        """`closed` yozuvlar uchun buy&hold benchmark blokini hisoblaydi (I/O —
        `benchmark_result_for_entry` orqali, har savdo o'z symbolining exit_date'dagi
        close narxini oladi). Provider xatosi/ma'lumot yo'qligi — o'sha ALOHIDA savdo
        SKIP qilinadi (None), butun blok yiqilmaydi.

        "outperform" — `journal.benchmark.outperformed_benchmark` orqali, FAQAT
        price-return birlikda (R-multiple EMAS) hisoblanadi; ta'rif shu funksiyaning
        docstringida (metodologik yurak)."""
        benchmarked: list[tuple[JournalEntry, object]] = []
        for entry in closed:
            benchmark = benchmark_result_for_entry(entry, provider=provider)
            if benchmark is not None:
                benchmarked.append((entry, benchmark))

        num_benchmarked = len(benchmarked)
        if num_benchmarked == 0:
            return {
                "num_benchmarked": 0,
                "num_benchmark_skipped": len(closed),
                "avg_benchmark_return_pct": None,
                "benchmark_positive_count": 0,
                "discretionary_outperformed_count": 0,
            }

        avg_benchmark_return = sum(b.benchmark_return for _, b in benchmarked) / num_benchmarked
        benchmark_positive_count = sum(1 for _, b in benchmarked if b.benchmark_return > 0)
        discretionary_outperformed_count = sum(
            1 for e, b in benchmarked if outperformed_benchmark(e.entry_price, e.exit_price, b)
        )

        return {
            "num_benchmarked": num_benchmarked,
            "num_benchmark_skipped": len(closed) - num_benchmarked,
            "avg_benchmark_return_pct": avg_benchmark_return * 100,
            "benchmark_positive_count": benchmark_positive_count,
            "discretionary_outperformed_count": discretionary_outperformed_count,
        }

    def _load(self) -> list[JournalEntry]:
        if not self.csv_path.exists() or self.csv_path.stat().st_size == 0:
            return []
        df = pd.read_csv(self.csv_path)
        if df.empty:
            return []

        entries: list[JournalEntry] = []
        for _, row in df.iterrows():
            entries.append(
                JournalEntry(
                    entry_id=int(row["entry_id"]),
                    symbol=str(row["symbol"]),
                    entry_date=date.fromisoformat(row["entry_date"]),
                    entry_price=float(row["entry_price"]),
                    stop_price=float(row["stop_price"]),
                    target_price=_none_if_nan(row["target_price"]),
                    reference_target_price=(
                        _none_if_nan(row["reference_target_price"])
                        if "reference_target_price" in df.columns
                        else None
                    ),
                    exit_mode=str(row["exit_mode"]),
                    reason="" if pd.isna(row["reason"]) else str(row["reason"]),
                    rr_planned=_none_if_nan(row["rr_planned"]),
                    notes="" if pd.isna(row["notes"]) else str(row["notes"]),
                    exit_date=None if pd.isna(row["exit_date"]) else date.fromisoformat(row["exit_date"]),
                    exit_price=_none_if_nan(row["exit_price"]),
                    r_multiple=_none_if_nan(row["r_multiple"]),
                    setup_type=_str_col(df, row, "setup_type"),
                    score=_float_col(df, row, "score"),
                    score_label=_str_col(df, row, "score_label"),
                    trend=_str_col(df, row, "trend"),
                    structure=_str_col(df, row, "structure"),
                    volume_confirmed=_bool_col(df, row, "volume_confirmed"),
                    entry_zone_low=_float_col(df, row, "entry_zone_low"),
                    entry_zone_high=_float_col(df, row, "entry_zone_high"),
                    invalidation=_float_col(df, row, "invalidation"),
                    target=_float_col(df, row, "target"),
                    risk_reward=_float_col(df, row, "risk_reward"),
                    target_source=_str_col(df, row, "target_source"),
                    status=_str_col(df, row, "status"),
                    score_reasons=_score_reasons_col(df, row),
                )
            )
        return entries

    def _save(self) -> None:
        rows = []
        for e in self.entries:
            d = asdict(e)
            d["entry_date"] = e.entry_date.isoformat()
            d["exit_date"] = e.exit_date.isoformat() if e.exit_date else None
            # score_reasons — tuple to'g'ridan-to'g'ri CSV katakka yozilsa
            # str(tuple) ("('a', 'b')") sifatida saqlanib, qayta o'qib bo'lmaydi
            # -- shuning uchun JSON-string (bo'sh tuple -> None, "reference_target_price"
            # konvensiyasidagi kabi "yo'q" = None).
            d["score_reasons"] = json.dumps(list(e.score_reasons)) if e.score_reasons else None
            rows.append(d)
        df = pd.DataFrame(rows, columns=_COLUMNS)
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(self.csv_path, index=False)
