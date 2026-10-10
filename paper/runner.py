"""paper/runner.py: sealed real-time paper-trading runner for V2-MOM (experiment V2-MOM-P001; protocol 2.3, DAY-27).

    python -m paper.runner run            process every completed, unprocessed XNYS session (idempotent; catch-up)
    python -m paper.runner status         health only (no positions or P&L before the seal time)
    python -m paper.runner check-health   exit 1 on a missed session or a failed last run (alerting)
    python -m paper.runner reveal [--session D]   positions / signals / daily P&L; refused before 2026-12-09 16:15 ET
    python -m paper.runner init-key       print a new random seal key (store it as the PAPER_SEAL_KEY secret)

Per run: lock -> preflight (v2.3 adoption committed, frozen config SHA, incident quarantine, seal key, data-only
endpoints) -> latest completed session from the XNYS calendar (close + 15 min, early closes included) -> fetch
inputs up to that session -> fail-closed checks -> replay of the frozen engine -> consistency of every previously
processed session -> risk checks -> per unprocessed session: sealed ledger (encrypted) then health record (commit
point). A crash before the health record is written leaves the session unprocessed; the next run redoes it.
No broker or trading endpoint exists here; nothing performance-bearing is printed before the seal time.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Callable

from acquisition.contract import ROOT_DIR
from backtest.v2 import forward as fw
from paper import data as pdata
from paper import ledger as pl
from paper import seal as ps
from paper.config import (
    ADOPTION_JSON_23, AMENDMENT_FILES_23, EXPERIMENT_ID, FIRST_SESSION, MARKET_TZ, SEAL_UNTIL, STALE_LOCK_SECONDS,
    ready_time, state_dir,
)

LATE_AFTER = timedelta(hours=3)
HEALTH_KEYS = ("experiment", "session", "status", "processed_utc", "late", "input_manifest_sha256", "ledger_sha256",
               "sealed_file_sha256", "strategy_config_sha256", "data_sessions", "missing_bars", "events_used",
               "review_pending_count", "code_version")


class RunnerError(RuntimeError):
    code = "RUNNER_ERROR"


class NotReady(RunnerError):
    code = "NOT_READY"


class InconsistentState(RunnerError):
    code = "INCONSISTENT_STATE"


class Busy(RunnerError):
    code = "LOCKED"


# ------------------------------------------------------------------ guards

def check_adoption_23(root: Path = ROOT_DIR, git_ok: Callable[..., bool] | None = None) -> dict:
    """Protocol 2.3 (sealed runner) adopted, pinned and committed unchanged; plus the committed v2.2 / v2.1 chain."""
    import hashlib
    git_ok = git_ok or fw._git_ok
    p = Path(root) / ADOPTION_JSON_23
    if not p.is_file():
        raise RunnerError(f"protocol-2.3 adoption record missing: {ADOPTION_JSON_23}")
    rec = json.loads(p.read_text(encoding="utf-8"))
    if rec.get("final_status") != "ADOPTED" or rec.get("protocol_version") != "2.3":
        raise RunnerError("protocol 2.3 is not ADOPTED")
    for f in AMENDMENT_FILES_23:
        if (rec.get("adopted_files_sha256_lf") or {}).get(f) != fw.lf_sha256(Path(root) / f):
            raise RunnerError(f"{f} differs from the adopted SHA-256")
    for f in (ADOPTION_JSON_23, *AMENDMENT_FILES_23):
        if not git_ok("ls-files", "--error-unmatch", f) or not git_ok("diff", "--quiet", "HEAD", "--", f):
            raise RunnerError(f"{f} is not committed unchanged; protocol 2.3 takes effect only from its commit")
    fw.check_adoption_22(root, git_ok)
    return {"adopted_utc_23": rec.get("decided_utc"),
            "pins": hashlib.sha256(json.dumps(rec.get("adopted_files_sha256_lf"), sort_keys=True).encode()).hexdigest()}


def load_env(path: Path | None = None) -> None:
    """Load the repo-root .env (gitignored) without overriding the environment, as acquisition.v2.stage_r does."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(path or (ROOT_DIR / ".env"), override=False)


def _redact(msg: str) -> str:
    for name in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY", "PAPER_SEAL_KEY", "PAPER_STATE_TOKEN"):
        v = os.environ.get(name)
        if v and len(v) >= 4:
            msg = msg.replace(v, "***")
    return msg


# ------------------------------------------------------------------ calendar

def _calendar(around: date):
    import exchange_calendars as xcals
    return xcals.get_calendar("XNYS", start=(around - timedelta(days=60)).isoformat(),
                              end=(around + timedelta(days=60)).isoformat())


