# Owner approval request — no execution token issued

Status: `NOT_EXECUTED`. KR/US history was already outcome-exposed. No new independent OOS or new alpha is claimed. The engineering handoff in #312 explicitly withholds execution authorization.

Approve only one `EXP-C-RECOVERY-02` comparison frozen by:

- Code/contract/test/source identity (canonical `FREEZE.json` SHA-256): `cf26eef726eb1945c70c5f2a984e1cb0262a24d1a2c6145fb8dfd98808b52ba0`.
- Source manifest SHA-256: `31e081493395784de9fb9e992ca87d1c3c3576b83482b3833312723571a2e26f`.
- Every executable SHA-256 is listed in `FREEZE.json`; original sealed source and dependency hashes are in `SOURCES.json`.
- Also bind the exact **new Draft PR HEAD commit** displayed in that PR (replace the placeholder below). Any code/head/source change invalidates approval. No hash may be silently re-pinned.

Required narrow exception: permit this one same-information historical recovery-return comparison despite `docs/research-program/03-studies-abc-ko.md` §C.7 and `05-priority-first-experiment-stop-list-ko.md` §4. The exception does not permit rerunning any original study, reopening H/I/J, variable grids, a new roadmap, trading allocation, promotion or merge. Both regions must be disclosed; a negative/underpowered result closes the experiment and keeps passive default.

Before first look, require a separate non-author exact-commit audit (Claude as specified by Owner) covering timestamps/vintage, dependence/power, leakage, fairness, rights and this closure exception. No such review is claimed here. The runner requires an approved GitHub review by a non-author at the exact head; reviewer independence/content must also be assessed by Owner. No reviewer or author identity is invented.

Source condition: make the **original** frozen US GSPC normalized/audit/raw bundle available in authorized runner temporary storage with all three exact hashes; no acquisition or proxy substitution is authorized by this package. Use the exact pinned KR/FRED files in place. Confirm original personal/noncommercial source rights without redistribution, a complete checkout with pinned Python/dependencies, durable private output, and GitHub permission to atomically claim the permanent study lock. Source equality, actual cohort support and vintage exactness are not presumed.

If approving, Owner must post exactly this JSON in the **new Draft PR**, replacing only `code_commit` with its exact head. This request file is not authorization:

```json
{
  "study": "EXP-C-RECOVERY-02",
  "freeze_sha256": "cf26eef726eb1945c70c5f2a984e1cb0262a24d1a2c6145fb8dfd98808b52ba0",
  "source_manifest_sha256": "31e081493395784de9fb9e992ca87d1c3c3576b83482b3833312723571a2e26f",
  "code_commit": "EXACT_NEW_DRAFT_PR_HEAD_SHA",
  "closure_exception": "C.7_AND_STOP_LIST_SINGLE_COMPARISON_ONLY",
  "outcome_exposed": true,
  "one_shot": true,
  "source_rights_accepted": true,
  "persistence_ready": true,
  "action": "AUTHORIZE_EXACT_HASH_HISTORICAL_EXECUTION"
}
```

The runner authenticates the commenter via GitHub, checks exact head, the non-author review, clean checkout, hashes and runtime, then creates `refs/tags/research-locks/EXP-C-RECOVERY-02` before parsing source values. Preserve every immutable access/eligibility/support/result receipt and the lock. A post-lock failure consumes the study with no retry. Support failure stops before label arithmetic or fitting; MDE/uncertainty failure stops after the single calculation. No research run is requested until all conditions are concrete and satisfied.
