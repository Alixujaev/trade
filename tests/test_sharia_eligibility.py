"""tests/test_sharia_eligibility.py: fail-closed Sharia eligibility registry (screening/eligibility.py).

Offline and synthetic: registries are written to tmp_path with fictitious tickers (AAA, BBB) and the test
methodology TEST_METHOD, so no test states that any real ticker is Sharia-compliant. The committed seed registry
(config/sharia_eligibility.csv) must make zero tickers tradable.
"""

from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

import pytest

from config.core_watchlist import CORE_WATCHLIST
from config.day_universe import FROZEN_DAY_UNIVERSE
from config.tactical_watchlist import HLAL_HOLDINGS
from screening import eligibility as el
from screening.eligibility import (
    DEFAULT_REGISTRY_PATH,
    REQUIRED_COLUMNS,
    Eligibility,
    EligibilityError,
    RecordStatus,
    load_registry,
)

ROOT = Path(__file__).resolve().parent.parent
TEST_METHODS = frozenset({"TEST_METHOD"})
BASE = dict(symbol="AAA", status="NON_COMPLIANT", valid_from="2026-01-01", valid_until="2026-03-31",
            methodology="TEST_METHOD", source="Synthetic test screen", source_ref="doc-1",
            source_date="2025-12-31", reviewer="tester", reviewed_on="2026-01-05", note="synthetic fixture")
SEED_DAYS = (date(2016, 1, 4), date(2026, 6, 2), date(2026, 10, 12), date(2026, 12, 9), date(2027, 1, 7))


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    def refuse(*_a, **_k):
        raise AssertionError("network access attempted in a Sharia eligibility test")
    monkeypatch.setattr(socket.socket, "connect", refuse)


def row(**kw) -> dict[str, str]:
    return {**BASE, **kw}


def write_csv(tmp_path: Path, rows: list[dict[str, str]], *, header: tuple[str, ...] = REQUIRED_COLUMNS,
              name: str = "reg.csv", newline: str = "\n", bom: bool = False) -> Path:
    lines = [",".join(header)] + [",".join(r.get(c, "") for c in header) for r in rows]
    p = tmp_path / name
    p.write_bytes((b"\xef\xbb\xbf" if bom else b"") + (newline.join(lines) + newline).encode("utf-8"))
    return p


def load_rows(tmp_path: Path, *rows: dict[str, str], accepted: frozenset[str] = el.ACCEPTED_METHODOLOGIES):
    return load_registry(write_csv(tmp_path, list(rows)), accepted_methodologies=accepted)


# ------------------------------------------------------------------ loader fails closed

def test_missing_file(tmp_path):
    with pytest.raises(EligibilityError, match="registry not found"):
        load_registry(tmp_path / "nope.csv")


def test_empty_file_has_no_header(tmp_path):
    p = tmp_path / "empty.csv"
    p.write_bytes(b"")
    with pytest.raises(EligibilityError, match="no header"):
        load_registry(p)


def test_missing_extra_and_duplicate_columns(tmp_path):
    with pytest.raises(EligibilityError, match="missing columns"):
        load_registry(write_csv(tmp_path, [], header=REQUIRED_COLUMNS[:-1]))
    with pytest.raises(EligibilityError, match="unknown columns"):
        load_registry(write_csv(tmp_path, [], header=REQUIRED_COLUMNS + ("valid_untill",)))
    with pytest.raises(EligibilityError, match="duplicate column"):
        load_registry(write_csv(tmp_path, [], header=REQUIRED_COLUMNS + ("note",)))


def test_wrong_field_count_and_blank_line(tmp_path):
    p = tmp_path / "short.csv"
    p.write_text(",".join(REQUIRED_COLUMNS) + "\nAAA,NON_COMPLIANT\n", encoding="utf-8")
    with pytest.raises(EligibilityError, match="line 2: expected 11 fields"):
        load_registry(p)
    blank = tmp_path / "blank.csv"
    blank.write_text(",".join(REQUIRED_COLUMNS) + "\n\n", encoding="utf-8")
    with pytest.raises(EligibilityError, match="expected 11 fields"):
        load_registry(blank)


