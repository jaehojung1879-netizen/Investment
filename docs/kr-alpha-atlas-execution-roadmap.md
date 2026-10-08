# kr-alpha-atlas — execution roadmap and stopping rules

The project has repeated one loop many times: design, data readiness, model execution, failure, repair, new design. This roadmap is finite on
purpose. Each phase has a fixed deliverable, a gate, a budget and a stopping rule, and the Korean historical program ends after Phase D whatever it
finds. "Finish" means completing this bounded program transparently. It does not mean proving that Korean alpha does not exist.

## Phase A — inventory and design (PR #211, this change)

Delivers: the tournament v1 forensic closure; the registry (`research_specs/kr-alpha-atlas-registry-v1.json`, 106 features in ten families) with
its validator and tests; the information map; the methodology; this roadmap; H2 reclassified as a `CANDIDATE_SIGNAL_FAMILY`; the two prospective
receipt safety repairs (registered-authorization-only live pathway; outcome final only after the maturity session closes).

No outcome access, no workflow dispatch, no production change.

## Phase B — outcome-blind data readiness (next PR, at most two PRs)

Builds:

1. One common PIT feature matrix over the reference universe, from **existing** code, for every registry feature marked READY or
   DERIVABLE_FROM_EXISTING_DATA. In priority order: family D (volume, via `liquidity_attention` on KRX OHLCV, which carries high/low), family E
   (liquidity), family C items already in `accounting_quality`, then H structure (`kr_industry_membership_v4`) and A derivations. Features come out
   of the same functions the receipts will use, so the historical and prospective feature paths are one path.
2. A readiness report with no label anywhere: coverage by feature x year x industry x liquidity tier; universe and membership coverage; terminal-event
   limitations (the 22 terminations, the eight terminal ends in 2018-2026); availability by prediction horizon; and which Level 1-3 contrasts are
   evaluable (enough names per date in every tercile cell).
3. A bounded new-source budget: at most ONE re-probe per blocked source, through the existing `Probes` dropdown (`kr-investor-flow`,
   `kr-short-selling`). A source that does not answer `SERVED` stays `SOURCE_BLOCKED` and the program continues without it. DART
   `alotMatter.json` / `list.json` collection for the ever-top-120 list (J02-J04) is allowed if it fits one collector run. `kr-canonical-v2` coverage
   is re-measured if it has landed, never awaited.
4. The weekly dry-run receipt writer, able to emit only `NOT_READY` / `BLOCKED` (no authorization exists), scheduled nowhere.

Guards: call counters and spy tests prove no target or forward price is built, the same discipline as alpha-opportunity-model-v5's harness.

Stops when: the readiness report is merged. Registry statuses are updated from measured coverage, so a feature can move from DERIVABLE to READY,
or to `DATA_BUILD_REQUIRED` if its coverage is below the 60% floor. Nothing waits for every gap to close.

**Status (Phase B PR):** items 1, 2 and 4 are built and run on the pinned real inputs; item 3 found the existing probe evidence sufficient, so no re-probe was spent.
The outcome-blind matrix, the readiness report, the Phase C eligibility manifest, the source and broader-universe feasibility register and the weekly dry run are described in
`docs/kr-alpha-atlas-phase-b.md`. The registry file is not edited: the report's `measuredStatus` is the measured overlay.

## Phase C — one registered development evaluation (one registration PR, then one execution)

The registration PR freezes, by hash, before any outcome: the data identity; the eligible feature list (READY features from Phase B only); baselines
B0-B4; horizons; the Level 1-3 statistics; the multiple-testing rules; costs; the verdict table (methodology §9); the result schema; and the execution
budget. It uses the repository's existing one-shot machinery (lock ref, preserved raw-input artifact, exact-byte seal). A failure before the lock
spends nothing; a failure after it consumes the study.

