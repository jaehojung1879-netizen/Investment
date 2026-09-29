"""Synthetic fixtures only: no historical investment or original filing values."""
from copy import deepcopy
from decimal import Decimal
import io
import json
from pathlib import Path
import random
import zipfile

import pytest

from pipeline import kr_xbrl_validation_sample as S
from pipeline import kr_xbrl_value_validation as V
from scripts import validate_kr_original_xbrl_values as CLI

ROOT = Path(__file__).resolve().parents[1]
IFRS = "http://xbrl.ifrs.org/taxonomy/2014-03-05/ifrs-full"


def stored(i=0):
    return {"id": str(i), "source": "DART:fnlttXbrl.xml:ORIGINAL", "ticker": f"{i:06d}.KS",
            "stockCode": f"{i:06d}", "corpCode": f"{i:08d}", "fiscalYear": 2015,
            "reportCode": ("11013", "11012", "11014")[i % 3], "reportName": "Q1",
            "receiptNos": ["20150515000001"], "currency": "KRW", "availableFrom": "2015-05-15",
            "accounts": {a: {"amounts": {"thstrm_amount": i}, "accountId": V.RULES[f][0],
                              "statement": sorted(V.RULES[f][1])[0]} for f, a in S.ACCOUNTS.items()},
            "canonicalization": {"zipSha256": "0" * 64, "accounts": {
                a: {"statementBasis": "CFS" if i % 2 else "OFS", "contextRef": "ctx", "unitRef": "u",
                    "decimals": "0"} for a in S.ACCOUNTS.values()}}}


def sample_frame():
    return [item for i in range(90) for item in S.project_record(stored(i))]


def package(family="assets", amount="1000", decimals="0", precision=None, unit="iso4217:KRW",
            instant="2015-03-31", basis="ConsolidatedMember", entity="00123456",
            statement=True, extra_fact="", attribute="", qualifier="", concept=None):
    item = next(r for r in S.project_record(stored()) if r["family"] == family)
    concept = concept or V.RULES[family][0]
    item.update(corpCode="00123456", stockCode="123456", ticker="123456.KS", basis="CFS",
                element=V.RULES[family][0], decimals=decimals)
    stage_period = (f"<x:instant>{instant}</x:instant>" if family in ("assets", "liabilities") else
                    f"<x:startDate>2015-01-01</x:startDate><x:endDate>{instant}</x:endDate>")
    dim = (f'<d:explicitMember dimension="f:ConsolidatedAndSeparateFinancialStatementsAxis">f:{basis}</d:explicitMember>'
           if basis else "")
    accuracy = (f' decimals="{decimals}"' if decimals is not None else "")
    accuracy += f' precision="{precision}"' if precision is not None else ""
    fact = f'<f:{concept} contextRef="ctx" unitRef="u"{accuracy}{attribute}>{amount}</f:{concept}>'
    xml = f'''<x:xbrl xmlns:x="{V.XBRLI}" xmlns:f="{IFRS}" xmlns:d="{V.XBRLDI}"
     xmlns:iso4217="{V.ISO}" xmlns:link="{V.LINK}" xmlns:xl="{V.XLINK}">
     <x:context id="ctx"><x:entity><x:identifier scheme="http://dart.fss.or.kr">{entity}</x:identifier></x:entity>
       <x:period>{stage_period}</x:period><x:scenario>{dim}{qualifier}</x:scenario></x:context>
     <x:unit id="u"><x:measure>{unit}</x:measure></x:unit>{fact}{extra_fact}</x:xbrl>'''
    title = {"assets": "Statement of financial position", "liabilities": "Statement of financial position",
             "net_income": "Statement of comprehensive income", "operating_cash_flow": "Statement of cash flows"}[family]
    link = f'''<link:linkbase xmlns:link="{V.LINK}" xmlns:xl="{V.XLINK}">
      <link:roleType roleURI="urn:test:statement"><link:definition>{title}</link:definition></link:roleType>
      <link:presentationLink xl:role="urn:test:statement">
       <link:loc xl:label="fact" xl:href="{IFRS}.xsd#ifrs-full_{concept}"/>
       <link:loc xl:label="root" xl:href="{IFRS}.xsd#ifrs-full_StatementAbstract"/>
       <link:presentationArc xl:from="root" xl:to="fact"/>
      </link:presentationLink></link:linkbase>'''
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("instance.xbrl", xml)
        if statement:
            z.writestr("presentation.xml", link)
    raw = out.getvalue()
    item["zipSha256"] = V.sha256(raw)
    filing = [{"rcept_no": item["receiptNos"][0], "corp_code": item["corpCode"],
               "stock_code": item["stockCode"], "rcept_dt": "20150515", "report_nm": "분기보고서 (2015.03)"}]
    return item, raw, filing


