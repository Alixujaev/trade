# DAY-16 — Systematic Strategy Research Protocol v2

## 0. Status, scope and labels

| Field | Value |
|---|---|
| Status | **REVISED DRAFT (DAY-16R, revision R1) — PENDING REVIEW AND COMMIT** |
| Version | **2.0** (revision R1; not yet frozen) |
| Drafted | 2026-10-07 (DAY-16); revised 2026-10-07 (DAY-16R) |
| Repository HEAD at drafting | `f5470b13142d8d48d12cc609ea925c6e11566018` (`chore: move project to repository root`), branch `feature/day-trading-research` |
| Parent documents | v1.0 `artifacts/day14/research-protocol.md`; v1.1 `artifacts/day15/protocol-v1.1.md`. Neither is modified. v2 governs only the v2 families defined here. |
| Machine-readable twin | `artifacts/day16/research-protocol-v2.json` |
| Checklist | `artifacts/day16/research-checklist.json` |

**Freeze procedure.**
1. This document is reviewed. Review corrections are made **before** the freeze commit and before any v2 data request.
2. The user commits the three DAY-16 files. The commit SHA and the SHA-256 of each file are recorded by the first v2 task that touches data.
3. The **commit date** of that freeze commit defines the start of the forward OOS (§3.6).
4. After the freeze commit, any change is a new protocol version (v2.0.x for clarifications that change no frozen value; v2.1 for anything else). Results stay attributed to the version they were produced under.

**Label vocabulary** (every normative statement carries one):
- **EXISTING CONVENTION** — inherited from v1.0/v1.1 or from repository code, and deliberately kept.
- **PROTOCOL DECISION** — chosen for v2 in this document.
- **RATIONALE** — the methodological reason for a decision. Rationales cite general literature or reasoning, **never** this project's historical results.
- **ASSUMPTION / OPEN** — not verified; see §20.
- **NOT YET IMPLEMENTED** — required code that does not exist.

**Drafting constraints observed (DAY-16 and DAY-16R):** no market-data endpoint was called; no price, bar or return was read; no backtest, metric or statistic was computed; no code was changed. The only computation was a local `exchange_calendars` 4.13.2 XNYS session resolution (no network). DAY-04 → DAY-15H performance files were **not** opened; the only prior-result information used is the DAY-15H gate outcome stated in the task brief (gate failed), which explains why v2 exists and is never used to choose a v2 parameter.

### 0.1 Revision log
| Rev | Task | Change |
|---|---|---|
| R0 | DAY-16 | initial draft |
| R1 | DAY-16R | **Price basis corrected:** execution and accounting moved from `adjustment=all` to **raw** OHLC with explicit corporate-action events (Alpaca corporate-actions API, cross-checked); signals moved to a **point-in-time total-return index** built from raw closes and past events; `adjustment=all` demoted to audit-only (§3.4). Staged acquisition: holdout bars only after the research gate (§3.9). Execution sizing, cash-shortfall rule, pending-order supersession, segment-boundary orders, initial-portfolio rule, calendar indexing, V2-LRV mechanics, gate-C completeness semantics, holdout and diagnostic wording made exact. Q4 downgraded to NON-BLOCKING; Q16 (corporate-action event coverage) added as BLOCKING. **No strategy parameter, universe, segment date, cost, benchmark or gate threshold changed.** |

---

## 1. Infrastructure inspected and reuse assessment

### 1.1 Inspected (read-only)
- `artifacts/day15/protocol-v1.1.md` (full); `artifacts/day14/research-protocol.md` (structure); `artifacts/day14/research-checklist.json` (schema); `artifacts/day13/research-synthesis.md` (headings only).
- `config/day_universe.py`; `requirements.txt`.
- `acquisition/v1_1/{alpaca_client,contract,sessions,snapshot,ledger,validation,environment,research}.py`; `acquisition/{capture_policy,snapshot,ledger,environment}.py`.
- `backtest/metrics.py`; `data/session.py`; `data/bars.py`; `data/v11_research_loader.py`.

### 1.2 Facts that constrain v2 (VERIFIED by reading)
1. The only Alpaca SIP dataset in the repository is **intraday** (5Min/15Min, 2026-06-03 → 2026-09-25, `data/oos_cache/protocol_v1.1/research/`). It is unusable for daily strategies with multi-month formation windows. **v2 requires new Alpaca SIP 1Day bar and corporate-action acquisitions** (later tasks).
2. The existing backtest engine (`backtest/day_engine.py`, `backtest/execution.py`, `backtest/metrics.py`) is a **per-trade, intraday, one-unit-per-trade** engine with no overnight positions and no corporate-action handling. **No portfolio engine exists** (NOT YET IMPLEMENTED).
3. `backtest/metrics.py` metrics are trade/R-multiple based. Only `max_drawdown_pct` is conceptually reusable.
4. No corporate-actions client exists in the repository (NOT YET IMPLEMENTED).

### 1.3 Reusable unchanged or by pattern (INFERRED from code reading)
| Component | Reuse | Change needed for v2 |
|---|---|---|
| `acquisition/v1_1/alpaca_client.py::AlpacaBarsClient` (pagination, retries, inclusive `end`, field map) | by pattern | parameterise `timeframe=1Day`, `adjustment ∈ {raw, all}`, `asof` |
| `acquisition/v1_1/snapshot.py` (write-once parquet/json, canonical content SHA-256, location guard) | unchanged | new root `data/oos_cache/protocol_v2/` |
| `acquisition/v1_1/ledger.py` (accepted units, accounting) | by pattern | unit = (symbol, series, acquisition stage) |
| `acquisition/v1_1/environment.py::capture_v11_environment` | by pattern | v2 protocol identity |
| `acquisition/v1_1/research.py` (preflight, integrity report, protocol identity) | by pattern | v2 documents and roots |
| `acquisition/capture_policy.py` (no capture before 16:15 ET) | unchanged | applies to forward OOS |
| `exchange_calendars==4.13.2` XNYS pin (`requirements.txt`, `acquisition/v1_1/sessions.py`) | unchanged | v2 segment resolver |
| `acquisition/v1_1/validation.py` | by pattern | daily-bar structural checks (§3.8) |
| `data/session.py` (`NY_TZ`, session-date mapping) | unchanged | — |

Nothing in this list is modified by DAY-16 / DAY-16R.

---

## 2. Research universe

