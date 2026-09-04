"""Exit Research v0 — entry generation bir marta, keyin A-F exit modellari solishtiriladi.

Tadqiqot savoli: Robot tanlagan entry'larda (o'zgarishsiz), pozitsiyani ba'zan yopadigan
exit modeli — shu entry'larni exitsiz ushlab turishdan (constrained buy&hold) ko'ra OOS
risk-adjusted natijani (Sharpe) yaxshilaydimi?

Muhim: `strategy.breakout_retest.generate_breakout_retest_signals` + `strategy.scoring.apply_scores`
har oyna (TRAIN/OOS) uchun FAQAT BIR MARTA chaqiriladi (`load_universe_frozen` orqali) — natijadagi
`SymbolData.signals` ro'yxati keyin barcha 6 exit modeliga AYNAN bir xil beriladi. Exit model
FAQAT `backtest/portfolio.py::PortfolioConfig.exit_model` orqali farq qiladi; universe/oyna/
komissiya/slippage/max_concurrent/max_portfolio_risk hammasi bir xil qoladi.

Ishlatish:
    python scripts/exit_research.py [SYMBOLS...] \
        --start 2020-01-01 --end 2026-09-03 --oos-start 2023-01-01 \
        --interval 1d --min-score 70 --max-concurrent 10 --max-portfolio-risk 0.10 \
        --commission-pct 0 --slippage-pct 0.05 --exits A,B,C,D,E,F \
        --output-csv reports/exit_research.csv

SYMBOLS bo'sh -> get_core_watchlist(). --start bo'sh -> ~5 yil oldin. --slippage-pct FOIZ
qiymat sifatida kiritiladi (masalan 0.05 -> 0.0005 ulush).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# Skript qayerdan ishga tushirilishidan qat'iy nazar paketlar topilishi uchun
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.exits import EXIT_MODEL_KEYS, build_exit_model  # noqa: E402
from backtest.portfolio import PortfolioConfig, PortfolioResult, SymbolData, run_portfolio  # noqa: E402
from backtest.types import TradeResult  # noqa: E402
from config.core_watchlist import get_core_watchlist  # noqa: E402
from config.settings import (  # noqa: E402
    BREAKOUT_COMMISSION_PCT,
    MAX_CONCURRENT_POSITIONS,
    MAX_PORTFOLIO_RISK_PCT,
    MIN_BREAKOUT_RR,
    SWING_LOOKBACK,
)
from scripts.backtest_breakout_retest import five_years_ago_iso  # noqa: E402
from scripts.backtest_portfolio import load_benchmark_df, load_universe  # noqa: E402

DEFAULT_EXITS = "A,B,C,D,E,F,NoExit"
DEFAULT_SLIPPAGE_PCT = 0.0005  # 0.05% — barcha exit modellari uchun bir xil, default
MIN_OOS_TRADES = 30
MEANINGFUL_MARGIN = 0.15
EXPERIMENTS_DIR = Path(__file__).resolve().parent.parent / "experiments"

_EXIT_MODEL_NAMES = {key: build_exit_model(key).name for key in EXIT_MODEL_KEYS}

_EXIT_REASON_LABELS: dict[str, str] = {
    "target": "TP",
    "stop": "SL",
    "trailing_stop": "TRAILING",
    "structure_break": "STRUCTURE_BREAK",
    "time_exit": "TIME_EXIT",
    "partial_tp": "partial",
    "end_of_data": "END_OF_DATA",
}

_BENCH_LABELS = {
    "equal_weight_buy_hold": "Equal-weight BH",
    "selection_bh": "Selection-BH",
    "capital_constrained_buy_hold": "Constrained BH",
}


# ======================================================================
# CLI
# ======================================================================


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Exit Research v0 — A-F exit modellari solishtiruvi")
    parser.add_argument("symbols", nargs="*", help="Bo'sh bo'lsa get_core_watchlist()")
    parser.add_argument("--start", default=None, help="ISO sana; bo'sh -> ~5 yil oldin")
    parser.add_argument("--end", default=None, help="ISO sana; bo'sh -> oxirigacha")
    parser.add_argument(
        "--oos-start", default=None,
        help="ISO sana: berilsa TRAIN=[--start, --oos-start) va OOS=[--oos-start, --end] "
             "alohida hisoblanadi. Verdict/JSON logging FAQAT shu berilganda ishlaydi.",
    )
    parser.add_argument("--interval", default="1d")
    parser.add_argument("--provider", default=None, help="yfinance yoki alpaca")
    parser.add_argument("--min-score", type=float, default=None)
    parser.add_argument("--max-concurrent", type=int, default=MAX_CONCURRENT_POSITIONS)
    parser.add_argument("--max-portfolio-risk", type=float, default=MAX_PORTFOLIO_RISK_PCT)
    parser.add_argument("--commission-pct", type=float, default=BREAKOUT_COMMISSION_PCT)
    parser.add_argument(
        "--slippage-pct", type=float, default=DEFAULT_SLIPPAGE_PCT * 100,
        help="FOIZ qiymat (masalan 0.05 -> 0.0005 ulush). Default 0.05.",
    )
    parser.add_argument(
        "--exits", default=DEFAULT_EXITS,
        help=f"Vergul bilan ajratilgan model harflari, masalan A,C,D. Default {DEFAULT_EXITS}.",
    )
    parser.add_argument("--output-csv", default=None, help="Berilsa: reports/exit_research.csv kabi")
    parser.add_argument("--min-oos-trades", type=int, default=MIN_OOS_TRADES)
    parser.add_argument("--meaningful-margin", type=float, default=MEANINGFUL_MARGIN)
    parser.add_argument("--benchmark-ticker", default="SPUS")
    parser.add_argument("--initial-capital", type=float, default=100_000.0)
    parser.add_argument("--lookback", type=int, default=SWING_LOOKBACK)
    parser.add_argument("--min-rr", type=float, default=MIN_BREAKOUT_RR)
    parser.add_argument("--require-trend", dest="require_trend", action="store_true", default=True)
    parser.add_argument("--no-require-trend", dest="require_trend", action="store_false")
    return parser.parse_args()


# ======================================================================
# Entry freeze — universe + signal'lar BIR MARTA quriladi
# ======================================================================


def load_universe_frozen(
    args: argparse.Namespace, *, start: str | None, end: str | None
) -> tuple[list[SymbolData], list[dict]]:
    """Bitta oyna uchun entry generation'ni BIR MARTA bajaradi.

    Natijadagi `list[SymbolData]` (va uning `.signals`) keyin har bir exit modeliga
    o'zgarishsiz beriladi — `run_all_models` uni qayta hisoblamaydi.
    """
    symbols = args.symbols if args.symbols else [h.ticker for h in get_core_watchlist()]
    return load_universe(
        symbols, interval=args.interval, provider_name=args.provider, start=start, end=end,
        lookback=args.lookback, min_rr=args.min_rr, require_trend=args.require_trend,
        min_score=args.min_score,
    )


def run_one_exit_model(
    symbols: list[SymbolData],
    *,
    model_key: str,
    cfg_base: PortfolioConfig,
    benchmark_df: pd.DataFrame | None,
    benchmark_ticker: str,
) -> PortfolioResult:
    """cfg_base'dan FAQAT exit_model farqi bilan bitta PortfolioConfig quradi va backtest qiladi.

    Universe/signal'lar (`symbols`) chaqiruvchidan keladi — bu yerda QAYTA HISOBLANMAYDI.
    """
    cfg = dataclasses.replace(cfg_base, exit_model=build_exit_model(model_key))
    return run_portfolio(
        symbols, cfg=cfg, benchmark_df=benchmark_df, benchmark_ticker=benchmark_ticker,
        include_constrained=True, include_selection=True,
    )


def run_all_models(
    symbols: list[SymbolData],
    *,
    model_keys: list[str],
    cfg_base: PortfolioConfig,
    benchmark_df: pd.DataFrame | None,
    benchmark_ticker: str,
) -> dict[str, PortfolioResult]:
    """Barcha `model_keys`'ni AYNAN bir xil `symbols` (frozen entries) ustida yugurtiradi."""
    return {
        key: run_one_exit_model(
            symbols, model_key=key, cfg_base=cfg_base, benchmark_df=benchmark_df,
            benchmark_ticker=benchmark_ticker,
        )
        for key in model_keys
    }


