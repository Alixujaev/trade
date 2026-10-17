"""tests/test_akinda_sync.py: Akinda /compliance client + sync CLI (mocked HTTP only; no network, no real API key).

Every HTTP call goes through an injected fake `get`; tests/conftest.py additionally blocks real sockets.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from acquisition.akinda import client as ac
from acquisition.akinda import sync as asy
from acquisition.akinda.contract import BASE_URL, DAILY_CALL_LIMIT, MAX_ATTEMPTS_PER_TICKER
from screening.eligibility import load_registry

FAKE_API_KEY = "fake-akinda-key-for-tests-only"
NOW = datetime(2026, 10, 19, 19, 0, tzinfo=timezone.utc)                  # 15:00 New York -> retrieved_on 2026-10-19


class Resp:
    def __init__(self, status: int, body):
        self.status_code = status
        self.content = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.headers = {}

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", "replace")


def ok(ticker, status="HALAL", scanned="Aug 06, 2026"):
    return Resp(200, {"company_name": "Synthetic", "halal_status": status, "last_scanned": scanned,
                      "last_updated": "Oct 16, 2026", "listing_country": "US", "reporting_currency": "USD",
                      "ticker": ticker})


class FakeGet:
    """Scripted responses per ticker (list consumed in order); records every call."""

    def __init__(self, script: dict[str, list]):
        self.script = {k: list(v) for k, v in script.items()}
        self.calls: list[dict] = []

    def __call__(self, url, *, headers, timeout, allow_redirects=True):
        self.calls.append({"url": url, "headers": dict(headers), "timeout": timeout,
                           "allow_redirects": allow_redirects})
        nxt = self.script[url.rsplit("/", 1)[1]].pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


def run(tmp_path, tickers, get, *, key=FAKE_API_KEY, valid_days=30, now=NOW):
    return asy.run_sync(tickers, valid_days=valid_days, out_root=tmp_path / "ev", api_key=key, get=get,
                        sleep=lambda _s: None, now=lambda: now)


def summary_of(tmp_path) -> dict:
    (run_dir,) = (tmp_path / "ev" / "runs").iterdir()
    return json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))


def all_written_text(root: Path) -> str:
    return "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in root.rglob("*") if p.is_file())


# ------------------------------------------------------------------ happy path and evidence

def test_halal_run_writes_validated_proposed_registry_and_evidence(tmp_path):
    get = FakeGet({"AAA": [ok("AAA")], "BBB": [ok("BBB", "NOT HALAL")]})
    code, summary = run(tmp_path, ["AAA", "BBB"], get)
    assert code == 0
    s = summary_of(tmp_path)
    assert s["provider"] == "Akinda B2B API v1" and s["methodology"] == "AKINDA_COMPLIANCE_API_V1"
    assert s["registry_validation"] == "ok" and s["stopped"] is None
    t = s["tickers"]["AAA"]
    assert t["http_status"] == 200 and t["halal_status_raw"] == "HALAL"
    assert t["last_scanned_raw"] == "Aug 06, 2026" and t["last_updated_raw"] == "Oct 16, 2026"
    assert t["retrieved_utc"].startswith("2026-10-19T19:00") and len(t["body_sha256"]) == 64
    run_dir = next((tmp_path / "ev" / "runs").iterdir())
    reg = load_registry(run_dir / "proposed.csv")                         # production defaults
    assert reg.decide("AAA", NOW.date()).tradable
    assert not reg.decide("BBB", NOW.date()).tradable
    assert (run_dir / "AAA.body").read_bytes() == ok("AAA").content


def test_key_goes_only_in_the_x_api_key_header(tmp_path):
    get = FakeGet({"AAA": [ok("AAA")]})
    run(tmp_path, ["AAA"], get)
    (call,) = get.calls
    assert call["url"] == f"{BASE_URL}/compliance/AAA"
    assert call["headers"]["X-API-Key"] == FAKE_API_KEY and FAKE_API_KEY not in call["url"]
    assert call["timeout"] > 0


def test_redirects_are_never_followed(tmp_path):
    get = FakeGet({"AAA": [ok("AAA")]})
    run(tmp_path, ["AAA"], get)
    assert get.calls[0]["allow_redirects"] is False                      # key header must not reach another host


@pytest.mark.parametrize("status", [301, 302, 307, 308])
def test_redirect_response_is_not_followed_and_creates_no_record(tmp_path, status):
    redirect = Resp(status, b"")
    redirect.headers = {"Location": "https://elsewhere.example/compliance/AAA"}
    get = FakeGet({"AAA": [redirect], "BBB": [ok("BBB")]})
    assert run(tmp_path, ["AAA", "BBB"], get)[0] == 0
    assert [c["url"].rsplit("/", 1)[1] for c in get.calls] == ["AAA", "BBB"]   # one call each, no follow-up
    t = summary_of(tmp_path)["tickers"]["AAA"]
    assert t["http_status"] == status and t["outcome"] == "no_record"
    run_dir = next((tmp_path / "ev" / "runs").iterdir())
    assert "AAA" not in load_registry(run_dir / "proposed.csv").records


# ------------------------------------------------------------------ configuration failures before any request

def test_missing_api_key_fails_before_any_request(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("AKINDA_API_KEY", raising=False)
    get = FakeGet({})
    env = tmp_path / "empty.env"
    env.write_text("", encoding="utf-8")
    code = asy.main(["--tickers", "AAA", "--valid-days", "30", "--out", str(tmp_path / "ev"),
                     "--env-file", str(env)], get=get)
    assert code == 2 and get.calls == []
    assert "AKINDA_API_KEY" in capsys.readouterr().out
    assert not (tmp_path / "ev" / "usage.jsonl").exists()


def test_api_key_is_read_from_env_file_without_exporting_it(tmp_path, monkeypatch):
    monkeypatch.delenv("AKINDA_API_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text(f"AKINDA_API_KEY={FAKE_API_KEY}\n", encoding="utf-8")
    assert asy.load_api_key(env) == FAKE_API_KEY
    import os
    assert "AKINDA_API_KEY" not in os.environ


@pytest.mark.parametrize("tickers, why", [
    ([], "at least one ticker"),
    ([f"T{i}" for i in range(DAILY_CALL_LIMIT + 1)], "at most"),
    (["AAA", "aaa"], "duplicate"),
    (["AA/A"], "invalid ticker"),
    (["../x"], "invalid ticker"),
])
def test_ticker_list_must_be_explicit_small_unique_and_safe(tmp_path, tickers, why):
    get = FakeGet({})
    with pytest.raises(ValueError, match=why):
        run(tmp_path, tickers, get)
    assert get.calls == []


@pytest.mark.parametrize("sub", ["data", "artifacts", "paper_state"])
def test_evidence_may_not_be_written_into_protected_paths(sub):
    with pytest.raises(ValueError, match="protected"):
        asy.run_sync(["AAA"], valid_days=30, out_root=asy.ROOT_DIR / sub / "akinda", api_key=FAKE_API_KEY,
                     get=FakeGet({}), sleep=lambda _s: None, now=lambda: NOW)


# ------------------------------------------------------------------ HTTP errors

@pytest.mark.parametrize("status", [401, 403])
def test_auth_or_plan_failure_stops_the_batch_without_retry(tmp_path, status):
    get = FakeGet({"AAA": [Resp(status, {"error": "nope"})], "BBB": [ok("BBB")]})
    code, _ = run(tmp_path, ["AAA", "BBB"], get)
    assert code == 3 and len(get.calls) == 1
    s = summary_of(tmp_path)
    assert s["stopped"]["kind"] == "auth" and "BBB" not in s["tickers"]


def test_429_stops_the_batch_immediately(tmp_path):
    get = FakeGet({"AAA": [ok("AAA")], "BBB": [Resp(429, {"error": "quota"})], "CCC": [ok("CCC")]})
    code, _ = run(tmp_path, ["AAA", "BBB", "CCC"], get)
    assert code == 3 and [c["url"].rsplit("/", 1)[1] for c in get.calls] == ["AAA", "BBB"]
    s = summary_of(tmp_path)
    assert s["stopped"]["kind"] == "rate_limited" and "CCC" not in s["tickers"]
    run_dir = next((tmp_path / "ev" / "runs").iterdir())
    assert load_registry(run_dir / "proposed.csv").decide("AAA", NOW.date()).tradable    # partial work kept


def test_server_errors_are_retried_a_bounded_number_of_times(tmp_path):
    get = FakeGet({"AAA": [Resp(503, b"busy")] * MAX_ATTEMPTS_PER_TICKER, "BBB": [Resp(500, b"x"), ok("BBB")]})
    code, _ = run(tmp_path, ["AAA", "BBB"], get)
    assert code == 0
    assert len(get.calls) == MAX_ATTEMPTS_PER_TICKER + 2
    s = summary_of(tmp_path)
    assert s["tickers"]["AAA"]["outcome"] == "no_record" and "attempts exhausted" in s["tickers"]["AAA"]["diagnostic"]
    assert s["tickers"]["BBB"]["outcome"] == "record"


def test_network_error_is_retried_then_succeeds(tmp_path):
    get = FakeGet({"AAA": [TimeoutError("timed out"), ok("AAA")]})
    assert run(tmp_path, ["AAA"], get)[0] == 0
    assert summary_of(tmp_path)["tickers"]["AAA"]["outcome"] == "record"


def test_not_covered_ticker_gets_no_record_and_batch_continues(tmp_path):
    get = FakeGet({"AAA": [Resp(404, {"error": "not_found"})], "BBB": [ok("BBB")]})
    assert run(tmp_path, ["AAA", "BBB"], get)[0] == 0
    s = summary_of(tmp_path)
    assert s["tickers"]["AAA"]["outcome"] == "no_record" and s["tickers"]["BBB"]["outcome"] == "record"
    run_dir = next((tmp_path / "ev" / "runs").iterdir())
    assert "AAA" not in load_registry(run_dir / "proposed.csv").records


def test_malformed_body_gets_no_record_but_keeps_evidence(tmp_path):
    get = FakeGet({"AAA": [Resp(200, b"<html>not json</html>")]})
    assert run(tmp_path, ["AAA"], get)[0] == 0
    t = summary_of(tmp_path)["tickers"]["AAA"]
    assert t["outcome"] == "no_record" and "not valid JSON" in t["diagnostic"]
    assert len(t["body_sha256"]) == 64


# ------------------------------------------------------------------ daily quota

def _seed_usage(tmp_path, n, *, age=timedelta(hours=1)):
    p = tmp_path / "ev" / "usage.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps({"utc": (NOW - age).isoformat(), "ticker": "OLD"}) + "\n" for _ in range(n)),
                 encoding="utf-8")


def test_run_larger_than_remaining_daily_budget_is_refused_up_front(tmp_path):
    _seed_usage(tmp_path, DAILY_CALL_LIMIT - 1)
    get = FakeGet({"AAA": [ok("AAA")], "BBB": [ok("BBB")]})
    with pytest.raises(ValueError, match="daily call budget"):
        run(tmp_path, ["AAA", "BBB"], get)
    assert get.calls == []


def test_usage_older_than_24_hours_does_not_count(tmp_path):
    _seed_usage(tmp_path, DAILY_CALL_LIMIT, age=timedelta(hours=24, seconds=1))
    assert run(tmp_path, ["AAA"], FakeGet({"AAA": [ok("AAA")]}))[0] == 0


def test_retries_count_against_the_budget_and_stop_the_batch(tmp_path):
    _seed_usage(tmp_path, DAILY_CALL_LIMIT - 1)
    get = FakeGet({"AAA": [Resp(503, b"busy"), ok("AAA")]})
    code, _ = run(tmp_path, ["AAA"], get)
    assert code == 3 and len(get.calls) == 1
    assert summary_of(tmp_path)["stopped"]["kind"] == "quota"


def test_every_attempt_is_recorded_before_it_is_sent(tmp_path):
    get = FakeGet({"AAA": [Resp(500, b"x"), ok("AAA")]})
    run(tmp_path, ["AAA"], get)
    lines = (tmp_path / "ev" / "usage.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(x)["ticker"] for x in lines] == ["AAA", "AAA"]


def test_corrupt_usage_ledger_fails_closed(tmp_path):
    p = tmp_path / "ev" / "usage.jsonl"
    p.parent.mkdir(parents=True)
    p.write_text("not json\n", encoding="utf-8")
    get = FakeGet({"AAA": [ok("AAA")]})
    with pytest.raises(ValueError, match="usage ledger"):
        run(tmp_path, ["AAA"], get)
    assert get.calls == []


def test_timezone_naive_ledger_timestamp_fails_closed(tmp_path, capsys, monkeypatch):
    p = tmp_path / "ev" / "usage.jsonl"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"utc": "2026-10-19T18:00:00", "ticker": "OLD"}) + "\n", encoding="utf-8")
    get = FakeGet({"AAA": [ok("AAA")]})
    with pytest.raises(ValueError, match="usage ledger .* line 1 is unreadable"):
        run(tmp_path, ["AAA"], get)
    monkeypatch.setenv("AKINDA_API_KEY", FAKE_API_KEY)
    code = asy.main(["--tickers", "AAA", "--valid-days", "30", "--out", str(tmp_path / "ev"),
                     "--env-file", str(tmp_path / "none.env")], get=get, now=lambda: NOW)
    assert code == 2 and get.calls == []
    out = capsys.readouterr().out
    assert "REFUSED" in out and "usage ledger" in out and FAKE_API_KEY not in out


# ------------------------------------------------------------------ secrets and write-once

def test_secret_never_reaches_disk_or_stdout(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("AKINDA_API_KEY", FAKE_API_KEY)
    get = FakeGet({"AAA": [Resp(500, f"echo key={FAKE_API_KEY}".encode())] * MAX_ATTEMPTS_PER_TICKER,
                   "BBB": [Resp(401, f"bad key {FAKE_API_KEY}".encode())]})
    code = asy.main(["--tickers", "AAA", "BBB", "--valid-days", "30", "--out", str(tmp_path / "ev"),
                     "--env-file", str(tmp_path / "none.env")], get=get, sleep=lambda _s: None, now=lambda: NOW)
    assert code == 3
    out = capsys.readouterr().out
    assert FAKE_API_KEY not in out
    assert FAKE_API_KEY not in all_written_text(tmp_path / "ev")                  # bodies are stored with the key redacted
    assert FAKE_API_KEY not in json.dumps(summary_of(tmp_path))


def test_redact_helper_removes_the_key():
    assert ac.redact(f"a {FAKE_API_KEY} b", FAKE_API_KEY) == "a *** b"


def test_run_directory_is_write_once(tmp_path):
    run(tmp_path, ["AAA"], FakeGet({"AAA": [ok("AAA")]}))
    with pytest.raises(FileExistsError):
        run(tmp_path, ["BBB"], FakeGet({"BBB": [ok("BBB")]}))           # same `now` -> same run id
