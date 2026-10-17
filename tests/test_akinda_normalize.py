"""tests/test_akinda_normalize.py: Akinda /compliance response -> proposed eligibility-registry row (pure, offline).

Synthetic payloads follow the documented /compliance example (fields ticker, company_name, halal_status,
listing_country, reporting_currency, last_scanned, last_updated). No network, no API key.
"""

from __future__ import annotations

import csv
from datetime import date, timedelta
import io

import pytest

from acquisition.akinda import normalize as nz
from acquisition.akinda.contract import NO_VERDICT_STATUSES
from screening import eligibility as el
from screening.eligibility import REQUIRED_COLUMNS, RecordStatus, load_registry

RETRIEVED = date(2026, 10, 19)
REF = "run 20261019T150000Z AAA.body sha256 abc"


def payload(**kw):
    base = {"company_name": "Synthetic Co", "halal_status": "HALAL", "last_scanned": "Aug 06, 2026",
            "last_updated": "Oct 16, 2026", "listing_country": "US", "reporting_currency": "USD", "ticker": "AAA"}
    return {**base, **kw}


def norm(p, *, ticker="AAA", valid_days=30):
    return nz.normalize(ticker, p, retrieved_on=RETRIEVED, valid_days=valid_days, source_ref=REF)


def load_rows(tmp_path, *rows):
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=REQUIRED_COLUMNS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    p = tmp_path / "proposed.csv"
    p.write_text(out.getvalue(), encoding="utf-8")
    return load_registry(p)                                              # production defaults, no override


# ------------------------------------------------------------------ recognised verdicts

def test_fresh_halal_becomes_compliant_and_is_tradable_under_production_defaults(tmp_path):
    n = norm(payload())
    assert n.row["status"] == "COMPLIANT"
    assert n.row["methodology"] == el.AKINDA_COMPLIANCE_METHODOLOGY
    assert n.row["source_date"] == "2026-08-06"                          # vendor last_scanned, not retrieval
    # 30 days from 2026-10-19 would end 2026-11-17, but the screen reaches 92 days on 2026-11-06: capped there.
    assert (n.row["valid_from"], n.row["valid_until"]) == ("2026-10-19", "2026-11-06")
    assert n.row["reviewed_on"] == "2026-10-19"
    reg = load_rows(tmp_path, n.row)
    assert reg.decide("AAA", RETRIEVED).tradable
    assert not reg.decide("AAA", RETRIEVED - timedelta(days=1)).tradable    # no backfilling before retrieval


def test_not_halal_becomes_non_compliant(tmp_path):
    n = norm(payload(halal_status="NOT HALAL"))
    assert n.row["status"] == "NON_COMPLIANT" and n.row["source_date"] == "2026-08-06"
    reg = load_rows(tmp_path, n.row)
    assert reg.decide("AAA", RETRIEVED).status is el.Eligibility.NON_COMPLIANT


@pytest.mark.parametrize("status", sorted(NO_VERDICT_STATUSES))
def test_doubtful_and_no_verdict_statuses_are_unverified(tmp_path, status):
    n = norm(payload(halal_status=status))
    assert n.row["status"] == "UNVERIFIED" and status in n.row["note"]
    assert not load_rows(tmp_path, n.row).decide("AAA", RETRIEVED).tradable


@pytest.mark.parametrize("status", ["HARAM", "halal", "Halal", " HALAL", "NOT_HALAL", "", "COMPLIANT"])
def test_unrecognised_status_is_unverified_with_diagnostic(tmp_path, status):
    n = norm(payload(halal_status=status))
    assert n.row["status"] == "UNVERIFIED"
    assert "unrecognised halal_status" in n.row["note"] and "unrecognised" in n.diagnostic
    assert not load_rows(tmp_path, n.row).decide("AAA", RETRIEVED).tradable


# ------------------------------------------------------------------ screening date and freshness

@pytest.mark.parametrize("scanned, why", [
    (None, "last_scanned is null"),
    ("2026-08-06", "unparseable last_scanned"),                 # undocumented format is not guessed
    ("06 Aug 2026", "unparseable last_scanned"),
    ("Oct 20, 2026", "after retrieval"),                         # future screening date
])
def test_halal_without_a_usable_screening_date_is_unverified(tmp_path, scanned, why):
    n = norm(payload(last_scanned=scanned))
    assert n.row["status"] == "UNVERIFIED" and n.row["source_date"] == ""
    assert why in n.row["note"]
    assert not load_rows(tmp_path, n.row).decide("AAA", RETRIEVED).tradable


