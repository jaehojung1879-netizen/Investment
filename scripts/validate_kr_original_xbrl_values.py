"""Audit the immutable 60-fact sample; exit 0 PASS, 2 FAIL, 3 BLOCKED, 4 process error.

This script never repairs candidate data. --download uses the existing
DART_API_KEY and repository HTTP helper solely for source transport.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import gzip
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import kr_xbrl_validation_sample as S  # noqa: E402
from pipeline import kr_xbrl_value_validation as V  # noqa: E402


def materialize(input_root, protocol):
    """Copy only explicitly frozen accounting shards from the pinned git object."""
    paths = ["ledger/fundamentals/kr-xbrl-original/dart-xbrl-2015.jsonl.gz"]
    paths.extend("ledger/fundamentals/kr-candidate-merged/" + name
                 for name in protocol["candidate"]["gitBlobSha1"])
    for relative in paths:
        dest = S.permitted_path(input_root, relative)
        raw = subprocess.check_output(["git", "show", S.SOURCE_COMMIT + ":" + relative], cwd=ROOT)
        if dest.exists():
            if dest.read_bytes() != raw:
                raise ValueError("REFUSE_OVERWRITING_DIFFERENT_INPUT")
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("xb") as stream:
                stream.write(raw)


def candidate_values(input_root, protocol, sample):
    """Join amounts only after frozen-file/frame verification has succeeded."""
    wanted = {r["recordId"] for r in sample["items"]}
    rows = {}
    for name in protocol["candidate"]["gitBlobSha1"]:
        path = S.permitted_path(input_root, "ledger/fundamentals/kr-candidate-merged/" + name)
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line, parse_float=Decimal, parse_int=Decimal)
                if row["id"] in wanted:
                    if row["id"] in rows:
                        raise ValueError("DUPLICATE_CANDIDATE_RECORD")
                    # Period metadata must retain integer shape for exact frame reproduction.
                    row["fiscalYear"] = int(row["fiscalYear"])
                    rows[row["id"]] = row
    result = {}
    for item in sample["items"]:
        row = rows[item["recordId"]]
        projected = {r["identity"]: r for r in S.project_record(row)}
        if projected[item["identity"]] != item:
            raise ValueError("CANDIDATE_PROVENANCE_DIFFERS_FROM_FROZEN_ITEM")
        field = V.RULES[item["family"]][3]
        result[item["identity"]] = row["accounts"][item["account"]]["amounts"][field]
    return result


def source_path(source_dir, item, suffix):
    receipts = item["receiptNos"]
    if len(receipts) != 1 or not re.fullmatch(r"[0-9]{14}", receipts[0]):
        raise ValueError("INVALID_SOURCE_RECEIPT")
    if not re.fullmatch(r"1101[234]", item["reportCode"]):
        raise ValueError("INVALID_SOURCE_REPORT_CODE")
    path = source_dir / (receipts[0] + "-" + item["reportCode"] + suffix)
    if path.is_symlink() or not path.resolve().is_relative_to(source_dir.resolve()):
        raise ValueError("SOURCE_PATH_ESCAPE_REFUSED")
    return path


def download_sources(source_dir, sample):
    key = os.environ.get("DART_API_KEY", "").strip()
    if not key:
        return {"status": "BLOCKED_ON_SOURCE_ACCESS", "reason": "DART_API_KEY absent"}
    # Import only for transport; no XS function or extraction path is invoked.
    from scripts.collect_dart_raw_statements import http, call_json
    source_dir.mkdir(parents=True, exist_ok=True)
    failures, seen = [], set()
    for item in sample["items"]:
        receipt = item["receiptNos"][0]
        if (receipt, item["reportCode"]) in seen:
            continue
        seen.add((receipt, item["reportCode"]))
        try:
            archive_path = source_path(source_dir, item, ".zip")
            if not archive_path.exists():
                raw = http("fnlttXbrl.xml", {"crtfc_key": key, "rcept_no": receipt,
                                           "reprt_code": item["reportCode"]})
                if not raw.startswith(b"PK"):
                    failures.append({"receipt": receipt, "reason": "DART did not serve a ZIP"})
                    continue
                with archive_path.open("xb") as stream:
                    stream.write(raw)
            index_path = source_path(source_dir, item, ".filing.json")
            if not index_path.exists():
                rows, page, total = [], 1, 1
                while page <= total:
                    payload = call_json("list.json", {"crtfc_key": key, "corp_code": item["corpCode"],
                        "bgn_de": receipt[:8], "end_de": receipt[:8], "pblntf_ty": "A",
                        "page_count": "100", "page_no": str(page)})
                    if payload.get("status") != "000":
                        raise ValueError("INDEX_NOT_SERVED")
                    total = int(payload.get("total_page", 0))
                    if total < page or total > 100:
                        raise ValueError("INVALID_PAGINATION")
                    rows.extend(payload.get("list", []))
                    page += 1
                with index_path.open("x", encoding="utf-8") as stream:
                    json.dump(rows, stream, ensure_ascii=False, sort_keys=True, indent=2)
        except Exception as exc:
            # Never expose transport exception text: it may carry a secret URL.
            failures.append({"receipt": receipt, "reason": type(exc).__name__})
    return {"status": "COMPLETED_WITH_SOURCE_ERRORS" if failures else "COMPLETED", "failures": failures}


def run(input_root, source_dir, download=False, materialize_from_git=False):
    protocol, sample = V.load_frozen(ROOT)
    if materialize_from_git:
        materialize(input_root, protocol)
    V.verify_frame(input_root, protocol, sample)
    values = candidate_values(input_root, protocol, sample)
    access = download_sources(source_dir, sample) if download else {"status": "LOCAL_SOURCE_ONLY"}
    results = []
    for item in sample["items"]:
        value = values[item["identity"]]
        try:
            path = source_path(source_dir, item, ".zip")
            index = source_path(source_dir, item, ".filing.json")
            raw = path.read_bytes() if path.exists() else None
            rows = json.loads(index.read_text()) if index.exists() else None
            row = V.validate_item(item, value, raw, rows)
            if index.exists():
                row["filingIndexSha256"] = V.sha256(index.read_bytes())
            results.append(row)
        except Exception as exc:
            results.append(V.outcome(item, value, "INFRASTRUCTURE_ERROR",
                                     "independent reader process error: " + type(exc).__name__))
    summary = V.summarize(results)
    return {"study": S.STUDY, "startingMain": S.MAIN_COMMIT,
            "candidateSha256": protocol["candidate"]["sha256"], "sourceCommit": S.SOURCE_COMMIT,
            "freezeCommit": V.FREEZE_COMMIT, "sampleSha256": V.SAMPLE_SHA256,
            "frameSize": protocol["frame"]["size"], "sampleSize": len(sample["items"]),
            "sourceAccess": access, **summary, "results": results,
            "sourceConfidence": "CANDIDATE_UNCONFIRMED",
            "promotionRecommended": summary["verdict"] == "PASS",
            "startupDeviation": protocol["startupDeviation"],
            "alphaOutcomesUsed": False, "historicalAlphaExecuted": False}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input-root", required=True, type=Path)
    p.add_argument("--source-dir", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--materialize-from-git", action="store_true")
    p.add_argument("--download", action="store_true")
    args = p.parse_args(argv)
    if args.output.exists():
        p.error("Output exists; use a new audit filename to preserve previous evidence")
    try:
        report = run(args.input_root, args.source_dir, args.download, args.materialize_from_git)
    except Exception as exc:
        report = {"study": S.STUDY, "verdict": "INFRASTRUCTURE_ERROR",
                  "reason": type(exc).__name__, "detail": "Preflight could not produce a complete audit"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")
    print(json.dumps({k: report[k] for k in ("verdict", "counts", "sourceAccess") if k in report}))
    return {"PASS": 0, "FAIL": 2, "BLOCKED": 3, "INFRASTRUCTURE_ERROR": 4}[report["verdict"]]


if __name__ == "__main__":
    raise SystemExit(main())
