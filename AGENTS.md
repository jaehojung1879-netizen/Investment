# Investment repository invariants

- Blocked artifacts must contain no actionable output, entry state, positions, or weights.
- Synthetic, seed, and stale artifacts must never pass production validation or deployment.
- Ledger signals are append-only and identified by date, region, ticker, and model version.
- Do not claim point-in-time behavior unless release visibility and vintage limitations are verified and documented.
- `liveValidated` is forbidden until real ledger requirements are met; builds never auto-promote it.
- Keep generated `data/site-data.json` separate from explicit synthetic fixtures.
- After changes run `python -m compileall pipeline`, `pytest -q`, seed generation, and artifact validation.
- Never merge directly to `main`.
