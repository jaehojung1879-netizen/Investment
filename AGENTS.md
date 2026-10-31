# Investment repository — active agent contract

**This is a compact entrypoint, not a repeal.** The former 3,241-line
`AGENTS.md` is preserved **byte-for-byte** at
[docs/invariants/archive/AGENTS-full-20261031.md](docs/invariants/archive/AGENTS-full-20261031.md).
Read applicable archived versioned rules and the registered research spec before
modifying that study. Where instructions differ, keep the stricter seal and
safety guardrails; do not reinterpret existing frozen contracts.

## Goal and decision authority
- **Research goal:** 6–12 month risk-adjusted NET alpha across market, industry,
  stock and Portfolio D; preserve hypothesis failures and ETF fallback.
- **Operating decision:** `signal-history:ledger/weekly-decisions/latest.json`
  and dated final receipts; KR `069500.KS`, US `SPY` (QQQ secondary).
  KR holds 0–5 admitted stocks only when defensible evidence exists.
- **Research only:** legacy Kelly `state/latest.json` holdings/weights, alpha
  screens, C1/C0 fixtures, paper challengers and experimental models.
  They are NOT separate live or approved investment recommendations.
  See [roles and data contract](docs/portfolio-d-evidence-boundary.md).

## Scientific invariants — preserve in every PR
- Unknown/unmeasured/missing is `None`, not zero, false or a positive signal;
  every ratio carries denominator, market and dated sample/support.
- No hindsight: validate point-in-time publication/vintage/lag, exchange
  calendar, decision finality and next-session execution; fail closed on gaps.
- Never use survivorship-biased or unverified total-return/corporate-action
  data as evidence of investable alpha. Verify vendor rights and retention.
- Freeze hypotheses, comparators, horizons, fees, first look, economic margins,
  uncertainty and multiplicity protocol **before** inspecting outcomes.
  Historical outcome-exposed research is exploratory, not prospective OOS.
- Do not edit or rerun sealed results, raw-data hashes, study protocols,
  protected workflows, historic ledgers or prior conclusions without explicit
  approved scope. C0 is the primary Market C comparator; C1 auxiliary.
- Compare like with like: common price/state/cash calendar, funded entry and
  terminal liquidation, 1x/2x/3x costs, same benchmark and execution convention.
  Report return, MDD, CVaR and mean exposure. Ex-post exposure-matched static
  paths are diagnostic, **not** causal timing alpha or tradable forecasts.
- Passive ETF default remains when evidence is lacking. No backtest/CI
  success, paper PASS or synthetic sign can authorize actual orders,
  model promotion or portfolio allocation.

## Engineering and review controls
- No direct push to main. Make smallest scoped change in an existing PR lane
  when applicable; do not create duplicate studies, workflows or version copies.
- Observe source SHA leases and existing owners/agents before edits.
- Before a code-readiness claim: `ruff check .`, relevant focused pytest,
  exact-HEAD GitHub Actions (full suite and import gate), seeded/artifact
  validation when applicable. A cancelled/pending CI is not a PASS.
- Blocked/synthetic/stale data never passes production validation.
  Research receipts are append-only with date, region and model identity.
- The original detailed invariants remain binding. Read corresponding archive
  sections, not all 258KB by default, and record the tests enforcing your scope.
- Report 5 items: change; actual decision impact; risks; test/CI SHA evidence;
  remaining blocker and next action. Never invent source, measured alpha or
  a successful cloud-agent dispatch.
