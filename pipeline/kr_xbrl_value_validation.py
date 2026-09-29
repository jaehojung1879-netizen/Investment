"""Independent fixed-sample XBRL reader. No production extraction imports.

Resolve recorded pointers against original bytes instead of repeating the
production window/pool selection. Unsupported or incomplete semantic evidence
blocks MATCH. Amounts are Decimal throughout, including JSON decoding.
"""
from __future__ import annotations

from collections import Counter
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile

from . import kr_xbrl_validation_sample as S

FREEZE_COMMIT = "e756f0aa4457aaa4840ea359df7eb9276ce77731"
PROTOCOL_SHA256 = "0aec37a4daed0d0765a25846cbdcbc410d70098fbed9340926a5376dd791cb0a"
SAMPLE_SHA256 = "590513ede1c8bd06d701f22f4b1aa01bcf8b004aa30b9410540865696e863e70"
XBRLI = "http://www.xbrl.org/2003/instance"
XBRLDI = "http://xbrl.org/2006/xbrldi"
LINK = "http://www.xbrl.org/2003/linkbase"
XLINK = "http://www.w3.org/1999/xlink"
ISO = "http://www.xbrl.org/2003/iso4217"
NIL = "{http://www.w3.org/2001/XMLSchema-instance}nil"
RULES = {
    "net_income": ("ProfitLoss", {"IS", "CIS"}, "duration", "thstrm_add_amount"),
    "operating_cash_flow": ("CashFlowsFromUsedInOperatingActivities", {"CF"}, "duration", "thstrm_amount"),
    "assets": ("Assets", {"BS"}, "instant", "thstrm_amount"),
    "liabilities": ("Liabilities", {"BS"}, "instant", "thstrm_amount"),
}
CLASSIFICATIONS = ("MATCH", "VALUE_MISMATCH", "SEMANTIC_MISMATCH", "METADATA_MISMATCH",
                   "AMBIGUOUS_SOURCE_FACT", "SOURCE_UNAVAILABLE", "INFRASTRUCTURE_ERROR")


# Entity identification schemes admitted as a DART corporation-code scheme in
# addition to the v1 host rule. v1 admits none; v2 (see
# kr_xbrl_value_validation_v2) passes exactly one, by exact string equality.
V1_CORP_CODE_SCHEMES = frozenset()


class Ambiguous(ValueError):
    pass


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def load_frozen(repo: Path):
    """Require exact bytes and actual pre-source commit in this history."""
    subprocess.run(["git", "merge-base", "--is-ancestor", FREEZE_COMMIT, "HEAD"],
                   cwd=repo, check=True, capture_output=True)
    result = []
    for suffix, seal in ((".json", PROTOCOL_SHA256), ("-sample.json", SAMPLE_SHA256)):
        name = "research_specs/" + S.STUDY + suffix
        raw = (repo / name).read_bytes()
        if sha256(raw) != seal:
            raise ValueError("FROZEN_FILE_CHANGED")
        frozen = subprocess.check_output(["git", "show", FREEZE_COMMIT + ":" + name], cwd=repo)
        if raw != frozen:
            raise ValueError("FREEZE_COMMIT_BYTES_DIFFER")
        result.append(json.loads(raw))
    protocol, sample = result
    if len(sample["items"]) != 60 or protocol["sample"]["manifestSha256"] != SAMPLE_SHA256:
        raise ValueError("SAMPLE_INTEGRITY_ERROR")
    return protocol, sample


def decimal_value(text):
    if not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)", str(text).strip()):
        raise Ambiguous("invalid XBRL decimal lexical form")
    value = Decimal(str(text).strip())
    if not value.is_finite():
        raise Ambiguous("nonfinite amount")
    return value


def equal_at_precision(source: Decimal, candidate: Decimal, decimals=None, precision=None):
    """Exact comparison or same declared rounding bucket; never float epsilon."""
    if not source.is_finite() or not candidate.is_finite():
        raise Ambiguous("nonfinite amount")
    if decimals is not None and precision is not None:
        raise Ambiguous("both decimals and precision declared")
    if decimals is None and precision is None:
        raise Ambiguous("no declared numeric accuracy")
    declaration = decimals if decimals is not None else precision
    if declaration == "INF":
        return source == candidate
    if not re.fullmatch(r"-?[0-9]+", str(declaration)):
        raise Ambiguous("invalid accuracy declaration")
    n = int(declaration)
    if abs(n) > 1000:
        raise Ambiguous("unsupported accuracy magnitude")
    if precision is not None:
        if n <= 0 or source == 0:
            raise Ambiguous("invalid or indeterminate significant precision")
        n = n - source.copy_abs().adjusted() - 1
    if source == candidate:
        return True
    if source.is_signed() != candidate.is_signed():
        return False
    with localcontext() as ctx:
        ctx.prec = max(len(source.as_tuple().digits), len(candidate.as_tuple().digits),
                       abs(source.adjusted()), abs(candidate.adjusted())) + abs(n) + 20
        quantum = Decimal(1).scaleb(-n)
        return source.quantize(quantum, rounding=ROUND_HALF_EVEN) == candidate.quantize(
            quantum, rounding=ROUND_HALF_EVEN)


