"""v3 rules. Synthetic fixtures only; no outcome data."""
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import zipfile

import pytest

from pipeline import kr_xbrl_validation_sample as S
from pipeline import kr_xbrl_value_validation as V
from pipeline import kr_xbrl_value_validation_v2 as V2
from pipeline import kr_xbrl_value_validation_v3 as V3
from scripts import validate_kr_original_xbrl_values_v3 as CLI3
from tests.test_kr_original_xbrl_value_validation_v2 import CIK, with_scheme

ROOT = Path(__file__).resolve().parents[1]
IFRS_NS = "http://xbrl.ifrs.org/taxonomy/2014-03-05/ifrs-full"


def run(module, scheme=CIK, value="1000", **kwargs):
    item, raw, rows = with_scheme(scheme, **kwargs)
    return module.validate_item(item, Decimal(value), raw, rows)


def swap_namespace(raw, new):
    src = zipfile.ZipFile(io.BytesIO(raw))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as dst:
        for info in src.infolist():
            data = src.read(info)
            if info.filename == "instance.xbrl":
                data = data.replace(('xmlns:f="%s"' % IFRS_NS).encode(), ('xmlns:f="%s"' % new).encode())
            dst.writestr(info.filename, data)
    return out.getvalue()


def test_v1_and_v2_still_block_without_presentation_evidence():
    assert run(V, scheme="http://dart.fss.or.kr", statement=False)["classification"] == "AMBIGUOUS_SOURCE_FACT"
    assert run(V2, statement=False)["reason"] == "source presentation does not prove required financial statement"


@pytest.mark.parametrize("family", S.FAMILIES)
def test_v3_matches_without_presentation_evidence(family):
    r = run(V3, family=family, statement=False)
    assert r["classification"] == "MATCH"
    fact = r["sourceFacts"][0]
    assert fact["presentation"] == [] and fact["presentationCorroboratesStatement"] is False
    assert fact["conceptIdentity"]["ifrsNamespace"] is True and fact["conceptIdentity"]["localName"] == V.RULES[family][0]


def test_presentation_present_is_recorded_as_corroboration_only():
    fact = run(V3, statement=True)["sourceFacts"][0]
    assert fact["presentationCorroboratesStatement"] is True and fact["presentation"]


def test_v3_keeps_v2_entity_rule():
    assert run(V3, scheme="http://dart.fss.or.kr/ifrs/cik", statement=False)["classification"] == "AMBIGUOUS_SOURCE_FACT"
    assert run(V3, entity="00999999", statement=False)["classification"] == "METADATA_MISMATCH"
    assert run(V3, entity="123456", statement=False)["classification"] == "METADATA_MISMATCH"


@pytest.mark.parametrize("kwargs,status", [
    ({"amount": "1001"}, "VALUE_MISMATCH"),
    ({"instant": "2014-03-31"}, "SEMANTIC_MISMATCH"),
    ({"unit": "iso4217:USD"}, "SEMANTIC_MISMATCH"),
    ({"basis": "SeparateMember"}, "SEMANTIC_MISMATCH"),
    ({"basis": ""}, "AMBIGUOUS_SOURCE_FACT"),
    ({"attribute": ' scale="3"'}, "AMBIGUOUS_SOURCE_FACT"),
    ({"decimals": None}, "AMBIGUOUS_SOURCE_FACT"),
    ({"amount": "NaN"}, "AMBIGUOUS_SOURCE_FACT"),
])
def test_all_other_checks_still_run_without_the_presentation_gate(kwargs, status):
    assert run(V3, statement=False, **kwargs)["classification"] == status


def test_extension_namespace_concept_is_ambiguous_not_assumed_equivalent():
    item, raw, rows = with_scheme(CIK, statement=False)
    item["zipSha256"] = V.sha256(swap_namespace(raw, "urn:company:extension"))
    r = V3.validate_item(item, Decimal("1000"), swap_namespace(raw, "urn:company:extension"), rows)
    assert r["classification"] == "AMBIGUOUS_SOURCE_FACT"
    assert "IFRS concept identity" in r["reason"]


