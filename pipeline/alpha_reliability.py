"""Separate what the signal SAYS from how much of it is worth acting on.

WHERE THIS CAME FROM
--------------------
Three studies on this ledger keep pointing at the same place and none of them
has looked at it directly. `selection_value` split the calibrated challenger's
+0.340pp/yr headline into +0.040pp of arithmetic stock selection and +0.300pp
of compounding, and measured that 92-93% of turnover is names being REPLACED
rather than weights retargeted. `regional-switch-hurdle-v1` was built to save
the fees those replacements cost, saved 0.270pp of cost drag — and gained
2.157pp of arithmetic stock selection, eight times more, which no cost argument
predicts. `signal-persistence-v1` then asked whether the ranking's newest
opinions are its worst ones: ADDED names realised -0.357% per block against
+0.980% for RETAINED, a paired -1.331% with a 95% interval of [-3.029, +0.174]
that CONTAINS zero, and averaging the percentile over the span it forecasts
moved net excess from -0.684pp to +2.289pp with every rung's interval spanning
zero.

Every one of those is the same claim wearing a different coat: THE CONVERSION
FROM A CONTINUOUS SIGNAL TO A DISCRETE FIVE-NAME BOOK IS LOSING MORE THAN THE
SIGNAL IS WORTH. This module studies that conversion. It adds no factor, moves
no factor weight, and sweeps no window.

WHAT THE INPUTS ACTUALLY LOOK LIKE, MEASURED BEFORE THE LADDER WAS SPECIFIED
---------------------------------------------------------------------------
`axis_diagnostics` reports these on the sealed pool and they are the reason the
design below is shaped the way it is. Two of them refuted a rung this module
was going to have:

* THE POOL LIVES IN TWO CALIBRATION BUCKETS. Its alpha percentiles run 91 to
  100 (mean 97.4, sd 2.33), and the bucket edges are (0, 60, 80, 90, 95, 100),
  so 83.5% of pool name-dates sit in 95-100 and the rest in 90-95. Names inside
  one bucket are handed the SAME expected excess, so for five names in six the
  ranking's alpha term is a constant and the ordering is decided by realised
  downside volatility alone. The premise that "74 versus 73 flips a holding" is
  not what happens here; what happens is that 97 versus 98 is not a difference
  the ranking can even represent.
* SHRINKING THE PERCENTILE TOWARD A NEUTRAL PERCENTILE CANNOT BE THE CHANNEL.
  Shrink toward the pool mean and a weak name at 93 moves UP into the top
  bucket — confidence would be raising an alpha claim, which is the one thing
  it must never do. Shrink toward 50 and every name lands in 60-80 together,
  which deletes the signal rather than refining it. The bucket map is too coarse
  a transmission line, so confidence is applied in ALPHA space instead, where
  the neutral point is a genuine neutral: zero benchmark excess.
* EVIDENCE COVERAGE IS ALREADY INSIDE THE LEVEL AND IS NOT AVAILABLE AS
  CONFIDENCE. `longterm` computes `alpha = rawAlpha x evidenceCoverage` before
  the percentile is taken, so `evidenceCoverage` and `factorCoverage` have
  already shrunk the number this module is handed. Using either again would
  charge the same doubt twice and would look like a new instrument while being
  a second helping of an old one. Both are excluded, and the diagnostic that
  shows why is published beside the ladder.

THE THREE LAYERS
----------------
LEVEL — what the four-factor structure says about this name now. Unchanged:
    the production `alphaPercentile`, the production 0.30/0.25/0.25/0.20 sleeve
    weights, and the production expanding bucket calibration that turns a
    percentile into an expected benchmark excess.

PERSISTENCE — is this a standing opinion or a fluctuation? Reused wholesale
    from `signal_persistence.PercentileSmoother` at k = 6, which is the
    forecast horizon in blocks (126 sessions / 21). Not re-searched here: this
    module imports that class rather than owning a second copy of the window,
    and no new k is introduced.

CONFIDENCE — how much of the level is worth acting on? Two factors, each in
    (0, 1], each fixed before any path was run, each built from information the
    level does NOT already contain:

      r_history = n.tau^2 / (n.tau^2 + sigma^2)
          the reliability ratio of a group mean under one-way partial pooling.
          `sigma` is the name's own backward percentile dispersion over the same
          k = 6 window the persistence layer averages, `n` its depth, and `tau`
          the cross-sectional dispersion of the smoothed percentiles among that
          region's pool names on that date. It asks whether this name's position
          in the cross-section is bigger than its own wobble. Every term is
          observable at the rebalance and nothing is fitted.

      r_agreement = 1 - sd(factor percentiles) / 50
          the four sleeves are the same four the level blends, but their SPREAD
          is thrown away when they are averaged. A name at the 97th percentile
          built from 99/98/95/96 and one built from 99/40/99/40 make the same
          claim on very different evidence. 50 is the arithmetic maximum sd of
          values bounded in [0, 100], not a fitted scale — the observed maximum
          is 49.5, which is the bound being real rather than chosen.

    confidence = r_history x r_agreement, and the level is contracted toward
    zero benchmark excess by it:

        reliable_alpha = confidence x alpha

    THIS IS A CONTRACTION, NEVER AN AMPLIFIER. |reliable_alpha| <= |alpha| and
    the sign is preserved, so confidence can only ever reduce what a name is
    credited with. It is not a factor, it earns no name a place it had not
    already earned on the level, and `contraction_holds` is asserted on every
    row of every block rather than argued for in prose.

THE LADDER — ONE AXIS PER RUNG
------------------------------
    CONTROL              latest raw percentile, confidence off, no hysteresis.
                         This is `signal_persistence`'s LATEST rung and
                         `switch_hurdle`'s CONTROL rung running the same loop,
                         so all three studies share one baseline and the gap
                         between that baseline and the published challenger
                         path (-0.684pp against -1.046pp) is a harness
                         difference that is published, not absorbed.
    PERSISTENCE          + the k = 6 backward smoother. Nothing else.
    PERSISTENCE_CONF     + the confidence contraction. Nothing else.
    PERSISTENCE_CONF_HYST + the incumbent/challenger uncertainty comparison.

THE HYSTERESIS, AND WHY IT IS NOT THE SWITCH HURDLE
---------------------------------------------------
`regional-switch-hurdle-v1` credits an incumbent the FRICTION its staying
avoids. That is a claim about the tax code. This credits an incumbent the part
of its own alpha that confidence discarded, which is a claim about the SIGNAL:

    incumbent  decision alpha = reliable_alpha + (1 - confidence).|alpha|
    challenger decision alpha = reliable_alpha - (1 - confidence).|alpha|

For a positive alpha that is exactly "judge the name you hold on the most
favourable reading of its own signal and the name you would buy on the least
favourable reading of its own" — a swap happens only when the two readings do
not overlap. Two names in the same calibration bucket carry the SAME alpha, so
under this rule they can never displace one another; under the control they do,
on nothing but a downside-volatility ordering. No transaction cost enters any
rung of this ladder. The two hypotheses are tested separately and their
combination is reported outside the ladder, because a number produced by moving
two axes is attributable to neither.

WHAT THIS IS NOT. Not a promotion, not a production change, not a claim that
any rung beats the benchmark going forward, and not a permutation null — no
rung here is tested against a permuted ranking, so nothing in this module may
be described as beating random. `k = 6` and the 1.0 multiple on the uncertainty
margin are inherited from studies that fixed them a priori; no new parameter is
introduced and no rung is a tuned variant.

A KNOWN LIMITATION, STATED BEFORE THE RESULT. The functional form guarantees
confidence cannot amplify an alpha claim. It does not guarantee that
`r_agreement` carries no return information of its own — cross-sleeve agreement
could be a weak factor rather than a reliability weight, and one historical
sample cannot separate those. What can be said is what the form enforces; what
cannot is left unclaimed.
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np

from . import benchmark_alpha as BA
from . import kelly_portfolio as KP
from . import portfolio_validation as PV
from . import signal_persistence as SP
from . import switch_hurdle as SH

VERSION = "alpha-reliability-v1"

CONTROL = "LATEST_ALPHA_NO_CONFIDENCE_NO_HYSTERESIS"
PERSISTENCE = "PERSISTENT_ALPHA_ONLY"
PERSISTENCE_CONFIDENCE = "PERSISTENT_ALPHA_X_SIGNAL_CONFIDENCE"
PERSISTENCE_CONFIDENCE_HYSTERESIS = "PERSISTENT_ALPHA_X_CONFIDENCE_PLUS_SIGNAL_HYSTERESIS"
LADDER = (CONTROL, PERSISTENCE, PERSISTENCE_CONFIDENCE,
          PERSISTENCE_CONFIDENCE_HYSTERESIS)

# Reported beside the ladder, never inside it: it adds the transaction-cost
# hurdle, which is a second axis and a different hypothesis.
STACKED = "PERSISTENT_ALPHA_X_CONFIDENCE_PLUS_SIGNAL_HYSTERESIS_PLUS_COST_HURDLE"

# Inherited from `signal_persistence`, which fixed it from the forecast horizon
# (126 sessions / 21 per block). This module does not re-open the window.
WINDOW_BLOCKS = SP.HORIZON_BLOCKS

# The arithmetic maximum sample dispersion of values bounded in [0, 100]: half
# at each end. It is the scale the quantity cannot exceed, not a fitted one.
MAX_PERCENTILE_DISPERSION = 50.0

# The full uncertainty margin, once on each side of the comparison. One unit of
# "the gap must clear the doubt", the same a-priori multiple `switch_hurdle`
# fixed for its own margin, and never swept.
UNCERTAINTY_MULTIPLE = 1.0

# Confidence is a product of these and of nothing else. Named here so the report
# and the tests read the same list the scorer does.
CONFIDENCE_COMPONENTS = ("historyReliability", "sleeveAgreement")

# Excluded from confidence because `longterm` already multiplies raw alpha by
# `evidenceCoverage` before the percentile is taken, so the level this module is
# handed has been shrunk by them once already.
CONFIDENCE_EXCLUSIONS = {
    "evidenceCoverage": "ALREADY_MULTIPLIED_INTO_ALPHA_BEFORE_THE_PERCENTILE",
    "factorCoverage": "COMPONENT_OF_EVIDENCE_COVERAGE_ALREADY_IN_THE_LEVEL",
}


def sleeve_agreement(factor_percentiles: dict | None):
    """How far the four sleeves are from saying the same thing, as a weight.

    The level blends the sleeves and throws their spread away. Two names can
    reach the same blended percentile from sleeves that agree and from sleeves
    that contradict each other, and only the second is a number whose evidence
    is internally inconsistent. Returns `None` below two present sleeves: one
    sleeve has no agreement to measure, and answering 1.0 there would hand the
    thinnest evidence in the cross-section the strongest reading on the scale.
    """
    values = [PV._finite(value) for value in (factor_percentiles or {}).values()]
    values = [value for value in values if value is not None]
    if len(values) < 2:
        return None
    spread = float(np.std(values, ddof=0))
    return float(np.clip(1.0 - spread / MAX_PERCENTILE_DISPERSION, 0.0, 1.0))


def history_reliability(own_sd, depth: int, cross_sd):
    """`n.tau^2 / (n.tau^2 + sigma^2)`: is the position bigger than the wobble?

    The reliability of a group mean under one-way partial pooling, with `sigma`
    the name's own backward dispersion, `n` how many blocks it is averaged over
    and `tau` the cross-sectional dispersion of the same quantity among the
    names it is being ranked against. Everything is observable at the rebalance.

    `None` where either dispersion could not be measured — a name with one
    observation has no wobble to compare against, and a cross-section with one
    name has no spread. Neither absence is 1.0.
    """
    if own_sd is None or cross_sd is None or depth < 1:
        return None
    between = float(cross_sd) ** 2 * max(int(depth), 1)
    within = float(own_sd) ** 2
    total = between + within
    if total <= 0:
        # A cross-section that does not move and a name that does not move are
        # the same reading twice; there is no ratio between two zeroes.
        return None
    return float(between / total)


class ReliabilityState:
    """Carries the backward window and the pooled dispersion prior across blocks.

    The window itself is `signal_persistence.PercentileSmoother` — this module
    does not own a second definition of "a name's own last k appearances". What
    it adds is the pooled within-name dispersion observed SO FAR, which is what
    a name too new to have its own dispersion is given. That is the standard
    partial-pooling degradation and it is backward-only: the pool median is
    recomputed from what has been seen before the block being scored, never from
    the whole history.
    """

    def __init__(self, window: int = WINDOW_BLOCKS):
        self.smoother = SP.PercentileSmoother(window)
        self._observed_sd: list[float] = []

    def observe_block(self, candidates: list[dict], date: str) -> None:
        for candidate in candidates:
            self.smoother.observe(candidate["ticker"], candidate.get("alphaPercentile"), date)

    def pooled_sd(self):
        """Median within-name dispersion seen so far, or `None` before any."""
        if not self._observed_sd:
            return None
        return float(np.median(self._observed_sd))

    def record_dispersions(self, tickers) -> None:
        for ticker in tickers:
            value = self.smoother.dispersion(ticker)
            if value is not None:
                self._observed_sd.append(value)


def confidence_rows(candidates: list[dict], state: ReliabilityState, date: str, *,
                    persistence: bool, confidence: bool) -> list[dict]:
    """Per-name level, persistence and confidence, with the absences named.

    Returns COPIES. The contexts are shared across every rung, so a rung that
    edited a candidate in place would contaminate every rung after it — the
    defect `signal_persistence` already has a test for.

    `persistence=False` reproduces the production percentile exactly, and
    `confidence=False` sets confidence to 1.0 and the margin to 0.0, which is
    the ABSENCE of the component rather than a fitted neutral value for it.
    """
    state.observe_block(candidates, date)
    smoother = state.smoother
    pooled = state.pooled_sd()

    smoothed_by_ticker = {}
    for candidate in candidates:
        ticker = candidate["ticker"]
        raw = PV._finite(candidate.get("alphaPercentile"))
        smoothed_by_ticker[ticker] = (
            smoother.smoothed(ticker, raw) if persistence else raw)

    # `tau` is measured among the names this name is actually ranked against:
    # the percentile is a within-region rank, so pooling the regions would
    # compare a Korean name's position to an American cross-section.
    by_region: dict[str, list[float]] = defaultdict(list)
    for candidate in candidates:
        value = smoothed_by_ticker.get(candidate["ticker"])
        if value is not None:
            by_region[candidate.get("region") or "UNKNOWN"].append(float(value))
    cross_sd = {region: (float(np.std(values, ddof=1)) if len(values) > 1 else None)
                for region, values in by_region.items()}

    rows = []
    for candidate in candidates:
        ticker = candidate["ticker"]
        region = candidate.get("region") or "UNKNOWN"
        depth = smoother.depth(ticker)
        own_sd = smoother.dispersion(ticker)
        own_sd_measured = own_sd is not None
        if own_sd is None:
            own_sd = pooled
        agreement = sleeve_agreement(candidate.get("factorPercentiles"))
        reliability = history_reliability(own_sd, depth, cross_sd.get(region))

        components = {"historyReliability": reliability, "sleeveAgreement": agreement}
        measured = [value for value in components.values() if value is not None]
        if not confidence:
            value, unmeasured = 1.0, []
        elif not measured:
            # Nothing behind the weight. The name abstains from the rung rather
            # than being handed the most favourable reading on the scale.
            value, unmeasured = None, list(CONFIDENCE_COMPONENTS)
        else:
            value = float(np.prod(measured))
            unmeasured = [key for key, blob in components.items() if blob is None]

        copied = dict(candidate)
        copied["rawAlphaPercentile"] = candidate.get("alphaPercentile")
        copied["alphaPercentile"] = smoothed_by_ticker.get(ticker)
        copied["signalConfidence"] = value
        copied["confidenceComponents"] = components
        copied["confidenceUnmeasuredComponents"] = unmeasured
        copied["ownPercentileSd"] = own_sd
        copied["ownPercentileSdMeasured"] = own_sd_measured
        copied["crossSectionPercentileSd"] = cross_sd.get(region)
        copied["smoothingDepth"] = depth
        rows.append(copied)

    # Dispersions are banked only AFTER the block has been scored, so the pooled
    # prior a new name receives is built from blocks that came before it.
    state.record_dispersions([c["ticker"] for c in candidates])
    return rows


def reliability_scores(rows: list[dict], calibration: PV.ExpandingBucketCalibration,
                       cfg_pf: dict, *, as_of: str, incumbents: set[str] | None = None,
                       hysteresis: bool = False, cost_hurdle: bool = False) -> list[dict]:
    """Score on the contracted alpha, optionally with the uncertainty comparison.

    The scoring SHAPE is production's: expected benchmark excess per unit of
    realised downside risk, times the entry-state multiplier. What changes is
    which expected excess is handed in.

    ELIGIBILITY IS NOT THE RULE, exactly as in `switch_hurdle`. A name with no
    matured calibration, no downside-risk unit or a blocking entry state is
    excluded on a fact about the name; no confidence weight and no incumbency
    credit can rescue it.
    """
    incumbents = incumbents or set()
    out = []
    for row in rows:
        ticker, region = row["ticker"], row.get("region") or "UNKNOWN"
        estimate = calibration.expected(region, row.get("alphaPercentile"))
        alpha = (estimate or {}).get("expectedExcessReturnPct")
        risk = KP._risk_unit(row)
        state = KP._state_multiplier(row, cfg_pf)
        confidence = row.get("signalConfidence")
        incumbent = ticker in incumbents

        excluded = []
        if estimate is None:
            excluded.append("MATURED_CALIBRATION_NOT_READY")
        if risk is None or risk <= 0:
            excluded.append("DOWNSIDE_RISK_UNAVAILABLE")
        if state <= 0:
            excluded.append("ENTRY_OR_RESEARCH_STATE_BLOCKS_SIZING")
        if confidence is None:
            excluded.append("SIGNAL_CONFIDENCE_UNMEASURABLE")

        if alpha is None or confidence is None:
            reliable = margin = None
        else:
            reliable = float(confidence) * float(alpha)
            # Exactly what the contraction discarded, so the margin and the
            # shrinkage are the same quantity read twice rather than two
            # separately chosen numbers.
            margin = UNCERTAINTY_MULTIPLE * (1.0 - float(confidence)) * abs(float(alpha))

        decision = reliable
        if decision is not None and hysteresis:
            decision = decision + margin if incumbent else decision - margin
        if decision is not None and cost_hurdle:
            buy, sell = SH.leg_costs(region, as_of, cfg_pf)
            decision = decision + sell if incumbent else decision - buy

        score = (decision / (risk * 100) * state
                 if decision is not None and risk and risk > 0 else -1e12)
        out.append({
            "ticker": ticker, "region": region,
            "sector": row.get("sector") or "Unclassified",
            "score": score, "convictionScore": score,
            "alphaPercentile": row.get("alphaPercentile"),
            "rawAlphaPercentile": row.get("rawAlphaPercentile"),
            "downsideVolPct": risk * 100 if risk else None,
            "evidenceCoverage": row.get("evidenceCoverage"),
            "expectedGrossBenchmarkExcessPct": alpha,
            "reliableAlphaPct": reliable,
            "signalConfidence": confidence,
            "confidenceComponents": row.get("confidenceComponents"),
            "uncertaintyMarginPct": margin,
            "calibrationBucket": (estimate or {}).get("bucket"),
            "smoothingDepth": row.get("smoothingDepth"),
            "incumbent": incumbent,
            "decisionAlphaPct": decision,
            # Carried for the structural diagnostics only. Nothing below reads
            # them, so a rung's ordering is exactly what it was without them.
            "factorPercentiles": dict(row.get("factorPercentiles") or {}),
            "entryState": ((row.get("entry") or {}).get("entryState")
                           or row.get("entryState")),
            "entryStateMultiplier": state,
            "eligible": not excluded, "exclusionCodes": excluded,
            # THE SAME LIST, IMMUTABLY. `select_portfolio_by_scores` shallow
            # copies each row, so `item["exclusionCodes"]` IS this list object
            # and `_select_scored` appends its cut codes straight into it. The
            # rows a caller keeps therefore come back carrying
            # BELOW_TARGET_COUNT_CUTOFF and the cap codes mixed in with the
            # facts that made the name ineligible in the first place, and
            # nothing in the output says which is which. A tuple cannot be
            # appended to, so this is the copy the diagnostics read.
            "eligibilityCodes": tuple(excluded),
            "calibration": estimate,
        })
    return out


def contraction_holds(scored: list[dict]) -> bool:
    """Confidence contracted every row toward zero and amplified none of them.

    The design's one hard guarantee, checked on the rows themselves on every
    block rather than argued for in the module docstring. A confidence weight
    that could raise an alpha claim would be a factor wearing a reliability
    label, which is the failure mode this rung exists to avoid.
    """
    for row in scored:
        alpha = row.get("expectedGrossBenchmarkExcessPct")
        reliable = row.get("reliableAlphaPct")
        if alpha is None or reliable is None:
            continue
        if abs(reliable) > abs(float(alpha)) + 1e-12:
            return False
        if float(alpha) * reliable < 0:
            return False
    return True


def run_rung(rung: str, *, contexts: dict, calibrator, calendar: list[dict],
             cfg_pf: dict, valuation) -> dict:
    """Value one rung on the fixed blocks, carrying incumbency and the window."""
    if rung not in LADDER and rung != STACKED:
        raise ValueError(f"unknown rung: {rung}")
    persistence = rung != CONTROL
    confidence = rung in (PERSISTENCE_CONFIDENCE, PERSISTENCE_CONFIDENCE_HYSTERESIS,
                          STACKED)
    hysteresis = rung in (PERSISTENCE_CONFIDENCE_HYSTERESIS, STACKED)
    cost_hurdle = rung == STACKED

    state = ReliabilityState(WINDOW_BLOCKS)
    research_cfg = BA.cost_config(cfg_pf)
    rows, decisions, failures = [], [], []
    terminal_weights: dict[str, float] = {}

    for block in calendar:
        signal_date = block["signalDate"]
        calibrator.advance(signal_date)
        raw_candidates, macro = contexts.get(signal_date) or ([], {})
        candidates = confidence_rows(raw_candidates, state, block["date"],
                                     persistence=persistence, confidence=confidence)
        incumbents = set(terminal_weights)
        scored = reliability_scores(candidates, calibrator, research_cfg,
                                    as_of=block["date"], incumbents=incumbents,
                                    hysteresis=hysteresis, cost_hurdle=cost_hurdle)
        if not contraction_holds(scored):
            raise ValueError(f"CONFIDENCE_AMPLIFIED_AN_ALPHA_CLAIM at {block['date']}")
        allocation = KP.selection_and_baseline(
            candidates, research_cfg, macro, scored=scored, method=rung)
        weights = allocation["weights"]
        selected = {c["ticker"]: c for c in allocation["selected"]}
        held = set(weights)
        # `select_portfolio_by_scores` sorts and annotates a COPY and publishes
        # only the selected names plus eight near misses, so the reason a name
        # did not make the cut is missing for everything below that window. The
        # structural diagnostics need it for the WHOLE cross-section — "ranked
        # below the fifth name", "blocked by a sector cap" and "blocked by a
        # region cap" are different facts and only the first is the ranking
        # making a choice. `annotate_selection` re-runs PRODUCTION's own
        # `_select_scored` on copies to recover all of them, and asserts it
        # reproduces the set this block actually held.
        cut_reasons, chosen = annotate_selection(candidates, scored, research_cfg,
                                                 method=rung)
        if not held <= chosen:
            raise ValueError(f"SELECTION_ANNOTATION_DISAGREES_WITH_PATH at {block['date']}")
        for row in scored:
            row["selectionExclusionCodes"] = cut_reasons.get(row["ticker"])
        decision = {
            "date": block["date"], "replayDate": signal_date, "selector": rung,
            "weights": weights,
            "regionByTicker": {t: selected[t].get("region") for t in weights},
            "cashPct": (1 - sum(weights.values())) * 100,
            "rebalanceDecision": True, "selectedTickers": list(weights),
        }
        outcome, diagnostic = valuation.window(decision, block)
        decisions.append({
            "date": block["date"], "signalDate": signal_date,
            "heldNames": len(weights),
            "retained": sorted(held & incumbents),
            "added": sorted(held - incumbents),
            "replaced": sorted(incumbents - held),
            "regionByTicker": {t: selected[t].get("region") for t in weights},
            "retainedByRegion": SH._count_by_region(held & incumbents, scored),
            "replacedByRegion": SH._count_by_region(incumbents - held, scored),
            "scored": scored,
            "valuationStatus": diagnostic["status"],
        })
        if outcome is None:
            failures.append({**block, **diagnostic})
            continue
        rows.append(outcome)
        terminal_weights = dict(outcome.get("terminalWeights") or {})
    expected = [b for b in calendar if b["endDate"] <= valuation.through]
    return {"rung": rung, "rows": rows, "decisions": decisions, "failures": failures,
            "complete": len(rows) == len(expected), "window": WINDOW_BLOCKS,
            "persistenceApplied": persistence, "confidenceApplied": confidence,
            "hysteresisApplied": hysteresis, "costHurdleApplied": cost_hurdle,
            "expectedBlocks": len(expected), "measuredBlocks": len(rows)}


# --------------------------------------------------------------------------- #
# Diagnostics: how much portfolio action one percentile point is buying
# --------------------------------------------------------------------------- #
def axis_diagnostics(contexts: dict, calendar: list[dict]) -> dict:
    """What the ranking's inputs look like, before any rung is read.

    `signal_persistence` established that a name's percentile moves a mean of
    1.146 points between blocks, which says the axis is narrow. This says
    something sharper: how much of that narrow axis the calibration can even
    represent, and how much dispersion the confidence components have to work
    with. A component with no spread cannot change a decision, and finding that
    out from the ladder's result instead of from the inputs would be reading a
    null result as a finding.
    """
    edges = (0, 60, 80, 90, 95, 100)
    percentiles, own_sd, cross_sd, agreement, coverage = [], [], [], [], []
    buckets: dict[str, int] = defaultdict(int)
    smoother = SP.PercentileSmoother(WINDOW_BLOCKS)
    for block in sorted(calendar, key=lambda b: b["date"]):
        candidates, _ = contexts.get(block["signalDate"]) or ([], {})
        by_region: dict[str, list[float]] = defaultdict(list)
        for candidate in candidates:
            value = PV._finite(candidate.get("alphaPercentile"))
            if value is None:
                continue
            percentiles.append(value)
            buckets[str(PV._bucket(value, edges))] += 1
            by_region[candidate.get("region") or "UNKNOWN"].append(value)
            dispersion = smoother.dispersion(candidate["ticker"])
            if dispersion is not None:
                own_sd.append(dispersion)
            weight = sleeve_agreement(candidate.get("factorPercentiles"))
            if weight is not None:
                agreement.append(weight)
            evidence = PV._finite(candidate.get("evidenceCoverage"))
            if evidence is not None:
                coverage.append(float(evidence))
        for values in by_region.values():
            if len(values) > 1:
                cross_sd.append(float(np.std(values, ddof=1)))
        smoother_block = block["date"]
        for candidate in candidates:
            smoother.observe(candidate["ticker"], candidate.get("alphaPercentile"),
                             smoother_block)
    total = sum(buckets.values())
    dominant = max(buckets.values()) if buckets else 0
    return {
        "available": bool(total),
        "bucketEdges": list(edges),
        "poolNameDates": total,
        "bucketCounts": dict(sorted(buckets.items())),
        "distinctBucketsOccupied": len(buckets),
        "largestBucketSharePct": round(dominant / total * 100, 2) if total else None,
        "alphaPercentile": _spread(percentiles),
        "ownPercentileSdOverWindow": _spread(own_sd),
        "crossSectionPercentileSdWithinRegionDate": _spread(cross_sd),
        "sleeveAgreement": _spread(agreement),
        "evidenceCoverageAlreadyInTheLevel": _spread(coverage),
        "confidenceExclusions": dict(CONFIDENCE_EXCLUSIONS),
        "note": ("The pool is already alpha-filtered, so its percentiles occupy very "
                 "few calibration buckets and names inside one bucket are handed the "
                 "SAME expected excess. Evidence coverage is reported because it is "
                 "ALREADY multiplied into alpha before the percentile is taken, which "
                 "is why it is not available as a confidence weight."),
    }


def _spread(values) -> dict:
    array = np.asarray([v for v in values if v is not None], dtype=float)
    if not array.size:
        return {"available": False, "observations": 0}
    return {
        "available": True, "observations": int(array.size),
        "mean": round(float(array.mean()), 4),
        "sd": round(float(array.std(ddof=1)), 4) if array.size > 1 else None,
        "p10": round(float(np.percentile(array, 10)), 4),
        "median": round(float(np.median(array)), 4),
        "p90": round(float(np.percentile(array, 90)), 4),
        "min": round(float(array.min()), 4), "max": round(float(array.max()), 4),
    }


def boundary_instability(decisions: list[dict]) -> dict:
    """What separates the last name held from the first name excluded.

    The book holds five of roughly twenty-four. If the marginal pair is
    separated by a real difference in expected alpha, the cut is a decision; if
    they carry the SAME calibrated alpha and are ordered by realised downside
    volatility alone, the cut is a coin the ranking is not entitled to flip.
    `tiedOnExpectedAlphaPct` is the number that distinguishes those, and it is
    the reason this study exists rather than a colour on its report.
    """
    gaps, alpha_gaps, percentile_gaps, confidence_gaps = [], [], [], []
    tied = 0
    measured = 0
    cap_bound = 0
    for decision in decisions:
        scored = decision.get("scored") or []
        eligible = [row for row in scored if row.get("eligible")]
        if len(eligible) < 2:
            continue
        ordered = sorted(eligible, key=lambda r: (-r["score"], str(r["ticker"])))
        held = set(decision.get("retained") or []) | set(decision.get("added") or [])
        inside = [row for row in ordered if row["ticker"] in held]
        outside = [row for row in ordered if row["ticker"] not in held
                   and _excluded_by_rank(row)]
        if not inside:
            continue
        if not outside:
            # Every near miss was stopped by a cap, so the cut was made by the
            # diversification rules rather than by the ranking. That is not a
            # boundary this study is entitled to read, and it is counted rather
            # than quietly dropped.
            cap_bound += 1
            continue
        marginal, first_out = inside[-1], outside[0]
        measured += 1
        gaps.append(_relative_gap(marginal["score"], first_out["score"]))
        alpha_gap = _difference(marginal.get("expectedGrossBenchmarkExcessPct"),
                                first_out.get("expectedGrossBenchmarkExcessPct"))
        if alpha_gap is not None:
            alpha_gaps.append(alpha_gap)
            if abs(alpha_gap) <= 1e-12:
                tied += 1
        percentile_gap = _difference(marginal.get("alphaPercentile"),
                                     first_out.get("alphaPercentile"))
        if percentile_gap is not None:
            percentile_gaps.append(percentile_gap)
        confidence_gap = _difference(marginal.get("signalConfidence"),
                                     first_out.get("signalConfidence"))
        if confidence_gap is not None:
            confidence_gaps.append(confidence_gap)
    return {
        "available": bool(measured), "rebalancesMeasured": measured,
        "rebalancesWhereEveryNearMissWasCapped": cap_bound,
        "relativeScoreGapAtCut": _spread(gaps),
        "expectedAlphaGapAtCutPp": _spread(alpha_gaps),
        "alphaPercentileGapAtCut": _spread(percentile_gaps),
        "confidenceGapAtCut": _spread(confidence_gaps),
        "tiedOnExpectedAlphaPct": (round(tied / len(alpha_gaps) * 100, 2)
                                   if alpha_gaps else None),
        "note": ("The marginal held name against the first excluded one, on the rung's "
                 "own ordering. A tie on expected alpha means the calibration could not "
                 "tell the two apart and the cut was made by downside volatility."),
    }


def replacement_anatomy(decisions: list[dict], priced_by_date: dict) -> dict:
    """Every swap the path made: what separated the two names, and who was right.

    A replacement is the most expensive action this book takes and the one the
    ranking has the least resolution to justify. Three things are measured and
    they answer different questions: how big the signal difference was, how
    often there was no difference at all, and whether the arriving name actually
    went on to beat the one it displaced over the block that followed.

    The success rate is a realised outcome and carries no look-ahead into the
    DECISION — it reads what the path already did against the cross-section the
    book was priced on, exactly as `signal_persistence.incumbency_outcomes`
    does. Nothing here feeds back into any rung.
    """
    alpha_gaps, percentile_gaps, confidence_gaps = [], [], []
    outcomes, tied_outcomes, separated_outcomes = [], [], []
    tied = replacements = 0
    small_move_total = small_move_replaced = 0
    previous_raw: dict[str, float] = {}

    for decision in sorted(decisions, key=lambda d: d["date"]):
        scored = {row["ticker"]: row for row in (decision.get("scored") or [])}
        priced = priced_by_date.get(decision["date"]) or {}
        replaced = list(decision.get("replaced") or [])
        added = list(decision.get("added") or [])

        # Did a name the ranking barely moved its opinion about get dropped?
        for ticker, row in scored.items():
            raw = PV._finite(row.get("rawAlphaPercentile"))
            if raw is None:
                continue
            was_held = ticker in set(decision.get("retained") or []) | set(replaced)
            if was_held and ticker in previous_raw and abs(raw - previous_raw[ticker]) <= 1.0:
                small_move_total += 1
                if ticker in replaced:
                    small_move_replaced += 1
        for ticker, row in scored.items():
            raw = PV._finite(row.get("rawAlphaPercentile"))
            if raw is not None:
                previous_raw[ticker] = raw

        if not replaced or not added:
            continue
        # Pair the swap at its margin: the weakest arrival against the strongest
        # departure is the pair the decision actually turned on.
        arrivals = sorted((scored[t] for t in added if t in scored),
                          key=lambda r: (r["score"], str(r["ticker"])))
        departures = sorted((scored[t] for t in replaced if t in scored),
                            key=lambda r: (-r["score"], str(r["ticker"])))
        if not arrivals or not departures:
            continue
        arrival, departure = arrivals[0], departures[0]
        replacements += 1
        alpha_gap = _difference(arrival.get("expectedGrossBenchmarkExcessPct"),
                                departure.get("expectedGrossBenchmarkExcessPct"))
        is_tied = alpha_gap is not None and abs(alpha_gap) <= 1e-12
        if alpha_gap is not None:
            alpha_gaps.append(alpha_gap)
            tied += int(is_tied)
        percentile_gap = _difference(arrival.get("alphaPercentile"),
                                     departure.get("alphaPercentile"))
        if percentile_gap is not None:
            percentile_gaps.append(percentile_gap)
        confidence_gap = _difference(arrival.get("signalConfidence"),
                                     departure.get("signalConfidence"))
        if confidence_gap is not None:
            confidence_gaps.append(confidence_gap)

        in_cell = priced.get(arrival["ticker"])
        out_cell = priced.get(departure["ticker"])
        if (in_cell is not None and out_cell is not None
                and in_cell.get("excessReturn") is not None
                and out_cell.get("excessReturn") is not None):
            realised = float(in_cell["excessReturn"]) - float(out_cell["excessReturn"])
            outcomes.append(realised)
            (tied_outcomes if is_tied else separated_outcomes).append(realised)

    return {
        "available": bool(replacements), "replacementsMeasured": replacements,
        "expectedAlphaGapAtReplacementPp": _spread(alpha_gaps),
        "alphaPercentileGapAtReplacement": _spread(percentile_gaps),
        "confidenceGapAtReplacement": _spread(confidence_gaps),
        "tiedOnExpectedAlphaPct": (round(tied / len(alpha_gaps) * 100, 2)
                                   if alpha_gaps else None),
        "arrivingMinusDepartingExcess": _outcome_block(outcomes),
        "whenTiedOnExpectedAlpha": _outcome_block(tied_outcomes),
        "whenSeparatedOnExpectedAlpha": _outcome_block(separated_outcomes),
        "incumbentsWhosePercentileMovedOnePointOrLess": small_move_total,
        "ofThoseReplacedPct": (round(small_move_replaced / small_move_total * 100, 2)
                               if small_move_total else None),
        "note": ("One pair per rebalance: the weakest arrival against the strongest "
                 "departure, which is the pair the decision turned on. The realised "
                 "figure is the forward 21-session benchmark excess of the arriving "
                 "name minus the departing one, read off the same priced cross-section "
                 "the book was valued on."),
    }


def _excluded_by_rank(row: dict) -> bool:
    """Did the ranking put this name below the cut, or did a cap stop it?

    `_select_scored` stamps `BELOW_TARGET_COUNT_CUTOFF` on everything it reaches
    after the book is full and a cap code on anything it refused earlier. A
    capped name is not the ranking's marginal reject, and comparing the last
    held name against it would measure the diversification rules. A row with no
    recorded reason sits outside the audited near-miss window, which puts it
    below the names that do carry one.
    """
    codes = row.get("selectionExclusionCodes")
    if not codes:
        return False
    if "SECTOR_NAME_LIMIT" in codes or "REGION_NAME_LIMIT" in codes:
        return False
    return "BELOW_TARGET_COUNT_CUTOFF" in codes


def annotate_selection(candidates: list[dict], scored: list[dict], cfg_pf: dict, *,
                       method: str) -> tuple[dict[str, list[str]], set[str]]:
    """Why each name did or did not make the cut, for the WHOLE cross-section.

    Calls PRODUCTION's `_select_scored` on copies rather than re-deriving the
    rule, so the annotation cannot drift from the selection it describes: a
    second implementation of the caps would eventually disagree with the one
    that picked the book and the diagnostic would be measuring itself. The
    caller asserts the returned set contains what the path actually held.
    """
    normalized = []
    for row in scored:
        item = dict(row)
        # From the pristine eligibility facts, never from a list an earlier
        # selection pass has already appended its own cut codes to.
        item["exclusionCodes"] = list(row.get("eligibilityCodes") or ())
        normalized.append(item)
    normalized.sort(key=lambda r: (-float(r.get("score") or 0.0), str(r.get("ticker") or "")))
    selected, _ = KP._select_scored(
        candidates, normalized, cfg_pf, method=method,
        score_formula_ko="진단 전용 재현", not_a_forecast_ko="진단 전용 재현")
    reasons = {row["ticker"]: list(row.get("exclusionCodes") or []) for row in normalized}
    return reasons, {row["ticker"] for row in selected}


def _average_ranks(values: np.ndarray) -> np.ndarray:
    """Ranks with ties averaged, which is what a rank correlation needs.

    The calibration hands most of this pool one expected alpha, so ties are the
    common case rather than the edge case; breaking them arbitrarily would
    invent an ordering and then measure how well the score reproduces it.
    """
    order = np.argsort(values, kind="stable")
    ranks = np.empty(values.size, dtype=float)
    ranks[order] = np.arange(values.size, dtype=float)
    sorted_values = values[order]
    start = 0
    for index in range(1, values.size + 1):
        if index == values.size or sorted_values[index] != sorted_values[start]:
            ranks[order[start:index]] = ranks[order[start:index]].mean()
            start = index
    return ranks


def _spearman(left, right):
    """Rank correlation, or `None` when either side has no spread to correlate."""
    x = np.asarray(left, dtype=float)
    y = np.asarray(right, dtype=float)
    if x.size < 3 or x.size != y.size:
        return None
    rx, ry = _average_ranks(x), _average_ranks(y)
    if rx.std() <= 0 or ry.std() <= 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def _eligible_rows(decision: dict) -> list[dict]:
    return [row for row in (decision.get("scored") or []) if row.get("eligible")]


def _held_of(decision: dict) -> set[str]:
    return set(decision.get("retained") or []) | set(decision.get("added") or [])


# --------------------------------------------------------------------------- #
# A. Is this a model that picks alpha, or one that picks low volatility?
# --------------------------------------------------------------------------- #
def risk_dominance(decisions: list[dict]) -> dict:
    """How much of the final ordering is the alpha term and how much is the risk term.

    The score is `expected excess / downside volatility x entry multiplier`, and
    the axis diagnostic already established that the calibration hands most of
    this pool ONE expected excess. When the numerator is a constant across five
    names in six, the ordering that remains is the denominator's. This measures
    that directly on the path's own rows rather than inferring it.

    Nothing counterfactual is run and no return is read. Every figure is the
    cross-section the rebalance actually scored, read three ways: what the score
    correlates with, which names the ranking would have held on alpha alone, and
    which ones the risk term moved across the cut.
    """
    alpha_corr, vol_corr, calibrated_corr = [], [], []
    lowvol_selected, lowvol_rejected = [], []
    vol_selected, vol_rejected = [], []
    overlap, inversions = [], []
    lowvol_is_top_driver = lowvol_top_two = driver_rows = 0
    promoted_by_low_risk = dropped_by_high_risk = 0
    promoted_examples, dropped_examples = [], []
    measured = 0

    for decision in sorted(decisions, key=lambda d: d["date"]):
        rows = _eligible_rows(decision)
        if len(rows) < 3:
            continue
        held = _held_of(decision)
        if not held:
            continue
        measured += 1
        score = np.array([float(r["score"]) for r in rows])
        percentile = np.array([PV._finite(r.get("alphaPercentile")) or np.nan for r in rows])
        vol = np.array([PV._finite(r.get("downsideVolPct")) or np.nan for r in rows])
        calibrated = np.array([PV._finite(r.get("expectedGrossBenchmarkExcessPct")) or np.nan
                               for r in rows])
        usable = ~np.isnan(percentile) & ~np.isnan(vol) & ~np.isnan(calibrated)
        if usable.sum() >= 3:
            alpha_corr.append(_spearman(percentile[usable], score[usable]))
            vol_corr.append(_spearman(vol[usable], score[usable]))
            calibrated_corr.append(_spearman(calibrated[usable], score[usable]))

        for row in rows:
            sleeves = {k: PV._finite(v) for k, v in (row.get("factorPercentiles") or {}).items()}
            sleeves = {k: v for k, v in sleeves.items() if v is not None}
            unit = PV._finite(row.get("downsideVolPct"))
            inside = row["ticker"] in held
            if unit is not None:
                (vol_selected if inside else vol_rejected).append(unit)
            if "lowvol" in sleeves:
                (lowvol_selected if inside else lowvol_rejected).append(sleeves["lowvol"])
            if inside and len(sleeves) >= 2:
                driver_rows += 1
                ordered = sorted(sleeves, key=lambda k: -sleeves[k])
                lowvol_is_top_driver += int(ordered[0] == "lowvol")
                lowvol_top_two += int("lowvol" in ordered[:2])

        # What the ranking would hold on the ALPHA term alone, at the same count
        # and under no other change. This is a reading of one block's own rows,
        # not a path: nothing is valued, carried forward or compounded.
        count = len(held)
        by_alpha = sorted(rows, key=lambda r: (-(PV._finite(r.get("alphaPercentile")) or -1e9),
                                               str(r["ticker"])))[:count]
        alpha_top = {r["ticker"] for r in by_alpha}
        overlap.append(len(alpha_top & held) / count)
        inversions.append(_ordering_inversions(rows, held))

        median_vol = float(np.nanmedian(vol)) if np.isfinite(vol).any() else None
        if median_vol is not None:
            for row in rows:
                unit = PV._finite(row.get("downsideVolPct"))
                if unit is None:
                    continue
                inside, top = row["ticker"] in held, row["ticker"] in alpha_top
                if inside and not top and unit < median_vol:
                    promoted_by_low_risk += 1
                    promoted_examples.append(unit - median_vol)
                if top and not inside and unit > median_vol:
                    # A name a CAP stopped was not dropped by its volatility.
                    codes = row.get("selectionExclusionCodes") or []
                    if not ({"SECTOR_NAME_LIMIT", "REGION_NAME_LIMIT"} & set(codes)):
                        dropped_by_high_risk += 1
                        dropped_examples.append(unit - median_vol)

    return {
        "available": bool(measured), "rebalancesMeasured": measured,
        "scoreVsAlphaPercentileSpearman": _spread([c for c in alpha_corr if c is not None]),
        "scoreVsCalibratedAlphaSpearman": _spread([c for c in calibrated_corr if c is not None]),
        "scoreVsDownsideVolSpearman": _spread([c for c in vol_corr if c is not None]),
        "downsideVolPctSelected": _spread(vol_selected),
        "downsideVolPctRejected": _spread(vol_rejected),
        "lowvolSleevePercentileSelected": _spread(lowvol_selected),
        "lowvolSleevePercentileRejected": _spread(lowvol_rejected),
        "heldNameSleeveRows": driver_rows,
        "lowvolIsTheHighestSleevePct": (round(lowvol_is_top_driver / driver_rows * 100, 2)
                                        if driver_rows else None),
        "lowvolIsInTheTopTwoSleevesPct": (round(lowvol_top_two / driver_rows * 100, 2)
                                          if driver_rows else None),
        "heldMatchingAlphaOnlyTopNPct": (round(float(np.mean(overlap)) * 100, 2)
                                         if overlap else None),
        "pairwiseOrderingInversionsPct": _spread(inversions),
        "heldDespiteLowerAlphaAndBelowMedianRisk": promoted_by_low_risk,
        "droppedDespiteTopAlphaAndAboveMedianRisk": dropped_by_high_risk,
        "promotedRiskGapToMedianPp": _spread(promoted_examples),
        "droppedRiskGapToMedianPp": _spread(dropped_examples),
        "note": ("Read off the rows each rebalance actually scored. The alpha-only "
                 "top-N is a within-block reading of the same cross-section, never a "
                 "path: nothing is valued or carried forward, and no realised return "
                 "enters any figure here. Names a sector or region cap stopped are "
                 "excluded from the risk-drop count, because a cap is not volatility."),
    }


def _ordering_inversions(rows: list[dict], held: set[str]) -> float:
    """Share of held/not-held pairs the alpha term orders the other way.

    One pair, one vote: for every name inside the book against every name
    outside it, does the alpha percentile agree that the inside one ranks
    higher? A tie counts as no inversion, because a tie is the calibration
    declining to order them rather than disagreeing.
    """
    inside = [PV._finite(r.get("alphaPercentile")) for r in rows if r["ticker"] in held]
    outside = [PV._finite(r.get("alphaPercentile")) for r in rows if r["ticker"] not in held]
    inside = [v for v in inside if v is not None]
    outside = [v for v in outside if v is not None]
    pairs = len(inside) * len(outside)
    if not pairs:
        return 0.0
    flipped = sum(1 for a in inside for b in outside if a < b)
    return flipped / pairs * 100.0


# --------------------------------------------------------------------------- #
# B. What the entry state's step function does to the ordering
# --------------------------------------------------------------------------- #
def entry_state_dynamics(decisions: list[dict]) -> dict:
    """Entry state moves the score in STEPS, so a technical trigger is a cliff.

    The multiplier is 1.0 / 0.5 / 0.25 / 0.0 by state, and it multiplies the
    whole score. A name crossing from `ACCUMULATE_GRADUALLY` into `WATCH` has
    its score halved with nothing about its alpha having changed, and a name
    crossing into `EVENT_RISK` or `AVOID` leaves the book outright. This counts
    how often that happened and how often it coincided with a swap.

    The key figure is the last one: transitions where the name's own alpha
    percentile moved a point or less — the same unit the boundary diagnostic
    uses — and its held status flipped anyway. That is the step function, not
    the signal, deciding what is owned.
    """
    transitions: dict[str, int] = defaultdict(int)
    with_action: dict[str, int] = defaultdict(int)
    state_counts: dict[str, int] = defaultdict(int)
    previous: dict[str, tuple[str | None, float | None, float | None]] = {}
    total = coincident = flat_alpha_flips = 0
    forced_out = 0
    blocking_departures = 0

    for decision in sorted(decisions, key=lambda d: d["date"]):
        rows = decision.get("scored") or []
        replaced = set(decision.get("replaced") or [])
        added = set(decision.get("added") or [])
        for row in rows:
            ticker = row["ticker"]
            state = row.get("entryState")
            multiplier = PV._finite(row.get("entryStateMultiplier"))
            percentile = PV._finite(row.get("rawAlphaPercentile"))
            state_counts[str(state)] += 1
            before = previous.get(ticker)
            previous[ticker] = (state, multiplier, percentile)
            if before is None:
                continue
            prior_state, prior_multiplier, prior_percentile = before
            if prior_state == state:
                continue
            total += 1
            label = f"{prior_state} -> {state}"
            transitions[label] += 1
            # "Coincided with a swap" means this rebalance moved this name in
            # or out, which is the only way a state change can have touched the
            # book at all. A state that moved on a name the book neither took
            # nor dropped changed nothing.
            if ticker in replaced or ticker in added:
                coincident += 1
                with_action[label] += 1
            if multiplier is not None and multiplier <= 0:
                forced_out += 1
                if ticker in replaced:
                    blocking_departures += 1
            # The step moved, the signal did not, and the book changed anyway.
            moved = (abs(percentile - prior_percentile)
                     if percentile is not None and prior_percentile is not None else None)
            if (moved is not None and moved <= 1.0 and ticker in replaced
                    and multiplier is not None and prior_multiplier is not None
                    and multiplier < prior_multiplier):
                flat_alpha_flips += 1

    grouped = {
        "intoOrOutOfEventRiskOrAvoid": sum(
            count for label, count in transitions.items()
            if "EVENT_RISK" in label or "AVOID" in label),
        "watchAgainstWaitForPullback": sum(
            count for label, count in transitions.items()
            if "WATCH" in label and "WAIT_FOR_PULLBACK" in label),
    }
    return {
        "available": bool(total), "transitionsObserved": total,
        "observedStates": dict(sorted(state_counts.items())),
        "byTransition": dict(sorted(transitions.items(), key=lambda kv: -kv[1])),
        "byTransitionCoincidingWithASwap": dict(
            sorted(with_action.items(), key=lambda kv: -kv[1])),
        "groupedTransitions": grouped,
        "transitionsCoincidingWithASwapPct": (round(coincident / total * 100, 2)
                                              if total else None),
        "transitionsIntoABlockingState": forced_out,
        "departuresWhoseStateHadTurnedBlocking": blocking_departures,
        "departuresWhereTheStepFellAndAlphaMovedOnePointOrLess": flat_alpha_flips,
        "note": ("A transition is a name's own state changing between two blocks it "
                 "appeared in. The last figure is the one that matters: the entry "
                 "multiplier fell, the name left the book, and its own alpha percentile "
                 "had moved a point or less. Entry logic is NOT changed by this study."),
    }


# --------------------------------------------------------------------------- #
# C. How often the diversification guard overrides the ranking
# --------------------------------------------------------------------------- #
def region_cap_binding(decisions: list[dict], cfg_pf: dict) -> dict:
    """Does `maxNamesPerRegion` decide the book more often than the signal does?

    A five-name book under a three-per-region cap can only ever be 3:2 or
    thinner, so the constraint is close to binding by construction — which is
    exactly why it has to be measured rather than assumed. For every name the
    cap stopped, this asks whether it outscored a name that was taken, and by
    how much in score, decision alpha and percentile.

    The unconstrained mix is the region composition of the top-N eligible names
    by the block's OWN score with the caps lifted. It is a reading of one
    block's ordering, not a path: nothing is valued and no return is read. The
    constraint is not removed anywhere in this study.
    """
    selection = cfg_pf.get("selection") or {}
    per_region = int(selection.get("maxNamesPerRegion", 0))
    per_sector = int(selection.get("maxNamesPerSector", 0))
    region_bound = sector_bound = measured = 0
    outscoring_blocks = 0
    score_gaps, alpha_gaps, percentile_gaps = [], [], []
    held_mix: dict[str, int] = defaultdict(int)
    free_mix: dict[str, int] = defaultdict(int)
    held_by_region_counts: dict[str, int] = defaultdict(int)

    for decision in sorted(decisions, key=lambda d: d["date"]):
        rows = _eligible_rows(decision)
        held = _held_of(decision)
        if not rows or not held:
            continue
        measured += 1
        ordered = sorted(rows, key=lambda r: (-float(r["score"]), str(r["ticker"])))
        inside = [r for r in ordered if r["ticker"] in held]
        region_of = decision.get("regionByTicker") or {}
        shape = "/".join(f"{region}:{count}" for region, count in sorted(
            _count_values(region_of[t] for t in held if t in region_of).items()))
        held_by_region_counts[shape] += 1
        for ticker in held:
            held_mix[str(region_of.get(ticker) or "UNKNOWN")] += 1

        blocked_region = [r for r in ordered
                          if "REGION_NAME_LIMIT" in (r.get("selectionExclusionCodes") or [])]
        blocked_sector = [r for r in ordered
                          if "SECTOR_NAME_LIMIT" in (r.get("selectionExclusionCodes") or [])]
        region_bound += int(bool(blocked_region))
        sector_bound += int(bool(blocked_sector))
        if blocked_region and inside:
            marginal = inside[-1]
            better = [r for r in blocked_region if float(r["score"]) > float(marginal["score"])]
            if better:
                outscoring_blocks += 1
                best = better[0]
                score_gaps.append(_relative_gap(best["score"], marginal["score"]))
                gap = _difference(best.get("decisionAlphaPct"), marginal.get("decisionAlphaPct"))
                if gap is not None:
                    alpha_gaps.append(gap)
                gap = _difference(best.get("alphaPercentile"), marginal.get("alphaPercentile"))
                if gap is not None:
                    percentile_gaps.append(gap)
        for row in ordered[:len(held)]:
            free_mix[str(row.get("region") or "UNKNOWN")] += 1

    return {
        "available": bool(measured), "rebalancesMeasured": measured,
        "maxNamesPerRegion": per_region, "maxNamesPerSector": per_sector,
        "rebalancesWhereTheRegionCapStoppedAName": region_bound,
        "rebalancesWhereTheSectorCapStoppedAName": sector_bound,
        "regionCapBindingPct": (round(region_bound / measured * 100, 2) if measured else None),
        "sectorCapBindingPct": (round(sector_bound / measured * 100, 2) if measured else None),
        "rebalancesWhereACappedNameOutscoredOneTaken": outscoring_blocks,
        "relativeScoreGapAtTheOverride": _spread(score_gaps),
        "decisionAlphaGapAtTheOverridePp": _spread(alpha_gaps),
        "alphaPercentileGapAtTheOverride": _spread(percentile_gaps),
        "heldNameDatesByRegion": dict(sorted(held_mix.items())),
        "heldRegionShapeCounts": dict(sorted(held_by_region_counts.items(),
                                             key=lambda kv: -kv[1])),
        "topNByScoreWithCapsLiftedByRegion": dict(sorted(free_mix.items())),
        "note": ("The capped-name comparison is against the LOWEST-scoring name the "
                 "book took, which is the one a lifted cap would have displaced. The "
                 "caps-lifted mix is a reading of each block's own ordering; no path is "
                 "run without the constraint and no realised return is used."),
    }


def _count_values(values) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for value in values:
        out[str(value or "UNKNOWN")] += 1
    return dict(out)


# --------------------------------------------------------------------------- #
# D. What a breadth rule would have to work with
# --------------------------------------------------------------------------- #
def breadth_readiness(decisions: list[dict]) -> dict:
    """The shape of the ordering a fixed count of five is currently cutting.

    Preparation only. `targetNames` is NOT changed by this study and no breadth
    rule is implemented or scored. What is recorded is what a later one would
    need: where the ordering actually separates, how many of the names a fixed
    five takes are indistinguishable from each other, and how many just outside
    it are indistinguishable from the fifth.

    "Near neutral" is a name whose reliable alpha is smaller than the
    uncertainty the contraction discarded from it — its own doubt is larger than
    its own claim. That is the module's existing quantity read against itself,
    not a threshold chosen for this diagnostic.
    """
    by_rank: dict[int, list[float]] = defaultdict(list)
    gaps: dict[str, list[float]] = defaultdict(list)
    near_neutral_top10, tied_in_top5, indistinct_6_to_10 = [], [], []
    dispersion_top5, dispersion_top10 = [], []
    eligible_counts = []
    measured = 0

    for decision in sorted(decisions, key=lambda d: d["date"]):
        rows = _eligible_rows(decision)
        if len(rows) < 2:
            continue
        measured += 1
        eligible_counts.append(len(rows))
        ordered = sorted(rows, key=lambda r: (-float(r["score"]), str(r["ticker"])))
        alpha = [PV._finite(r.get("decisionAlphaPct")) for r in ordered]
        for rank in range(1, 11):
            if rank <= len(alpha) and alpha[rank - 1] is not None:
                by_rank[rank].append(alpha[rank - 1])
        for label, (high, low) in (("rank3MinusRank4", (3, 4)), ("rank5MinusRank6", (5, 6)),
                                   ("rank8MinusRank9", (8, 9)), ("rank10MinusRank11", (10, 11))):
            if low <= len(alpha) and alpha[high - 1] is not None and alpha[low - 1] is not None:
                gaps[label].append(alpha[high - 1] - alpha[low - 1])

        window = ordered[:10]
        near_neutral_top10.append(sum(
            1 for r in window
            if (PV._finite(r.get("reliableAlphaPct")) is not None
                and PV._finite(r.get("uncertaintyMarginPct")) is not None
                and abs(float(r["reliableAlphaPct"])) <= float(r["uncertaintyMarginPct"]))))

        top5 = ordered[:5]
        expected5 = [PV._finite(r.get("expectedGrossBenchmarkExcessPct")) for r in top5]
        expected5 = [v for v in expected5 if v is not None]
        tied_in_top5.append(len(expected5) - len(set(round(v, 10) for v in expected5)))
        fifth = expected5[-1] if len(expected5) == len(top5) and expected5 else None
        tail = ordered[5:10]
        if fifth is not None:
            indistinct_6_to_10.append(sum(
                1 for r in tail
                if PV._finite(r.get("expectedGrossBenchmarkExcessPct")) is not None
                and abs(float(r["expectedGrossBenchmarkExcessPct"]) - fifth) <= 1e-12))
        for target, values in ((dispersion_top5, [PV._finite(r.get("decisionAlphaPct")) for r in top5]),
                               (dispersion_top10, [PV._finite(r.get("decisionAlphaPct")) for r in window])):
            clean = [v for v in values if v is not None]
            if len(clean) > 1:
                target.append(float(np.std(clean, ddof=1)))

    return {
        "available": bool(measured), "rebalancesMeasured": measured,
        "targetNamesUnchanged": 5,
        "eligibleCandidates": _spread(eligible_counts),
        "decisionAlphaByRankPp": {str(rank): _spread(values)
                                  for rank, values in sorted(by_rank.items())},
        "decisionAlphaGapsPp": {label: _spread(values) for label, values in sorted(gaps.items())},
        "namesInTopTenWhoseDoubtExceedsTheirClaim": _spread(near_neutral_top10),
        "tiedPairsInsideTheTopFive": _spread(tied_in_top5),
        "ranksSixToTenTiedWithTheFifthName": _spread(indistinct_6_to_10),
        "decisionAlphaDispersionTopFivePp": _spread(dispersion_top5),
        "decisionAlphaDispersionTopTenPp": _spread(dispersion_top10),
        "note": ("Preparation for a later study and nothing more: `targetNames` stays "
                 "at five here, no breadth rule is implemented, and no rung was added. "
                 "Near-neutral is a name whose own discarded uncertainty exceeds its "
                 "own reliable alpha, which is the module's existing quantity read "
                 "against itself rather than a threshold chosen here."),
    }


# --------------------------------------------------------------------------- #
# Why each departure actually happened
# --------------------------------------------------------------------------- #
def departure_causes(decisions: list[dict]) -> dict:
    """One mutually exclusive reason per name that left the book.

    Asked in the order the machinery applies them, so a name is attributed to
    the FIRST thing that would have removed it: the screen dropped it, its own
    facts made it ineligible, a cap refused it, or the ranking put it below the
    cut. Without the ordering the same departure would be counted under several
    headings and the shares would not add up to the departures.

    For the ones the ranking outranked, the name's own movement since its
    previous appearance is reported — percentile, reliable alpha and confidence
    — so a reader can see which of them moved rather than being told.
    """
    causes: dict[str, int] = defaultdict(int)
    ineligibility: dict[str, int] = defaultdict(int)
    percentile_moves, alpha_moves, confidence_moves = [], [], []
    previous: dict[str, dict] = {}
    departures = 0

    for decision in sorted(decisions, key=lambda d: d["date"]):
        rows = {row["ticker"]: row for row in (decision.get("scored") or [])}
        for ticker in sorted(decision.get("replaced") or []):
            departures += 1
            row = rows.get(ticker)
            if row is None:
                causes["LEFT_THE_RESEARCH_POOL"] += 1
                continue
            codes = set(row.get("eligibilityCodes") or ())
            cut = set(row.get("selectionExclusionCodes") or ())
            if "ENTRY_OR_RESEARCH_STATE_BLOCKS_SIZING" in codes:
                causes["ENTRY_OR_RESEARCH_STATE_TURNED_BLOCKING"] += 1
            elif codes:
                causes["BECAME_INELIGIBLE_ON_ITS_OWN_FACTS"] += 1
                # "Ineligible" pools three very different facts — a calibration
                # that has not matured yet, a missing risk unit, and an
                # unmeasurable confidence — and only the last two are about the
                # name. Reported apart so an early-history artefact cannot read
                # as a selection decision.
                for code in sorted(codes):
                    ineligibility[code] += 1
            elif "SECTOR_NAME_LIMIT" in cut:
                causes["SECTOR_CAP"] += 1
            elif "REGION_NAME_LIMIT" in cut:
                causes["REGION_CAP"] += 1
            else:
                causes["OUTRANKED_AT_THE_CUT"] += 1
                before = previous.get(ticker)
                if before is not None:
                    for key, target in (("rawAlphaPercentile", percentile_moves),
                                        ("reliableAlphaPct", alpha_moves),
                                        ("signalConfidence", confidence_moves)):
                        move = _difference(row.get(key), before.get(key))
                        if move is not None:
                            target.append(move)
        for ticker, row in rows.items():
            previous[ticker] = row

    return {
        "available": bool(departures), "departuresMeasured": departures,
        "byCause": dict(sorted(causes.items(), key=lambda kv: -kv[1])),
        "ineligibilityByCode": dict(sorted(ineligibility.items(), key=lambda kv: -kv[1])),
        "bySharePct": {cause: round(count / departures * 100, 2)
                       for cause, count in sorted(causes.items(), key=lambda kv: -kv[1])}
        if departures else {},
        "outrankedOwnPercentileMove": _spread(percentile_moves),
        "outrankedOwnReliableAlphaMovePp": _spread(alpha_moves),
        "outrankedOwnConfidenceMove": _spread(confidence_moves),
        "note": ("Causes are asked in the order the machinery applies them, so each "
                 "departure is attributed once and the shares sum to the departures. "
                 "The movement figures are the departing name's own change since its "
                 "previous appearance, signed."),
    }


def _outcome_block(values) -> dict:
    array = np.asarray(list(values), dtype=float)
    if not array.size:
        return {"available": False, "observations": 0}
    return {
        "available": True, "observations": int(array.size),
        "meanPct": round(float(array.mean()) * 100, 4),
        "medianPct": round(float(np.median(array)) * 100, 4),
        "winRatePct": round(float((array > 0).mean()) * 100, 2),
        # `_bootstrap_ci` already returns percentage points, so the mean above
        # is the only figure that needs scaling.
        "ci95Pct": (PV._bootstrap_ci(array, draws=4000, seed=11)
                    if array.size >= 2 else [None, None]),
    }


def _relative_gap(high, low):
    """The cut's width against its own level, so it reads across regimes.

    Scores are alpha per unit of downside risk and their level drifts with the
    calibration, so a raw gap of 0.01 means different things in 2013 and 2025.
    """
    if high is None or low is None:
        return None
    base = max(abs(float(high)), abs(float(low)))
    if base <= 0:
        return None
    return float(abs(float(high) - float(low)) / base)


def _difference(left, right):
    left, right = PV._finite(left), PV._finite(right)
    if left is None or right is None:
        return None
    return float(left) - float(right)


def retention_rates(decisions: list[dict]) -> dict:
    """Names kept against names replaced, in total and by region."""
    return SH.turnover_by_region(decisions)


def freeze_manifest() -> dict:
    return {
        "id": VERSION,
        "status": "CHALLENGER",
        "ladder": list(LADDER),
        "reportedSeparately": STACKED,
        "axisPerRung": {
            CONTROL: "NONE_THIS_IS_THE_BASELINE",
            PERSISTENCE: "BACKWARD_ONLY_K6_ALPHA_PERCENTILE_WINDOW",
            PERSISTENCE_CONFIDENCE: "CONTRACT_EXPECTED_ALPHA_BY_SIGNAL_CONFIDENCE",
            PERSISTENCE_CONFIDENCE_HYSTERESIS:
                "CREDIT_AN_INCUMBENT_THE_UNCERTAINTY_THE_CONTRACTION_DISCARDED",
        },
        "confidenceComponents": list(CONFIDENCE_COMPONENTS),
        "confidenceForm": "RELIABLE_ALPHA_EQUALS_CONFIDENCE_TIMES_CALIBRATED_ALPHA",
        "confidenceIsAContraction": True,
        "confidenceExclusions": dict(CONFIDENCE_EXCLUSIONS),
        "windowBlocks": WINDOW_BLOCKS,
        "windowSource": "INHERITED_FROM_SIGNAL_PERSISTENCE_V1_FORECAST_HORIZON",
        "uncertaintyMultiple": UNCERTAINTY_MULTIPLE,
        "maxPercentileDispersion": MAX_PERCENTILE_DISPERSION,
        "transactionCostHurdleInLadder": False,
        "permutationNullRun": False,
        # Added after the ladder was run and scored. Each one READS the paths
        # the ladder already produced; none adds a rung, changes a score, moves
        # a constraint or touches production. The ladder's numbers are the same
        # with them present and absent, which is what makes them safe to add to
        # a finished study.
        "structuralDiagnosticsAreObservationalOnly": True,
        "structuralDiagnostics": [
            "risk_dominance", "entry_state_dynamics", "region_cap_binding",
            "breadth_readiness", "departure_causes",
        ],
        "constraintsHeldFixedByTheseDiagnostics": [
            "lowvol sleeve weight stays 0.20 inside the four-factor alpha",
            "the downside-volatility denominator stays in the selection score",
            "inverse-downside-volatility baseline sizing is unchanged",
            "entry-state multipliers are unchanged",
            "maxNamesPerRegion stays 3 and maxNamesPerSector stays 2",
            "targetNames stays 5",
        ],
        "factorsAdded": [],
        "factorWeightsChanged": False,
        "parametersIntroduced": [],
        "heldFixedAcrossRungs": [
            "fixed 21-session evaluation blocks and their cadence",
            "PIT research candidate pool",
            "0.30/0.25/0.25/0.20 momentum/value/quality/low-vol sleeve weights",
            "expanding bucket calibration of percentile to expected excess",
            "entry-state and research-view exclusions",
            "name/sector/region caps, maxPositionWeight, cash floor",
            "conviction-tilted inverse-downside-volatility weights",
            "realistic dated transaction cost schedule on the realised path",
            "no transaction-cost switch hurdle",
        ],
        "promotionEligible": False,
        "liveValidated": False,
        "productionChanged": False,
    }