| Item | Rule | Label |
|---|---|---|
| Symbols | The 25 symbols of `config/day_universe.py::FROZEN_DAY_UNIVERSE`: AAPL, MSFT, NVDA, AMZN, META, GOOGL, TSLA, AVGO, AMD, QCOM, INTC, MU, AMAT, ADBE, CRM, ORCL, CSCO, COST, WMT, KO, PEP, NFLX, JNJ, JPM, XOM | EXISTING CONVENTION |
| Canonical storage | `config/day_universe.py::FROZEN_DAY_UNIVERSE` (committed); the v2 JSON repeats the list for hashing | EXISTING CONVENTION |
| Shared across strategies | **Yes.** All three strategies and benchmark B1 use exactly these 25 symbols | PROTOCOL DECISION |
| Benchmark-only symbol | **SPY** (from `MARKET_BENCHMARK_SYMBOLS`), used **only** for benchmark B2. Never ranked, never traded by a strategy. QQQ is not used | PROTOCOL DECISION |
| Entry / exit of symbols | **None.** The universe is static for every segment. No additions, removals or replacements | EXISTING CONVENTION |
| Missing data | A symbol without a required observation is **ineligible for that decision only** (§4–§6, §8.6); it is never imputed, never replaced, never removed for performance reasons. All exclusions are listed in the run report | PROTOCOL DECISION |
| Point-in-time membership | **NOT point-in-time.** The list was assembled in 2026 (first committed `dcebe47`, 2026-09-28; historical selection timestamp UNKNOWN / NOT RECORDED, v1.1 O3) from present-day US mega/large caps | ASSUMPTION / OPEN (disclosed) |
| Survivorship / hindsight | **Known limitation, not solved.** This is a **hindsight-selected universe**: a 2026 list of surviving, currently large companies applied to 2016–2026 data. Every symbol is known to have survived and to be large *today*, which favours long-only strategies and plausibly momentum in particular. Benchmark B1 shares the bias, so relative comparisons are partly — **not fully** — protected; **B1 does not eliminate survivorship bias.** No v2 result may be described as survivorship-safe or as representative of a point-in-time investable universe | ASSUMPTION / OPEN (disclosed, §20 Q5) |
| Delistings | None of the 25 delisted in the period, **by construction** (the list contains survivors). This is the bias above, not evidence of its absence | disclosed |
| Ticker changes | META traded as **FB** before 2022-06-09. Historical bars and corporate actions for META before that date must be obtained via Alpaca's symbol mapping (`asof`). Coverage is NOT VERIFIED | ASSUMPTION / OPEN (§20 Q3, BLOCKING) |
| Corporate actions | Several symbols split during the data period (e.g. AAPL 2020; AMZN, GOOGL, TSLA 2022; NVDA, AVGO, WMT 2024 — general public knowledge, not read from data). Handled by §3.4 and §11; a corporate action is never a signal | PROTOCOL DECISION |

---

## 3. Data

### 3.1 Provider contract (PROTOCOL DECISION)
| Item | Value |
|---|---|
| Provider | Alpaca Market Data API — **unchanged provider** (EXISTING CONVENTION) |
| Bars endpoint | `GET /v2/stocks/{symbol}/bars`, `feed=sip` (EXISTING CONVENTION), `timeframe=1Day` |
| Bar series acquired | **`adjustment=raw`** (canonical for execution, accounting and as input to the signal index) and **`adjustment=all`** (audit only) — §3.4 |
| Corporate-action events | Alpaca corporate-actions endpoint (exact endpoint and version recorded by the acquisition task): forward/reverse splits (ex-date, ratio) and cash dividends (ex-date, cash amount per share, regular and special) for the 25 symbols + SPY — §3.4, §20 Q16 |
| Symbol mapping | `asof` fixed to the acquisition date and recorded (§20 Q3) |
| Bounds | explicit `start` / `end` (UTC RFC-3339) on every bar request; **`end` is inclusive** (EXISTING CONVENTION, v1.1 §2) |
| Symbols | 25 universe symbols + SPY |
| Credentials | `.env` `ALPACA_API_KEY` / `ALPACA_SECRET_KEY`; never printed, logged or stored (EXISTING CONVENTION) |
| Excluded providers | yfinance, Massive, or any back-fill. No v2 bar or event may come from another provider (EXISTING CONVENTION) |
| Storage | write-once tree `data/oos_cache/protocol_v2/` (git-ignored), never `data/cache/`, never `protocol_v1.0/` or `protocol_v1.1/` |

### 3.2 Daily vs intraday
v2 is **daily only**. Signals use daily closes; fills use daily opens. No intraday bar is used by any v2 strategy. (PROTOCOL DECISION. RATIONALE: the three families are defined in the literature on daily or lower frequency; intraday data would add microstructure choices not needed to test them.)

### 3.3 Calendar, timezone, sessions, indexing, bar and timestamp semantics
- Calendar: `exchange_calendars` 4.13.2, `XNYS`; sessions in America/New_York (EXISTING CONVENTION).
- **Session index (PROTOCOL DECISION):** every `t`, `t−k`, `t+1` in this protocol is an index into the **XNYS calendar session sequence**, not into a symbol's row sequence. If a symbol has no bar at a required index, that observation is **missing**; there is **no** fallback to the nearest available row.
- A 1Day bar is assigned to exactly one XNYS session date. Storage: tz-aware UTC index as returned, plus an explicit `session_date` column derived deterministically in America/New_York (PROTOCOL DECISION).
- **Information availability (PROTOCOL DECISION):** the session-`t` **close** is usable only after 16:00 ET of `t` (13:00 ET on early-close days). A corporate-action event with ex-date `d` is usable from the start of session `d` (before its open). The session-`t+1` **open** is used only as a fill price for orders decided at or before the close of `t`; it is never a signal input.
- **Bar semantics — ASSUMPTION / OPEN (§20 Q1, BLOCKING):** it is NOT VERIFIED whether Alpaca SIP 1Day `open`/`close` equal the primary-listing official opening/closing auction prints or the first/last consolidated trade, and whether extended-hours trades are included in OHLC. The acquisition task must verify this from documentation and a structural probe **before any v2 research run**. If 1Day OHLC includes extended-hours trades, the protocol must be amended (v2.0.x) before any run; it is never "corrected" after results.
- Early closes: a daily bar on an early-close session is a normal session bar.

### 3.4 Price series and corporate-action policy (PROTOCOL DECISION; revised R1)

Three series with strictly separated roles:

| Role | Series | Allowed uses | Forbidden uses |
|---|---|---|---|
| **A. Trading / execution / accounting** | **raw OHLC** (`adjustment=raw`): `O_i(k)`, `C_i(k)` | fill prices (raw open), position marking (raw close), share quantities, costs, equity, benchmarks | — |
| **B. Signal / return series** | **PIT total-return index** `TR_i(k)` built from raw closes and events with ex-date ≤ k (formula below) | every strategy signal (§4–§6), ranking, volatility, pair formation, spreads | fills, marking, accounting; any use of price *levels* |
| **C. Corporate-action audit** | `adjustment=all` bars (`C^all_i(k)`) and the event list | the implied-factor cross-check below; disclosure | **any** signal, fill, mark, weight or P&L input |

**Why (RATIONALE):** a historically *adjusted* price at date `k` is the raw price rescaled by every corporate action that occurred **after** `k` up to the acquisition date. Its level was never observable at `k`; filling or marking at it uses future corporate-action information and fills at prices that never traded. Raw OHLC are the prices actually observable at `k`. Signals need return continuity across splits and dividends, which the PIT index provides using only events already effective at `k`.

**Events (from the Alpaca corporate-actions endpoint):** for symbol `i` and session `k`:
- `q_i(k)` = split ratio effective at ex-date `k` (new shares per old share; forward split > 1, reverse split < 1); `q = 1` when no split;
- `d_i(k)` = cash dividend per share with ex-date `k`, expressed **per share held at the close of the previous session** (pre-split basis if a split shares the ex-date); `d = 0` when none. Regular and special cash dividends are both included.
- Any other event type (spin-off, stock dividend not expressible as a split, merger, rights) for a universe symbol in an acquired range is a **BLOCKING data review** before any run; it is never ignored silently.

**PIT total-return index (series B):**
- `TR_i(k₀) = 1` at the symbol's first available close in the snapshot.
- For each later session `k` with a bar, with `p` = the previous session with a bar for `i`:
  `TR_i(k) = TR_i(p) · ( C_i(k) · Q_i(p,k) + D_i(p,k) ) / C_i(p)`,
  where `Q_i(p,k)` = product of `q_i` over ex-dates in `(p, k]`, and `D_i(p,k)` = sum over ex-dates `e` in `(p, k]` of `d_i(e)` multiplied by the product of `q_i` over ex-dates in `(e, k]` (dividend cash carried in post-split share units). For `p = k−1` with one event this reduces to `TR(k) = TR(k−1)·(C(k)·q(k) + d(k))/C(k−1)`.
