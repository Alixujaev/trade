"""acquisition/v2/reviews.py: classification of Stage R BLOCKING data reviews (protocol §3.4/§3.8 + v2.0.1).

Deterministic rules on acquired data only. Each item -> RESOLVED / RESOLVED_EXCLUDED / BLOCKING with a reason.
- name_change touching a Stage R entity whose old and new CUSIP are equal (pure rename) -> RESOLVED if the
  entity's cross-check has no unmatched factor change on that date; otherwise BLOCKING.
- merger where the Stage R entity is the ACQUIRER -> RESOLVED under the same cross-check condition (holder's
  shares and cash are unaffected); acquiree side or any other type -> BLOCKING.
- foreign-entity record (ticker match, CUSIP mismatch) -> RESOLVED_EXCLUDED (v2.0.1 C2 rule 4).
- identity conflicts, normalisation blockers, complete/all differences, cross-check mismatches, structural
  HARD_FAIL/BLOCKING, undated records -> BLOCKING.
"""

from __future__ import annotations

from typing import Any

MERGER_TYPES = ("cash_mergers", "stock_mergers", "stock_and_cash_mergers")


def classify(*, records: list[dict[str, Any]], identity: dict[str, Any], normalised: dict[str, Any],
             quality: dict[str, Any], crosscheck: dict[str, Any], validation: dict[str, Any],
             ca_counts: dict[str, Any]) -> dict[str, Any]:
    by_id = {str(r.get("id")): r for r in records}
    items: list[dict[str, Any]] = []

    def cc_clean_on(ent: str, day: str) -> bool:
        per = crosscheck["per_symbol"].get(ent)
        return per is not None and day not in set(per.get("unmatched_changes", []))

    for it in normalised["review_items"]:
        r = by_id[it["id"]]
        ent, typ, day = it["entity"], it["ca_type"], it["event_date"]
        if typ == "name_changes":
            same = bool(r.get("old_cusip")) and r.get("old_cusip") == r.get("new_cusip")
            ok = same and cc_clean_on(ent, day)
            items.append({"item": f"name_change {r.get('old_symbol')}->{r.get('new_symbol')}", "entity": ent,
                          "event_date": day, "id": it["id"],
                          "status": "RESOLVED" if ok else "BLOCKING",
                          "reason": ("pure rename (old CUSIP == new CUSIP), no unmatched raw/all factor change"
                                     if ok else "rename changes CUSIP or coincides with an unmatched factor change")})
        elif typ in MERGER_TYPES and it["role"] == "acquirer":
            ok = cc_clean_on(ent, day)
            items.append({"item": f"{typ} {r.get('acquirer_symbol')}<-{r.get('acquiree_symbol')}", "entity": ent,
                          "event_date": day, "id": it["id"], "status": "RESOLVED" if ok else "BLOCKING",
                          "reason": ("Stage R entity is the acquirer: holder share count and cash unaffected; "
                                     "no unmatched raw/all factor change" if ok
                                     else "acquirer-side event coincides with an unmatched factor change")})
        else:
            items.append({"item": f"{typ} ({it['role']})", "entity": ent, "event_date": day, "id": it["id"],
                          "status": "BLOCKING", "reason": "event type/role not supported by §3.4 accounting"})

    for f in identity["foreign_entity_records"]:
        r = by_id.get(f["id"], {})
        label = (f"{r.get('old_symbol')}->{r.get('new_symbol')}" if r.get("old_symbol") else f["ticker"])
        items.append({"item": f"foreign-entity {f['ca_type']} {label}", "entity": f["entity"],
                      "event_date": f["event_date"], "id": f["id"], "status": "RESOLVED_EXCLUDED",
                      "reason": f["reason"] + "; excluded from the Stage R entity (v2.0.1 C2 rule 4)"})
    for c in identity["conflicts"]:
        items.append({"item": f"identity conflict {c['kind']}", "entity": c.get("entity") or c.get("entities"),
                      "status": "BLOCKING", "reason": "v2.0.1 C2 rule 7"})
    for u in identity["unassigned_records"]:
        items.append({"item": f"unassigned {u['ca_type']}", "id": u["id"], "event_date": u["event_date"],
                      "status": "BLOCKING", "reason": "record matches no Stage R entity by CUSIP or ticker"})
    for b in normalised["blocking"]:
        items.append({"item": f"normalisation {b['kind']}", "entity": b.get("entity"),
                      "event_date": b.get("event_date") or b.get("ex_date"), "status": "BLOCKING",
                      "reason": "protocol §3.4 / v2.0.1 C3/C4"})
    if quality["blocking"]:
        items.append({"item": "data_quality complete vs all difference", "status": "BLOCKING",
                      "reason": f"only_in_all={len(quality['only_in_all'])}, only_in_complete="
                                f"{len(quality['only_in_complete'])}, content_differs={len(quality['same_id_content_differs'])}"})
    for sym, v in sorted(crosscheck["per_symbol"].items()):
        if v["status"] != "OK":
            items.append({"item": f"raw/all cross-check {sym}", "entity": sym, "status": "BLOCKING",
                          "reason": (f"unmatched_changes={len(v.get('unmatched_changes', []))}, unmatched_events="
                                     f"{len(v.get('unmatched_events', []))}, split_checks_failed="
                                     f"{sum(1 for s in v.get('split_magnitude_checks', []) if s['ok'] is not True)}, "
                                     f"uncheckable_events={len(v.get('uncheckable_events', []))}")})
    for key, v in sorted(validation["per_series"].items()):
        if v["status"] != "OK":
            items.append({"item": f"structural {key}", "status": v["status"],
                          "reason": "; ".join(v.get("hard_fail", []) + v.get("blocking", []))})
    for key, v in sorted(validation["raw_vs_all"].items()):
        if v["status"] != "OK":
            items.append({"item": f"raw/all session sets {key}", "status": "HARD_FAIL", "reason": "session sets differ"})
    undated = sum(c.get("discarded_no_date", 0) for c in ca_counts.values())
    if undated:
        items.append({"item": "corporate-action records without any date", "status": "BLOCKING",
                      "reason": f"{undated} records could not be placed relative to the Stage R boundary"})
    blocking = [i for i in items if i["status"] in ("BLOCKING", "HARD_FAIL")]
    return {"items": items, "blocking_count": len(blocking),
            "status_counts": {s: sum(1 for i in items if i["status"] == s)
                              for s in ("RESOLVED", "RESOLVED_EXCLUDED", "BLOCKING", "HARD_FAIL")},
            "usable_for_research": not blocking}