@pytest.mark.parametrize("symbol, match", [("", "empty symbol"), ("aaa", "not normalised"),
                                           (" AAA", "not normalised")])
def test_symbol_must_be_present_and_normalised(tmp_path, symbol, match):
    with pytest.raises(EligibilityError, match=match):
        load_rows(tmp_path, row(symbol=symbol))


@pytest.mark.parametrize("status", ["compliant", "HALAL", "", "UNKNOWN"])
def test_invalid_status(tmp_path, status):
    with pytest.raises(EligibilityError, match="invalid status"):
        load_rows(tmp_path, row(status=status))


@pytest.mark.parametrize("field", ["valid_from", "valid_until", "reviewed_on", "source_date"])
@pytest.mark.parametrize("value", ["2026-02-30", "20260101", "2026/01/01", "soon"])
def test_invalid_dates(tmp_path, field, value):
    with pytest.raises(EligibilityError, match=f"line 2: invalid {field}"):
        load_rows(tmp_path, row(**{field: value}))


def test_missing_required_dates_and_reviewer(tmp_path):
    for field in ("valid_from", "valid_until", "reviewed_on"):
        with pytest.raises(EligibilityError, match=f"invalid {field}"):
            load_rows(tmp_path, row(**{field: ""}))
    with pytest.raises(EligibilityError, match="empty reviewer"):
        load_rows(tmp_path, row(reviewer=""))


def test_window_order_and_max_validity(tmp_path):
    with pytest.raises(EligibilityError, match="valid_from after valid_until"):
        load_rows(tmp_path, row(valid_from="2026-02-01", valid_until="2026-01-31"))
    ok = load_rows(tmp_path, row(valid_from="2026-01-01", valid_until="2026-04-02"))      # 92 days inclusive
    assert ok.records["AAA"][0].valid_until == date(2026, 4, 2)
    with pytest.raises(EligibilityError, match="validity of 93 days exceeds 92"):
        load_rows(tmp_path, row(valid_from="2026-01-01", valid_until="2026-04-03"))


@pytest.mark.parametrize("status", ["COMPLIANT", "NON_COMPLIANT"])
@pytest.mark.parametrize("field", ["methodology", "source", "source_ref", "source_date"])
def test_unsourced_decided_rows_are_structural_errors(tmp_path, status, field):
    with pytest.raises(EligibilityError, match=f"{status} row requires {field}"):
        load_rows(tmp_path, row(status=status, **{field: ""}), accepted=TEST_METHODS)


def test_point_in_time_source_and_review_order(tmp_path):
    with pytest.raises(EligibilityError, match="look-ahead"):
        load_rows(tmp_path, row(source_date="2026-01-02"))
    with pytest.raises(EligibilityError, match="reviewed_on .* before source_date"):
        load_rows(tmp_path, row(reviewed_on="2025-12-30"))
    rec = load_rows(tmp_path, row(source_date="2026-01-01", reviewed_on="2026-01-01")).records["AAA"][0]
    assert rec.source_date == rec.valid_from == rec.reviewed_on == date(2026, 1, 1)


def test_compliant_requires_an_accepted_methodology(tmp_path):
    assert el.ACCEPTED_METHODOLOGIES == frozenset()
    with pytest.raises(EligibilityError, match="not an accepted methodology"):
        load_rows(tmp_path, row(status="COMPLIANT"))                              # default: empty accepted set
    with pytest.raises(EligibilityError, match="not an accepted methodology"):
        load_rows(tmp_path, row(status="COMPLIANT", methodology="OTHER"), accepted=TEST_METHODS)
    assert load_rows(tmp_path, row(status="COMPLIANT"), accepted=TEST_METHODS).records["AAA"][0].status \
        is RecordStatus.COMPLIANT