- `TR_i(k)` is undefined (missing) where `C_i(k)` is missing.
- Only **ratios** of `TR` are meaningful; every signal uses ratios only. Because `TR` is chain-linked forward in time from data effective at each date, `TR_i(k)` depends only on raw closes and events with ex-date ≤ k (point-in-time by construction).
- Implied treatment: series B assumes dividend reinvestment for *signal* purposes only. Accounting (series A) credits dividends as cash (§11).

**Cross-check (series C, data only, never results):** per symbol, `f_i(k) = C_i(k) / C^all_i(k)`. Every session where `f` changes by more than a numerical tolerance of 1e-6 (relative) must coincide with an event in the event list, and every event must coincide with a change in `f`; split events must match the factor change ratio to within 0.1 %. Any mismatch is a **BLOCKING data review** decided before any research run and documented. The meaning of `adjustment=all` is needed only to interpret mismatches (§20 Q4, NON-BLOCKING).

No symbol-session is excluded because of a corporate action (EXISTING CONVENTION).

### 3.5 Data period and warmup
- Alpaca SIP historical coverage is assumed to start in **2016** (ASSUMPTION / OPEN, §20 Q2, BLOCKING verification).
- Data request start: **2016-01-04** (first XNYS session of 2016; VERIFIED locally by calendar).
- Warmup/formation-only data: 2016-01-04 → 2017-01-31 (272 sessions). No trade, no evaluation.
- Required lookbacks (§4–§6): 252 sessions (momentum, relative-value formation), 60 returns / 61 closes (reversal volatility).

### 3.6 v2 timeline (PROTOCOL DECISION; user-approved structure)

Rule (authoritative; dates are its resolution with `exchange_calendars` 4.13.2 XNYS, resolved locally 2026-10-07):

| Segment | Rule | First | Last | Sessions | Role |
|---|---|---|---|---|---|
| Warmup / formation history | XNYS sessions from 2016-01-04 to the last session before Research | 2016-01-04 | 2017-01-31 | 272 | inputs only |
| **Research** | XNYS sessions in [2017-02-01, 2022-12-30] | 2017-02-01 | 2022-12-30 | **1490** | research gate (§13) |
| **Holdout (historical pseudo-OOS)** | XNYS sessions in [2023-01-03, 2026-06-02] | 2023-01-03 | 2026-06-02 | **856** | one-shot holdout gate (§15) |
| **Excluded** | XNYS sessions from 2026-06-03 to the freeze-commit date, inclusive | 2026-06-03 | commit date | 88 if committed 2026-10-07 | formation history only; **never evaluated** |
| **Forward OOS (true OOS)** | the **252** XNYS sessions starting at the first session strictly after the freeze-commit date | commit + 1 session | +251 sessions | **252** | final validation (§15) |

Example only: if the freeze commit is dated 2026-10-07, forward OOS = 2026-10-08 → 2027-10-08.

RATIONALE:
1. **Research starts 2017-02-01**, not 2017-01-03: the first momentum decision needs `TR(t−252)`; for a signal on 2016-12-30 that index lies before 2016-01-04 (verified locally: index −1), while for the signal on 2017-01-31 it is 2016-02-01. 2017-02-01 is therefore the first month-start at which every strategy has a complete lookback inside the assumed Alpaca coverage. It is a data-availability rule, not a performance choice.
2. **Research ends / holdout starts at the calendar-year boundary 2022/2023**, fixed by calendar before any v2 data exists.
3. **Holdout ends 2026-06-02**, the last session before the earliest data this project has already viewed (v1.1 warmup starts 2026-06-03). Sessions from 2026-06-03 onward were seen (intraday, by the day-trading research) and are therefore **excluded from every v2 evaluation**.
4. **The holdout is pseudo-OOS, not OOS, and is intentionally not blind.** Its data predate this protocol, and the protocol authors have general knowledge of 2023–2026 market history (for example, which large caps rallied); the universe itself was selected with hindsight. A holdout pass is labelled HOLDOUT-PASSED, never "validated".
5. **Forward OOS is the only true OOS**: its sessions do not exist when the protocol is frozen. 252 sessions ≈ one year: 12 momentum rebalances, ≈ 52 reversal rebalances, exactly 2 relative-value trading periods. It is short (§20 Q11); its length is fixed now and is never extended or shortened after looking. **No data dated after the freeze commit may be acquired or inspected before the forward period has ended** (§3.9).

### 3.7 Embargo (PROTOCOL DECISION)
- **No session embargo between Research and Holdout, or between Excluded and Forward.**
- RATIONALE: each segment is simulated as a separate run that **starts flat** (all cash) at its first session and is **liquidated at its last close** (§11). No position, label or holding-period return crosses a segment boundary. Lookback/formation windows may read earlier sessions; that is past, already-observable data and is PIT-legal. The Excluded segment handles v2's information-set problem (2026-06-03 → commit) explicitly.

### 3.8 Data-quality policy (PROTOCOL DECISION)
Structural checks per symbol × series:

| Check | Outcome on failure |
|---|---|
| exactly one bar per XNYS session where a bar exists; no bar on a non-session date | off-calendar bar → **HARD FAIL** (stop, review) |
| duplicate timestamps / duplicate session dates | **HARD FAIL** |
| monotonic increasing index, tz-aware UTC | **HARD FAIL** |
| OHLC consistency (`low ≤ min(open, close)`, `high ≥ max(open, close)`, all > 0) | **HARD FAIL** |
| volume ≥ 0 | **HARD FAIL**; zero-volume count reported |
| missing sessions (session in calendar, no bar) | **listed**, never imputed; handled by §3.3 and §8.6 |
| raw vs all session-date sets identical | mismatch → **HARD FAIL** |
| corporate-action cross-check (§3.4) | mismatch → **BLOCKING data review** |
| unsupported corporate-action type (§3.4) | **BLOCKING data review** |
| first available bar per symbol ≤ 2016-01-04 + 5 sessions (research acquisition) | otherwise **BLOCKING review** (coverage, §20 Q2) |

A symbol missing more than **2 %** of the sessions of any evaluated segment triggers a **BLOCKING data review before the run** (PROTOCOL DECISION; RATIONALE: mega-caps should have essentially complete daily coverage; widespread gaps indicate an acquisition defect, not a market event). Review outcomes are decided on data, never on results.

### 3.9 Staged acquisition, data revision, snapshots and PIT (PROTOCOL DECISION; revised R1)
- Write-once snapshots, content and file SHA-256, `run.json`/`environment.json`, derived manifest; overwrite forbidden (EXISTING CONVENTION, v1.1 §17/§23). Each stage stores raw bars, `all` bars and the corporate-action event list.
- **Stage R (research):** acquired after the freeze commit: bars and events **2016-01-04 → 2022-12-30**.
- **Stage H (holdout):** acquired **only after** the research gate has been recorded for all three families **and only if at least one family is RESEARCH-PASSED**: bars and events **2021-01-04 → 2026-06-02** (includes ≥ 252 sessions of lookback before 2023-01-03, so the holdout run reads a single snapshot).
- **Stage F (forward):** acquired **only after** the forward period has ended (not before 16:15 ET of its last session, `capture_policy`) and only if at least one family is HOLDOUT-PASSED: bars and events **2025-01-02 → last forward session** (≥ 252 sessions of lookback before any forward start in 2026 or later). **No interim forward data is acquired or inspected.**
- **One snapshot per run:** each evaluation run reads exactly one stage's snapshot.
- **Overlap control:** raw bars and events in overlapping ranges of different stages (R∩H = 2021-01-04 → 2022-12-30; H∩F = 2025-01-02 → 2026-06-02) are compared cell by cell: IDENTICAL or DISCREPANCY (EXISTING CONVENTION). A DISCREPANCY is reported and investigated before the later run; originals are never overwritten. `adjustment=all` levels are **expected** to differ between stages (rebasing) and are excluded from this comparison; their implied factors are re-checked per stage instead.
- A decision at session `t` may use only bars with `session_date ≤ t` (close-derived fields) and events with ex-date ≤ t; the execution at `t+1` uses only the `t+1` raw open and events with ex-date `t+1` (§8, §11).

