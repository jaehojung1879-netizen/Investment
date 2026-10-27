"""Independent acquisition receipt for #286's fixed 68 original DART XBRL filings. No price, return or outcome.

#286's public download route (`dart.fss.or.kr/pdf/download/ifrs.do`, its unchanged `portable_collection`) was run
from this environment first: 136 requests, every attachment request answered HTTP 200 with an empty body, so all 68
were `SOURCE_ATTACHMENT_UNRESOLVED / PUBLIC_ATTACHMENT_NOT_A_ZIP`. This module uses DART's official original-XBRL API
instead (`opendart.fss.or.kr/api/fnlttXbrl.xml`, an authenticated key), the endpoint this repository already reads
for fiscal-2015 originals. It is a different ROUTE to the same receipt and is labelled as such on every row; whether
its ZIP is byte-identical to the public popup's ZIP is not known, because that popup served nothing.

Reads #286's pinned `portable-plan.json.gz` (by SHA-256) and edits nothing of #286. Raw ZIPs stay in a local output
directory and are never committed; the receipt records receipt number, route, SHA-256, size and identity checks.
Usage:
  DART_API_KEY=... python -I collect_receipt.py collect <plan.json.gz> <new output dir>
  python -I collect_receipt.py receipt <plan.json.gz> <output dir> <receipt.json>
  DART_API_KEY=... python -I collect_receipt.py verify <receipt.json>     # re-fetch in memory, compare SHA-256
"""
from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

PLAN_SHA256 = "2c73067ced7c59a2b23a693b5db6aca37f45d69c478c2f789df877126f738766"
API = "https://opendart.fss.or.kr/api/fnlttXbrl.xml"
ANNUAL = "11011"
MAX_BYTES = 64 << 20


def load_plan(path):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != PLAN_SHA256:
        raise ValueError("PLAN_NOT_THE_PINNED_FIXED68_PLAN")
    plan = json.loads(gzip.decompress(raw))
    targets = plan["targets"]
    if len(targets) != 68 or len({t["receipt"] for t in targets}) != 68:
        raise ValueError("FIXED_68_CHANGED")
    return targets


def collect(plan_path, out_dir, key, pause=0.5):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=False)
    entries = []
    for t in load_plan(plan_path):
        query = urllib.parse.urlencode({"crtfc_key": key, "rcept_no": t["receipt"], "reprt_code": ANNUAL})
        status, raw, error = None, b"", None
        try:
            with urllib.request.urlopen(API + "?" + query, timeout=60) as resp:
                status, raw = resp.status, resp.read(MAX_BYTES + 1)
        except OSError as exc:            # never print the URL: it carries the key
            error = type(exc).__name__
        name = t["receipt"] + ".bin"
        (out / name).write_bytes(raw)
        entries.append({"receipt": t["receipt"], "httpStatus": status, "transportError": error, "file": name,
                        "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
                        "retrievedAt": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()})
        time.sleep(pause)
    (out / "manifest.json").write_text(json.dumps({"route": "OPENDART_FNLTTXBRL_API", "reprtCode": ANNUAL,
                                                    "entries": entries}, indent=1) + "\n")
    return entries


def inspect_zip(raw, corp_code, period_end_month):
    """Identity checks on one served package, read in memory only. Every check is reported, none is required."""
    if not raw.startswith(b"PK"):
        status = re.search(rb"<status>\s*(\d{3})\s*</status>", raw[:4096])
        return {"isZip": False, "dartStatus": status.group(1).decode() if status else None}
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        infos = z.infolist()
        names = [i.filename for i in infos]
        if len(infos) > 256 or sum(i.file_size for i in infos) > 512 << 20:
            return {"isZip": True, "refused": "ZIP_TOO_LARGE"}
        instances = [i for i in infos if i.filename.lower().endswith(".xbrl") and "/" not in i.filename
                     and "\\" not in i.filename]
        doc = z.read(instances[0]).decode("utf-8", "replace") if len(instances) == 1 else ""
    year, month = period_end_month.split("-")
    ends = set(re.findall(r"<(?:xbrli:)?endDate>\s*(\d{4}-\d{2})-\d{2}\s*</", doc))
    instants = set(re.findall(r"<(?:xbrli:)?instant>\s*(\d{4}-\d{2})-\d{2}\s*</", doc))
    identifiers = set(re.findall(r"<(?:xbrli:)?identifier[^>]*>\s*([^<\s]+)\s*</", doc))
    return {"isZip": True, "members": len(names), "instanceFiles": len(instances),
            "instanceNamedForCorpCode": bool(instances) and instances[0].filename.startswith(corp_code + "_"),
            "entityIdentifierIsCorpCode": identifiers == {corp_code},
            "entityIdentifiers": sorted(identifiers)[:3],
            "fiscalPeriodEndPresent": f"{year}-{month}" in ends | instants,
            "backslashMemberNames": sum("\\" in n for n in names)}


