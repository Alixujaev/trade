# ORB SIP snapshot diagnostic: Stage 4 decision record

> Decision document. No code, snapshot, protocol or data file was changed.
> No backtest, test or network call was run.
> Prepared by the implementation agent from the owner-approved decisions.
> It takes effect for the protocol owner when committed.
> Stage 5 code must not precede this commit.

## Record identity

- Task: ORB SIP snapshot diagnostic, Stage 4 decision record.
- Working HEAD: `949aa66` (branch `feature/day-trading-research`).
- Snapshot directory (git-ignored, write-once, read-only):
  `data/oos_cache/protocol_v1.1/research/snapshots/research_20261006T095201Z/`
- Snapshot ID: `research_20261006T095201Z`
- Pinned SHA-256 of `files.json`:
  `b43b8996d1e45a58c61aba74bc8bc83b173809e554f4c0c125c0f4f5f6b95139`
- Pinned SHA-256 of `units.json`:
  `6a0466192a87ce53cb27d8b5e55a4fb510f8e790d8cc75548b6e9987a3b76b74`
- Pinned SHA-256 of `run.json`:
  `8b57b2dad2c22b69dee25845ef6d4d3520811088124c35b3b668e6fb510a4278`
- Pin sources (committed):
  - `artifacts/day15/day15h-alpaca-rebaseline.json`, lines 1130-1132 (all three hashes).
  - `artifacts/day15/day15g-research-acquisition.md`, lines 108-109 (`run.json` and `units.json`).

## Decisions

### ORB-SIP-D1: Integration

Option A. Research-only 5m DataFrames from
`load_v11_research(...).frame(symbol, "5m", ("research",))`
are injected directly into the unchanged `backtest/orb_engine.run_orb_backtest`.

There is no new `DataProvider`. There is no change to `data/factory.py`, `DATA_PROVIDER`,
`AlpacaProvider`, or any strategy, risk or execution code.

### ORB-SIP-D2: Data and window

- Snapshot `research_20261006T095201Z`: Alpaca Market Data v2, `feed=sip`, `adjustment=raw`,
  RTH only. Its identity is pinned to the three SHA-256 values above.
- Research segment only: 2026-07-02 to 2026-09-25 inclusive (60 XNYS sessions).
- No warmup bars, no embargo bars (2026-09-28) and no OOS bars (on or after 2026-09-29).
- Universe: the 25 symbols of `FROZEN_DAY_UNIVERSE`. No SPY or QQQ. No extended hours.
- No warmup is supplied, so the first session has no prior close for any symbol.
  This is the same starting condition as the prior yfinance run.

### ORB-SIP-D3: Corporate actions

Prices stay raw as recorded. No session is excluded, and no price or volume adjustment is
applied.

This policy applies only to this SIP diagnostic run. Whether protocol v1.1 section 18 governs
ORB is not decided and is not assumed.

### ORB-SIP-D4: Disclosure

Corporate-action events for 2026-07-02 to 2026-09-25 are unknown, because no event data was
acquired for that period (the v2 Stage H events end on 2026-06-02).

An event could affect:

- (a) the rolling 20-bar volume filter on an ex-date's opening bars, which span the
  09:45-11:00 ET entry window;
- (b) the minimum-price filter of $5, which uses the raw prior close.

Stops, targets, sizing and exits are computed intraday on raw prices, and no position is held
overnight.

### ORB-SIP-D5: Interpretation

This is a descriptive, diagnostic re-run on the same 60 sessions already examined with
yfinance data (`artifacts/orb/smoke_test/`). It is not independent evidence and it is not
strategy validation.

- SIP results are reported on their own.
- The yfinance report is referenced by path only. There are no deltas, no merged or
  side-by-side numeric comparison, and no pooling.
- SIP volume can change `volume_ok` outcomes compared with yfinance. This is disclosed and
  never tuned away.

This does not contradict `artifacts/orb/diagnostics_v2/sip_availability.md`, line 101, which
says the data is not ready for a non-overlapping SIP test. This run overlaps by design.

### ORB-SIP-D6: No network

No corporate-action requests, no market-data downloads and no network calls of any kind.
The run executes inside `no_network()` and under the test socket guard.

## Explicitly undecided

- Whether protocol v1.1 section 18 (`artifacts/day15/protocol-v1.1.md`, lines 245-252)
  governs ORB in general.
- Any non-overlapping SIP test for ORB, which would need a new date range, a new acquisition
  and a matching source-verified earnings calendar.
- Any corporate-action event lookup for 2026-06-03 to 2026-09-28.

## References

- Supersedes: none.
- `artifacts/orb/diagnostics_v2/sip_availability.md`: SIP 5m availability and snapshot
  provenance.
- `artifacts/orb/smoke_test/report.md`: prior yfinance ORB run, referenced by path only.
- `artifacts/orb/provenance_correction.md`: yfinance provenance of `data/cache`.
- `artifacts/day15/protocol-v1.1.md`: protocol v1.1, including section 18.
- `artifacts/day15/day15h-alpaca-rebaseline.json`: source of the pinned hashes.
- `artifacts/day15/day15g-research-acquisition.md`: snapshot acquisition record.
