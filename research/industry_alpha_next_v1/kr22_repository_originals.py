"""Reconcile the KR22 DART request plan with original filings the repository already holds, and re-read them.

SOURCE-ONLY. No network, price, return, label or outcome. The industry foundation v2 already ran list.json A001 for
every ever-Top120 issuer and kept the public-viewer originals (`dsaf001/main.do` plus the `회사의 개요` / `사업의 내용`
sections from `report/viewer.do`) of the earliest non-correction annual report for each issuer-year. Those bytes sit in
`data/kr-industry-membership-foundation-v2`, matched by exact corp code. `kr22-collection-plan.json` was built without
reading them, so this module measures how much of the plan they already answer, publishes the request list that
genuinely remains, and re-reads every retained in-window section for explicit industry statements.

Nothing is admitted. Each explicit KSIC candidate is passed, unchanged, through `kr_industry_membership_v2.admit` with
the observation the v2 builder itself would construct. A pass only means the provenance is mechanically sound. The
frozen v2 template (issuer-subject sentences only) did not produce the row, and the frozen v4 crosswalk decides the
group, so admission remains a foundation decision.
"""
from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import html
import json
import re
import sys
from pathlib import Path

from pipeline import kr_industry_membership_v2 as V
from pipeline import kr_industry_membership_v4 as V4

from . import kr22_collection_plan as P
from . import kr22_recovery as K

HERE = Path(__file__).resolve().parent
V2 = Path("data/kr-industry-membership-foundation-v2")
V1 = Path("data/kr-industry-membership-foundation-v1")
CROSSWALK = Path("research_specs/kr-industry-membership-foundation-v4/crosswalk.json")
REPORT = HERE / "kr22-repository-originals.json"
REMAINING_PLAN = HERE / "kr22-remaining-plan.json"
CONTRACT = "KR22_REPOSITORY_ORIGINALS_RECONCILIATION_V1"


