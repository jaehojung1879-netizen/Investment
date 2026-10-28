"""Versioned original-number audit; the fixed68 acquisition CODE8 stays intact.

The two readers below retain legacy-v1 arithmetic/units/period/identity rules.
Only proven opposite-basis contexts are noncandidates (+6/-1 source change).
This is opt-in evidence inspection, not PIT cohort or research admission.
"""
from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal
import io
from pathlib import Path
import re
from urllib.parse import urlparse, parse_qs
import xml.etree.ElementTree as ET
import zipfile

from . import features as F
from . import pit_filing_evidence as LEGACY
from .pit_filing_evidence import XI, XD, ISO, _official_namespace, sha, package_namespaces

VERSION = "mixed-basis-v2"
LEGACY_MODULE_SHA256 = "df840a0b630190cb9d8239701d504d3bffae44e23ac214b3c2cd27f05f2919a6"


def identity():
    legacy = sha(Path(LEGACY.__file__).read_bytes())
    if legacy != LEGACY_MODULE_SHA256:
        raise ValueError("REGISTERED_LEGACY_NUMERIC_CODE_CHANGED")
    return {"version": VERSION, "moduleSha256": sha(Path(__file__).read_bytes()),
            "legacyModuleSha256": legacy, "cohortVerifierChanged": False,
            "sourceAdmissionAuthorized": False}


def _context(root, element, record, namespaces):
    ctxs = root.findall("{" + XI + "}context")
    matches = [x for x in ctxs if x.get("id") == element.get("contextRef")]
    if len(matches) != 1:
        raise ValueError("ORIGINAL_CONTEXT_AMBIGUOUS")
    ctx = matches[0]
    entity = ctx.find("{" + XI + "}entity/{" + XI + "}identifier")
    if entity is None or entity.text != record["corpCode"]:
        raise ValueError("ORIGINAL_CONTEXT_ISSUER_MISMATCH")
    scheme = urlparse(entity.get("scheme", ""))
    if scheme.netloc != "dart.fss.or.kr" or scheme.scheme not in ("http", "https"):
        raise ValueError("ORIGINAL_IDENTITY_SCHEME_UNPROVEN")
    members = ctx.findall(".//{" + XD + "}explicitMember")
    expected = "ConsolidatedMember" if record["fsDiv"] == "CFS" else "SeparateMember"
    if (len(members) != 1 or (members[0].text or "").split(":")[-1] not in ("ConsolidatedMember", "SeparateMember")
            or members[0].get("dimension", "").split(":")[-1] != "ConsolidatedAndSeparateFinancialStatementsAxis"
            or ctx.findall(".//{" + XD + "}typedMember")):
        raise ValueError("ORIGINAL_STATEMENT_BASIS_OR_DIMENSION_UNPROVEN")
    for qname in (members[0].text, members[0].get("dimension")):
        prefix, sep, _ = (qname or "").partition(":")
        if sep != ":" or not _official_namespace(namespaces.get(prefix, ""), "ifrs-full"):
            raise ValueError("ORIGINAL_BASIS_QNAME_UNPROVEN")
    # A proven opposite basis is not the requested fact; unproven contexts above still refuse.
    if (members[0].text or "").split(":")[-1] != expected:
        return None
    period = ctx.find("{" + XI + "}period")
    return {x.tag.rsplit("}", 1)[-1]: x.text for x in period} if period is not None else {}