def check(value="1000", **kwargs):
    item, raw, rows = package(**kwargs)
    return V.validate_item(item, Decimal(value), raw, rows)


def test_sample_reproducible_and_balanced_under_input_permutations():
    frame = sample_frame()
    selected = S.select(frame)
    random.Random(41).shuffle(frame)
    assert selected == S.select(frame)
    assert len(selected) == 60
    assert len({r["identity"] for r in selected}) == 60
    assert len({r["corpCode"] for r in selected}) == 60
    for family in S.FAMILIES:
        assert sum(r["family"] == family for r in selected) == 15
        assert {r["reportCode"] for r in selected if r["family"] == family} == {"11013", "11012", "11014"}


def test_amount_access_is_forbidden_during_projection():
    class NoAmounts(dict):
        def __getitem__(self, key):
            if key == "amounts":
                raise AssertionError("amount was accessed")
            return super().__getitem__(key)

        def get(self, key, default=None):
            if key == "amounts":
                raise AssertionError("amount was accessed")
            return super().get(key, default)

    rows = []
    for i in range(90):
        row = stored(i)
        row["accounts"] = {k: NoAmounts(v) for k, v in row["accounts"].items()}
        rows.extend(S.project_record(row))
    assert S.select(rows) == S.select(sample_frame())


def test_numeric_sign_magnitude_missingness_and_provenance_status_do_not_select():
    before, after = [], []
    for i in range(90):
        row = stored(i)
        before.extend(S.project_record(row))
        for a in row["accounts"]:
            row["accounts"][a]["amounts"] = {"anything": None if i % 2 else -(10 ** 30)}
            row["canonicalization"]["accounts"][a]["status"] = "AMBIGUOUS"
        after.extend(S.project_record(row))
    assert before == after
    assert S.select(before) == S.select(after)


def test_short_or_duplicate_frame_refused():
    with pytest.raises(ValueError, match="INSUFFICIENT"):
        S.select(sample_frame()[:4])
    frame = sample_frame()
    with pytest.raises(ValueError, match="DUPLICATE"):
        S.select(frame + frame[:1])


@pytest.mark.parametrize("path", ["ledger/results/alpha.json", "ledger/prices/us.jsonl.gz",
    "signal-history/outcomes.json", "../ledger/fundamentals/kr-xbrl-original/dart-xbrl-2015.jsonl.gz",
    "ledger/fundamentals/kr-candidate-merged/coverage-audit/results.json"])
def test_outcome_path_refusal(tmp_path, path):
    with pytest.raises(ValueError, match="REFUSED"):
        S.permitted_path(tmp_path, path)


def test_symlink_refusal(tmp_path):
    relative = "ledger/fundamentals/kr-xbrl-original/dart-xbrl-2015.jsonl.gz"
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    target.symlink_to(tmp_path / "forbidden")
    with pytest.raises(ValueError, match="SYMLINK"):
        S.permitted_path(tmp_path, relative)


@pytest.mark.parametrize("family", S.FAMILIES)
def test_independent_reader_matches_each_account_family(family):
    report = check(family=family)
    assert report["classification"] == "MATCH"
    assert report["sourceFacts"][0]["unit"] == "{" + V.ISO + "}KRW"
    assert report["sourceFacts"][0]["presentation"]


