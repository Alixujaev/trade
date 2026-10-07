"""acquisition/v2/ca_client.py: Alpaca corporate actions for Stage R (v2.0.1 C1, C4).

LEAKAGE BOUNDARY (v2.0.1 C1 rule 4): every page is reduced, inside `fetch_window`, to records whose
event_date (ex_date, else effective_date, else process_date) lies in [2016-01-04, 2022-12-30]. Records outside
are dropped immediately and only counted; no raw page, no discarded record and no field of a discarded record
ever leaves this module (not returned, not logged, not persisted).
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from acquisition.v2.contract import (
    CA_DATA_QUALITY, CA_TYPES, CA_WINDOWS, EVENT_DATE_MAX, EVENT_DATE_MIN, CorporateActionsConfig,
)
from acquisition.v2.http import MAX_PAGES, AlpacaRequestError, HttpClient, RequestGuardError


def event_date(record: dict[str, Any]) -> str | None:
    """v2.0.1 C1 rule 1: ex_date, else effective_date, else process_date (ISO YYYY-MM-DD)."""
    for k in ("ex_date", "effective_date", "process_date"):
        v = record.get(k)
        if v:
            return str(v)[:10]
    return None


def boundary_filter(type_records: list[tuple[str, dict[str, Any]]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Keep records with EVENT_DATE_MIN <= event_date <= EVENT_DATE_MAX. Returns kept records (each tagged with
    'ca_type' and 'event_date') and aggregate counts only."""
    kept: list[dict[str, Any]] = []
    counts = {"kept": 0, "discarded_after_stage_r": 0, "discarded_before_stage_r": 0, "discarded_no_date": 0}
    for typ, rec in type_records:
        ed = event_date(rec)
        if ed is None:
            counts["discarded_no_date"] += 1
            continue
        if ed > EVENT_DATE_MAX:
            counts["discarded_after_stage_r"] += 1
            continue
        if ed < EVENT_DATE_MIN:
            counts["discarded_before_stage_r"] += 1
            continue
        out = dict(rec)
        out["ca_type"] = typ
        out["event_date"] = ed
        kept.append(out)
        counts["kept"] += 1
    return kept, counts


class CorporateActionsClient:
    def __init__(self, http: HttpClient, *, config: CorporateActionsConfig | None = None) -> None:
        self.http = http
        self.config = config or CorporateActionsConfig()

    def fetch_window(self, window: str, data_quality: str, symbols: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if window not in CA_WINDOWS:
            raise RequestGuardError(f"window {window!r} not in frozen {sorted(CA_WINDOWS)}")
        if data_quality not in CA_DATA_QUALITY:
            raise RequestGuardError(f"data_quality {data_quality!r} not in {CA_DATA_QUALITY}")
        start, end = CA_WINDOWS[window]
        params: dict[str, Any] = {"symbols": ",".join(symbols), "types": ",".join(CA_TYPES), "start": start,
                                  "end": end, "limit": self.config.limit, "sort": self.config.sort,
                                  "data_quality": data_quality}
        kept: list[dict[str, Any]] = []
        totals = {"kept": 0, "discarded_after_stage_r": 0, "discarded_before_stage_r": 0, "discarded_no_date": 0}
        pages: list[dict[str, Any]] = []
        token: str | None = None
        for _ in range(MAX_PAGES):
            p = dict(params, page_token=token) if token else params
            body, info = self.http.get_json(self.config.url, p)
            ca = body.get("corporate_actions") or {}
            flat = [(typ, rec) for typ, items in ca.items() for rec in (items or [])]
            page_kept, counts = boundary_filter(flat)
            del flat, ca                       # nothing outside the boundary survives this iteration
            kept.extend(page_kept)
            for k, v in counts.items():
                totals[k] += v
            token = body.get("next_page_token")
            del body
            pages.append({**info, "kept": counts["kept"], "next_page_token_present": bool(token)})
            if not token:
                break
        else:
            raise AlpacaRequestError(f"more than {MAX_PAGES} corporate-action pages for {window}/{data_quality}")
        record = {"window": window, "process_date_window": [start, end], "data_quality": data_quality,
                  "url": self.config.url, "params": {k: v for k, v in params.items() if k != "symbols"},
                  "symbols": list(symbols), "page_count": len(pages), "pages": pages, "counts": totals,
                  "request_utc": pd.Timestamp.now(tz="UTC").isoformat()}
        return kept, record
