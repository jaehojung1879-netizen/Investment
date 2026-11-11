# Decision desk: independent release preflight

**Verdict: #321 + #334 integrate cleanly. The read-only desk is an experimental research disclosure, not a scientifically validated stock selector. Do not activate its writer/evaluator yet.** This is a focused delta to [#333](https://github.com/jaehojung1879-netizen/Investment/pull/333), not a new research audit or a strategy run.

No existing branch, workflow permission, allocation, sealed result, lock or production ref was changed. This branch adds only this audit directory. Local merge commits were not pushed. Owner approval remains necessary for integration and deployment.

## Exact versions

| Ref | Actual HEAD, refreshed 2026-11-11 UTC |
|---|---|
| main | `37f8cbf6b1c066f6b3c65235953648d17ebf2f69` |
| #321 | `cd2892eb6d6623c2527eeda690959d18839acc4d` |
| #329 | `0a1f494171576af6928fe531145a8c8f050253fd` |
| #330 | `8657acd5dd840617fc25a6a0cce467294edf72bf` |
| #331 | `49c3aa891b1e85520c2a90d0d062678a738a87cf` |
| #332 | `0f39c2fef93a9cf924f45ae87662de41090f2528` |
| #333 | `61d0d3f6b003ecb95af7af1dcde1911030b4f95d` |
| #334 | `d876c6f0dd87dc9e34fdb081631f8a85f649e37c` |

Local merge `37b24def6da03095ed60c86c9e83167f0c058402` has parents **#334, #321**, tree `0ad82bca2b021ff18eaa416695577443014fc71e`. Reverse-order `git merge-tree --write-tree <321> <334>` gives the same tree. Both PR histories and #315 parent `23522002` remain reachable. No conflict; this does not establish remote combined CI or production deployment.

## Evidence chain: what the implementation actually establishes

Paths below are in `research/decision_desk_v1/` at exact #334 unless prefixed otherwise.

| Link / requested check | Independent finding |
|---|---|
| Receipts → universe (A/B/C) | `evidence.py:45,61` verifies production receipt digests and unions receipt candidates/watchlist. Each region has **12 preselected longTerm picks**, **5 enriched watchlist entries**, union **12**, not 12 watchlist entries or an independent market scan. `pipeline/weekly_decision.py:664,696` identifies the pool; `pipeline/longterm.py:509` caps picks at 8–12. **7/12 lack coverage/risk/fundamental detail**, so eligibility is effectively confined to the 5 enriched names. The receipt discloses selected-pool denominator 12; the upstream full screened/eligible population and selection attrition are absent from the packet/desk. Broad discovery/market coverage claims are unsupported. |
| Gates → AI → weights (D/F/G) | `evidence.py:76`, `judgment.py:50,107` reproduce KR **1/12** and US **3/12** gate passers; B2 selects KR 0, US TRV. These are deterministic checks of a selective packet, not evidence that the ranking predicts returns. **10% is a frozen experimental sizing convention**, not an estimated optimum. `protocol.json.authorExposureDisclosure` acknowledges seeing candidates before fixing rules; protocol/review/first records share commit `860a1845`. Labels have no calibrated probability or expected-return mapping. Forbidden JSON keys are refused, but free prose containing “Expected return 999% with 100% probability” passes (G4). |
| Portfolio controls (E) | November B0 = B1 = 100% 069500.KS / SPY. B1 faithfully copies the production receipt; it is **not an independent active rule challenger**. KR B2 also equals the ETF. US B2 tests only a 10% TRV overlay on 90% SPY. No evidence of AI alpha or optimal sizing follows. |
| Frozen ledger → publication (H/I) | First six lines retain SHA256 `3854d94f…c7b050`; annotations identify exactly both B2 records as `PIT_CONTAMINATED`. Both card and ledger show exclusion badges. `desk.py:296` checks commit time and current remote reachability: useful Git provenance, **not a trusted first-push timestamp or proof of reasoning independence** (G8). Commit-reveal cannot prove what an agent read or remove pretrained knowledge. No actual falsification of the November commit time is alleged. |
| Evaluator → primary comparison (H) | `evaluate.py:127` scores every record and ignores contamination/independence annotations. `build_desk.py:111` joins badges back for display, but outcomes have no primary-comparison eligibility flag/filter (G7). There is currently no aggregate primary score; therefore exclusion is a display/protocol promise, not an enforced statistical comparison. |
| History → web (D) | `build_desk.py:159` copies pinned published results, with exploratory/corrected/blocked types; blocked history is null, old US allocation is explicitly reconstructed. This is disclosure, **not promotion**. #333's historical restrictions remain: KR strategy momentum +15.49pp is phase0/outcome-exposed, Holm .186; stock cash economics remain SOURCE_BLOCKED; US FX PIT claim withdrawn. These results were not rerun here. |