def receipt(plan_path, out_dir, receipt_path):
    out = Path(out_dir)
    manifest = json.loads((out / "manifest.json").read_text())
    targets = {t["receipt"]: t for t in load_plan(plan_path)}
    rows = []
    for e in manifest["entries"]:
        t = targets[e["receipt"]]
        raw = (out / e["file"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != e["sha256"]:
            raise ValueError("RAW_CHANGED: " + e["receipt"])
        checks = inspect_zip(raw, t["corpCode"], t["periodEndMonth"])
        ok = checks.get("isZip") and checks.get("instanceNamedForCorpCode") and checks.get("entityIdentifierIsCorpCode") \
            and checks.get("fiscalPeriodEndPresent")
        rows.append({"receipt": e["receipt"], "corpCode": t["corpCode"], "ticker": t["ticker"],
                     "fiscalYear": t["fiscalYear"], "periodEndMonth": t["periodEndMonth"],
                     "availableFrom": t["availableFrom"], "route": "OPENDART_FNLTTXBRL_API",
                     "httpStatus": e["httpStatus"], "transportError": e["transportError"],
                     "sha256": e["sha256"], "bytes": e["bytes"], "retrievedAt": e["retrievedAt"], "checks": checks,
                     "status": "ACQUIRED_IDENTITY_CHECKED_VALUES_UNVERIFIED" if ok else
                               ("ACQUIRED_IDENTITY_NOT_CONFIRMED" if checks.get("isZip") else "NOT_ACQUIRED")})
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    doc = {"schema": "KR_WC68_INDEPENDENT_ACQUISITION_RECEIPT_V1", "planSha256": PLAN_SHA256,
           "forPr": "jaehojung1879-netizen/Investment#286", "route": "OPENDART_FNLTTXBRL_API",
           "publicPopupRouteResult": {"requests": 136, "statusCounts": {"SOURCE_ATTACHMENT_UNRESOLVED": 68},
                                      "reason": "PUBLIC_ATTACHMENT_NOT_A_ZIP (HTTP 200, empty body)"},
           "rawBytesCommitted": False, "historicalOutcomesRead": 0, "sourceAdmissionAuthorized": False,
           "originalFinancialValuesVerified": False, "statusCounts": dict(sorted(counts.items())), "rows": rows}
    Path(receipt_path).write_text(json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    return doc


def verify(receipt_path, key, pause=0.5):
    """Hash-anchored re-acquisition: fetch each receipt again in memory and compare with the committed SHA-256.
    The route is byte-deterministic (re-fetches on 2026-10-27 matched exactly), so a verifier needs the key, not the
    bytes; nothing is written to disk and nothing needs to be redistributed."""
    doc = json.loads(Path(receipt_path).read_text())
    if doc.get("planSha256") != PLAN_SHA256:
        raise ValueError("RECEIPT_NOT_FOR_THE_PINNED_PLAN")
    result = {"match": 0, "differ": [], "transportError": []}
    for r in doc["rows"]:
        query = urllib.parse.urlencode({"crtfc_key": key, "rcept_no": r["receipt"], "reprt_code": ANNUAL})
        try:
            with urllib.request.urlopen(API + "?" + query, timeout=60) as resp:
                raw = resp.read(MAX_BYTES + 1)
        except OSError as exc:            # never print the URL: it carries the key
            result["transportError"].append([r["receipt"], type(exc).__name__])
            continue
        if hashlib.sha256(raw).hexdigest() == r["sha256"]:
            result["match"] += 1
        else:
            result["differ"].append(r["receipt"])
        time.sleep(pause)
    return result


def main(argv):
    if argv[0] == "collect":
        key = os.environ.get("DART_API_KEY")
        if not key:
            raise SystemExit("DART_API_KEY is required")
        entries = collect(argv[1], argv[2], key)
        print(json.dumps({"entries": len(entries), "zip": sum(e["bytes"] > 0 for e in entries)}))
    elif argv[0] == "verify":
        key = os.environ.get("DART_API_KEY")
        if not key:
            raise SystemExit("DART_API_KEY is required")
        print(json.dumps(verify(argv[1], key)))
    elif argv[0] == "receipt":
        print(json.dumps(receipt(argv[1], argv[2], argv[3])["statusCounts"]))


if __name__ == "__main__":
    main(sys.argv[1:])
