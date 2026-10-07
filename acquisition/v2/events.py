"""acquisition/v2/events.py: Stage R event normalisation (protocol §3.4 + v2.0.1 C3/C4).

- cash dividend: d = Alpaca `rate` (declared, unadjusted per share; regular and special alike) - v2.0.1 C3.
- forward split: q = new_rate / old_rate, must be > 1; reverse split: q must be < 1.
- every other type touching a Stage R entity -> review item (frozen §3.4 BLOCKING data review).
- BLOCKING: same-ex-date split + dividend (C3 rule 4); duplicate (type, entity, event_date) with different
  ids (C4 rule 3); complete-vs-all difference (C4 rule 2); missing/invalid rate fields.
Records assigned only as foreign entities are never normalised.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

SPLIT_TYPES = {"forward_splits": "forward", "reverse_splits": "reverse"}
DIVIDEND_TYPE = "cash_dividends"


def _num(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None


def normalise(records: list[dict[str, Any]], identity: dict[str, Any]) -> dict[str, Any]:
    by_id = {str(r.get("id")): r for r in records}
    events: list[dict[str, Any]] = []
    review_items: list[dict[str, Any]] = []
    blocking: list[dict[str, Any]] = []
    for a in identity["assignments"]:
        r = by_id[a["id"]]
        typ, ent = r["ca_type"], a["entity"]
        base = {"entity": ent, "id": a["id"], "ca_type": typ, "event_date": r["event_date"], "identity_match": a["match"],
                "role": a["role"]}
        if typ == DIVIDEND_TYPE and a["role"] == "subject":
            d = _num(r.get("rate"))
            if d is None or d < 0:
                blocking.append({**base, "kind": "invalid_dividend_rate"})
                continue
            events.append({**base, "event": "cash_dividend", "ex_date": r.get("ex_date"), "d": d,
                           "special": bool(r.get("special")), "foreign_flag": bool(r.get("foreign")),
                           "record_date": r.get("record_date"), "payable_date": r.get("payable_date"),
                           "process_date": r.get("process_date"), "cusip": r.get("cusip")})
        elif typ in SPLIT_TYPES and a["role"] == "subject":
            new, old = _num(r.get("new_rate")), _num(r.get("old_rate"))
            if not new or not old:
                blocking.append({**base, "kind": "invalid_split_rates"})
                continue
            q = new / old
            kind = SPLIT_TYPES[typ]
            if (kind == "forward" and not q > 1) or (kind == "reverse" and not q < 1):
                blocking.append({**base, "kind": f"{kind}_split_ratio_direction_invalid"})
                continue
            events.append({**base, "event": f"{kind}_split", "ex_date": r.get("ex_date"), "q": q,
                           "process_date": r.get("process_date"), "cusip": r.get("cusip") or r.get("new_cusip")})
        else:
            review_items.append({**base, "fields_present": sorted(k for k in r if k not in ("ca_type", "event_date"))})

    # same-ex-date split + dividend (C3 rule 4)
    by_key: dict[tuple[str, str], set[str]] = defaultdict(set)
    for e in events:
        by_key[(e["entity"], e["ex_date"])].add("split" if "split" in e["event"] else "dividend")
    for (ent, ex), kinds in sorted(by_key.items()):
        if kinds == {"split", "dividend"}:
            blocking.append({"kind": "same_ex_date_split_and_dividend", "entity": ent, "ex_date": ex})

    # duplicates (C4 rule 3)
    groups: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for e in events:
        groups[(e["ca_type"], e["entity"], e["event_date"])].add(e["id"])
    for (typ, ent, ed), ids in sorted(groups.items()):
        if len(ids) > 1:
            blocking.append({"kind": "duplicate_records", "ca_type": typ, "entity": ent, "event_date": ed,
                             "ids": sorted(ids)})
    events.sort(key=lambda e: (e["entity"], e["event_date"], e["event"], e["id"]))
    return {"rule": "protocol §3.4 + v2.0.1 C3/C4", "events": events, "review_items": review_items,
            "blocking": blocking,
            "counts": {"events": len(events), "dividends": sum(1 for e in events if e["event"] == "cash_dividend"),
                       "splits": sum(1 for e in events if "split" in e["event"]), "review_items": len(review_items),
                       "blocking": len(blocking)}}


def compare_quality(complete: list[dict[str, Any]], audit_all: list[dict[str, Any]],
                    relevant_ids: set[str]) -> dict[str, Any]:
    """v2.0.1 C4 rule 2: id sets of data_quality=complete vs all (after the C1 boundary filter)."""
    c_ids = {str(r.get("id")) for r in complete}
    a_ids = {str(r.get("id")) for r in audit_all}
    only_all, only_complete = sorted(a_ids - c_ids), sorted(c_ids - a_ids)
    common_differ = sorted(i for i in c_ids & a_ids
                           if {k: v for k, v in next(r for r in complete if str(r.get("id")) == i).items()}
                           != {k: v for k, v in next(r for r in audit_all if str(r.get("id")) == i).items()})
    relevant = sorted((set(only_all) | set(only_complete) | set(common_differ)))
    return {"complete_count": len(c_ids), "all_count": len(a_ids), "only_in_all": only_all,
            "only_in_complete": only_complete, "same_id_content_differs": common_differ,
            "blocking": bool(relevant),
            "relevant_universe_ids_affected": sorted(set(relevant) & relevant_ids) if relevant_ids else relevant}