## Time and return verification

**PASS within stated conventions:** H.10 2026-11-05 observation releases **11-09 21:15Z**; H.15 11-05 observation releases **11-06 21:15Z**, after the US **21:00Z** cutoff. Holiday/DST boundary checks pass. Official Fed H.10/H.15 pages were retrieved independently; the H.15 schedule is inferred from dated release columns, VIX's next-business-day rule is conservative rather than a verified FRED posting time. KR close is **06:30Z**; US 11-06 closing bars cannot enter that day's Korean cutoff. Injected future observations/bars are rejected. Original November inputs/reviews/decisions were not repaired.

**Unverified PIT scope:** packet v2 retains observation dates and scheduled availability, receipt generation, packet sealing, review generation, self-reported publication, and execution deadline. Its manifest contains acquisition time. **Original publication/vintage/revision timestamps of each fundamental and revised FRED observation are not enforced.** `packet.py:34,43` reads current vendor history; revision metadata disappears. Future revision and future fundamental-publication injections change/pass the prior decision inputs (G1/G2). Yahoo split-adjusted prior prices retain future split knowledge (G9); rescaling *both* dividends and prices leaves total returns invariant, but does not authenticate as-traded historical price levels or vintage fundamentals. Schedule filtering alone is not PIT_EXACT.

**Forward arithmetic PASS:** synthetic 10% stock /90% ETF with returns 20%/10% and costs .4%/.1% gives **10.853% net**, **.963pp excess**; flat prices give **−.13%** cost and **−.26%** at 2x. The same dates are passed to the benchmark. Endpoints are `sessions[126]` / `[252]`, excluding entry, using XKRX/XNYS calendars. Entry-day distributions are excluded; split-adjusted quotes plus equally adjusted dividends are counted once. Missing quotes, zero volume, missing exit/delisting, unverified splits and unexplained moves block rather than become 0%.

**Execution/economics limits:** November's first close references are US **11-11 21:00Z**, KR **11-12 06:30Z**, after the initial record commit. They are closing-auction reference prices, not broker fills; no auction order/size/liquidity evidence exists. v2 fixes the common execution session after a 48h review window and its open as registration deadline. Returns are **regional local currency (KRW/USD)**, without cross-currency aggregation. Ex-date immediate dividend reinvestment is a total-return-index convention, not payment-date cash accounting; taxes/withholding and cash receivables are not modeled. Terminal proceeds/share exchanges are not implemented: missing exits remain SOURCE_BLOCKED, not certified losses. A trusted corporate-action package is still needed.

## Reproduced gaps and release gates

`test_independent.py` has **18 passing cases +12 strict expected failures**. Running `--runxfail` produces **12 FAIL /18 PASS**, including actual future-information injections. These are unmet release assertions; the default xfail summary must never be called a clean safety PASS. No assertion in existing tests was relaxed.

| Gap | Counterexample / required treatment |
|---|---|
| G1/G2/G9 | Revised old observations, future fundamental publication and future split-adjusted quotes survive. Label vintage limits explicitly; enforce timestamp/vintage provenance before a clean prospective performance claim. |
| G3 | `validate_desk.py:19` compares full cutoff with date-only generation; a valid **same-day** v2 record is rejected. Later-day reviews pass. Fix timestamp parsing in both publication validators before using that case. |
| G4/G8 | Prose forecast and publication/independence claims exceed automated verification. Narrow visible claims; validate prose/review evidence and obtain a server-observed publication receipt for stronger claims. |
| G5/G6 | `evaluate.py:127` permanently suppresses SOURCE_BLOCKED retries; constant zero quotes silently score a flat gross return minus costs. Require finite positive prices and append-only superseding evaluation records. |
| G7/G12 | Primary exclusion is not machine-enforced; `desk.py:356` calls only 1x even though the helper supports 2x. Add explicit eligible-comparison membership and persist/render both costs. |
| G10 | `desk.py:196` refuses **all** records after deadline; it does not automatically record the promised B0/B1 + B2_NO_REVIEW fallback. Clarify/fix the missed-deadline path without backfilling B2. |
| G11 | `ledger.py:163` has no lock/CAS. Two concurrent valid appends fork the hash chain. Keep this writer disabled/single-process; use an atomic append transaction before activation. Existing production ledger and #321 state publisher are separate paths. |

## CI / Pages / release decision

