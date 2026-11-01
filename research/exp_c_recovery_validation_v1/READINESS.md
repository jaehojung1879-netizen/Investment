# Pre-outcome admissibility correction

Real evaluated rows KR/US: 0/0; tests of historical forecast skill: 0; source prices/states/returns/labels parsed: 0. Status remains **EXECUTION_BLOCKED / SOURCE_BLOCKED**, not a negative forecast finding. Owner reports Sonnet's audit of `4c2a4ba2cd9ecb9dddf4b7a00133d3e24f2b31fd` as leakage/fairness PASS with execution blockers. That report is not an APPROVED GitHub review or authorization, and does not automatically audit this revision.

## KR bound, exactly what is counted

`readiness.py` imports only the original hash-verified calendar and the existing pure support functions. It reads no market source. With XKRX 4.11.1, lunar-calendar 0.4.0, original 1990-01-03 grid origin, three existing 2026 closure corrections and end 2026-09-17:

- 9,033 calendar sessions; 1,027 weekly decisions from 2007-01-01; 1,014 decisions with calendar-mature H63 endpoints.
- Optimistically all covariates/paths are complete and every decision is stressed. The first possible test is 2010-06-18; last is 2026-06-12. Fixed bins floor(grid position/126) run from 39 through 71 inclusive: **33 occupied bins maximum**, not 32. These are support bins, not independent crisis episodes.
- Code greedily counts training windows when next execution > previous end; requires 12 such windows, and every train end +63 < test decision. Label end = decision+64. Thus the continuous-session lower bound on the earliest test is first decision +11×64+128 = first decision+832; actual week ends delay this. The script applies actual weekly positions and the strict inequality, not a year-length approximation.
- Monotonicity: deleting eligible/stressed rows cannot bring a support-qualified test earlier or create a new occupied bin. Therefore the all-complete/all-stressed panel proves an upper bound.
- **All weeks stressed is sufficient, not necessary.** Keep just the first 12 greedy training rows and the first eligible test in each of the 33 bins: 45 hypothetical stressed rows already give 33 supported test bins. This is a constructive counterexample to the audit's all-weeks requirement, not measured KR state history. For the 32 threshold at least 32 reachable bins must each contain a complete stressed decision with its own 12-window past support; at most one of the 33 theoretical bins can be lost, but this condition alone does not guarantee training support. Full code condition is necessary and sufficient.

Reproduce: `python research/exp_c_recovery_validation_v1/readiness.py`. No lock or data token required for this calendar-only calculation. Local calculation used Python 3.12 with pinned calendar libraries; this is not the Python 3.11 execution runtime. Synthetic regression covers the bound and sparse counterexample; exact calendar tests run when dependencies are installed.

## Input-only scan is a separate permission

`run.py --prepare [--us-source-root PATH]` verifies the freeze, checks pinned runtime and optionally hashes existing sources; no parsing, model, forward-path inspection, GitHub mutation or study lock. Missing sources remain SOURCE_BLOCKED. A hash match proves identity, not rights or admissibility. Full source/runtime checks also remain before the execution lock.

An actual cohort/support scan is **not authorized by this revision**. Even without label arithmetic, original `prepare_sources/common_rows` reads whole price paths, calculates trailing returns/volatility and inspects future path validity. It cannot be repurposed as an outcome-free scan. A narrow Owner C.7/stop-list exception and exact code/source hash authorization would need to specify: date/presence metadata only for future maturity; precomputed authenticated as-of state/feature-definedness flags or permission for blinded input derivation; no exposure of price levels, return/volatility values, forward losses or scores; minimal counts/IDs and missingness receipt; independent attestation and immutable access log; no retries or threshold changes. Presence-only future eligibility gives an **upper bound** until actual path validity is established. A materialized flag bundle needs provenance, as-of/hold semantics, source hashes and approval before use. No new unverified flag file is accepted here. This scan is technically feasible in a segregated authorized runner; current sandbox lacks the original US bundle, complete checkout and pinned execution runtime. Neither an actual input scan nor historical first look was performed.

## Keep 32; do not reinterpret planning power

32 remains unchanged. ceil(((1.959964+0.841621)/0.5)^2)=32 is a standardized independent-block planning approximation. With 33 the analogous standardized MDE is about 0.488; with 32 about 0.495. Two-bin bootstrap dependence, sparse occupancy and only 33 maximum bins mean these are not guaranteed effective sample sizes or calibrated 80% power. The actual fixed absolute MDE gate remains 0.0005 squared-return units with bootstrap SE. No MDE in return percentage points or observed power is inferred without losses. No threshold reduction is proposed or applied; any future change must freeze a new pre-outcome justification/calibration, disclose old/new effective dependence and MDE assumptions, and narrow the claim to exploratory precision if adequate power cannot be justified. Calendar feasibility is not a GO decision.

## US source contract: computational versus evidentiary necessity

The model numerically consumes `YAHOO_GSPC/normalized.csv`. `audit.json` and `raw_chart.json` are not covariates; they bind source identity, normalization provenance and the original freeze. **All three exact hashes remain mandatory under the current source gate and Owner contract**, even though only one is arithmetically necessary. Inability to recover any original file means SOURCE_BLOCKED. A future authenticated custody/lineage attestation policy could be considered by Owner, but is not implemented or treated as equivalent; no fresh download, changed provider/index, ETF splice or hash relaxation is allowed here. Existing sources were not acquired.

## Same-account independent audit: unresolved Owner policy

The current non-author-login APPROVED gate remains fail-closed. GitHub cannot approve one's own PR; a separate model using the same login does not satisfy it. Options, requiring explicit Owner choice before code/gate changes:

1. Retain gate: a genuinely separate reviewer identity submits an actual exact-head APPROVED review after independent audit. No account/identity is fabricated.
2. Owner accepts content-based independence: separately authored audit artifact with reviewer/model provenance, exact code/source/freeze hashes, audit text digest and explicit unresolved findings, followed by authenticated Owner acceptance and a separately scoped execution authorization. This changes the trust boundary from platform identity to Owner-attested provenance; it needs a reviewed new gate implementation and audit. It is not achieved by copying an approval string or using the old-head audit.
3. Keep execution blocked if neither provenance policy is acceptable.

Owner must still decide the narrow historical exception, whether to authorize a segregated input-only scan, source custody/rights and the independent-audit identity policy. No execution authorization, review, lock consumption, historical run or main merge is implied.
