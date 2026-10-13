"""US H63 supplemental calibration (150-244 names per date): the frozen protocol, its inheritance from the parent, the verdict rule.

The expensive Monte Carlo is NOT run here (see scripts/run_us_h63_supplemental_calibration.py). These tests pin what can be pinned
cheaply: the protocol is byte-identical to its builder, the parent calibration is untouched, only permitted keys differ, the cell
grid covers the geometry it claims, the verdict cannot PASS around an INCONCLUSIVE or missing cell, replicates are reproducible
from their seed key, nothing here can read market data, and a committed result (if present) obeys its own frozen rule.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import alpha_inference_mc_decision as mc        # noqa: E402
from pipeline import us_h63_supplemental_calibration as S     # noqa: E402

FROZEN_SUPPLEMENT_SHA = "a354ed0fed40b3c752cef3d20efacb6df1190979421e10b956826b1f0f41b3d5"
SUPPLEMENT = json.loads(S.PROTOCOL_PATH.read_bytes())


def test_protocol_is_frozen_and_equals_its_builder():
    assert hashlib.sha256(S.PROTOCOL_PATH.read_bytes()).hexdigest() == FROZEN_SUPPLEMENT_SHA
    assert json.loads(json.dumps(S.build_protocol())) == SUPPLEMENT
    assert SUPPLEMENT["status"] == "FROZEN_BEFORE_ANY_REPLICATE" and SUPPLEMENT["outcomeFree"] is True


def test_parent_calibration_is_untouched():
    parent = S.verify_parent()
    assert parent["status"] == "FROZEN_BEFORE_ANY_REPLICATE"
    assert S.sha256_file(S.PARENT_RESULT) == S.PARENT_RESULT_SHA256
    assert json.loads(S.PARENT_RESULT.read_bytes())["p3Status"] == "PASS"


def test_parent_change_is_refused(monkeypatch, tmp_path):
    altered = tmp_path / "parent.json"
    altered.write_bytes(S.PARENT_PROTOCOL.read_bytes() + b" ")
    monkeypatch.setattr(S, "PARENT_PROTOCOL", altered)
    with pytest.raises(RuntimeError, match="PARENT_CALIBRATION_CHANGED"):
        S.verify_parent()


def test_only_permitted_keys_differ_from_the_parent():
    parent = S.verify_parent()
    eff = S.effective_protocol(SUPPLEMENT)
    changed = set(S.semantic_differences(parent, eff))
    assert changed <= S.PERMITTED_DIFFERENCES
    for key in ("methods", "acceptance", "geometry", "baseReturns", "inferentialTarget", "replicates"):
        assert eff[key] == parent[key], key
    assert eff["methods"]["snCriticalValue"] == 28.31 and eff["seed"] != parent["seed"]
    assert eff["replicates"] == 2000 and eff["sampleLengths"]["weeks"] == [260, 700]


def test_a_changed_frozen_rule_is_refused():
    for mutate, match in ((lambda d: d["monteCarloDecision"].__setitem__("passSideOneSidedAlpha", 0.05), "monteCarloDecision"),
                          (lambda d: d.__setitem__("replicates", 500), "replicates"),
                          (lambda d: d["dgps"][0].__setitem__("innovation", "STUDENT_T"), "dgps")):
        bad = copy.deepcopy(SUPPLEMENT)
        mutate(bad)
        with pytest.raises(RuntimeError, match="SUPPLEMENT_CHANGED_FROZEN_PARENT_KEY: " + match):
            S.effective_protocol(bad)
    reused = copy.deepcopy(SUPPLEMENT)
    reused["seed"] = S.verify_parent()["seed"]
    with pytest.raises(RuntimeError, match="SUPPLEMENT_REUSES_PARENT_SEED"):
        S.effective_protocol(reused)


def test_cell_grid_covers_the_range_the_parent_did_not():
    parent = S.verify_parent()
    dgps = SUPPLEMENT["dgps"]
    gating = [d["name"] for d in parent["dgps"] if d["gating"]]
    assert len(dgps) == len(gating) * len(S.TARGET_AVAILABLE_NAMES) == 15
    assert {d["parentDgp"] for d in dgps} == set(gating)
    assert all(d["gating"] for d in dgps)
    targets = sorted({d["targetAvailableNames"] for d in dgps})
    assert targets == [150, 200, 244]
    geometry = SUPPLEMENT["historicalGeometry"]
    assert min(targets) == geometry["protocolFloorNamesPerDate"] and max(targets) == geometry["parentMinimumNamesPerDate"] - 1
    assert geometry["definedDatesBelowParentMinimum"] == 163
    for d in dgps:        # the universe is the only structural override besides the name
        base = next(p for p in parent["dgps"] if p["name"] == d["parentDgp"])
        keep = {k: v for k, v in d.items() if k not in ("name", "parentDgp", "targetAvailableNames", "universe")}
        assert keep == {k: v for k, v in base.items() if k not in ("name", "universe")}
        assert abs(d["universe"] * (1 - d["missingRate"]) - d["targetAvailableNames"]) < 0.5 + 1e-9


def test_decision_count_matches_the_cell_list():
    expected = len(SUPPLEMENT["dgps"]) * len(SUPPLEMENT["sampleLengths"]["weeks"]) * 4
    assert SUPPLEMENT["monteCarloDecision"]["failSideDecisionCount"] == expected == 120


def _cell(state=mc.PASS, holds=True, name="X"):
    return {"dgp": name, "weeks": 260, "primaryState": state, "geometry": {"holds": holds}}


def test_verdict_cannot_pass_around_an_inconclusive_missing_or_misshapen_cell():
    ok = [_cell(name=str(i)) for i in range(4)]
    assert S.verdict(ok, 4)["supplementStatus"] == "SUPPLEMENT_PASS"
    for bad in ([*ok[:3], _cell(mc.INCONCLUSIVE)], [*ok[:3], _cell(mc.FAIL)], ok[:3], [*ok[:3], _cell(holds=False)]):
        v = S.verdict(bad, 4)
        assert v["supplementStatus"] == "SUPPLEMENT_BLOCKED" and v["onBlocked"].startswith("STOP")


def test_geometry_summary_flags_a_miss():
    assert S.geometry_summary([{"mean": 150.2, "min": 140, "max": 160}], 150)["holds"] is True
    assert S.geometry_summary([{"mean": 160.0, "min": 150, "max": 170}], 150)["holds"] is False


def _tiny(index_name="BASE__N150", universe=40):
    eff = S.effective_protocol(SUPPLEMENT)
    eff = copy.deepcopy(eff)
    i = next(k for k, d in enumerate(eff["dgps"]) if d["name"] == index_name)
    eff["dgps"][i]["universe"] = universe
    return eff, i


def test_replicate_is_reproducible_from_its_seed_key_alone():
    eff, i = _tiny()
    a = S.replicate_job((eff, i, 40, 3))
    b = S.replicate_job((eff, i, 40, 3))
    c = S.replicate_job((eff, i, 40, 4))
    assert a == b and a != c
    assert a["CT_SN"] is not None and a["CT_SN"]["lower"] <= a["CT_SN"]["upper"]


def test_geometry_check_streams_never_overlap_scored_replicates():
    assert S.GEOMETRY_CHECK_OFFSET > SUPPLEMENT["replicates"]


def test_module_and_runner_read_no_market_data():
    banned = ("replay", "historical", "price", "outcome", "sealed", "kelly", "us_cash_profitability", "yfinance", "requests", "urllib")
    for rel in ("pipeline/us_h63_supplemental_calibration.py", "scripts/run_us_h63_supplemental_calibration.py"):
        tree = ast.parse((ROOT / rel).read_text())
        mods = []
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                mods += [a.name for a in n.names]
            elif isinstance(n, ast.ImportFrom):
                mods += [(n.module or "") + "." + a.name for a in n.names]
        assert not [m for m in mods if any(b in m.lower() for b in banned)], (rel, mods)


def test_committed_result_follows_its_frozen_rule():
    if not S.RESULT_PATH.exists():
        pytest.skip("result not yet produced")
    r = json.loads(S.RESULT_PATH.read_bytes())
    assert r["developmentOnly"] is False and r["readsRealData"] is False
    assert r["protocolSha256"] == FROZEN_SUPPLEMENT_SHA == S.sha256_file(S.PROTOCOL_PATH)
    assert r["parent"]["protocolSha256"] == S.PARENT_PROTOCOL_SHA256 and r["replicates"] == 2000 and r["seed"] == SUPPLEMENT["seed"]
    assert [(c["dgp"], c["weeks"]) for c in r["cells"]] == [(d["name"], w) for d in SUPPLEMENT["dgps"] for w in (260, 700)]
    assert r["verdict"] == S.verdict(r["cells"], 30)
    for c in r["cells"]:
        assert c["primaryState"] == c["methods"]["CT_SN"]["state"]
    assert r["codeSha256"]["pipeline/us_h63_inference_calibration.py"] == S.PARENT_CODE_SHA256