---

## 4. Strategy A — Cross-sectional momentum (family `V2-MOM`)

`TR_i(k)` = series B (§3.4); indices are XNYS calendar indices (§3.3).

| Item | Frozen specification |
|---|---|
| Signal session `t` | the **last XNYS session of each calendar month** (America/New_York dates) |
| Ranking timestamp | after the close of `t` |
| Signal | `MOM_i(t) = TR_i(t−21) / TR_i(t−252) − 1`. The close of `t` and closes `t−20 … t` are **not** used |
| Eligible | `TR_i(t−21)` and `TR_i(t−252)` both defined (bars present at those exact indices) |
| Ranking | descending `MOM_i`; ties broken by ascending ticker |
| Selected | top **5** eligible symbols; if fewer than 5 are eligible, all eligible are selected and the remaining target weight is cash |
| Target weights | **0.20** for each selected symbol; **0** for every other symbol (including current holdings that are no longer selected) |
| Rebalance (execution) timestamp | market-on-open at session `t+1` (the first session of the next month) (§8) |
| Existing holdings | a holding that remains selected is **resized to 0.20** of `E_open` (§11.3); a holding no longer selected is **sold in full**; a newly selected symbol is **bought** to 0.20 |
| Holding interval | from the execution open at `t+1` to the next execution open (≈ 21 sessions); no trading in between |
| Cash between rebalances | allowed and expected: cash arises from unselected weight, cancelled buys (§8.6), the cost scaling `λ` (§8.4) and dividends credited as cash (§11); cash is **not** reinvested before the next scheduled rebalance |
| Missing data | ineligible for ranking per above; missing open at `t+1` → §8.6 |
| Turnover / costs | §11.4 and §9, on actual traded notional |

RATIONALE (literature, not project results): cross-sectional momentum over the past 12 months excluding the most recent month (Jegadeesh & Titman 1993; Fama–French UMD "2–12") is the canonical specification. Skipping the latest month separates momentum from the documented one-month reversal. 252/21 sessions are the standard trading-day equivalents of 12/1 months. Top-quintile selection (5 of 25) and monthly rebalancing are the standard portfolio sort. Equal weighting avoids a second signal. No alternative lookback is tested.

---

## 5. Strategy B — Short-term mean reversion, long-only (family `V2-STR`)

| Item | Frozen specification |
|---|---|
| Signal session `t` | the **last XNYS session of each ISO calendar week** (Monday–Sunday, America/New_York dates) |
| Ranking timestamp | after the close of `t` |
| 5-session return | `r5_i(t) = TR_i(t) / TR_i(t−5) − 1` (the close of `t` **is** included) |
| Daily returns | `R_i(k) = TR_i(k) / TR_i(k−1) − 1` (simple **daily** total returns) |
| Volatility | `σ_i(t)` = sample standard deviation (ddof = 1) of the **60 daily returns** `R_i(k)`, `k = t−59 … t` (uses closes `t−60 … t`; the current return `R_i(t)` **is** included). `σ_i` is **daily** volatility; it is re-estimated at every signal session (rolling, not frozen) |
| Centring | `r̄5(t)` = arithmetic mean of `r5_j(t)` over the **eligible symbols at the same `t`** (a cross-sectional mean, not a historical average) |
| Signal | `z_i(t) = (r5_i(t) − r̄5(t)) / (σ_i(t) · √5)` |
| Eligible | all 61 closes `TR_i(t−60 … t)` defined **and** `σ_i(t) > 0` |
| Ranking | ascending `z_i` (most negative = relatively weakest); ties broken by ascending ticker |
| Selected | the **5** lowest-`z` eligible symbols (fewer eligible → all eligible, remainder cash) |
| Target weights | **0.20** each; 0 for all others |
| Rebalance (execution) timestamp | market-on-open at `t+1` (the first session after `t`, normally the first session of the next week) |
| Existing holdings | resized to 0.20 if still selected; sold in full if not; new selections bought |
| Holding interval | from the execution open to the next execution open (≈ 5 sessions) |
| Unconditional | always targets the 5 relatively weakest names; there is no absolute-return entry threshold |
| Exit | only by non-selection at a rebalance or at segment end (§11.6); no stop |
| Missing data / cash | as §4 |
| Turnover / costs | §11.4 and §9; **turnover, cost per execution and cost drag are first-class outputs** (§12) |

RATIONALE: weekly cross-sectional reversal is the canonical short-horizon reversal (Lehmann 1990; Lo & MacKinlay 1990; Jegadeesh 1990 for the monthly analogue). Centring on the same-day cross-sectional mean makes the signal *relative* weakness rather than a market-wide move. Dividing by `σ√5` scales the 5-day move by the stock's own 5-day volatility (√5 converts daily to 5-day scale under an i.i.d. approximation) so selection is not mechanically dominated by the highest-volatility names. 60 sessions (~3 months) is a conventional short volatility window. The long-only form buys the losers' side only; it is not a long-short reversal portfolio. Short-horizon reversal is highly cost-sensitive, so net-of-cost results and turnover are mandatory outputs.

---

## 6. Strategy C — Long-only relative value (family `V2-LRV`)

### 6.1 What "relative value" means here (RATIONALE; disclosed)
Classical pairs trading (Gatev, Goetzmann & Rouwenhorst 2006, "GGR") is **long-short**: it buys the cheap leg *and* shorts the rich leg, an approximately market-neutral spread bet. **V2-LRV is not that strategy and is not market-neutral.** It keeps GGR's *relationship identification* (distance method) and *divergence trigger*, but it only **buys the relatively undervalued (lagging) member** of a historically co-moving pair. Each position is a **single long stock** whose return is the stock's full return: market exposure plus whatever relative-value component exists. V2-LRV is a **conditional long-only stock-selection strategy**; its results must not be compared with published long-short pairs results.

**Residual market exposure (disclosed and measured):** an invested slot carries the market exposure of the held stock (beta ≈ 1 for these mega caps, not estimated); a flat slot is cash. Portfolio exposure (Σ weights) therefore varies between 0 and 1 and is **reported every session** (§12). A positive result may come from market exposure rather than relative value; the B1 comparison and the exposure report are the protection against mistaking one for the other.

### 6.2 Specification

Notation: `p_0 … p_125` = the 126 sessions of a trading period; `t_F` = the session immediately before `p_0` (the **formation close**); formation window `F = {t_F − 251, …, t_F}` (252 sessions), `F_0 = t_F − 251`.