def test_non_compliant_methodology_need_not_be_accepted(tmp_path):
    rec = load_rows(tmp_path, row(methodology="ANY_SCREEN")).records["AAA"][0]
    assert rec.status is RecordStatus.NON_COMPLIANT and rec.methodology == "ANY_SCREEN"


def test_unverified_rows_need_no_provenance(tmp_path):
    rec = load_rows(tmp_path, row(status="UNVERIFIED", methodology="", source="", source_ref="",
                                  source_date="")).records["AAA"][0]
    assert rec.status is RecordStatus.UNVERIFIED and rec.source_date is None


def test_contradictory_records_fail_closed(tmp_path):
    with pytest.raises(EligibilityError, match="overlapping records for AAA: lines 2, 3"):
        load_rows(tmp_path, row(), row(status="UNVERIFIED", valid_from="2026-03-01", valid_until="2026-04-30"))
    with pytest.raises(EligibilityError, match="overlapping records for AAA"):
        load_rows(tmp_path, row(), row())                                           # identical duplicates
    with pytest.raises(EligibilityError, match="overlapping records for AAA"):     # one shared day
        load_rows(tmp_path, row(), row(valid_from="2026-03-31", valid_until="2026-04-30"))
    ok = load_rows(tmp_path, row(), row(valid_from="2026-04-01", valid_until="2026-04-30"))
    assert len(ok.records["AAA"]) == 2


def test_any_bad_row_rejects_the_whole_registry(tmp_path):
    with pytest.raises(EligibilityError, match="line 3"):
        load_rows(tmp_path, row(symbol="BBB"), row(status="bogus"))


def test_reverse_chronological_rows_sort_and_diagnose(tmp_path):
    april = row(valid_from="2026-04-01", valid_until="2026-04-30", source_date="2026-03-31", reviewed_on="2026-04-01")
    reg = load_rows(tmp_path, april, row())                                      # line 2 = April, line 3 = Jan-Mar
    assert [r.line for r in reg.records["AAA"]] == [3, 2]
    assert reg.decide("AAA", date(2026, 3, 15)).record.line == 3
    assert reg.decide("AAA", date(2026, 4, 15)).record.line == 2
    assert reg.decide("AAA", date(2025, 12, 31)).reason == "not_yet_valid"
    assert reg.decide("AAA", date(2026, 5, 1)).reason == "expired"
    with pytest.raises(EligibilityError, match="overlapping records for AAA: lines 3, 2"):
        load_rows(tmp_path, april, row(valid_from="2026-03-01", valid_until="2026-04-01"))
    with pytest.raises(EligibilityError, match="overlapping records for AAA: lines 2, 4"):
        load_rows(tmp_path, row(valid_until="2026-01-31"), row(valid_from="2026-03-01"),
                  row(valid_from="2026-01-15", valid_until="2026-02-10"))


# ------------------------------------------------------------------ source freshness (M1)

FRESH_92 = dict(valid_from="2026-04-03", valid_until="2026-04-30", source_date="2026-01-01", reviewed_on="2026-04-03")


def test_source_freshness_boundary(tmp_path):
    rec = load_rows(tmp_path, row(**FRESH_92)).records["AAA"][0]
    assert (rec.valid_from - rec.source_date).days == el.MAX_SOURCE_AGE_DAYS == 92
    with pytest.raises(EligibilityError, match="stale source: .* 93 days before valid_from"):
        load_rows(tmp_path, row(**{**FRESH_92, "source_date": "2025-12-31"}))


@pytest.mark.parametrize("status", ["COMPLIANT", "NON_COMPLIANT", "UNVERIFIED"])
def test_source_freshness_applies_to_every_status(tmp_path, status):
    stale = row(status=status, **{**FRESH_92, "source_date": "2025-12-31"})
    with pytest.raises(EligibilityError, match="stale source"):
        load_rows(tmp_path, stale, accepted=TEST_METHODS)
    assert load_rows(tmp_path, row(status=status, **FRESH_92), accepted=TEST_METHODS).records["AAA"][0].status.value \
        == status