def latest_completed_session(now: datetime) -> date | None:
    """Last XNYS session whose official close + 15 min (early closes included) is at or before `now`."""
    import pandas as pd
    cal = _calendar(now.astimezone(MARKET_TZ).date())
    day = now.astimezone(MARKET_TZ).date()
    s = cal.date_to_session(pd.Timestamp(day), "previous")
    for _ in range(3):
        close = cal.closes[s].tz_convert(MARKET_TZ).to_pydatetime()
        if ready_time(close) <= now:
            return s.date()
        s = cal.previous_session(s)
    return None


# ------------------------------------------------------------------ state

class State:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else state_dir()
        for d in ("runs", "sealed", "data"):
            (self.root / d).mkdir(parents=True, exist_ok=True)

    def record(self, session: date) -> dict | None:
        p = self.root / "runs" / f"{session.isoformat()}.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None

    def processed(self) -> dict[str, dict]:
        out = {}
        for p in sorted((self.root / "runs").glob("????-??-??.json")):
            r = json.loads(p.read_text(encoding="utf-8"))
            if r.get("status") == "OK":
                out[r["session"]] = r
        return out

    def write_atomic(self, rel: str, payload: bytes) -> None:
        p = self.root / rel
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_bytes(payload)
        os.replace(tmp, p)

    def acquire_lock(self) -> None:
        p = self.root / "run.lock"
        try:
            fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if time.time() - p.stat().st_mtime < STALE_LOCK_SECONDS:
                raise Busy("another run holds the lock") from None
            p.unlink()                                                    # stale lock from a crashed run
            fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)

    def release_lock(self) -> None:
        (self.root / "run.lock").unlink(missing_ok=True)


# ------------------------------------------------------------------ run

def _default_fetcher(state: State) -> Callable[[date], tuple[Any, dict]]:
    def fetch(session: date):
        from acquisition.v2 import stage_r as sr
        from acquisition.v2.http import HttpClient
        inputs = pdata.fetch_inputs(session, HttpClient(*sr._credentials()))
        data, extra = pdata.build_market_data(inputs, FIRST_SESSION)
        ref = pdata.snapshot(state.root, inputs, extra["events"])
        return data, {**extra["info"], "input_manifest_sha256": ref}
    return fetch


def run(now: datetime | None = None, *, state: State | None = None, fetch: Callable | None = None,
        adoption_check: Callable[[], dict] | None = None, key: bytes | None = None, code_version: str = "") -> dict:
    now = now or datetime.now(timezone.utc)
    state = state or State()
    state.acquire_lock()
    try:
        (adoption_check or check_adoption_23)()
        config_sha = fw.check_config_sha()
        fw.check_quarantine()
        pdata.check_endpoints()
        key = key if key is not None else ps.load_key()
        target = latest_completed_session(now)
        if target is None or target < FIRST_SESSION:
            raise NotReady(f"no completed session of {EXPERIMENT_ID} yet (first session {FIRST_SESSION})")
        done = state.processed()
        todo = [d for d in pdata.sessions_between(FIRST_SESSION, target) if d.isoformat() not in done]
        if not todo:
            out = {"status": "NOOP", "target": target.isoformat(), "processed_total": len(done)}
            state.write_atomic("heartbeat.json", json.dumps({"last_run_utc": now.isoformat(), **out}, indent=1).encode())
            return out
        data, info = (fetch or _default_fetcher(state))(target)
        if data.sessions[-1] != target:
            raise pdata.DataFailClosed(f"stale data: last session {data.sessions[-1]} != {target}")
        first_idx = data.index_of(FIRST_SESSION)
        for iso, rec in done.items():                                   # consistency of every processed session
            d = date.fromisoformat(iso)
            res = pl.replay(data, first_idx, data.index_of(d))
            if pl.ledger_sha256(pl.session_ledger(data, res, d, rec["input_manifest_sha256"], config_sha)) != rec["ledger_sha256"]:
                raise InconsistentState(f"replay of processed session {iso} no longer matches its stored ledger")
        written = []
        for d in todo:
            res = pl.replay(data, first_idx, data.index_of(d))
            pl.check_risk(data, res)
            led = pl.session_ledger(data, res, d, info["input_manifest_sha256"], config_sha)
            blob = ps.seal(pl.canonical(led), key)
            state.write_atomic(f"sealed/{d.isoformat()}.bin", blob)
            close = _calendar(d).closes[d.isoformat()].tz_convert(MARKET_TZ).to_pydatetime()
            rec = {"experiment": EXPERIMENT_ID, "session": d.isoformat(), "status": "OK",
                   "processed_utc": now.astimezone(timezone.utc).isoformat(),
                   "late": now > ready_time(close) + LATE_AFTER, "input_manifest_sha256": info["input_manifest_sha256"],
                   "ledger_sha256": pl.ledger_sha256(led), "sealed_file_sha256": hashlib.sha256(blob).hexdigest(),
                   "strategy_config_sha256": config_sha, "data_sessions": info.get("sessions"),
                   "missing_bars": info.get("missing_bars"), "events_used": info.get("events_used"),
                   "review_pending_count": len(info.get("review_pending", [])), "code_version": code_version}
            state.write_atomic(f"runs/{d.isoformat()}.json", json.dumps(rec, indent=1, sort_keys=True).encode())  # commit point
            written.append(d.isoformat())
        out = {"status": "OK", "target": target.isoformat(), "processed_now": written, "processed_total": len(done) + len(written)}
        state.write_atomic("heartbeat.json", json.dumps({"last_run_utc": now.isoformat(), **out}, indent=1).encode())
        return out
    except Exception as e:
        err = {"utc": now.astimezone(timezone.utc).isoformat(), "code": getattr(e, "code", type(e).__name__),
               "message": _redact(str(e))}
        if not isinstance(e, (NotReady, Busy)):
            state.write_atomic("last_error.json", json.dumps(err, indent=1).encode())
        raise
    finally:
        state.release_lock()                                            # acquire_lock raised Busy before this try