def run_windows_all_models(
    args: argparse.Namespace, *, model_keys: list[str]
) -> dict[str, dict[str, PortfolioResult]]:
    """--oos-start berilsa {"TRAIN": {...}, "OOS": {...}}, aks holda {"TO'LIQ": {...}}.

    Har oyna uchun `load_universe_frozen` ALOHIDA (turli sana oralig'i -> turli data/entry'lar
    tabiiy), lekin bitta oyna ICHIDA barcha model_keys bir xil `symbols` obyektini ishlatadi.
    """
    start = args.start or five_years_ago_iso()
    cfg_base = PortfolioConfig(
        initial_capital=args.initial_capital,
        max_concurrent_positions=args.max_concurrent,
        max_portfolio_risk_pct=args.max_portfolio_risk,
        commission_pct=args.commission_pct,
        slippage_pct=args.slippage_pct / 100.0,
        interval=args.interval,
    )

    def _window(win_start: str | None, win_end: str | None) -> dict[str, PortfolioResult]:
        symbols, _errors = load_universe_frozen(args, start=win_start, end=win_end)
        bench_df, _bench_err = load_benchmark_df(
            args.benchmark_ticker, interval=args.interval, provider_name=args.provider,
            start=win_start, end=win_end,
        )
        return run_all_models(
            symbols, model_keys=model_keys, cfg_base=cfg_base, benchmark_df=bench_df,
            benchmark_ticker=args.benchmark_ticker,
        )

    if not args.oos_start:
        return {"TO'LIQ": _window(start, args.end)}

    train_end = (pd.Timestamp(args.oos_start) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    return {
        "TRAIN": _window(start, train_end),
        "OOS": _window(args.oos_start, args.end),
    }


# ======================================================================
# Reporting — metrik nomlash (spec) <- portfolio.py metrikalari
# ======================================================================


def to_report_metrics(m: dict, *, trades: list[TradeResult]) -> dict:
    """portfolio.py metrics dict'ini spec nomlariga moslaydi + calmar_pct/trade_count qo'shadi.

    `trade_count` — leg='partial' qatorlar chiqarib tashlangan (Model E'da bitta pozitsiya
    ikkita TradeResult'ga bo'linadi; savdo SONI baribir 1 bo'lishi kerak).
    """
    max_dd = m["max_drawdown_pct"]
    calmar = (m["cagr_pct"] / abs(max_dd)) if max_dd else 0.0
    trade_count = sum(1 for t in trades if t.leg != "partial")
    return {
        "total_return_pct": m["total_return_pct"],
        "cagr_pct": m["cagr_pct"],
        "max_dd_pct": max_dd,
        "sharpe": m["sharpe"],
        "sortino": m["sortino"],
        "calmar_pct": calmar,
        "expectancy_r": m["expectancy_r"],
        "profit_factor": m["profit_factor"],
        "avg_hold_bars": m["avg_hold_days"],
        "trade_count": trade_count,
        "num_skipped": m["num_skipped"],
        "skipped_by_reason": m["skipped_by_reason"],
    }


def benchmark_report_metrics(bm: dict) -> dict:
    """Benchmark curve_metrics dict'ini (return_pct/cagr_pct/max_drawdown_pct/sharpe/sortino)
    xuddi shu ustunlarga moslaydi. expectancy/profit_factor/avg_hold/trade_count'i yo'q (None)."""
    max_dd = bm.get("max_drawdown_pct", 0.0)
    calmar = (bm["cagr_pct"] / abs(max_dd)) if max_dd else 0.0
    return {
        "total_return_pct": bm.get("return_pct", 0.0),
        "cagr_pct": bm.get("cagr_pct", 0.0),
        "max_dd_pct": max_dd,
        "sharpe": bm.get("sharpe", 0.0),
        "sortino": bm.get("sortino", 0.0),
        "calmar_pct": calmar,
        "expectancy_r": None,
        "profit_factor": None,
        "avg_hold_bars": None,
        "trade_count": bm.get("trade_count"),
    }


def exit_reason_breakdown(trades: list[TradeResult]) -> dict[str, int]:
    """exit_reason -> spec label -> son (Counter)."""
    return dict(Counter(_EXIT_REASON_LABELS.get(t.exit_reason, t.exit_reason) for t in trades))


def _benchmark_by_name(result: PortfolioResult, name: str) -> dict:
    for b in result.benchmarks:
        if b.name == name:
            return b.metrics or {}
    return {}


# ======================================================================
# Verdict engine
# ======================================================================


def _tiered_verdict(
    *,
    sample_trade_count: int,
    sharpe_delta: float,
    min_oos_trades: int,
    meaningful_margin: float,
    edge_label: str,
    no_edge_label: str,
) -> str:
    """Ikkala tier (Level 1/Level 2) uchun umumiy margin+low-sample gate mantig'i."""
    if sample_trade_count < min_oos_trades:
        return "INCONCLUSIVE (low sample)"
    if sharpe_delta >= meaningful_margin:
        return edge_label
    if sharpe_delta > 0:
        return "INCONCLUSIVE"
    return no_edge_label


def verdict_for_model(
    *,
    oos_trade_count: int,
    oos_sharpe: float,
    baseline_oos_sharpe: float,
    min_oos_trades: int = MIN_OOS_TRADES,
    meaningful_margin: float = MEANINGFUL_MARGIN,
) -> str:
    """LEVEL 2 (Exit): 1) low sample -> INCONCLUSIVE. 2) delta=oos_sharpe-baseline_oos_sharpe:
    >=margin -> 'EXIT IMPROVEMENT'; 0<delta<margin -> INCONCLUSIVE; <=0 -> NO EDGE.

    `baseline_oos_sharpe` — NoExit-capped (control group, bir xil max_concurrent/
    max_portfolio_risk ostida) OOS Sharpe'i, `compute_level2_verdicts` orqali. Constrained BH
    EMAS: constrained BH boshqa sizing (fixed-$) ishlatadi va hech qachon exit qilib capital
    recycle qilmaydi, shu bois exit-timing ta'sirini sof isbotlay olmaydi (confounded) —
    faqat ma'lumot/kontekst uchun jadvalda qoladi.
    """
    return _tiered_verdict(
        sample_trade_count=oos_trade_count, sharpe_delta=oos_sharpe - baseline_oos_sharpe,
        min_oos_trades=min_oos_trades, meaningful_margin=meaningful_margin,
        edge_label="EXIT IMPROVEMENT", no_edge_label="NO EDGE",
    )


def verdict_for_selection(
    *,
    oos_trade_count: int,
    selection_oos_sharpe: float,
    equal_weight_oos_sharpe: float,
    min_oos_trades: int = MIN_OOS_TRADES,
    meaningful_margin: float = MEANINGFUL_MARGIN,
) -> str:
    """LEVEL 1 (Selection): Selection-BH OOS Sharpe'ni Equal-weight BH OOS Sharpe'iga
    solishtiradi — 'SELECTION EDGE' / 'NO SELECTION EDGE' / 'INCONCLUSIVE (low sample)'."""
    return _tiered_verdict(
        sample_trade_count=oos_trade_count,
        sharpe_delta=selection_oos_sharpe - equal_weight_oos_sharpe,
        min_oos_trades=min_oos_trades, meaningful_margin=meaningful_margin,
        edge_label="SELECTION EDGE", no_edge_label="NO SELECTION EDGE",
    )


def compute_level2_verdicts(
    oos_results: dict[str, PortfolioResult],
    *,
    min_oos_trades: int = MIN_OOS_TRADES,
    meaningful_margin: float = MEANINGFUL_MARGIN,
) -> dict[str, str]:
    """LEVEL 2 (Exit): har A-F (NoExit-capped'dan TASHQARI) uchun OOS Sharpe'ni NoExit-capped
    (bir xil max_concurrent/max_portfolio_risk ostidagi control) OOS Sharpe'iga solishtiradi —
    ikkalasi ham BIR XIL cheklov ostida, shuning uchun adolatli (apples-to-apples).
    Constrained-BH confounded baseline EMAS.

    NoExit-capped natija ro'yxatda bo'lmasa — bo'sh dict. NoExit-capped'ning O'ZI
    MIN_OOS_TRADES'dan kam savdo qilgan bo'lsa (odatda shunday — doim BAND bo'lgan
    slot(lar) tufayli kam savdo) — BARCHA A-F uchun 'INCONCLUSIVE (baseline low sample)'
    (har bir modelning o'z trade_count'idan qat'i nazar — baseline shovqinli bo'lsa,
    solishtiruvning O'ZI ishonchsiz).
    """
    if "NOEXIT" not in oos_results:
        return {}
    no_exit_result = oos_results["NOEXIT"]
    no_exit_trade_count = sum(1 for t in no_exit_result.trades if t.leg != "partial")
    no_exit_sharpe = no_exit_result.metrics["sharpe"]

    verdicts: dict[str, str] = {}
    for key, result in oos_results.items():
        if key == "NOEXIT":
            continue  # control group -- o'ziga verdict berilmaydi
        if no_exit_trade_count < min_oos_trades:
            verdicts[key] = "INCONCLUSIVE (baseline low sample)"
            continue
        trade_count = sum(1 for t in result.trades if t.leg != "partial")
        verdicts[key] = verdict_for_model(
            oos_trade_count=trade_count, oos_sharpe=result.metrics["sharpe"],
            baseline_oos_sharpe=no_exit_sharpe, min_oos_trades=min_oos_trades,
            meaningful_margin=meaningful_margin,
        )
    return verdicts


def compute_level1_verdict(
    oos_results: dict[str, PortfolioResult],
    *,
    min_oos_trades: int = MIN_OOS_TRADES,
    meaningful_margin: float = MEANINGFUL_MARGIN,
) -> str:
    """LEVEL 1 (Selection): Selection-BH OOS Sharpe'ni Equal-weight BH OOS Sharpe'iga
    solishtiradi (bitta oyna uchun BITTA xulosa — har-modelga emas). Selection-BH'ning
    trade_count'i (= candidate soni) MIN_OOS_TRADES'dan kam bo'lsa -> low-sample. Har qanday
    OOS natijaning `.benchmarks` ishlatiladi — barchasida bir xil (bir xil universe/oyna/
    xarajat)."""
    if not oos_results:
        return "INCONCLUSIVE (low sample)"
    first = next(iter(oos_results.values()))
    selection_bm = _benchmark_by_name(first, "selection_bh")
    equal_weight_bm = _benchmark_by_name(first, "equal_weight_buy_hold")
    if not selection_bm:
        return "INCONCLUSIVE (low sample)"
    trade_count = selection_bm.get("trade_count") or 0
    return verdict_for_selection(
        oos_trade_count=trade_count, selection_oos_sharpe=selection_bm.get("sharpe", 0.0),
        equal_weight_oos_sharpe=equal_weight_bm.get("sharpe", 0.0),
        min_oos_trades=min_oos_trades, meaningful_margin=meaningful_margin,
    )


def best_exit(verdicts: dict[str, str], oos_sharpes: dict[str, float]) -> tuple[str | None, str]:
    """LEVEL 2 (Exit): OOS bo'yicha max(Sharpe) 'EXIT IMPROVEMENT' model. Hech biri bo'lmasa
    (None, 'NO EXIT EDGE FOUND')."""
    edge_keys = [k for k, v in verdicts.items() if v.startswith("EXIT IMPROVEMENT")]
    if not edge_keys:
        return None, "NO EXIT EDGE FOUND"
    key = max(edge_keys, key=lambda k: oos_sharpes[k])
    return key, verdicts[key]


# ======================================================================
# Result table (spec section 13)
# ======================================================================

_TABLE_COLS = [
    "Model", "Return", "CAGR", "DD", "Sharpe", "Sortino", "Calmar", "Expectancy",
    "Profit Factor", "Avg Hold", "Trades", "Verdict",
]


def _row(label: str, rm: dict, *, verdict: str | None) -> dict:
    def _r(v: float | None, nd: int) -> float | None:
        return round(v, nd) if v is not None else None

    return {
        "Model": label,
        "Return": _r(rm["total_return_pct"], 2),
        "CAGR": _r(rm["cagr_pct"], 2),
        "DD": _r(rm["max_dd_pct"], 2),
        "Sharpe": _r(rm["sharpe"], 3),
        "Sortino": _r(rm["sortino"], 3),
        "Calmar": _r(rm["calmar_pct"], 3),
        "Expectancy": _r(rm["expectancy_r"], 4),
        "Profit Factor": _r(rm["profit_factor"], 3),
        "Avg Hold": _r(rm["avg_hold_bars"], 2),
        "Trades": rm["trade_count"],
        "Verdict": verdict or "-",
    }


def build_result_table(
    model_results: dict[str, PortfolioResult], *, verdicts: dict[str, str] | None = None
) -> pd.DataFrame:
    """Ustunlar: Model, Return, CAGR, DD, Sharpe, Sortino, Calmar, Expectancy, Profit Factor,
    Avg Hold, Trades, Verdict. Qatorlar tartibi: Equal-weight BH (pol), Constrained BH
    (kontekst, verdict'ga ta'sir qilmaydi), NoExit (control -- verdict shunga bog'langan),
    so'ng A-F."""
    if not model_results:
        return pd.DataFrame(columns=_TABLE_COLS)

    verdicts = verdicts or {}
    rows: list[dict] = []
    first = next(iter(model_results.values()))
    for bench_name, label in _BENCH_LABELS.items():
        bm = _benchmark_by_name(first, bench_name)
        rows.append(_row(label, benchmark_report_metrics(bm), verdict=None))

    if "NOEXIT" in model_results:
        no_exit_result = model_results["NOEXIT"]
        rm = to_report_metrics(no_exit_result.metrics, trades=no_exit_result.trades)
        rows.append(_row("NoExit-capped (control)", rm, verdict="CONTROL"))

    for key, result in model_results.items():
        if key == "NOEXIT":
            continue
        rm = to_report_metrics(result.metrics, trades=result.trades)
        label = f"{key} ({_EXIT_MODEL_NAMES.get(key, key)})"
        rows.append(_row(label, rm, verdict=verdicts.get(key)))

    return pd.DataFrame(rows, columns=_TABLE_COLS)


# ======================================================================
# JSON experiment logging (spec section 14)
# ======================================================================


def git_commit_hash() -> str:
    """`git rev-parse --short HEAD`. Har qanday xato/timeout -> 'unknown'."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5,
            cwd=Path(__file__).resolve().parent.parent,
        )
        if out.returncode == 0:
            return out.stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001
        pass
    return "unknown"


def experiment_id(*, model_name: str, timestamp: datetime, commit: str) -> str:
    return f"{timestamp:%Y%m%d_%H%M%S}_{model_name}_{commit}"


def write_experiment(
    *,
    model_key: str,
    universe: list[str],
    start: str,
    end: str | None,
    oos_start: str | None,
    interval: str,
    commission_pct: float,
    slippage_pct: float,
    train_metrics: dict,
    oos_metrics: dict,
    benchmarks: dict,
    skip_breakdown: dict,
    verdict: str,
    selection_verdict: str,
    experiments_dir: Path = EXPERIMENTS_DIR,
) -> Path:
    """experiments/<id>.json yaratadi. HECH QACHON overwrite qilmaydi.

    `verdict` — LEVEL 2 (Exit), shu model uchun. `selection_verdict` — LEVEL 1 (Selection),
    bitta run ichida BARCHA model fayllari uchun bir xil (oyna-darajasidagi xulosa).
    """
    experiments_dir.mkdir(parents=True, exist_ok=True)
    model_name = _EXIT_MODEL_NAMES.get(model_key, model_key)
    commit = git_commit_hash()
    timestamp = datetime.now(timezone.utc)
    payload = {
        "exit_model": model_name,
        "params": dataclasses.asdict(build_exit_model(model_key)),
        "universe": universe,
        "period": {"start": start, "end": end},
        "oos_start": oos_start,
        "interval": interval,
        "costs": {"commission_pct": commission_pct, "slippage_pct": slippage_pct},
        "train_metrics": train_metrics,
        "oos_metrics": oos_metrics,
        "benchmarks": benchmarks,
        "skip_breakdown": skip_breakdown,
        "verdict": verdict,
        "selection_verdict": selection_verdict,
        "verdict_baseline": {"selection": "equal_weight_bh", "exit": "no_exit_capped"},
        "git_commit": commit,
        "timestamp": timestamp.isoformat(),
    }

    exp_id = experiment_id(model_name=model_name, timestamp=timestamp, commit=commit)
    path = experiments_dir / f"{exp_id}.json"
    suffix = 1
    while path.exists():  # bir soniyada 2+ run -- hech qachon overwrite qilinmasin
        path = experiments_dir / f"{exp_id}_{suffix}.json"
        suffix += 1
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


# ======================================================================
# CSV export (spec section 17)
# ======================================================================

_CSV_COLS = [
    "split", "model", "total_return_pct", "cagr_pct", "max_dd_pct", "sharpe", "sortino",
    "calmar_pct", "expectancy_r", "profit_factor", "avg_hold_bars", "trade_count", "verdict",
]


def _csv_metric_fields(rm: dict) -> dict:
    """Model va benchmark qatorlari o'rtasida ORTAQ 10 raqamli ustun (verdict/split/model'siz)."""
    return {
        "total_return_pct": rm["total_return_pct"], "cagr_pct": rm["cagr_pct"],
        "max_dd_pct": rm["max_dd_pct"], "sharpe": rm["sharpe"], "sortino": rm["sortino"],
        "calmar_pct": rm["calmar_pct"], "expectancy_r": rm["expectancy_r"],
        "profit_factor": rm["profit_factor"], "avg_hold_bars": rm["avg_hold_bars"],
        "trade_count": rm["trade_count"],
    }


def build_csv_rows(
    all_results: dict[str, dict[str, PortfolioResult]], *, verdicts: dict[str, str] | None = None
) -> pd.DataFrame:
    """(split, model) -> bitta qator. Uch benchmark (Equal-weight/Constrained/NoExit) + A-F.
    `verdicts` faqat OOS split'dagi A-F qatorlariga qo'llanadi; NoExit har doim 'CONTROL',
    Equal-weight/Constrained BH har doim '-'."""
    verdicts = verdicts or {}
    rows: list[dict] = []
    for split, model_results in all_results.items():
        if model_results:
            first = next(iter(model_results.values()))
            for bench_name, label in _BENCH_LABELS.items():
                bm = _benchmark_by_name(first, bench_name)
                rm = benchmark_report_metrics(bm)
                rows.append({"split": split, "model": label, **_csv_metric_fields(rm), "verdict": "-"})

        for key, result in model_results.items():
            rm = to_report_metrics(result.metrics, trades=result.trades)
            if key == "NOEXIT":
                verdict = "CONTROL"
            elif split == "OOS":
                verdict = verdicts.get(key, "-")
            else:
                verdict = "-"
            rows.append({
                "split": split, "model": _EXIT_MODEL_NAMES.get(key, key),
                **_csv_metric_fields(rm), "verdict": verdict,
            })
    return pd.DataFrame(rows, columns=_CSV_COLS)


# ======================================================================
# main
# ======================================================================


def main() -> None:
    args = parse_args()
    model_keys = [k.strip().upper() for k in args.exits.split(",") if k.strip()]
    for key in model_keys:
        if key not in EXIT_MODEL_KEYS:
            raise SystemExit(f"Noma'lum exit model: {key!r} (kutilgan: {EXIT_MODEL_KEYS})")
    if "NOEXIT" not in model_keys:
        print(
            "OGOHLANTIRISH: NoExit (control) --exits ro'yxatida yo'q -- verdict hisoblanmaydi "
            "(barcha exit modellari uchun Verdict='N/A (no NoExit baseline)').",
            file=sys.stderr,
        )

    windows = run_windows_all_models(args, model_keys=model_keys)

    verdicts: dict[str, str] = {}
    selection_verdict = "INCONCLUSIVE (low sample)"
    if "OOS" in windows:
        verdicts = compute_level2_verdicts(
            windows["OOS"], min_oos_trades=args.min_oos_trades,
            meaningful_margin=args.meaningful_margin,
        )
        selection_verdict = compute_level1_verdict(
            windows["OOS"], min_oos_trades=args.min_oos_trades,
            meaningful_margin=args.meaningful_margin,
        )

    for label, model_results in windows.items():
        print(f"\n=== {label} ===")
        table = build_result_table(model_results, verdicts=verdicts if label == "OOS" else None)
        print(table.to_string(index=False))

    if "OOS" in windows:
        first_oos = next(iter(windows["OOS"].values()))
        sel_bm = _benchmark_by_name(first_oos, "selection_bh")
        eq_bm = _benchmark_by_name(first_oos, "equal_weight_buy_hold")
        print(
            f"\nLEVEL 1 (Selection): {selection_verdict}  "
            f"(Selection-BH Sharpe={sel_bm.get('sharpe', 0.0):.3f} vs "
            f"Equal-weight Sharpe={eq_bm.get('sharpe', 0.0):.3f}, "
            f"trades={sel_bm.get('trade_count', 0)})"
        )
        oos_sharpes = {key: r.metrics["sharpe"] for key, r in windows["OOS"].items()}
        best_key, best_verdict = best_exit(verdicts, oos_sharpes)
        if best_key is None:
            print(f"LEVEL 2 (Exit): BEST EXIT: None / VERDICT: {best_verdict}")
        else:
            print(
                f"LEVEL 2 (Exit): BEST EXIT: {best_key} ({_EXIT_MODEL_NAMES[best_key]})  "
                f"OOS Sharpe={oos_sharpes[best_key]:.3f}  VERDICT: {best_verdict}"
            )

    if "TRAIN" in windows and "OOS" in windows:
        universe = args.symbols if args.symbols else [h.ticker for h in get_core_watchlist()]
        start = args.start or five_years_ago_iso()
        no_exit_oos = windows["OOS"].get("NOEXIT")
        no_exit_report = (
            to_report_metrics(no_exit_oos.metrics, trades=no_exit_oos.trades)
            if no_exit_oos is not None else None
        )
        for key in model_keys:
            if key == "NOEXIT":
                continue  # control group -- o'zi uchun alohida experiment yozilmaydi
            train_result = windows["TRAIN"][key]
            oos_result = windows["OOS"][key]
            train_metrics = to_report_metrics(train_result.metrics, trades=train_result.trades)
            oos_metrics = to_report_metrics(oos_result.metrics, trades=oos_result.trades)
            train_metrics["exit_reason_breakdown"] = exit_reason_breakdown(train_result.trades)
            oos_metrics["exit_reason_breakdown"] = exit_reason_breakdown(oos_result.trades)
            benchmarks = {b.name: b.metrics for b in oos_result.benchmarks}
            if no_exit_report is not None:
                benchmarks["no_exit_capped"] = no_exit_report
            path = write_experiment(
                model_key=key, universe=universe, start=start, end=args.end,
                oos_start=args.oos_start, interval=args.interval,
                commission_pct=args.commission_pct, slippage_pct=args.slippage_pct / 100.0,
                train_metrics=train_metrics, oos_metrics=oos_metrics, benchmarks=benchmarks,
                skip_breakdown=oos_result.metrics["skipped_by_reason"],
                verdict=verdicts.get(key, "N/A (no NoExit baseline)"),
                selection_verdict=selection_verdict,
            )
            print(f"Experiment saqlandi: {path}")

    if args.output_csv:
        csv_df = build_csv_rows(windows, verdicts=verdicts)
        out_path = Path(args.output_csv)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        csv_df.to_csv(out_path, index=False)
        print(f"\nCSV saqlandi: {out_path.resolve()}")


if __name__ == "__main__":
    main()
