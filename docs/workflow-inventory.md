# Workflow inventory

What is actually in `.github/workflows/` today, why, and where a closed
study's results still live. Written for an operator who wants to know what
to click, not what was tried — see `docs/results/` and this file's RETIRED
section's links for the numbers.

Before this pass (`workflow-hygiene-live-data-fixes-v1`, 2026-09-24): 25
workflow files, most of them one-shot research studies already closed and
published. After: **9**. Nothing was deleted from the repository — every
retired workflow's code, its `docs/results/*` artifact, and the workflow
file itself all still exist in git history; only the Actions "Run workflow"
entry point was removed.

## ACTIVE

Workflows that run production infrastructure or standing evidence
collection — the ones an operator actually depends on.

| Workflow | Schedule | Manual run needed? | What it does |
|---|---|---|---|
| `Tests` (`tests.yml`) | on every PR / push to `main` | No — runs automatically | Full test suite + lint gate before merge |
| `Build insight data and deploy Pages` (`pages.yml`) | daily 08:20 KST + on push to `main` | No | Builds `data/site-data.json` and deploys the public dashboard |
| `Append paper-signal ledger` (`ledger.yml`) | daily 00:10 UTC | No | Appends the day's cross-section to the immutable signal ledger (`signal-history` branch) |
| `Collect fundamentals` (`fundamentals.yml`) | daily 03:40 UTC | No (`auto` mode picks statements-then-shares itself) | DART (KR) + Finnhub (US) point-in-time fundamentals collection |
| `Collect universe history` (`universe.yml`) | monthly, 1st, 04:20 UTC | No | Monthly index-membership snapshots |
| `Historical point-in-time replay` (`replay.yml`) | daily 02:40 UTC | No (incremental) | Extends the sealed `replay-v16` historical ledger and weekly ML retrain |
| `Collect DART ownership events` (`dart-ownership-events.yml`) | none — `workflow_dispatch` only | **Yes, `mode: auto`** (see below) | KR 5%-rule ownership disclosure collection (DS004) |
| `Seal fundamental acceleration signal` (`fundamental-acceleration-seal.yml`) | none yet — `workflow_dispatch` only, deliberately (see its own header comment) | Yes, periodically, until converted to a schedule | Appends today's fundamental-acceleration reading immutably, before its 126-day horizon can be known, building the prospective sample `fundamental-acceleration-discovery-v1` is a bridge for |
| `Probes` (`probes.yml`) | none — `workflow_dispatch` only | On demand | One dropdown covering every external-source availability check (see below) |

**`Collect DART ownership events`, `mode: auto` (the default) is the one
button this whole PR was written to make sufficient**: it runs a small
schema probe first, and only proceeds to collect if that probe reports
`SERVED`. If the source or key is refused, or an expected field goes
missing, the run stops and is reported as a failed job — never a quiet
success with nothing collected. Collection resolves the PIT historical KR
membership union to DART issuer identities, then resumes by issuer and raw
contract. `probe` also checks the official filing index for disclosures older
than the bounded `majorstock.json` response; that depth check may report
`BLOCKED_HISTORICAL_DEPTH` without changing the endpoint schema verdict.
`probe`/`collect` remain as explicit manual overrides.

## ON-DEMAND PROBES

Not part of daily operation — these measure whether an external source is
currently reachable, so "is it still blocked?" is always a single dropdown
selection and a click away, never a bespoke workflow to write. All routed
through `.github/workflows/probes.yml`'s `probe` input.

| Probe | Source | Last confirmed status (2026-09-24) |
|---|---|---|
| `sec-egress` / `sec-headers` / `sec-fundamentals` / `sec-bulk-datasets` | SEC (Form 4, 8-K, bulk financial statements) | `BLOCKED` — site-wide from this repo's Actions IP pool |
| `guru-13f-access` | SEC 13F bulk dataset + per-manager submissions | `BLOCKED`, route `NONE` (run 35964478931) — see `docs/guru-decision-atlas-data-v1.md` |
| `fmp-fundamentals` | Financial Modeling Prep | see `docs/results/` for the most recent cap measurement |
| `dart-fundamentals` | DART DS002 (statements) | `SERVED` — production already depends on this |
| `krx-index-membership` | KRX Open API | mixed — per-endpoint, see `AGENTS.md`'s vendor-refusal invariants |
| `kr-investor-flow` | KRX public statistics portal (investor-type net trading) | `BLOCKED_SOURCE` — HTTP 400 `LOGOUT` on the first call (run 35963936572) |
| `kr-short-selling` | KRX public statistics portal (short-sale screens) | `BLOCKED_SOURCE` — HTTP 400 on every `MDCSTAT301`/`MDCSTAT305` candidate tried (run 35964424923) |
| `us-pit-fundamentals` / `us-delisted-prices` | Multi-vendor PIT fundamentals / delisted-price fallback chain | see `docs/results/` |
| `alfred-macro-vintages` | ALFRED (FRED vintages) | permanently closed for 10 of 28 panel columns — see `AGENTS.md`'s macro-vintage invariants |
| `kr-delisting-coverage` | Korean delisted-name price coverage | see `docs/results/` |

