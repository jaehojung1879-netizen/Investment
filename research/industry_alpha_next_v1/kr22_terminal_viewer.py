"""The 35 terminal amendment filings: a pinned public-viewer plan, a reusing collector, an offline verifier and a
candidate extractor. Nothing here has run against DART; nothing it extracts is adopted.

SOURCE-ONLY. No price, return, label or outcome. The 35 receipts are exactly the `failedTerminalReceiptsToRetry` of
`kr22-source-recovery.json`, i.e. the receipts `document-fetch-state.json` (signal-history `d646a69`) marks
FETCH_FAILED for the in-window securities; `document.xml` answered DART's 147-byte 014 envelope for every one on an
exhausted retry. All 35 are AMENDMENTS ([기재정정] / [첨부정정]) of decision filings whose originals the repository
already retains, plus one FSS correction order (정정명령부과); the repository's own failure review
(`docs/results/kr-terminal-document-parsing.json`) classes them 20 MATERIALLY_BLOCKING, 10 POTENTIALLY_MATERIAL and
5 REDUNDANT_SUPERSEDED_OR_UNNECESSARY, and that class travels with each receipt.

Reuse, not reimplementation:

* HTTP: `scripts/collect_kr_industry_membership_sources.Collector.request` (call budget, body-size cap, no key) and
  its `nodes()` (exact rcpNo node list from `dsaf001/main.do`). Its `receipt()` fetches only two annual-report
  sections, so this module walks EVERY node of the receipt instead, capped per receipt; that file is not edited.
* Parsing: `pipeline.kr_terminal_action_document_parser.document_structure` / `labeled_rows` / `korean_date`, the
  parser already validated on the 92 retained originals, which also flags 정정전/정정후 correction tables.

A collection failure (no HTTP status, a non-200 status, a body over budget, the call budget) is never read as the
filing not existing: every receipt is already listed by `list.json` in the repository's disclosure index, so an empty
viewer is recorded as LISTED_BUT_VIEWER_EMPTY for a human to read, never as an absence.
"""
from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlencode

from pipeline import kr_terminal_action_document_parser as DP

from . import inputs as IN
from . import kr22_collection_plan as P

HERE = Path(__file__).resolve().parent
PLAN_PATH = HERE / "kr22-terminal-viewer-plan.json"
CONTRACT = "KR22_TERMINAL_VIEWER_PLAN_V1"
MANIFEST_CONTRACT = "KR22_TERMINAL_VIEWER_MANIFEST_V1"
FAILURE_REVIEW = Path("docs/results/kr-terminal-document-parsing.json")
MAIN = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo="
VIEWER = "https://dart.fss.or.kr/report/viewer.do?"
NODE_KEYS = ("rcpNo", "dcmNo", "eleId", "offset", "length", "dtd")
MAX_NODES_PER_RECEIPT = 15
MAX_CONSECUTIVE_TRANSPORT_FAILURES = 3
AMENDMENT = re.compile(r"^\[(기재정정|첨부정정|첨부추가|발행조건확정)\]")
# Rows the decision forms state; the labels the existing parser already knows plus the share-exchange forms'.
FIELDS = {**{k: v for k, v in DP.FIELD_LABELS.items()},
          "exchangeRatio": ("주식교환비율", "교환비율", "주식이전비율", "이전비율"),
          "exchangeDate": ("주식교환일", "주식이전일", "교환일", "이전일"),
          "newSharesIssued": ("교환신주의 수", "교환ㆍ이전 신주 수", "합병신주의 종류와 수", "발행할 신주의 수",
                              "교부할 주식의 수", "합병신주의 수"),
          "transferDate": ("양도기준일", "영업양도기준일", "양도예정일자")}


