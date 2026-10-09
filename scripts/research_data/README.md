# Research-data vault (DAY-26)

Immutable Stage R / Stage H market-data snapshots are kept in a **private** GitHub repository,
[`Alixujaev/trade-research-data`](https://github.com/Alixujaev/trade-research-data), as versioned release assets.
They are never stored in this repository or its git history.

| Lives where | What |
|---|---|
| this repo (`Alixujaev/trade`) | code, research artifacts, review records, **pinned vault manifests** (`vaults/*.json`) |
| data vault (release assets) | the immutable source snapshots, byte-for-byte, as deterministic `.tar.gz` archives |
| your machine only | derived outputs, which are re-computable from code + snapshots and are never a replacement for the snapshots |

## Versions

| Version (release tag) | Components | Boundaries |
|---|---|---|
| `protocol-v2-historical-v1` | `stage_r`: `stage_r_20261007T093410Z` + 4 review outputs (manifest `aefef19d…06bd`, approved review `755c905e…d698`) | sessions 2016-01-04 .. 2022-12-30 |
| | `stage_h`: `stage_h_20261008T100604Z` + 2 validation records (manifest `eff95959…4a34`, DAY-20A validation `e2a7d5a7…530f`) | sessions 2021-01-04 .. 2026-06-02 |
| | `evidence`: 2 content-addressed SEC filings cited by review records | n/a |

A version is never edited. New data gets a new version id, a new release, and a new pinned manifest.

## Restore on a fresh machine or agent environment

```bash
git clone https://github.com/Alixujaev/trade.git && cd trade
git checkout feature/day-trading-research
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt      # Linux/macOS: .venv/bin/pip
gh auth login                                      # or set GH_TOKEN (see below)
.venv/Scripts/python -m scripts.research_data.restore --version protocol-v2-historical-v1
.venv/Scripts/python -m scripts.research_data.verify  --version protocol-v2-historical-v1
```

Restore is written to `data/oos_cache/protocol_v2/`, the paths `backtest/v2/data.py` reads.
Options: `--components stage_r stage_h evidence` (downloads only those assets), `--dest DIR`,
and `--from-dir DIR` (assets already on disk, e.g. copied from another PC).

**Auth for cloud agents / headless machines:** create a fine-grained personal access token limited to
`Alixujaev/trade-research-data` with **Contents: read-only**, and expose it as the `GH_TOKEN` environment
variable or secret. Never commit it. `gh` picks it up automatically.

## What restore guarantees (fails closed: exit 1, nothing overwritten)

1. The downloaded `vault-manifest.json` must be byte-identical to `scripts/research_data/vaults/<version>.json`.
   That committed file is the trust root.
2. Each archive's size and SHA-256 are checked **before** extraction.
3. Extraction goes entry by entry into a temp dir next to the destination. It rejects absolute, drive and
   backslash paths, `..`, links, devices, duplicates, and any entry not in the manifest.
4. Every file's size and SHA-256 are checked. Every snapshot, review and validation dir is re-checked against
   its own `manifest.json` (`acquisition.v2.reevaluate.verify_snapshot`), along with the recorded bindings
   (`USABLE_FOR_RESEARCH`, `READY_FOR_HISTORICAL_HOLDOUT_EVALUATION`, source snapshot hash).
5. No bar session and no event `ex_date`/`event_date` may fall outside the component's historical boundary.
6. An existing unit that verifies identically is skipped, which makes restore idempotent. An existing unit that
   differs aborts the whole restore before anything is moved.

The tooling contacts only GitHub. It never calls a market-data provider and never touches forward-OOS data.
The vault contains nothing after 2026-06-02.

## Maintainer: publishing a new version

```bash
python -m scripts.research_data.publish build --out <dir outside repo> --version <new-id> --pin
python -m scripts.research_data.publish upload --staging <same dir> --version <new-id> --confirm
```

`build` verifies the source trees against the signed-off hashes and boundaries, writes deterministic archives,
and round-trips them through a full restore. `upload` creates the private repo only if it is missing (and
refuses a public one). It refuses an existing tag, then downloads every asset back and verifies it.
For a new version, add its spec next to `protocol_v2_spec()` in `publish.py`.
