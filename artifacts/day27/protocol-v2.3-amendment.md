# DAY-27 — Protocol v2.3 Amendment: Sealed Real-Time Paper-Trading Runner `V2-MOM-P001` (parallel to `fwd-gate2`)

> **STATUS: ADOPTED — 2026-10-10T15:47:33Z** (decision record `artifacts/day27/protocol-v2.3-adoption.json`).
> It takes effect from the commit that contains this amendment and its adoption record, not earlier; `paper/runner.py` refuses to run until then. It is append-only: protocol 2.1 and 2.2, their adoption records and the DAY-26C incident record are not modified, and **the `fwd-gate2` calendar, rules and access guards are unchanged.**

| Field | Value |
|---|---|
| Protocol version | **2.3** (`2.0 R1 + 2.0.1 + 2.0.2 + 2.0.3 + 2.0.4 + 2.1 + 2.2 + 2.3`) |
| Authorisation | Explicit protocol-owner instruction "DAY-27 — BUILD REAL-TIME PAPER TRADING" (2026-10-10). The owner chose "parallel + sealed" (*Parallel + muhrlangan*), an internal virtual ledger, and GitHub Actions as the deployment target. |
| Experiment | **`V2-MOM-P001`** (benchmarks `V2-B1-P001`, `V2-B2-P001`). It is separate from `fwd-gate2` / `V2-MOM-F003`. |
| Strategy | V2-MOM unchanged (config SHA-256 `62827d70ccd17e21dd2e1d1f652357fa5b0de2c79454d1811677eac8e79388c0`). The runner calls the frozen engine `backtest/v2` (`simulate_targets`, `mom_targets`, `month_end_flags`, B1/B2 rules). |
| First sample session | 2026-10-12. The initial decision is at the 2026-10-09 close (§8.14), and the experiment continues indefinitely. |
| Seal | Positions, fills, decisions, equity and P&L are encrypted until **2026-12-09 16:15 America/New_York** (the `fwd-gate2` capture time). |

## 1. Why

The owner wants a continuously operated paper experiment that runs **in parallel** with the blind `fwd-gate2`. Both use the same frozen V2-MOM. Any visible paper position or P&L before the gate ends would reveal the gate's outcome and void it.

## 2. Rules

| ID | Rule |
|---|---|
| P1 | **Separation.** `V2-MOM-P001` has its own data path (Alpaca market-data API, fetched by `paper/data.py` into `$PAPER_STATE_DIR`), its own state and its own ID. Its data and results are **never** used as `fwd-gate2` evidence; the gate's single Stage F snapshot remains the only gate evidence. |
| P2 | **Frozen strategy, virtual ledger.** Decisions, fills, sizing, λ, costs (5 bps primary) and corporate actions are produced only by the frozen engine, replayed up to each completed session. No order is sent to any broker; no trading endpoint is reachable (`GuardedHttp` allows only `https://data.alpaca.markets/`). Real-money trading is impossible in this code. |
| P3 | **Seal.** Every performance-bearing output (positions, weights, cash, fills, decisions, pending orders, equity, P&L) is written only as an encrypted, authenticated blob: HMAC-SHA256 counter-mode encryption with an HMAC tag, keyed by the `PAPER_SEAL_KEY` secret. `reveal`/`unseal` refuse before the seal time. Plaintext outputs are limited to health: session, timestamps, data completeness counts, hashes, error codes. |
| P4 | **Exception E7** to DAY-22 §3.2.2 ("operational data feeds … must never calculate or expose forward strategy performance during the blind evaluation window"). Calculation is permitted **only inside the sealed runner**; exposure remains prohibited until the seal time. **Any decryption or disclosure of `V2-MOM-P001` performance before 2026-12-09 16:15 ET is a protocol breach that makes `fwd-gate2` `FORWARD42-INVALID (protocol-breach)` and must be disclosed.** The time lock is enforced in code; custody of the key is procedural, and that is disclosed here. |
| P5 | **Fail closed.** The runner records nothing if any of the following fails, and the error is logged with secrets redacted: v2.3/v2.2/v2.1 adoption not committed or pins mismatched; config SHA changed; quarantined incident file in a data path; missing, stale or incomplete bars; a non-session label; structural HARD_FAIL/BLOCKING; identity or normalisation conflicts; an authentication error; inconsistent state (replay of a processed session no longer matches its stored hash); a risk invariant broken (≤ 5 names, target weight ≤ 0.2, sum ≤ 1, exposure ≤ 1, cash ≥ 0, fills at the raw open). Corporate-action cross-check/review items are reported as `review_pending` in health rather than blocking (no human review records exist for live data). |
| P6 | **Timing.** A session is processed only after its official close + 15 minutes (early closes included). Missed sessions are processed on the next run (catch-up) and flagged `late`; because the replay is point-in-time, catch-up equals on-time processing. |
| P7 | **Idempotency.** One health record per session is the commit point. A processed session is never reprocessed; orders are a pure function of the replay, so retries and restarts cannot duplicate them. |

## 3. Implementation

- `paper/config.py`, `paper/seal.py`, `paper/data.py`, `paper/ledger.py`, `paper/runner.py` (CLI `python -m paper.runner {run,status,check-health,reveal,init-key}`).
- `tests/test_day27_paper.py`: synthetic and network-free.
- `.github/workflows/paper-trading.yml`: prepared, **not activated**. It needs a push, secrets and owner approval.

## 4. Unchanged

V2-MOM rules and config SHA; protocol 2.2 and the `fwd-gate2` calendar (2026-10-12 → 2026-12-09), guards and status (PENDING); the DAY-26C quarantine; all frozen and historical artifacts.