def test_wrong_family_concept_is_a_semantic_mismatch():
    item, raw, rows = with_scheme(CIK, family="assets", statement=False)
    item["element"] = "Liabilities"
    assert V3.validate_item(item, Decimal("1000"), raw, rows)["classification"] in (
        "AMBIGUOUS_SOURCE_FACT", "SEMANTIC_MISMATCH")


def test_conflicting_duplicate_facts_still_ambiguous():
    extra = '<f:Assets contextRef="ctx" unitRef="u" decimals="0">2000</f:Assets>'
    assert run(V3, statement=False, extra_fact=extra)["classification"] == "AMBIGUOUS_SOURCE_FACT"


def test_v3_uses_the_exact_v1_sample_and_closed_results_are_untouched():
    protocol_v1, protocol, sample = V3.load_frozen(ROOT)
    assert protocol["sample"]["requiredSha256"] == V.SAMPLE_SHA256 and len(sample["items"]) == 60
    assert protocol["candidate"]["sha256"] == protocol_v1["candidate"]["sha256"]
    for name, seal in (("research_specs/kr-original-xbrl-value-validation-v1-sample.json", V.SAMPLE_SHA256),
                       ("research_specs/kr-original-xbrl-value-validation-v2.json", V2.PROTOCOL_SHA256)):
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == seal
    assert not (ROOT / "research_specs/kr-original-xbrl-value-validation-v3-sample.json").exists()
    v2 = json.loads((ROOT / "docs/results/kr-original-xbrl-value-validation-v2-report.json").read_text())
    assert v2["verdict"] == "BLOCKED" and v2["counts"]["AMBIGUOUS_SOURCE_FACT"] == 60


def test_v3_protocol_is_frozen(tmp_path, monkeypatch):
    (tmp_path / "research_specs").mkdir()
    for name in ("kr-original-xbrl-value-validation-v1.json", "kr-original-xbrl-value-validation-v1-sample.json",
                 "kr-original-xbrl-value-validation-v2.json", "kr-original-xbrl-value-validation-v3.json"):
        (tmp_path / "research_specs" / name).write_bytes((ROOT / "research_specs" / name).read_bytes())
    tampered = tmp_path / "research_specs/kr-original-xbrl-value-validation-v3.json"
    tampered.write_bytes(tampered.read_bytes() + b" ")
    for mod in (V3, V2, V):
        monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: None)
    monkeypatch.setattr(V.subprocess, "check_output", lambda args, **k: (ROOT / args[-1].partition(":")[2]).read_bytes())
    monkeypatch.setattr(V2.subprocess, "check_output", lambda args, **k: (ROOT / args[-1].partition(":")[2]).read_bytes())
    with pytest.raises(ValueError, match="V3_PROTOCOL_CHANGED"):
        V3.load_frozen(tmp_path)


def test_v3_cli_refuses_closed_result_paths(tmp_path):
    for name in ("kr-original-xbrl-value-validation-v1-report.json", "kr-original-xbrl-value-validation-v2-report.json"):
        with pytest.raises(SystemExit):
            CLI3.main(["--input-root", str(tmp_path), "--source-dir", str(tmp_path), "--output", str(tmp_path / name)])


def test_no_production_parser_or_outcome_access():
    for name in ("pipeline/kr_xbrl_value_validation_v3.py", "scripts/validate_kr_original_xbrl_values_v3.py"):
        code = (ROOT / name).read_text()
        assert "dart_xbrl_statements" not in code and "resolve_account(" not in code
        for forbidden in ("kelly_portfolio", "portfolio_validation", "replay_valuation", "historical_outcomes", "docs/results/alpha"):
            assert forbidden not in code
    with pytest.raises(ValueError, match="OUTCOME_OR_UNAPPROVED_PATH_REFUSED"):
        S.permitted_path(ROOT, "ledger/historical/replay-v16/x.jsonl.gz")
