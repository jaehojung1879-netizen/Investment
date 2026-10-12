"""Current CHAMPION policy fidelity, immutable observations and independent regions."""
import gzip
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from pipeline import current_champion_decisions as C
from pipeline import kelly_portfolio as K
from pipeline import weekly_publish as P

ROOT = Path(__file__).resolve().parents[1]


def source():
    """Invented schema fixture only; no real current recommendation or return."""
    def candidate(ticker, region, rank, risk):
        return {"ticker": ticker, "region": region, "sector": ticker,
                "alphaPercentile": rank, "evidenceCoverage": .9,
                "longTermResearchView": "POSITIVE", "risk": {"downsideVolPct": risk},
                "entry": {"entryState": "ACCUMULATE_GRADUALLY"},
                "factorPercentiles": {"momentum": rank, "lowvol": 80}}
    kr = [candidate("SYN_KR_"+str(i), "KR", 96-i*4, 12+i*7) for i in range(5)]
    us = [candidate("SYN_US_"+str(i), "US", 95-i*3, 15+i*4) for i in range(5)]
    return {"generatedAt": "2026-10-12T00:00:00Z", "dataMode": "live",
            "provenance": {"buildCommitSha": "a"*40}, "recommendationsBlocked": False,
            "longTerm": {"weightsWithheld": False, "regions": {"KR": {"picks": kr}, "US": {"picks": us}}},
            "indices": [{"symbol": "^KS11", "asOf": "2026-10-08", "freshnessStatus": "CURRENT"},
                        {"symbol": "^GSPC", "asOf": "2026-10-09", "freshnessStatus": "CURRENT"}],
            "details": {r["ticker"]: {"asOf": "2026-10-08" if r["region"] == "KR" else "2026-10-09"}
                        for r in kr+us},
            "macroRegime": {"regime": "Reflation", "confidence": .8,
                            "riskBudget": {"equityRangePct": [30, 60]}}, "names": {}}


def test_original_engine_non_equal_sizing_and_exact_c2_parity():
    site = source()
    result = C.build(site, "a"*64)
    cfg = C.methodology()
    for region, row in result["regions"].items():
        assert row["status"] == "READY"
        a, b = row["decisions"]["C1"], row["decisions"]["C2"]
        original = K.selection_and_baseline(site["longTerm"]["regions"][region]["picks"], cfg, site["macroRegime"])
        assert a["stockWeights"] == original["weights"] == b["stockWeights"]
        assert a["holdings"] == b["holdings"]
        assert a["stockCount"] == 3  # Original maxNamesPerRegion remains binding.
        assert len(set(a["stockWeights"].values())) > 1
        assert all(w != .15 for w in a["stockWeights"].values())
        assert a["weights"]["CASH"] == b["weights"]["SPY" if region == "US" else "069500.KS"]
        assert sum(a["weights"].values()) == pytest.approx(1)
        assert sum(b["weights"].values()) == pytest.approx(1)
        assert row["receipt"]["liveValidated"] is False
        assert row["receipt"]["cadence"] != "21_SESSION_ANCHORS_NOT_WEEKLY"


def test_region_independence_and_no_combined_kelly_or_13f_dependency():
    site = source()
    original = C.build(site, "a"*64)["regions"]["KR"]
    site["longTerm"]["regions"]["US"]["picks"] = []
    site["modelPortfolio"] = {"finalWeights": {"SYN_KR_0": .99}, "cashPct": 1}
    site["institutionalHoldings13F"] = {"managers": [{"shares": 99999}]}
    site["nationalPensionService"] = {"equityWeightPct": 99}
    assert C.build(site, "a"*64)["regions"]["KR"] == original


