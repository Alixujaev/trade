"""acquisition/akinda/sync.py: explicit-ticker Akinda /compliance sync -> evidence + validated proposed registry rows.

    python -m acquisition.akinda.sync --tickers AAPL MSFT --valid-days N [--out DIR] [--env-file PATH]

- At most DAILY_CALL_LIMIT tickers per run; no default universe, no scan.
- Daily budget: every HTTP attempt is appended to <out>/usage.jsonl BEFORE it is sent; attempts in the last 24 h
  count. A run that needs more tickers than the remaining budget is refused up front; a retry that would exceed it
  stops the batch. Calls made outside this tool (dashboard, other machines) are invisible to this ledger.
- 401/403/429/quota stop the batch; results already obtained are kept. 404 and malformed bodies get no record.
- Evidence (write-once, git-ignored): <out>/runs/<run_id>/<TICKER>.body (redacted bytes), proposed.csv,
  summary.json. proposed.csv is validated with screening.eligibility.load_registry (production defaults).
- This tool never edits config/sharia_eligibility.csv.
Exit codes: 0 completed; 2 refused before any request; 3 batch stopped; 4 proposed registry failed validation.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Callable
from zoneinfo import ZoneInfo

from acquisition.akinda.client import AkindaClient, AkindaError, redact
from acquisition.akinda.contract import (
    API_KEY_ENV,
    DAILY_CALL_LIMIT,
    DEFAULT_EVIDENCE_ROOT,
    PROTECTED_ROOTS,
    PROVIDER,
    QUOTA_WINDOW,
    TICKER_RE,
)
from acquisition.akinda.normalize import normalize
from acquisition.contract import ROOT_DIR
from screening.eligibility import (
    AKINDA_COMPLIANCE_METHODOLOGY,
    MAX_VALIDITY_DAYS,
    REQUIRED_COLUMNS,
    EligibilityError,
    load_registry,
)

NY = ZoneInfo("America/New_York")
__all__ = ["ROOT_DIR", "load_api_key", "run_sync", "main"]


def load_api_key(env_file: Path) -> str | None:
    """Environment first, then the .env file (read without exporting it to os.environ)."""
    key = os.environ.get(API_KEY_ENV)
    if key:
        return key
    if Path(env_file).is_file():
        from dotenv import dotenv_values
        return dotenv_values(env_file).get(API_KEY_ENV) or None
    return None


def _check_tickers(tickers: list[str]) -> list[str]:
    if not tickers:
        raise ValueError("at least one ticker is required (no default universe)")
    if len(tickers) > DAILY_CALL_LIMIT:
        raise ValueError(f"at most {DAILY_CALL_LIMIT} tickers per run (Basic plan daily limit)")
    norm = [t.strip().upper() if isinstance(t, str) else t for t in tickers]
    bad = [t for t in norm if not isinstance(t, str) or not TICKER_RE.match(t)]
    if bad:
        raise ValueError(f"invalid ticker(s): {bad}")
    if len(set(norm)) != len(norm):
        raise ValueError(f"duplicate ticker(s) in {norm}")
    return norm


def _check_out(out_root: Path) -> Path:
    out = Path(out_root).resolve()
    for p in PROTECTED_ROOTS:
        if out == p.resolve() or out.is_relative_to(p.resolve()):
            raise ValueError(f"evidence directory {out} is inside protected path {p}")
    return out


class UsageLedger:
    def __init__(self, path: Path, now: Callable[[], datetime]) -> None:
        self.path, self.now = path, now

    def used(self) -> int:
        if not self.path.is_file():
            return 0
        cutoff = self.now() - QUOTA_WINDOW
        n = 0
        for i, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            try:
                utc = datetime.fromisoformat(json.loads(line)["utc"])
                if utc.utcoffset() is None:
                    raise ValueError("timestamp has no timezone")
            except (ValueError, KeyError, TypeError) as exc:
                raise ValueError(f"usage ledger {self.path} line {i} is unreadable ({type(exc).__name__}); "
                                 "refusing to guess the remaining daily budget") from None
            n += utc > cutoff
        return n

    def record(self, ticker: str) -> None:
        if self.used() >= DAILY_CALL_LIMIT:
            raise AkindaError(f"daily call budget of {DAILY_CALL_LIMIT} per 24 h is used up", kind="quota")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"utc": self.now().isoformat(), "ticker": ticker}) + "\n")


def _proposed_csv(rows: list[dict[str, str]]) -> str:
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=REQUIRED_COLUMNS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return out.getvalue()


def run_sync(tickers: list[str], *, valid_days: int, out_root: Path, api_key: str | None,
             get: Callable[..., Any] | None = None, sleep: Callable[[float], None] = time.sleep,
             now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> tuple[int, dict[str, Any]]:
    tickers = _check_tickers(list(tickers))
    if isinstance(valid_days, bool) or not isinstance(valid_days, int) or not 1 <= valid_days <= MAX_VALIDITY_DAYS:
        raise ValueError(f"valid_days must be an int in 1..{MAX_VALIDITY_DAYS}")
    out = _check_out(out_root)
    if not api_key:
        raise ValueError(f"{API_KEY_ENV} is not set (environment or .env); no request was made")
    ledger = UsageLedger(out / "usage.jsonl", now)
    remaining = DAILY_CALL_LIMIT - ledger.used()
    if len(tickers) > remaining:
        raise ValueError(f"run needs {len(tickers)} calls but only {max(remaining, 0)} remain in the daily call "
                         f"budget ({DAILY_CALL_LIMIT} per 24 h); no request was made")

    started = now()
    run_id = started.strftime("%Y%m%dT%H%M%SZ")
    run_dir = out / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)                      # write-once
    client = AkindaClient(api_key, get=get, sleep=sleep, before_attempt=ledger.record)
    summary: dict[str, Any] = {"provider": PROVIDER, "methodology": AKINDA_COMPLIANCE_METHODOLOGY, "run_id": run_id,
                               "started_utc": started.isoformat(), "valid_days": valid_days,
                               "requested": tickers, "tickers": {}, "stopped": None}
    rows: list[dict[str, str]] = []
    for t in tickers:
        try:
            res = client.fetch(t)
        except AkindaError as exc:
            summary["stopped"] = {"ticker": t, "kind": exc.kind, "status": exc.status,
                                  "message": redact(str(exc), api_key)}
            break
        retrieved = now()
        entry: dict[str, Any] = {"retrieved_utc": retrieved.isoformat(), "http_status": res.http_status,
                                 "attempts": res.attempts, "outcome": "no_record"}
        if res.body is not None:
            (run_dir / f"{t}.body").write_bytes(res.body)
            entry["body_sha256"] = hashlib.sha256(res.body).hexdigest()
        if res.http_status is None:
            entry["diagnostic"] = "attempts exhausted without a usable response"
        elif res.http_status != 200:
            entry["diagnostic"] = f"HTTP {res.http_status}: no record (e.g. 404 = not in Akinda coverage)"
        else:
            try:
                payload = json.loads(res.body.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                entry["diagnostic"] = "malformed: body is not valid JSON"
            else:
                ref = f"run {run_id} {t}.body sha256 {entry['body_sha256']}"
                n = normalize(t, payload, retrieved_on=retrieved.astimezone(NY).date(), valid_days=valid_days,
                              source_ref=ref)
                entry.update({"halal_status_raw": n.halal_status_raw, "last_scanned_raw": n.last_scanned_raw,
                              "last_updated_raw": n.last_updated_raw, "diagnostic": n.diagnostic})
                if n.row is not None:
                    rows.append(n.row)
                    entry.update({"outcome": "record", "record_status": n.row["status"]})
        summary["tickers"][t] = entry

    proposed = run_dir / "proposed.csv"
    proposed.write_text(_proposed_csv(rows), encoding="utf-8")
    try:
        load_registry(proposed)                                         # production defaults, no override
        summary["registry_validation"] = "ok"
    except EligibilityError as exc:
        summary["registry_validation"] = f"FAILED: {exc}"
    summary["finished_utc"] = now().isoformat()
    text = redact(json.dumps(summary, indent=1, sort_keys=True, default=str), api_key)
    (run_dir / "summary.json").write_text(text, encoding="utf-8")
    code = 4 if summary["registry_validation"] != "ok" else 3 if summary["stopped"] else 0
    return code, json.loads(text)


def main(argv: list[str] | None = None, *, get: Callable[..., Any] | None = None,
         sleep: Callable[[float], None] = time.sleep,
         now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tickers", nargs="+", required=True)
    ap.add_argument("--valid-days", type=int, required=True,
                    help=f"validity window of each new record in days (1..{MAX_VALIDITY_DAYS}); operator choice")
    ap.add_argument("--out", default=str(DEFAULT_EVIDENCE_ROOT))
    ap.add_argument("--env-file", default=str(ROOT_DIR / ".env"))
    a = ap.parse_args(argv)
    key = load_api_key(Path(a.env_file))
    try:
        code, summary = run_sync(a.tickers, valid_days=a.valid_days, out_root=Path(a.out), api_key=key, get=get,
                                 sleep=sleep, now=now)
    except (ValueError, FileExistsError) as exc:
        print(f"REFUSED: {redact(str(exc), key or '')}")
        return 2
    brief = {t: {k: e.get(k) for k in ("outcome", "record_status", "halal_status_raw", "diagnostic")}
             for t, e in summary["tickers"].items()}
    print(redact(json.dumps({"run_id": summary["run_id"], "stopped": summary["stopped"],
                             "registry_validation": summary["registry_validation"], "tickers": brief},
                            indent=1, default=str), key or ""))
    return code


if __name__ == "__main__":
    sys.exit(main())
