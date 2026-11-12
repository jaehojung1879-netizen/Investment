# Current release and PR consolidation — 2026-11-12

**Actual cleanup:23 open →17, closed #299/#306/#320/#322/#327/#330 with replacement comments.** Six remote branches and their exact heads remain. #307/#314/#328/#332 were retargeted to main without HEAD changes. [Single follow-up PR register](../../docs/integration-20261110/PR-REGISTER-20261112.md) · [Exact inventory/blob/CI/log evidence](consolidation-20261112.json.gz) · [Versioned verification](verification.json). No new PR, main merge, deploy, dispatch, writer activation or historical study execution.

## Latest #334 moved during final verification; the delta is now checked

#334 advanced from `2e1cef5987eaee0f72d3b33fb8358c54e5da9dd5` to **`645d9fe0b3693a219693234468b70f43bc7f0bd2`** with author repairs8c6d382(G14) and645d9fe0(G16), six files,+151/−11. Only the changed scope was rechecked; old whole-suite results are not transferred to the new HEAD.

**G14 and G16 are now independently PASS.** The same three assertions fail on2e1cef59 and pass on645d9fe0. New fact fields/duplicates/nonfinite or unsourced values are refused. Preview and stale production data are qualified in the top summary, detailed card and selection table. Actual data/desk.json and its pin, production weights and original six November rows did not change. This is evidence of real fixes, not trust in the author's report.

| Latest test layer | Actual result and limit |
|---|---|
| Independent suite | **49 PASS/2 typed strict XFAIL**; --runxfail gives2 FAIL/49 PASS, only residual G1/G2 missing historical vintage/publication provenance |
| Latest changed area + old terminal | **113 PASS** on exact645d9fe0+#321; contains both research folders and original terminal/Python→Node protection tests |
| Latest browser | KR/US×1280/390 PASS, no page errors/overflow, pinned Git responses. Rendering PASS is not deployed Pages success |
| Earlier full local integration | **6612 PASS/2 FAIL/3 SKIP/4 existing XFAIL**,3273.56s, exact2e1cef59+#321 only. Both failures lack pinned8b43d6ee historical script blobs in the filtered checkout; exact hydration gives2/2 PASS. No clean single-run full PASS, and no latest645d9fe0 full rerun, is claimed |
| Unchanged #321 operating/protection checks |128 PASS reused; none of the six new files changes that closure.235 protected hashes, original six records and formal-job bytes remain unchanged |
| Remote PR CI | #321 exact6521 PASS; latest #334 run43203465272 at645d9fe0 IN_PROGRESS. Previous2e run1 FAIL/6516 PASS from threadpoolctl3.8.0 |
| Normal Pages/deploy/state | Latest main run43150678545 has1 FAIL/6423 PASS; normal build/deploy/state skipped. #321 green Pages was diagnostic-only. Actual deployment and publication were not run |

Latest local merge **`c697056b5381faa7ba0c98950f0914a546d54bc6`**, parents645d9fe0/cd2892eb, tree **`4b6ede8d3324b1ae03d09e57192a6004ef545729`**; conflict0 and reverse-order tree agrees. Main remains37f8cbf6. #315 parent23522002, registration05957005 and consumed09ba076f remain ancestors. This merge was not pushed. #307 still conflicts in app.js/index.html; #314 tree merge is clean.

## Current gate decisions

- G1/G2: metadata-bearing future values are refused; missing legacy vintage/publication still strict XFAIL and blocks DESK_V2_B2. New PROSPECTIVE_V1 has no macro input and retains separate CI_GREEN/Owner gates. No writer/BX is activated.
- G3/G4/G13: same-day timestamps, numeric claims on actual decide path, review-before-seal rejection PASS.
- G5/G6/G7: append-only blocked retries, invalid quotes and primary exclusion PASS. Both contaminated B2 records and all three unobserved-before-deadline US November records are excluded.
- G8/G9: contemporaneous public reachability versus late observation and undoing future split adjustment PASS within stated conventions. Git time/order is not trusted first-publication or proof of the reviewer's knowledge independence.
- G10: the clarified deadline refuses all-path backfilling. It does not implement the old late B0/B1 fallback promise.
- G11/G12:32 concurrent local appends/CAS and official1x/2x persisted evaluation PASS. This does not establish a multi-clone production writer transaction.
- G14/G16: fixed and independent positive regressions now retained in this same audit; previous strict markers were removed only after the failures/PASS controls.
- G15: actual builder supplies field-specific metadata;40 financial facts across10 dossiers retain their own reportDate/availableFrom. No old ROE-date failure is carried forward as if unfixed.