def test_validity_window_and_source_freshness_are_independent(tmp_path):
    rec = load_rows(tmp_path, row(**{**FRESH_92, "valid_until": "2026-07-03"})).records["AAA"][0]  # 92 + 92 days
    assert (rec.valid_until - rec.valid_from).days + 1 == 92 and (rec.valid_from - rec.source_date).days == 92


def test_unverified_supplied_source_date_is_validated(tmp_path):
    unv = dict(status="UNVERIFIED", methodology="", source="", source_ref="")
    with pytest.raises(EligibilityError, match="line 2: invalid source_date"):
        load_rows(tmp_path, row(**unv, source_date="2026/01/01"))
    with pytest.raises(EligibilityError, match="look-ahead"):
        load_rows(tmp_path, row(**unv, source_date="2026-01-02"))
    with pytest.raises(EligibilityError, match="reviewed_on 2025-12-31 before source_date 2026-01-01"):
        load_rows(tmp_path, row(**unv, source_date="2026-01-01", reviewed_on="2025-12-31"))


# ------------------------------------------------------------------ allowlist argument (L1)

def test_accepted_methodologies_bare_string_is_rejected(tmp_path):
    p = write_csv(tmp_path, [row(status="COMPLIANT", methodology="A")])
    for bad in ("AAOIFI", b"AAOIFI"):
        with pytest.raises(TypeError, match="not a single string"):
            load_registry(p, accepted_methodologies=bad)                            # type: ignore[arg-type]


@pytest.mark.parametrize("bad, exc, match", [
    ({""}, EligibilityError, "empty or padded"),
    ({" TEST_METHOD "}, EligibilityError, "empty or padded"),
    ({"TEST_METHOD", 1}, TypeError, "must be str"),
    ([None], TypeError, "must be str"),
    (None, TypeError, "iterable"),
    (5, TypeError, "iterable"),
])
def test_accepted_methodologies_entries_are_validated(tmp_path, bad, exc, match):
    with pytest.raises(exc, match=match):
        load_registry(write_csv(tmp_path, []), accepted_methodologies=bad)


def test_allowlist_is_validated_before_the_file_is_read(tmp_path):
    with pytest.raises(TypeError, match="not a single string"):
        load_registry(tmp_path / "nope.csv", accepted_methodologies="TEST_METHOD")  # type: ignore[arg-type]


def test_allowlist_accepts_any_iterable_of_names_and_policy_is_unchanged(tmp_path):
    compliant = row(status="COMPLIANT")
    assert load_rows(tmp_path, compliant, accepted=["TEST_METHOD"]).records["AAA"][0].status \
        is RecordStatus.COMPLIANT                                                     # type: ignore[arg-type]
    with pytest.raises(EligibilityError, match="not an accepted methodology"):
        load_rows(tmp_path, compliant, accepted=("OTHER",))                          # type: ignore[arg-type]
    assert load_rows(tmp_path, row(methodology="UNLISTED"), accepted=frozenset()).records["AAA"][0].status \
        is RecordStatus.NON_COMPLIANT


# ------------------------------------------------------------------ Phase 2 safeguards (AAOIFI_MVP_DECISIONS.md)

DRAFT_METHOD = "AAOIFI_SS21_V1_DRAFT"


@pytest.mark.parametrize("bad", [DRAFT_METHOD, "aaoifi_ss21_v1_draft", "X_Draft_2", "DRAFT"])
def test_draft_methodology_can_never_be_accepted(tmp_path, bad):
    with pytest.raises(EligibilityError, match="draft methodology .* cannot be accepted"):
        load_registry(write_csv(tmp_path, []), accepted_methodologies=frozenset({bad}))
    with pytest.raises(EligibilityError, match="draft methodology"):                # refused before the file is read
        load_registry(tmp_path / "nope.csv", accepted_methodologies=frozenset({"TEST_METHOD", bad}))