- #321 exact remote Tests [42369756685](https://github.com/jaehojung1879-netizen/Investment/actions/runs/42369756685): **6,521 passed**. Install log independently confirms threadpoolctl **3.7.0**, joblib **1.6.0**.
- #321 Pages [42369756681](https://github.com/jaehojung1879-netizen/Investment/actions/runs/42369756681): **matrix-diagnostic success; build-and-deploy SKIPPED**. Not a production deployment PASS.
- #334 exact remote Tests [43113069420](https://github.com/jaehojung1879-netizen/Investment/actions/runs/43113069420): **1 failed /6,473 passed**, same threadpoolctl **3.8.0** failure. This is not a remote CI PASS; the combined local constraints are not on its branch.
- Latest main Pages [43055527324](https://github.com/jaehojung1879-netizen/Investment/actions/runs/43055527324): **1 failed /6,423 passed**, installed threadpoolctl **3.8.0**, expected SINGLE_THREAD but raised PINNED_DEPENDENCY_VERSION_REQUIRED. Deploy/state publication SKIPPED. **Common CI failure remains on main.**
- Local combined: **50/50 desk tests**, legacy/desk Node contracts, Ruff/compileall, **235 protected hashes**, unchanged `research_specs/`, `docs/results/`, requirements, and unchanged #334 UI/research bytes. State-publisher concurrency, base-tree preservation, force:false retry and old ledger tests are exercised; actual branch-policy/token/disk behavior is not established by mocks.
- Desktop/mobile browser: **KR/US ×1280/390 PASS**, no overflow/page errors, plus fresh pinned legacy ETF receipt renders correctly. These use exact Git response replay, not a production URL/deployment. Historical/stale C1/C2 blocks remain visible; no allocation is changed.
- Full combined suite and final remote #334 status: see [verification.json](verification.json) and evidence logs for the completed results; only those exact results may be called PASS.

**Safe order / minimal Owner action:** (1) approve **exact #321 plain merge**, explicitly including its existing production state-publisher change; a main push already triggers normal Pages, so approval must cover that operational consequence. Do not squash away #315 ancestry. Observe main Tests → real build/validation → deploy → state publication, checking ledger subtree identity before/after and normal concurrent ledger ancestry. (2) Claude narrows the visible claims: 12 selected/5 enriched population, identical B0/B1, experimental 10%, uncalibrated AI, November exclusion, and limited Git-time proof. Keep evaluations pending and writer disabled; address evaluator gaps before activation. (3) Incorporate approved main into #334 with preserved ancestry; run remote combined Tests on the new exact HEAD. Owner then approves **read-only #334 merge/publication only**, followed by real URL/hash and old/new-view smoke checks. (4) Writer activation, monthly operator assignment and BX enablement require separate approval after G1/G2/G5/G6/G7/G11/G12 are resolved or explicitly prevented by the operating contract. No source license purchase or historical strategy rerun is necessary merely to publish accurately labeled research.

**Answer:** verified are provenance links, frozen-record preservation, selected-pool/gate accounting, scoped return arithmetic and local integration. Experimental are stock-selection value, AI labels, 10% sizing, full PIT/vintage independence and future executable economics. The website needs approved #321 operational integration, narrower #334 disclosures, exact combined remote CI, then approved read-only publication with production evidence. This audit grants none of those operational approvals.

## Reproduction

```bash
git fetch origin main signal-history refs/pull/321/head refs/pull/329/head refs/pull/330/head refs/pull/331/head refs/pull/332/head refs/pull/333/head refs/pull/334/head
# In a NEW detached worktree at d876c6f0 (never Claude's active worktree):
git merge --no-ff --no-edit cd2892eb6d6623c2527eeda690959d18839acc4d
pip install -c constraints/ci-registered-numerics-v1.txt -r requirements.txt -r requirements-dev.txt
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
python -m pytest -q
python -m pytest -q research/decision_desk_v1
# From this audit-only checkout, point to that merged worktree:
AUDIT_TARGET=/absolute/path/to/merged python -m pytest -q audits/desk_preflight_20261111/test_independent.py
AUDIT_TARGET=/absolute/path/to/merged python -m pytest -q --runxfail audits/desk_preflight_20261111/test_independent.py # expected exit 1
# Serve the merged checkout on 127.0.0.1:8765; browser test needs Playwright + Chromium:
AUDIT_TARGET=/absolute/path/to/merged node audits/desk_preflight_20261111/browser.cjs
```

Partial clones must hydrate pinned historical Git blobs first; missing blobs are an environment failure, not a scientific failure or a reason to weaken assertions. This audit branch alone has no #334 implementation: tests explicitly skip unless AUDIT_TARGET contains it.
