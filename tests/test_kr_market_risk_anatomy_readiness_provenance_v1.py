"""The committed readiness record, source report and provenance are exactly what the committed snapshot and frozen rules produce."""
import importlib.util
import json
from pathlib import Path

from pipeline import kr_market_risk_anatomy_execution as E

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "docs/results"


def load_writer():
    spec = importlib.util.spec_from_file_location("writer", ROOT / "scripts/write_kr_market_risk_readiness.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_committed_readiness_json_and_report_equal_a_fresh_label_free_run():
    writer = load_writer()
    fresh = E.readiness_audit(ROOT)
    assert (R / "kr-market-risk-anatomy-v1-readiness.json").read_text() == json.dumps(fresh, sort_keys=True, indent=2, default=str) + "\n"
    assert (ROOT / "docs/kr-market-risk-anatomy-v1-source-readiness.md").read_text() == writer.render(fresh)
    committed = json.loads((R / "kr-market-risk-anatomy-v1-readiness.json").read_text())
    assert committed["decision"] in ("READY_FOR_MARKET_RISK_ANATOMY_EXECUTION", "DATA_BLOCKED_BEFORE_MARKET_RISK_ANATOMY") and committed["decision"].startswith("DATA_BLOCKED")
    assert committed["counters"] == {"analysisCalls": 0, "episodeCalls": 0, "forwardTargetCalls": 0, "markerWrites": 0, "valueReads": 0}


def test_provenance_pins_the_freeze_snapshot_and_acquisition_identities():
    prov = json.loads((R / "kr-market-risk-anatomy-v1-source-provenance.json").read_text())
    spec = json.loads((ROOT / "research_specs/kr-market-risk-anatomy-v1.json").read_text())
    assert prov["preSourceFreeze"]["commit"] == spec["preSourceFreezeCommit"] == "8091944a2dea3a7fc91c6135b364222bdc997fd0"
    assert prov["preSourceFreeze"]["designSha256"] == spec["designSha256"] and prov["preSourceFreeze"]["containedAnySourceValue"] is False
    assert prov["sourceAcquisition"]["auditSha256"] == spec["sourcePins"]["auditSha256"] and prov["sourceAcquisition"]["artifactId"] == 11308459691
    assert prov["sourceAcquisition"]["successfulRunId"] == 37217470467 and len(prov["postFreezeChangesAllIdentityOrImplementationOnly"]) == 2
    assert any("No forward return, drawdown" in s for s in prov["statements"])
