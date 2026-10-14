# ORB — data provenance correction (IEX → yfinance)

Date: 2026-10-14. Text-only correction. No network, no download, no backtest or paper run. No code, config, strategy, parameter, metric, trade or CSV/JSON change. V2-MOM, fwd-gate2 and DAY-27B files were not touched.

## 1. Files changed

| File | Line | Before | After |
|---|---|---|---|
| `artifacts/orb/smoke_test/report.md` | 6 | "60 sessions of IEX 5m data" | "60 sessions of yfinance 5m data (`data/cache`; documented provenance, not recorded per file - see this report)" |
| `artifacts/orb/diagnostics_v2/report.md` | 3 | "over 60 IEX sessions" | "over 60 yfinance-cache sessions" |
| `artifacts/orb/diagnostics_v2/report.md` | 49 | "SIP preferred over IEX for volume" | "SIP preferred over the yfinance cache for volume" |
| `artifacts/orb/diagnostics/report.md` | 61 | "Caveat: IEX volume is not consolidated." | "Caveat: volume is from the yfinance cache, not SIP (aggregate within ~1-7% of Alpaca SIP on these sessions)." |
| `artifacts/orb/diagnostics/report.md` | 78 | "(60 IEX sessions)" | "(60 yfinance-cache sessions)" |
| `artifacts/orb/diagnostics_v2/sip_availability.md` | §5 | "reports were not changed" | marked corrected; points here |

The smoke-test CSVs, `metrics.json`, and the diagnostics CSVs contain no source label. They were not modified, and their SHA-256 hashes are identical before and after the edit.

## 2. Evidence

The ORB smoke test read `data/cache/<SYM>_5m.parquet` read-only with the network blocked (`scripts/backtest_orb.py:61-67`, `--cache-dir data/cache`). It created no provider.

1. **File naming.** `data/yfinance_provider.py:158` writes `CACHE_DIR/{symbol}_{interval}{_ext}.parquet`. The IEX-hard-coded `data/alpaca_provider.py:158` writes `CACHE_DIR/alpaca_{symbol}_{interval}…`. The ORB inputs (`AAPL_5m.parquet`, …) match the yfinance pattern. The only Alpaca-pattern files in the cache are `alpaca_*_4h.parquet`.
2. **Project documents.** `artifacts/day14/data-expansion-spec.md:24`: "Provider | yfinance only. Switching to Alpaca (IEX feed, not consolidated volume) would change RVOL semantics and is a separate experiment." `artifacts/day15/day15c-provider-audit.md:56`: "all in-sample research (DAY-04 → DAY-12B) used the yfinance 5m cache."
3. **Empirical volume check (read-only).** The check joined `data/cache/<T>_5m.parquet` with the Alpaca `feed=sip` snapshot `data/oos_cache/protocol_v1.1/research/snapshots/research_20261006T095201Z/<T>_5m.parquet` on the same UTC bar starts: 4,680 bars per ticker, 2026-07-02..09-25. IEX is one venue and carries only a small fraction of consolidated volume. The cache volume instead matches consolidated SIP volume to within a few percent, which **rules out IEX**. Close prices agree to a median relative difference of about 2e-08.

| Ticker | Bars | Σ cache vol / Σ SIP vol | Median per-bar ratio |
|---|---|---|---|
| AAPL | 4680 | 1.028 | 0.995 |
| ADBE | 4680 | 1.020 | 0.999 |
| AMAT | 4680 | 1.041 | 0.999 |
| AMD | 4680 | 1.038 | 0.998 |
| AMZN | 4680 | 1.028 | 0.998 |
| AVGO | 4680 | 1.038 | 0.998 |
| COST | 4680 | 1.009 | 0.992 |
| CRM | 4680 | 1.022 | 1.000 |
| CSCO | 4680 | 1.020 | 1.000 |
| GOOGL | 4680 | 1.031 | 0.996 |
| INTC | 4680 | 1.052 | 1.000 |
| JNJ | 4680 | 1.005 | 0.995 |
| JPM | 4680 | 1.022 | 0.998 |
| KO | 4680 | 1.007 | 0.997 |
| META | 4680 | 1.042 | 0.997 |
| MSFT | 4680 | 1.032 | 0.997 |
| MU | 4680 | 1.068 | 0.998 |
| NFLX | 4680 | 1.025 | 1.000 |
| NVDA | 4680 | 1.031 | 0.994 |
| ORCL | 4680 | 1.043 | 1.000 |
| PEP | 4680 | 1.016 | 0.999 |
| QCOM | 4680 | 1.029 | 0.999 |
| TSLA | 4680 | 1.022 | 0.998 |
| WMT | 4680 | 1.030 | 0.999 |
| XOM | 4680 | 1.020 | 1.000 |

## 3. Not verified

- **Per-file provenance.** The parquet files carry no provider metadata (only `pandas` and `ARROW:schema` keys). `data/cache/` is git-ignored, and no write log exists. "yfinance" therefore rests on evidence 1–2 and is consistent with evidence 3. No record per file proves it.
- **Volume definition.** The cache volume is close to SIP but not identical: the aggregate is 0.5–6.8% higher. The cause (yfinance aggregation, trade-condition filtering, or late prints) is not established.
- **Origin of the "IEX" label.** It comes from a hard-coded string in `scripts/backtest_orb.py:320` (`"- Smoke test on 60 sessions of IEX 5m data: …"`). The diagnostics reports repeated it.

## 4. Open issue

`scripts/backtest_orb.py:320` was deliberately left unchanged. Any re-run of the smoke test will write the "IEX" label into `smoke_test/report.md` again. Fixing that string requires a separate, explicitly approved code change.
