# Investment — Active Agent Charter

**Purpose.** This is a short, active instruction file for every human or AI contributor to this repository. It states the current decision hierarchy, scientific boundaries, and operational safeguards. **It is not the historical research ledger.** The exact prior full AGENTS.md (v2.55, original main blob d8a1a9020cceef45475cee2d58ad1349a304050e) is preserved without rewriting at:
docs/archive/research-invariants/AGENTS-v2.55-full-2026-11-08.md

That archive contains 59 historical research-specific invariant sections. Their original research outcomes, parameter choices, provenance and failures remain available there. When a particular historical study is relevant, consult its original frozen spec, result, audit and archive; do not copy its study-specific findings into new universal instructions or silently treat old observations as current evidence.

## 1. Mission and immutable investment policy

- Deliver **reproducible 6–12 month, risk-adjusted, net-of-cost economic advantage versus investable passive ETFs**. Engineering, charts, dashboards, PRs and tests are means, not the outcome.
- **Korea:** compare against 069500.KS (KODEX 200). Recommend **0–5 equities, not a fixed number**; only hold individually selected equities when supported by verified incremental economic evidence. No qualified names => region ETF 100%.
- **United States:** SPY baseline, QQQ supplementary; keep KR and US empirical decisions, returns and risk accounting separate.
- Maintain the research hierarchy **Market → Industry → Stock → Portfolio**. A new event-information axis is one possible source of edge, not a replacement for the ultimate objective.
- No live transactions or automatic trading authorization are implied by this charter. Never represent exploratory research, model rankings, or paper positions as verified investment advice or executed portfolio performance.

## 2. The anti-loop rule — enforce on every task

**Before starting any new Claude/Codex task, read the previous task's original promise, the latest owner decision, and the current exact Git evidence.** The next task must answer:
1. What was promised last time, with explicit completion criteria?
2. What actually changed? Give a measured **before → after** in eligible economic events, evidence quality, economic result, or necessary blocker status, referencing exact code and source hashes.
3. What did not change? Which hypotheses are CLOSED, BLOCKED or NOT_EXECUTED?
4. Is the proposed work the **smallest action that changes an economic decision**? Why is it not the last plan repeated under another name?

**Do not start another framework, harness, dashboard, CI cycle, research PR, or large prompt merely because the prior work produced code rather than the promised economic result.** When an execution harness already exists but zero input sources are admitted, prioritize admitting the necessary existing source data, repairing a concrete correctness defect, or making a STOP/PIVOT decision. Do not build a second harness.

One research cycle should end in a material scientific update: a source-admission improvement, an actual hypothesis result, a defensible rejection/uncertainty verdict, or a bounded SOURCE_BLOCKED/STOP decision. Failure to improve any of these must be reported as failure of the current cycle, not rebranded as successful research preparation.

**Every handoff, in this order:** prior promise → verified delta → economic meaning → remaining blockers and cost → KEEP / REJECT / INCONCLUSIVE / SOURCE_BLOCKED / STOP → **one smallest next action and named responsible agent**. Do not generate new plans until the prior plan is reconciled. Issue #292 is the active coordination record, not permission to restart terminated research.

## 3. Research contracts and scientific validity

- A hypothesis, sample, population, event definition, horizon, benchmark, fees, thresholds, multiplicity, confidence procedure, missingness rules, and stop criteria must be frozen **before** reading outcomes. Separate hypothesis-generation history from truly forward evidence.
- Use the **study's frozen registration, exact code/input digests, owner approvals and sealed result** as the source of truth. This charter never amends a frozen spec or overrides a registration, an exact-hash approval, a one-time-consumption lock, or a protected workflow.
- No unauthorized historical outcome / NAV / label run, no reseal, no re-run on a consumed sample, no threshold-chasing or post-hoc promotion. Require the specific study's exact-hash authorization and verified prerequisites; an existing paper/live authorization does not transfer to historical testing or production.
- Test *economic* usefulness, not just statistical significance: realistic and dated transaction taxes, spreads, turnover, dividends, investor account costs, cash funding, industry/market beta, risk, dependence, delistings and benchmark total return. Distinguish stock-selection alpha from market exposure, compounding, regime luck and costs.
- Results are one of **SOURCE_BLOCKED, NOT_EXECUTED, EXPLORATORY, INCONCLUSIVE, REJECTED, DEVELOPMENT_SUPPORT, PROSPECTIVE, INDEPENDENTLY_VERIFIED** as appropriate. State sample, denominator, uncertainty, source vintage and exact benchmark. Missing data are unknown, not zero. A confidence interval containing zero is not verified alpha.
- A negative or null finding is legitimate completed research. Honor the stop rule; do not optimize the same outcome-exposed history until it produces a positive headline. If a source blocker cannot be resolved within the specifically bounded task, disclose costs, likely impact and whether the research should be paused or abandoned.
- Keep control and treatment on a common valid population, capital basis, timeline, and return definition. Do not compare gross selection confidence intervals with net-of-cost thresholds without explaining the differing estimands.