# --------------------------------------------------------------------------- #
# Plan (repository bytes only)
# --------------------------------------------------------------------------- #
def build_plan(root=IN.ROOT):
    root = Path(root)
    recovery = json.loads((HERE / "kr22-source-recovery.json").read_text())
    blobs = IN.git_blobs(P.SOURCE_COMMIT, [P.DISCLOSURES, P.FETCH_STATE], root)
    index = {r["receiptNo"]: r for r in (json.loads(x) for x in gzip.decompress(blobs[P.DISCLOSURES]).decode().splitlines() if x.strip())}
    state = json.loads(blobs[P.FETCH_STATE])["receipts"]
    review = {f["receiptNo"]: f for f in json.loads((root / FAILURE_REVIEW).read_text())["failures"]}
    targets = []
    for q in recovery["requests"]:
        for receipt in q.get("failedTerminalReceiptsToRetry") or []:
            d, st, rv = index[receipt], state[receipt], review[receipt]
            if st["status"] != "FETCH_FAILED" or d["ticker"] != q["code"] or rv["ticker"] != q["code"]:
                raise ValueError("RECEIPT_PROVENANCE_DISAGREES: " + receipt)
            targets.append({"receiptNo": receipt, "ticker": q["code"], "corpCode": d["corpCode"],
                            "reportName": d["reportName"], "receiptDate": d["receiptDate"],
                            "filerName": d["filerName"], "isAmendment": d["isAmendment"],
                            "amendmentMarker": (AMENDMENT.match(d["reportName"]) or [None, None])[1],
                            "priorDocumentXml": "DART_014_FILE_NOT_SERVED_ON_EXHAUSTED_RETRY",
                            "priorReviewCategory": rv["category"], "priorReviewReason": rv["reason"]})
    targets.sort(key=lambda t: (t["ticker"], t["receiptNo"]))
    body = {"contract": CONTRACT, "denominator": 22, "historicalOutcomeComputed": False, "keyRequired": False,
            "host": "dart.fss.or.kr", "maxNodesPerReceipt": MAX_NODES_PER_RECEIPT, "timeoutSeconds": 30,
            "maxBodyBytes": 8 << 20, "maxCalls": len(targets) * (1 + MAX_NODES_PER_RECEIPT),
            "counts": {c: sum(t["priorReviewCategory"] == c for t in targets)
                       for c in sorted({t["priorReviewCategory"] for t in targets})},
            "targets": targets,
            "inputs": {"signalHistoryCommit": P.SOURCE_COMMIT, "blobSha1": {p: IN.blob_sha1(blobs[p]) for p in sorted(blobs)},
                       "failureReviewSha256": IN.sha256((root / FAILURE_REVIEW).read_bytes()),
                       "kr22SourceRecoverySha256": IN.sha256((HERE / "kr22-source-recovery.json").read_bytes())}}
    return {**body, "planSha256": P.digest(body)}


def load_plan(path=PLAN_PATH):
    plan = json.loads(Path(path).read_text())
    body = {k: v for k, v in plan.items() if k != "planSha256"}
    if plan.get("contract") != CONTRACT or P.digest(body) != plan.get("planSha256"):
        raise ValueError("PLAN_DIGEST_MISMATCH")
    return plan


# --------------------------------------------------------------------------- #
# Collection (authorized environment only; reuses the existing public-viewer Collector)
# --------------------------------------------------------------------------- #
def _collector(plan):
    from scripts import collect_kr_industry_membership_sources as S   # existing, unedited
    return S.Collector(plan, plan["maxCalls"]), S.nodes


