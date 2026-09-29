"""v2 entity-scheme rule. Synthetic fixtures only; no outcome data."""
from decimal import Decimal
import io
import json
from pathlib import Path
import zipfile

import pytest

from pipeline import kr_xbrl_validation_sample as S
from pipeline import kr_xbrl_value_validation as V
from pipeline import kr_xbrl_value_validation_v2 as V2
from scripts import validate_kr_original_xbrl_values_v2 as CLI2
from tests.test_kr_original_xbrl_value_validation import package

ROOT = Path(__file__).resolve().parents[1]
CIK = "http://dart.fss.or.kr/ifrs/CIK"


def with_scheme(scheme, family="assets", **kwargs):
    item, raw, rows = package(family=family, **kwargs)
    src = zipfile.ZipFile(io.BytesIO(raw))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as dst:
        for info in src.infolist():
            data = src.read(info)
            if info.filename == "instance.xbrl":
                data = data.replace(b'scheme="http://dart.fss.or.kr"', ('scheme="%s"' % scheme).encode())
            dst.writestr(info.filename, data)
    raw = out.getvalue()
    item["zipSha256"] = V.sha256(raw)
    return item, raw, rows


def v1(scheme, **kwargs):
    item, raw, rows = with_scheme(scheme, **kwargs)
    return V.validate_item(item, Decimal("1000"), raw, rows)


def v2(scheme, **kwargs):
    item, raw, rows = with_scheme(scheme, **kwargs)
    return V2.validate_item(item, Decimal("1000"), raw, rows)


def test_v1_still_rejects_cik_scheme_and_stays_blocked():
    r = v1(CIK)
    assert r["classification"] == "AMBIGUOUS_SOURCE_FACT"
    assert r["reason"] == "context entity scheme not independently established as DART identity"


@pytest.mark.parametrize("family", S.FAMILIES)
def test_v2_accepts_exact_cik_scheme_and_matches(family):
    assert v2(CIK, family=family)["classification"] == "MATCH"


@pytest.mark.parametrize("scheme", [
    CIK + "/", CIK.replace("http:", "https:"), CIK.lower().replace("cik", "cik"),
    "http://dart.fss.or.kr/ifrs/cik", "http://dart.fss.or.kr/ifrs/", "http://dart.fss.or.kr/ifrs/CIK2",
    "http://opendart.fss.or.kr/ifrs/CIK", "http://www.sec.gov/CIK", "http://dart.fss.or.kr/other/CIK",
    "http://example.com/ifrs/CIK", ""])
def test_v2_rejects_unsupported_alternate_schemes(scheme):
    assert v2(scheme)["classification"] == "AMBIGUOUS_SOURCE_FACT"


def test_v2_leaves_v1_bare_host_scheme_behaviour_unchanged():
    assert v2("http://dart.fss.or.kr")["classification"] == "MATCH"


def test_corp_code_mismatch_under_cik_is_metadata_failure():
    assert v2(CIK, entity="00999999")["classification"] == "METADATA_MISMATCH"


def test_no_stock_code_fallback_under_cik_scheme():
    r = v2(CIK, entity="123456")  # the fixture's stockCode
    assert r["classification"] == "METADATA_MISMATCH"


@pytest.mark.parametrize("kwargs,status", [
    ({"instant": "2014-03-31"}, "SEMANTIC_MISMATCH"),
    ({"unit": "iso4217:USD"}, "SEMANTIC_MISMATCH"),
    ({"basis": "SeparateMember"}, "SEMANTIC_MISMATCH"),
    ({"basis": ""}, "AMBIGUOUS_SOURCE_FACT"),
    ({"statement": False}, "AMBIGUOUS_SOURCE_FACT"),
    ({"attribute": ' scale="3"'}, "AMBIGUOUS_SOURCE_FACT"),
    ({"decimals": None}, "AMBIGUOUS_SOURCE_FACT"),
    ({"amount": "1001"}, "VALUE_MISMATCH"),
])
def test_every_later_check_still_runs_after_the_entity_check(kwargs, status):
    assert v2(CIK, **kwargs)["classification"] == status


def test_matching_raw_amount_alone_is_not_a_match():
    # Entity/scheme/amount all agree, but the presentation proof is missing.
    assert v2(CIK, statement=False)["classification"] == "AMBIGUOUS_SOURCE_FACT"


