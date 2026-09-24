import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import collect_dart_ownership_events as collector  # noqa: E402
from pipeline import dart_ownership_events as DOE  # noqa: E402


def _universe():
    return {
        "securityCount": 2, "issuerCount": 2,
        "currentUniverseSecurityCount": 1, "currentUniverseIssuerCount": 1,
        "historicalOnlySecurityCount": 1, "historicalOnlyIssuerCount": 1,
        "successfullyMappedDartCorpCodes": 2, "unresolvedIdentityCount": 0,
    }


def test_fetch_state_resumes_completed_issuers_under_same_raw_contract(tmp_path):
    state = {"contract": collector.STATE_CONTRACT, "rawContract": DOE.RAW_CONTRACT,
             "issuers": {"001": {"status": "SUCCESS"}}}
    (tmp_path / "fetch-state.json").write_text(json.dumps(state), encoding="utf-8")
    assert collector.load_state(tmp_path) == state


def test_old_fetch_contract_triggers_defined_refresh_without_erasing_shards(tmp_path):
    (tmp_path / "fetch-state.json").write_text(
        json.dumps({"contract": "V1", "rawContract": "RAW_V1", "issuers": {"001": {}}}),
        encoding="utf-8")
    state = collector.load_state(tmp_path)
    assert state["issuers"] == {}
    assert state["previousContract"] == "RAW_V1"


def test_manifest_generation_is_deterministic_and_reports_coverage():
    state = {"issuers": {
        "001": {"status": "SUCCESS", "queriedAt": "2026-09-24T00:00:00Z"},
        "002": {"status": "ERROR", "lastAttemptAt": "2026-09-24T00:00:00Z"},
    }}
    event = {"id": "dart-ownership:20240101000001", "availableFrom": "2024-01-01"}
    kwargs = dict(universe=_universe(), state=state, shards={2024: [event]},
                  updated_at="2026-09-24T00:00:00Z",
                  this_run={"calls": 1, "stopReason": "CALL_BUDGET_SPENT"})
    first = collector.build_manifest(**kwargs)
    second = collector.build_manifest(**kwargs)
    assert first == second
    assert first["companiesQueried"] == 2
    assert first["successfullyQueriedCompanies"] == 1
    assert first["companiesRemaining"] == 1
    assert first["eventCount"] == 1
    assert first["shardCoverage"] == ["2024"]