Read-only metadata checks match membership hash/change2026-08-19/gap83days, mixed-period KR70/US354, GOOGL's carried2020-06-30 share source/B/P2.4455, and WDC's invalid per-share fact flag. This generic carry-age flag is not independent certification of every split/shareholder-return account. ROE remains an internal proxy, FF OP partial and GP/A unavailable; zero strategies are validated for capital.

**#334 is now MERGE_CANDIDATE, not merge-approved.** Exact #321 Owner plain-merge approval covers A pins+B existing post-deploy state publisher+C closed read-only provenance. Observe real main CI/normal Pages/state/ledger preservation. Then the author merges that main into #334, obtains exact combined remote CI, and requests separate read-only publication approval on the new exact HEAD. No general latest-head full PASS or actual Pages deployment has been established here. Do not add another dependency fix or audit PR.

Other preserved checks: #307 Node35 PASS, #314 shadow57+daily/hook45 PASS, seed validation PASS and production seed acceptance REFUSED in a separate worktree. #328's additional synthetic rebase failure is missing committer identity (two environments reproduce FAIL/PASS), not only the common pin; repair comment6820644611 names the fixture. #326 retains eight additional workflow-protection failures, DO NOT MERGE. Existing C2 annotated claim4944827a→9dc2928d stays untouched; old claim-absence comments are not current execution authority.

## Reproduce the latest tree in an isolated worktree

```bash
git fetch origin refs/pull/321/head refs/pull/334/head
git worktree add --detach /tmp/desk-latest 645d9fe0b3693a219693234468b70f43bc7f0bd2
git -C /tmp/desk-latest merge --no-ff --no-edit cd2892eb6d6623c2527eeda690959d18839acc4d
# Use Python3.11 and prepare pinned historical Git objects before no-lazy-fetch checks.
pip install -c /tmp/desk-latest/constraints/ci-registered-numerics-v1.txt -r /tmp/desk-latest/requirements.txt -r /tmp/desk-latest/requirements-dev.txt
AUDIT_TARGET=/tmp/desk-latest python -m pytest -q audits/desk_preflight_20261111/test_independent.py
AUDIT_TARGET=/tmp/desk-latest python -m pytest -q --runxfail audits/desk_preflight_20261111/test_independent.py # expected exactly2 failures
# For browser.cjs serve the target on loopback; AUDIT_URL overrides the default8765 port.
```

---

## Historical preflight below — 2026-11-11 d876/ef2 inputs only

The original report remains historical evidence. Its old current-verdict wording,15 strict XFAILs and earlier suite failures do not describe the latest HEAD.

# Decision desk: independent release preflight

**Current verdict: #321 + latest #334 `ef2f012b` merge cleanly, but release readiness is not PASS.** The refreshed census has a Python-version-dependent metadata reproducibility failure. The desk is an experimental disclosure with zero current stock selections, not a validated stock selector. Keep its writer/evaluator disabled. This is a focused delta to [#333](https://github.com/jaehojung1879-netizen/Investment/pull/333), not a new research program.

No existing branch, workflow permission, allocation, sealed result, lock or production ref was changed. This branch adds only this audit directory. Local merge commits were not pushed. Owner approval remains necessary for integration and deployment.

## Latest HEAD moved during the audit: current findings supersede the old UI assessment

#334 advanced from `d876c6f0` to **`ef2f012bca5a5c4a513497eb5841f46a47325ce0`** (three commits, 51-file delta). Its Evidence-First v2 now discloses **KR 300→78 factor-complete→61 B1-eligible→5 reviewed→0 selected; US 503→356→206→5→0**. This is a separate dated census, not an enlargement or repair of the original November 12/12 cohort. US membership is current survivors; liquidity is a membership proxy without volume checks. KR is a top-300 snapshot at 2026-10-30, US 2026-11-10; neither is an unrestricted full-market universe.

Improvements verified: all non-benchmark paths remain **E0/E1, zero decision-eligible**; new dossiers are HOLD_FOR_RESEARCH; digit-bearing AI prose and future-dated facts are refused. Legacy B1 maps to **v3.B2 production**, legacy B2/BX to **v3.B3 AI**, with every original ledger byte preserved. **v3.B1 is an academic screen, not an executed independent rule portfolio**. The old contaminated cohort is now explicitly archived and keeps its exclusion badges. Claims of calibrated AI returns, optimal 10% sizing or investability remain unsupported. The new academic translation remains weak/E1; its arithmetic replication is not alpha validation.

