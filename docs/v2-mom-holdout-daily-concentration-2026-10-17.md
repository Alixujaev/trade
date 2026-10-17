# V2-MOM historical holdout: daily active-return concentration (descriptive)

| Field | Value |
|---|---|
| Date | 2026-10-17 |
| Nature | **Descriptive arithmetic on saved, committed holdout artifacts.** Not a backtest, re-simulation, validation test or DAY-25B diagnostic (DAY-25B's scope is closed). It cannot change V2-MOM's status. |
| Status of V2-MOM (unchanged) | RESEARCH-PASSED · HOLDOUT-PASSED (historical pseudo-OOS) · FROZEN FOR FORWARD OOS; `fwd-gate2` PENDING |
| Repository HEAD at calculation | `f6d628692f2faa35e41df7e1c59dd1e8d98851e8` |
| Related | `docs/strategy-evidence-inventory-2026-10-17.md` §7 (where these figures were listed as unpersisted) |

## 1. Sources and sample

| File | Committed in | SHA-256 (prefix) | Content |
|---|---|---|---|
| `artifacts/day21/v2/V2-MOM-H001/5bps/equity.csv` | `8645e91` (2026-10-08) | `36fa0c994e338780` | Daily equity of V2-MOM at 5 bps per side (`session,equity,exposure,n_held`) |
| `artifacts/day21/v2/V2-B1-holdout/5bps/equity.csv` | `8645e91` (2026-10-08) | `18119199c1fd0aea` | Daily equity of the B1 benchmark (equal-weight 25) at 5 bps |
| `artifacts/day21/v2/V2-MOM-H001/5bps/metrics.json` | `8645e91` | `61737c9c82d061e4` | `starting_capital`, `ending_equity`, `cagr`, `calendar_years` (cross-checks) |
| `artifacts/day21/v2/V2-B1-holdout/5bps/metrics.json` | `8645e91` | `a5b6b625ec16719a` | Same fields for B1 |

**Sample:**
- **Period:** the historical holdout, 2023-01-03 → 2026-06-02, 856 XNYS sessions (`artifacts/day16/research-protocol-v2.md:158`; `artifacts/day21/day21-historical-holdout-report.md:11`).
- **No overlap with the sealed forward test:** `fwd-gate2` covers 2026-10-12 → 2026-12-09 (`artifacts/day26d/protocol-v2.2-amendment.md:11`), so these artifacts contain no forward-test data.
- **Nothing sealed was read:** no forward-test, paper-runner or sealed file was accessed.

## 2. Validation (all passed)

- **Dates:** both files have 856 rows, no duplicate dates, strictly increasing order and identical date lists. They match the 856 XNYS sessions in the range exactly (`exchange_calendars` 4.13.2): none missing, none extra.
- **Value format:** values are serialised as `np.float64(<number>)`. They were parsed with a strict pattern, and no row was malformed or non-finite.
- **Starting and ending equity:**
  - E₀ = 100,000 for both series, from `metrics.json` `starting_capital`. It is not a CSV row; the first row is equity after session 1.
  - The last row equals `metrics.json` `ending_equity`, so it **includes** the final liquidation cost.
- **Recomputed metrics match the saved values exactly:** total return and CAGR for both series, all four calendar-year returns, and the 2026 monthly product (1.198862).

## 3. Method

- **Daily return:** rₜ = Eₜ / Eₜ₋₁ − 1, with E₀ = 100,000 as the prior value for the first session.
- **Daily active return:** aₜ = r_MOM,t − r_B1,t.
- **Additive active contribution:** cₜ = [(E_MOM,t − E_MOM,t−1) − (E_B1,t − E_B1,t−1)] / E₀.
  - Σcₜ = (E_MOM,T − E_B1,T) / E₀ exactly; this was checked numerically.
  - It equals the total-return difference R_MOM − R_B1.
- **Top-k days:** sessions are ranked by largest positive cₜ, with cutoffs k = 5, 10 and 20 fixed before looking at results.
  - "Remaining" is the descriptive sum Σcₜ minus the selected days.
  - It is **not** a re-simulation and does not mean the strategy didn't trade on those days.
- **Monthly return:** equity at the month's last session ÷ equity at the previous month's last session − 1. A month is "partial" if the data contains fewer sessions than the XNYS calendar has for that month.

## 4. Results

### 4.1 Full period

| | V2-MOM | B1 |
|---|---|---|
| Compounded total return | +521.68% | +326.25% |
| CAGR (252/856) | 71.25% | 53.24% |

**Compounded active return:**
- total-return difference **+195.43 pp**;
- CAGR difference **+18.01 pp**.

**Daily active returns, a separate quantity:**
- Σaₜ = +0.4808, a simple sum that is **not** the compounded active return;
- 436 positive days and 420 negative days.

**Additive contributions:**
- the net total is +1.9543, against gross positive +9.0814 (439 days) and gross negative −7.1270 (417 days);
- by year: 2023 −0.1047, 2024 +0.1929, 2025 −0.2428, **2026 +2.1088** (104 sessions).

### 4.2 Top positive additive-contribution days

| Cutoff | Combined | Share of net total | Share of gross positive | Remaining net | Sessions left | Years of the selected days |
|---|---|---|---|---|---|---|
| Top 5 | +1.3490 | 69.0% | 14.9% | +0.6054 | 851 | 2026 ×5 |
| Top 10 | +2.1250 | 108.7% | 23.4% | **−0.1707** | 846 | 2026 ×9, 2025 ×1 |
| Top 20 | +3.0310 | 155.1% | 33.4% | **−1.0767** | 836 | 2026 ×16, 2025 ×3, 2024 ×1 |

| Rank | Session | cₜ | r_MOM | r_B1 | aₜ |
|---|---|---|---|---|---|
| 1 | 2026-05-08 | +0.3352 | +9.89% | +4.66% | +5.24% |
| 2 | 2026-05-26 | +0.2980 | +8.07% | +3.91% | +4.15% |
| 3 | 2026-04-24 | +0.2786 | +9.82% | +3.16% | +6.66% |
| 4 | 2026-05-05 | +0.2264 | +7.01% | +2.78% | +4.23% |
| 5 | 2026-05-06 | +0.2109 | +6.60% | +3.20% | +3.40% |
| 6 | 2026-05-20 | +0.1861 | +5.22% | +2.28% | +2.94% |
| 7 | 2026-04-29 | +0.1673 | +4.73% | +0.94% | +3.79% |
| 8 | 2025-09-10 | +0.1671 | +8.78% | +2.67% | +6.11% |
| 9 | 2026-04-08 | +0.1292 | +7.39% | +3.55% | +3.84% |
| 10 | 2026-01-21 | +0.1264 | +5.84% | +2.02% | +3.81% |
| 11 | 2026-04-30 | +0.1228 | +3.03% | +0.33% | +2.70% |
| 12 | 2026-04-01 | +0.1092 | +5.56% | +1.78% | +3.78% |
| 13 | 2026-01-02 | +0.1013 | +4.58% | +0.95% | +3.63% |
| 14 | 2026-01-28 | +0.0954 | +3.90% | +1.06% | +2.84% |
| 15 | 2026-02-02 | +0.0863 | +3.25% | +0.68% | +2.57% |
| 16 | 2026-01-13 | +0.0830 | +2.62% | −0.07% | +2.69% |
| 17 | 2024-12-13 | +0.0806 | +4.33% | +0.82% | +3.51% |
| 18 | 2026-01-09 | +0.0781 | +4.26% | +1.58% | +2.68% |
| 19 | 2025-09-05 | +0.0756 | +3.38% | +0.47% | +2.91% |
| 20 | 2025-11-05 | +0.0739 | +3.88% | +1.17% | +2.72% |

The five most negative days are also in 2026: 01-23 (−0.1422), 05-12 (−0.1361), 05-15 (−0.1344), 02-04 (−0.1208) and 05-07 (−0.1167).

**Shares above 100% mean the ratio is misleading.** Large positive and negative days offset each other (gross +9.08 against −7.13), so the small net total is a fragile denominator. The share of gross positive contributions is the more stable description.

### 4.3 2026 by month

| Month | Sessions in data / XNYS sessions | V2-MOM | B1 | Active | Additive contribution |
|---|---|---|---|---|---|
| 2026-01 | 20/20 | +17.08% | +4.81% | +12.27 pp | +0.3396 |
| 2026-02 | 19/19 | −5.81% | −2.77% | −3.04 pp | −0.1057 |
| 2026-03 | 22/22 | −7.43% | −5.12% | −2.31 pp | −0.0760 |
| 2026-04 | 21/21 | +57.99% | +21.15% | +36.84 pp | +1.0640 |
| 2026-05 | 20/20 | +33.53% | +18.72% | +14.80 pp | +0.8749 |
| 2026-06 | **2/21, partial** (data ends 2026-06-02; the last day includes liquidation cost) | +2.10% | +2.79% | −0.69 pp | +0.0121 |

## 5. Findings

**Observed (from the data):**
- **2026 dominates.** It contributes +2.109 of the +1.954 net additive active contribution; 2023–2025 sum to −0.155.
- **April and May 2026 together contribute +1.939.**
- **The best days are concentrated.** The 10 largest positive days (9 in 2026) sum to more than the net total; removing them descriptively leaves −0.171.

**Interpretation:**
- The historical holdout advantage over B1 is concentrated in a short period and a small number of days, not spread broadly across the sample.
- B1 also rose strongly in April and May 2026. Whether V2-MOM's excess came from higher sensitivity to that rally or from selection is **not** established here.

## 6. Limitations

- **Dollar weighting:** cₜ is scaled by E₀. Mean V2-MOM equity was about 376k in 2026 against about 121k in 2023, so later days carry more weight mechanically. A ranking by unweighted aₜ was not calculated.
- **Outcome-selected exclusion:** removing the top days is a descriptive subtraction chosen after seeing the outcome. It is not a neutral statistical test, and the worst days are kept.
- **Same caveats as the holdout itself:** one historical pseudo-OOS sample that was not blind (protocol `:168`); a hindsight-selected, survivorship-biased universe (Q5); no statistical significance (HAC p = 0.166, DAY-21 §4, not re-tested here).
- **Scope:** this is not forward evidence and says nothing about future performance or live-trading readiness.

## 7. Reproduction (read-only)

The calculation uses Python 3.12 and `exchange_calendars`, on the four committed files above only.

1. **Parse:** read each `equity.csv` and parse values as `float(re.match(r"^np\.float64\((.+)\)$", v).group(1))`. Stop on any value that doesn't match.
2. **Check alignment:** both files must have the same dates, and those dates must equal `xcals.get_calendar("XNYS").sessions_in_range("2023-01-03", "2026-06-02")`.
3. **Compute:** set E₀ = `metrics.json["starting_capital"]`. Compute rₜ, aₜ and cₜ as defined in §3, and rank the sessions by cₜ.
4. **Monthly:** take the last-session equity of each month, divided by the previous month's last-session equity.
5. **Cross-check:** compare total return, CAGR = (E_T/E₀)^(252/856) − 1 and `calendar_years[*].return` with `metrics.json`. All must match exactly.