def xml_document(raw):
    """Scoped namespace maps, so QName-valued units/dimensions are expanded."""
    if re.search(br"<!\s*(?:DOCTYPE|ENTITY)", raw, re.I):
        raise Ambiguous("DTD/entity declaration refused")
    scopes, stack, pending, root = {}, [], [], None
    for event, obj in ET.iterparse(io.BytesIO(raw), events=("start-ns", "start", "end")):
        if event == "start-ns":
            pending.append(obj)
        elif event == "start":
            scope = dict(stack[-1]) if stack else {}
            scope.update(pending)
            pending = []
            stack.append(scope)
            scopes[id(obj)] = scope
            if root is None:
                root = obj
        else:
            stack.pop()
    return root, scopes


def expand(text, node, scopes):
    prefix, sep, local = str(text or "").strip().partition(":")
    if not sep:
        local, prefix = prefix, ""
    namespace = scopes[id(node)].get(prefix)
    if not namespace or not local:
        raise Ambiguous("unresolved QName")
    return "{" + namespace + "}" + local


def is_ifrs(qname):
    return bool(re.match(r"^\{https?://(?:xbrl\.ifrs\.org|xbrl\.iasb\.org)/taxonomy/[^}]+\}", qname))


def archive_documents(raw):
    documents = []
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        if len(infos) > 2000 or sum(i.file_size for i in infos) > 200_000_000:
            raise Ambiguous("archive exceeds independent-reader safety limits")
        if len({i.filename for i in infos}) != len(infos):
            raise Ambiguous("duplicate archive entry names")
        for info in infos:
            if info.is_dir():
                continue
            if info.file_size > 64_000_000:
                raise Ambiguous("oversized source entry")
            data = archive.read(info)
            if not data.lstrip().startswith(b"<"):
                continue
            try:
                root, scopes = xml_document(data)
            except ET.ParseError:
                if info.filename.lower().endswith((".xml", ".xbrl", ".xsd")):
                    raise Ambiguous("malformed XML source entry") from None
                continue
            documents.append((info.filename, sha256(data), root, scopes))
    return documents


def context_info(root, scopes, ref):
    matches = [e for e in root.findall("{" + XBRLI + "}context") if e.get("id") == ref]
    if len(matches) != 1:
        raise Ambiguous("context identifier not unique/resolved within instance")
    c = matches[0]
    ids = c.findall("{" + XBRLI + "}entity/{" + XBRLI + "}identifier")
    periods = c.findall("{" + XBRLI + "}period")
    if len(ids) != 1 or len(periods) != 1:
        raise Ambiguous("entity/period not uniquely specified")
    period = {}
    for e in periods[0]:
        key = e.tag.rsplit("}", 1)[-1]
        if key in period:
            raise Ambiguous("duplicate context period field")
        period[key] = (e.text or "").strip()
    dims = []
    for container in c.iter():
        if container.tag not in ("{" + XBRLI + "}segment", "{" + XBRLI + "}scenario"):
            continue
        for e in container:
            if e.tag != "{" + XBRLDI + "}explicitMember":
                raise Ambiguous("unsupported typed or non-dimensional context qualifier")
            dims.append((expand(e.get("dimension"), e, scopes), expand(e.text, e, scopes)))
    return {"entity": (ids[0].text or "").strip(), "entityScheme": ids[0].get("scheme"),
            "period": period, "dimensions": sorted(dims)}


def unit_info(root, scopes, ref):
    units = [e for e in root.findall("{" + XBRLI + "}unit") if e.get("id") == ref]
    if len(units) != 1:
        raise Ambiguous("unit identifier not unique/resolved within instance")
    if len(units[0]) != 1 or units[0][0].tag != "{" + XBRLI + "}measure":
        return "COMPOUND_OR_DIVIDE_UNIT"
    node = units[0][0]
    return expand(node.text, node, scopes)


