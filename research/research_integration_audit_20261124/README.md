# Research Integration Audit — 2026-11-24

[한국어 결정 보고서](REPORT-ko.md). Audit and merge preparation for PR #343-#373 against main@4f4497bc. Additive files only:
no study code, data, result, protocol, authorization or production file is changed by this directory.

- `evidence/github-snapshot.json`: exact HEAD/base SHA, draft flag, CI run and conclusion, commits and files over base, existing
  files modified, for every open PR #343-#373 (#371 is an issue), plus the PR-less ladder branch under #349.
- `evidence/lineage.json`: ancestry of the two stacks, the integration branch composition, and `git merge-tree` results against
  #344, #370, #372 and #373.
- `evidence/pin-audit.json`: every SHA-256 pin in the JSON files the stacks add, re-verified by `check_pins.py`, with each
  mismatch classified and the one repair made on this branch.
- `evidence/us-input-lineage.json`: which studies read US market caps before the #353 (943 rows) and CTVA (6665:1000) corrections.
- `evidence/closed-pr-preservation.json`: closed, unmerged PRs #259-#330 and where their head commits survive.
- `check_pins.py`: re-runs the pin audit from committed bytes; `tests/test_research_integration_audit_20261124.py` runs it in CI.

The one code change on this branch outside this directory restores
`research/industry_alpha_discovery_v1/hwp_text.py` to its authorized bytes (see `pin-audit.json` → `repairedInThisBranch`).
