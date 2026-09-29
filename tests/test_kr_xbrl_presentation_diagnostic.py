"""Synthetic fixtures only; no source values, outcomes or network."""
import hashlib
import io
import json
from pathlib import Path
import zipfile

import pytest

from pipeline import kr_xbrl_presentation_diagnostic as D
from pipeline import kr_xbrl_value_validation as V
from pipeline import kr_xbrl_value_validation_v2 as V2

ROOT = Path(__file__).resolve().parents[1]
IFRS = "http://xbrl.iasb.org/taxonomy/2010-04-30/ifrs"
XSD = "http://www.w3.org/2001/XMLSchema"


def item(family="assets"):
    return {"identity": "000001.KS:2015:11013:" + family, "family": family, "reportCode": "11013",
            "basis": "CFS", "receiptNos": ["20150515000001"], "ticker": "000001.KS", "corpCode": "00000001",
            "element": V.RULES[family][0], "contextRef": "ctx"}


def build(family="assets", role_def="Statement of financial position", role_in_other_doc=False,
          href=None, with_arc=True, with_link=True, with_role=True, local_schema=False):
    el = V.RULES[family][0]
    href = href if href is not None else f"{IFRS}/ifrs.xsd#ifrs_{el}"
    instance = f'''<x:xbrl xmlns:x="{V.XBRLI}" xmlns:f="{IFRS}" xmlns:link="{V.LINK}" xmlns:xl="{V.XLINK}">
      <link:schemaRef xl:href="ext.xsd"/>
      <x:context id="ctx"><x:entity><x:identifier scheme="http://dart.fss.or.kr/ifrs/CIK">00000001</x:identifier></x:entity>
        <x:period><x:instant>2015-03-31</x:instant></x:period></x:context>
      <x:unit id="u"><x:measure>iso4217:KRW</x:measure></x:unit>
      <f:{el} contextRef="ctx" unitRef="u" decimals="0">1</f:{el}></x:xbrl>'''
    role = (f'<link:roleType roleURI="urn:r" id="r"><link:definition>{role_def}</link:definition>'
            '<link:usedOn>link:presentationLink</link:usedOn></link:roleType>') if with_role else ""
    arc = '<link:presentationArc xl:from="root" xl:to="fact"/>' if with_arc else ""
    pres = (f'<link:linkbase xmlns:link="{V.LINK}" xmlns:xl="{V.XLINK}">'
            + ('' if role_in_other_doc else role)
            + (f'<link:presentationLink xl:role="urn:r"><link:loc xl:label="fact" xl:href="{href}"/>'
               f'<link:loc xl:label="root" xl:href="x.xsd#root"/>{arc}</link:presentationLink>' if with_link else "")
            + '</link:linkbase>')
    xsd = (f'<xs:schema xmlns:xs="{XSD}" xmlns:link="{V.LINK}" targetNamespace="urn:ext">'
           + (role if role_in_other_doc else "")
           + (f'<xs:element id="ext_{el}" name="{el}"/>' if local_schema else "") + '</xs:schema>')
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("inst.xbrl", instance)
        z.writestr("ext.xsd", xsd)
        z.writestr("ext_pre.xml", pres)
        z.writestr("readme.txt", "not xml")
    return out.getvalue()


def firstbreak(**kw):
    fam = kw.get("family", "assets")
    return D.diagnose_item(item(fam), build(**kw))["trace"]["firstBreak"]


def test_full_evidence_is_accepted_by_reader_and_diagnostic():
    d = D.diagnose_item(item(), build())
    assert d["currentReaderPresentationEvidenceCount"] == 1
    assert d["trace"]["firstBreak"] == "READER_ACCEPTS_LOC_BUT_CALL_RETURNED_EMPTY"  # nothing broken to attribute


def test_inventory_lists_files_types_roles_refs():
    d = D.diagnose_item(item(), build())
    types = {f["name"]: f["type"] for f in d["files"]}
    assert types["inst.xbrl"] == "XBRL_INSTANCE" and types["ext.xsd"] == "XSD"
    assert types["ext_pre.xml"] == "LINKBASE:presentation" and types["readme.txt"] == "NON_XML"
    assert all(len(f["sha256"]) == 64 for f in d["files"]) and d["fileCount"] == 4
    assert d["roleTypes"][0]["usedOn"] == ["link:presentationLink"]
    assert d["references"][0]["kind"] == "schemaRef" and d["references"][0]["scope"] == "INSIDE_ZIP"
    assert d["presentationNetworks"][0]["kind"] == "BS"


