import pytest

from pipeline import rp1_d_composition_contract as D


KR2, US2 = ["005930.KS", "000660.KS"], ["AAPL", "MSFT"]


def _a(region="KR", **kw):
    base = {"validated": True, "calibrated": True, "expectedNetExcessPct": 5.0, "uncertaintyPct": 2.0, "roundTripCostPct": 1.0,
            "candidates": KR2 if region == "KR" else US2, "excessCostBasis": D.GROSS,
            "benchmark": D.REGISTERED_BENCHMARKS[region]}
    base.update(kw)
    return base


@pytest.fixture
def resolved(monkeypatch):
    """SYNTHETIC: exercise the eligible path as if the owner had resolved the definition. Production stays UNRESOLVED."""
    monkeypatch.setattr(D, "EXPECTED_EXCESS_DEFINITION", "SINGLE_COST_DEDUCTION")


def test_no_inputs_is_passive_default():
    o = D.compose()
    assert o["status"] == "BLOCKED_NO_VALIDATED_SELECTION_INPUT" and o["activeNames"] == [] and o["shadowCandidates"] == []
    assert o["defaultPolicy"] == D.DEFAULT_POLICY and o["productionAffected"] is False


@pytest.mark.parametrize("kw,reason", [({"validated": False}, "A_NOT_VALIDATED"), ({"calibrated": False}, "A_NOT_CALIBRATED"),
                                       ({"expectedNetExcessPct": 0.5}, "A_EDGE_NOT_ABOVE_ROUND_TRIP_COST"),
                                       ({"expectedNetExcessPct": None}, "A_NUMERIC_FIELD_UNAVAILABLE"),
                                       ({"expectedNetExcessPct": float("nan")}, "A_NUMERIC_FIELD_UNAVAILABLE"),
                                       ({"candidates": []}, "A_NO_CANDIDATES")])
def test_unqualified_a_falls_back(kw, reason, resolved):
    o = D.compose({"KR": _a(**kw)})
    assert reason in o["regions"]["KR"]["reasons"] and o["shadowCandidates"] == []


def test_missing_field_is_unqualified_not_zero():
    a = _a()
    del a["uncertaintyPct"]
    assert D.qualify_a(a, "KR") == (False, ["A_FIELD_MISSING:uncertaintyPct"])


def test_qualified_a_lists_candidates_without_weights(resolved):
    o = D.compose({"KR": _a(), "US": _a("US", candidates=["AAPL", "MSFT", "NVDA"])}, b={"adverse": True})
    assert o["status"].startswith("CANDIDATES_ELIGIBLE") and len(o["shadowCandidates"]) == D.MAX_NAMES
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
            "roundTripCostPct": 1.0, "candidates": ["005930.KS"], "excessCostBasis": D.GROSS, "benchmark": "069500.KS"}
    base.update(kw)
    return base


def test_duplicates_removed_and_counted(resolved):
    out = D.compose({"KR": _h(candidates=["005930.KS", "005930.KS", "000660.KS", "005930.KS"])})
    assert [c["ticker"] for c in out["shadowCandidates"]] == ["000660.KS", "005930.KS"]
    assert out["regions"]["KR"]["duplicatesRemoved"] == 2


@pytest.mark.parametrize("bad", [None, "", "  ", " 005930.KS", "005930.KS ", 5, 5.0, True, {"x": 1}, ["005930.KS"],
                                 "5930.KS", "005930", "005930.KQ", "005930.ks", "None"])
def test_one_malformed_kr_identifier_voids_the_record_and_is_never_repaired(bad, resolved):
    ok, why = D.qualify_a(_h(candidates=["000660.KS", bad]), "KR")
    assert not ok and "A_CANDIDATE_IDENTIFIER_INVALID" in why
    assert D.compose({"KR": _h(candidates=["000660.KS", bad])})["shadowCandidates"] == []