def fetch_receipt(collector, nodes, target, cap=MAX_NODES_PER_RECEIPT):
    receipt = target["receiptNo"]
    if not re.fullmatch(r"\d{14}", receipt):
        raise ValueError("EXACT_RECEIPT_REQUIRED")
    record = {"receiptNo": receipt, "responses": [], "nodes": [], "status": None}
    main = collector.request(MAIN + receipt)
    record["responses"].append(main)
    if main["status"] is None:
        record["status"] = "TRANSPORT_FAILURE"
        return record
    if main["status"] != 200 or main["raw"] is None:
        record["status"] = "HTTP_%s" % main["status"] if main.get("error") is None else main["error"]
        return record
    try:
        available = nodes(main["raw"], receipt)
    except UnicodeError:
        record["status"] = "MAIN_NOT_UTF8"
        return record
    if not available:
        record["status"] = "LISTED_BUT_VIEWER_EMPTY"
        return record
    if len(available) > cap:
        record["status"] = "NODE_CAP_EXCEEDED"
        record["nodeCount"] = len(available)
        return record
    for node in available:
        response = collector.request(VIEWER + urlencode({k: node[k] for k in NODE_KEYS}))
        response["node"] = node
        record["responses"].append(response)
        record["nodes"].append({"node": node, "status": response["status"], "sha256": response.get("sha256")})
    ok = all(n["status"] == 200 and n["sha256"] for n in record["nodes"])
    record["status"] = "SERVED" if ok else "NODE_FETCH_INCOMPLETE"
    return record