## 4. Data correctness and evidence provenance

- **PIT is mandatory:** only issuer/security identifiers, universes, filings, account figures, corrections and securities available by the signal decision time. Date-only disclosures are **DATE_ONLY_CONSERVATIVE**, never **PIT_EXACT** without genuine publication-time proof. A currently served amended document is not the original historical document.
- Use actual shareholder **total returns**, including dividends and actions. Distinguish ex-date, record date, pay date and announcement date; fiscal cash DPS is not itself an ex-date event. Do not interpret absent vendor dividends, missing ETF distributions, missing bar dates or a terminated security as zero performance.
- Research with suspended, renamed, merged, converted, preferred/common, or delisted securities must preserve point-in-time identity, actual tradability and valid terminal consideration. Never impute a missing terminal price, backfill an unknown value, or let future observations leak into the permitted data cutoff.
- Maintain auditable source receipts, provenance, hashes, source rights and input validity. A stored file or byte-valid digest is **not** evidence of historical vintage, coverage completeness, investor execution, or legal right to use a data source.
- A statistic without a measurable basis is **None/UNKNOWN**; report measured numerator, denominator, selection universe and coverage. Never turn incomplete input into extreme market scores, a verified signal, or a default-zero result.
- Source collection and source use must respect data-provider terms and access rights. Explicitly identify REFUSED, BLOCKED, DEGRADED or unknown instead of inventing substitutes or silently broadening scope.

## 5. Execution, releases and safety boundaries

- Existing research registrations, hashes, result files, authorizations, consumed-locks, workflow inventories, paper ledgers, source snapshots and production files are **protected**. No merge to main, workflow dispatch, historical result execution, production writer activation, seal change, force-push or history rewrite without the appropriate separate owner decision.
- Blocked, stale or synthetic outputs contain **no actionable positions, weights or recommendations**. Never let seed/synthetic data pass production validation or deployment. No liveValidated or equivalent status until real ledger and validation requirements are satisfied.
- Ledger signals are **append-only**, keyed by date/region/security/model version; idempotence, freshness, no backdating and provenance are required. A registered prospective schedule or dry-run is not evidence of a successful first live receipt. A live outcome cannot be backfilled and called forward evidence.
- GitHub Actions / Pages success claims must refer to the specific job and exact commit; a green diagnostic with skipped deployment is not a production deployment. Protect the original signal-history and avoid expensive full-worktree checkout or unbounded workspace accumulation.
- Check and respect exact-head CI, Python/runtime pins, tests and formal artifact validation for the code in scope. Where feasible run ruff, compileall, the relevant tests, complete pytest, seed generation and artifact validation; report **what was actually run** and failures. Passing tests is engineering readiness, not an alpha result.
- Use isolated branches and reviewable PRs. **Never merge directly to main.** A review by the code author is not independent approval. Do not create redundant parallel PRs or duplicate existing modules.

## 6. Agents, priorities and source of truth

- One active owner per overlapping code path. Coordinate through **Issue #292** with a brief CLAIM before changes and HANDOFF with exact SHA, tests, evidence, blocker and next action. GitHub comments do not themselves launch an external Claude/Codex session.
- Prefer reusing current source parsers, economic kernels, comparison engines, PIT calendar/identity rules, audit routines, tests and registers over creating another near-duplicate implementation.
- **Priority ranking:** (1) correctness flaws that could mislead investment decisions; (2) specific empirical inputs needed by an already-frozen study; (3) actual preapproved economic evaluation and stop/continue decision; (4) prospective evidence integrity; (5) necessary production/CI repairs; (6) cosmetic or general infrastructure.
- Track KR and US ambitions separately. The current research status is **dynamic**: check GitHub main, open PR heads, research specs, true ledger receipts and Issue #292; do not copy old dates, percentages, N, CI or "ready" labels from this charter as current facts.
- Existing historical decisions, including archived C2/Phase C conclusions, remain binding unless a newly approved information axis and independent evidence justify a different study. **Never silently reopen or reinterpret previously exhausted historical tests.**
- The canonical hierarchy is: (a) explicit latest owner instructions and applicable immutable safety gates; (b) the exact frozen study contract and source evidence; (c) this active common charter; (d) relevant archived study-specific guidance; (e) Issue #292 dynamic status/handoffs. A summary or prior conversation is not a substitute for exact repository evidence.
- An ambiguous, unavailable or conflicting source must be reported, not guessed. A research blocker is not an instruction to spend indefinitely on more infrastructure.

## 7. Archive and scope of this cleanup

- Full original root instruction text: docs/archive/research-invariants/AGENTS-v2.55-full-2026-11-08.md (historical, read on demand).
- Current coordination and anti-loop rules: https://github.com/jaehojung1879-netizen/Investment/issues/292.
- Frozen research specifications and source audits in their existing original paths remain authoritative; consult them only for their respective studies.
- **This cleanup changes only contributor guidance and archives its former text.** It does not approve an experiment, change a numerical model, delete data, edit a seal, alter the original archived evidence or operate a production workflow.
