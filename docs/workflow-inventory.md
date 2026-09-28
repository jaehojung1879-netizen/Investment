# Workflow inventory

This document is the operator-facing inventory for `.github/workflows/`.
Every workflow file currently on disk must appear in the ACTIVE table; closed
one-shot research workflows may remain on disk only when the table explicitly
says not to run them. Historical one-shot workflows removed from the Actions
surface remain documented under RETIRED RESEARCH.

There are **16 workflow files** on the current branch, including the three
synthetic inference calibration versions. Calibration v1 and v2 are closed
substantive failures retained only for reproducibility. Calibration v3 is the
only pending inference-calibration action.

## ACTIVE

| Workflow | Schedule | Manual run needed? | What it does |
|---|---|---|---|
| `Tests` (`tests.yml`) | on every PR / push to `main` | No — runs automatically | Full test suite + lint/import gate before merge. |
| `Build insight data and deploy Pages` (`pages.yml`) | daily 08:20 KST + on push to `main` | No | Builds site data and deploys Pages. |
| `Append paper-signal ledger` (`ledger.yml`) | daily 00:10 UTC | No | Appends the daily cross-section to the immutable signal ledger. |
| `Collect fundamentals` (`fundamentals.yml`) | daily 03:40 UTC | No for scheduled collection | DART/Finnhub PIT fundamentals plus the guarded KR raw-statement repair routes. The repaired KR accounting foundation is complete for the historical scope; do not repeatedly dispatch `raw-statements` merely to revisit not-yet-mature 2026 filings. |
| `Collect universe history` (`universe.yml`) | monthly, 1st, 04:20 UTC | No | Monthly point-in-time membership snapshots. |
| `Historical point-in-time replay` (`replay.yml`) | daily 02:40 UTC | No | Extends replay-v16 using frozen PIT inputs and weekly ML retraining. |
| `Collect DART ownership events` (`dart-ownership-events.yml`) | none — `workflow_dispatch` only | **Yes, `mode: auto`** | KR 5%-rule ownership disclosure collection with probe-first fail-closed behavior. |
| `Collect KR terminated-security corporate actions` (`kr-corporate-action-collection.yml`) | none — `workflow_dispatch` only | **Yes, `mode: auto`** when additional source collection is actually required | DART disclosure-index, dividend-section, and terminal-action evidence collection for the terminated-security foundation. |
| `Seal fundamental acceleration signal` (`fundamental-acceleration-seal.yml`) | none yet | Yes, periodically | Appends genuinely prospective acceleration observations before their 126-session horizon can be known. |
| `Alpha opportunity model v1` (`alpha-opportunity-model-v1.yml`) | none — `workflow_dispatch` only | **Do not run** | Legacy sealed preregistration harness; superseded by later design/data-integrity work. |
| `Alpha opportunity model v2` (`alpha-opportunity-model-v2.yml`) | none — `workflow_dispatch` only | **Do not run** | Superseded before execution by later data-integrity work. Do not revive it as a historical outcome search. |
| `Alpha opportunity model v4 execution (KR)` (`alpha-opportunity-model-v4-execution.yml`) | none — `workflow_dispatch` only | **Do not run for Alpha outcomes while v5 preparation is in progress** | Existing guarded KR v4 harness retained for reproducibility. Its prior gate-only execution stopped before labels because the then-sealed data foundation failed integrity requirements. |
| `Synthetic alpha inference calibration v1` (`alpha-inference-calibration-v1.yml`) | none — `workflow_dispatch` only | **Do not run — closed substantive FAIL** | Run `36472769120` completed the registered synthetic contract and failed coverage. Preserved only for reproducibility; see `docs/results/alpha-inference-calibration-v1-report.md`. |
| `Synthetic alpha inference calibration v2` (`alpha-inference-calibration-v2.yml`) | none — `workflow_dispatch` only | **Do not run — closed substantive FAIL** | Run `36476033206` completed all 40 registered synthetic cells and failed the frozen coverage contract even after circular moving blocks + basic intervals. Preserved only for reproducibility; see `docs/results/alpha-inference-calibration-v2-report.md`. |
| `Synthetic alpha inference calibration v3` (`alpha-inference-calibration-v3.yml`) | none — `workflow_dispatch` only | **Run exactly once only after the v3 protocol PR is merged** | Synthetic-only self-normalized fixed-b (`b=1`) interval calibration. No block-length choice or bootstrap evaluation draws; no historical Alpha outcomes or `signal-history` outcome artifacts are read. A complete substantive FAIL closes v3. |
| `Probes` (`probes.yml`) | none — `workflow_dispatch` only | On demand | Dispatcher for external-source availability/schema probes. |