def load_v2(root=K.ROOT):
    """v2 inventory rows and the annual originals v2 and v1 retained, every archive and blob re-hashed as the builders do."""
    root = Path(root)
    inventory = []
    for path in sorted((root / V2 / "inventory").glob("batch-*/inventory.json")):
        inventory.extend(json.loads(path.read_text()))
    records, sources = {}, {}
    # v2 kept its own annual originals and reused v1's retained ones; both are read, v2 first.
    manifests = sorted((root / V2 / "acquired-dart/annual").glob("batch-*/manifest-originals.json")) + \
        sorted((root / V1 / "acquired-dart").glob("manifest-*.json"))
    for path in manifests:
        manifest = json.loads(path.read_text())
        raw = (path.parent / manifest["archive"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != manifest["archiveSha256"]:
            raise ValueError("V2_ARCHIVE_CHANGED: " + str(path))
        for sha, b64 in json.loads(gzip.decompress(raw)).items():
            body = base64.b64decode(b64)
            if hashlib.sha256(body).hexdigest() != sha:
                raise ValueError("V2_SOURCE_SHA_CHANGED: " + sha)
            sources[sha] = body
        for record in manifest["records"]:
            receipt = re.search(r"rcpNo=(\d{14})", record["responses"][0]["url"]).group(1)
            if "target" in record and record["target"]["receiptNos"][0] != receipt:
                raise ValueError("RECORD_TARGET_DIFFERS_FROM_MAIN_URL: " + receipt)
            records.setdefault(receipt, record)
    return inventory, records, sources


def plain(body):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", body.decode("utf-8", errors="strict"))))


def stated_hierarchy(text, code):
    """Labels the same filing states for the prefixes of `code` (e.g. '582 소프트웨어 개발및 공급업' for J58222)."""
    if not code:
        return []
    digits = re.sub(r"\D", "", code)
    out = []
    for n in (2, 3, 4):
        m = re.search(r"(?<!\d)" + digits[:n] + r"\s+([가-힣][가-힣 ,ㆍ·및]{1,40}?업)(?=\s|$)", text)
        if m:
            out.append({"level": n, "code": digits[:n], "label": "".join(m.group(1).split())})
    return out


def candidate_rows(target, record, sources, crosswalk):
    """Explicit KSIC statements in one retained receipt, each with the unchanged v2 admit verdict and crosswalk group."""
    main = record["responses"][0]
    main_raw = sources.get(main.get("sha256"))
    identity = "openCorpInfoNew('" + target["corpCode"] + "',"
    release = "%s-%s-%s" % (target["receiptNos"][0][:4], target["receiptNos"][0][4:6], target["receiptNos"][0][6:8])
    rows = []
    for section in record.get("sections", []):
        if section["node"]["rcpNo"] != target["receiptNos"][0]:
            raise ValueError("LATER_RECEIPT_NODE_REFUSED")
        body = sources.get(section["sha256"])
        if body is None:
            continue
        text = plain(body)
        for cand in P.industry_candidates(body.decode("utf-8")):
            row = {"security_id": "KRX:" + target["ticker"], "ticker": target["ticker"], "corpCode": target["corpCode"],
                   "receipt_no": target["receiptNos"][0], "known_from": release, "subject_scope": "ISSUER",
                   "identity_status": "DATED_ISSUER_SECURITY", "identity_source_sha256": main.get("sha256"),
                   "identity_locator": identity, "source_sha256": section["sha256"],
                   "source_locator": body.decode("utf-8"), "reported_label": cand["statedLabel"],
                   "reported_code": cand["reportedCode"],
                   "evidence_tier": "DART_EXPLICIT_ISSUER_CLASSIFICATION" if cand["reportedCode"] else "DART_EXPLICIT_ISSUER_LABEL"}
            admitted, reason = V.admit(row, sources, {})
            title_ok = bool(main_raw) and main_raw.decode("utf-8").count(identity) == 1 and \
                release.replace("-", ".") in (re.search(r"<title>(.*?)</title>", main_raw.decode("utf-8"), re.S) or [""," "])[1]
            hierarchy = stated_hierarchy(text, cand["reportedCode"])
            rows.append({"fiscalYear": target["fiscalYear"], "receiptNo": target["receiptNos"][0], "knownFrom": release,
                         "section": section["section"], "reportedCode": cand["reportedCode"],
                         "reportedLabel": cand["reportedLabel"], "admitMechanical": admitted is not None,
                         "admitReason": reason, "datedIssuerReleaseProven": title_ok,
                         "frozenV2TemplateProducedIt": False,
                         "crosswalkGroupOfReportedLabel": V4.research_group(cand["reportedLabel"], crosswalk),
                         "statedHierarchy": [dict(h, crosswalkGroup=V4.research_group(h["label"], crosswalk)) for h in hierarchy]})
    return rows


def reconcile(plan, report, inventory, records, sources, crosswalk, v2_observations):
    corp_to_code = {q["dartCorpCode"]: q["code"] for q in report["requests"]}
    by_code = {corp_to_code[r["issuer"]["corpCode"]]: r for r in inventory if r["issuer"]["corpCode"] in corp_to_code}
    retained = set(records)
    template_rows = {(o["ticker"], o["receipt_no"]) for o in v2_observations}
    securities, remaining = [], []
    for q in report["requests"]:
        code = q["code"]
        row = by_code.get(code)
        selected = {s["fiscalYear"]: s for s in (row or {}).get("selected", [])}
        missing = set((row or {}).get("missingYears", []))
        complete = bool(row and row.get("paginationComplete"))
        needed = sorted(q["fiscalYearsNeedingListJsonQuery"])
        answered = [y for y in needed if complete and (y in selected or y in missing)]
        held = sorted(q["annualReportReceiptsHeldInRepository"].values())
        held_years = {int(y) for y in q["annualReportReceiptsHeldInRepository"]}
        cands = []
        for fy, s in sorted(selected.items()):
            receipt = s["receiptNos"][0]
            if receipt in retained:
                cands.extend(candidate_rows(s, records[receipt], sources, crosswalk))
            else:
                remaining.append({"kind": "ANNUAL_ORIGINAL_NOT_RETAINED", "code": code, "corpCode": q["dartCorpCode"],
                                  "fiscalYear": fy, "receiptNo": receipt, "route": "PUBLIC_VIEWER_NO_KEY"})
        securities.append({
            "code": code, "corpCode": q["dartCorpCode"], "v2IssuerFound": row is not None,
            "v2PaginationComplete": complete, "selectedAnnualReceipts": len(selected),
            "selectedRetained": sum(s["receiptNos"][0] in retained for s in selected.values()),
            "listedNoOriginalYears": sorted(missing),
            "planFiscalYearSlots": len(needed), "planFiscalYearSlotsAnsweredByRepository": len(answered),
            "planHeldReceipts": len(held), "planHeldReceiptsRetainedAsOriginals": sum(r in retained for r in held),
            # A held kr-raw receipt that v2 did not keep is not needed when v2 kept the earliest original for that year.
            "planHeldFiscalYearsWithRetainedOriginal": sum(1 for y in held_years
                                                           if y in selected and selected[y]["receiptNos"][0] in retained),
            "industryCandidates": cands,
            "v2TemplateObservations": sum(1 for t, _ in template_rows if t == code)})
    for r in plan["requests"]:
        if r["kind"] == "DOCUMENT_DIVIDEND_DECISION":
            remaining.append({"kind": r["kind"], "code": r["code"], "corpCode": r["corpCode"], "receiptNo": r["receiptNo"],
                              "route": "OPENDART_DOCUMENT_XML_WITH_KEY_OR_PUBLIC_VIEWER"})
        elif r["kind"] == "VIEWER_ROUTE_REQUIRED":
            remaining.append({"kind": r["kind"], "code": r["code"], "corpCode": r["corpCode"], "receiptNo": r["receiptNo"],
                              "route": "PUBLIC_VIEWER_NO_KEY"})
    with_cands = [s for s in securities if s["industryCandidates"]]
    summary = {
        "denominator": report["summary"]["denominator"], "inWindowSecurities": len(securities),
        "v2IssuersFound": sum(s["v2IssuerFound"] for s in securities),
        "planFiscalYearSlots": sum(s["planFiscalYearSlots"] for s in securities),
        "planFiscalYearSlotsAnsweredByRepository": sum(s["planFiscalYearSlotsAnsweredByRepository"] for s in securities),
        "planHeldReceipts": sum(s["planHeldReceipts"] for s in securities),
        "planHeldReceiptsRetainedAsOriginals": sum(s["planHeldReceiptsRetainedAsOriginals"] for s in securities),
        "planHeldFiscalYearsWithRetainedOriginal": sum(s["planHeldFiscalYearsWithRetainedOriginal"] for s in securities),
        "selectedAnnualReceipts": sum(s["selectedAnnualReceipts"] for s in securities),
        "selectedAnnualReceiptsRetained": sum(s["selectedRetained"] for s in securities),
        "remainingRequests": {k: sum(r["kind"] == k for r in remaining) for k in
                              ("ANNUAL_ORIGINAL_NOT_RETAINED", "DOCUMENT_DIVIDEND_DECISION", "VIEWER_ROUTE_REQUIRED")},
        "securitiesWithExplicitKsicStatement": [s["code"] for s in with_cands],
        "explicitKsicReceipts": sum(len({c["receiptNo"] for c in s["industryCandidates"]}) for s in with_cands),
        "mechanicallyAdmissibleRows": sum(c["admitMechanical"] and c["datedIssuerReleaseProven"]
                                          for s in with_cands for c in s["industryCandidates"]),
        "v2TemplateObservationsForTheseSecurities": sum(s["v2TemplateObservations"] for s in securities),
        "industryAdmitted": {"before": 0, "after": 0},
        "admissionBlockedBy": ["FROZEN_V2_TEMPLATE_REQUIRES_ISSUER_SUBJECT_SENTENCE",
                               "REPORTED_LABEL_NOT_IN_FROZEN_V4_CROSSWALK; ONLY_A_STATED_HIERARCHY_LABEL_MAPS"]}
    return {"contract": CONTRACT, "evidenceClass": "SOURCE_ONLY_RECONCILIATION_NOT_ADMISSION",
            "historicalOutcomesRead": 0, "pricesRead": 0, "networkUsed": False,
            "planSha256": plan["planSha256"], "summary": summary, "securities": securities, "remainingRequests": remaining}


def coverage_if_admitted(result, src):
    """Study-window member-months each candidate security would carry a known industry for, IF its candidate rows were
    admitted: months after the first candidate's known_from (strictly), by the last-known-public rule. Hypothetical."""
    out = {}
    for s in result["securities"]:
        rows = [c for c in s["industryCandidates"] if c["admitMechanical"] and c["datedIssuerReleaseProven"]]
        if not rows:
            continue
        first = min(c["knownFrom"] for c in rows)
        months = K._window_months(s["code"], src)
        out[s["code"]] = {"firstKnownFrom": first, "windowMemberMonths": len(months),
                          "monthsAfterFirstKnownFrom": sum(m > first[:7] for m in months)}
    return out


def build(root=K.ROOT):
    root = Path(root)
    inventory, records, sources = load_v2(root)
    crosswalk = json.loads((root / CROSSWALK).read_text())
    v2_obs = json.loads(gzip.decompress((root / V2 / "state/observations.json.gz").read_bytes()))
    report = json.loads((HERE / "kr22-source-recovery.json").read_text())
    out = reconcile(P.load_plan(), report, inventory, records, sources, crosswalk, v2_obs)
    src = K.load(root)[0]
    out["summary"]["coverageIfAdmitted"] = coverage_if_admitted(out, src)
    out["summary"]["studyWindowMemberMonthsAll16"] = sum(K.window_member_months(q["code"], src) for q in report["requests"])
    out["inputs"] = {"crosswalkSha256": hashlib.sha256((root / CROSSWALK).read_bytes()).hexdigest(),
                     "v2Receipts": len(records), "v2Sources": len(sources)}
    return out


def remaining_plan(plan, result):
    """The original plan reduced to what the repository does not already hold and the existing OpenDART collector can
    fetch: the dividend-decision documents. Same contract and digest rule, so `kr22_collection_plan.collect` and
    `verify` run on it unchanged. The 35 viewer-route receipts stay out: no collector in the repository fetches them."""
    keep = {r["receiptNo"] for r in result["remainingRequests"] if r["kind"] == "DOCUMENT_DIVIDEND_DECISION"}
    body = {k: v for k, v in plan.items() if k not in ("planSha256", "requests", "counts", "fiscalYearSlots")}
    body["requests"] = [r for r in plan["requests"] if r.get("receiptNo") in keep and r["kind"] == "DOCUMENT_DIVIDEND_DECISION"]
    body["counts"] = {k: sum(r["kind"] == k for r in body["requests"]) for k in P.KINDS}
    body["fiscalYearSlots"] = 0
    body["reducedFrom"] = {"planSha256": plan["planSha256"], "reconciliation": CONTRACT,
                           "droppedAsAlreadyHeld": ["LIST_A001", "DOCUMENT_ANNUAL"],
                           "droppedNoCollector": ["VIEWER_ROUTE_REQUIRED"]}
    return {**body, "planSha256": P.digest(body)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd")
    b = sub.add_parser("build")
    b.add_argument("--output", default=str(REPORT))
    c = sub.add_parser("collect-remaining")
    c.add_argument("--output", required=True)
    # 141 documents plus one list.json confirmation each (the exchange forms carry no issuer code).
    c.add_argument("--max-calls", type=int, default=400)
    k = sub.add_parser("confirm-remaining")
    k.add_argument("--input", required=True)
    k.add_argument("--max-calls", type=int, default=200)
    for name in ("verify-remaining", "extract-remaining"):
        sub.add_parser(name).add_argument("--input", required=True)
    args = ap.parse_args(argv)
    if args.cmd in (None, "build"):
        result = build()
        Path(getattr(args, "output", str(REPORT))).write_text(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
        REMAINING_PLAN.write_text(json.dumps(remaining_plan(P.load_plan(), result), ensure_ascii=False, indent=1,
                                             sort_keys=True) + "\n")
        return 0
    if args.cmd == "verify-remaining":
        problems = P.verify(P.load_plan(REMAINING_PLAN), args.input)
        sys.stdout.write(json.dumps({"problems": problems}, ensure_ascii=False) + "\n")
        return 0 if not problems else 3
    if args.cmd == "extract-remaining":
        rows = P.extract(P.load_plan(REMAINING_PLAN), args.input)
        report = json.loads((HERE / "kr22-source-recovery.json").read_text())
        sys.stdout.write(json.dumps({"effect": P.acquisition_effect(report, rows), "rows": rows}, ensure_ascii=False,
                                    indent=1) + "\n")
        return 0
    import os
    key = os.environ.get("DART_API_KEY")
    if not key:
        sys.stderr.write("DART_API_KEY is required; refusing to start.\n")
        return 2
    plan = P.load_plan(REMAINING_PLAN)
    list_page, document = P._dart_callers(key)
    if args.cmd == "confirm-remaining":
        manifest = P.confirm_listings(plan, args.input, list_page=list_page, max_calls=args.max_calls, pause=0.3)
        stop, directory = manifest["listingStop"], args.input
    else:
        # `collect` takes its two callers as keyword-only arguments; passing them positionally raised TypeError.
        manifest = P.collect(plan, args.output, list_page=list_page, document=document, max_calls=args.max_calls, pause=0.3)
        stop, directory = (manifest.get("listingStop") if manifest["stop"] == "COMPLETE" else manifest["stop"]), args.output
    problems = P.verify(plan, directory)
    sys.stdout.write(json.dumps({"stop": stop, "calls": manifest["calls"], "listingCalls": manifest.get("listingCalls", 0),
                                 "entries": len(manifest["entries"]), "verifyProblems": problems}, ensure_ascii=False) + "\n")
    return 0 if stop == "COMPLETE" and not problems else 3


if __name__ == "__main__":
    sys.exit(main())
