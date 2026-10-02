from dataclasses import asdict, replace
import ast
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

import pytest

from pipeline import industry_foundation as F
from scripts import audit_market_industry_stock_foundation as A

ROOT = Path(__file__).resolve().parents[1]
SHA = hashlib.sha256(b"invented source").hexdigest()
D = "2020-01-03"


def member(security="SYN_A", **kwargs):
    values = dict(security_id=security, ticker=security, region="KR", taxonomy_id="SYNTHETIC",
                  taxonomy_version="v1", industry_id="A", valid_from="2019-01-01", valid_to=None,
                  source_date="2019-01-01", release_date="2019-01-02", known_to=None,
                  source="synthetic://fixture", source_sha256=SHA,
                  evidence_kind="DATED_ASSIGNMENT", identity_provenance="synthetic identity")
    values.update(kwargs)
    return F.Membership(**values)


def cohort(rows=None, universe=("SYN_A", "SYN_B"), **kwargs):
    cfg = dict(region="KR", taxonomy_id="SYNTHETIC", taxonomy_version="v1",
               industry_id="A", minimum_constituents=2)
    cfg.update(kwargs)
    return F.freeze_cohort(rows or [member(), member("SYN_B")], universe, D, **cfg)


def obs(value, **kwargs):
    fields = dict(value=value, entry_date="2020-01-06", exit_date="2020-02-03",
                  currency="KRW", basis="ADJUSTED_INDEX_RETURN_PARTIAL_DISTRIBUTIONS",
                  source_sha256=SHA)
    fields.update(kwargs)
    return F.ReturnObservation(**fields)


def aggregate(c=None, observations=None, **kwargs):
    cfg = dict(weighting="EQUAL_WEIGHT", scope="SYNTHETIC", entry_date="2020-01-06",
               exit_date="2020-02-03", basis="ADJUSTED_INDEX_RETURN_PARTIAL_DISTRIBUTIONS", currency="KRW")
    cfg.update(kwargs)
    return F.aggregate_industry(c or cohort(), observations if observations is not None else {
        "SYN_A": obs(.2), "SYN_B": obs(-.1)}, **cfg)


def test_current_classification_never_backfills_or_masquerades_as_dated():
    with pytest.raises(ValueError, match="BACKFILL"):
        member(evidence_kind="CURRENT_SNAPSHOT_ONLY", source_date="2026-01-01", release_date="2026-01-01")
    row = member(evidence_kind="CURRENT_SNAPSHOT_ONLY", valid_from="2019-01-01")
    assert not row.visible(D)


@pytest.mark.parametrize("overrides", [
    {"release_date": D}, {"release_date": "2021-01-01"}, {"valid_from": "2021-01-01"},
    {"valid_to": D}, {"known_to": "2020-01-02"}])
def test_effective_and_publication_and_knowledge_boundaries(overrides):
    assert not member(**overrides).visible(D)


def test_date_only_supersession_and_future_effective_announcement():
    assert member(known_to=D).visible(D)
    assert member(valid_from=D).visible(D)
    assert not member(valid_from="2020-02-01").visible(D)
    assert member(valid_from="2020-02-01").visible("2020-02-01")


def test_retrospective_correction_preserves_original_known_group():
    old = member(known_to="2021-01-01")
    revised = member(industry_id="B", release_date="2021-01-01")
    query = dict(region="KR", taxonomy_id="SYNTHETIC", taxonomy_version="v1")
    assert F.membership_at([revised, old], "SYN_A", D, **query).industry_id == "A"
    assert F.membership_at([old, revised], "SYN_A", "2021-01-02", **query).industry_id == "B"


def test_ambiguous_visible_assignments_raise_and_versions_never_mix():
    with pytest.raises(ValueError, match="AMBIGUOUS"):
        cohort([member(), member(industry_id="B"), member("SYN_B")])
    c = cohort([member(), member("SYN_B", taxonomy_version="v2")])
    assert not c.ready and c.missing_classification == ("SYN_B",)