@pytest.mark.parametrize("bad", ["aapl", "AAPL ", "", "123", "TOOLONGNAME", "005930.KS", None])
def test_us_identifier_rules_are_region_specific(bad, resolved):
    rec = dict(_h(candidates=["AAPL", bad]), benchmark="SPY")
    assert "A_CANDIDATE_IDENTIFIER_INVALID" in D.qualify_a(rec, "US")[1]
    assert D.qualify_a(dict(_h(candidates=["AAPL", "BRK-B", "BF.B"]), benchmark="SPY"), "US")[0] is True


def test_non_list_candidates_are_invalid_not_iterated(resolved):
    for bad in ("005930.KS", ("005930.KS",), {"005930.KS"}, None):
        assert "A_CANDIDATE_IDENTIFIER_INVALID" in D.qualify_a(_h(candidates=bad), "KR")[1]
    assert "A_NO_CANDIDATES" in D.qualify_a(_h(candidates=[]), "KR")[1]


def test_nonpositive_uncertainty_and_negative_cost_rejected():
    assert "A_UNCERTAINTY_NOT_POSITIVE" in D.qualify_a(_h(uncertaintyPct=-1), "KR")[1]
    assert "A_UNCERTAINTY_NOT_POSITIVE" in D.qualify_a(_h(uncertaintyPct=0), "KR")[1]
    assert "A_ROUND_TRIP_COST_NEGATIVE" in D.qualify_a(_h(roundTripCostPct=-50), "KR")[1]


def test_allocation_key_scan_is_case_and_underscore_insensitive():
    import pytest
    for k in ("Weight", "target_weight", "ORDERS"):
        with pytest.raises(ValueError):
            D.assert_no_allocation({"activeNames": [], "productionAffected": False, "x": {k: 1}})


# ---- Economic input contract: gross / net / benchmark-relative / round trip ----
# G = E[R_i - R_b] (gross, benchmark-relative), C = round trip (stock buy+sell and the ETF sell; benchmark leg charged
# nothing), net N = G - C. Economic gate: G - C > 0 <=> N > 0. All values synthetic; none is an empirical expectation.

G, C = 0.8, 0.5
N = G - C


def test_production_definition_is_unresolved_and_blocks_every_record():
    assert D.EXPECTED_EXCESS_DEFINITION == "UNRESOLVED" and D.UPSTREAM_PRODUCER is None
    ok, why = D.qualify_a(_a(expectedNetExcessPct=99.0, roundTripCostPct=0.1), "KR")
    assert not ok and why == ["A_EXPECTED_EXCESS_DEFINITION_UNRESOLVED"]
    out = D.compose({"KR": _a(), "US": _a("US")})
    assert out["status"] == "BLOCKED_NO_VALIDATED_SELECTION_INPUT" and out["shadowCandidates"] == []
    assert out["economicInputContract"]["expectedExcessDefinition"] == "UNRESOLVED"
    assert out["economicInputContract"]["upstreamProducer"] is None


@pytest.mark.parametrize("value, basis, expected_edge", [(G, D.GROSS, N), (N, D.NET, N)])
def test_cost_is_charged_exactly_once_on_either_declared_basis(value, basis, expected_edge):
    assert D.edge_after_cost(value, C, basis) == pytest.approx(expected_edge)


def test_double_deduction_and_no_deduction_are_both_distinguishable():
    double = N - C        # a NET value run through "value - C": charged twice, G > 2C
    never = G             # a GROSS value tested against 0: charged never
    once = D.edge_after_cost(N, C, D.NET)
    assert double < 0 < once < never
    # Same economics, opposite verdicts under the two mistakes:
    assert not double > 0 and once > 0
    thin_gross = 0.3      # G < C: uneconomic
    assert thin_gross > 0 and not D.edge_after_cost(thin_gross, C, D.GROSS) > 0


@pytest.mark.parametrize("gross", [-1.0, 0.0, 0.2, 0.5, 0.50001, 0.9, 1.0, 2.0])
@pytest.mark.parametrize("cost", [0.0, 0.25, 0.5, 1.0])
def test_same_economics_same_verdict_whichever_basis_the_producer_uses(gross, cost):
    as_gross = D.edge_after_cost(gross, cost, D.GROSS)
    as_net = D.edge_after_cost(gross - cost, cost, D.NET)
    assert (as_gross > 0) == (as_net > 0)


