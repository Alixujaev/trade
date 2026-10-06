"""scripts/rebaseline_day15h.py: DAY-15H — DAY-04 baseline re-baseline on the v1.1 Alpaca SIP research data.

    python scripts/rebaseline_day15h.py [--trades-csv PATH]

Reads only data/oos_cache/protocol_v1.1/research (via data/v11_research_loader.py). No network, no yfinance,
no data/cache, no OOS. Writes artifacts/day15/day15h-alpaca-rebaseline.json.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from acquisition.environment import capture_environment  # noqa: E402
from acquisition.run import INTEGRITY_BASELINE, hash_dirs  # noqa: E402
from acquisition.validation import expected_bar_opens  # noqa: E402
from acquisition.v1_1.contract import FIRST_OOS_SESSION, PROTOCOL_DOC  # noqa: E402
from acquisition.v1_1.sessions import resolve_v11_sessions  # noqa: E402
from backtest.day_types import ExecutionConfig  # noqa: E402
from backtest.v11_rebaseline import (  # noqa: E402
    distribution, execution_config_dict, future_mutation_check, per_symbol_metrics, pooled_metrics,
    research_gate, run_baseline, trades_digest, warmup_mutation_check,
)
from data.session import to_eastern  # noqa: E402
from data.v11_research_loader import load_v11_research  # noqa: E402

OUT_JSON = ROOT / "artifacts" / "day15" / "day15h-alpaca-rebaseline.json"
OLD_DAY04 = ROOT / "artifacts" / "day04" / "multi-symbol-results.json"
FUTURE_CUTOFF = date(2026, 9, 14)


def _git(*a: str) -> str:
    return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def data_audit(data) -> dict:
    cal = {s.session: s for s in resolve_v11_sessions()}
    issues, max_ts = [], None
    for sym, ivs in data.frames.items():
        for iv, df in ivs.items():
            if df.index.duplicated().any():
                issues.append(f"{sym} {iv} duplicates")
            sess = pd.Series(to_eastern(df.index).date, index=df.index)
            got = set(sess)
            if got != set(data.warmup_sessions) | set(data.research_sessions):
                issues.append(f"{sym} {iv} session set mismatch")
            for d in got:
                grid = expected_bar_opens(cal[d], iv)
                if not df.index[(sess == d).to_numpy()].equals(grid):
                    issues.append(f"{sym} {iv} {d} grid mismatch")
            m = df.index.max()
            max_ts = m if max_ts is None or m > max_ts else max_ts
    return {
        "research_sessions": len(data.research_sessions), "warmup_sessions": len(data.warmup_sessions),
        "embargo_sessions_classified": [d.isoformat() for d in data.embargo_sessions],
        "embargo_loaded_into_engine": False, "symbols": len(data.frames),
        "intervals": sorted({iv for v in data.frames.values() for iv in v}),
        "max_bar_open_loaded_utc": max_ts.isoformat(), "oos_first_session": FIRST_OOS_SESSION.isoformat(),
        "oos_data_read": bool(max_ts is not None and to_eastern(max_ts).date() >= FIRST_OOS_SESSION),
        "rth_grid_issues": issues, "columns_used": ["open", "high", "low", "close", "volume"],
        "provider_vwap_used": False, "adjustment": data.identity["provider_config"]["adjustment"],
        "feed": data.identity["provider_config"]["feed"], "yfinance_or_data_cache_used": False,
        "passed": not issues,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trades-csv", default=None)
    a = ap.parse_args()
    t0 = datetime.now(timezone.utc)
    base = json.loads(INTEGRITY_BASELINE.read_text(encoding="utf-8"))["hashes"]
    h0 = hash_dirs()
    frozen_before = [d for d in base if base[d] != h0.get(d)]

    data = load_v11_research()
    audit = data_audit(data)
    print(json.dumps({k: audit[k] for k in ("research_sessions", "warmup_sessions", "symbols", "max_bar_open_loaded_utc",
                                            "oos_data_read", "passed")}), flush=True)
    if not audit["passed"] or audit["oos_data_read"]:
        print("DATA AUDIT FAILED — stopping", flush=True)
        return 3

    cfg = ExecutionConfig()
    runs = run_baseline(data, cfg, log=lambda m: print(m, flush=True))
    sess_ok = all(r["research_sessions"] == 60 for r in runs)
    prefix_ok = all(r["prefix_ok"] for r in runs)
    per_sym = [per_symbol_metrics(r, cfg) for r in runs]
    pooled = pooled_metrics(runs, cfg)
    dist = distribution(per_sym)
    digest1 = trades_digest(runs)

    print("determinism re-run ...", flush=True)
    runs2 = run_baseline(data, cfg)
    digest2 = trades_digest(runs2)
    pooled2 = pooled_metrics(runs2, cfg)
    determinism = {"trades_sha256_run1": digest1, "trades_sha256_run2": digest2,
                   "pooled_metrics_equal": json.dumps(pooled, sort_keys=True, default=str) ==
                   json.dumps(pooled2, sort_keys=True, default=str)}
    determinism["passed"] = digest1 == digest2 and determinism["pooled_metrics_equal"]
    del runs2

    print("PIT future mutation ...", flush=True)
    pit_future = future_mutation_check(data, runs, FUTURE_CUTOFF, cfg)
    print("PIT warmup mutation ...", flush=True)
    pit_warm = warmup_mutation_check(data, runs, cfg)
    pit = {"future_mutation": pit_future,
           "warmup_prefix": {"passed": prefix_ok, "description": "warmup-only run reproduces full-run warmup trades "
                             "for every symbol (validates research-counter subtraction)"},
           "warmup_mutation": pit_warm,
           "embargo": {"embargo_session": [d.isoformat() for d in data.embargo_sessions], "loaded_into_engine": False,
                       "evaluated_embargo_trades": sum(1 for r in runs for t in r["research_trades"]
                                                       if to_eastern(t.setup_time).date() in set(data.embargo_sessions))}}
    pit["passed"] = pit_future["passed"] and prefix_ok and pit["embargo"]["evaluated_embargo_trades"] == 0

    status = _git("status", "--porcelain", "--untracked-files=all").splitlines()
    dirty = [ln[3:].strip() for ln in status if ln.strip()]
    repro = {
        "git_commit": _git("rev-parse", "HEAD"), "git_dirty": bool(dirty),
        "uncommitted_files": {p: _sha(ROOT.parent / p) if (ROOT.parent / p).is_file() else
                              (_sha(ROOT / p) if (ROOT / p).is_file() else None) for p in dirty},
        "protocol": {"path": PROTOCOL_DOC, "sha256": _sha(ROOT / PROTOCOL_DOC),
                     "commit": _git("log", "-1", "--format=%H", "--", PROTOCOL_DOC)},
        "signal_module": {"path": "strategy/day/vwap_momentum.py", "sha256": _sha(ROOT / "strategy/day/vwap_momentum.py"),
                          "commit": _git("log", "-1", "--format=%H", "--", "strategy/day/vwap_momentum.py")},
        "engine_module_sha256": _sha(ROOT / "backtest/day_engine.py"),
        "execution_module_sha256": _sha(ROOT / "backtest/execution.py"),
        "environment": {k: v for k, v in capture_environment().items() if k in
                        ("python_version", "platform", "distributions_sha256", "environment_sha256", "git_commit")},
        "dataset": data.identity,
        "command": "python scripts/rebaseline_day15h.py",
    }
    repro["complete"] = all(repro[k] for k in ("git_commit", "protocol", "signal_module", "environment", "dataset"))

    h1 = hash_dirs()
    frozen_after = [d for d in base if base[d] != h1.get(d)]
    snap_ok = all(_sha(data.snapshot_dir / n) == h for n, h in data.identity["data_file_sha256"].items())
    integrity = {"data_audit_passed": audit["passed"], "research_sessions_60_per_symbol": sess_ok,
                 "frozen_v10_changed_before": frozen_before, "frozen_v10_changed_after": frozen_after,
                 "snapshot_files_unchanged": snap_ok}
    integrity["passed"] = (audit["passed"] and sess_ok and not frozen_before and not frozen_after and snap_ok)

    primary = pooled["primary_metric"]["value"]
    gate = research_gate(primary, {"data_integrity": integrity["passed"], "pit": pit["passed"],
                                   "determinism": determinism["passed"], "reproducibility": repro["complete"]})

    old = json.loads(OLD_DAY04.read_text(encoding="utf-8"))
    out = {
        "experiment": "DAY-15H Alpaca SIP research re-baseline of the DAY-04 baseline", "protocol_version": "v1.1",
        "family": "F-BASE", "provenance": "PREDECLARED (protocol v1.1 §20–§21)",
        "run_utc": t0.isoformat(), "finished_utc": datetime.now(timezone.utc).isoformat(),
        "windows": {"warmup": [data.warmup_sessions[0].isoformat(), data.warmup_sessions[-1].isoformat()],
                    "research": [data.research_sessions[0].isoformat(), data.research_sessions[-1].isoformat()],
                    "embargo_excluded": [d.isoformat() for d in data.embargo_sessions]},
        "universe": sorted(data.frames), "execution_config": execution_config_dict(cfg),
        "data_audit": audit, "pooled": pooled, "symbol_distribution": dist, "per_symbol": per_sym,
        "determinism": determinism, "pit": pit, "integrity": integrity, "reproducibility": repro, "gate": gate,
        "historical_reference_day04_yfinance": {
            "label": "HISTORICAL REFERENCE — NOT CURRENT GATE RESULT", "path": "artifacts/day04/multi-symbol-results.json",
            "aggregate_trade_stats": old["aggregate_trade_stats"], "symbol_distribution": old["symbol_distribution"],
            "slippage_sensitivity": old["slippage_sensitivity"],
            "per_symbol": {m["symbol"]: {k: m[k] for k in ("trades", "strategy_total_return", "buy_hold_return", "total_R")}
                           for m in old["per_symbol_metrics"]}},
        "oos": "No OOS data was downloaded or evaluated.",
    }
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    if a.trades_csv:
        rows = [{"symbol": t.symbol, "setup_time": t.setup_time, "entry_time": t.entry_time, "exit_time": t.exit_time,
                 "exit_reason": t.exit_reason, "setup_status": t.setup_status, "net_return": t.net_return,
                 "r_multiple": t.r_multiple} for r in runs for t in r["research_trades"]]
        pd.DataFrame(rows).to_csv(a.trades_csv, index=False)
    print(json.dumps({"gate": gate, "primary": primary, "trades": pooled["aggregate"]["total_trades"],
                      "determinism": determinism["passed"], "pit": pit["passed"], "integrity": integrity["passed"]},
                     indent=2, default=str))
    print(f"written: {OUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