def test_ticker_reuse_is_not_security_identity():
    rows = [member(ticker="SAME"), member("SYN_B", ticker="SAME")]
    assert cohort(rows).security_ids == ("SYN_A", "SYN_B")
    assert not cohort(rows, universe=("SAME", "SYN_B")).ready


@pytest.mark.parametrize("overrides", [
    {"region": "EU"}, {"source_sha256": ""}, {"identity_provenance": ""},
    {"release_date": "2018-01-01"}, {"valid_to": "2019-01-01"},
    {"known_to": "2019-01-02"}, {"valid_from": "2019-02-30"},
    {"evidence_kind": "INFERRED_FROM_TODAY"}])
def test_invalid_provenance_and_intervals_refused(overrides):
    with pytest.raises(ValueError):
        member(**overrides)


def test_source_bytes_and_membership_identity_checks():
    F.verify_source(member(), b"invented source")
    with pytest.raises(ValueError, match="IDENTITY_CHANGED"):
        F.verify_source(member(), b"changed")
    rows = [member(), member("SYN_B")]
    assert F.membership_identity(rows) == F.membership_identity(rows[::-1])
    with pytest.raises(ValueError, match="DUPLICATE"):
        F.membership_identity(rows + [rows[0]])


def test_unclassified_full_universe_blocks_group_not_dropped():
    c = cohort(universe=("SYN_A", "SYN_B", "UNCLASSIFIED_EXIT"))
    value = aggregate(c)
    assert value["return"] is None and value["missingClassification"] == ["UNCLASSIFIED_EXIT"]
    assert value["status"] == "DATA_INSUFFICIENT"


def test_out_of_industry_names_are_not_constituents_and_entrants_wait():
    rows = [member(), member("SYN_B"), member("OTHER", industry_id="B"),
            member("ENTRANT", valid_from="2021-01-01")]
    c = cohort(rows, universe=("SYN_A", "SYN_B", "OTHER"))
    assert c.ready and c.security_ids == ("SYN_A", "SYN_B")
    assert aggregate(c, {"SYN_A": obs(.2), "SYN_B": obs(-.1), "OTHER": obs(999)})["return"] == pytest.approx(.05)
    assert "ENTRANT" not in c.security_ids


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), True, -1.01])
def test_missing_nonfinite_and_invalid_economic_value_is_never_zero(value):
    result = aggregate(observations={"SYN_A": obs(.2), "SYN_B": obs(value)})
    assert result["return"] is None and result["missingConstituents"] == ["SYN_B"]


def test_unresolved_terminated_security_stays_in_frozen_denominator():
    result = aggregate(observations={"SYN_A": obs(.2), "SYN_B": obs(-.1, terminal_status="UNRESOLVED")})
    assert result["return"] is None and result["constituentCount"] == 2
    missing = aggregate(observations={"SYN_A": obs(.2)})
    assert missing["return"] is None and missing["missingConstituents"] == ["SYN_B"]
    # Proven zero terminal wealth differs from unavailable terms.
    assert aggregate(observations={"SYN_A": obs(.2), "SYN_B": obs(-1, terminal_status="RESOLVED")})["return"] == pytest.approx(-.4)


def test_equal_weight_and_cap_weight_are_deterministic_and_distinct():
    fixture = json.loads((ROOT / "tests/fixtures/industry-foundation.synthetic.json").read_text())
    observations = {s: obs(v) for s, v in fixture["stockSimpleReturns"].items()}
    caps = {s: F.Capitalization(v, "2020-01-02", "2020-01-02", "KRW", SHA)
            for s, v in fixture["capitalizations"].items()}
    ew = aggregate(observations=observations)
    cw = aggregate(observations=observations, weighting="MARKET_CAP_WEIGHT", capitalizations=caps)
    assert ew["return"] == pytest.approx(.05)
    assert cw["return"] == pytest.approx(.125)
    assert cw == aggregate(cohort([member("SYN_B"), member()], universe=("SYN_B", "SYN_A")),
                          dict(reversed(list(observations.items()))), weighting="MARKET_CAP_WEIGHT", capitalizations=caps)