def test_compliant_under_draft_methodology_is_impossible(tmp_path):
    p = write_csv(tmp_path, [row(status="COMPLIANT", methodology=DRAFT_METHOD)])
    with pytest.raises(EligibilityError, match="not an accepted methodology"):
        load_registry(p)
    with pytest.raises(EligibilityError, match="draft methodology"):
        load_registry(p, accepted_methodologies=frozenset({DRAFT_METHOD}))


def test_draft_methodology_may_label_non_tradable_rows(tmp_path):
    reg = load_rows(tmp_path,
                    row(methodology=DRAFT_METHOD),
                    row(symbol="BBB", status="UNVERIFIED", methodology=DRAFT_METHOD, source="", source_ref="",
                        source_date="", note="interest-bearing debt not classifiable (D7)"))
    for sym in ("AAA", "BBB"):
        d = reg.decide(sym, date(2026, 2, 2))
        assert d.record.methodology == DRAFT_METHOD and not d.tradable


@pytest.mark.parametrize("note", ["", "   "])
def test_unverified_row_requires_a_reason_note(tmp_path, note):
    unv = row(status="UNVERIFIED", methodology="", source="", source_ref="", source_date="", note=note)
    with pytest.raises(EligibilityError, match="line 2: UNVERIFIED row requires a note"):
        load_rows(tmp_path, unv)


def test_unverified_reason_is_preserved_and_never_tradable(tmp_path):
    reason = "market-cap price source unlicensed (D1); fundamentals missing (D14)"
    reg = load_rows(tmp_path, row(status="UNVERIFIED", methodology="", source="", source_ref="", source_date="",
                                  note=reason), accepted=TEST_METHODS)
    d = reg.decide("AAA", date(2026, 2, 2))
    assert (d.status, d.reason, d.record.note, d.tradable) == \
        (Eligibility.UNVERIFIED, "recorded_unverified", reason, False)


@pytest.mark.parametrize("status", ["COMPLIANT", "NON_COMPLIANT"])
def test_decided_rows_may_still_have_an_empty_note(tmp_path, status):
    rec = load_rows(tmp_path, row(status=status, note=""), accepted=TEST_METHODS).records["AAA"][0]
    assert rec.status.value == status and rec.note == ""


def test_module_allowlist_is_still_empty():
    assert el.ACCEPTED_METHODOLOGIES == frozenset()


# ------------------------------------------------------------------ CSV parse errors and encodings (L2)

def test_csv_parse_error_fails_closed_with_chaining(tmp_path):
    p = write_csv(tmp_path, [row(symbol="BBB"), row(note="x" * (csv.field_size_limit() + 1))])
    with pytest.raises(EligibilityError, match="line 3: CSV parse error") as info:
        load_registry(p)
    assert isinstance(info.value.__cause__, csv.Error)