| # | Item | Frozen specification |
|---|---|---|
| 1 | Normalisation method | price relative to the first formation session, computed on series B |
| 2 | Normalisation window | the 252-session formation window `F` |
| 3 | Normalised formation price | `N_i(k) = TR_i(k) / TR_i(F_0)`, `k ∈ F` |
| 4 | Eligibility | `TR_i(k)` defined for **all** 252 `k ∈ F` |
| 5 | Distance | `SSD_ij = Σ_{k∈F} (N_i(k) − N_j(k))²` over all eligible unordered pairs, written with `ticker_i < ticker_j` |
| 6 | Pair selection | sort pairs by ascending `SSD`; ties by (ticker_i, ticker_j) ascending. **Greedy disjoint:** take the first pair, remove both symbols from the candidate set, repeat until **5 pairs** are chosen or no pair remains (fewer pairs → unused slots stay cash) |
| 7 | Formation spread scale | `σ_ij` = sample std (ddof = 1) of `D_ij(k) = N_i(k) − N_j(k)` over `k ∈ F`; **frozen at formation** and never re-estimated during the trading period |
| 8 | Trading-period normalisation | `M_i(t) = TR_i(t) / TR_i(t_F)` (rebased to 1 at the formation close) for `t ∈ {p_0 … p_125}` |
| 9 | Spread and sign | `S_ij(t) = M_i(t) − M_j(t)` with `ticker_i < ticker_j`; `S_ij(t_F) = 0` by construction. (GGR convention: σ is estimated on the formation-normalised spread `D`, the trading spread is rebased at `t_F`; both are stated deliberately.) |
| 10 | Trigger | **strict** inequality `|S_ij(t)| > 2 · σ_ij`, evaluated at the close of `t` |
| 11 | Lagging member | `j` if `S_ij(t) > 0`; `i` if `S_ij(t) < 0` (the member with the lower `M(t)`) |
| 12 | Entry window | entry signals are evaluated only at the closes of `p_0 … p_124`; an entry signal at the close of `t` executes at the open of `t+1` (§8) |
| 13 | Entry | if the slot is flat **and has no pending order**, and the trigger holds: buy the lagging member with the **entire slot capital** (§11.3) |
| 14 | Exit (convergence) | a position opened when the spread sign was `s₀ = sign(S_ij)` at the entry-signal close is exited when, at a close `t ∈ {p_0 … p_124}`, `s₀ · S_ij(t) ≤ 0`; sell at the open of `t+1` |
| 15 | Exit (period end) | any position still open after the close of `p_125` is sold at the open of the next session (`p_126`, which is the first session of the next cycle). If `p_125` is the segment's last session, the position is liquidated by the segment-end rule (§11.6) |
| 16 | Same-close exit and entry | on a close where a slot's exit condition fires, **no entry signal is evaluated for that slot**; entry evaluation resumes at the next close after the slot is flat |
| 17 | Holding while other signals appear | while a slot holds a position, further entry triggers for that slot are ignored; signals of other slots are independent |
| 18 | Simultaneous triggers | slots are independent and their symbols are disjoint, so several slots may enter or exit at the same open without conflict; within one open all sells precede buys (§8.4) |
| 19 | Pair weight / portfolio weight | each slot invests its whole slot capital in one stock or holds it as cash; a slot's portfolio weight is its value ÷ equity (≈ 0.20 at period start, then drifting) |
| 20 | Slot capital | at the open of `p_0` (after any exits of the previous cycle and their costs) equity `E_open(p_0)` is split into **5 equal slot capitals**; each slot's capital then evolves with its own P&L, costs and dividends; slots never lend to each other |
| 21 | Cycles | sequential, non-overlapping. The next cycle's formation close is `p_125`; its `p_0` is the session after `p_125` |
| 22 | First / last cycle in a segment | the first cycle's `t_F` is the session immediately before the segment's first session; the last cycle is truncated at the segment's last session (no entry evaluated at the segment's last close; open positions liquidated per §11.6) |
| 23 | Pair composition frozen | the 5 pairs and their `σ_ij` are fixed for the whole trading period |
| 24 | Re-entry | allowed within the same trading period after an exit, under rows 12–13 |
| 25 | Missing data | no entry/exit **signal** at a close where either member's `TR` is undefined; an existing position is held and marked per §11.5 |
| 26 | Turnover / costs | each entry and exit is traded notional (§11.4, §9) |

RATIONALE: GGR's distance method (12-month formation, 6-month trading, 2σ trigger, close on convergence) is the most widely replicated, assumption-light pair-formation procedure; it needs no cointegration test or hedge ratio. 252/126 sessions are the trading-day equivalents of 12/6 months. **Deviations from GGR, decided here (not from results):** (a) long-only (lagging member only), (b) 5 pairs, matching the 5-name portfolios of A and B, (c) **disjoint** greedy selection, so no symbol occupies two slots in a 25-name universe, (d) non-overlapping sequential cycles rather than GGR's monthly-staggered overlapping portfolios.

### 6.3 Formation / evaluation separation for V2-LRV
- Pair choice and `σ_ij` use only `TR` at sessions in `F` (all ≤ `t_F`), known after the close of `t_F`.
- Trading-period signals use `TR` at `t_F` and at `t` (≤ the decision close) and the frozen pair parameters.
- A later cycle's formation window overlaps earlier trading periods; that is past data at its use time and is PIT-legal.

---

## 7. Formation / evaluation separation and PIT (all strategies)

**Answer to "at exactly what timestamp is every model input known?" (PROTOCOL DECISION):** every signal input is a function of series-B values `TR_i(k)` for sessions `k ≤ t`, which depend only on raw closes `C_i(k ≤ t)` and corporate-action events with ex-date ≤ t; all are known after the close of `t` (16:00 ET; 13:00 ET on early closes). Every trade decided from those inputs executes at the raw **open of `t+1`**. No signal uses an open, high, low or volume, any series-C value, or any datum dated after `t`.

| Quantity | Observations available at decision time `t` | Includes `t`? | Rolling or frozen |
|---|---|---|---|
| V2-MOM signal | `TR(t−252)`, `TR(t−21)` | **No** | recomputed each month-end |
| V2-STR `r5` | `TR(t−5)`, `TR(t)` | **Yes** | recomputed each week-end |
| V2-STR `σ` | `TR(t−60 … t)` (60 daily returns) | **Yes** | rolling 60-return window, recomputed each week-end |
| V2-STR `r̄5` | same-`t` cross-section of `r5` | **Yes** | recomputed each week-end |
| V2-LRV pairs, `SSD`, `σ_ij` | `TR(t_F−251 … t_F)` | **Yes** (`t_F`) | **frozen** for the 126-session trading period |
| V2-LRV `S(t)` | `TR(t_F)`, `TR(t)` | **Yes** | evaluated daily |
| Ranking (A, B) | same-`t` signal values, ticker for ties | **Yes** | per signal session |
| Target weights | fixed constants (0.20) or slot rules | — | — |
| Execution sizing | raw opens of `t+1`, cash, holdings after `t+1` events (§11.3) | execution-time only | per execution |

Mandatory tests before any v2 result is accepted (NOT YET IMPLEMENTED):
1. **Future-mutation test:** for randomly chosen decision dates, altering or deleting all bars and events dated after `t` must not change any decision made at `t`.
2. **Truncation test:** running a strategy on data truncated at `t` produces exactly the decisions made at `t` in the full run.
3. **Fill-source test:** every fill price equals the **raw** open `O_i(t+1)` of series A; no fill or mark ever reads series B or C.
4. **Index test:** `TR_i(k)` computed on data truncated at `k` equals `TR_i(k)` computed on the full snapshot.

---

## 8. Execution model (shared; PROTOCOL DECISION; revised R1)

