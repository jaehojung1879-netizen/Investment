"""Read original annual-report evidence; raw API receipt != original value vintage.

No I/O. Callers supply pinned bytes. Missing source packages never become an
implicit attestation. The existing source archives contain main/overview pages,
not the original working-capital financial facts; those two tiers stay apart.
"""
from __future__ import annotations

from datetime import date
import calendar
from decimal import Decimal
from html import unescape
import hashlib
import io
import re
from urllib.parse import urlparse, parse_qs
import xml.etree.ElementTree as ET
import zipfile

from . import features as F

XI = "http://www.xbrl.org/2003/instance"
XD = "http://xbrl.org/2006/xbrldi"
ISO = "http://www.xbrl.org/2003/iso4217"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def normal_name(value):
    return re.sub(r"\s+", "", str(value).replace("주식회사", "").replace("(주)", "").replace("㈜", ""))


def original_main(target, raw, url):
    """Verify preserved listing-row metadata against the original main page.

    'Earliest non-correction' is the old collector's listing selection, not a
    claim that this function proved completeness of every DART listing page.
    Nothing here certifies the original financial amounts or fiscal start.
    """
    listing = target.get("listingMetadata", {})
    receipts = target.get("receiptNos", [])
    if len(receipts) != 1 or not re.fullmatch(r"\d{14}", str(receipts[0])):
        raise ValueError("ORIGINAL_RECEIPT_UNRESOLVED")
    receipt = receipts[0]
    parsed = urlparse(url)
    if (parsed.scheme != "https" or parsed.netloc != "dart.fss.or.kr" or parsed.path != "/dsaf001/main.do"
            or parse_qs(parsed.query) != {"rcpNo": [receipt]}):
        raise ValueError("ORIGINAL_MAIN_URL_MISMATCH")
    name = listing.get("report_nm", "")
    period = re.fullmatch(r"사업보고서\s*\((\d{4})\.(\d{2})\)", name)
    if (period is None or target.get("originalStatus") != "EARLIEST_NON_CORRECTION_ANNUAL_LIST_ROW"
            or listing.get("rcept_no") != receipt or listing.get("rcept_dt") != receipt[:8]
            or target.get("availableFrom") != date.fromisoformat(f"{receipt[:4]}-{receipt[4:6]}-{receipt[6:8]}").isoformat()
            or target.get("identityBasis") != "EXACT_STOCK_CODE"
            or listing.get("stock_code") != target.get("ticker", "").split(".")[0]
            or listing.get("corp_code") != target.get("corpCode")
            or target.get("reportPeriod") != f"{period[1]}-{period[2]}"
            or str(target.get("fiscalYear")) != period[1]):
        raise ValueError("ORIGINAL_LISTING_IDENTITY_OR_PERIOD_MISMATCH")
    date(int(period[1]), int(period[2]), 1)
    text = raw.decode("utf-8")
    titles = re.findall(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
    expected_date = f"{receipt[:4]}.{receipt[4:6]}.{receipt[6:8]}"
    title = unescape(re.sub("<[^>]+>", "", titles[0])).strip() if titles else ""
    parts = title.split("/")
    nodes = set(re.findall(r"node\d+\[['\"]rcpNo['\"]\]\s*=\s*['\"](\d+)['\"]", text))
    if (len(parts) != 3 or normal_name(parts[0]) != normal_name(listing.get("corp_name"))
            or parts[1] != "사업보고서" or parts[2] != expected_date or nodes != {receipt}):
        raise ValueError("ORIGINAL_MAIN_TITLE_OR_RECEIPT_MISMATCH")
    return {"ticker": target["ticker"], "corpCode": target["corpCode"], "receipt": receipt,
            "availableFrom": target["availableFrom"], "fiscalYear": target["fiscalYear"],
            "periodEndMonth": target["reportPeriod"], "companyName": parts[0],
            "mainSha256": sha(raw), "url": url, "metadataTier": "ORIGINAL_LIST_ROW_AND_MAIN_MATCH",
            "originalFinancialValuesVerified": False, "fiscalStartVerified": False}


def _official_namespace(uri, prefix):
    u = urlparse(uri)
    if prefix.startswith("ifrs"):
        return u.scheme in ("http", "https") and u.netloc in ("xbrl.ifrs.org", "xbrl.iasb.org")
    return prefix == "dart" and u.scheme in ("http", "https") and u.netloc == "dart.fss.or.kr"


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
    if (len(members) != 1 or (members[0].text or "").split(":")[-1] != expected
            or members[0].get("dimension", "").split(":")[-1] != "ConsolidatedAndSeparateFinancialStatementsAxis"
            or ctx.findall(".//{" + XD + "}typedMember")):
        raise ValueError("ORIGINAL_STATEMENT_BASIS_OR_DIMENSION_UNPROVEN")
    for qname in (members[0].text, members[0].get("dimension")):
        prefix, sep, _ = (qname or "").partition(":")
        if sep != ":" or not _official_namespace(namespaces.get(prefix, ""), "ifrs-full"):
            raise ValueError("ORIGINAL_BASIS_QNAME_UNPROVEN")
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


def package_namespaces(raw):
    """Reject prefix rebinding rather than guess a lexical QName's namespace."""
    out = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for name in z.namelist():
            if not name.lower().endswith((".xml", ".xbrl")):
                continue
            body = z.read(name)
            root = ET.fromstring(body)
            if root.tag != "{" + XI + "}xbrl":
                continue
            for _, pair in ET.iterparse(io.BytesIO(body), events=("start-ns",)):
                prefix, uri = pair
                if prefix in out and out[prefix] != uri:
                    raise ValueError("ORIGINAL_NAMESPACE_REBINDING_UNPROVEN")
                out[prefix] = uri
    return out