**Latest technical blocker:** the combined changed-area suite gives **172 PASS /1 FAIL** (`test_census_reproduces_from_the_pinned_signal_history_commit`). A second isolated run reproduces it. Independent recursive comparison finds **exactly two differences, both `/regions/{KR,US}/b1/rule` whitespace**; all numbers, nominees and funnel counts agree. `census.py` serializes `b1_screen.__doc__.strip()`. A definition-only probe proves CPython **3.11.17 versus 3.13.5** produces different `.strip()` strings and equal `inspect.cleandoc()` strings. **Claude should explicitly canonicalize the rule string and regenerate census → dossiers → desk and its app pin, retaining the exact equality assertion.** No scientific result or original November record needs changing. [Mismatch](latest-census-diff.json) · [probe](probe_docstring.py).

New independent contract gaps: **G14** unknown fact fields bypass the census-value check, allowing an invented numerical fact; **G15** `contract.facts_from_census` assigns ROE's filing/publication date to every financial field, although `census.latest_filings` tracks field-specific sources. Preserve each field's actual provenance or narrow the date claim; unknown facts must be refused. These supplement the unchanged legacy evaluator/PIT/append gaps below.

Latest independent suite: **21 PASS /15 typed strict XFAIL**; `--runxfail`: **15 FAIL /21 PASS**. Latest desktop/mobile + fresh legacy browser checks PASS, public desk pin SHA256 **`fb005a25877efdb36f1ed876343b00c5541700f2eb059550fd85c43b2aa39c62`** matches. Latest remote Tests **43118847675 was IN_PROGRESS**, not PASS. The completed full suite below applies to the earlier `d876c6f0` merge, not this refreshed HEAD; latest changed areas and unchanged maintenance guards were tested separately.

**Current release order:** Owner may first approve exact #321 plain merge including its existing state publication consequence; observe real normal Pages/state/ledger preservation. Before approving #334 read-only publication, obtain Claude's canonical metadata fix, correct/narrow fact provenance, and **remote combined CI on the new exact HEAD**. Keep writer/evaluator/BX disabled pending their independent failures. The population and archival UI corrections previously requested are substantially implemented; do not ask Claude to redo them. Prospective fixes need a versioned contract; never repair November retrospectively.

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
| #334 latest | `ef2f012bca5a5c4a513497eb5841f46a47325ce0` (initially `d876c6f0dd87dc9e34fdb081631f8a85f649e37c`) |

Latest local merge **`f497814dd6dbcb2fb7abdf997870e962f54d30fb`**, parents **ef2f012b, cd2892eb**, tree **`fb738918bd6a1561ea0ff7e97b9b757337a6ec99`**, has no conflicts; reverse-order merge-tree agrees. Earlier completed baseline merge `37b24def6da03095ed60c86c9e83167f0c058402` has parents **d876c6f0, cd2892eb**, tree `0ad82bca2b021ff18eaa416695577443014fc71e`. Both preserve #315 parent `23522002`. Neither is remote combined CI or production deployment.

## Evidence chain: what the implementation actually establishes

**The following table audits the legacy November pipeline, unchanged at latest HEAD.** Paths are in `research/decision_desk_v1/` unless prefixed otherwise. Its population limitations do not describe the new separate 300/503 census above.

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

At latest HEAD `test_independent.py` has **21 passing cases +15 strict expected failures**, each constrained to its intended failure type. Running `--runxfail` produces **15 FAIL /21 PASS**, including actual future-information injections. Initial-head results were 18 PASS /13 XFAIL; the new dossier rejects digits/future dates but has G14/G15. These are unmet release assertions, not a clean safety PASS. No assertion in existing tests was relaxed.

