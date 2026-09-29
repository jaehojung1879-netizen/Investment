"""Outcome-free structural diagnostic of original DART XBRL packages.

Reads only accounting/XBRL source structure. It never edits the v1/v2 reader:
it calls it, unmodified, to reproduce its result and then decomposes where the
reader's presentation chain first breaks. Nothing here selects a validation
sample, repairs data or reads market or outcome artifacts.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import io
import posixpath
import xml.etree.ElementTree as ET
import zipfile

from . import kr_xbrl_value_validation as V

STUDY = "kr-original-xbrl-presentation-evidence-diagnostic-v1"
SEED = "KR_ORIGINAL_XBRL_PRESENTATION_DIAGNOSTIC_V1"
FAMILY_ORDER = ("net_income", "operating_cash_flow", "assets", "liabilities")
STAGE_ORDER = ("11013", "11012", "11014")
XSD = "http://www.w3.org/2001/XMLSchema"
XBRLI = V.XBRLI
LINK = V.LINK
XLINK = V.XLINK
LINK_KINDS = {"presentationLink": "presentation", "definitionLink": "definition", "labelLink": "label",
              "calculationLink": "calculation", "referenceLink": "reference", "footnoteLink": "footnote"}
SHORT = 160


def local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def select_subset(items):
    """Deterministic, identity/provenance-only subset of the frozen items."""
    def key(item):
        return hashlib.sha256((SEED + "|" + item["identity"]).encode()).hexdigest()
    chosen = []
    for fi, family in enumerate(FAMILY_ORDER):
        for si, stage in enumerate(STAGE_ORDER):
            want = "CFS" if (fi + si) % 2 == 0 else "OFS"
            cell = [i for i in items if i["family"] == family and i["reportCode"] == stage]
            preferred = [i for i in cell if i["basis"] == want] or cell
            chosen.append(min(preferred, key=key)["identity"])
    return chosen


def _classify(name, root):
    tag = root.tag
    if tag == "{" + XBRLI + "}xbrl":
        return "XBRL_INSTANCE"
    if tag == "{" + XSD + "}schema":
        return "XSD"
    if tag == "{" + LINK + "}linkbase":
        kinds = sorted({LINK_KINDS[local(e.tag)] for e in root.iter() if local(e.tag) in LINK_KINDS})
        return "LINKBASE:" + ("+".join(kinds) if kinds else "EMPTY")
    return "OTHER_XML"


def _scope(href, doc_name, names):
    """Where a reference points, without fetching anything."""
    path = href.partition("#")[0]
    if not path:
        return "SAME_DOCUMENT"
    if path.startswith(("http://", "https://")):
        base = path.rsplit("/", 1)[-1]
        return "EXTERNAL_URL" + ("_BASENAME_IN_ZIP" if base in {posixpath.basename(n) for n in names} else "")
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(doc_name), path))
    if resolved in names:
        return "INSIDE_ZIP"
    if posixpath.basename(path) in {posixpath.basename(n) for n in names}:
        return "INSIDE_ZIP_BY_BASENAME_ONLY"
    return "RELATIVE_NOT_IN_ZIP"


def parse_archive(raw):
    entries, docs = [], []
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            data = archive.read(info)
            entry = {"name": info.filename, "size": info.file_size, "sha256": hashlib.sha256(data).hexdigest(),
                     "xmlLike": data.lstrip().startswith(b"<")}
            if entry["xmlLike"]:
                try:
                    root, scopes = V.xml_document(data)
                    entry.update(type=_classify(info.filename, root), rootTag=root.tag,
                                 targetNamespace=root.get("targetNamespace"))
                    docs.append((info.filename, entry["sha256"], root, scopes))
                except (ET.ParseError, V.Ambiguous) as exc:
                    entry.update(type="UNPARSEABLE_XML", parseError=type(exc).__name__)
            else:
                entry["type"] = "NON_XML"
            entries.append(entry)
    return entries, docs


def references(docs, names):
    refs = []
    for name, _, root, _ in docs:
        for e in root.iter():
            t = local(e.tag)
            if t in ("schemaRef", "linkbaseRef", "roleRef", "arcroleRef"):
                href = e.get("{" + XLINK + "}href") or ""
                refs.append({"doc": name, "kind": t, "href": href[:300],
                             "roleURI": e.get("roleURI"), "arcroleURI": e.get("arcroleURI"),
                             "role": e.get("{" + XLINK + "}role"), "arcrole": e.get("{" + XLINK + "}arcrole"),
                             "scope": _scope(href, name, names) if href else None})
    return refs


def role_types(docs):
    result = []
    for name, _, root, _ in docs:
        for role in root.iter("{" + LINK + "}roleType"):
            definition = " ".join((d.text or "").strip() for d in role.findall("{" + LINK + "}definition"))
            result.append({"doc": name, "roleURI": role.get("roleURI"), "definition": definition,
                           "usedOn": [(u.text or "").strip() for u in role.findall("{" + LINK + "}usedOn")]})
    return result


def concept_ids(docs):
    ids = {}
    for name, _, root, _ in docs:
        if root.tag == "{" + XSD + "}schema":
            for node in root.findall("{" + XSD + "}element"):
                if node.get("id") and node.get("name"):
                    ids[node.get("id")] = {"doc": name, "name": node.get("name"),
                                           "ns": root.get("targetNamespace")}
    return ids


def presentation_networks(docs, definitions, names):
    networks = []
    for name, _, root, _ in docs:
        for link in root.iter("{" + LINK + "}presentationLink"):
            role = link.get("{" + XLINK + "}role")
            arcs = link.findall("{" + LINK + "}presentationArc")
            live = [a for a in arcs if a.get("use") != "prohibited"]
            connected = set()
            for a in live:
                connected.update((a.get("{" + XLINK + "}from"), a.get("{" + XLINK + "}to")))
            locs = []
            for loc in link.findall("{" + LINK + "}loc"):
                href = loc.get("{" + XLINK + "}href", "")
                label = loc.get("{" + XLINK + "}label")
                locs.append({"label": label, "href": href, "fragment": href.partition("#")[2],
                             "connected": label in connected, "scope": _scope(href, name, names)})
            definition = definitions.get(role)
            networks.append({"doc": name, "role": role, "definitionFound": definition is not None,
                             "definition": (definition or "")[:SHORT], "kind": V.statement_kind(definition or ""),
                             "locs": locs, "arcCount": len(arcs), "liveArcCount": len(live)})
    return networks


def _matches(loc, element):
    frag = loc["fragment"]
    return frag in ("ifrs_" + element, "ifrs-full_" + element) or frag.endswith("_" + element) or frag == element


def trace_fact(item, docs, definitions, networks, concepts, expectation):
    element = item["element"]
    hits = []
    for name, entry_hash, root, scopes in docs:
        if root.tag != "{" + XBRLI + "}xbrl":
            continue
        for e in root:
            if e.get("contextRef") == item["contextRef"] and local(e.tag) == element:
                hits.append((name, root, scopes, e))
    trace = {"instancePointerMatches": len(hits)}
    if not hits:
        trace["firstBreak"] = "FACT_POINTER_ABSENT"
        return trace
    name, root, scopes, fact = hits[0]
    qname = fact.tag
    ctx = V.context_info(root, scopes, fact.get("contextRef"))
    trace.update(elementQName=qname, isIfrsConcept=V.is_ifrs(qname), instance=name,
                 context={"entity": ctx["entity"], "entityScheme": ctx["entityScheme"], "period": ctx["period"],
                          "dimensions": ctx["dimensions"]},
                 unitRef=fact.get("unitRef"), decimals=fact.get("decimals"), rawText=fact.text,
                 expectation=expectation)
    matched = []
    for n in networks:
        for loc in n["locs"]:
            if _matches(loc, element):
                accepted = False
                frag = loc["fragment"]
                resolved = concepts.get(frag)
                resolved_q = ("{" + str(resolved["ns"]) + "}" + resolved["name"]) if resolved else None
                if resolved_q is None and V.re.match(r"https?://(?:xbrl\.ifrs\.org|xbrl\.iasb\.org)/", loc["href"]):
                    if frag in ("ifrs_" + element, "ifrs-full_" + element):
                        resolved_q = qname
                accepted = (resolved_q == qname and loc["connected"] and n["kind"] in expectation)
                matched.append({"doc": n["doc"], "role": n["role"], "roleDefinition": n["definition"],
                                "definitionFound": n["definitionFound"], "kind": n["kind"],
                                "href": loc["href"][:300], "fragment": frag, "connected": loc["connected"],
                                "scope": loc["scope"], "resolvesInLocalXsd": frag in concepts,
                                "resolvedQName": resolved_q, "readerWouldAccept": accepted})
    trace["matchedLocs"] = matched[:12]
    trace["matchedLocCount"] = len(matched)
    trace["networkCount"] = len(networks)
    trace["networksWithStatementKind"] = sum(1 for n in networks if n["kind"])
    if not networks:
        trace["firstBreak"] = "NO_PRESENTATION_LINKBASE_IN_ZIP"
    elif not any(n["kind"] for n in networks):
        trace["firstBreak"] = ("ROLE_DEFINITION_MISSING" if not any(n["definitionFound"] for n in networks)
                               else "ROLE_DEFINITION_WORDING_NOT_RECOGNISED")
    elif not matched:
        trace["firstBreak"] = "ELEMENT_NOT_IN_ANY_PRESENTATION_LOC"
    elif any(m["readerWouldAccept"] for m in matched):
        trace["firstBreak"] = "READER_ACCEPTS_LOC_BUT_CALL_RETURNED_EMPTY"
    elif not any(m["kind"] in expectation for m in matched):
        trace["firstBreak"] = "ELEMENT_ONLY_IN_OTHER_OR_UNKNOWN_ROLE"
    elif not any(m["connected"] and m["kind"] in expectation for m in matched):
        trace["firstBreak"] = "LOC_NOT_CONNECTED_BY_LIVE_ARCS"
    else:
        trace["firstBreak"] = "HREF_NOT_RESOLVED_TO_ELEMENT_QNAME"
    return trace


def diagnose_item(item, raw):
    entries, docs = parse_archive(raw)
    names = {e["name"] for e in entries}
    roles = role_types(docs)
    definitions = {}
    for r in roles:
        definitions.setdefault(r["roleURI"], r["definition"])
    concepts = concept_ids(docs)
    networks = presentation_networks(docs, definitions, names)
    expectation = sorted(V.RULES[item["family"]][1])
    trace = trace_fact(item, docs, definitions, networks, concepts, expectation)
    # The exact production call, unmodified, to reproduce the empty evidence.
    try:
        reader_evidence = len(V.presentation_evidence(docs, trace["elementQName"]))
    except KeyError:
        reader_evidence = None
    kinds = Counter(n["kind"] or "UNMAPPED" for n in networks)
    return {
        "identity": item["identity"], "family": item["family"], "reportCode": item["reportCode"],
        "basis": item["basis"], "receipt": item["receiptNos"][0], "ticker": item["ticker"],
        "corpCode": item["corpCode"], "zipSha256": hashlib.sha256(raw).hexdigest(), "fileCount": len(entries),
        "files": [{k: v for k, v in e.items() if k != "xmlLike"} for e in entries],
        "references": references(docs, names), "roleTypes": roles,
        "presentationNetworks": [
            {"doc": n["doc"], "role": n["role"], "definitionFound": n["definitionFound"], "definition": n["definition"],
             "kind": n["kind"], "locCount": len(n["locs"]), "arcCount": n["arcCount"], "liveArcCount": n["liveArcCount"],
             "sampleHrefs": [l["href"][:SHORT] for l in n["locs"][:4]],
             "hrefScopes": dict(Counter(l["scope"] for l in n["locs"]))} for n in networks],
        "networkKindCounts": dict(kinds), "localConceptIdCount": len(concepts),
        "trace": trace, "currentReaderPresentationEvidenceCount": reader_evidence,
    }


HYPOTHESES = {
    1: "role definition lives in a different document than the presentationLink",
    2: "role definition wording not handled by statement_kind",
    3: "presentation loc href is a relative company-taxonomy path",
    4: "fragment does not equal ifrs_<element> or ifrs-full_<element>",
    5: "concept exists only in an imported external taxonomy, not mapped locally",
    6: "local XSD concept id differs from the element QName",
    7: "extension element substitutes for the standard IFRS element",
    8: "presentationArc connectivity filtering excludes labels/locators",
    9: "linkbases are referenced but not embedded in the ZIP",
    10: "no relevant presentation network exists at all",
}


def summarize(diagnoses):
    breaks = Counter(d["trace"].get("firstBreak") for d in diagnoses)
    scopes = Counter()
    for d in diagnoses:
        for m in d["trace"].get("matchedLocs", []):
            scopes[m["scope"]] += 1
    referenced_not_embedded = sum(
        1 for d in diagnoses for r in d["references"]
        if r["kind"] == "linkbaseRef" and (r["scope"] == "RELATIVE_NOT_IN_ZIP"
                                           or (r["scope"] or "").startswith("EXTERNAL_URL")))
    return {
        "items": len(diagnoses), "firstBreakCounts": dict(breaks), "matchedLocScopes": dict(scopes),
        "readerEmptyCount": sum(1 for d in diagnoses if d["currentReaderPresentationEvidenceCount"] == 0),
        "itemsWithAnyPresentationNetwork": sum(1 for d in diagnoses if d["presentationNetworks"]),
        "itemsWithStatementKindNetwork": sum(1 for d in diagnoses if d["trace"].get("networksWithStatementKind")),
        "itemsWithMatchedLoc": sum(1 for d in diagnoses if d["trace"].get("matchedLocCount")),
        "linkbaseRefsNotEmbedded": referenced_not_embedded,
        "networkKindsSeen": dict(sum((Counter(d["networkKindCounts"]) for d in diagnoses), Counter())),
    }
