# paper/: sealed real-time paper-trading runner `V2-MOM-P001`

Protocol 2.3 (`artifacts/day27/protocol-v2.3-amendment.md`). The runner trades V2-MOM **virtually** with the frozen research engine (`backtest/v2`) every XNYS session. Positions and P&L stay **sealed** until **2026-12-09 16:15 America/New_York**, so that the blind gate `fwd-gate2` (same strategy) stays valid. No broker or trading endpoint exists in this code, so it can't place a real-money order.

## Commands

```
python -m paper.runner init-key       # once: prints a new seal key -> store as PAPER_SEAL_KEY (secret, never commit)
python -m paper.runner run            # process every completed, unprocessed session (idempotent; catch-up)
python -m paper.runner status         # health only: processed sessions, late flags, last error (no P&L before seal)
python -m paper.runner check-health   # exit 1 on a missed session or a failed last run
python -m paper.runner reveal [--session YYYY-MM-DD]   # positions, signals, daily P&L; refused before the seal time
```

`--now` is accepted only by `status` / `check-health`; `run` and `reveal` always use the wall clock.

**Environment:**
- `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` (repo-root `.env` or environment variables);
- `PAPER_SEAL_KEY` (64 hex characters; repo-root `.env` or environment variable);
- optional `PAPER_STATE_DIR` (default `paper_state/`, gitignored).

## What one run does

1. **Lock.** Concurrent runs are refused; a stale lock (older than 2 h) is reclaimed.
2. **Preflight.** It refuses unless:
   - protocol 2.3 (and the 2.2/2.1 chain) is committed with its pins unchanged;
   - the V2-MOM config SHA is unchanged;
   - no quarantined DAY-26C file is in `data/`;
   - only `https://data.alpaca.markets/` URLs are configured.
3. **Pick the target session.** It takes the latest XNYS session whose official close + 15 min has passed (early closes included). Before that it reports `NOT_READY` and writes nothing.
4. **Fetch and check data.** It fetches raw and `all` daily bars (2025-01-02 → session) and corporate actions with the existing v2 clients, then runs the Stage H derivations. It fails closed on missing, stale or off-calendar bars, structural failures, conflicts or authentication errors.
5. **Check consistency.** It replays the frozen engine (V2-MOM, B1, B2; 5 bps), and every previously processed session must reproduce its stored ledger hash.
6. **Record each unprocessed session.** It runs the risk checks, writes the sealed ledger `sealed/<D>.bin`, then the health record `runs/<D>.json` (the commit point).

## State layout (`$PAPER_STATE_DIR`)

| Path | Content |
|---|---|
| `runs/<D>.json` | health record: no performance |
| `sealed/<D>.bin` | encrypted ledger: positions, fills, decisions, pending orders, equity, P&L |
| `data/<D>-<sha12>/` | content-addressed, write-once input snapshot with manifest SHA-256 |
| `heartbeat.json` | last successful run |
| `last_error.json` | last failure, secrets redacted |
| `run.lock` | lock held during a run |

## Unattended operation (prepared, not activated)

`.github/workflows/paper-trading.yml` runs at 20:35 and 21:35 UTC on weekdays. It needs:
- your approval;
- a push to the default branch;
- the secrets `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `PAPER_SEAL_KEY`, `PAPER_STATE_TOKEN`;
- a `paper-state` branch in the **private** repo `Alixujaev/trade-research-data`.

A failed run or a missed session fails the job, and GitHub e-mails the owner. Each run commits the state to the private repo, so its git history is the backup.

Known limits:
- GitHub can delay scheduled jobs; catch-up absorbs this.
- GitHub disables schedules in repositories with no activity for 60 days.
- This repository is public, so the job prints health only.