@pytest.mark.parametrize("kwargs,status", [
    ({"value": "1001"}, "VALUE_MISMATCH"),
    ({"value": "-1000"}, "VALUE_MISMATCH"),
    ({"instant": "2014-03-31"}, "SEMANTIC_MISMATCH"),
    ({"unit": "iso4217:USD"}, "SEMANTIC_MISMATCH"),
    ({"basis": "SeparateMember"}, "SEMANTIC_MISMATCH"),
    ({"basis": ""}, "AMBIGUOUS_SOURCE_FACT"),
    ({"entity": "unmapped-business-registration-number"}, "AMBIGUOUS_SOURCE_FACT"),
    ({"statement": False}, "AMBIGUOUS_SOURCE_FACT"),
    ({"attribute": ' scale="3"'}, "AMBIGUOUS_SOURCE_FACT"),
    ({"attribute": ' sign="-"'}, "AMBIGUOUS_SOURCE_FACT"),
    ({"amount": "NaN"}, "AMBIGUOUS_SOURCE_FACT"),
    ({"decimals": None}, "AMBIGUOUS_SOURCE_FACT"),
    ({"decimals": "0", "precision": "3"}, "AMBIGUOUS_SOURCE_FACT"),
])
def test_numeric_and_semantic_failures(kwargs, status):
    assert check(**kwargs)["classification"] == status


def test_prior_axis_and_equity_components_are_not_totals():
    q = '<d:explicitMember dimension="f:ComponentsOfEquityAxis">f:EquityAttributableToOwnersOfParentMember</d:explicitMember>'
    assert check(qualifier=q)["classification"] == "SEMANTIC_MISMATCH"


def test_filing_metadata_mismatch_is_confirmed():
    item, raw, rows = package()
    rows[0]["corp_code"] = "other"
    assert V.validate_item(item, 1000, raw, rows)["classification"] == "METADATA_MISMATCH"


def test_no_later_amendment_substitution():
    item, raw, rows = package()
    rows[0]["report_nm"] = "[기재정정]분기보고서 (2015.03)"
    assert V.validate_item(item, 1000, raw, rows)["classification"] == "METADATA_MISMATCH"


def test_unit_reference_metadata_not_silently_corrected():
    item, raw, rows = package()
    item["unitRef"] = "wrong"
    assert V.validate_item(item, 1000, raw, rows)["classification"] == "METADATA_MISMATCH"


def test_source_unavailable_and_hash_mismatch_do_not_pass():
    item, raw, rows = package()
    assert V.validate_item(item, 1000)["classification"] == "SOURCE_UNAVAILABLE"
    assert V.validate_item(item, 1000, raw + b"changed", rows)["classification"] == "AMBIGUOUS_SOURCE_FACT"
    assert V.validate_item(item, 1000, raw)["classification"] == "AMBIGUOUS_SOURCE_FACT"


def test_conflicting_duplicate_source_facts_are_ambiguous():
    duplicate = '<f:Assets contextRef="ctx" unitRef="u" decimals="0">1001</f:Assets>'
    report = check(extra_fact=duplicate)
    assert report["classification"] == "AMBIGUOUS_SOURCE_FACT"
    assert len(report["sourceFacts"]) == 2


def test_equal_duplicate_facts_resolve():
    duplicate = '<f:Assets contextRef="ctx" unitRef="u" decimals="0">1000.0</f:Assets>'
    assert check(extra_fact=duplicate)["classification"] == "MATCH"


@pytest.mark.parametrize("source,candidate,decimals,precision,expected", [
    ("1000", "1000.000", "INF", None, True),
    ("1000", "1000.1", "INF", None, False),
    ("1000", "1000.4", "0", None, True),
    ("1000", "1000.6", "0", None, False),
    ("1000", "1400", "-3", None, True),
    ("1000", "1600", "-3", None, False),
    ("1230", "1231", None, "3", True),
    ("1230", "1240", None, "3", False),
    ("9007199254740993", "9007199254740992", "0", None, False),
])
def test_exact_decimal_and_declared_accuracy(source, candidate, decimals, precision, expected):
    assert V.equal_at_precision(Decimal(source), Decimal(candidate), decimals, precision) is expected


def test_precision_zero_and_undeclared_accuracy_do_not_match():
    for args in [(None, None), (None, "0"), ("NaN", None), ("0", "3")]:
        with pytest.raises(V.Ambiguous):
            V.equal_at_precision(Decimal(1000), Decimal(1000), *args)


def test_scoped_qname_resolution():
    raw = b'<a xmlns:p="urn:one"><b xmlns:p="urn:two">p:v</b><c>p:v</c></a>'
    root, scopes = V.xml_document(raw)
    assert V.expand(root[0].text, root[0], scopes) == "{urn:two}v"
    assert V.expand(root[1].text, root[1], scopes) == "{urn:one}v"