def test_last_updated_is_never_used_as_the_screening_date():
    n = norm(payload(last_scanned=None, last_updated="Oct 19, 2026"))
    assert n.row["status"] == "UNVERIFIED" and n.row["source_date"] == ""
    assert n.last_updated_raw == "Oct 19, 2026"


def test_freshness_boundary_uses_the_registry_source_age_limit(tmp_path):
    limit = el.MAX_SOURCE_AGE_DAYS
    ok = (RETRIEVED - timedelta(days=limit)).strftime("%b %d, %Y")
    stale = (RETRIEVED - timedelta(days=limit + 1)).strftime("%b %d, %Y")
    assert norm(payload(last_scanned=ok)).row["status"] == "COMPLIANT"
    s = norm(payload(last_scanned=stale))
    assert s.row["status"] == "UNVERIFIED" and s.row["source_date"] == "" and "stale" in s.row["note"]
    load_rows(tmp_path, norm(payload(last_scanned=ok)).row)                 # loads under production rules


def test_validity_is_capped_where_the_screening_reaches_maximum_age(tmp_path):
    n = norm(payload(last_scanned="Aug 06, 2026"), valid_days=el.MAX_VALIDITY_DAYS)
    end = date.fromisoformat(n.row["valid_until"])
    assert (end - date(2026, 8, 6)).days == el.MAX_SOURCE_AGE_DAYS
    reg = load_rows(tmp_path, n.row)
    assert reg.decide("AAA", end).tradable and not reg.decide("AAA", end + timedelta(days=1)).tradable


def test_validity_is_not_capped_when_the_screening_stays_fresh():
    n = norm(payload(last_scanned="Oct 01, 2026"), valid_days=30)
    assert n.row["valid_until"] == "2026-11-17"                          # 2026-10-01 + 92 is later


def test_stale_not_halal_is_unverified_not_a_fresh_verdict():
    stale = (RETRIEVED - timedelta(days=el.MAX_SOURCE_AGE_DAYS + 1)).strftime("%b %d, %Y")
    assert norm(payload(halal_status="NOT HALAL", last_scanned=stale)).row["status"] == "UNVERIFIED"


@pytest.mark.parametrize("days", [0, -1, el.MAX_VALIDITY_DAYS + 1])
def test_validity_window_must_be_explicit_and_within_the_registry_limit(days):
    with pytest.raises(ValueError, match="valid_days"):
        norm(payload(), valid_days=days)


def test_validity_window_at_the_registry_limit_is_accepted(tmp_path):
    n = norm(payload(), valid_days=el.MAX_VALIDITY_DAYS)
    load_rows(tmp_path, n.row)


# ------------------------------------------------------------------ malformed / contradictory -> no record

@pytest.mark.parametrize("p, why", [
    (["not", "an", "object"], "not a JSON object"),
    ({k: v for k, v in payload().items() if k != "halal_status"}, "missing field halal_status"),
    ({k: v for k, v in payload().items() if k != "last_scanned"}, "missing field last_scanned"),
    ({k: v for k, v in payload().items() if k != "ticker"}, "missing field ticker"),
    (payload(ticker="BBB"), "ticker echo"),
    (payload(ticker="aaa"), "ticker echo"),
    (payload(halal_status=None), "halal_status is not a string"),
    (payload(halal_status=1), "halal_status is not a string"),
    (payload(last_scanned=20260806), "last_scanned is not a string or null"),
])
def test_malformed_or_contradictory_response_produces_no_record(p, why):
    n = norm(p)
    assert n.row is None and why in n.diagnostic


# ------------------------------------------------------------------ provenance

def test_row_carries_provider_methodology_and_evidence_reference():
    r = norm(payload()).row
    assert r["source"] == "Akinda B2B API v1 /compliance"
    assert r["source_ref"] == REF
    assert r["reviewer"].startswith("akinda-sync")
    assert set(r) == set(REQUIRED_COLUMNS)


def test_rows_never_compliant_under_a_methodology_outside_the_registry_allowlist():
    assert el.AKINDA_COMPLIANCE_METHODOLOGY in el.ACCEPTED_METHODOLOGIES
    assert RecordStatus.COMPLIANT.value == norm(payload()).row["status"]
