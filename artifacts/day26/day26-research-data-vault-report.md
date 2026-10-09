# DAY-26: Permanent cross-device research-data vault (completion report)

Date: 2026-10-09. Infrastructure only: no strategy evaluation, no forward data, no change to V2-MOM, the protocol, DAY-22 or DAY-24.
Machine-readable record: `day26-research-data-vault-report.json`.

## Result

| Item | Value |
|---|---|
| Data repository | https://github.com/Alixujaev/trade-research-data (**PRIVATE**, owner `Alixujaev`, created by this task, git contents: `README.md` only) |
| Release (immutable version id) | [`protocol-v2-historical-v1`](https://github.com/Alixujaev/trade-research-data/releases/tag/protocol-v2-historical-v1) (not draft, not prerelease) |
| Trust anchor (main repo) | `scripts/research_data/vaults/protocol-v2-historical-v1.json`, SHA-256 `505f2b3fe898a4c87caab734312a1bc0639e0f79aaa75d247dfbbf2907044968` |
| Main branch | `feature/day-trading-research`, committed locally, **not pushed** |

## Assets (local = uploaded = downloaded)

| Asset | Bytes | SHA-256 | Files | Downloaded hash matches |
|---|---:|---|---:|---|
| `stage_r-protocol-v2-historical-v1.tar.gz` | 5,495,126 | `1b4cb1067de929945f5582f979c1623df11dbcc035568929720fd93b553e1513` | 99 | yes |
| `stage_h-protocol-v2-historical-v1.tar.gz` | 3,248,886 | `42fd47fbaf22cd960b6e41cbad04536344ac38c14d70253c0418ffd3fa078604` | 67 | yes |
| `evidence-sec-protocol-v2-historical-v1.tar.gz` | 13,366 | `d74230e9b81140fb1295e946745d129d8f0cae6fb998a0163ca894ae41c4a1c1` | 2 | yes |
| `vault-manifest.json` | 41,766 | `505f2b3fe898a4c87caab734312a1bc0639e0f79aaa75d247dfbbf2907044968` | n/a | yes (also byte-identical to the trust anchor) |

The archives are deterministic: an independent rebuild was byte-identical.

## Snapshot anchors verified after download and restore

| Anchor | Path | manifest.json SHA-256 |
|---|---|---|
| Stage R snapshot | `stage_r/stage_r_20261007T093410Z` | `aefef19d48b80f842bae3c61cc439b9a2a44082189e28733d5ab25a1735006bd` |
| Stage R approved review (v2.0.4, `USABLE_FOR_RESEARCH`) | `stage_r/reviews/v2_0_4__stage_r_20261007T093410Z` | `755c905e0adae6c7cac924aa8146384defe7053784b526675e7b51d714f6d698` |
| Stage H snapshot | `stage_h/stage_h_20261008T100604Z` | `eff959594658303c9aafeb81d18a159b742071821a4fe081e462691455be4a34` |
| Stage H DAY-20A validation (`READY_FOR_HISTORICAL_HOLDOUT_EVALUATION`) | `stage_h/validation__stage_h_20261008T100604Z__day20a` | `e2a7d5a72d5a12342554edff34efb3e398b10eb8db101716dbc806592f82530f` |

Every other unit was also verified against its own `manifest.json`: three earlier Stage R review outputs, the first Stage H validation, and two content-addressed SEC filings.

**Date boundaries** (bars converted to New York session date; event `ex_date`/`event_date` checked):

| Component | Permitted | Observed bars | Last event date |
|---|---|---|---|
| Stage R | 2016-01-04 .. 2022-12-30 | 2016-01-04 .. 2022-12-30 | 2022-12-30 |
| Stage H | 2021-01-04 .. 2026-06-02 | 2021-01-04 .. 2026-06-02 | 2026-05-26 |

## Verification performed

1. Before upload, the four staged artifacts were re-hashed. They matched the recorded full hashes and the per-archive hashes in the pinned manifest, and the pinned manifest equalled the staged one.
2. Repository and release checks:
   - `publish upload` created the repo with `--private`, re-read it, and confirmed `isPrivate == true`.
   - The tag did not exist before; the release was created with exactly the four files.
   - All four assets were downloaded into a fresh temp dir, and each SHA-256 equals the local artifact.
   - A full restore from the downloaded assets verified every file, manifest, binding and boundary.
3. Independent post-checks:
   - `gh repo view` reports owner `Alixujaev`, `PRIVATE`.
   - `gh release view` lists exactly the four assets, with the expected sizes.
4. A clean-room restore through `gh` restored all 10 units, and `diff -rq` showed them byte-identical to the originals. A second run gave 10 × "already present, verified, skipped".
5. A restore over the real `data/oos_cache/protocol_v2` gave 10 × "already present, verified, skipped". The SHA-256 list of all 168 source files was identical before and after.
6. Fresh-environment check: `git clone` with `core.autocrlf=true`, then `restore` and `verify` run through `gh` from the clone's own code. The pinned manifest stayed byte-exact (`.gitattributes` marks it binary). All 10 units were restored, and the result was byte-identical to the originals. This passed at two clone depths.

## Defect found during the fresh-clone check, and the fix

The first fresh-clone restore, in a deep directory, exceeded the Windows 260-character path limit inside the restore staging area. It raised a raw `FileNotFoundError` and wrote nothing (the destination stayed empty and the temp dir was removed). Commit `fe6a422` fixes this:
- staging now uses short temp names;
- any filesystem error before the move phase becomes a `VaultError` stating that nothing was changed, with guidance to enable `LongPathsEnabled` or use a shorter clone path;
- the README carries the Windows note, and a new test covers the failure path.

The same deep-path clone then restored and verified successfully. The published assets were not affected and were not changed.

## Tests

- Full suite on commit `8a21aeb` (after upload): **1361 passed, 0 failed** (28 warnings, 59m18s).
- On the final code `fe6a422` (long-path fix): `tests/test_day26_research_data.py` plus the Stage R, Stage H, holdout and cache-immutability suites gave **71 passed** (29 DAY-26 tests).
- **Not completed:** a full-suite re-run on `fe6a422` was stopped by Claude Code because the system was low on memory. The run did not fail; it was not restarted. The fix touches only `scripts/research_data/vault.py`, which no other module imports, plus its test and README.

## Code added

`scripts/research_data/`:
- `vault.py`: core (safe extract, verify, boundaries, restore)
- `restore.py`, `verify.py`, `publish.py`: CLIs
- `README.md`: fresh-environment commands
- `vaults/protocol-v2-historical-v1.json`: trust anchor

Plus `tests/test_day26_research_data.py`, which has 28 tests on synthetic fixtures and one governance test binding the pinned anchors to `backtest/v2/data.py` and `acquisition/v2/contract.py`.

## Fresh-environment restore

```bash
git clone https://github.com/Alixujaev/trade.git && cd trade && git checkout feature/day-trading-research
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt      # Linux/macOS: .venv/bin/pip
gh auth login                                                             # or GH_TOKEN (read-only fine-grained PAT)
.venv/Scripts/python -m scripts.research_data.restore --version protocol-v2-historical-v1
.venv/Scripts/python -m scripts.research_data.verify  --version protocol-v2-historical-v1
```

## Governance

No forward-period data was accessed, downloaded or inspected, and no market-data provider was contacted. The original snapshots were only read. The frozen V2-MOM configuration, protocol, DAY-22 lockdown and DAY-24 proposal are unchanged.

## Limitations and remaining manual actions

- **Push required for other devices:** the DAY-26 commit is local only (by instruction). Another device can restore only after you push `feature/day-trading-research`, since the push carries the tooling and the trust anchor.
- **Immutable releases not enabled:** GitHub's repository-level "immutable releases" setting was not turned on. Integrity does not depend on it, because any changed asset fails the pinned-manifest check. Enabling it is optional extra hardening.
- **Cloud agents:** they need a fine-grained, read-only `GH_TOKEN` scoped to `Alixujaev/trade-research-data`.
- **PATH:** `gh` is installed at `C:\Program Files\GitHub CLI` but was not on this session's Git-Bash PATH. New terminals pick it up.
- **Not in the vault (intentionally):** legacy `protocol_v1.x` caches, `data/cache` and `day08-market-cache.tar.gz`.
