# Corporate prospective receipt continuity — read-only, 2026-11-25 KST

Related to the independent #292 comment 7140864790, not #371/#373 or #372. No new return/label read, registration change, scheduled writer, ledger write, workflow or production change. This tool monitors only the already-authorized A1/B1 corporate writer, not the separately implemented B-H1 coverage tool.

Actual fixed signal-history snapshot `fa50ea2183e07ca07bbe879d7265121a4a88ee66`: file SHA256 `7a584fed00ca3b152970f8a851c0d31f13e4eccfebfb42152ae7053d22664b82`. All 3 stored records (Nov 9, 11, 12; events 2, 5, 1) independently matched their row SHA256, the original authorization bytes SHA256 `c7191d7542a4e3b0d832e63625201585998632ef680d1976c0e2f0faab115d1e`, pinned spec and code, count and LIVE mode. Recomputed against canonical raw rows via connector, not via running this CLI on a local clone. Public git committer timestamps for the 3 append commits are also inside their respective stated windows; these timestamps do not establish first push time or source completeness.

At cutoff 2026-11-24T18:35:00Z (Nov 25 03:35 KST), the Nov 24 session is still in the registered window before the Nov 25 open; classify it as pending, not missed. Prior closed sessions Nov 10, 13, 16, 17, 18, 19, 20, 23 are absent from this snapshot. Expected closed windows 11; observed valid 3. This count is a calendar-based operational diagnosis, not an economic sample size. The external Claude schedule has not been accessed or repaired.

## Usage

From a full repository checkout with the registration and signal-history Git objects already available, and normal pinned dependencies installed:

```sh
python scripts/audit_corporate_receipt_continuity.py --ledger-sha fa50ea2183e07ca07bbe879d7265121a4a88ee66 --as-of 2026-11-24T18:35:00Z
python -m pytest -q tests/test_corporate_receipt_continuity.py
```

The CLI only reads Git objects and uses the existing exchange calendar; ATTENTION exits 1, unavailable or malformed input fails instead of treating it as zero observations. It does not validate historical append-prefix immutability or actual network publication timestamps. Missing dates are never written or reconstructed. The historical snapshot's outstanding holes remain visible even if later sessions resume. Inspect the original writer logs and recover using the existing #322 ops guidance, never create competing writers.

Local isolated synthetic tests: 6 passed. Full repository CI and CLI on the actual Git objects are not yet verified in the chat container (no GitHub DNS). The actual connector-based raw hash and registration checks above are separate from the local tests.