| Item | Rule |
|---|---|
| 8.1 Signal timestamp | close of session `t` (after 16:00 ET / 13:00 ET early close) |
| 8.2 Order timestamp | after the close of `t`, before the open of `t+1`; market-on-open orders expressed as **target weights** (A/B) or **slot actions** (C) |
| 8.3 Fill price | **raw open** `O_i(t+1)` (series A). Never a series-B or series-C value |
| 8.4 Order of operations at each open | (1) apply corporate-action events with ex-date `t+1` (§11.2); (2) compute `E_open` (§11.3); (3) convert target weights / slot actions into trade notionals; (4) execute **all sells** at the raw open, cash += proceeds·(1 − s); (5) execute **buys**: with total buy notional `B` and available cash `K`, every buy is scaled by `λ = min(1, K / (B·(1 + s)))`, cash −= λ·B·(1 + s). `λ < 1` can arise from costs and from overnight price moves; it is reported per execution |
| 8.5 Same-bar restriction | a decision at `t` never fills at any price of `t` |
| 8.6 Missing bar at the execution open | **buy** for that symbol: **cancelled**; its target weight stays in cash until the next scheduled decision (A/B) or the slot's next signal (C). **sell** for that symbol: becomes a **pending sell**, retried at each subsequent open at which the symbol has a bar, until filled or **superseded** by a newer decision for the same symbol (A/B: the next rebalance's target replaces it; C: none exists because the slot is not re-evaluated while a sell is pending). A retry is a pre-committed instruction and reads no information after its decision close, so it creates no look-ahead; it does not change the intended signal |
| 8.7 Gaps | the open is the fill whatever the overnight gap; no stops, no limit prices |
| 8.8 Market close handling | no orders at the close; closes are used only for signals and marking |
| 8.9 Forced exits | only (a) not selected at rebalance (A/B), (b) convergence or period end (C), (c) segment end (§11.6). No stop-loss, no take-profit |
| 8.10 Overnight | positions are held overnight and across weekends/holidays (unlike v1.x) |
| 8.11 Position overlap | at most **one position per symbol per strategy**; strategies are simulated independently (no cross-strategy netting) |
| 8.12 Simultaneous signals | A/B: one combined target-weight vector per execution. C: independent slots over disjoint symbols. Processing order within an open: sells, then buys, each in ascending ticker order (affects nothing but log order) |
| 8.13 Partial fills | **none**: every unscaled order fills in full (fractional shares; mega-cap liquidity assumption, §20 Q6); `λ` scaling is the only reduction |
| 8.14 Initial portfolio | at the segment's first session: **every strategy evaluates its own signal formula at the session immediately before the segment start**, even if that session is not on the strategy's regular schedule (V2-STR, and V2-LRV formation close), and executes at the segment's first open. Thereafter the regular schedule applies |
| 8.15 Segment boundaries | decisions taken at the segment's **last** close are discarded (their execution would fall outside the segment); pending orders at segment end are discarded; open positions are handled by §11.6 |

RATIONALE: next-open execution at raw prices is the simplest rule that makes look-ahead structurally impossible for close-based signals and fills only at prices that actually traded.

---

## 9. Transaction-cost model (PROTOCOL DECISION; scenarios EXISTING CONVENTION)

| Scenario | Per side `s` | Role |
|---|---|---|
| 0 bps | 0 | gross reference |
| **5 bps** | 0.0005 | **primary friction scenario** |
| 10 bps | 0.0010 | stress scenario |

- Cost of an execution = `s × Σ_i |traded notional_i|` (raw open × shares traded), buys and sells alike, deducted from cash at that open (§8.4).
- Initial portfolio construction and final liquidation are charged (§11.6). Benchmarks are charged identically on their own trades (§10).
- Each scenario is a **separate deterministic simulation** (costs change the equity path and therefore later notionals).
- Commission is folded into the per-side rate; no spread or market-impact model (EXISTING CONVENTION). Corporate-action events are not trades and carry no cost.
- 5 bps is a **predefined friction scenario**, not a profitability threshold or an estimate of true cost.
- Costs are never changed after results (EXISTING CONVENTION).

---

## 10. Benchmarks (PROTOCOL DECISION)

| ID | Definition | Role |
|---|---|---|
| **B1** | **Equal-weight buy-and-hold of the same 25 symbols**, simulated by **the same engine and accounting as the strategies** (§8, §11): at the segment's first open, target weight 1/n in each of the `n` symbols with a bar on that session (others excluded for the segment and listed); **no rebalancing** (weights drift); splits adjust shares; dividends are credited as **cash and not reinvested**; same `λ` rule; same cost scenario on the initial buy and the final liquidation; same marking and missing-data rules | **primary comparison; used in the economic gate (§13.B)** |
| **B2** | **SPY buy-and-hold**: 100 % target weight in SPY at the segment's first open, same engine, accounting and costs | broad-market reference only; **not gated** |

- Computed for every segment and every cost scenario, over exactly the strategy's sessions.
- Benchmarks are fixed here and never changed or added after results, and are never used to describe a strategy positively beyond the numbers.

---

## 11. Portfolio model and accounting (PROTOCOL DECISION; revised R1)

**Single price basis:** holdings are share quantities valued at **raw** prices (series A). Series B never enters accounting; series C never enters anything except the audit.

| Item | Rule |
|---|---|
| 11.1 Accounting | daily equity curve `E(k) = cash(k) + Σ_i shares_i(k) · mark_i(k)` at each session close; one independent simulation per (strategy or benchmark, segment, cost scenario) |
| 11.2 Corporate actions (start of session `k`, before the open) | for every event with ex-date `k`: **split** — `shares_i ← shares_i · q_i(k)` (no cash or P&L effect); **cash dividend** — `cash ← cash + shares_i(k−1 close) · d_i(k)` using the shares held at the previous close (pre-split basis per §3.4). Dividends are credited on the **ex-date** (pay-date lag ignored, §20 Q9) and stay in cash until the next scheduled trade |
| 11.3 Sizing | at each execution open: `E_open = cash + Σ_i shares_i · v_i`, where `v_i = O_i(k)` if the symbol has a bar at `k`, else its last mark (§11.5). Target notional `= w_i^target · E_open` (A/B) or slot capital (C); trade notional = target notional − `shares_i · O_i(k)`; quantities = notional / `O_i(k)` |
| 11.4 Turnover | per execution: `TO = ½ · Σ_i |executed trade notional_i| / E_open`; annual turnover = Σ TO / (segment sessions / 252) |
| 11.5 Marking | `mark_i(k) = C_i(k)` if a bar exists; otherwise the last available close `C_i(p)` divided by `Q_i(p, k)` (the product of split ratios since `p`), so a split during a missing-bar spell does not distort value |
| 11.6 Segment start / end | each segment starts 100 % cash (`E_0 = 100,000`) before its first open; at the segment's last close all positions are marked and a liquidation cost `s × Σ_i shares_i · mark_i` is deducted; `E_T` is the post-liquidation equity; pending orders are discarded |
| 11.7 Leverage / cash | `cash ≥ 0` at all times (guaranteed by `λ`); no borrowing, no shorting, no margin; cash earns **0 %** (§20 Q7) |
| 11.8 Max simultaneous positions | A: 5; B: 5; C: 5 (one per slot); B1: 25; B2: 1 |
| 11.9 Fractional shares | **assumed** (disclosed, §20 Q8) |
| 11.10 Rounding | no share rounding; values in float64; rounding only at presentation |
| 11.11 Commission / slippage | folded into §9 per-side rate |
| 11.12 Determinism | no randomness; all ties resolved by ticker order; no seeds required |

---

## 12. Metrics (frozen before implementation)

Notation: daily simple portfolio returns `r_d = E(d)/E(d−1) − 1` from consecutive close-marked equity (the first uses `E_0`; the last uses post-liquidation `E_T`); `N` = number of sessions in the segment; `E_0` = 100,000.

**Primary metric (PROTOCOL DECISION):** **net CAGR at 5 bps per side** = `(E_T / E_0)^(252 / N) − 1` from the 5 bps simulation.