@pytest.mark.parametrize("kw,expected", [
    ({"with_link": False}, "NO_PRESENTATION_LINKBASE_IN_ZIP"),
    ({"with_role": False}, "ROLE_DEFINITION_MISSING"),
    ({"role_def": "Some unrelated table"}, "ROLE_DEFINITION_WORDING_NOT_RECOGNISED"),
    ({"href": "x.xsd#other_Concept"}, "ELEMENT_NOT_IN_ANY_PRESENTATION_LOC"),
    ({"with_arc": False}, "LOC_NOT_CONNECTED_BY_LIVE_ARCS"),
    ({"href": "company.xsd#ext_Assets"}, "HREF_NOT_RESOLVED_TO_ELEMENT_QNAME"),
])
def test_first_break_classification(kw, expected):
    assert firstbreak(**kw) == expected


def test_role_definition_in_another_document_still_resolves():
    d = D.diagnose_item(item(), build(role_in_other_doc=True))
    assert d["presentationNetworks"][0]["definitionFound"] and d["presentationNetworks"][0]["kind"] == "BS"


def test_element_only_in_other_statement_role():
    assert firstbreak(role_def="Statement of cash flows") == "ELEMENT_ONLY_IN_OTHER_OR_UNKNOWN_ROLE"


def test_external_and_relative_scopes_are_reported_not_fetched():
    names = {"a.xsd", "sub/b.xsd"}
    assert D._scope("http://x.org/t/a.xsd#f", "doc.xml", names) == "EXTERNAL_URL_BASENAME_IN_ZIP"
    assert D._scope("http://x.org/t/z.xsd#f", "doc.xml", names) == "EXTERNAL_URL"
    assert D._scope("b.xsd#f", "sub/doc.xml", names) == "INSIDE_ZIP"
    assert D._scope("q.xsd#f", "doc.xml", names) == "RELATIVE_NOT_IN_ZIP"


def test_subset_is_deterministic_frozen_and_metadata_only():
    _, _, sample = V2.load_frozen(ROOT)
    spec = json.loads((ROOT / "research_specs/kr-original-xbrl-presentation-evidence-diagnostic-v1.json").read_text())
    subset = D.select_subset(sample["items"])
    assert subset == spec["subset"]["identities"] and len(subset) == len(set(subset)) == 12
    by = {i["identity"]: i for i in sample["items"]}
    assert {by[i]["family"] for i in subset} == set(V.RULES) and {by[i]["reportCode"] for i in subset} == set(D.STAGE_ORDER)
    assert {by[i]["basis"] for i in subset} == {"CFS", "OFS"}
    shuffled = list(reversed(sample["items"]))
    assert D.select_subset(shuffled) == subset


def test_closed_versions_are_unchanged_and_no_outcome_code_used():
    assert hashlib.sha256((ROOT / "research_specs/kr-original-xbrl-value-validation-v1-sample.json").read_bytes()).hexdigest() == V.SAMPLE_SHA256
    assert hashlib.sha256((ROOT / "research_specs/kr-original-xbrl-value-validation-v2.json").read_bytes()).hexdigest() == V2.PROTOCOL_SHA256
    assert json.loads((ROOT / "docs/results/kr-original-xbrl-value-validation-v2-report.json").read_text())["verdict"] == "BLOCKED"
    for name in ("pipeline/kr_xbrl_presentation_diagnostic.py", "scripts/diagnose_kr_xbrl_presentation_evidence.py"):
        code = (ROOT / name).read_text()
        for forbidden in ("kelly_portfolio", "portfolio_validation", "replay_valuation", "historical_outcomes", "docs/results/alpha"):
            assert forbidden not in code


def test_summary_counts():
    ds = [D.diagnose_item(item(), build(with_link=False)), D.diagnose_item(item(), build(with_link=False))]
    s = D.summarize(ds)
    assert s["firstBreakCounts"] == {"NO_PRESENTATION_LINKBASE_IN_ZIP": 2} and s["itemsWithAnyPresentationNetwork"] == 0
