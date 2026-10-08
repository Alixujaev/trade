"""acquisition/v2/reviews.py: classification of Stage R BLOCKING data reviews (protocol §3.4/§3.8 + v2.0.1-v2.0.3).

v2.0.3 (when a review-record inventory is supplied): UNEXPLAINED_CHANGE, UNCONFIRMED_EVENT and IDENTITY_UNVERIFIED
items are resolved ONLY by records applied by review_records.load (committed, validated); otherwise BLOCKING.
Report categories: PASS / BLOCKING / FIRST_SESSION_UNTESTABLE / IDENTITY_UNVERIFIED / UNRESOLVED.

v2.0.4 (protocol="v2.0.4"): same record-driven outcomes, plus MOOT (a v2.0.3 record whose item no longer exists under
exact evaluation; non-blocking), NUMERICAL_FALSE_POSITIVE (non-blocking audit item), NUMERICAL_FALSE_NEGATIVE (audit
item; the exact detection itself goes through the normal coincidence rules) and EXACT_EVALUATION_INVALID (BLOCKING).

v2.0.2: IDENTITY_UNVERIFIED records (rule 4a) -> BLOCKING; FIRST_SESSION_UNTESTABLE events (item 2) are listed
and non-blocking; the cross-check clean-date condition uses the v2.0.2 unexplained-change dates.

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

from acquisition.v2.review_records import item_key_str

MERGER_TYPES = ("cash_mergers", "stock_mergers", "stock_and_cash_mergers")
CATEGORIES = ("PASS", "BLOCKING", "FIRST_SESSION_UNTESTABLE", "IDENTITY_UNVERIFIED", "UNRESOLVED")
CATEGORIES_V204 = CATEGORIES + ("MOOT", "NUMERICAL_FALSE_POSITIVE", "NUMERICAL_FALSE_NEGATIVE", "EXACT_EVALUATION_INVALID")
STATUSES = ("RESOLVED", "RESOLVED_EXCLUDED", "FIRST_SESSION_UNTESTABLE", "BLOCKING", "HARD_FAIL")
STATUSES_V204 = STATUSES + ("MOOT", "NUMERICAL_FALSE_POSITIVE", "NUMERICAL_FALSE_NEGATIVE")


def open_items(crosscheck: dict[str, Any], identity: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """v2.0.3 items that a committed review record may address (item_key_str -> item)."""
    out: dict[str, dict[str, Any]] = {}
    for sym, v in sorted(crosscheck["per_symbol"].items()):
        for pr in v.get("unexplained_pairs", []):
            key = {"entity": sym, "session": pr["k"]}
            out[item_key_str("UNEXPLAINED_CHANGE", key)] = {"item_type": "UNEXPLAINED_CHANGE", "item_key": key,
                                                            "p": pr["p"], "k": pr["k"]}
        for u in v.get("unconfirmed_event_records", []):
            key = {"entity": sym, "ex_date": u["ex_date"], "ca_id": u["id"]}
            out[item_key_str("UNCONFIRMED_EVENT", key)] = {"item_type": "UNCONFIRMED_EVENT", "item_key": key,
                                                           "event": u["event"]}
    for u in identity.get("identity_unverified_records", []):
        key = {"entity": u["entity"], "event_date": u["event_date"], "ca_id": u["id"]}
        out[item_key_str("IDENTITY_UNVERIFIED", key)] = {"item_type": "IDENTITY_UNVERIFIED", "item_key": key,
                                                         "ca_type": u["ca_type"], "role": u["role"]}
    return out


def _category(item: dict[str, Any]) -> str:
    if item.get("category"):
        return item["category"]
    st = item["status"]
    if st in ("RESOLVED", "RESOLVED_EXCLUDED"):
        return "PASS"
    if st == "FIRST_SESSION_UNTESTABLE":
        return "FIRST_SESSION_UNTESTABLE"
    return "BLOCKING"


def classify(*, records: list[dict[str, Any]], identity: dict[str, Any], normalised: dict[str, Any],
             quality: dict[str, Any], crosscheck: dict[str, Any], validation: dict[str, Any],
             ca_counts: dict[str, Any], review_inventory: dict[str, Any] | None = None,
             protocol: str = "v2.0.3") -> dict[str, Any]:
    """review_inventory None -> v2.0.2 classification (unchanged). A dict (from review_records.load, possibly with
    no records) -> v2.0.3 classification: record-driven outcomes, default BLOCKING."""
    if review_inventory is not None:
        return _classify_v203(records=records, identity=identity, normalised=normalised, quality=quality,
                              crosscheck=crosscheck, validation=validation, ca_counts=ca_counts,
                              inventory=review_inventory, protocol=protocol)
    by_id = {str(r.get("id")): r for r in records}
    items: list[dict[str, Any]] = []

    def cc_clean_on(ent: str, day: str) -> bool:
        per = crosscheck["per_symbol"].get(ent)
        return per is not None and day not in set(per.get("unexplained_changes", []))

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
    for u in identity.get("identity_unverified_records", []):
        r = by_id.get(u["id"], {})
        label = (f"{r.get('acquirer_symbol')}<-{r.get('acquiree_symbol')}" if r.get("acquirer_symbol")
                 else f"{r.get('old_symbol')}->{r.get('new_symbol')}" if r.get("old_symbol") else u["ticker"])
        items.append({"item": f"identity-unverified {u['ca_type']} {label}", "entity": u["entity"],
                      "event_date": u["event_date"], "id": u["id"], "status": "BLOCKING",
                      "classification": "IDENTITY_UNVERIFIED",
                      "reason": "v2.0.2 rule 4a: entity has no CUSIP anchor; resolution requires a same-provider anchor "
                                "or an explicit committed reviewer record (economic neutrality is not identity evidence)"})
    for sym, v in sorted(crosscheck["per_symbol"].items()):
        for e in v.get("first_session_untestable", []):
            items.append({"item": f"first-session {e['event']} {sym}", "entity": sym, "event_date": e["ex_date"],
                          "id": e["id"], "status": "FIRST_SESSION_UNTESTABLE",
                          "reason": "v2.0.2 item 2: ex_date <= first common session; non-blocking; excluded from TR/accounting"})
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
                          "reason": (f"unexplained_changes={len(v.get('unexplained_changes', []))}, unconfirmed_events="
                                     f"{len(v.get('unconfirmed_events', []))}, split_checks_failed="
                                     f"{sum(1 for s in v.get('split_magnitude_checks', []) if s['ok'] is not True)}, "
                                     f"precision_degenerate_pairs={len(v.get('precision_degenerate_pairs', []))}, "
                                     f"uncheckable_events={len(v.get('uncheckable_events', []))}"
                                     + (f", {v['reason']}" if v.get("reason") else ""))})
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
                              for s in ("RESOLVED", "RESOLVED_EXCLUDED", "FIRST_SESSION_UNTESTABLE", "BLOCKING",
                                        "HARD_FAIL")},
            "usable_for_research": not blocking}


def _classify_v203(*, records, identity, normalised, quality, crosscheck, validation, ca_counts, inventory,
                   protocol="v2.0.3"):
    """v2.0.3 items 2-5. Only records applied by review_records.load can resolve an item; default BLOCKING."""
    by_id = {str(r.get("id")): r for r in records}
    applied = inventory.get("applied", {})
    items: list[dict[str, Any]] = []

    def decision(item_type: str, key: dict[str, Any]) -> dict[str, Any] | None:
        return applied.get(item_key_str(item_type, key))

    # unexplained changes that remain open (not resolved as provider artifacts) define "unclean" dates
    unclean: dict[str, set[str]] = {}
    for sym, v in crosscheck["per_symbol"].items():
        unclean[sym] = set()
        for pr in v.get("unexplained_pairs", []):
            d = decision("UNEXPLAINED_CHANGE", {"entity": sym, "session": pr["k"]})
            if not (d and d["decision"] == "PROVIDER_ADJUSTMENT_ARTIFACT"):
                unclean[sym].add(pr["k"])

    def clean_on(ent: str, day: str) -> bool:
        return ent in crosscheck["per_symbol"] and day not in unclean.get(ent, set())

    for it in normalised["review_items"]:
        r = by_id[it["id"]]
        ent, typ, day = it["entity"], it["ca_type"], it["event_date"]
        if typ == "name_changes":
            same = bool(r.get("old_cusip")) and r.get("old_cusip") == r.get("new_cusip")
            ok = same and clean_on(ent, day)
            items.append({"item": f"name_change {r.get('old_symbol')}->{r.get('new_symbol')}", "entity": ent,
                          "event_date": day, "id": it["id"], "status": "RESOLVED" if ok else "BLOCKING",
                          "reason": ("pure rename (old CUSIP == new CUSIP), no open unexplained change on that date"
                                     if ok else "rename changes CUSIP or coincides with an open unexplained change")})
        elif typ in MERGER_TYPES and it["role"] == "acquirer":
            ok = clean_on(ent, day)
            items.append({"item": f"{typ} {r.get('acquirer_symbol')}<-{r.get('acquiree_symbol')}", "entity": ent,
                          "event_date": day, "id": it["id"], "status": "RESOLVED" if ok else "BLOCKING",
                          "reason": ("acquirer-side: holder share count and cash unaffected; no open unexplained change"
                                     if ok else "acquirer-side event coincides with an open unexplained change")})
        else:
            items.append({"item": f"{typ} ({it['role']})", "entity": ent, "event_date": day, "id": it["id"],
                          "status": "BLOCKING", "reason": "event type/role not supported by §3.4 accounting"})

    for f in identity["foreign_entity_records"]:
        r = by_id.get(f["id"], {})
        label = (f"{r.get('old_symbol')}->{r.get('new_symbol')}" if r.get("old_symbol") else f["ticker"])
        items.append({"item": f"foreign-entity {f['ca_type']} {label}", "entity": f["entity"],
                      "event_date": f["event_date"], "id": f["id"], "status": "RESOLVED_EXCLUDED",
                      "reason": f["reason"] + "; excluded from the Stage R entity (v2.0.1 C2 rule 4)"})

    for u in identity.get("identity_unverified_records", []):
        r = by_id.get(u["id"], {})
        label = (f"{r.get('acquirer_symbol')}<-{r.get('acquiree_symbol')}" if r.get("acquirer_symbol")
                 else f"{r.get('old_symbol')}->{r.get('new_symbol')}" if r.get("old_symbol") else u["ticker"])
        base = {"item": f"identity-unverified {u['ca_type']} {label}", "entity": u["entity"],
                "event_date": u["event_date"], "id": u["id"]}
        d = decision("IDENTITY_UNVERIFIED", {"entity": u["entity"], "event_date": u["event_date"], "ca_id": u["id"]})
        if d and d["decision"] == "SAME_ENTITY":
            ok = u["ca_type"] in MERGER_TYPES and u["role"] == "acquirer" and clean_on(u["entity"], u["event_date"])
            items.append({**base, "status": "RESOLVED" if ok else "BLOCKING", "review_record": d,
                          "reason": "committed review SAME_ENTITY; processed as frozen §3.4 review item "
                                    + ("(acquirer-side, clean date)" if ok else "(not an acquirer-side merger on a clean date)")})
        elif d and d["decision"] == "DIFFERENT_ENTITY":
            items.append({**base, "status": "RESOLVED_EXCLUDED", "review_record": d,
                          "reason": "committed review DIFFERENT_ENTITY; excluded from the entity"})
        else:
            items.append({**base, "status": "BLOCKING", "category": "IDENTITY_UNVERIFIED",
                          "review_record": d,
                          "reason": "v2.0.2 rule 4a / v2.0.3 item 5: no anchor and no applicable committed review record"})

    excluded_events: list[str] = []
    for sym, v in sorted(crosscheck["per_symbol"].items()):
        for e in v.get("first_session_untestable", []):
            items.append({"item": f"first-session {e['event']} {sym}", "entity": sym, "event_date": e["ex_date"],
                          "id": e["id"], "status": "FIRST_SESSION_UNTESTABLE",
                          "reason": "v2.0.2 item 2: ex_date <= first common session; non-blocking; excluded from TR/accounting"})
        for pr in v.get("unexplained_pairs", []):
            d = decision("UNEXPLAINED_CHANGE", {"entity": sym, "session": pr["k"]})
            base = {"item": f"unexplained-change {sym} {pr['k']}", "entity": sym, "event_date": pr["k"],
                    "item_type": "UNEXPLAINED_CHANGE"}
            if d and d["decision"] == "PROVIDER_ADJUSTMENT_ARTIFACT":
                items.append({**base, "status": "RESOLVED", "review_record": d,
                              "reason": "committed review PROVIDER_ADJUSTMENT_ARTIFACT (mechanical evidence check passed)"})
            elif d and d["decision"] == "MISSING_EVENT_CONFIRMED":
                items.append({**base, "status": "BLOCKING", "review_record": d,
                              "reason": "committed review MISSING_EVENT_CONFIRMED: requires acquisition/amendment"})
            else:
                items.append({**base, "status": "BLOCKING", "category": "UNRESOLVED", "review_record": d,
                              "reason": "v2.0.3 item 3: unexplained change without an applicable committed review record"})
        for u in v.get("unconfirmed_event_records", []):
            d = decision("UNCONFIRMED_EVENT", {"entity": sym, "ex_date": u["ex_date"], "ca_id": u["id"]})
            base = {"item": f"unconfirmed-event {sym} {u['event']} {u['ex_date']}", "entity": sym,
                    "event_date": u["ex_date"], "id": u["id"], "item_type": "UNCONFIRMED_EVENT"}
            if d and d["decision"] == "EVENT_RETAINED":
                items.append({**base, "status": "RESOLVED", "review_record": d,
                              "reason": "committed review EVENT_RETAINED (mechanical evidence check passed)"})
            elif d and d["decision"] == "EVENT_REJECTED":
                excluded_events.append(u["id"])
                items.append({**base, "status": "RESOLVED_EXCLUDED", "review_record": d,
                              "reason": "committed review EVENT_REJECTED: event excluded from TR/accounting"})
            else:
                items.append({**base, "status": "BLOCKING", "category": "UNRESOLVED", "review_record": d,
                              "reason": "v2.0.3 item 4: unconfirmed event without an applicable committed review record"})
        structural = (v.get("precision_degenerate_pairs") or v.get("uncheckable_events") or v.get("reason")
                      or any(s["ok"] is not True for s in v.get("split_magnitude_checks", [])))
        if structural:
            items.append({"item": f"raw/all cross-check {sym}", "entity": sym, "status": "BLOCKING",
                          "reason": (f"split_checks_failed={sum(1 for s in v.get('split_magnitude_checks', []) if s['ok'] is not True)}, "
                                     f"precision_degenerate_pairs={len(v.get('precision_degenerate_pairs', []))}, "
                                     f"uncheckable_events={len(v.get('uncheckable_events', []))}"
                                     + (f", {v['reason']}" if v.get("reason") else ""))})

    for inv in inventory.get("invalid", []):
        items.append({"item": f"invalid review record {inv.get('file')}", "status": "BLOCKING",
                      "reason": "v2.0.3 item 2: " + "; ".join(inv.get("reasons", []))})
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
    if protocol == "v2.0.4":
        for m in inventory.get("moot", []):
            key = m["key"].split("|")
            items.append({"item": f"moot review record {m['file']}", "entity": key[1].split("=", 1)[1],
                          "event_date": key[2].split("=", 1)[1], "item_type": key[0], "status": "MOOT",
                          "category": "MOOT", "review_record": {k: m.get(k) for k in ("record_id", "decision",
                                                                                      "blob_sha256", "file")},
                          "reason": "v2.0.4: " + m["reason"]})
        for sym, v in sorted(crosscheck["per_symbol"].items()):
            for pr in v.get("numerical_false_positives", []):
                items.append({"item": f"numerical-false-positive {sym} {pr['k']}", "entity": sym,
                              "event_date": pr["k"], "p": pr["p"], "status": "NUMERICAL_FALSE_POSITIVE",
                              "category": "NUMERICAL_FALSE_POSITIVE",
                              "reason": "v2.0.4: exact NO DETECTION, float64 DETECTION; not a factor change; non-blocking"})
            for pr in v.get("numerical_false_negatives", []):
                items.append({"item": f"numerical-false-negative {sym} {pr['k']}", "entity": sym,
                              "event_date": pr["k"], "p": pr["p"], "status": "NUMERICAL_FALSE_NEGATIVE",
                              "category": "NUMERICAL_FALSE_NEGATIVE",
                              "reason": "v2.0.4: exact DETECTION, float64 NO DETECTION; exact detection stands and is "
                                        "evaluated by the normal coincidence rules"})
            for k in v.get("exact_evaluation_invalid_pairs", []):
                items.append({"item": f"exact-evaluation-invalid {sym} {k}", "entity": sym, "event_date": k,
                              "status": "BLOCKING", "category": "EXACT_EVALUATION_INVALID",
                              "reason": "v2.0.4: a value of the pair has no exact representation"})
    for i in items:
        i["category"] = _category(i)
    blocking = [i for i in items if i["status"] in ("BLOCKING", "HARD_FAIL")]
    sym_blocking = sorted({i["entity"] for i in blocking if isinstance(i.get("entity"), str)
                           and i["entity"] in crosscheck["per_symbol"]
                           and (i["item"].startswith(("unexplained-change", "unconfirmed-event", "raw/all cross-check",
                                                      "exact-evaluation-invalid")))})
    v204 = protocol == "v2.0.4"
    out = {"protocol": protocol, "items": items, "blocking_count": len(blocking),
            "status_counts": {s: sum(1 for i in items if i["status"] == s) for s in (STATUSES_V204 if v204 else STATUSES)},
            "category_counts": {c: sum(1 for i in items if i["category"] == c)
                                for c in (CATEGORIES_V204 if v204 else CATEGORIES)},
            "crosscheck_symbols_blocking": sym_blocking,
            "crosscheck_symbols_pass": sorted(set(crosscheck["per_symbol"]) - set(sym_blocking)),
            "events_excluded_by_review": excluded_events,
            "review_records": {"files_found": inventory.get("files_found", []), "applied": len(applied),
                               "invalid": len(inventory.get("invalid", []))},
            "usable_for_research": not blocking}
    if v204:
        out["review_records"]["moot"] = len(inventory.get("moot", []))
    return out