@pytest.mark.parametrize("kw, reason", [({"excessCostBasis": None}, "A_EXCESS_COST_BASIS_UNDECLARED"),
                                        ({"excessCostBasis": "net"}, "A_EXCESS_COST_BASIS_UNDECLARED"),
                                        ({"benchmark": "^KS200"}, "A_BENCHMARK_NOT_REGISTERED"),
                                        ({"benchmark": "SPY"}, "A_BENCHMARK_NOT_REGISTERED")])
def test_undeclared_basis_or_wrong_benchmark_fails_closed(kw, reason, resolved):
    ok, why = D.qualify_a(_a(**kw), "KR")
    assert not ok and reason in why


def test_missing_basis_or_benchmark_is_a_missing_field():
    for k in ("excessCostBasis", "benchmark"):
        a = _a()
        del a[k]
        assert D.qualify_a(a, "KR") == (False, ["A_FIELD_MISSING:" + k])


def test_resolved_gate_admits_net_value_the_old_double_deduction_rejected(resolved):
    ok, _ = D.qualify_a(_a(expectedNetExcessPct=N, roundTripCostPct=C, excessCostBasis=D.NET), "KR")
    assert ok and not (N - C > 0)  # the pre-contract rule `value - cost > 0` would have rejected it
    assert D.qualify_a(_a(expectedNetExcessPct=0.3, roundTripCostPct=C, excessCostBasis=D.GROSS), "KR")[0] is False


def test_economic_contract_record_carries_no_allocation_or_outcome():
    out = D.compose()
    D.assert_no_allocation(out)
    assert set(out["economicInputContract"]) == {"expectedExcessDefinition", "upstreamProducer", "gateWhenResolved",
                                                 "costBases", "registeredBenchmarks"}


# ---- Second #265 audit round: cap, region order, approval provenance, nested keys ----

def _kr(n):
    return [f"{i:06d}.KS" for i in range(1, n + 1)]


def test_cost_at_or_above_100_pct_is_out_of_domain(resolved):
    for cost in (100.0, 150.0, 1e9):
        assert "A_ROUND_TRIP_COST_OUT_OF_DOMAIN" in D.qualify_a(_h(roundTripCostPct=cost, expectedNetExcessPct=1e12), "KR")[1]
    assert D.qualify_a(_h(roundTripCostPct=99.9, expectedNetExcessPct=200.0), "KR")[0] is True


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan"), True, "1.0", None])
def test_non_finite_or_non_numeric_uncertainty_and_cost_rejected(value, resolved):
    for field in ("uncertaintyPct", "roundTripCostPct"):
        assert "A_NUMERIC_FIELD_UNAVAILABLE" in D.qualify_a(_h(**{field: value}), "KR")[1]


def test_more_names_than_cap_is_blocked_not_cut_by_input_or_region_order(resolved):
    # Pre-fix: KR 5 + US 1 returned 5 KR names and no US name, because the pool was cut in input order.
    out = D.compose({"KR": _h(candidates=_kr(5)), "US": dict(_h(candidates=["AAPL"]), benchmark="SPY")})
    assert out["status"] == "BLOCKED_CAP_SELECTION_RULE_UNRESOLVED" and out["shadowCandidates"] == []
    assert out["eligibleNameCount"] == 6 and out["capSelectionRule"] == "UNRESOLVED"
    assert "DEFAULT_PASSIVE_ETF_POLICY_RETAINED" in out["reasons"]
    one_region = D.compose({"KR": _h(candidates=_kr(6))})
    assert one_region["status"] == "BLOCKED_CAP_SELECTION_RULE_UNRESOLVED" and one_region["shadowCandidates"] == []


