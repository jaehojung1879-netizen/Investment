"""RP1 Track D — minimal SHADOW composition contract (eligibility check, no allocation).

Connects independently qualified outputs of Track A (stock selection), B (market-state context) and C (exposure rule) into one shadow
record. It is not an optimizer and produces no weight, order, recommendation or production decision. Default is the existing passive ETF
policy with zero active names; that default is restored whenever any gate below is not met. `docs/research-program/README.md` section D.

Gates (all must hold for A to be listed as a candidate for a SEPARATE economic validation, never for a position):
  - A: validated selection evidence, calibrated expected net excess return, uncertainty, and expected net excess above the round-trip cost
    (stock buy + stock sell + the passive-ETF sell that funds it). Missing is never zero.
  - B: contributes context only. No multiplier unless a conditional effect was validated AND shown incremental to C.
  - C: contributes a region rule only when an owner-approved interpretation exists. It is applied once to one fixed book, never stacked on B.
Currencies are never summed: candidates are reported per region.

Economic input contract (UNRESOLVED, fail-closed). 04 sec.7 and README sec.D state the gate as "calibrated expected net excess >
round-trip cost (stock + ETF sell)" without saying what "net" removes. With gross benchmark-relative excess G = E[R_i - R_b] and
round-trip cost C (the benchmark leg is charged nothing), the economic gate is G - C > 0. A value that is ALREADY net of C, run
through "value - C > 0", is charged twice (G > 2C); a gross value tested against 0 is charged never. No upstream producer of this
field exists anywhere in the repository (Track A publishes no calibrated expected excess), so no definition can be confirmed:
while EXPECTED_EXCESS_DEFINITION is UNRESOLVED every A record is ineligible and the passive default holds. Each record must still
declare its cost basis and registered benchmark, so a future producer cannot be misread in either direction.
"""
from __future__ import annotations

import json

STUDY = "rp1-d-composition-contract-v1"
EVIDENCE_CLASS = "SHADOW_CONTRACT_NO_ALLOCATION"
MAX_NAMES = 5
DEFAULT_POLICY = "EXISTING_PASSIVE_ETF_POLICY"
REGIONS = ("KR", "US")
FORBIDDEN_KEYS = ("weight", "weights", "order", "orders", "recommendation", "targetWeight", "notional", "shares")
_FORBIDDEN_NORMALISED = frozenset(k.lower() for k in FORBIDDEN_KEYS)
A_REQUIRED = ("validated", "calibrated", "expectedNetExcessPct", "uncertaintyPct", "roundTripCostPct", "candidates",
              "excessCostBasis", "benchmark")
# 04 sec.6 primary benchmarks; the excess must be relative to exactly these.
REGISTERED_BENCHMARKS = {"KR": "069500.KS", "US": "SPY"}
GROSS, NET = "GROSS_OF_ROUND_TRIP_COST", "NET_OF_ROUND_TRIP_COST"
COST_BASES = (GROSS, NET)
# Owner decision required (PR #265). SINGLE_COST_DEDUCTION is the only resolution this code can apply; anything else is a change.
EXPECTED_EXCESS_DEFINITION = "UNRESOLVED"
RESOLVED_DEFINITIONS = ("SINGLE_COST_DEDUCTION",)
UPSTREAM_PRODUCER = None


def edge_after_cost(value, cost, basis):
    """Benchmark-relative expected edge with the round-trip cost charged exactly once, or None if the basis is unknown."""
    if not (_num(value) and _num(cost)) or basis not in COST_BASES:
        return None
    return value - cost if basis == GROSS else value


def economic_input_contract():
    return {"expectedExcessDefinition": EXPECTED_EXCESS_DEFINITION, "upstreamProducer": UPSTREAM_PRODUCER,
            "gateWhenResolved": "BENCHMARK_RELATIVE_EDGE_AFTER_ONE_ROUND_TRIP_COST_GT_0", "costBases": list(COST_BASES),
            "registeredBenchmarks": dict(REGISTERED_BENCHMARKS)}


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != float("inf")


def clean_tickers(cands):
    """Non-empty stripped string tickers, de-duplicated, input order kept. Anything else is dropped, never coerced with str()."""
    if not isinstance(cands, list):
        return []
    out = []
    for t in cands:
        if isinstance(t, str) and t.strip() and t.strip() not in out:
            out.append(t.strip())
    return out


