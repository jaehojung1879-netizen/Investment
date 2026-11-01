# EXP-C-RECOVERY-02

Read `RESULTS.md` first. This is one independently executable package, with no production imports of it, workflows or real-data fixtures. All additions belong to this directory. It is a new experiment ID within the existing C track, not a renamed track; Market-C2 is unrelated to CHAMPION-C2.

From the repository root (Python 3.11, repository-pinned NumPy/Pandas and calendar dependencies):

```sh
python research/exp_c_recovery_validation_v1/run.py
python -m unittest discover -s research/exp_c_recovery_validation_v1 -p 'test_*.py' -v
```

The default command verifies `FREEZE.json` and prints `NOT_EXECUTED`, its exact identity, and zero source parses. It does not acquire data, run a prior study or create a lock. Unit tests use only invented observations. `CONTRACT.json` is the complete fixed preregistration; `SOURCES.json` binds original references, code, rates, rights and costs. M1 adds no interactions; M2 adds exactly signed return63 and vol21/vol63−1.

After the exact-head Owner exception/authorization, a separate non-author audit of that commit (Claude per handoff), matching authorized US temporary source bundle, complete frozen checkout and durable output are available, the one-shot command is:

```sh
python research/exp_c_recovery_validation_v1/run.py --execute \
  --approval-comment-id OWNER_COMMENT_ID \
  --us-source-root /authorized/temporary/original-us-bundle \
  --output /durable/private/exp-c-recovery-02-first-look
```

`gh` must be configured with permission to read the new Draft PR and create the permanent study lock. Owner comment ID must belong to that new Draft PR, whose exact head it authorizes. No credentials are embedded. No execution was attempted. The package never invokes source acquisition, an old evaluator or a workflow. A hash or source-rights failure stops; it cannot re-pin a revised history. Output must be outside the repository and durable; raw sources stay private and ephemeral.

One global atomic `refs/tags/research-locks/EXP-C-RECOVERY-02` consumes first look before any value parsing. Output is created exclusively and fsynced. Preserve the lock and all receipts even on failure; no retry. Eligibility/missingness IDs are persisted before label arithmetic or fit. Support is checked before labels: insufficient support in either country stops all fitting with `POWER_BLOCKED`, reporting both potential sizes and absent scores. Otherwise the one registered comparison and diagnostics produce `result.json`, with per-country folds, common IDs, scores and uncertainty. Historical time-ordered OOS remains **EXPLORATORY** because both histories were previously exposed.

The bootstrap uses 126-session calendar bins and two-bin blocks, with empty bins retained. This corrects overlapping weekly losses under weak-dependence assumptions; it does not declare bins or crisis episodes independent. The 32-bin floor and 80% MDE are conservative planning gates, not proof of power. No calibration campaign, tuning, trading mapping or extra experiment is included. Any `NO_EVIDENCE`/`POWER_BLOCKED` verdict ends this experiment and keeps passive as default.

`FREEZE.json` hashes executable code, tests, source manifest and contract. Its canonical JSON SHA-256 is the execution identity. The human approval packet and absent-result prose are outside that hash to avoid self-reference; Owner approval also pins the exact Git commit, binding every file. Full CI is the existing repository Tests workflow on the Draft PR's exact head; no workflow changes or dispatches are included.