def test_dtd_refused():
    with pytest.raises(V.Ambiguous, match="DTD"):
        V.xml_document(b'<!DOCTYPE x [<!ENTITY e "x">]><x>&e;</x>')


def test_strict_verdict_priorities_and_complete_counts():
    rows = [{"classification": "MATCH"}] * 60
    assert V.summarize(rows)["verdict"] == "PASS"
    assert V.summarize(rows)["descriptiveTwoSided95UpperMismatchBound"] > 0
    for classification in V.CLASSIFICATIONS[1:]:
        report = V.summarize(rows[:59] + [{"classification": classification}])
        expected = ("FAIL" if classification.endswith("MISMATCH") else
                    "INFRASTRUCTURE_ERROR" if classification == "INFRASTRUCTURE_ERROR" else "BLOCKED")
        assert report["verdict"] == expected
        assert report["counts"][classification] == 1
    assert V.summarize(rows[:59])["verdict"] == "INFRASTRUCTURE_ERROR"
    assert V.summarize([{"classification": "VALUE_MISMATCH"},
                        {"classification": "INFRASTRUCTURE_ERROR"}])["verdict"] == "FAIL"


def test_actual_frozen_files_and_commit_are_unchanged():
    protocol, sample = V.load_frozen(ROOT)
    assert len(sample["items"]) == protocol["sample"]["size"] == 60
    assert protocol["frame"]["size"] == 2037


def test_tampered_manifest_refused_before_source_access(tmp_path, monkeypatch):
    directory = tmp_path / "research_specs"
    directory.mkdir()
    for suffix in (".json", "-sample.json"):
        name = S.STUDY + suffix
        (directory / name).write_bytes((ROOT / "research_specs" / name).read_bytes())
    manifest = directory / (S.STUDY + "-sample.json")
    manifest.write_bytes(manifest.read_bytes() + b" ")
    monkeypatch.setattr(V.subprocess, "run", lambda *a, **k: None)
    monkeypatch.setattr(V.subprocess, "check_output", lambda args, **k:
                        (ROOT / args[-1].partition(":")[2]).read_bytes())
    with pytest.raises(ValueError, match="FROZEN_FILE_CHANGED"):
        V.load_frozen(tmp_path)


def test_missing_key_never_invokes_transport(tmp_path, monkeypatch):
    monkeypatch.delenv("DART_API_KEY", raising=False)
    assert CLI.download_sources(tmp_path, {"items": []}) == {
        "status": "BLOCKED_ON_SOURCE_ACCESS", "reason": "DART_API_KEY absent"}


def test_source_path_rejects_traversal(tmp_path):
    item, _, _ = package()
    item["receiptNos"] = ["../../results"]
    with pytest.raises(ValueError, match="INVALID_SOURCE_RECEIPT"):
        CLI.source_path(tmp_path, item, ".zip")


def test_sanitizer_emits_only_known_commands_not_surrounding_narrative():
    text = "# Anything\nRun pytest -q and ruff check .\nThe published headline moved: SECRET_RESULT.\n"
    text += "Never merge directly to `main`.\nAn unlabelled model was much better: SECRET_COMPARISON."
    clean = S.sanitize_mixed_document(text)
    assert "pytest -q" in clean and "Never merge" in clean
    assert "SECRET" not in clean and "published headline" not in clean


def test_reader_never_imports_production_fact_parser():
    code = (ROOT / "pipeline/kr_xbrl_value_validation.py").read_text()
    assert "dart_xbrl_statements" not in code
    assert "resolve_account(" not in code and "extract_facts(" not in code


def test_saved_report_is_complete_and_preserves_fixed_items():
    protocol, sample = V.load_frozen(ROOT)
    report = json.loads((ROOT / "docs/results" / (S.STUDY + "-report.json")).read_text())
    assert report["sampleSha256"] == protocol["sample"]["manifestSha256"]
    assert [r["sampleItem"] for r in report["results"]] == sample["items"]
    assert all(r["candidateValue"] is not None for r in report["results"])
    assert report["verdict"] == "BLOCKED"
    assert report["counts"]["SOURCE_UNAVAILABLE"] == 60


def test_changed_frame_metadata_changes_selection_identity():
    frame = sample_frame()
    changed = deepcopy(frame)
    changed[0]["contextRef"] = "other"
    assert S.digest(frame) != S.digest(changed)