@pytest.mark.parametrize("change,reason", [
    (lambda s: s.update(dataMode="synthetic"), "UNSAFE_OR_NON_LIVE_SOURCE"),
    (lambda s: s.update(stale=True), "UNSAFE_OR_NON_LIVE_SOURCE"),
    (lambda s: s.update(meta={"syntheticData": True}), "UNSAFE_OR_NON_LIVE_SOURCE"),
    (lambda s: s["macroRegime"].update(confidence=None), "MACRO_RISK_CONTEXT_MISSING"),
    (lambda s: s["macroRegime"]["riskBudget"].update(equityRangePct=[70, 30]), "MACRO_RISK_CONTEXT_MISSING"),
    (lambda s: s.update(recommendationsBlocked=True), "UNSAFE_OR_NON_LIVE_SOURCE"),
    (lambda s: s["longTerm"].update(weightsWithheld=True), "LONG_TERM_INPUTS_WITHHELD"),
    (lambda s: s["longTerm"]["regions"].pop("KR"), "REGIONAL_CHAMPION_CANDIDATE_POOL_MISSING"),
    (lambda s: s["longTerm"]["regions"]["KR"].update(picks=[]), "REGIONAL_CHAMPION_CANDIDATE_POOL_EMPTY"),
    (lambda s: s["indices"][0].update(asOf="2026-09-30"), "REGIONAL_INDEX_NOT_CURRENT"),
    (lambda s: s["indices"][0].update(asOf="2026-10-12"), "REGIONAL_INDEX_NOT_CURRENT"),
    (lambda s: s["details"]["SYN_KR_0"].update(asOf="2026-10-07"), "CANDIDATE_SESSION_NOT_CURRENT"),
    (lambda s: s["longTerm"]["regions"]["KR"]["picks"][0]["risk"].clear(), "INCOMPLETE_CANDIDATE"),
    (lambda s: s["longTerm"]["regions"]["KR"]["picks"][0].update(region="US"), "INCOMPLETE_CANDIDATE"),
    (lambda s: s.update(macroRegime=None), "MACRO_RISK_CONTEXT_MISSING"),
])
def test_no_phantom_current_holdings(change, reason):
    site = source()
    change(site)
    row = C.build(site, "a"*64)["regions"]["KR"]
    assert row["status"] == "BLOCKED" and row["decisions"] == {}
    assert any(code.startswith(reason) for code in row["reasonCodes"])


def test_invalid_us_session_does_not_block_kr():
    site = source()
    site["indices"][1]["asOf"] = "bad date"
    result = C.build(site, "a"*64)
    assert result["regions"]["KR"]["status"] == "READY"
    assert result["regions"]["US"]["status"] == "BLOCKED"


def test_missing_is_not_zero_and_zero_eligible_is_valid_cash_or_etf():
    site = source()
    for c in site["longTerm"]["regions"]["KR"]["picks"]:
        c["alphaPercentile"] = 30
    row = C.build(site, "a"*64)["regions"]["KR"]
    assert row["decisions"]["C1"]["weights"] == {"CASH": 1.0}
    assert row["decisions"]["C2"]["weights"] == {"069500.KS": 1.0}
    assert row["decisions"]["C1"]["stockCount"] == 0


def test_append_only_current_observations_and_same_session_refusal(tmp_path):
    site = source()
    C.publish(site, "a"*64, tmp_path)
    before = (tmp_path/"receipts.jsonl").read_bytes()
    assert C.publish(site, "b"*64, tmp_path)["regions"]["KR"]["status"] == "READY"
    assert (tmp_path/"receipts.jsonl").read_bytes() == before
    site["longTerm"]["regions"]["KR"]["picks"][0]["alphaPercentile"] = 99
    row = C.publish(site, "c"*64, tmp_path)["regions"]["KR"]
    assert row["status"] == "BLOCKED" and row["decisions"] == {}
    assert row["reasonCodes"] == ["CONFLICTING_SAME_SESSION_INPUT"]
    assert (tmp_path/"receipts.jsonl").read_bytes() == before
    site["generatedAt"] = "2026-10-13T00:00:00Z"
    site["indices"][0]["asOf"] = "2026-10-12"
    site["indices"][1]["asOf"] = "2026-10-12"
    for r in site["details"].values():
        r["asOf"] = "2026-10-12"
    C.publish(site, "d"*64, tmp_path)
    after = (tmp_path/"receipts.jsonl").read_bytes()
    assert after.startswith(before) and len(after) > len(before)


def test_tampered_history_refused(tmp_path):
    C.publish(source(), "a"*64, tmp_path)
    path = tmp_path/"receipts.jsonl"
    rows = path.read_text().splitlines()
    row = json.loads(rows[0]); row["decisions"]["C1"]["stockWeights"] = {}
    path.write_text(json.dumps(row)+'\n'+'\n'.join(rows[1:])+'\n')
    with pytest.raises(ValueError, match="INVALID_RESEARCH_RECEIPT_HISTORY"):
        C.publish(source(), "b"*64, tmp_path)


