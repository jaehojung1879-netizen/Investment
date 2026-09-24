# Alpha research philosophy v2

> **This is a philosophy/governance document. It changes no production
> behavior.** No `FACTOR_WEIGHTS`, CHAMPION, selector, Kelly parameter,
> entry rule, region cap, or macro multiplier is touched by this document.
> It fixes the *objective* future research is designed against; it does
> not itself run a study, select a feature, or promote anything.

## 0. Objective

The objective of this project is:

> Find candidate investments, available at this capital's actual scale,
> whose expected return meaningfully exceeds their own appropriate passive
> benchmark, after transaction costs — and size capital into them only
> when that expected advantage is large enough to be worth the concentration
> risk of holding it.

Every principle below is a consequence of that one sentence. None of them
is a performance claim; none of them is decided by looking at a result.

## 1. What is explicitly NOT required

- **A fixed number of holdings.** Five names is not a target. A dynamic
  count bounded only by whether a candidate clears the opportunity
  threshold (§2) is the design; `dynamic-breadth-v1` already tested one
  version of this (contains zero, per `AGENTS.md`) — that result does not
  retire the *principle*, only that specific rule's construction.
- **A minimum invested fraction.** If nothing clears the threshold, holding
  cash (or the region's own benchmark, undecided by this document) is a
  valid outcome, not a failure to find an idea.
- **A fixed regional quota.** Region is an important context — different
  information availability, different market structure, different cost
  schedule — but it is not a capital-allocation target set in advance.
  `region-quota-removal-v1` already measured what the ranking wants
  without a region cap (KR-concentrated, point estimate worse, interval
  containing zero) — that result quantifies a trade-off; it does not, by
  itself, mean regional exposure should be either capped or uncapped going
  forward. Whether region ends up looking capped, uncapped, or
  something else is an empirical question for a specific future study, not
  a philosophical commitment made here.
- **Treating US and KR as one model, or as two models forever.** Both are
  live options. `regional-alpha-research-separation-v1` split them because
  every factor tested at the time was region-sign-unstable; that was a
  response to a specific measurement, not a permanent architectural law.
  A future study is free to propose a single cross-region construction IF
  it can show the comparability prerequisite `region-quota-removal-v1`
  already named (a common cross-region scale) holds for whatever it
  proposes.
- **Institutional scalability.** See §3.
- **Ranking every candidate from best to worst.** The question this project
  answers is narrower: is there a MEANINGFUL, ACTIONABLE advantage over the
  benchmark, not a complete ordering of the universe. A ranking is a tool
  toward that question, not the deliverable itself.

## 2. The opportunity threshold

A candidate is investable only when its expected advantage over its own
appropriate passive benchmark is large enough, after costs, to be worth the
concentration and liquidity risk of holding it specifically — not "the
nearest thing that beats zero." The exact quantitative form of this
threshold (a hurdle rate, a confidence interval requirement, a Kelly-derived
floor) is a decision for whichever future study proposes it; this document
fixes only that such a threshold must exist and must be justified against
the cost of holding the position, not set to guarantee some number of names
get through. `switch-hurdle-v1`'s cost-derived hysteresis and
`dynamic-breadth-v1`'s SE-distinguishability walk are both existing
instruments that already implement one candidate SHAPE of such a
threshold — reusable, not necessarily final.

## 3. Small-capital edge

**Institutional scalability is not a requirement.** This capital does not
need the strategy to absorb billions of dollars without moving the market
it trades in, and that fact is a genuine source of edge, not a limitation
to apologize for. Specifically, this project may:

- Concentrate in a small number of names when conviction is unusually high.
- Consider small- and mid-liquidity opportunities a fund with a large
  mandate would have to pass on purely on capacity grounds.
- Go without a trade for an extended period when nothing clears the
  threshold.
- Accept tracking error against any benchmark — tracking error is a
  constraint institutions accept for mandate reasons this capital does not
  have.
- Research signals that are real but too small in aggregate market impact
  for an institution's mandate to bother with.

**This is not a license to buy illiquid names carelessly.** Every one of
the following stays in force regardless of capital size:

- Realistic transaction cost, modeled per-region from the same dated
  schedule `_turnover_cost` already charges the realised path
  (`switch-hurdle-v1`'s own discipline).
- Slippage and a position-capacity ceiling relative to the name's own
  liquidity.
- A liquidity floor below which a name is not considered regardless of its
  apparent expected return.
- Survivorship control — no backfilling today's universe onto the past.
- Full point-in-time discipline — nothing in this project trades on
  information it could not have had on the date in question.

## 4. Signal construction vs. portfolio construction

Two separable questions, kept separate:

1. **Stock-selection signal**: does this candidate have a meaningful
   expected advantage over its own benchmark? This is the domain of
   feature/information research (the data-foundation work this project's
   `alpha-research-foundation-v2` phase is building).
2. **Portfolio construction / risk management**: given a set of candidates
   that clear the threshold, how much capital goes to each, how much stays
   in cash, and how concentrated the book gets. This is a separate design
   layer and should not be silently re-decided by a change to the signal
   layer — `entry-selection-separation-v1` is the concrete cautionary
   example: production's entry-state multiplier decides BOTH who is held
   (signal-layer question) AND how fast a position is approached
   (construction-layer question) inside one score, and that conflation was
   exactly what that study tested separating.

## 5. Alpha decomposition

A future portfolio-level evaluation should be able to separate, not just
report, a headline number into:

1. **Stock selection alpha** — the arithmetic excess return from picking
   better names than the benchmark's own membership, per name held
   (`selection_value.decompose_edge`'s existing arithmetic/compounding
   split is the reusable instrument for this).
2. **Regional / asset-allocation alpha** — the excess return from how
   capital was split across regions or asset classes, isolated by
   comparing the actual portfolio against a passive reference mix with the
   SAME regional weights (§6).
3. **Cash / risk-timing contribution** — the return (positive or negative)
   contributed by periods spent uninvested or under-invested relative to a
   fully-invested benchmark.
4. **Costs** — transaction costs and any other realised drag, reported
   separately, never netted invisibly into one of the above.

No study is required to compute all four in this PR or in any single PR —
this section fixes the vocabulary and the requirement that they be
SEPARABLE when a future evaluation is built, not that they be built now.

## 6. Benchmark principle

Each stock's own alpha is measured against its own appropriate regional
benchmark (US equity against a US benchmark such as SPY or another
pre-defined US reference; KR equity against a KR benchmark such as KODEX
200 or another pre-defined KR reference) — this is already this
repository's existing practice and is restated here as a fixed principle,
not a new rule.

For a WHOLE-PORTFOLIO evaluation, the reference must be built with the same
regional weights the actual portfolio held, not a single global index: if
the book is 70% US / 30% KR on a given date, the passive reference for that
date is 70% US benchmark / 30% KR benchmark, not 100% of either. This is
what makes §5's decomposition possible — without a regional-weight-matched
reference, a US-region rally shows up looking like stock-selection skill
when it is actually a regional-allocation effect. No specific benchmark
symbol, blend methodology, or rebalancing cadence for this reference is
fixed here; that is an implementation decision for whichever study first
needs to compute it.

## 7. Horizon philosophy

Not every information source is evaluated on the same forward window.
Economically motivated horizon buckets (assigned by economic reasoning
about the information's own half-life, never chosen after looking at which
horizon "worked"):

| Information family | Expected horizon |
|---|---|
| Market attention / volume shock / event shock | 5–63 trading days |
| Investor flow (accumulation/distribution) | 21–63 trading days |
| Momentum / price leadership | 63–126 trading days |
| Estimate revision (where PIT-safe data exists) | 21–126 trading days |
| Fundamental quality / valuation / structural change | 126–252 trading days |

A future study PRE-REGISTERS which horizon(s) it will evaluate at, before
seeing any result, per this table's economic reasoning — never selects the
horizon that happens to look best after the fact. This mirrors the
discipline `alpha-information-inventory-v1`'s own time-axis buckets already
established; this document promotes that bucket table from an inventory
artifact to a standing research rule.

## 8. What this document does not decide

This document does not select a next hypothesis, does not grade a data
source, and does not compute or imply any expected return for anything. It
fixes the questions a future study must be able to answer about its own
design (what threshold, what horizon, what benchmark, which decomposition
terms) — it does not answer any of them itself. The actual next
hypotheses, with their own economic rationale and data readiness, are
tracked in `docs/alpha-information-inventory-v1-next-hypotheses.md` and
whatever documents supersede it.
