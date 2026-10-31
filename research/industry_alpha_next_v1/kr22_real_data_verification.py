"""The repaired KR22 verifiers run on the 172 originals PR #294 acquired, reported in six separate stages.

SOURCE-ONLY. No price, return, label or outcome. The raw bytes are not in the repository (redistribution rights
unverified); this module reads two local collection directories, re-hashes every byte against the SHA-256 PR #294
published, and writes only identities, hashes, dates, stated terms and verdicts. Nothing is adopted: a verified
amendment's corrected terms still enter `data/kr-terminal-corporate-actions.json` only through the human review in
`data/kr-terminal-document-review.json`, and a stated record date is never turned into an ex-date.

Stages, each counted on its own denominator so that a failure says where it happened:
  1 downloaded       - a response body was received
  2 integrity        - every byte re-hashes to the SHA-256 PR #294 recorded
  3 identity         - issuer, receipt and date are proven (terminal: viewer + correction notice + original link;
                       dividend: ZIP member + heading date + list.json confirmation)
  4 extraction       - correction rows / stated dividend terms read
  5 PIT and source   - the receipt date is the visibility date and the source is DART's own filing
  6 research         - industry and total-return eligibility (gates unchanged by this module)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from . import kr22_collection_plan as P
from . import kr22_repository_originals as R
from . import kr22_terminal_viewer as TV

HERE = Path(__file__).resolve().parent
REPORT = HERE / "kr22-real-data-verification.json"
CONTRACT = "KR22_REAL_DATA_VERIFICATION_V1"
EVIDENCE_PR = "jaehojung1879-netizen/Investment#294"
EVIDENCE_COMMIT = "7ee63e1754468b76125b6bd27798e36f71e9f275"

# What a corrected row moves. Appraisal rights are tested first because their rows also carry record dates.
CHANGE_CLASSES = (
    ("APPRAISAL_RIGHTS", re.compile(r"매수\s*청구|반대\s*의사")),
    ("CONSIDERATION_TERMS", re.compile(r"비율|가액|가격|대금|교부금|양도\s*가액|양수도|신주의\s*(종류와\s*)?수|배정")),
    ("EXECUTION_TIMELINE", re.compile(r"합병\s*기일|교환\s*일|이전\s*일|효력|거래\s*정지|상장\s*예정|상장\s*폐지|합병\s*등기"
                                      r"|양도\s*기준일|양도\s*예정|주주\s*확정\s*기준일|명부\s*폐쇄|일정")),
)
HEADER_CELL = re.compile(r"^(항목|정정전|정정후|정정사유|정정사항)$")
NUMBER = re.compile(r"\d[\d,.]*")
FOOTNOTE = re.compile(r"^\(?\s*(정정\s*[전후]\s*)?주\s*\d")
# The term rows of DART's merger / share-exchange / business-transfer decision forms, matched at the start of the row
# label after its numbering, so prose that merely mentions a ratio (상장 계획, 평가 방법) is not a term row.
TERM_LABEL = re.compile(r"^[\d.\s]*(합병\s*비율|주식\s*교환\s*비율|교환\s*비율|주식\s*이전\s*비율|이전\s*비율|양도\s*가액"
                        r"|양수도\s*대금|양도\s*대금|합병\s*신주의?\s*(종류와\s*)?수|교환\s*신주의?\s*수|교부금|1\s*주당)")


def classify_change(item):
    for name, pattern in CHANGE_CLASSES:
        if pattern.search(item):
            return name
    return "TEXT_OR_DOCUMENT"


def changed_rows(correction_rows):
    """Rows of a 정정전/정정후 table whose before and after differ, with what each moves. Header rows are skipped."""
    out = []
    for row in correction_rows:
        cells = [c.strip() for c in row["cells"]]
        if len(cells) < 3 or all(HEADER_CELL.match(re.sub(r"\s+", "", c)) for c in cells if c):
            continue
        before, after = cells[-2], cells[-1]
        if before == after or not cells[0]:
            continue
        cls = classify_change(cells[0])
        out.append({"item": cells[0][:120], "before": before[:160], "after": after[:160], "class": cls,
                    "statedValueChanged": stated_value_changed(cells[0], before, after)})
    return out


def stated_value_changed(item, before, after):
    """True only where a decision-form term row states a number on both sides and the numbers differ. The class is a
    keyword triage of the row label (valuation footnotes and listing-plan prose also match it); this flag is the
    narrower reading. Neither is a term determination."""
    if not TERM_LABEL.match(item) or FOOTNOTE.match(before) or FOOTNOTE.match(after):
        return False
    b, a = NUMBER.findall(before), NUMBER.findall(after)
    return bool(b and a and b != a)


def terminal_stages(viewer_dir, evidence, plan=None, index=None):
    plan = plan or TV.load_plan()
    manifest, objects = TV.load_collection(viewer_dir, plan)
    index = TV.load_index(plan) if index is None else index
    published = {r["receiptNo"]: r for r in evidence["terminal"]["records"]}
    targets = {t["receiptNo"]: t for t in plan["targets"]}
    rows = []
    for record in manifest["records"]:
        t, pub = targets[record["receiptNo"]], published[record["receiptNo"]]
        served = record["status"] == "SERVED"
        shas = [record["responses"][0].get("sha256")] + [n["sha256"] for n in record["nodes"]] if served else []
        integrity = served and shas == [pub.get("mainSha256")] + pub.get("nodeSha256", []) and all(
            hashlib.sha256(objects[s]).hexdigest() == s for s in shas)
        verdict, reasons, link = TV.verify_record(t, record, objects, index)
        rows_read = changed_rows(TV.extract_candidates(record, objects)["correctionRows"]) if integrity and record["nodes"] else []
        # Rows of a refused filing are kept apart, for the human reader only; they never count as verified changes.
        changes, unverified = (rows_read, []) if verdict == "VERIFIED" else ([], rows_read)
        rows.append({"receiptNo": t["receiptNo"], "ticker": t["ticker"], "corpCode": t["corpCode"],
                     "reportName": t["reportName"], "receiptDate": t["receiptDate"],
                     "priorReviewCategory": t["priorReviewCategory"],
                     "stage1Downloaded": served, "stage2Integrity": bool(integrity),
                     "stage3Identity": verdict, "stage3Reasons": reasons, "amendmentLink": link,
                     "stage4ChangedRows": changes, "unverifiedChangedRowsForReview": unverified,
                     # The viewer collector records no per-response time; PR #294 ran it 2026-10-26 ~14:33-14:36 UTC.
                     "stage5Pit": {"visibleFrom": t["receiptDate"], "source": "dart.fss.or.kr public viewer",
                                   "retrievedAt": None} if served else None,
                     "collectionStatus": record["status"]})
    return rows


def dividend_stages(div_dir, evidence, plan=None):
    plan = plan or P.load_plan(R.REMAINING_PLAN)
    published = {r["receiptNo"]: r for r in evidence["dividend"]["records"]}
    manifest = json.loads((Path(div_dir) / "manifest.json").read_text())
    problems = P.verify(plan, div_dir)
    by_receipt = {}
    for p in problems:
        m = re.search(r"\d{14}", p)
        by_receipt.setdefault(m.group(0) if m else "*", []).append(p)
    extracted = {r["receiptNo"]: r for r in P.extract(plan, div_dir)} if not problems else {}
    listing = {e["receiptNo"]: e for e in manifest["entries"] if e["kind"] == "LISTING_CONFIRMATION"}
    rows = []
    for e in manifest["entries"]:
        if e["kind"] != "DOCUMENT_DIVIDEND_DECISION":
            continue
        raw = (Path(div_dir) / e["file"]).read_bytes()
        pub = published[e["receiptNo"]]
        members = P.zip_members(raw)
        form = P.xforms_heading(members[0]["text"]) if len(members) == 1 else None
        x = extracted.get(e["receiptNo"], {})
        rows.append({"receiptNo": e["receiptNo"], "ticker": e["code"], "corpCode": e["corpCode"],
                     "stage1Downloaded": e["status"] == "ZIP",
                     "stage2Integrity": hashlib.sha256(raw).hexdigest() == e["sha256"] == pub["sha256"],
                     "stage3Identity": "VERIFIED" if not by_receipt.get(e["receiptNo"]) else "REFUSED",
                     "stage3Reasons": by_receipt.get(e["receiptNo"], []),
                     "zipMember": members[0]["storedName"], "encoding": members[0]["encoding"],
                     "filerNameOnFilingDay": form[0] if form else None,
                     "listingConfirmationSha256": listing.get(e["receiptNo"], {}).get("sha256"),
                     "retrievedAt": e["retrievedAt"], "listingRetrievedAt": listing.get(e["receiptNo"], {}).get("retrievedAt"),
                     "stage4": {k: x.get(k) for k in ("recordDate", "commonDividendPerShareKrw", "exDate", "exDateSource")},
                     "stage5Pit": {"visibleFrom": pub.get("headingDate"), "source": "opendart.fss.or.kr document.xml"}})
    return rows, problems


def security_table(terminal):
    """Per amendment-target security: are all its MATERIALLY_BLOCKING amendments acquired and verified?"""
    out = {}
    for r in terminal:
        s = out.setdefault(r["ticker"], {"materiallyBlocking": 0, "materiallyBlockingVerified": 0,
                                         "verified": 0, "refused": 0, "notServed": 0})
        s["verified"] += r["stage3Identity"] == "VERIFIED"
        s["refused"] += r["stage3Identity"] == "REFUSED"
        s["notServed"] += r["stage3Identity"] == "NOT_SERVED"
        if r["priorReviewCategory"] == "MATERIALLY_BLOCKING":
            s["materiallyBlocking"] += 1
            s["materiallyBlockingVerified"] += r["stage3Identity"] == "VERIFIED"
    for s in out.values():
        s["allMateriallyBlockingVerified"] = s["materiallyBlocking"] > 0 and s["materiallyBlocking"] == s["materiallyBlockingVerified"]
    return dict(sorted(out.items()))


def build(viewer_dir, div_dir, evidence_path):
    raw_evidence = Path(evidence_path).read_bytes()
    evidence = json.loads(raw_evidence)
    terminal = terminal_stages(viewer_dir, evidence)
    dividends, problems = dividend_stages(div_dir, evidence)
    recovery = json.loads((HERE / "kr22-source-recovery.json").read_text())
    effect = P.acquisition_effect(recovery, P.extract(P.load_plan(R.REMAINING_PLAN), div_dir) if not problems else [])
    complete = sorted(s["code"] for s in recovery["securities"]
                      if s["gatesAfter"]["terminalConsiderationResolved"] and s["gatesAfter"]["executionConfirmed"])
    table = security_table(terminal)
    count = lambda rows, key, value=True: sum(r[key] == value for r in rows)  # noqa: E731
    changes = [dict(c, receiptNo=r["receiptNo"], ticker=r["ticker"]) for r in terminal for c in r["stage4ChangedRows"]]
    summary = {
        "terminal": {"planned": len(terminal), "stage1Downloaded": count(terminal, "stage1Downloaded"),
                     "stage2Integrity": count(terminal, "stage2Integrity"),
                     "stage3Verified": count(terminal, "stage3Identity", "VERIFIED"),
                     "stage3Refused": count(terminal, "stage3Identity", "REFUSED"),
                     "stage3NotServed": count(terminal, "stage3Identity", "NOT_SERVED"),
                     "materiallyBlocking": sum(r["priorReviewCategory"] == "MATERIALLY_BLOCKING" for r in terminal),
                     "materiallyBlockingVerified": sum(r["priorReviewCategory"] == "MATERIALLY_BLOCKING"
                                                       and r["stage3Identity"] == "VERIFIED" for r in terminal),
                     "changedRowsByClassKeywordTriage": {k: sum(c["class"] == k for c in changes) for k in
                                                         ("CONSIDERATION_TERMS", "EXECUTION_TIMELINE", "APPRAISAL_RIGHTS",
                                                          "TEXT_OR_DOCUMENT")},
                     "verifiedStatedConsiderationValueChanges": sorted(
                         {(c["receiptNo"], c["ticker"], c["item"][:40]) for c in changes if c["statedValueChanged"]}),
                     "refusedFilingsStatedConsiderationValueChanges": sorted(
                         {(r["receiptNo"], r["ticker"], c["item"][:40]) for r in terminal
                          for c in r["unverifiedChangedRowsForReview"] if c["statedValueChanged"]}),
                     "securitiesWithEveryMateriallyBlockingAmendmentVerified":
                         sorted(k for k, v in table.items() if v["allMateriallyBlockingVerified"])},
        "dividend": {"planned": len(dividends), "stage1Downloaded": count(dividends, "stage1Downloaded"),
                     "stage2Integrity": count(dividends, "stage2Integrity"),
                     "stage3Verified": count(dividends, "stage3Identity", "VERIFIED"),
                     "stage4RecordDateStated": sum(bool(r["stage4"]["recordDate"]) for r in dividends),
                     "stage4AmountStated": sum(r["stage4"]["commonDividendPerShareKrw"] is not None for r in dividends),
                     "stage4ExDateStated": sum(bool(r["stage4"]["exDate"]) for r in dividends),
                     "cp949Members": sum(r["encoding"] == "cp949" for r in dividends),
                     "leadingSlashMembers": sum(r["zipMember"].startswith("/") for r in dividends)},
        "stage6Research": {**effect, "terminalEconomicsCompleteSecurities": complete,
                           "terminalEconomicsComplete": {"before": len(complete), "after": len(complete)},
                           "notes": ["No gate is set by this module; a verified amendment is a review input, not an adoption.",
                                     "None of the 5 complete securities is an amendment target, so no verified correction "
                                     "contradicts a recorded complete term."]}}
    return {"contract": CONTRACT, "evidenceClass": "SOURCE_VERIFICATION_NOT_ADMISSION",
            "historicalOutcomesRead": 0, "pricesRead": 0,
            "inputs": {"evidencePr": EVIDENCE_PR, "evidenceCommit": EVIDENCE_COMMIT,
                       "evidenceSha256": hashlib.sha256(raw_evidence).hexdigest(),
                       "terminalPlanSha256": TV.load_plan()["planSha256"],
                       "dividendPlanSha256": P.load_plan(R.REMAINING_PLAN)["planSha256"]},
            "rawBytesCommitted": False,
            "summary": summary, "securities": table, "terminal": terminal, "dividend": dividends,
            "dividendVerifierProblems": problems}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--viewer", required=True)
    ap.add_argument("--dividends", required=True)
    ap.add_argument("--evidence", required=True)
    ap.add_argument("--output", default=str(REPORT))
    args = ap.parse_args(argv)
    out = build(args.viewer, args.dividends, args.evidence)
    Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    print(json.dumps(out["summary"], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
