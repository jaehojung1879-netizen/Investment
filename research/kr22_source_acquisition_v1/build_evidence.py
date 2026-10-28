"""Evidence record for the first live KR22 source acquisition (2026-10-26). No price, return or label is read.

Inputs are two local collection directories produced by the unmodified PR #290 collectors; raw bytes stay out of the
repository (redistribution rights are unverified) and only identities, hashes, dates and classifications are written.
Usage: python -I build_evidence.py <viewer35_dir> <div141_dir> <plan_dir> <company_names.json> <out.json>
"""
from __future__ import annotations

import base64
import collections
import gzip
import hashlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path

TERM = re.compile(r"비율|가액|가격|합병기일|교환일|이전일|합병등기|교부|신주|거래정지|확정기준일|매수|1주당|상장예정|상장폐지")
RATIO = re.compile(r"비율|가액|가격|교부")


def digits(text):
    return re.findall(r"\d[\d,.]*", text)


def plain(text):
    text = re.sub(r"<style.*?</style>", "", text, flags=re.S | re.I)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()


def korean_date(text):
    m = re.search(r"(\d{4})\s*[.년-]\s*(\d{1,2})\s*[.월-]\s*(\d{1,2})", text or "")
    return "%s-%02d-%02d" % (m.group(1), int(m.group(2)), int(m.group(3))) if m else None


def terminal(viewer_dir, plan_dir):
    sys.path.insert(0, str(plan_dir))
    from research.industry_alpha_next_v1 import kr22_terminal_viewer as V

    plan = V.load_plan(Path(plan_dir) / "research/industry_alpha_next_v1/kr22-terminal-viewer-plan.json")
    manifest, objects = V.load_collection(viewer_dir, plan)
    targets = {t["receiptNo"]: t for t in plan["targets"]}
    rows = []
    for rec in manifest["records"]:
        t = targets[rec["receiptNo"]]
        row = {"receiptNo": t["receiptNo"], "ticker": t["ticker"], "corpCode": t["corpCode"],
               "priorReviewCategory": t["priorReviewCategory"], "reportName": t["reportName"],
               "receiptDate": t["receiptDate"], "collection": rec["status"]}
        if rec["status"] != "SERVED":
            rows.append(row)
            continue
        main = objects[rec["responses"][0]["sha256"]].decode()
        title = re.search(r"<title>(.*?)</title>", main, re.S).group(1).strip()
        names = [n["node"].get("text") for n in rec["nodes"]]
        structure = V.extract_candidates(rec, objects)
        changes = []
        for c in structure["correctionRows"]:
            k = c["cells"]
            if len(k) >= 4 and k[-2] != k[-1] and TERM.search(k[0]) and digits(k[-2]) != digits(k[-1]):
                changes.append({"item": k[0][:80], "before": k[-2][:120], "after": k[-1][:120],
                                "touchesRatioOrConsideration": bool(RATIO.search(k[0]))})
        row.update({
            "mainSha256": rec["responses"][0]["sha256"], "nodeSha256": [n["sha256"] for n in rec["nodes"]],
            "viewerTitle": title, "titleDateEqualsReceiptDate": title.split("/")[-1] == t["receiptDate"].replace("-", "."),
            "corpIdentityUnique": main.count("openCorpInfoNew('%s'," % t["corpCode"]) == 1,
            "allNodesCarryReceiptNo": all(n["node"]["rcpNo"] == t["receiptNo"] for n in rec["nodes"]),
            "firstNodeIsCorrectionNotice": any("정 정 신 고" in (x or "") for x in names),
            "correctionRowCount": len(structure["correctionRows"]), "termValueChanges": changes})
        rows.append(row)
    return {"calls": manifest["calls"], "planSha256": plan["planSha256"], "archiveSha256": manifest["archiveSha256"],
            "records": rows}


