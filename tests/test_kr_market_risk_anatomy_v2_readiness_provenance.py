"""The committed v2 readiness record and source report are exactly what the committed v1-retained snapshot and the frozen v2 rules produce."""
import importlib.util
import json
from pathlib import Path

from pipeline import kr_market_risk_anatomy_v2_execution as E

ROOT = Path(__file__).resolve().parents[1]


def test_committed_readiness_equals_a_fresh_label_free_run_and_explains_the_v1_difference():
    spec = importlib.util.spec_from_file_location("writer2", ROOT / "scripts/write_kr_market_risk_v2_readiness.py")
    writer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(writer)
    fresh = E.readiness_audit(ROOT)
    assert (ROOT / E.READINESS_PATH).read_text() == json.dumps(fresh, sort_keys=True, indent=2, default=str) + "\n"
    assert (ROOT / "docs/kr-market-risk-anatomy-v2-source-readiness.md").read_text() == writer.render(fresh)
    committed = json.loads((ROOT / E.READINESS_PATH).read_text())
    assert committed["counters"] == {"analysisCalls": 0, "episodeCalls": 0, "forwardTargetCalls": 0, "markerWrites": 0, "valueReads": 0}
    assert committed["v1Comparison"]["_v1Decision"] == "DATA_BLOCKED_BEFORE_MARKET_RISK_ANATOMY"
    if committed["decision"] == E.DECISION_READY:
        ref = committed["selectedReference"]
        assert committed["primaryReference"]["primary"] == "FDR_KS200" and committed["v1Comparison"]["FDR_KS200"]["v1Reasons"] == ["STALE_LAST_DATE"]
        assert ref["spliced"] is False and ref["liveOperationalFreshness"]["liveReady"] is False and ref["quality"]["badSessions"] == 0


def test_provenance_pins_the_freeze_and_states_the_non_outcome_boundary():
    prov = json.loads((ROOT / "docs/results/kr-market-risk-anatomy-v2-provenance.json").read_text())
    assert prov["preReadinessFreeze"]["containedAnyOutcome"] is False and prov["preReadinessFreeze"]["containedAnyReadinessOutput"] is False
    assert prov["predecessor"]["unchanged"] is True and prov["predecessor"]["status"] == "DATA_BLOCKED_BEFORE_MARKET_RISK_ANATOMY"
    assert "not blind to source METADATA" in prov["disclosure"] and any("No historical market-risk outcome" in s for s in prov["statements"])
    assert any("NOT live-ready" in s for s in prov["statements"]) and any("No KOSPI 200 / KOSPI composite series was spliced" in s for s in prov["statements"])