# ------------------------------------------------------------------ inspection

def status(state: State | None = None) -> dict:
    state = state or State()
    done = state.processed()
    err_p = state.root / "last_error.json"
    last = max(done) if done else None
    return {"experiment": EXPERIMENT_ID, "sealed_until": SEAL_UNTIL.isoformat(), "processed_sessions": len(done),
            "last_processed_session": last, "late_sessions": sorted(s for s, r in done.items() if r.get("late")),
            "review_pending_sessions": sorted(s for s, r in done.items() if r.get("review_pending_count")),
            "last_error": json.loads(err_p.read_text(encoding="utf-8")) if err_p.is_file() else None,
            "recent": [{k: done[s].get(k) for k in ("session", "processed_utc", "late", "missing_bars")}
                       for s in sorted(done)[-5:]]}


def check_health(now: datetime | None = None, state: State | None = None) -> tuple[bool, str]:
    now = now or datetime.now(timezone.utc)
    state = state or State()
    expected = latest_completed_session(now)
    if expected is None or expected < FIRST_SESSION:
        return True, "experiment not started yet"
    done = state.processed()
    missing = [d.isoformat() for d in pdata.sessions_between(FIRST_SESSION, expected) if d.isoformat() not in done]
    err_p, hb_p = state.root / "last_error.json", state.root / "heartbeat.json"
    if err_p.is_file():
        err = json.loads(err_p.read_text(encoding="utf-8"))
        last_ok = max((r["processed_utc"] for r in done.values()), default="")
        if hb_p.is_file():                                              # a later successful run (OK or NOOP) clears it
            hb = json.loads(hb_p.read_text(encoding="utf-8")).get("last_run_utc", "")
            last_ok = max(last_ok, datetime.fromisoformat(hb).astimezone(timezone.utc).isoformat() if hb else "")
        if err["utc"] > last_ok:
            return False, f"last run failed: {err['code']}"
    if missing:
        return False, f"missed sessions: {missing}"
    return True, f"healthy through {expected.isoformat()}"


def reveal(session: date | None = None, *, now: datetime | None = None, state: State | None = None,
           key: bytes | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if now < SEAL_UNTIL:
        raise ps.SealError(f"sealed until {SEAL_UNTIL.isoformat()} (protocol 2.3 E7); refusing to reveal")
    state = state or State()
    done = state.processed()
    iso = session.isoformat() if session else max(done)
    blob = (state.root / "sealed" / f"{iso}.bin").read_bytes()
    led = json.loads(ps.unseal(blob, key if key is not None else ps.load_key(), now))
    if pl.ledger_sha256(led) != done[iso]["ledger_sha256"]:
        raise InconsistentState("sealed ledger does not match its health record")
    return led


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("run", "status", "check-health", "reveal", "init-key"))
    ap.add_argument("--now", help="ISO timestamp (testing / replay only)")
    ap.add_argument("--session")
    a = ap.parse_args(argv)
    try:
        if a.now and a.command in ("run", "reveal"):                    # the wall clock is authoritative for the seal
            raise RunnerError(f"--now is not accepted for {a.command} (time lock / processing timestamps)")
        now = datetime.fromisoformat(a.now) if a.now else None
        load_env()
        if a.command == "init-key":
            print(ps.new_key_hex())
            return 0
        if a.command == "run":
            print(json.dumps(run(now, code_version=os.environ.get("GITHUB_SHA", "")), indent=1))
            return 0
        if a.command == "status":
            print(json.dumps(status(), indent=1))
            return 0
        if a.command == "check-health":
            ok, msg = check_health(now)
            print(("HEALTHY: " if ok else "UNHEALTHY: ") + msg)
            return 0 if ok else 1
        print(json.dumps(reveal(date.fromisoformat(a.session) if a.session else None, now=now), indent=1))
        return 0
    except NotReady as e:
        print(f"NOT_READY: {e}")
        return 0
    except Exception as e:                                               # noqa: BLE001 - fail closed, redacted
        print(f"FAILED ({getattr(e, 'code', type(e).__name__)}): {_redact(str(e))}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