@pytest.mark.parametrize("bad", [
    F.Capitalization(None, "2020-01-02", "2020-01-02", "KRW", SHA),
    F.Capitalization(0, "2020-01-02", "2020-01-02", "KRW", SHA),
    F.Capitalization(1, "2020-02-01", "2020-02-01", "KRW", SHA),
    F.Capitalization(1, D, D, "KRW", SHA),
    F.Capitalization(1, "2020-01-02", "2020-01-02", "USD", SHA),
    F.Capitalization(1, "2020-01-02", "2020-01-02", "KRW", ""), None])
def test_cap_weights_require_signal_visible_positive_same_currency_inputs(bad):
    caps = {"SYN_A": F.Capitalization(3, "2020-01-02", "2020-01-02", "KRW", SHA), "SYN_B": bad}
    result = aggregate(weighting="MARKET_CAP_WEIGHT", capitalizations=caps)
    assert result["return"] is None and result["missingCaps"] == ["SYN_B"]


@pytest.mark.parametrize("kwargs", [
    {"entry_date": D}, {"exit_date": "2020-01-06"}, {"basis": "TOTAL_SHAREHOLDER_RETURN"}])
def test_bad_interval_or_partial_distributions_cannot_be_total_return(kwargs):
    if "basis" in kwargs:
        assert aggregate(**kwargs)["return"] is None
    else:
        with pytest.raises(ValueError, match="INTERVAL"):
            aggregate(**kwargs)


def test_explicit_price_and_complete_shareholder_bases():
    for basis, state in [("PRICE_RETURN", "EXCLUDED_PRICE_BASIS"), ("TOTAL_SHAREHOLDER_RETURN", "COMPLETE")]:
        observations = {"SYN_A": obs(.2, basis=basis, distribution_status=state),
                        "SYN_B": obs(-.1, basis=basis, distribution_status=state)}
        assert aggregate(observations=observations, basis=basis)["return"] == pytest.approx(.05)
    assert not obs(.2, basis="PRICE_RETURN").valid()


def test_decomposition_exact_and_signal_date_industry_is_frozen():
    rows = [member(known_to="2020-01-10"), member("SYN_A", industry_id="B", release_date="2020-01-10"), member("SYN_B")]
    c = cohort(rows)
    result = F.decompose(c, "SYN_A", obs(.2), aggregate(c), obs(.04), scope="SYNTHETIC")
    parts = result["components"]
    assert parts["industry_excess_return"] == pytest.approx(.01)
    assert parts["stock_within_industry_return"] == pytest.approx(.15)
    assert parts["industry_excess_return"] + parts["stock_within_industry_return"] == pytest.approx(parts["stock_market_relative_return"])
    assert result["industryId"] == "A"
    assert parts["market_return"] + parts["industry_excess_return"] + parts["stock_within_industry_return"] == pytest.approx(.2)


def test_decomposition_contract_identity_and_membership_are_required():
    c, industry = cohort(), aggregate()
    with pytest.raises(ValueError, match="NOT_IN_SIGNAL"):
        F.decompose(c, "OTHER", obs(.2), industry, obs(.04), scope="SYNTHETIC")
    with pytest.raises(ValueError, match="COHORT_IDENTITY"):
        F.decompose(replace(c, industry_id="B"), "SYN_A", obs(.2), industry, obs(.04), scope="SYNTHETIC")
    for kw in [{"currency": "USD"}, {"exit_date": "2020-02-04"}, {"basis": "PRICE_RETURN", "distribution_status": "EXCLUDED_PRICE_BASIS"}]:
        with pytest.raises(ValueError, match="CONTRACT_MISMATCH"):
            F.decompose(c, "SYN_A", obs(.2), industry, obs(.04, **kw), scope="SYNTHETIC")
    assert F.decompose(c, "SYN_A", obs(None), industry, obs(.04), scope="SYNTHETIC")["components"] is None


