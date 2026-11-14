# ml-strategy-tournament-v1 (KR)

Exploratory competition of 141 ML configurations + 7 rule baselines on the PIT Top120 Korean universe, 2016-01 → 2026-09, every strategy run through
the same 0–5 name + 069500.KS portfolio rule. Evidence class `EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY`. Read [`REPORT-ko.md`](REPORT-ko.md).

| file | role |
|---|---|
| `config.json` | frozen grid, labels, folds, portfolio rule, costs; `preOutcomeRevisions` R1–R2 and `postOutcomeAdditions` A1 |
| `build_features.py` | calls the existing Phase B builder (`kr_alpha_atlas_inputs.load_inputs` + `kr_alpha_atlas_matrix.build_matrix`) at signal-history `4ea107ed` |
| `prepare_dataset.py` | market state, BOK rate, H126/H252 labels vs the reconciled 069500.KS series; `results/data-eligibility.json` |
| `tournament.py` | model grid, walk-forward fitting, calibration gate, daily NAV engine, metrics |
| `run_tournament.py` | fits every configuration per outer year (`--h252` for the secondary horizon) |
| `evaluate.py` | gated (primary) and forced top-5 (sensitivity) books, leaderboards |
| `analyze.py` | TOP-10 tables, winner anatomy (contributions, leave-names-out, ablation, SHAP, linear counterpart), DSR / CSCV-PBO / block bootstrap / nested selection |
| `independent_nav.py` | share-unit NAV recomputation from recorded holdings + raw closes (does not call the engine) |
| `audit_checks.py` | PIT, filing visibility, purge, duplicates, permutation leak canary |
| `export_records.py`, `render_report.py` | compact records and `results/tables-ko.md` |

Research-only dependency beyond `requirements.txt`: `xgboost==3.4.1`. Nothing here is imported by `pipeline/`, production, or any workflow.