def test_v2_uses_the_exact_v1_sample_and_files():
    protocol_v1, protocol, sample = V2.load_frozen(ROOT)
    assert protocol["sample"]["requiredSha256"] == V.SAMPLE_SHA256 == \
        "590513ede1c8bd06d701f22f4b1aa01bcf8b004aa30b9410540865696e863e70"
    assert protocol["candidate"]["sha256"] == protocol_v1["candidate"]["sha256"]
    assert len(sample["items"]) == 60
    assert V.sha256((ROOT / "research_specs/kr-original-xbrl-value-validation-v1-sample.json").read_bytes()) == V.SAMPLE_SHA256
    assert not (ROOT / "research_specs/kr-original-xbrl-value-validation-v2-sample.json").exists()


def test_v1_result_files_are_not_mutated_by_v2():
    report = json.loads((ROOT / "docs/results/kr-original-xbrl-value-validation-v1-report.json").read_text())
    assert report["verdict"] == "BLOCKED" and report["counts"]["AMBIGUOUS_SOURCE_FACT"] == 60
    assert V.sha256((ROOT / "docs/results/kr-original-xbrl-value-validation-v1-report.json").read_bytes()) == \
        "6341d0aae30c014c8f15b2cae7261609742b52dae7f698d2bc33fe0b5a74380b"


def test_v2_protocol_is_frozen_and_changes_exactly_one_scheme():
    _, protocol, _ = V2.load_frozen(ROOT)
    assert V2.V2_CORP_CODE_SCHEMES == frozenset({CIK}) and V.V1_CORP_CODE_SCHEMES == frozenset()
    assert protocol["singleSemanticChange"]["rule"].count(CIK) == 1


def test_tampered_v2_protocol_refused(tmp_path, monkeypatch):
    (tmp_path / "research_specs").mkdir()
    for name in ("kr-original-xbrl-value-validation-v1.json", "kr-original-xbrl-value-validation-v1-sample.json",
                 "kr-original-xbrl-value-validation-v2.json"):
        (tmp_path / "research_specs" / name).write_bytes((ROOT / "research_specs" / name).read_bytes())
    tampered = tmp_path / "research_specs/kr-original-xbrl-value-validation-v2.json"
    tampered.write_bytes(tampered.read_bytes() + b" ")
    monkeypatch.setattr(V2.subprocess, "run", lambda *a, **k: None)
    monkeypatch.setattr(V.subprocess, "run", lambda *a, **k: None)
    monkeypatch.setattr(V.subprocess, "check_output", lambda args, **k: (ROOT / args[-1].partition(":")[2]).read_bytes())
    with pytest.raises(ValueError, match="V2_PROTOCOL_CHANGED"):
        V2.load_frozen(tmp_path)


def test_v2_cli_refuses_v1_result_path(tmp_path):
    with pytest.raises(SystemExit):
        CLI2.main(["--input-root", str(tmp_path), "--source-dir", str(tmp_path),
                   "--output", str(tmp_path / "kr-original-xbrl-value-validation-v1-report.json")])


def test_v2_does_not_use_production_parser_or_outcomes():
    for name in ("pipeline/kr_xbrl_value_validation_v2.py", "scripts/validate_kr_original_xbrl_values_v2.py"):
        code = (ROOT / name).read_text()
        assert "dart_xbrl_statements" not in code and "resolve_account(" not in code
        for forbidden in ("replay", "kelly_portfolio", "portfolio_validation", "docs/results/alpha"):
            assert forbidden not in code
    with pytest.raises(ValueError, match="OUTCOME_OR_UNAPPROVED_PATH_REFUSED"):
        S.permitted_path(ROOT, "ledger/historical/replay-v16/x.jsonl.gz")


def test_saved_v2_report_preserves_the_exact_v1_items_and_v1_is_separate():
    _, _, sample = V2.load_frozen(ROOT)
    report = json.loads((ROOT / "docs/results/kr-original-xbrl-value-validation-v2-report.json").read_text())
    assert [r["sampleItem"] for r in report["results"]] == sample["items"]
    assert report["sampleSha256"] == V.SAMPLE_SHA256
    assert sum(report["counts"].values()) == 60 and report["verdict"] == "BLOCKED"
    assert report["counts"]["MATCH"] == 0 and report["promotionRecommended"] is False