def statement_kind(definition):
    text = definition.casefold()
    # Equity must precede income: a long equity role can mention income too.
    for kind, patterns in (("SCE", ("changes in equity", "자본변동표")),
                           ("CF", ("cash flows", "cash flow statement", "현금흐름표")),
                           ("BS", ("financial position", "balance sheet", "재무상태표", "대차대조표")),
                           ("CIS", ("comprehensive income", "포괄손익계산서")),
                           ("IS", ("income statement", "profit or loss", "손익계산서"))):
        if any(p in text for p in patterns):
            return kind
    return None


def presentation_evidence(documents, element):
    definitions, concepts, evidence = {}, {}, []
    xsd = "{http://www.w3.org/2001/XMLSchema}"
    for _, _, root, _ in documents:
        for role in root.iter("{" + LINK + "}roleType"):
            definitions[role.get("roleURI")] = " ".join(role.itertext())
        if root.tag == xsd + "schema":
            for node in root.findall(xsd + "element"):
                if node.get("id") and node.get("name"):
                    concepts[node.get("id")] = "{" + str(root.get("targetNamespace")) + "}" + node.get("name")
    for name, entry_hash, root, _ in documents:
        for link in root.iter("{" + LINK + "}presentationLink"):
            role = link.get("{" + XLINK + "}role")
            definition = definitions.get(role, "")
            kind = statement_kind(definition)
            if kind is None:
                continue
            connected = set()
            for arc in link.findall("{" + LINK + "}presentationArc"):
                if arc.get("use") == "prohibited":
                    continue
                connected.update((arc.get("{" + XLINK + "}from"), arc.get("{" + XLINK + "}to")))
            for loc in link.findall("{" + LINK + "}loc"):
                if loc.get("{" + XLINK + "}label") not in connected:
                    continue
                href = loc.get("{" + XLINK + "}href", "")
                fragment = href.partition("#")[2]
                resolved = concepts.get(fragment)
                # External taxonomy href must itself identify an IFRS authority;
                # an arbitrary custom '#ifrs_Assets' fragment proves nothing.
                if resolved is None and re.match(r"https?://(?:xbrl\.ifrs\.org|xbrl\.iasb\.org)/", href):
                    if fragment in ("ifrs_" + element.rsplit("}", 1)[-1],
                                    "ifrs-full_" + element.rsplit("}", 1)[-1]):
                        resolved = element
                if resolved == element:
                    evidence.append({"entry": name, "entrySha256": entry_hash, "role": role,
                                     "definition": definition, "statement": kind, "href": href})
    return evidence


def outcome(item, candidate_value, status, reason, **evidence):
    return {"identity": item["identity"], "sampleItem": item,
            "candidateValue": str(candidate_value) if candidate_value is not None else None,
            "classification": status, "reason": reason, **evidence}