def test_compounding_does_not_make_simple_gaps_additive_across_time():
    rs, ri, rm = .2, .1, -.1
    qsi, qim, qsm = (1+rs)/(1+ri)-1, (1+ri)/(1+rm)-1, (1+rs)/(1+rm)-1
    assert qsi + qim != pytest.approx(qsm)
    assert qsi + qim + qsi*qim == pytest.approx(qsm)
    assert math.log((1+rs)/(1+ri)) + math.log((1+ri)/(1+rm)) == pytest.approx(math.log((1+rs)/(1+rm)))
    stock = (1+.2)*(1-.1)-1
    market = (1+.1)*(1+.1)-1
    naive = (1+.1)*(1-.2)-1
    assert naive != pytest.approx(stock-market)


def test_outcome_free_coverage_retains_gaps_and_emits_counts_not_taxonomy_choice():
    rows = [member(known_to="2020-01-10"), member("SYN_A", industry_id="B", release_date="2020-01-10"), member("SYN_B")]
    schedule = {D: ["SYN_A", "SYN_B", "MISSING"], "2020-02-01": ["SYN_A", "SYN_B"]}
    result = F.coverage_audit(rows, schedule, region="KR", taxonomy_id="SYNTHETIC", taxonomy_version="v1")
    assert result["status"] == "DATA_FOUNDATION_REQUIRED" and not result["taxonomyChosen"]
    assert result["dates"][0]["coverageFraction"] == 2/3
    assert result["dates"][0]["universeCount"] == 3
    assert result["dates"][1]["groupCounts"] == {"A": 1, "B": 1}
    assert result["observedAdjacentDateChanges"] == [{"date": "2020-02-01", "securityId": "SYN_A"}]
    assert F.coverage_audit([], {}, region="KR", taxonomy_id="SYNTHETIC", taxonomy_version="v1")["status"] == "DATA_FOUNDATION_REQUIRED"


def test_too_small_group_is_data_insufficient_and_minimum_is_explicit():
    assert aggregate(cohort(minimum_constituents=3))["return"] is None
    for value in [0, 1, True, 2.5]:
        with pytest.raises(ValueError, match="GROUP_SIZE"):
            cohort(minimum_constituents=value)


def test_synthetic_only_return_boundary():
    for scope in ["HISTORICAL", "PRODUCTION", None]:
        with pytest.raises(ValueError, match="NOT_AUTHORIZED"):
            aggregate(scope=scope)
        with pytest.raises(ValueError, match="NOT_AUTHORIZED"):
            F.decompose(cohort(), "SYN_A", obs(.2), aggregate(), obs(.04), scope=scope)


def test_row_json_schema_matches_runtime_and_forbids_extra_fields():
    schema = json.loads((ROOT / "research_specs/market-industry-stock-membership-v1.schema.json").read_text())
    assert set(schema["required"]) == set(asdict(member()))
    assert set(schema["properties"]) == set(asdict(member()))
    assert schema["additionalProperties"] is False


def test_metadata_audit_cannot_reach_return_or_outcome_engines(monkeypatch):
    def refuse(*args, **kwargs):
        pytest.fail("Metadata audit reached return primitives")
    monkeypatch.setattr(F, "aggregate_industry", refuse)
    monkeypatch.setattr(F, "decompose", refuse)
    result = A.audit()
    A.assert_audit_only(result)
    assert result["historicalClassificationCoverageFraction"] is None
    assert not result["historicalOutcomeComputed"] and not result["modelFitPerformed"]
    for file in [ROOT / "pipeline/industry_foundation.py", ROOT / "scripts/audit_market_industry_stock_foundation.py"]:
        tree = ast.parse(file.read_text())
        imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        assert not any(x and ("execution" in x or "model" in x or "evaluation" in x or "price" in x) for x in imports)
    workflow = (ROOT / ".github/workflows/market-industry-stock-foundation-v1.yml").read_text()
    assert "contents: read" in workflow and "--execute" not in workflow and "secrets" not in workflow
    assert "run: python scripts/audit_market_industry_stock_foundation.py" in workflow


