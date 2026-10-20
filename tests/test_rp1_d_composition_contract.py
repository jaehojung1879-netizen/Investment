import pytest

from pipeline import rp1_d_composition_contract as D


def _a(**kw):
    base = {"validated": True, "calibrated": True, "expectedNetExcessPct": 5.0, "uncertaintyPct": 2.0, "roundTripCostPct": 1.0,
            "candidates": ["AAA", "BBB"]}
    base.update(kw)
    return base


def test_no_inputs_is_passive_default():
    o = D.compose()
    assert o["status"] == "BLOCKED_NO_VALIDATED_SELECTION_INPUT" and o["activeNames"] == [] and o["shadowCandidates"] == []
    assert o["defaultPolicy"] == D.DEFAULT_POLICY and o["productionAffected"] is False


@pytest.mark.parametrize("kw,reason", [({"validated": False}, "A_NOT_VALIDATED"), ({"calibrated": False}, "A_NOT_CALIBRATED"),
                                       ({"expectedNetExcessPct": 0.5}, "A_EDGE_NOT_ABOVE_ROUND_TRIP_COST"),
                                       ({"expectedNetExcessPct": None}, "A_NUMERIC_FIELD_UNAVAILABLE"),
                                       ({"expectedNetExcessPct": float("nan")}, "A_NUMERIC_FIELD_UNAVAILABLE"),
                                       ({"candidates": []}, "A_NO_CANDIDATES")])
def test_unqualified_a_falls_back(kw, reason):
    o = D.compose({"KR": _a(**kw)})
    assert reason in o["regions"]["KR"]["reasons"] and o["shadowCandidates"] == []


def test_missing_field_is_unqualified_not_zero():
    a = _a()
    del a["uncertaintyPct"]
    assert D.qualify_a(a, "KR") == (False, ["A_FIELD_MISSING:uncertaintyPct"])


def test_qualified_a_lists_candidates_without_weights():
    o = D.compose({"KR": _a(), "US": _a(candidates=["X", "Y", "Z", "W"])}, b={"adverse": True}, c={"ownerApprovedInterpretation": True})
    assert o["status"].startswith("CANDIDATES_ELIGIBLE") and len(o["shadowCandidates"]) == D.MAX_NAMES and o["candidatesTruncatedAtMax"]
    assert o["activeNames"] == [] and o["b"]["used"] is False and o["c"]["used"] is False
    assert {c["region"] for c in o["shadowCandidates"]} == {"KR", "US"}


def test_b_alone_never_creates_candidates():
    assert D.compose(b={"adverse": True})["shadowCandidates"] == []


def test_allocation_keys_are_refused():
    o = D.compose()
    o["b"]["targetWeight"] = 0.1
    with pytest.raises(ValueError, match="ALLOCATION_KEY_FORBIDDEN"):
        D.assert_no_allocation(o)
    o2 = D.compose()
    o2["activeNames"] = ["AAA"]
    with pytest.raises(ValueError):
        D.assert_no_allocation(o2)


def _h(**kw):
    base = {"validated": True, "calibrated": True, "expectedNetExcessPct": 5.0, "uncertaintyPct": 1.0,
            "roundTripCostPct": 1.0, "candidates": ["A"]}
    base.update(kw)
    return base


def test_duplicates_removed_and_malformed_tickers_dropped():
    out = D.compose({"KR": _h(candidates=["A", "A", " A ", None, "", 5, {"x": 1}, "  ", "B"])})
    assert [c["ticker"] for c in out["shadowCandidates"]] == ["A", "B"]


def test_only_malformed_candidates_is_unqualified():
    ok, why = D.qualify_a(_h(candidates=[None, "", 5]), "KR")
    assert not ok and "A_NO_CANDIDATES" in why


def test_nonpositive_uncertainty_and_negative_cost_rejected():
    assert "A_UNCERTAINTY_NOT_POSITIVE" in D.qualify_a(_h(uncertaintyPct=-1), "KR")[1]
    assert "A_UNCERTAINTY_NOT_POSITIVE" in D.qualify_a(_h(uncertaintyPct=0), "KR")[1]
    assert "A_ROUND_TRIP_COST_NEGATIVE" in D.qualify_a(_h(roundTripCostPct=-50), "KR")[1]


def test_allocation_key_scan_is_case_and_underscore_insensitive():
    import pytest
    for k in ("Weight", "target_weight", "ORDERS"):
        with pytest.raises(ValueError):
            D.assert_no_allocation({"activeNames": [], "productionAffected": False, "x": {k: 1}})
