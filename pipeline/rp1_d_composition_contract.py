"""RP1 Track D — minimal SHADOW composition contract (eligibility check, no allocation).

Connects independently qualified outputs of Track A (stock selection), B (market-state context) and C (exposure rule) into one shadow
record. It is not an optimizer and produces no weight, order, recommendation or production decision. Default is the existing passive ETF
policy with zero active names; that default is restored whenever any gate below is not met. `docs/research-program/README.md` section D.

Gates (all must hold for A to be listed as a candidate for a SEPARATE economic validation, never for a position):
  - A: validated selection evidence, calibrated expected net excess return, uncertainty, and expected net excess above the round-trip cost
    (stock buy + stock sell + the passive-ETF sell that funds it). Missing is never zero.
  - B: contributes context only. No multiplier unless a conditional effect was validated AND shown incremental to C.
  - C: contributes a region rule only when an owner-approved interpretation exists, proven by a REGISTERED artifact digest (none is
    registered). A caller's `ownerApprovedInterpretation` boolean is ignored and flagged. Applied once to one fixed book, never on B.
  - Cap: at most 5 names in total. No ranking or allocation rule is registered, so more eligible names than the cap is BLOCKED; the
    contract never chooses which names, or which region, fill the cap. Within the cap names are listed by region then ticker.
  - Identifiers: exact KR `NNNNNN.KS` / US ticker strings; one malformed, padded or non-string entry voids the record.
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
import math
import re

STUDY = "rp1-d-composition-contract-v1"
EVIDENCE_CLASS = "SHADOW_CONTRACT_NO_ALLOCATION"
MAX_NAMES = 5
DEFAULT_POLICY = "EXISTING_PASSIVE_ETF_POLICY"
REGIONS = ("KR", "US")
FORBIDDEN_KEYS = ("weight", "weights", "order", "orders", "recommendation", "targetWeight", "notional", "shares",
                  "allocation", "allocations", "quantity", "qty", "positionSize", "buy", "sell")
_FORBIDDEN_NORMALISED = frozenset(k.lower() for k in FORBIDDEN_KEYS)
# A key CONTAINING one of these is an allocation or order field whatever its prefix ("krWeight", "target weights").
_FORBIDDEN_FRAGMENTS = ("weight", "allocation", "notional", "recommend", "quantity", "qty")
# Candidate identifiers in the form the repository's PIT universes use. Anything else is refused, never repaired.
TICKER_PATTERNS = {"KR": re.compile(r"[0-9]{6}\.KS"), "US": re.compile(r"[A-Z][A-Z0-9]{0,5}(?:[.-][A-Z]{1,2})?")}
# A percentage cost of 100% or more of the traded notional is outside the quantity's domain.
MAX_ROUND_TRIP_COST_PCT = 100.0
# No ranking or allocation rule exists that may choose WHICH names fill the 5-name cap (README sec.D, 04 sec.7). Until the owner
# registers one, more eligible names than the cap is BLOCKED rather than cut by input order or region order.
CAP_SELECTION_RULE = "UNRESOLVED"
# SHA-256 of owner-approval artifacts for a C (exposure-rule) interpretation. Empty: none is registered, so no caller can assert one.
OWNER_APPROVED_C_ARTIFACTS = frozenset()
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
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return False
    try:
        return math.isfinite(v)
    except OverflowError:
        # JSON integers can exceed the float domain used by edge_after_cost.
        # Refuse them before arithmetic, including while the definition is unresolved.
        return False


def inspect_tickers(cands, region=None):
    """(valid unique tickers in input order, invalid entries, duplicates removed). Never coerced with str(), never stripped:
    a padded, non-string or wrongly formatted identifier is reported as invalid, not repaired into a name."""
    if not isinstance(cands, list):
        return [], [cands], 0
    pattern = TICKER_PATTERNS.get(region)
    valid, invalid, duplicates = [], [], 0
    for t in cands:
        ok = isinstance(t, str) and t != "" and t == t.strip() and (pattern is None or pattern.fullmatch(t) is not None)
        if not ok:
            invalid.append(t)
        elif t in valid:
            duplicates += 1
        else:
            valid.append(t)
    return valid, invalid, duplicates


def clean_tickers(cands, region=None):
    """Valid unique tickers only; callers that need to know what was refused use inspect_tickers."""
    return inspect_tickers(cands, region)[0]


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
    elif a["roundTripCostPct"] >= MAX_ROUND_TRIP_COST_PCT:
        reasons.append("A_ROUND_TRIP_COST_OUT_OF_DOMAIN")
    elif a["excessCostBasis"] in COST_BASES and not edge_after_cost(
            a["expectedNetExcessPct"], a["roundTripCostPct"], a["excessCostBasis"]) > 0:
        reasons.append("A_EDGE_NOT_ABOVE_ROUND_TRIP_COST")
    valid, invalid, _ = inspect_tickers(a["candidates"], region)
    if invalid:
        reasons.append("A_CANDIDATE_IDENTIFIER_INVALID")  # one malformed entry voids the record; nothing is silently dropped
    elif not valid:
        reasons.append("A_NO_CANDIDATES")
    return not reasons, reasons


def c_approval(c):
    """Owner approval of a C interpretation comes only from a registered artifact digest, never from a caller's boolean."""
    if not isinstance(c, dict):
        return {"used": False, "approved": False, "reasons": []}
    reasons = []
    if "ownerApprovedInterpretation" in c:
        reasons.append("C_SELF_ASSERTED_APPROVAL_IGNORED")
    digest = c.get("ownerApprovalArtifactSha256")
    approved = isinstance(digest, str) and digest in OWNER_APPROVED_C_ARTIFACTS
    if not approved:
        reasons.append("C_OWNER_APPROVAL_PROVENANCE_UNRESOLVED")
    out = {"used": False, "approved": approved, "reasons": reasons}
    if approved:
        out["appliedOnceToFixedBook"] = True
    return out