| Gap | Counterexample / required treatment |
|---|---|
| G1/G2/G9 | Revised old observations, future fundamental publication and future split-adjusted quotes survive. Label vintage limits explicitly; enforce timestamp/vintage provenance before a clean prospective performance claim. |
| G3 | `validate_desk.py:19` compares full cutoff with date-only generation; a valid **same-day** v2 record is rejected. Later-day reviews pass. Fix timestamp parsing in both publication validators before using that case. |
| G4/G8 | Prose forecast and publication/independence claims exceed automated verification. Narrow visible claims; validate prose/review evidence and obtain a server-observed publication receipt for stronger claims. |
| G5/G6 | `evaluate.py:127` permanently suppresses SOURCE_BLOCKED retries; constant zero quotes silently score a flat gross return minus costs. Require finite positive prices and append-only superseding evaluation records. |
| G7/G12 | Primary exclusion is not machine-enforced; `desk.py:356` calls only 1x even though the helper supports 2x. Add explicit eligible-comparison membership and persist/render both costs. |
| G10 | `desk.py:196` refuses **all** records after deadline; it does not automatically record the promised B0/B1 + B2_NO_REVIEW fallback. Clarify/fix the missed-deadline path without backfilling B2. |
| G11 | `ledger.py:163` has no lock/CAS. Two concurrent valid appends fork the hash chain. Keep this writer disabled/single-process; use an atomic append transaction before activation. Existing production ledger and #321 state publisher are separate paths. |
| G13 | `desk.py:196` calls `judgment.check_review` directly, bypassing `cmd_check_review`'s generation-after-packet-seal check. A review dated before packet sealing produces v2 records. Require stage/time validation in the actual decide path. |
| G14/G15 | New `evidence_first_v2/contract.py`: unknown fact names evade value matching; financial fact dates all reuse `roeFrom`. Tested separately at latest HEAD; not failures of the improved digit/future-date rejection. |

## CI / Pages / release decision

- #321 exact remote Tests [42369756685](https://github.com/jaehojung1879-netizen/Investment/actions/runs/42369756685): **6,521 passed**. Install log independently confirms threadpoolctl **3.7.0**, joblib **1.6.0**.
- #321 Pages [42369756681](https://github.com/jaehojung1879-netizen/Investment/actions/runs/42369756681): **matrix-diagnostic success; build-and-deploy SKIPPED**. Not a production deployment PASS.
- #334 exact remote Tests [43113069420](https://github.com/jaehojung1879-netizen/Investment/actions/runs/43113069420): **1 failed /6,473 passed**, same threadpoolctl **3.8.0** failure. This is not a remote CI PASS; the combined local constraints are not on its branch.
- Latest main Pages [43055527324](https://github.com/jaehojung1879-netizen/Investment/actions/runs/43055527324): **1 failed /6,423 passed**, installed threadpoolctl **3.8.0**, expected SINGLE_THREAD but raised PINNED_DEPENDENCY_VERSION_REQUIRED. Deploy/state publication SKIPPED. **Common CI failure remains on main.**
- Local combined: **50/50 desk tests**, legacy/desk Node contracts, Ruff/compileall, **235 protected hashes**, unchanged `research_specs/`, `docs/results/`, requirements, and unchanged #334 UI/research bytes. State-publisher concurrency, base-tree preservation, force:false retry and old ledger tests are exercised; actual branch-policy/token/disk behavior is not established by mocks.
- Initial-head desktop/mobile browser: **KR/US ×1280/390 PASS**, no overflow/page errors, plus fresh pinned legacy ETF receipt renders correctly. These use exact Git response replay, not a production URL/deployment. The real public DESK raw URL separately returned bytes matching SHA256 `7d03a711…d3d20e`. Historical/stale C1/C2 blocks remain visible; no allocation is changed.
- **Earlier-head full combined suite:** 6,559 PASS /12 FAIL /3 SKIP /4 XFAIL in 2,096.61s. All 12 failures were missing historical Git blobs; after hydration, **all 12 PASS in 2.95s**. Every test passes across those runs, but **there was no clean single-run full PASS**. Latest-head changed-area suite instead has the real metadata mismatch above. See [verification.json](verification.json); do not transfer old-HEAD/full-suite labels to latest HEAD.

**Owner action:** follow the current release order at the top. Exact #321 approval includes its existing deploy/state behavior because a main push triggers normal Pages. Exact #334 approval stays conditional on the metadata fix, accurate fact provenance and remote combined CI. No new writer, BX, license purchase or historical study execution is authorized by this audit.

**Answer:** verified are frozen-record preservation, legacy selected-pool accounting, latest census numerical/nominee agreement, scoped synthetic return arithmetic and ancestry-preserving local integration. Experimental are stock-selection value, AI interpretation, fixed sizing, full PIT/vintage independence and future executable economics. Latest publication needs explicit census metadata canonicalization, accurate/narrow fact dates, approved #321 operations, exact combined remote CI and approved read-only #334 publication. No writer activation or production deployment is approved or claimed here.

## Reproduction

```bash
git fetch origin main signal-history refs/pull/321/head refs/pull/329/head refs/pull/330/head refs/pull/331/head refs/pull/332/head refs/pull/333/head refs/pull/334/head
# In a NEW detached worktree at ef2f012b (never Claude's active worktree):
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
