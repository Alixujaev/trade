# DAY-13 — OOS Gate Decision

**Question:** *Is there currently a sufficiently specified, non-post-hoc candidate that is methodologically clean enough to take into an independent OOS test?*

## Decision: **NO**

No OOS gate is defined, and no OOS test is run or scheduled. No candidate is named. A candidate is not invented in order to proceed.

## Why no candidate qualifies

Evidence is in `research-matrix.json` and `research-synthesis.md`.

1. **No in-sample candidate survives the stated costs.**
   - None of the 38 variant rows with trades (DAY-04 → DAY-12B) has a non-negative compounded return at 5 or 10 bps per side.
   - The largest mean gross trade return of any variant (+0.0288%, DAY-06A gap ≥ 4%, 210 trades) is below the ≈0.10% round-trip cost at 5 bps per side.
   - An OOS test is meant to confirm an in-sample result, and there is no cost-robust in-sample result to confirm.
2. **Every gross-improving variant is either a selection or post-hoc.**
   - Gap ≥ 4% (DAY-06A), CAP 1 (DAY-10), ATR × 1.00 (DAY-09), MORNING (DAY-11) and BE 0.75R (DAY-07A) are each the best gross member of a 3–5-variant family compared on the same 60 sessions. Promoting any of them now would be in-sample selection.
   - DAY-12B (BE 0.5R) was chosen after DAY-12A and is the 4th threshold of an already-explored family.
3. **No OOS-candidate criterion was ever predeclared.** No repository protocol states, before results, which variant would advance or under what acceptance rule. Writing one now, after seeing all 40 rows, would be post-hoc.
4. **Several components were never testable on the frozen data:**
   - premarket RVOL (0 premarket volume in yfinance history);
   - catalyst data (unavailable);
   - intrabar order within 5m bars (50.4% of baseline trades are single-bar).
5. **No independent data exists in the frozen cache.** 5m bars cover only 2026-07-02 → 2026-09-25, the same window used by every experiment. An OOS test would need new data, which DAY-13 must not acquire.

## What would be required before any future OOS gate (requirements, not a candidate)

These are generic preconditions. They do not select or imply any variant.

- **Frozen rule declared before the OOS data is accessed:**
  - exact signal, entry, stop, target, exit, costs, sizing and same-bar semantics;
  - the code commit hash;
  - the exact configuration object.
- **The rule justified by in-sample evidence that is itself cost-robust** at the costs that will be used OOS. That is not met today.
- **A disjoint dataset:**
  - sessions strictly after 2026-09-25, or another non-overlapping period;
  - the same universe definition (or one fixed in advance);
  - a data source and cache frozen and hashed before any result is computed.
- **Predefined costs:** per-side bps levels fixed in advance, plus a statement of whether the compounded 1-unit model or a sized portfolio model is the primary metric.
- **Predefined handling rules:**
  - missing data: explicit exclusion with counts;
  - same-bar ambiguity: STOP_FIRST unless changed before data access;
  - gap fills: the current engine fills stops at the stop price even when a bar opens beyond it — this must be decided in advance, given DAY-12B's 84.21R sensitivity.
- **Predefined metrics and report format:**
  - trades, WR, PF, total / avg / median R, max DD;
  - 0 / 5 / 10 bps returns;
  - mean trade return versus round-trip cost;
  - per-symbol spread.
- **Acceptance / rejection framework:** written before OOS data is seen.
  - Numerical acceptance thresholds: **NOT PREDEFINED.** No threshold can be justified from prior research, because no in-sample variant met a cost-robust bar.
  - OOS results must not be used to tune the rule.

## Status

DAY-13 ends with this decision. DAY-14 is not started, and no optimization or further experiment has been run.