def test_invalid_utf8_fails_closed(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_bytes(",".join(REQUIRED_COLUMNS).encode("utf-8") + b"\nAAA,\xff\xfe\n")
    with pytest.raises(EligibilityError, match="not valid UTF-8"):
        load_registry(p)


def test_quoted_values_with_commas_load_correctly(tmp_path):
    r = row(source="Example Screen, Inc.", source_ref="doc-1, section 2", note='says "a, b"')
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(REQUIRED_COLUMNS)
    w.writerow([r[c] for c in REQUIRED_COLUMNS])
    p = tmp_path / "quoted.csv"
    p.write_bytes(buf.getvalue().encode("utf-8"))
    assert b'"Example Screen, Inc."' in p.read_bytes()
    rec = load_registry(p).records["AAA"][0]
    assert (rec.source, rec.source_ref, rec.note, rec.line) == ("Example Screen, Inc.", "doc-1, section 2",
                                                                'says "a, b"', 2)


# ------------------------------------------------------------------ accepted inputs

def test_header_only_registry_is_empty(tmp_path):
    reg = load_registry(write_csv(tmp_path, []))
    assert dict(reg.records) == {}
    assert reg.decide("AAA", date(2026, 1, 2)).status is Eligibility.UNKNOWN


def test_crlf_and_bom_load_identically_with_equal_sha(tmp_path):
    rows = [row(), row(symbol="BBB", status="UNVERIFIED", note="ETF membership only - not evidence")]
    regs = [load_registry(write_csv(tmp_path, rows, name=f"r{i}.csv", newline=nl, bom=bom))
            for i, (nl, bom) in enumerate((("\n", False), ("\r\n", False), ("\r\n", True)))]
    assert regs[0].records == regs[1].records == regs[2].records
    assert regs[0].source_sha256 == regs[1].source_sha256 == regs[2].source_sha256
    lf = (",".join(REQUIRED_COLUMNS) + "\n" + "\n".join(",".join(r[c] for c in REQUIRED_COLUMNS) for r in rows)
          + "\n").encode("utf-8")
    assert regs[0].source_sha256 == hashlib.sha256(lf).hexdigest()


def test_records_are_read_only(tmp_path):
    reg = load_rows(tmp_path, row())
    with pytest.raises(TypeError):
        reg.records["BBB"] = ()                                                     # type: ignore[index]


# ------------------------------------------------------------------ decisions

@pytest.fixture
def registry(tmp_path):
    return load_rows(
        tmp_path,
        row(),                                                                         # AAA NON_COMPLIANT Jan-Mar
        row(status="UNVERIFIED", valid_from="2026-04-10", valid_until="2026-05-10",   # gap 04-01..04-09
            methodology="", source="", source_ref="", source_date=""),
        row(symbol="BBB", status="COMPLIANT", valid_from="2026-02-01", valid_until="2026-02-28"),
        accepted=TEST_METHODS,
    )


def test_unknown_symbol(registry):
    d = registry.decide("ZZZ", date(2026, 2, 2))
    assert (d.status, d.reason, d.record, d.tradable) == (Eligibility.UNKNOWN, "no_record", None, False)


@pytest.mark.parametrize("day, status, reason", [
    (date(2025, 12, 31), Eligibility.UNKNOWN, "not_yet_valid"),
    (date(2026, 1, 1), Eligibility.NON_COMPLIANT, "recorded_non_compliant"),
    (date(2026, 3, 31), Eligibility.NON_COMPLIANT, "recorded_non_compliant"),
    (date(2026, 4, 1), Eligibility.UNKNOWN, "expired"),                               # gap
    (date(2026, 4, 9), Eligibility.UNKNOWN, "expired"),
    (date(2026, 4, 10), Eligibility.UNVERIFIED, "recorded_unverified"),
    (date(2026, 5, 10), Eligibility.UNVERIFIED, "recorded_unverified"),
    (date(2026, 5, 11), Eligibility.UNKNOWN, "expired"),
])
def test_window_boundaries(registry, day, status, reason):
    d = registry.decide("AAA", day)
    assert (d.status, d.reason, d.tradable) == (status, reason, False)
    assert (d.record is None) == (status is Eligibility.UNKNOWN)


def test_compliant_is_tradable_only_inside_its_window(registry):
    start, end = date(2026, 2, 1), date(2026, 2, 28)
    day = date(2026, 1, 1)
    while day <= date(2026, 3, 31):
        d = registry.decide("BBB", day)
        assert d.tradable == (start <= day <= end) == registry.is_tradable("BBB", day)
        assert d.reason == ("recorded_compliant" if d.tradable else ("not_yet_valid" if day < start else "expired"))
        day += timedelta(days=1)


def test_query_symbol_is_normalised_and_empty_is_rejected(registry):
    assert registry.decide(" bbb ", date(2026, 2, 2)).symbol == "BBB"
    assert registry.is_tradable("bbb", date(2026, 2, 2))
    with pytest.raises(EligibilityError, match="empty symbol"):
        registry.decide("  ", date(2026, 2, 2))


def test_query_day_must_be_a_date(registry):
    with pytest.raises(TypeError, match="datetime.date"):
        registry.decide("AAA", datetime(2026, 2, 2, 10, 0))
    with pytest.raises(TypeError, match="datetime.date"):
        registry.decide("AAA", "2026-02-02")                                            # type: ignore[arg-type]


# ------------------------------------------------------------------ filter_universe

def test_filter_universe_order_and_reasons(registry):
    tradable, decisions = registry.filter_universe(["ZZZ", "BBB", "aaa"], date(2026, 2, 2))
    assert tradable == ("BBB",)
    assert list(decisions) == ["ZZZ", "BBB", "AAA"]
    assert {s: d.reason for s, d in decisions.items()} == {
        "ZZZ": "no_record", "BBB": "recorded_compliant", "AAA": "recorded_non_compliant"}


def test_filter_universe_rejects_duplicates_bad_day_and_bare_string(registry):
    with pytest.raises(EligibilityError, match="duplicate symbol in universe: AAA"):
        registry.filter_universe(["AAA", "aaa"], date(2026, 2, 2))
    with pytest.raises(TypeError):
        registry.filter_universe(["AAA"], datetime(2026, 2, 2))
    with pytest.raises(TypeError):
        registry.filter_universe("AAA", date(2026, 2, 2))


# ------------------------------------------------------------------ committed seed: zero tradable

def test_seed_registry_is_header_only():
    lines = DEFAULT_REGISTRY_PATH.read_bytes().replace(b"\r\n", b"\n").decode("utf-8").splitlines()
    assert lines == [",".join(REQUIRED_COLUMNS)]
    assert dict(load_registry().records) == {}


@pytest.mark.parametrize("name, symbols", [
    ("FROZEN_DAY_UNIVERSE", list(FROZEN_DAY_UNIVERSE)),
    ("HLAL_HOLDINGS", list(dict.fromkeys(t.strip().upper() for t, _ in HLAL_HOLDINGS))),
    ("CORE_WATCHLIST", list(dict.fromkeys(h.ticker.strip().upper() for h in CORE_WATCHLIST))),
])
def test_seed_registry_makes_zero_tickers_tradable(name, symbols):
    reg = load_registry()
    assert symbols, name
    for day in SEED_DAYS:
        tradable, decisions = reg.filter_universe(symbols, day)
        assert tradable == (), (name, day)
        assert {(d.status, d.reason) for d in decisions.values()} == {(Eligibility.UNKNOWN, "no_record")}


# ------------------------------------------------------------------ purity and isolation

def test_load_does_not_modify_or_create_files(tmp_path):
    p = write_csv(tmp_path, [row()])
    before = (hashlib.sha256(p.read_bytes()).hexdigest(), sorted(tmp_path.iterdir()))
    load_registry(p).decide("AAA", date(2026, 2, 2))
    assert (hashlib.sha256(p.read_bytes()).hexdigest(), sorted(tmp_path.iterdir())) == before


def test_import_pulls_in_no_trading_data_or_network_modules():
    code = "import json, sys; import screening.eligibility; print(json.dumps(sorted(sys.modules)))"
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True,
                         env={"PYTHONDONTWRITEBYTECODE": "1", "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
                              "PYTHONPATH": str(ROOT)})
    mods = json.loads(out.stdout)
    banned = ("paper", "paper_orb", "backtest", "strategy", "acquisition", "data", "signals", "journal",
              "requests", "yfinance", "alpaca", "httpx", "telegram", "pandas")
    loaded = [m for m in mods if any(m == b or m.startswith(b + ".") for b in banned)]
    assert loaded == []


def test_screening_source_has_no_order_network_or_write_code():
    src = "\n".join(p.read_text(encoding="utf-8") for p in sorted((ROOT / "screening").glob("*.py")))
    for banned in ("submit_order", "TradingClient", "place_order", "http://", "https://", "requests", "urllib",
                   "yfinance", "alpaca", "open(", "write_text", "write_bytes", "mkdir", "unlink", "rename"):
        assert banned not in src, banned