def validate_item(item, candidate_value, raw=None, filing_rows=None,
                  corp_code_schemes=V1_CORP_CODE_SCHEMES, presentation_gate=True):
    """Read source fact by recorded pointer, independently validate its semantics."""
    def result(status, reason, **evidence):
        return outcome(item, candidate_value, status, reason, **evidence)

    if raw is None:
        return result("SOURCE_UNAVAILABLE", "BLOCKED_ON_SOURCE_ACCESS: original ZIP bytes unavailable")
    actual_hash = sha256(raw)
    if actual_hash != item.get("zipSha256"):
        return result("AMBIGUOUS_SOURCE_FACT", "original archive hash not reproduced; source version unresolved",
                      retrievedZipSha256=actual_hash)
    receipts = item.get("receiptNos") or []
    if len(receipts) != 1:
        return result("METADATA_MISMATCH", "candidate does not identify one original receipt")
    if filing_rows is None:
        return result("AMBIGUOUS_SOURCE_FACT", "independent DART filing-index identity evidence absent")
    rows = [r for r in filing_rows if str(r.get("rcept_no")) == receipts[0]]
    if len(rows) != 1:
        return result("AMBIGUOUS_SOURCE_FACT", "receipt not uniquely confirmed in independently obtained index")
    filing = rows[0]
    end = str(item["fiscalYear"]) + {"11013": "-03-31", "11012": "-06-30", "11014": "-09-30"}[item["reportCode"]]
    name = str(filing.get("report_nm", ""))
    if (str(filing.get("corp_code")) != item["corpCode"]
            or str(filing.get("stock_code")) != item["stockCode"]
            or str(filing.get("rcept_dt")) != str(item.get("availableFrom", "")).replace("-", "")
            or item["ticker"].split(".")[0] != item["stockCode"]):
        return result("METADATA_MISMATCH", "filing-index issuer/stock/receipt-date differs", filingIndexRow=filing)
    report_word = "반기보고서" if item["reportCode"] == "11012" else "분기보고서"
    if name != report_word + " (" + end[:7].replace("-", ".") + ")":
        # Whitespace variation is not a different filing.
        if re.sub(r"\s", "", name) != report_word + "(" + end[:7].replace("-", ".") + ")":
            return result("METADATA_MISMATCH", "filing-index report/stage is different or amended", filingIndexRow=filing)
    detailed, ev = [], None
    try:
        documents = archive_documents(raw)
        matches = []
        for entry, entry_hash, root, scopes in documents:
            if root.tag != "{" + XBRLI + "}xbrl":
                continue
            for e in root:
                if e.get("contextRef") == item.get("contextRef") and e.tag.rsplit("}", 1)[-1] == item.get("element"):
                    matches.append((entry, entry_hash, root, scopes, e))
        if not matches:
            raise Ambiguous("recorded element/context pointer absent from original instance")
        if len(matches) > 1:
            signatures = set()
            for _, _, root, scopes, fact in matches:
                signatures.add(S.digest({"element": fact.tag,
                    "context": context_info(root, scopes, fact.get("contextRef")),
                    "unit": unit_info(root, scopes, fact.get("unitRef")),
                    "value": str(decimal_value(fact.text or "").normalize()),
                    "attributes": dict(fact.attrib)}))
            if len(signatures) > 1:
                return result("AMBIGUOUS_SOURCE_FACT", "duplicate source pointers disagree",
                              sourceFacts=[{"entry": n, "entrySha256": h,
                                            "factXml": ET.tostring(f, encoding="unicode")}
                                           for n, h, _, _, f in matches])
        values, detailed = [], []
        for entry, entry_hash, root, scopes, fact in matches:
            if not is_ifrs(fact.tag):
                raise Ambiguous("local-name match does not prove an IFRS concept identity")
            concept, statements, period_type, _ = RULES[item["family"]]
            context = context_info(root, scopes, fact.get("contextRef"))
            unit = unit_info(root, scopes, fact.get("unitRef"))
            ev = {"entry": entry, "entrySha256": entry_hash, "elementQName": fact.tag,
                  "contextRef": fact.get("contextRef"), "context": context, "unitRef": fact.get("unitRef"),
                  "unit": unit, "decimals": fact.get("decimals"), "precision": fact.get("precision"),
                  "rawText": fact.text}
            if fact.tag.rsplit("}", 1)[-1] != concept or item["statement"] not in statements:
                return result("SEMANTIC_MISMATCH", "candidate account/statement is not target family", source=ev)
            expected_period = ({"instant": end} if period_type == "instant" else
                               {"startDate": str(item["fiscalYear"]) + "-01-01", "endDate": end})
            if context["period"] != expected_period:
                return result("SEMANTIC_MISMATCH", "prior/current/instant/duration period substitution", source=ev)
            scheme = context.get("entityScheme") or ""
            if scheme in corp_code_schemes:
                # Exact-string scheme independently established as a DART
                # corporation-code scheme: the identifier must be the corpCode.
                # No stockCode substitution is allowed under it.
                if context["entity"] != item["corpCode"]:
                    return result("METADATA_MISMATCH",
                                  "context entity identifier differs from the frozen corpCode", source=ev)
            else:
                if context["entity"] not in (item["corpCode"], item["stockCode"]):
                    raise Ambiguous("context entity uses an identifier not independently mapped to issuer")
                if not re.fullmatch(r"https?://(?:dart|opendart)\.fss\.or\.kr/?", scheme):
                    raise Ambiguous("context entity scheme not independently established as DART identity")
            dims = context["dimensions"]
            basis = None
            if len(dims) == 1:
                axis, member = dims[0]
                if (is_ifrs(axis) and is_ifrs(member)
                        and axis.rsplit("}", 1)[-1] == "ConsolidatedAndSeparateFinancialStatementsAxis"):
                    basis = {"ConsolidatedMember": "CFS", "SeparateMember": "OFS"}.get(member.rsplit("}", 1)[-1])
            if dims and basis is None:
                return result("SEMANTIC_MISMATCH", "context carries a component/prior/unsupported dimension", source=ev)
            if basis is None:
                raise Ambiguous("unqualified context does not independently prove consolidated/separate basis")
            if basis != item["basis"]:
                return result("SEMANTIC_MISMATCH", "statement basis differs", source=ev)
            if unit != "{" + ISO + "}KRW" or item["currency"] != "KRW":
                return result("SEMANTIC_MISMATCH", "currency or unit is not candidate KRW monetary unit", source=ev)
            if fact.get("unitRef") != item["unitRef"] or fact.get("decimals") != item["decimals"]:
                return result("METADATA_MISMATCH", "unitRef/decimals provenance differs", source=ev)
            roles = presentation_evidence(documents, fact.tag)
            ev["presentation"] = roles
            if presentation_gate:
                if not any(r["statement"] in statements for r in roles):
                    raise Ambiguous("source presentation does not prove required financial statement")
            else:
                # v3: membership is descriptive corroboration only. The concept is
                # identified by IFRS-namespace expanded QName (checked above through
                # is_ifrs and the frozen local name); nothing is assumed for others.
                ev["conceptIdentity"] = {"namespace": fact.tag.partition("}")[0].lstrip("{"),
                                         "localName": fact.tag.rsplit("}", 1)[-1], "ifrsNamespace": True}
                ev["presentationCorroboratesStatement"] = any(r["statement"] in statements for r in roles)
            if fact.get(NIL) in ("true", "1"):
                raise Ambiguous("source fact is nil")
            if any(fact.get(a) is not None for a in ("scale", "sign", "format")):
                raise Ambiguous("unsupported standard-XBRL transformation attribute")
            number = decimal_value(fact.text or "")
            values.append(number)
            ev["sourceValue"] = str(number)
            detailed.append(ev)
        if len(set(values)) != 1:
            return result("AMBIGUOUS_SOURCE_FACT", "duplicate source pointers disagree", sourceFacts=detailed)
        candidate = Decimal(str(candidate_value))
        comparisons = [equal_at_precision(v, candidate, d["decimals"], d["precision"])
                       for v, d in zip(values, detailed)]
        if not all(comparisons):
            return result("VALUE_MISMATCH", "candidate amount differs at source-declared precision",
                          sourceFacts=detailed, filingIndexRow=filing)
        return result("MATCH", "independently resolved source identity, semantics and Decimal amount",
                      sourceFacts=detailed, filingIndexRow=filing, sourceZipSha256=actual_hash)
    except (Ambiguous, ET.ParseError, zipfile.BadZipFile, InvalidOperation) as exc:
        return result("AMBIGUOUS_SOURCE_FACT", str(exc), sourceZipSha256=actual_hash,
                      sourceFacts=detailed, lastSourceFact=ev)