### Operator notes

- `Collect DART ownership events`, `mode: auto`, probes first and proceeds only
  when the source contract is served. Vendor refusal is a failed/blocked
  measurement, never permission to scrape around the source.
- The Alpha opportunity v1/v2/v4 workflow files remain visible because the
  repository preserves sealed historical research machinery. Their presence is
  not permission to spend another historical-outcome attempt.
- For inference calibration, the authoritative progression is now
  **v1 FAIL -> v2 FAIL -> v3 pending**. Never rerun v1/v2 with another seed,
  threshold, or favorable sensitivity.

## ON-DEMAND PROBES

All are routed through `probes.yml` unless a dedicated collector above is the
operator entry point.

| Probe | Source / purpose | Current interpretation |
|---|---|---|
| `sec-egress` / `sec-headers` / `sec-fundamentals` / `sec-bulk-datasets` | SEC access | Prior Actions measurements were blocked; re-probe only to measure a changed source condition. |
| `guru-13f-access` | SEC 13F availability | Prior route blocked; no proxy/scraping workaround. |
| `fmp-fundamentals` | FMP fundamental source | See the latest source-capability result under `docs/results/`. |
| `dart-fundamentals` | DART DS002 | Served; production collection already depends on it. |
| `krx-index-membership` | KRX membership source | Endpoint-specific status; follow repository vendor-refusal invariants. |
| `kr-investor-flow` | KRX investor-flow source | Previously blocked source. |
| `kr-short-selling` | KRX short-sale source | Previously blocked source. |
| `us-pit-fundamentals` / `us-delisted-prices` | US historical data routes | See the latest source-capability reports. |
| `alfred-macro-vintages` | ALFRED vintage coverage | Known historical-vintage gaps remain documented. |
| `kr-delisting-coverage` | KR delisted-name coverage | See the latest data-foundation report. |

## RETIRED RESEARCH

These workflow files are intentionally absent from `.github/workflows/`.
Their code/results remain in git history or `docs/results/`; restoring one is a
new research action and must not be used as a same-sample rescue.

| Retired workflow | Study | Closed status / result location |
|---|---|---|
| `regional-alpha-model.yml` | `regional-alpha-model-v1` | Historical discovery closed; see `docs/alpha-research-foundation-v2-errata.md`. |
| `benchmark-alpha.yml` | `benchmark-relative-alpha-v1` | Closed; see `docs/results/benchmark-alpha-report.md`. |
| `selection-value.yml` | `selection-value-decomposition-v1` | Closed diagnostic; see `docs/results/`. |
| `switch-hurdle.yml` | `regional-switch-hurdle-v1` | Closed; see `docs/results/switch-hurdle-report.md`. |
| `signal-persistence.yml` | `signal-persistence-v1` | Closed; see `docs/results/`. |
| `alpha-reliability.yml` | `alpha-reliability-v1` | Closed; see `docs/results/alpha-reliability-report.md`. |
| `alpha-risk-separation.yml` | `alpha-risk-separation-v1` | Closed; see `docs/results/alpha-risk-separation-report.md`. |
| `alpha-risk-separation-diagnostics.yml` | diagnostic extension | Closed; see `docs/results/`. |
| `dynamic-breadth.yml` | `dynamic-breadth-v1` | Closed; see `docs/results/`. |
| `region-quota-removal.yml` | `region-quota-removal-v1` | Closed; see `docs/results/`. |
| `entry-selection-separation.yml` | `entry-selection-separation-v1` | Closed; see `docs/results/`. |
| `lowvol-alpha-separation.yml` | `lowvol-alpha-separation-v1` | Closed; see `docs/results/`. |
| `alpha-calibration-resolution.yml` | `alpha-calibration-resolution-v1` | Closed; see `docs/results/`. |
| `four-factor-signal-attribution-audit.yml` | `four-factor-signal-attribution-audit-v1` | Closed; see `docs/results/`. |
| `fundamental-acceleration-discovery.yml` | `fundamental-acceleration-discovery-v1` | Closed historical discovery; prospective sealing remains separate. |
| `regional-rotation.yml` | `regional-rotation-v1` | Closed; see `docs/results/regional-rotation-report.md`. |

The retirement table is an audit trail, not a list of workflows to restore.