def test_identity_audit_refuses_contract_tampering(tmp_path):
    spec_path = tmp_path / A.SPEC
    spec_path.parent.mkdir(parents=True)
    spec_path.write_bytes((ROOT / A.SPEC).read_bytes())
    spec_path.with_suffix(".sha256").write_text("0"*64)
    with pytest.raises(ValueError, match="SPEC_IDENTITY"):
        A.audit(tmp_path)
    spec_path.with_suffix(".sha256").write_bytes((ROOT / A.SPEC).with_suffix(".sha256").read_bytes())
    with pytest.raises((ValueError, FileNotFoundError)):
        A.audit(tmp_path)


def test_cli_has_no_historical_execute_flag_and_emits_only_metadata(tmp_path):
    output = tmp_path / "readiness.json"
    done = subprocess.run([sys.executable, str(ROOT / "scripts/audit_market_industry_stock_foundation.py"),
                           "--output", str(output)], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    result = json.loads(output.read_text())
    A.assert_audit_only(result)
    assert result["historicalMembershipRowsVerified"] == 0
    refuse = subprocess.run([sys.executable, str(ROOT / "scripts/audit_market_industry_stock_foundation.py"),
                             "--output", str(tmp_path / "other.json"), "--execute"], capture_output=True)
    assert refuse.returncode != 0 and not (tmp_path / "other.json").exists()
    overwrite = subprocess.run([sys.executable, str(ROOT / "scripts/audit_market_industry_stock_foundation.py"),
                                "--output", str(output)], capture_output=True)
    assert overwrite.returncode != 0


def test_output_firewall_rejects_hidden_outcome_or_portfolio_keys():
    for key in A.FORBIDDEN_OUTPUT_KEYS:
        with pytest.raises(ValueError, match="FORBIDDEN"):
            A.assert_audit_only({"nested": [{key: []}]})


def test_direct_cohort_cannot_bypass_identity_denominator_contract():
    c = cohort()
    for overrides in [{"security_ids": ("SYN_A", "SYN_A")},
                      {"security_ids": ("SYN_B", "SYN_A")},
                      {"missing_classification": ("SYN_A",)},
                      {"universe_sha256": ""}]:
        with pytest.raises(ValueError):
            replace(c, **overrides)


def test_stock_observation_must_match_the_aggregated_constituent_identity():
    with pytest.raises(ValueError, match="STOCK_OBSERVATION_IDENTITY"):
        F.decompose(cohort(), "SYN_A", obs(.3), aggregate(), obs(.04), scope="SYNTHETIC")


def test_membership_iterators_and_schedule_order_cannot_change_the_measurement():
    rows = [member(), member("SYN_B")]
    assert cohort(iter(rows)) == cohort(rows)
    cfg = dict(region="KR", taxonomy_id="SYNTHETIC", taxonomy_version="v1")
    a = F.coverage_audit(rows, {D: ["SYN_A", "SYN_B"]}, **cfg)
    b = F.coverage_audit(iter(rows), {D: ["SYN_B", "SYN_A"]}, **cfg)
    assert a == b


def test_us_has_separate_namespace_and_native_currency():
    rows = [member(region="US"), member("SYN_B", region="US")]
    c = cohort(rows, region="US")
    value = aggregate(c, {"SYN_A": obs(.2, currency="USD"), "SYN_B": obs(-.1, currency="USD")}, currency="USD")
    assert value["return"] == pytest.approx(.05)
    assert not cohort(rows).ready
