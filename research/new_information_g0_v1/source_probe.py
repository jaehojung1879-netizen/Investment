"""Outcome-blind OpenDART feasibility sampler. No portfolio or return inputs.

Live mode requires --live and an externally supplied OPENDART_API_KEY.
Only explicitly bounded date windows are queried. Never commit raw disclosures
or results containing investor names. This probe does NOT infer purpose changes.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path

WINDOWS = (
    ("2021-05-01", "2021-05-31"),
    ("2023-05-01", "2023-05-31"),
    ("2025-05-01", "2025-05-31"),
    ("2026-05-01", "2026-05-31"),
)
DETAILS = {"ownership_purpose": "D001", "insider": "D002"}
BASE = "https://opendart.fss.or.kr/api/"
MAX_RESPONSE_BYTES = 8_000_000
MAX_ZIP_EXPANDED_BYTES = 16_000_000


def request_bytes(endpoint: str, params: dict[str, str]) -> bytes:
    url = BASE + endpoint + "?" + urllib.parse.urlencode(params)
    # Do not log the URL: it contains the API secret.
    try:
        with urllib.request.urlopen(url, timeout=25) as response:
            data = response.read(MAX_RESPONSE_BYTES + 1)
    except Exception as exc:
        raise RuntimeError("OpenDART request failed; URL/key withheld") from None
    if len(data) > MAX_RESPONSE_BYTES:
        raise ValueError("Exceeded response size bound")
    return data


def parse_listing(payload: dict) -> list[dict]:
    status = str(payload.get("status", ""))
    if status == "013":
        return []
    if status != "000":
        raise ValueError("OpenDART non-success status " + status)
    rows = payload.get("list")
    if not isinstance(rows, list):
        raise ValueError("OpenDART listing missing list")
    out = []
    for row in rows:
        receipt = str(row.get("rcept_no", ""))
        date = str(row.get("rcept_dt", ""))
        if not (re.fullmatch(r"\d{14}", receipt) and re.fullmatch(r"\d{8}", date)):
            raise ValueError("Malformed receipt or filing date")
        name = str(row.get("report_nm", ""))
        out.append({
            "rcept_no": receipt,
            "rcept_dt": date,
            "corp_code": str(row.get("corp_code", "")),
            "report_nm": name,
            "correction_flag": any(mark in name for mark in ("기재정정", "첨부정정", "첨부추가")),
            "viewer": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + receipt,
        })
    return out


def summarize(rows: list[dict], *, truncated: bool, detail: str) -> dict:
    # Counts represent listing sample only, NOT the population or actual signals.
    receipts = {r["rcept_no"]: r for r in rows}
    unique = list(receipts.values())
    return {
        "detail": detail,
        "sampled_receipts": len(unique),
        "sampled_firms": len({r["corp_code"] for r in unique if r["corp_code"]}),
        "correction_receipts": sum(bool(r["correction_flag"]) for r in unique),
        "filings_by_year": dict(sorted(Counter(r["rcept_dt"][:4] for r in unique).items())),
        "pages_not_exhausted": truncated,
        "event_count": None,
        "independent_event_count": None,
        "purpose_change_count": None,
        "pit_verified_events": 0,
        "assessment": "METADATA_ONLY_NOT_SIGNAL",
    }


def scan_original_zip(binary: bytes) -> dict:
    """Fingerprint a public filing; don't auto-assign a purpose-change event."""
    if not zipfile.is_zipfile(io.BytesIO(binary)):
        raise ValueError("document.xml did not return a ZIP archive")
    n = 0
    found_heading = False
    with zipfile.ZipFile(io.BytesIO(binary)) as archive:
        for info in archive.infolist():
            n += info.file_size
            if n > MAX_ZIP_EXPANDED_BYTES:
                raise ValueError("Expanded archive exceeds safety limit")
            if info.is_dir() or not info.filename.lower().endswith((".xml", ".html", ".htm")):
                continue
            text_bytes = archive.read(info)
            for codec in ("utf-8", "euc-kr"):
                try:
                    decoded = text_bytes.decode(codec)
                    break
                except UnicodeError:
                    decoded = ""
            if "보유목적" in decoded or "보유 목적" in decoded:
                found_heading = True
    return {
        "sha256": hashlib.sha256(binary).hexdigest(),
        "expanded_bytes": n,
        "has_purpose_text_hint": found_heading,
        "manual_original_and_prior_filing_comparison_required": True,
        "confirmed_purpose_switch": None,
    }


def offline(path: Path) -> dict:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(obj, list):
        pages = obj
    else:
        pages = [obj]
    rows = [r for p in pages for r in parse_listing(p)]
    return summarize(rows, truncated=True, detail="fixture_unbounded_population")


def live(*, key: str, documents_per_detail: int) -> dict:
    results = {}
    for label, detail in DETAILS.items():
        all_rows = []
        n_reported_total = 0
        for start, end in WINDOWS:
            payload = json.loads(request_bytes("list.json", {
                "crtfc_key": key,
                "bgn_de": start.replace("-", ""),
                "end_de": end.replace("-", ""),
                "last_reprt_at": "N",  # Corrections must remain visible.
                "pblntf_ty": "D",
                "pblntf_detail_ty": detail,
                "sort": "date",
                "sort_mth": "asc",
                "page_no": "1",
                "page_count": "100",
            }).decode("utf-8"))
            rows = parse_listing(payload)
            all_rows.extend(rows)
            n_reported_total += int(payload.get("total_count") or 0)
        item = summarize(
            all_rows,
            truncated=n_reported_total > len(all_rows),
            detail=detail,
        )
        # Only fingerprint a small deterministic set; never save personal names.
        samples = sorted({r["rcept_no"] for r in all_rows})[:documents_per_detail]
        docs = []
        for receipt in samples:
            info = scan_original_zip(request_bytes("document.xml", {
                "crtfc_key": key,
                "rcept_no": receipt,
            }))
            docs.append({"rcept_no": receipt, **info})
        item["document_fingerprints"] = docs
        item["requested_windows"] = WINDOWS
        item["total_reported_in_windows"] = n_reported_total
        results[label] = item
    return {
        "research_status": "SOURCE_AUDIT_ONLY",
        "no_price_or_outcome_access": True,
        "asof_caveat": "rcept_dt lacks time; use NEXT_XKRX_SESSION only after filing clock checked",
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--offline-list", type=Path)
    p.add_argument("--live", action="store_true")
    p.add_argument("--documents-per-detail", type=int, default=0)
    p.add_argument("--output", type=Path)
    args = p.parse_args(argv)
    if args.live == bool(args.offline_list):
        p.error("Choose exactly one of --live and --offline-list")
    if not 0 <= args.documents_per_detail <= 6:
        p.error("--documents-per-detail must be 0..6")
    if args.live:
        key = os.environ.get("OPENDART_API_KEY", "")
        if not re.fullmatch(r"[A-Za-z0-9]{40}", key):
            p.error("Provide OPENDART_API_KEY through environment (never CLI)")
        output = live(key=key, documents_per_detail=args.documents_per_detail)
    else:
        if args.documents_per_detail:
            p.error("Offline mode has no document retrieval")
        output = {"research_status": "SYNTHETIC_FIXTURE_ONLY",
                  "results": offline(args.offline_list)}
    encoded = json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
