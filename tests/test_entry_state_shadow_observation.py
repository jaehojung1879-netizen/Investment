"""No-network regression tests for the pinned read-only shadow observation."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
SCRIPT = ROOT / "scripts/entry_state_shadow_observation.mjs"


def fixture():
    a = {"ticker": "A", "region": "KR", "sector": "Finance",
         "alphaPercentile": 90, "downsideVolPct": 20, "eligible": True,
         "entryStateMultiplier": 1, "convictionScore": 1.0,
         "evidenceCoverage": 1, "riskUnitFallback": False}
    b = {"ticker": "B", "region": "KR", "sector": "Health",
         "alphaPercentile": 90, "downsideVolPct": 20, "eligible": True,
         "entryStateMultiplier": .25, "convictionScore": .5,
         "evidenceCoverage": 1, "riskUnitFallback": False}
    config = {"kellyPortfolio": {
        "selection": {"targetNames": 2, "maxNamesPerRegion": 2,
                      "maxNamesPerSector": 2, "minAlphaPercentile": 66,
                      "convictionTiltRange": 1},
        "maxPositionWeight": .6, "maxSectorWeight": 1,
        "regionCaps": {"KR": 1}, "watchWeightMultiplier": .5,
        "waitForPullbackWeightMultiplier": .25}}
    s = {"targetNames": 2, "maxNamesPerRegion": 2,
         "maxNamesPerSector": 2, "minAlphaPercentile": 66,
         "consideredCount": 2, "eligibleCount": 2, "ranking": [a, b]}
    latest = {"schema": "CURRENT_CHAMPION_ARTIFACT_V1",
              "version": "current-champion-decisions-v1",
              "sourceArtifactSha256": "a" * 64,
              "generatedAt": "2026-10-31T05:44:37Z", "liveValidated": False,
              "regions": {"KR": {"status": "READY",
                                 "sourceObservedDate": "2026-10-30",
                                 "asOfDate": "2026-10-30",
                                 "receiptId": "test|KR|2026-10-30",
                                 "decisions": {"C2": {
                                     "appliedMinCashPct": 20,
                                     "selection": s,
                                     "weights": {"A": .6, "B": .2,
                                                 "069500.KS": .2}}}}}}
    weekly = {"generatedAt": latest["generatedAt"],
              "regions": {"KR": {"status": "PASSIVE_NO_DEFENSIBLE_EDGE",
                                 "asOfDate": "2026-10-30",
                                 "inputs": {"siteDataSha256": "a" * 64},
                                 "candidates": [
                                     {"ticker": "A", "sector": "Finance",
                                      "alphaPercentile": 90,
                                      "downsideVolPct": 20,
                                      "entryState": "ACCUMULATE_GRADUALLY",
                                      "edgeAvailable": False,
                                      "expectedNetAdvantagePct": None},
                                     {"ticker": "B", "sector": "Health",
                                      "alphaPercentile": 90,
                                      "downsideVolPct": 20,
                                      "entryState": "WAIT_FOR_PULLBACK",
                                      "edgeAvailable": False,
                                      "expectedNetAdvantagePct": None}]}}}
    return latest, weekly, config


def run(tmp_path, latest, weekly, cfg, *, output=False):
    if NODE is None:
        pytest.skip("Node unavailable")
    # Create an isolated REAL Git object to test that the runner authenticates
    # source bytes, not merely a caller-supplied reference or input hash.
    repo = tmp_path
    if not (repo / ".git").exists():
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
    paths = [
        repo / "ledger/research-strategies/current-champion-decisions-v1/latest.json",
        repo / "ledger/weekly-decisions/latest.json",
        repo / "config.json",
    ]
    for path, obj in zip(paths, (latest, weekly, cfg)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj))
    subprocess.run(["git", "-C", str(repo), "add", "ledger", "config.json"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=fixture",
                    "-c", "user.email=fixture@example.invalid", "commit",
                    "--allow-empty", "-q", "-m", "source snapshot"], check=True)
    sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                  text=True).strip()
    args = [NODE, str(SCRIPT), *(str(p) for p in paths), sha, sha]
    if output:
        args.append(str(repo / "observation.json"))
    return subprocess.run(args, text=True, capture_output=True,
                          check=False, cwd=repo)


def test_real_selection_v_weight_throttle_not_returns(tmp_path):
    a, b, cfg = fixture()
    out = run(tmp_path, a, b, cfg)
    assert out.returncode == 0, out.stderr
    observed = json.loads(out.stdout)
    kr = observed["regions"]["KR"]
    assert kr["legacyControlOnly"]["sameAsPublished"] is True
    assert kr["legacyControlOnly"]["stocks"] == {"A": .6, "B": .2}
    assert kr["scenarioStockCounts"] == [0, 1, 2, 3, 4, 5, 10]
    assert kr["currentPolicy"]["stockCount"] == 0
    assert kr["currentPolicy"]["benchmarkWeight"] == 1
    assert kr["researchScenarios"][0]["stateAtPositionWeight"]["stocks"] == {}
    assert kr["researchScenarios"][2]["stateAtPositionWeight"]["selected"] == ["B", "A"]
    assert kr["researchScenarios"][2]["stateAtPositionWeight"]["stocks"] == {"B": .15, "A": .2}
    assert kr["researchScenarios"][2]["stateAtPositionWeight"]["residual"] == .65
    assert kr["researchScenarios"][3]["status"] == "INSUFFICIENT_ELIGIBLE_NAMES"
    assert kr["cardinalityWinner"] is None
    assert kr["realizedReturn"] is None and kr["expectedAlpha"] is None
    assert observed["regions"]["US"]["status"] == "BLOCKED"
    # Owner correction (2026-11-01): no permanent combined KR+US maximum is imposed by research code.
    policy = observed["portfolioDPolicy"]
    assert policy["permanentCombinedMaximum"] is None and "feasibleCountPairs" not in policy
    assert policy["regionalScenariosAreNotSimultaneousCombinedAllocations"] is True
    assert kr["researchScenarios"][-1]["stockCount"] == 10
    assert kr["researchScenarios"][-1]["status"] == "INSUFFICIENT_ELIGIBLE_NAMES"
    assert observed["residualConvention"].startswith("ETF_NOT_CASH")


def test_unpublished_candidate_might_cross_cutoff_blocks(tmp_path):
    a, b, cfg = fixture()
    a["regions"]["KR"]["decisions"]["C2"]["selection"]["consideredCount"] = 3
    a["regions"]["KR"]["decisions"]["C2"]["selection"]["eligibleCount"] = 3
    b["regions"]["KR"]["candidates"].append({
        "ticker": "C", "sector": "Industry", "alphaPercentile": 100,
        "downsideVolPct": 10, "entryState": "WAIT_FOR_PULLBACK",
        "edgeAvailable": False, "expectedNetAdvantagePct": None})
    out = run(tmp_path, a, b, cfg)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout)["regions"]["KR"]["reason"] == (
        "TRUNCATED_RANKING_COULD_CHANGE_CONTROL")


def test_control_parity_failure_never_returns_alternative_weights(tmp_path):
    a, b, cfg = fixture()
    a["regions"]["KR"]["decisions"]["C2"]["weights"]["A"] = .5
    out = run(tmp_path, a, b, cfg)
    assert out.returncode == 0, out.stderr
    x = json.loads(out.stdout)["regions"]["KR"]
    assert x["reason"] == "ORIGINAL_CONTROL_RECONSTRUCTION_FAILED"
    assert x.get("researchScenarios") is None


def test_cross_generation_or_source_mismatch_refused(tmp_path):
    a, b, cfg = fixture()
    b["regions"]["KR"]["inputs"]["siteDataSha256"] = "b" * 64
    out = run(tmp_path, a, b, cfg)
    assert out.returncode == 0
    assert json.loads(out.stdout)["regions"]["KR"]["status"] == "BLOCKED"
    b["generatedAt"] = "2026-10-30T00:00:00Z"
    out = run(tmp_path, a, b, cfg)
    assert out.returncode != 0
    assert "DIFFERENT_GENERATION_CANNOT_PAIR" in out.stderr


def test_observation_write_is_create_only(tmp_path):
    a, b, cfg = fixture()
    first = run(tmp_path, a, b, cfg, output=True)
    assert first.returncode == 0, first.stderr
    content = (tmp_path / "observation.json").read_bytes()
    second = run(tmp_path, a, b, cfg, output=True)
    assert second.returncode != 0
    assert (tmp_path / "observation.json").read_bytes() == content


def test_five_names_are_allowed_without_becoming_a_forced_recommendation(tmp_path):
    a, b, cfg = fixture()
    region = a["regions"]["KR"]["decisions"]["C2"]
    for name, score, sector in [
        ("C", .4, "Energy"), ("D", .3, "Industry"), ("E", .2, "Utilities")
    ]:
        region["selection"]["ranking"].append({
            "ticker": name, "region": "KR", "sector": sector,
            "alphaPercentile": 90, "downsideVolPct": 20, "eligible": True,
            "entryStateMultiplier": 1, "convictionScore": score,
            "evidenceCoverage": 1, "riskUnitFallback": False
        })
        b["regions"]["KR"]["candidates"].append({
            "ticker": name, "sector": sector, "alphaPercentile": 90,
            "downsideVolPct": 20, "entryState": "ACCUMULATE_GRADUALLY",
            "edgeAvailable": False, "expectedNetAdvantagePct": None
        })
    region["selection"]["consideredCount"] = 5
    region["selection"]["eligibleCount"] = 5
    out = run(tmp_path, a, b, cfg)
    assert out.returncode == 0, out.stderr
    row = json.loads(out.stdout)["regions"]["KR"]
    assert row["legacyControlOnly"]["stockCount"] == 2
    assert row["researchScenarios"][5]["stockCount"] == 5
    assert len(row["researchScenarios"][5]["stateAtPositionWeight"]["stocks"]) == 5
    assert row["currentPolicy"]["stockCount"] == 0
    assert row["cardinalityWinner"] is None


def test_no_positive_edge_cannot_be_converted_to_three_or_five_stock_policy(tmp_path):
    a, b, cfg = fixture()
    b["regions"]["KR"]["status"] = "UNKNOWN"
    out = run(tmp_path, a, b, cfg)
    assert out.returncode == 0, out.stderr
    row = json.loads(out.stdout)["regions"]["KR"]
    assert row["currentPolicy"]["stockCount"] is None
    assert row["cardinalityWinner"] is None


def test_omitted_candidate_below_cutoff_does_not_crash(tmp_path):
    """Regression: the bounded check read an undefined `x` and threw ReferenceError on any omitted pool name."""
    a, b, cfg = fixture()
    a["regions"]["KR"]["decisions"]["C2"]["selection"]["consideredCount"] += 1
    b["regions"]["KR"]["candidates"].append({
        "ticker": "Z", "sector": "Energy", "alphaPercentile": 10, "downsideVolPct": 20,
        "entryState": "ACCUMULATE_GRADUALLY", "edgeAvailable": False, "expectedNetAdvantagePct": None})
    out = run(tmp_path, a, b, cfg)
    assert out.returncode == 0, out.stderr
    kr = json.loads(out.stdout)["regions"]["KR"]
    assert "ReferenceError" not in out.stderr
    audit = kr["researchScenarios"][1]["rankStateInSelection"]["candidateAudit"]
    assert {r["ticker"]: r["status"] for r in audit}["Z"] == "NOT_IN_PUBLISHED_RANKING_BOUNDED_BELOW_CUTOFF"