def _observed_state(b):
    """B context is reported only as None/bool; any other caller content is dropped, never copied into the record."""
    v = b.get("adverse") if isinstance(b, dict) else None
    return v if v is None or isinstance(v, bool) else "UNRECOGNISED_INPUT_IGNORED"


def compose(a_by_region=None, b=None, c=None):
    """Shadow composition. Always returns passive default unless Track A qualifies a region; never emits a weight."""
    malformed_a = a_by_region is not None and not isinstance(a_by_region, dict)
    a_by_region = {} if malformed_a else (a_by_region or {})
    regions, reasons, pool = {}, [], {}
    if malformed_a:
        reasons.append("A_INPUT_NOT_A_MAPPING")
    for r in REGIONS:
        ok, why = qualify_a(a_by_region.get(r), r)
        regions[r] = {"aEligible": ok, "reasons": why}
        if ok:
            valid, _, duplicates = inspect_tickers(a_by_region[r]["candidates"], r)
            pool[r] = valid
            regions[r]["duplicatesRemoved"] = duplicates
    eligible_names = sum(len(v) for v in pool.values())
    # Listing order is region then ticker: it carries no rank, and neither input order nor region order can decide a name.
    listed = [{"region": r, "ticker": t} for r in REGIONS for t in sorted(pool.get(r, ()))]
    capped = eligible_names > MAX_NAMES
    if capped and CAP_SELECTION_RULE == "UNRESOLVED":
        candidates = []
        status = "BLOCKED_CAP_SELECTION_RULE_UNRESOLVED"
        reasons += ["MORE_ELIGIBLE_NAMES_THAN_CAP_WITHOUT_A_REGISTERED_SELECTION_RULE", "DEFAULT_PASSIVE_ETF_POLICY_RETAINED"]
    elif listed:
        candidates = listed
        status = "CANDIDATES_ELIGIBLE_FOR_SEPARATE_ECONOMIC_VALIDATION"
    else:
        candidates = []
        status = "BLOCKED_NO_VALIDATED_SELECTION_INPUT"
        reasons.append("DEFAULT_PASSIVE_ETF_POLICY_RETAINED")
    b_ctx = {"used": False, "role": "CONTEXT_ONLY",
             "observedState": _observed_state(b)}
    out = {"studyId": STUDY, "evidenceClass": EVIDENCE_CLASS, "defaultPolicy": DEFAULT_POLICY, "status": status,
           "activeNames": [], "shadowCandidates": candidates, "eligibleNameCount": eligible_names,
           "capSelectionRule": CAP_SELECTION_RULE, "candidatesListingIsNotARanking": True, "regions": regions,
           "b": b_ctx, "c": c_approval(c), "reasons": reasons, "economicInputContract": economic_input_contract(),
           "productionAffected": False}
    assert_no_allocation(out)
    return out


def _forbidden_key(k):
    if not isinstance(k, str):
        return False
    norm = re.sub(r"[\s_\-.]", "", k).lower()
    return norm in _FORBIDDEN_NORMALISED or any(f in norm for f in _FORBIDDEN_FRAGMENTS)


def assert_no_allocation(obj):
    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if _forbidden_key(k):
                    raise ValueError("ALLOCATION_KEY_FORBIDDEN: " + k)
                walk(v)
        elif isinstance(x, (list, tuple, set, frozenset)):
            for v in x:
                walk(v)
    walk(obj)
    if obj.get("activeNames") or obj.get("productionAffected") is not False:
        raise ValueError("SHADOW_CONTRACT_MUST_NOT_ACTIVATE_NAMES")
    json.dumps(obj, allow_nan=False)
    return True
