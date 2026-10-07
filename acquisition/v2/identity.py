"""acquisition/v2/identity.py: corporate-action entity identity (v2.0.1 C2).

Rules implemented (amendment C2):
1. A non-empty CUSIP is authoritative; the ticker is a query key only.
2. Aliases: name_changes whose new_symbol is a Stage R symbol and whose old_cusip is in that symbol's CUSIP set.
3. Anchor of T: new_cusip of the latest name_change with new_symbol = T; else the single non-empty CUSIP among
   T's split/dividend records (several CUSIPs must be chain-linked). CUSIP set = anchor + chain closure.
4. Ticker match + non-empty CUSIP outside the set -> foreign-entity record (excluded, listed).
5. Empty CUSIP -> matched by ticker only if T has no foreign-entity record; otherwise a conflict.
7. Conflicts: (a) unlinked CUSIPs, (b) empty CUSIP with a foreign entity, (c) CUSIP in two sets,
   (d) unorderable name change; plus a name change into T from a ticker that was not queried (missed alias).
No mapping is invented beyond the acquired records.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

_PAIRS = (("symbol", "cusip"), ("symbol", "old_cusip"), ("symbol", "new_cusip"),
          ("old_symbol", "old_cusip"), ("new_symbol", "new_cusip"),
          ("acquirer_symbol", "acquirer_cusip"), ("acquiree_symbol", "acquiree_cusip"),
          ("source_symbol", "source_cusip"), ("target_symbol", "target_cusip"))
_ROLE = {"symbol": "subject", "old_symbol": "renamed_from", "new_symbol": "renamed_to",
         "acquirer_symbol": "acquirer", "acquiree_symbol": "acquiree", "source_symbol": "source",
         "target_symbol": "target"}
SPLIT_DIV_TYPES = ("cash_dividends", "forward_splits", "reverse_splits", "unit_splits", "stock_dividends")
CHAIN_TYPES = ("name_changes", "forward_splits", "reverse_splits", "unit_splits")


def _c(v: Any) -> str:
    return str(v).strip() if v else ""


def _refs(rec: dict[str, Any]) -> list[tuple[str, str, str]]:
    """(ticker, cusip, role) pairs present in a record; empty cusip -> ''."""
    out: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    pairs = list(_PAIRS)
    if "symbol" in rec and not any(k in rec for k in ("cusip", "old_cusip", "new_cusip")):
        pairs.append(("symbol", "__none__"))
    for sk, ck in pairs:
        if sk in rec and (ck in rec or ck == "__none__"):
            t, c = _c(rec.get(sk)), _c(rec.get(ck))
            if not t and not c:
                continue
            if (t, c) in seen:
                continue
            seen.add((t, c))
            out.append((t, c, _ROLE[sk]))
    return out


def _chain_edges(records: list[dict[str, Any]]) -> list[tuple[str, str]]:
    edges = []
    for r in records:
        if r["ca_type"] in CHAIN_TYPES:
            a, b = _c(r.get("old_cusip")), _c(r.get("new_cusip"))
            if a and b and a != b:
                edges.append((a, b))
    return edges


def _closure(start: str, edges: list[tuple[str, str]]) -> set[str]:
    adj: dict[str, set[str]] = defaultdict(set)
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)
    seen, stack = {start}, [start]
    while stack:
        for n in adj[stack.pop()]:
            if n not in seen:
                seen.add(n)
                stack.append(n)
    return seen


def resolve(records: list[dict[str, Any]], entities: list[str], queried: list[str]) -> dict[str, Any]:
    """records: boundary-filtered CA records (each with 'ca_type', 'event_date', 'id').
    entities: Stage R symbols (25 + SPY). queried: symbols used as CA query keys."""
    ents = set(entities)
    conflicts: list[dict[str, Any]] = []
    edges = _chain_edges(records)

    # anchors
    anchors: dict[str, str | None] = {}
    anchor_source: dict[str, str] = {}
    for t in sorted(ents):
        ncs = [r for r in records if r["ca_type"] == "name_changes" and _c(r.get("new_symbol")) == t and _c(r.get("new_cusip"))]
        if ncs:
            dates = [str(r.get("process_date") or r["event_date"]) for r in ncs]
            latest = max(dates)
            top = [r for r, d in zip(ncs, dates) if d == latest]
            cands = {_c(r.get("new_cusip")) for r in top}
            if len(cands) > 1:
                conflicts.append({"kind": "d_unorderable_name_change", "entity": t,
                                  "ids": sorted(str(r.get("id")) for r in top)})
                anchors[t] = None
                anchor_source[t] = "conflict"
                continue
            anchors[t] = cands.pop()
            anchor_source[t] = "name_change"
            continue
        cus = sorted({_c(r.get("cusip")) for r in records
                      if r["ca_type"] in SPLIT_DIV_TYPES and _c(r.get("symbol")) == t and _c(r.get("cusip"))})
        if not cus:
            anchors[t] = None
            anchor_source[t] = "none (no CUSIP-bearing split/dividend or name-change record)"
            continue
        linked = _closure(cus[0], edges)
        if not set(cus) <= linked:
            conflicts.append({"kind": "a_unlinked_cusips", "entity": t, "cusip_count": len(cus)})
            anchors[t] = None
            anchor_source[t] = "conflict"
            continue
        anchors[t] = cus[0]
        anchor_source[t] = "split_dividend_records"

    cusip_sets = {t: (sorted(_closure(a, edges)) if a else []) for t, a in anchors.items()}
    owner: dict[str, list[str]] = defaultdict(list)
    for t, cs in cusip_sets.items():
        for c in cs:
            owner[c].append(t)
    for c, ts in owner.items():
        if len(ts) > 1:
            conflicts.append({"kind": "c_cusip_in_two_sets", "entities": sorted(ts)})

    # aliases (name change into an entity, same CUSIP set)
    aliases: dict[str, str] = {}
    for r in records:
        if r["ca_type"] != "name_changes":
            continue
        new_t, old_t, old_c = _c(r.get("new_symbol")), _c(r.get("old_symbol")), _c(r.get("old_cusip"))
        if new_t in ents and old_t and old_t != new_t and old_c and old_c in set(cusip_sets.get(new_t, [])):
            aliases[old_t] = new_t
            if old_t not in queried:
                conflicts.append({"kind": "missed_alias", "entity": new_t, "alias": old_t, "id": str(r.get("id"))})

    def to_entity(ticker: str) -> str | None:
        if ticker in ents:
            return ticker
        return aliases.get(ticker)

    assignments: list[dict[str, Any]] = []
    foreign: list[dict[str, Any]] = []
    unassigned: list[dict[str, Any]] = []
    ticker_only: list[tuple[int, str]] = []
    for r in records:
        matched: dict[str, dict[str, Any]] = {}
        frn: list[dict[str, Any]] = []
        for ticker, cusip, role in _refs(r):
            if cusip and len(owner.get(cusip, [])) == 1:
                ent = owner[cusip][0]
                matched.setdefault(ent, {"entity": ent, "role": role, "match": "cusip"})
                continue
            ent = to_entity(ticker)
            if ent is None:
                continue
            if cusip:
                frn.append({"ticker": ticker, "entity": ent, "role": role,
                            "reason": "ticker matches a Stage R entity but CUSIP is not in its CUSIP set"})
            else:
                matched.setdefault(ent, {"entity": ent, "role": role, "match": "ticker_only"})
        base = {"id": str(r.get("id")), "ca_type": r["ca_type"], "event_date": r["event_date"]}
        if matched:
            for ent, m in sorted(matched.items()):
                assignments.append({**base, **m})
                if m["match"] == "ticker_only":
                    ticker_only.append((len(assignments) - 1, ent))
        if frn and not matched:
            for f in frn:
                foreign.append({**base, **f})
        if not matched and not frn:
            unassigned.append(base)

    foreign_entities = {f["entity"] for f in foreign}
    for idx, ent in ticker_only:
        if ent in foreign_entities:
            a = assignments[idx]
            conflicts.append({"kind": "b_empty_cusip_with_foreign_entity", "entity": ent, "id": a["id"],
                              "ca_type": a["ca_type"], "event_date": a["event_date"]})

    return {"rule": "v2.0.1 C2", "entities": sorted(ents), "queried_symbols": sorted(queried),
            "anchors": anchors, "anchor_source": anchor_source, "cusip_sets": cusip_sets, "aliases": aliases,
            "assignments": assignments, "foreign_entity_records": foreign, "unassigned_records": unassigned,
            "conflicts": conflicts,
            "counts": {"records": len(records), "assigned": len(assignments),
                       "assigned_by_cusip": sum(1 for a in assignments if a["match"] == "cusip"),
                       "assigned_ticker_only": sum(1 for a in assignments if a["match"] == "ticker_only"),
                       "foreign": len(foreign), "unassigned": len(unassigned), "conflicts": len(conflicts)}}