def dividends(div_dir, names, plan_dir):
    plan = json.loads((Path(plan_dir) / "research/industry_alpha_next_v1/kr22-remaining-plan.json").read_text())
    req = {r["receiptNo"]: r for r in plan["requests"]}
    manifest = json.loads((Path(div_dir) / "manifest.json").read_text())
    rows = []
    for e in manifest["entries"]:
        raw = (Path(div_dir) / e["file"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == e["sha256"]
        member = zipfile.ZipFile(io.BytesIO(raw))
        body = member.read(member.namelist()[0])
        try:
            text, enc = body.decode("utf-8"), "utf-8"
        except UnicodeDecodeError:
            text, enc = body.decode("cp949", "replace"), "cp949"
        p = plain(text)
        r = req[e["receiptNo"]]
        head = re.search(r"([^/\s]{1,20})/현금ㆍ현물 배당 결정/\((\d{4}\.\d{2}\.\d{2})\)", p)
        corp = names[r["corpCode"]]
        name_match = bool(head) and (head.group(1) in corp or corp.replace("(주)", "").replace("주식회사", "").strip().endswith(head.group(1)))
        rec = re.search(r"배당기준일\s*(.{0,40})", p)
        pay = re.search(r"배당금지급\s*예정일자\s*(.{0,40})", p)
        rows.append({"receiptNo": e["receiptNo"], "ticker": e["code"], "corpCode": r["corpCode"], "sha256": e["sha256"],
                     "bytes": e["bytes"], "encoding": enc, "zipStatus": e["status"],
                     "isDecisionForm": bool(head), "headingDate": head.group(2).replace(".", "-") if head else None,
                     "headingDateEqualsReceiptDate": bool(head) and head.group(2).replace(".", "-") == r["receiptDate"],
                     "issuerNameInHeading": head.group(1) if head else None, "issuerNameMatchesCurrentCorpName": name_match,
                     "recordDate": korean_date(rec[1]) if rec else None, "paymentDate": korean_date(pay[1]) if pay else None,
                     "exDateStated": "배당락" in p})
    return {"calls": manifest["calls"], "stop": manifest["stop"], "records": rows}


def main(argv):
    viewer, div, plan_dir, names_path, out = argv
    names = json.loads(Path(names_path).read_text())
    t, d = terminal(viewer, plan_dir), dividends(div, names, plan_dir)
    served = [r for r in t["records"] if r["collection"] == "SERVED"]
    summary = {
        "terminal": {"planned": len(t["records"]), "served": len(served), "listedButViewerEmpty": len(t["records"]) - len(served),
                     "identityUnique": sum(r["corpIdentityUnique"] for r in served),
                     "receiptNoOnAllNodes": sum(r["allNodesCarryReceiptNo"] for r in served),
                     "titleDateEqualsReceiptDate": sum(r["titleDateEqualsReceiptDate"] for r in served),
                     "correctionNoticePresent": sum(r["firstNodeIsCorrectionNotice"] for r in served),
                     "byCategory": dict(collections.Counter((r["priorReviewCategory"], r["collection"]) .__str__() for r in t["records"])),
                     "amendmentsChangingRatioOrConsideration": sorted(r["receiptNo"] for r in served
                                                                       if any(c["touchesRatioOrConsideration"] for c in r["termValueChanges"])),
                     "amendmentsChangingAnyTermValue": sum(bool(r["termValueChanges"]) for r in served)},
        "dividend": {"planned": len(d["records"]), "responses": len(d["records"]),
                     "zip": sum(r["zipStatus"] == "ZIP" for r in d["records"]),
                     "isDecisionForm": sum(r["isDecisionForm"] for r in d["records"]),
                     "headingDateEqualsReceiptDate": sum(r["headingDateEqualsReceiptDate"] for r in d["records"]),
                     "issuerNameMatchesCurrentCorpName": sum(r["issuerNameMatchesCurrentCorpName"] for r in d["records"]),
                     "recordDateExtracted": sum(bool(r["recordDate"]) for r in d["records"]),
                     "paymentDateExtracted": sum(bool(r["paymentDate"]) for r in d["records"]),
                     "exDateStated": sum(r["exDateStated"] for r in d["records"])}}
    Path(out).write_text(json.dumps({"terminal": t, "dividend": d, "summary": summary}, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    _ = (base64, gzip)


if __name__ == "__main__":
    main(sys.argv[1:])