| Secondary metric | Definition |
|---|---|
| Gross CAGR | as primary, 0 bps simulation |
| Net CAGR @10 bps | as primary, 10 bps simulation |
| Volatility | `std(r_d, ddof=1) × √252` |
| Sharpe | `mean(r_d) / std(r_d, ddof=1) × √252`, risk-free = 0 (disclosed) |
| Sortino | `mean(r_d) / sqrt(mean(min(r_d, 0)²)) × √252` |
| Max drawdown | max peak-to-trough decline of close-marked equity |
| Calmar | CAGR / |max drawdown| (same cost scenario) |
| Turnover | per execution `TO`; mean per execution; annual turnover (§11.4) |
| Executions | count of opens with ≥ 1 fill; mean and min `λ` |
| Cost per execution / cost drag | total costs ÷ executions; cost drag = gross CAGR − net CAGR (5 and 10 bps) |
| Dividends | total dividend cash credited |
| Positions | number of position episodes (contiguous holding of one symbol); mean simultaneous positions |
| Exposure | mean, min and max of daily `Σ_i shares_i · mark_i / E` |
| Episode statistics (secondary, descriptive) | per position episode net return: win rate, mean, median, profit factor (Σ gains / |Σ losses|) |
| Benchmark | B1 and B2 CAGR (same scenario); strategy − B1 CAGR; tracking error `std(r_d − r_d^B1, ddof=1)·√252`; information ratio |
| Worst period | worst calendar month and worst calendar year return |
| Subperiods | all metrics above per calendar year (partial first/last years labelled) |
| Symbol breadth | share of symbols ever held whose cumulative P&L contribution is > 0 |
| Concentration | top-2 symbols' share of Σ|P&L contribution|; HHI of time-averaged weights |
| Statistical diagnostic (not gated) | annualised active return vs B1, HAC (Newey–West, lag 5) t-statistic; Holm-adjusted p-values across the three families (§14) |

A metric that is mathematically undefined for a run (e.g. episode statistics with zero episodes, Calmar with zero drawdown) is reported as **`undefined` with the reason**; it is never imputed.

RATIONALE: CAGR of a fully specified, cost-charged portfolio is the economically meaningful quantity for portfolio strategies; trade-level metrics are secondary because rebalance-driven "trades" are not independent bets.

---

## 13. Research gate (predeclared)

Applied **per strategy**, independently and **identically to all three families**, on the **Research** segment (§3.6). The same gate is re-applied, unchanged, on the Holdout and Forward segments (§15).

### A. Methodological validity — HARD FAIL (any one ⇒ FAIL, no economic evaluation)
1. look-ahead detected (future-mutation, truncation, fill-source or index test fails, §7);
2. data corruption, structural-check failure, unresolved BLOCKING data review, or manifest/hash mismatch (§3.8, §3.9);
3. non-deterministic results: two identical runs do not produce identical allocation decisions, fills and metrics;
4. unreproducible run: reproducibility block (§17) incomplete;
5. future information in formation, ranking, pair selection, parameter estimation, sizing or weighting;
6. execution or accounting semantics violated (§8, §11), including any fill or mark at a non-raw price;
7. incomplete required dataset.

### B. Economic (PROTOCOL DECISION; user-approved)
PASS requires **both**:
1. `net CAGR @5 bps ≥ 0`; **and**
2. `net CAGR @5 bps ≥ B1 net CAGR @5 bps` (same segment, same sessions, same exclusions, same engine, B1 charged the same per-side cost on its own trades). **Margin = 0.**

Comparisons use the **unrounded float64** values; equality passes. The gate is deterministic given the run outputs.

RATIONALE for condition 2: every v2 strategy is a long-only selection rule inside a universe of hindsight-selected, surviving mega caps over a period with strong equity drift. Under the null hypothesis of **no selection skill**, such a portfolio is still expected to earn approximately the universe's own return, which is very likely positive, so condition 1 alone has almost no power. The natural null for a selection strategy is **passive exposure to the same universe** (B1). The margin is zero so that no magnitude is invented.

**Why this is a minimum, not proof of an edge:** passing B means only that, after the predefined friction, the strategy did not lose money and did not underperform passive ownership of the same names over one historical sample. It does not establish statistical significance, persistence, capacity, or robustness to the universe's survivorship bias. No minimum Sharpe, trade count, breadth or benchmark margin is imposed; these are **NOT PREDEFINED thresholds that may never be added after results**.

### C. Robustness — reporting completeness only
A gate PASS additionally requires that the run report **contains** every item of §16 for 0/5/10 bps (values or `undefined (reason)`). C is a **completeness requirement only**: no numerical threshold is attached to any robustness item, no robustness value can cause a PASS or a FAIL, and robustness results are **never** used to choose, modify or rank a configuration. A missing item ⇒ FAIL (report incomplete), never "pass pending".

Outcome vocabulary: `RESEARCH-PASSED`, `RESEARCH-FAILED (methodological)`, `RESEARCH-FAILED (economic)`, `RESEARCH-FAILED (incomplete)`.

---

## 14. Data snooping and multiple testing (PROTOCOL DECISION)

| Item | Rule |
|---|---|
| Strategy family IDs | `V2-MOM` (§4), `V2-STR` (§5), `V2-LRV` (§6) |
| Experiment IDs | `<family>-R001` (Research), `<family>-H001` (Holdout), `<family>-F001` (Forward). Benchmarks: `V2-B1-<segment>`, `V2-B2-<segment>` |
| Frozen parameters | every value in §3.4, §4–§6, §8–§12 and the v2 JSON `strategies` block; hashed as the strategy-config SHA-256 (§17) |
| Allowed variants | **none.** Each family has exactly one frozen specification |
| New experiment | **any** change to a frozen value, rule, universe, data source, price basis, segment, cost, benchmark, metric or gate. It receives a new ID (`-R002`, …) and a new protocol version, is labelled **DERIVED FROM PRIOR OBSERVATION** if proposed after any v2 result, and **can never be confirmed on a segment already used** by its parent |
| Failed families | a failed family is recorded as failed and is **not silently modified**; any modified version is a new DERIVED experiment under the row above |
| Technical re-runs | allowed only for a documented technical failure with an identical frozen configuration; reported as such; both runs kept |
| Recording | every run (pass, fail, crash, zero-position) is recorded in the experiment registry with its reproducibility block; nothing is deleted |
| Cumulative trial count | v2 starts at **3 pre-registered configurations**. Earlier families (F-BASE and DAY-05 → DAY-12B variants) are a different strategy class and are listed as prior context, not pooled |
| Comparing families | families are evaluated **independently against the same gate**; they are not ranked to choose a winner. Cross-family tables are descriptive only |
| Winner selection | prohibited at every stage: every family that passes a stage proceeds; no family is promoted, dropped or prioritised because another looked better |
| Diagnostic multiplicity control | HAC t-statistics of active return vs B1 with **Holm-adjusted** p-values across the 3 families, per segment. **Diagnostic only:** it cannot pass, fail or rescue a family, cannot override the gate, and cannot be used to select among families (RATIONALE: with ≈ 6 years of daily data and correlated strategies, significance tests have low power; gating on them would add an unvalidated threshold, but omitting them would hide the multiplicity) |

**"Best among tested" vs "validated" (normative):** the family with the highest metric in a stage is only the *best among three tested configurations on one sample*. Selection among several tested strategies inflates the expected best result even when no strategy has an edge. A family is called **validated under protocol v2** only after `FORWARD-PASSED` (§15), and even then with the limitations of §20 attached.

---

## 15. OOS / graduation protocol (PROTOCOL DECISION; user-approved structure)

```
Research gate (§13)  ──pass──▶  Holdout gate (same §13 rules)  ──pass──▶  Forward OOS gate (same §13 rules)
   all families                  all research-passed families               all holdout-passed families
   RESEARCH-PASSED               HOLDOUT-PASSED (pseudo-OOS)                FORWARD-PASSED = validated under v2
```