Then exactly one execution. No parameter, feature, horizon, threshold or baseline changes after it starts. Families that failed readiness are
reported `BLOCKED`, not waited for. Anything run afterwards is labelled `EXPLORATORY_POST_OUTCOME` and can never rescue, reclassify or reopen the
registered result.

## Phase D — KR final development assessment (one PR)

One report, **KR Alpha Research — Final Development Assessment**, published in full, failures included. It answers:

- which features and families had positive directional development evidence, which had none, and which were wrong-signed;
- which were redundant with the simple baselines, and which added independent information;
- which depended on an industry, a regime or a liquidity tier;
- which survived the declared multiple-testing correction;
- which were economic after costs, and which were too illiquid or sparse to trade;
- which stayed unavailable for data reasons;
- which candidates, if any, are frozen for prospective tracking.

No CAGR is presented without its A-G decomposition, and no headline is the only conclusion.

## Phase E — prospective KR monitoring, then the US handoff

- Freeze any `INDEPENDENT_DEVELOPMENT_SUPPORT` candidate (zero is a valid number). Register its authorization in the receipts module, and only
  then write weekly receipts through the LIVE pathway, strictly after the merge's KST date.
- Monitoring is isolated: no model, feature or threshold experimentation touches a frozen candidate. A changed candidate is a new candidate with a
  new authorization and a new ledger.
- Evaluation of matured receipts follows a separately frozen prospective evaluation plan. No date is promised: an H126 receipt needs about six months
  to mature, and the evidence length is the plan's decision.
- The US program starts as soon as Phase D is merged. It does not wait for Korean receipts to mature.

## Termination conditions for Korean development research

The Korean historical program is CLOSED when either of these holds:

1. Phase D is merged; or
2. Phase C is formally `BLOCKED` because the Phase B readiness report leaves fewer than two families with any READY feature after its budget. Phase D
   is then written from the readiness report alone.

After closure: no new broad KR historical search, no Alpha Signal v3 or Tournament v2, and no re-running of a closed study because no candidate won.
New KR historical work is admissible only for a genuinely new information axis whose data did not exist at Phase C (for example investor flow if
KRX access opens), through its own preregistration. Even then, KR history remains outcome-exposed development evidence.

## US research handoff

Reused unchanged:

- the registry schema and validator (a `us-alpha-atlas-registry-v1.json` with US sources, filing lags and benchmarks);
- PIT rules (receipt or acceptance-time availability, never period end);
- the alpha decomposition (§2 of the methodology) with a US benchmark (SPY or a pre-declared alternative, never switched mid-study);
- the multiple-testing declarations and the verdict table;
- source-readiness gates, including the vendor-refusal invariants;
- the prospective receipt core (`pipeline/prospective_receipt_core.py`) and its LIVE/SYNTHETIC separation;
- the cost-aware investability checks, re-parameterised to the US cost schedule.

Region-specific, never inherited: microstructure, filing lags (10-Q/10-K versus DART), benchmark, costs, survivorship repair. The US delisted-member
history gap (212 of 324 departed identities without usable history; `alpha-opportunity-model-v3`) must be bounded before any US historical claim.

US must not repeat the closed 31-feature `regional-alpha-model-v1` matrix (`NO_MODEL_EVIDENCE`). Its distinct axes, subject to source feasibility:

| Axis | Note |
|---|---|
| Dividend-policy changes | `CommonStockDividendsPerShareDeclared` is already in the US PIT store |
| Profitability and accrual quality | `accounting_quality` fields exist for the US (97% OCF coverage) |
| Institutional ownership changes (13F) | SEC egress currently blocked; quarterly with a 45-day lag |
| Insider transactions (Form 4) | same SEC block |
| Short interest | source feasibility unverified |
| Microstructure and liquidity | from US OHLCV, as family D/E here |
| Earnings announcement effects | 8-K access blocked; filing dates from the PIT store |
| Macro-conditioned leadership | ALFRED vintage gaps limit history |