def qualify_a(a, region):
    """(eligible, reasons) for one region's Track A record. None / malformed input is unqualified, never a zero."""
    if not isinstance(a, dict):
        return False, ["A_INPUT_ABSENT"]
    reasons = [f"A_FIELD_MISSING:{k}" for k in A_REQUIRED if k not in a]
    if reasons:
        return False, reasons
    if EXPECTED_EXCESS_DEFINITION not in RESOLVED_DEFINITIONS:
        reasons.append("A_EXPECTED_EXCESS_DEFINITION_UNRESOLVED")
    if a["excessCostBasis"] not in COST_BASES:
        reasons.append("A_EXCESS_COST_BASIS_UNDECLARED")
    if a["benchmark"] != REGISTERED_BENCHMARKS.get(region):
        reasons.append("A_BENCHMARK_NOT_REGISTERED")
    if a["validated"] is not True:
        reasons.append("A_NOT_VALIDATED")
    if a["calibrated"] is not True:
        reasons.append("A_NOT_CALIBRATED")
    if not all(_num(a[k]) for k in ("expectedNetExcessPct", "uncertaintyPct", "roundTripCostPct")):
        reasons.append("A_NUMERIC_FIELD_UNAVAILABLE")
    elif a["uncertaintyPct"] <= 0:
        reasons.append("A_UNCERTAINTY_NOT_POSITIVE")
    elif a["roundTripCostPct"] < 0:
        reasons.append("A_ROUND_TRIP_COST_NEGATIVE")
    elif a["excessCostBasis"] in COST_BASES and not edge_after_cost(
            a["expectedNetExcessPct"], a["roundTripCostPct"], a["excessCostBasis"]) > 0:
        reasons.append("A_EDGE_NOT_ABOVE_ROUND_TRIP_COST")
    if not clean_tickers(a["candidates"]):
        reasons.append("A_NO_CANDIDATES")
    return not reasons, reasons


def compose(a_by_region=None, b=None, c=None):
    """Shadow composition. Always returns passive default unless Track A qualifies a region; never emits a weight."""
    a_by_region = a_by_region or {}
    regions, reasons, pool = {}, [], []
    for r in REGIONS:
        ok, why = qualify_a(a_by_region.get(r), r)
        regions[r] = {"aEligible": ok, "reasons": why}
        if ok:
            pool.extend((r, t) for t in clean_tickers(a_by_region[r]["candidates"]))
    # Cross-region cap is on the total number of names; the order is the input order, no score is invented here.
    candidates = [{"region": r, "ticker": t} for r, t in pool[:MAX_NAMES]]
    truncated = len(pool) > MAX_NAMES
    b_ctx = {"used": False, "role": "CONTEXT_ONLY",
             "observedState": b.get("adverse") if isinstance(b, dict) else None}
    c_ctx = {"used": False, "approved": bool(isinstance(c, dict) and c.get("ownerApprovedInterpretation") is True)}
    if c_ctx["approved"]:
        c_ctx["appliedOnceToFixedBook"] = True
    if candidates:
        status = "CANDIDATES_ELIGIBLE_FOR_SEPARATE_ECONOMIC_VALIDATION"
    else:
        status = "BLOCKED_NO_VALIDATED_SELECTION_INPUT"
        reasons.append("DEFAULT_PASSIVE_ETF_POLICY_RETAINED")
    out = {"studyId": STUDY, "evidenceClass": EVIDENCE_CLASS, "defaultPolicy": DEFAULT_POLICY, "status": status,
           "activeNames": [], "shadowCandidates": candidates, "candidatesTruncatedAtMax": truncated, "regions": regions,
           "b": b_ctx, "c": c_ctx, "reasons": reasons, "economicInputContract": economic_input_contract(),
           "productionAffected": False}
    assert_no_allocation(out)
    return out


def assert_no_allocation(obj):
    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if isinstance(k, str) and k.replace("_", "").lower() in _FORBIDDEN_NORMALISED:
                    raise ValueError("ALLOCATION_KEY_FORBIDDEN: " + k)
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(obj)
    if obj.get("activeNames") or obj.get("productionAffected") is not False:
        raise ValueError("SHADOW_CONTRACT_MUST_NOT_ACTIVATE_NAMES")
    json.dumps(obj, allow_nan=False)
    return True