1. **No holdout data before the research gate.** Holdout bars are not acquired (Stage H, §3.9) until the research gate result of **all three** families is recorded, and only if at least one family passed.
2. **Holdout use restrictions (normative):** the holdout is **not** used for tuning, parameter selection, strategy modification or winner selection. It is **intentionally not blind** (§3.6 rationale 4).
3. **No rescue:** a family that failed the research gate is **never run on the holdout**; no holdout result of any family can rescue, re-qualify or modify a research-failed family.
4. **All** families that pass research are run on the holdout with the identical frozen configuration. None is chosen or dropped by expected or observed performance.
5. The holdout is **one-shot**: one run per family (technical re-runs only per §14). No tuning, no parameter change, no segment change.
6. **All** families that pass the holdout proceed to the forward OOS with the identical frozen configuration. Forward data are acquired once, after the forward period ends (Stage F, §3.9); **no interim forward performance is computed or inspected**, and no data dated after the freeze commit is inspected before then.
7. The forward-OOS specification must be **identical** to the frozen research specification (same strategy-config SHA-256).
8. If **no** family passes research, v2 stops at research: no holdout acquisition, no forward acquisition. Result recorded as "v2 research gate: NO".
9. If no family passes the holdout, v2 stops: no forward acquisition.
10. Stage results never override one another: a family failing any stage is not rescued by another stage.
11. **Status meanings:** RESEARCH-PASSED = minimum in-sample viability; HOLDOUT-PASSED = survived a historical pseudo-OOS that the authors could not blind themselves to; FORWARD-PASSED = survived one year of genuinely unseen data — the only status labelled "validated under v2", still subject to §20 (survivorship, single universe, short sample).

---

## 16. Robustness checks (frozen; reporting, not search)

Frozen list, reported for every family on every evaluated segment (the completeness set of §13.C):
1. cost sensitivity: 0 / 5 / 10 bps (§9);
2. calendar-year subperiods (§12);
3. symbol breadth and concentration (§12);
4. turnover, `λ` and cost drag (§12);
5. exposure and benchmark-relative behaviour (B1, B2, tracking error, information ratio);
6. drawdown profile (max drawdown, worst month, worst year);
7. statistical diagnostic (§12, §14).

**Not permitted:** parameter grids; alternative lookbacks, holding periods, selection counts, thresholds, weightings, price bases, universes or dates; "robustness" re-runs whose outcome would change which configuration is reported. Any such study is a **new, derived experiment** under §14, never part of this protocol's evaluation. Robustness exists to show whether the frozen result survives friction and decomposition, not to find a better configuration.

---

## 17. Reproducibility (mandatory per run)

Every run artifact contains a reproducibility block with:
- protocol version (`2.0`, revision) and SHA-256 of the three DAY-16 files, plus the freeze-commit SHA;
- git commit SHA and dirty flag; dirty files listed with SHA-256 (a dirty tree is allowed only for untracked run outputs);
- Python version, platform, `exchange_calendars` version, full distribution list and its SHA-256 (pattern of `acquisition/v1_1/environment.py`);
- data: stage and snapshot ID, per-file content and file SHA-256 for raw bars, `all` bars and the event list, manifest SHA-256, corporate-action endpoint and version, `asof` date (dataset version = snapshot ID);
- strategy-config SHA-256: SHA-256 of the canonical JSON (sorted keys, UTF-8, compact separators) of the family's `strategies.<family>` block plus the shared `price_series`, `execution`, `costs` and `portfolio` blocks of the v2 JSON;
- random seeds: **none used** (asserted);
- exact command line and working directory;
- run start/end timestamps (UTC);
- result-artifact SHA-256 for every output file.

**Determinism requirement:** two runs with identical inputs must produce byte-identical allocation/fill logs and identical metrics. A mismatch is a HARD FAIL (§13.A3), investigated, never resolved by choosing one result.

---

## 18. Artifact structure

DAY-16 (this task):
```
artifacts/day16/
    research-protocol-v2.md      human-readable protocol (this file)
    research-protocol-v2.json    machine-readable frozen decisions
    research-checklist.json      PREDEFINED / OPEN / NOT APPLICABLE / NOT YET IMPLEMENTED checklist
```
Planned later locations (not created now): data snapshots under `data/oos_cache/protocol_v2/{stage_r,stage_h,stage_f}/`; run artifacts under `artifacts/day17+/v2/<experiment-id>/`; an append-only experiment registry `artifacts/v2-experiment-registry.json` (created by the first run task).

---

## 19. Checklist
See `artifacts/day16/research-checklist.json`. An item is PREDEFINED only where this document fully specifies it.

---

## 20. Open questions and limitations

| # | Question | Status | Resolution path |
|---|---|---|---|
| Q1 | Alpaca SIP **1Day bar semantics**: official auction open/close vs first/last trade; inclusion of extended-hours trades; timestamp label of a daily bar | **BLOCKING** | verify from Alpaca documentation and a structural probe in the acquisition task, before any v2 run; amend (v2.0.x) if OHLC include extended hours |
| Q2 | SIP 1Day **coverage from 2016-01-04** for all 25 symbols and SPY; 1Day entitlement on the existing key (only 5Min verified, DAY-15E) | **BLOCKING** | acquisition task; a gap forces a documented amendment, never a silent date shift |
| Q3 | **META/FB** pre-2022-06-09 bars and events via `asof` mapping | **BLOCKING** | acquisition task; if unavailable, amendment before any run |
| Q4 | Exact content and method of **`adjustment=all`** (audit series only) | NON-BLOCKING (R1: downgraded; needed only to interpret cross-check mismatches) | documentation |
| Q5 | **Survivorship / hindsight universe**: present-day survivors applied back to 2016 | NON-BLOCKING (disclosed, unsolved) | no claim made; B1 shares but does not remove the bias; any fix is a new protocol |
| Q6 | Market-on-open **fill realism**: Alpaca daily open vs achievable opening-auction price; no impact model | NON-BLOCKING | disclosed; costs are friction scenarios only |
| Q7 | **Cash earns 0 %** (understates returns in high-rate years, most for exposure-varying V2-LRV) | NON-BLOCKING | disclosed; exposure reported |
| Q8 | **Fractional shares** assumed | NON-BLOCKING | disclosed |
| Q9 | **Dividends credited as cash on the ex-date**, not reinvested; pay-date lag ignored (accounting); the signal index assumes reinvestment (signals only) | NON-BLOCKING | disclosed |
| Q10 | **V2-LRV residual market exposure** (long-only, not market-neutral) | NON-BLOCKING | disclosed (§6.1); exposure and B1 reported |
| Q11 | **Statistical power**: ≈ 71 monthly / ≈ 309 weekly rebalances in Research; forward OOS = 1 year; the families are correlated with each other and with B1 | NON-BLOCKING | diagnostic HAC + Holm reported; no significance gate |
| Q12 | **Forward OOS start** depends on the freeze-commit date | NON-BLOCKING | rule-defined (§3.6); recorded at commit |
| Q13 | **Calendar resolution** of 2027 sessions by `exchange_calendars` 4.13.2 (rule-based future holidays) | NON-BLOCKING | the rule governs; an unscheduled closure is a documented review, never a substitution (EXISTING CONVENTION) |
| Q14 | **Portfolio engine, v2 bar and corporate-action acquisition, TR-index builder, data loader, PIT tests, experiment registry** do not exist | NOT YET IMPLEMENTED (blocks *running*, not the protocol) | reviewed implementation tasks after the freeze commit; they must not alter any frozen value |
| Q15 | 2 % missing-session review threshold (§3.8) is a data-quality heuristic | NON-BLOCKING | applied before results only |
| Q16 | **Alpaca corporate-actions endpoint**: coverage from 2016 for 25 symbols + SPY (including META/FB), field semantics (ex-date, split ratio direction, cash amount per pre-split share, special dividends), entitlement on the existing key | **BLOCKING** (R1) | acquisition task, verified before any run; cross-check §3.4 must pass |

---

## 21. What this protocol does not do
No strategy is implemented, no backtest is run, no data is downloaded, no performance is calculated. The next task reviews this revised protocol before the freeze commit.
