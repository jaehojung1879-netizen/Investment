"""The committed contracts equal what the builder produces from the sealed modules; register entries follow the shared schema;
no committed lane artefact carries an outcome-like key."""
import json
import re
from pathlib import Path

from research.master_research_program_v1.evidence_map import register as REG
from research.master_research_program_v1.market_industry import build_contracts as B

HERE = Path(__file__).resolve().parent
OUTCOME_TOKENS = {"return", "returns", "nav", "cagr", "sharpe", "ic", "excess", "pnl", "alpha", "drawdown", "mdd"}
ALLOWED_KEYS = {"returnsRead"}


def _load(name):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def test_contracts_are_reproducible_from_sealed_modules():
    assert _load("market-timing-prospective-contract-v1.json") == json.loads(json.dumps(B.market_timing_contract()))
    assert _load("industry-relative-prospective-contract-v1.json") == json.loads(json.dumps(B.industry_contract()))


def test_market_contract_mapping_tables_equal_sealed_tables():
    from pipeline import kr_market_risk_model as K
    c = _load("market-timing-prospective-contract-v1.json")
    for cid in K.CANDIDATE_ORDER:
        assert c["candidates"]["mappingTables"][cid] == K.mapping_table(cid)
    assert c["candidates"]["levels"] == list(K.LEVELS)
    assert c["status"].startswith("PROPOSED")
    assert set(c["inference"]["lags"]) == {"H126", "H252"}


def test_register_entries_validate_against_shared_schema():
    entries = _load("register-entries.json")["entries"]
    ids = [e["researchId"] for e in entries]
    assert len(ids) == len(set(ids))
    for e in entries:
        REG.validate(e)
        assert e["track"] in {"MARKET", "INDUSTRY", "DATA"}
    for needed in ("M-KR-TIMING-PROSPECTIVE", "M-US-TIMING-PROSPECTIVE", "I-US-SECTOR-PIT", "I-KR-INDUSTRY-PROSPECTIVE",
                   "I-US-INDUSTRY-PROSPECTIVE", "D-US-SECTOR-FOUNDATION"):
        assert needed in ids


def _numeric_keys(value, path=""):
    if isinstance(value, dict):
        for k, v in value.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                yield k
            yield from _numeric_keys(v, path + "." + k)
    elif isinstance(value, list):
        for v in value:
            yield from _numeric_keys(v, path)


def test_lane_artefacts_publish_no_outcome_numbers():
    for name in ("market_receipts_status.json", "us-sector-foundation-v1.json", "kr-industry-foundation-status-v1.json"):
        payload = _load(name)
        assert payload["outcomeFree"] is True
        leaked = [k for k in _numeric_keys(payload) if k not in ALLOWED_KEYS
                  and OUTCOME_TOKENS & {t.lower() for t in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])", k)}]
        assert leaked == [], (name, leaked)
    status = _load("market_receipts_status.json")
    assert status["stateValuesRead"] is False
    assert {s["status"] for s in status["KR"]["ledgers"]} <= {"RECORDING", "STALLED", "MISSING"}
