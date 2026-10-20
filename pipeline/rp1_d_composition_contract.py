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
A_REQUIRED = ("validated", "calibrated", "expectedNetExcessPct", "uncertaintyPct", "roundTripCostPct", "candidates")


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
    elif a["expectedNetExcessPct"] - a["roundTripCostPct"] <= 0:
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
           "b": b_ctx, "c": c_ctx, "reasons": reasons, "productionAffected": False}
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