def collect(output, plan=None, collector=None, nodes=None):
    """Fetch every planned receipt into `output` (must not exist). Stops after repeated transport failures rather
    than repeating requests a gateway is refusing."""
    plan = plan or load_plan()
    if plan["historicalOutcomeComputed"]:
        raise ValueError("OUTCOME_FREE_PLAN_REQUIRED")
    if collector is None:
        collector, nodes = _collector(plan)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    objects, records, streak, stopped = {}, [], 0, None
    for target in plan["targets"]:
        try:
            record = fetch_receipt(collector, nodes, target, plan["maxNodesPerReceipt"])
        except ValueError as exc:
            if str(exc) != "CALL_BUDGET_EXCEEDED":
                raise
            stopped = "CALL_BUDGET_EXCEEDED"
            break
        for response in record["responses"]:
            raw = response.pop("raw", None)
            if raw is not None:
                objects.setdefault(hashlib.sha256(raw).hexdigest(), base64.b64encode(raw).decode())
        records.append(record)
        streak = streak + 1 if record["status"] == "TRANSPORT_FAILURE" else 0
        if streak >= MAX_CONSECUTIVE_TRANSPORT_FAILURES:
            stopped = "REPEATED_TRANSPORT_FAILURE"
            break
    archive = output / "objects.json.gz"
    archive.write_bytes(gzip.compress(json.dumps(objects, sort_keys=True, separators=(",", ":")).encode(), mtime=0))
    manifest = {"contract": MANIFEST_CONTRACT, "planSha256": plan["planSha256"], "records": records,
                "calls": collector.calls, "stopped": stopped, "archive": archive.name,
                "archiveSha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "historicalOutcomeComputed": False}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=1) + "\n")
    return manifest


# --------------------------------------------------------------------------- #
# Offline verification and candidate extraction
# --------------------------------------------------------------------------- #
def load_collection(directory, plan=None):
    plan = plan or load_plan()
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest.get("contract") != MANIFEST_CONTRACT or manifest.get("planSha256") != plan["planSha256"]:
        raise ValueError("MANIFEST_NOT_FOR_THIS_PLAN")
    raw = (directory / manifest["archive"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest["archiveSha256"]:
        raise ValueError("ARCHIVE_CHANGED")
    objects = {}
    for sha, b64 in json.loads(gzip.decompress(raw)).items():
        body = base64.b64decode(b64)
        if hashlib.sha256(body).hexdigest() != sha:
            raise ValueError("OBJECT_SHA_CHANGED: " + sha)
        objects[sha] = body
    return manifest, objects


def verify_record(target, record, objects):
    """Identity, date, amendment and node checks for one served receipt. Returns (verdict, reasons)."""
    if record["status"] != "SERVED":
        return "NOT_SERVED", [record["status"]]
    reasons = []
    main = objects.get(record["responses"][0].get("sha256"))
    if main is None:
        return "REFUSED", ["MAIN_OBJECT_MISSING"]
    text = main.decode("utf-8")
    title = (re.search(r"<title>(.*?)</title>", text, re.S) or [None, ""])[1]
    if text.count("openCorpInfoNew('%s'," % target["corpCode"]) != 1:
        reasons.append("ISSUER_IDENTITY_NOT_UNIQUE_IN_MAIN")
    if target["receiptDate"].replace("-", ".") not in title:
        reasons.append("RECEIPT_DATE_NOT_IN_TITLE")
    if target["amendmentMarker"] and "[" + target["amendmentMarker"] + "]" not in title:
        reasons.append("AMENDMENT_MARKER_NOT_IN_TITLE")
    for n in record["nodes"]:
        if n["node"]["rcpNo"] != target["receiptNo"]:
            reasons.append("FOREIGN_RECEIPT_NODE")
        if n["sha256"] not in objects:
            reasons.append("NODE_OBJECT_MISSING")
    return ("VERIFIED" if not reasons else "REFUSED"), reasons


def extract_candidates(record, objects):
    """Correction rows (정정전/정정후) and labelled decision rows from every node, as candidates only."""
    corrections, fields = [], {}
    for n in record["nodes"]:
        structure = DP.document_structure(objects[n["sha256"]].decode("utf-8"))
        for row in structure["rows"]:
            if row["isCorrectionTable"]:
                corrections.append({"node": n["node"]["text"], "cells": row["cells"]})
        for field, labels in FIELDS.items():
            for label in labels:
                for row in DP.labeled_rows(structure, label):
                    value = " | ".join(row["cells"][1:])
                    fields.setdefault(field, []).append({"node": n["node"]["text"], "label": label, "value": value,
                                                         "date": DP.korean_date(row["cells"][1]) if len(row["cells"]) > 1 else None})
    return {"correctionRows": corrections, "fieldCandidates": fields, "adopted": False}


def verify_and_extract(directory, plan=None):
    plan = plan or load_plan()
    manifest, objects = load_collection(directory, plan)
    targets = {t["receiptNo"]: t for t in plan["targets"]}
    out = []
    for record in manifest["records"]:
        if record["receiptNo"] not in targets:
            raise ValueError("RECEIPT_NOT_IN_PLAN: " + record["receiptNo"])
        t = targets[record["receiptNo"]]
        verdict, reasons = verify_record(t, record, objects)
        row = {"receiptNo": t["receiptNo"], "ticker": t["ticker"], "reportName": t["reportName"],
               "priorReviewCategory": t["priorReviewCategory"], "collectionStatus": record["status"],
               "verification": verdict, "reasons": reasons}
        if verdict == "VERIFIED":
            row.update(extract_candidates(record, objects))
        out.append(row)
    missing = sorted(set(targets) - {r["receiptNo"] for r in manifest["records"]})
    return {"contract": MANIFEST_CONTRACT + "_VERIFICATION", "planSha256": plan["planSha256"], "stopped": manifest["stopped"],
            "notAttempted": missing, "records": out,
            "counts": {k: sum(r["verification"] == k for r in out) for k in ("VERIFIED", "REFUSED", "NOT_SERVED")}}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("plan")
    c = sub.add_parser("collect")
    c.add_argument("--output", required=True)
    v = sub.add_parser("verify")
    v.add_argument("--input", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "collect":
        m = collect(args.output)
        print(json.dumps({"calls": m["calls"], "stopped": m["stopped"],
                          "status": {r["receiptNo"]: r["status"] for r in m["records"]}}, indent=1))
    elif args.cmd == "verify":
        print(json.dumps(verify_and_extract(args.input), ensure_ascii=False, indent=1))
    else:
        plan = build_plan()
        PLAN_PATH.write_text(json.dumps(plan, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
        json.dump({"planSha256": plan["planSha256"], "counts": plan["counts"], "targets": len(plan["targets"])}, sys.stdout)
        print()


if __name__ == "__main__":
    main()