def original_financial_facts(record, metadata, package, field):
    """Compare original XBRL facts to raw API values using exact Decimal amounts.

    Both stock balance and annual revenue require unambiguous issuer, CFS/OFS,
    exact source concept, KRW unit and period. No context/label guessing. This
    deliberately strict reader is a supported route for future evidence, NOT a
    certification that existing archives actually contain these ZIPs.
    """
    if package is None:
        return {"ready": False, "reasons": ["ORIGINAL_VALUE_VINTAGE_UNVERIFIED", "FISCAL_DURATION_UNPROVEN"],
                "start": None, "end": None}
    raw = package["raw"]
    if sha(raw) != package.get("sha256"):
        raise ValueError("ORIGINAL_PACKAGE_DIGEST_MISMATCH")
    if package.get("route") == "DART_PUBLIC_ATTACHMENT":
        from .xbrl_recovery import validate_public_provenance
        validate_public_provenance(metadata, package)
    else:
        url = urlparse(package["url"])
        if (url.scheme != "https" or url.netloc != "opendart.fss.or.kr" or url.path != "/api/fnlttXbrl.xml"
                or parse_qs(url.query) != {"rcept_no": [metadata["receipt"]], "reprt_code": ["11011"]}):
            raise ValueError("ORIGINAL_PACKAGE_RECEIPT_MISMATCH")
    roots = []
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        infos = z.infolist()
        if (len(infos) > 100 or sum(i.file_size for i in infos) > 32 * 1024 * 1024
                or len({i.filename for i in infos}) != len(infos)):
            raise ValueError("ORIGINAL_PACKAGE_UNSAFE_OR_DUPLICATE")
        for info in infos:
            if not info.filename.lower().endswith((".xml", ".xbrl")):
                continue
            body = z.read(info)
            if b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():
                raise ValueError("ORIGINAL_XML_DTD_REFUSED")
            root = ET.fromstring(body)
            if root.tag == "{" + XI + "}xbrl":
                roots.append(root)
    if len(roots) != 1:
        raise ValueError("ORIGINAL_INSTANCE_AMBIGUOUS")
    root = roots[0]
    namespaces = package_namespaces(raw)
    contexts = {}
    for key in ("sales", field):
        rows = F.matching_rows(record, key)
        candidate, reason = F.amount(record, key)
        if reason or len(rows) != 1:
            raise ValueError("RAW_FACT_UNRESOLVED:" + key)
        prefix, local = rows[0]["account_id"].split("_", 1)
        facts = []
        for x in root:
            if "}" not in x.tag or x.tag.rsplit("}", 1)[-1] != local:
                continue
            uri = x.tag[1:].split("}", 1)[0]
            if not _official_namespace(uri, prefix):
                continue
            ctx = _context(root, x, record, namespaces)
            if ctx is None:
                continue
            # Original revenue can be comparative too. Match the current fiscal
            # end-month, then require exactly one fact (no later-year backfill).
            end = ctx.get("endDate", ctx.get("instant", ""))
            if not end.startswith(metadata["periodEndMonth"] + "-"):
                continue
            units = [u for u in root.findall("{" + XI + "}unit") if u.get("id") == x.get("unitRef")]
            if len(units) != 1 or len(list(units[0])) != 1:
                raise ValueError("ORIGINAL_UNIT_UNPROVEN")
            measure = units[0].find("{" + XI + "}measure")
            # Resolve the QName prefix from namespace declarations in this very
            # instance, not merely its suffix (evil:KRW is not iso4217:KRW).
            unit_qname = (measure.text or "") if measure is not None else ""
            unit_prefix, sep, unit_local = unit_qname.partition(":")
            if sep != ":" or unit_local != "KRW" or namespaces.get(unit_prefix) != ISO:
                raise ValueError("ORIGINAL_UNIT_UNPROVEN")
            if x.get("decimals") != "INF" and not re.fullmatch(r"-?\d+", x.get("decimals", "")):
                raise ValueError("ORIGINAL_NUMERIC_ACCURACY_UNPROVEN")
            if x.get("{http://www.w3.org/2001/XMLSchema-instance}nil") in ("true", "1"):
                raise ValueError("ORIGINAL_NIL_FACT")
            value = Decimal(x.text or "NaN")
            if not value.is_finite() or value != candidate:
                raise ValueError("ORIGINAL_VALUE_MISMATCH:" + key)
            facts.append(ctx)
        if len(facts) != 1:
            raise ValueError("ORIGINAL_FACT_AMBIGUOUS_OR_MISSING:" + key)
        contexts[key] = facts[0]
    flow = contexts["sales"]
    start, end = F.day(flow.get("startDate")), F.day(flow.get("endDate"))
    expected_start = date(end.year if end.month == 12 else end.year - 1, end.month % 12 + 1, 1)
    if (start != expected_start or end.day != calendar.monthrange(end.year, end.month)[1]
            or contexts[field].get("instant") != end.isoformat()
            or end.year != record["fiscalYear"]):
        raise ValueError("FISCAL_DURATION_OR_BALANCE_END_MISMATCH")
    return {"ready": True, "reasons": [], "start": start.isoformat(), "end": end.isoformat(),
            "sourceSha256": sha(raw), "receipt": metadata["receipt"]}
