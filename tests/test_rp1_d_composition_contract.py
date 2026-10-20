import pytest

from pipeline import rp1_d_composition_contract as D


def _a(region="KR", **kw):
    base = {"validated": True, "calibrated": True, "expectedNetExcessPct": 5.0, "uncertaintyPct": 2.0, "roundTripCostPct": 1.0,
            "candidates": ["AAA", "BBB"], "excessCostBasis": D.GROSS, "benchmark": D.REGISTERED_BENCHMARKS[region]}
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
    o = D.compose({"KR": _a(), "US": _a("US", candidates=["X", "Y", "Z", "W"])}, b={"adverse": True}, c={"ownerApprovedInterpretation": True})
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
            "roundTripCostPct": 1.0, "candidates": ["A"], "excessCostBasis": D.GROSS, "benchmark": "069500.KS"}
    base.update(kw)
    return base


def test_duplicates_removed_and_malformed_tickers_dropped(resolved):
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