def summarize(results, expected=60):
    counts = {c: 0 for c in CLASSIFICATIONS}
    for r in results:
        counts[r["classification"]] += 1
    if any(counts[c] for c in ("VALUE_MISMATCH", "SEMANTIC_MISMATCH", "METADATA_MISMATCH")):
        verdict = "FAIL"
    elif len(results) != expected or counts["INFRASTRUCTURE_ERROR"]:
        verdict = "INFRASTRUCTURE_ERROR"
    elif counts["MATCH"] == expected:
        verdict = "PASS"
    else:
        verdict = "BLOCKED"
    report = {"verdict": verdict, "counts": counts, "expected": expected, "audited": len(results)}
    if verdict == "PASS":
        report["descriptiveTwoSided95UpperMismatchBound"] = 1 - 0.025 ** (1 / expected)
    return report


def verify_frame(root, protocol, sample):
    original = S.permitted_path(root, "ledger/fundamentals/kr-xbrl-original/dart-xbrl-2015.jsonl.gz")
    if sha256(original.read_bytes()) != protocol["frame"]["originalShardSha256"]:
        raise ValueError("ORIGINAL_SHARD_CHANGED")
    frame = S.frame_from_file(root)
    if S.digest(frame) != protocol["frame"]["sha256"] or S.select(frame) != sample["items"]:
        raise ValueError("FIXED_SAMPLE_REPRODUCTION_FAILED")
    counts = Counter(r["family"] for r in sample["items"])
    if counts != dict.fromkeys(S.FAMILIES, 15):
        raise ValueError("SAMPLE_QUOTAS_CHANGED")
    for name, expected in protocol["candidate"]["gitBlobSha1"].items():
        path = S.permitted_path(root, "ledger/fundamentals/kr-candidate-merged/" + name)
        raw = path.read_bytes()
        actual = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        if actual != expected:
            raise ValueError("CANDIDATE_SHARD_CHANGED")