A `BLOCKED` verdict here is never retried automatically and never silently
worked around (no scraping, no proxy rotation, no CAPTCHA bypass) — see
`AGENTS.md`. Re-running the same probe after a vendor changes something is
the entire point of keeping it on this list.

## RETIRED RESEARCH

Removed from the Actions menu because the study is closed: a verdict was
reached, published to `docs/results/`, and no rung promotes production. The
workflow file, its code, and its results all remain in git history and can
be restored (`git log --diff-filter=D -- .github/workflows/<name>.yml`) if
a study needs to be re-run under a materially new condition — never as a
same-sample re-tune (see `AGENTS.md`'s selection-value invariants on why
that specific failure mode is disallowed here).

| Retired workflow | Study | Verdict | Results |
|---|---|---|---|
| `regional-alpha-model.yml` | `regional-alpha-model-v1` | `EXECUTED` / `NO_MODEL_EVIDENCE` (US & KR) / historical discovery closed on the existing 31-feature matrix | `docs/alpha-research-foundation-v2-errata.md` |
| `benchmark-alpha.yml` | `benchmark-relative-alpha-v1` | `BENCHMARK_NOT_BEATEN` | `docs/results/benchmark-alpha-report.md` |
| `selection-value.yml` | `selection-value-decomposition-v1` | read-only diagnostic, no promotion | `docs/results/selection-value-report.md` |
| `switch-hurdle.yml` | `regional-switch-hurdle-v1` | first paired interval to clear zero (+2.757pp), still not promoted (`promotionEligible: false`) | `docs/results/switch-hurdle-report.md` |
| `signal-persistence.yml` | `signal-persistence-v1` | all point estimates same direction, no rung separates | `docs/results/signal-persistence-report.md` |
| `alpha-reliability.yml` | `alpha-reliability-v1` | confidence-shrinkage rung refuted by its own pre-test | `docs/results/alpha-reliability-report.md` |
| `alpha-risk-separation.yml` | `alpha-risk-separation-v1` | paired interval contains zero | `docs/results/alpha-risk-separation-report.md` |
| `alpha-risk-separation-diagnostics.yml` | diagnostic extension of the above | read-only, no score/rule changed | `docs/results/` (same study) |
| `dynamic-breadth.yml` | `dynamic-breadth-v1` | paired interval contains zero | `docs/results/` |
| `region-quota-removal.yml` | `region-quota-removal-v1` | point estimate worse, interval contains zero | `docs/results/` |
| `entry-selection-separation.yml` | `entry-selection-separation-v1` | paired interval contains zero (4th and last study `alpha-reliability-v1` pre-registered) | `docs/results/` |
| `lowvol-alpha-separation.yml` | `lowvol-alpha-separation-v1` | Case B — sleeve removal does not help | `docs/results/` |
| `alpha-calibration-resolution.yml` | `alpha-calibration-resolution-v1` | Case B — ordinal rescue does not help | `docs/results/` |
| `four-factor-signal-attribution-audit.yml` | `four-factor-signal-attribution-audit-v1` | no sleeve clears significance; region-sign-unstable | `docs/results/` |
| `fundamental-acceleration-discovery.yml` | `fundamental-acceleration-discovery-v1` | Case D — no discovery evidence | `docs/results/` |
| `regional-rotation.yml` | `regional-rotation-v1` | validated CHALLENGER, all timing-metric CIs contain zero | `docs/results/regional-rotation-report.md` |

See `AGENTS.md` for the full, dated invariant write-up behind every row
above — this table exists to say where to click, not to re-argue any of
them.

## Judgment calls made, and why

- **`fundamental-acceleration-seal.yml` stayed ACTIVE, not RETIRED.**
  Unlike every workflow in the RETIRED table, it is not a closed backward
  -looking study — it is the mechanism accumulating the genuinely
  prospective sample `fundamental-acceleration-discovery-v1`'s own design
  doc named as the confirmatory evidence a same-sample replay can never be.
  Its own header comment says converting it to a schedule is "a follow-up,
  not decided here" — this PR does not decide that either; it stays a
  manual, periodic trigger.
- **`dart-ownership-events.yml` stayed ACTIVE and was simplified, not
  retired** — its probe is `SERVED` (measured 2026-09-24), unlike the two
  KRX-portal sources folded into `Probes`.
- **`kr-investor-flow.yml` was removed entirely (not merely trimmed)**
  rather than kept as a collect-only workflow with its probe jobs moved
  out. Both of its axes (investor flow, short-selling) measured
  `BLOCKED_SOURCE`; a collect workflow with nothing to collect is exactly
  the clutter this pass exists to remove. `scripts/collect_kr_investor_flow.py`
  and `scripts/collect_kr_short_selling.py` are unchanged and still callable
  manually (`gh workflow run` against a restored workflow file, or a new
  one) once a probe reports `SERVED`.
- **`guru-13f-backfill.yml` was removed for the same reason**, after its
  own probe run measured `BLOCKED`/`NONE` directly rather than by inference
  from an adjacent SEC measurement.