def test_listing_within_cap_is_independent_of_input_and_region_order(resolved):
    kr, us = _h(candidates=["000660.KS", "005930.KS"]), dict(_h(candidates=["MSFT", "AAPL", "NVDA"]), benchmark="SPY")
    first = D.compose({"KR": kr, "US": us})
    swapped = D.compose({"US": dict(us, candidates=list(reversed(us["candidates"]))),
                         "KR": dict(kr, candidates=list(reversed(kr["candidates"])))})
    assert first["shadowCandidates"] == swapped["shadowCandidates"]
    assert [c["ticker"] for c in first["shadowCandidates"]] == ["000660.KS", "005930.KS", "AAPL", "MSFT", "NVDA"]
    assert first["candidatesListingIsNotARanking"] is True


@pytest.mark.parametrize("c", [{"ownerApprovedInterpretation": True}, {"ownerApprovedInterpretation": "yes"},
                               {"ownerApprovedInterpretation": True, "ownerApprovalArtifactSha256": "0" * 64},
                               {"ownerApprovalArtifactSha256": "f" * 64}])
def test_caller_cannot_assert_owner_approval(c):
    out = D.compose(c=c)["c"]
    assert out["approved"] is False and "appliedOnceToFixedBook" not in out
    assert "C_OWNER_APPROVAL_PROVENANCE_UNRESOLVED" in out["reasons"]
    if "ownerApprovedInterpretation" in c:
        assert "C_SELF_ASSERTED_APPROVAL_IGNORED" in out["reasons"]


def test_only_a_registered_artifact_digest_approves_c(monkeypatch):
    digest = "a" * 64
    monkeypatch.setattr(D, "OWNER_APPROVED_C_ARTIFACTS", frozenset({digest}))  # SYNTHETIC registry
    assert D.compose(c={"ownerApprovalArtifactSha256": digest})["c"]["approved"] is True
    assert D.OWNER_APPROVED_C_ARTIFACTS == frozenset({digest})
    monkeypatch.undo()
    assert D.OWNER_APPROVED_C_ARTIFACTS == frozenset()


@pytest.mark.parametrize("payload", [{"x": ({"weight": 1},)}, {"x": {"kr-weight": 1}}, {"x": {"allocation": 1}},
                                     {"x": {"Target Weights": 1}}, {"x": [{"qty": 3}]}, {"x": {frozenset(): 1, "positionSize": 2}},
                                     {"x": [[{"deep": {"KRW_Notional": 1}}]]}, {"x": {"Buy": 1}}, {"x": {"order.qty": 1}},
                                     {"x": {"targetAllocationPct": 0.2}}])
def test_nested_allocation_and_order_fields_are_refused(payload):
    with pytest.raises(ValueError, match="ALLOCATION_KEY_FORBIDDEN"):
        D.assert_no_allocation({"activeNames": [], "productionAffected": False, **payload})


def test_scan_allows_the_contracts_own_keys():
    for out in (D.compose(), D.compose(c={"ownerApprovedInterpretation": True}), D.compose(b={"adverse": False})):
        assert D.assert_no_allocation(out) is True


def test_unicode_digits_are_not_a_kr_identifier():
    assert D.inspect_tickers(["٠٠٥٩٣٠.KS"], "KR")[0] == []
    assert D.inspect_tickers(["005930.KS"], "KR")[0] == ["005930.KS"]


@pytest.mark.parametrize("bad", ["x", [], 5, ("a",)])
def test_non_mapping_a_input_fails_closed(bad):
    out = D.compose(a_by_region=bad)
    assert out["shadowCandidates"] == [] and out["activeNames"] == []
    assert "A_INPUT_NOT_A_MAPPING" in out["reasons"]


@pytest.mark.parametrize("adv", [{"weight": 1}, float("nan"), {1, 2}, "free text"])
def test_untrusted_b_content_is_not_copied_or_fatal(adv):
    out = D.compose(b={"adverse": adv})
    assert out["b"]["observedState"] == "UNRECOGNISED_INPUT_IGNORED"