def test_sealed_selected_anchor_sizing_and_scores_without_any_return_calculation():
    raw = (ROOT/"docs/results/regional-standalone-paths.json.gz").read_bytes()
    frozen = json.loads(gzip.decompress(raw))
    for region in ("KR", "US"):
        for index in (0, 77, 154):
            anchor = frozen["regional"][region][index]
            # The sealed selected set proves POSITIVE eligibility. It is not a
            # reconstruction of the complete historical candidate pool.
            candidates = [{**{k: r.get(k) for k in (
                            "ticker", "region", "sector", "alphaPercentile", "evidenceCoverage", "entryState")},
                           "longTermResearchView": "POSITIVE",
                           "risk": {"downsideVolPct": r["downsideVolPct"]}}
                          for r in anchor["selected"]]
            got = C.allocation(region, candidates, C.methodology(), {"regime": anchor["macroRegime"]})["C1"]
            assert got["stockWeights"] == anchor["weights"]
            assert got["residualWeightPct"] == anchor["cashPct"]
            assert {r["ticker"]: r["convictionScore"] for r in got["holdings"]} == {
                r["ticker"]: r["convictionScore"] for r in anchor["selected"]}
    assert hashlib.sha256(raw).hexdigest() == "7a09751f99f5d892821cac6bbb4f28359049d58364cb40db1814fac4f93210cb"


def test_original_p1_bytes_unchanged_and_research_namespace_is_staged(tmp_path):
    site = source()
    # Available input with no supported edge: legitimate original P1 passive
    # receipts, without fitting or inventing a return estimate.
    site["historicalValidation"] = {"alphaCalibration": {"available": True, "regions": {}}}
    root = tmp_path/"ledger"
    weekly = root/"weekly-decisions"
    weekly.mkdir(parents=True)
    site_file = tmp_path/"site.json"; site_file.write_text(json.dumps(site))
    # The official path is exercised with its existing outcome-free history
    # adapter mocked here, never dispatching a replay or touching live ledgers.
    with patch.object(P.H, "build_history", return_value={}):
        assert P.main([str(site_file), str(weekly/"receipts.jsonl"), str(tmp_path/"latest.json"),
                       str(tmp_path/"receipts.jsonl"), str(tmp_path/"status.json")]) == 0
    official = (tmp_path/"receipts.jsonl").read_bytes()
    assert len(official.splitlines()) == 2
    # A standalone call has precisely the same official output and no implicit
    # research path, proving that the hook doesn't alter P1 decisions/digests.
    with patch.object(P.H, "build_history", return_value={}):
        assert P.main([str(site_file), str(tmp_path/"standalone-in.jsonl"), str(tmp_path/"second.json"),
                       str(tmp_path/"second-receipts.jsonl")]) == 0
    assert (tmp_path/"second-receipts.jsonl").read_bytes() == official
    assert (tmp_path/"second.json").read_bytes() == (tmp_path/"latest.json").read_bytes()
    assert (root/"research-strategies"/C.VERSION/"latest.json").exists()
    workflow = (ROOT/".github/workflows/ledger.yml").read_text()
    assert "git add ledger" in workflow


def test_research_publication_failure_preserves_official_p1(tmp_path):
    site = source()
    site["historicalValidation"] = {"alphaCalibration": {"available": True, "regions": {}}}
    site_file = tmp_path/"site.json"; site_file.write_text(json.dumps(site))
    weekly = tmp_path/"ledger/weekly-decisions"; weekly.mkdir(parents=True)
    with patch.object(P.H, "build_history", return_value={}), patch.object(C, "publish", side_effect=OSError("fixture")):
        assert P.main([str(site_file), str(weekly/"receipts.jsonl"), str(tmp_path/"latest.json"),
                       str(tmp_path/"receipts.jsonl"), str(tmp_path/"status.json")]) == 0
    assert json.loads((tmp_path/"status.json").read_text())["status"] == "PUBLISHED"
    assert len((tmp_path/"receipts.jsonl").read_text().splitlines()) == 2
    status = tmp_path/"ledger/research-strategies"/C.VERSION/"publication-status.json"
    assert json.loads(status.read_text())["status"] == "REFUSED"
