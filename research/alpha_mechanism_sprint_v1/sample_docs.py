"""Fetch DART ``document.xml`` for preliminary-earnings receipts and keep the results table.

The plan comes from ``analyze.py`` (``--write-sample-plan`` for the seeded
parser-development sample, ``--write-full-plan`` for every original filing).
Stored per receipt: the SHA-256 of the served bytes, the results-table text
(so the parser can be revised without refetching) and the parsed fields.
The API key is never written. Outcome-blind.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sprint  # noqa: E402

ENDPOINT = "https://opendart.fss.or.kr/api/document.xml"


def fetch(key: str, rcept_no: str) -> bytes:
    query = urllib.parse.urlencode({"crtfc_key": key, "rcept_no": rcept_no})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(f"{ENDPOINT}?{query}", timeout=60) as response:
                return response.read()
        except OSError:
            if attempt == 3:
                raise
            time.sleep(2 ** (attempt + 1))
    raise AssertionError("unreachable")


def parse_payload(blob: bytes) -> dict:
    if not blob.startswith(b"PK"):
        return {"served": "NOT_ZIP", "bytes": len(blob), "head": blob[:120].decode("utf-8", "replace")}
    archive = zipfile.ZipFile(io.BytesIO(blob))
    texts = []
    for name in sorted(archive.namelist()):
        raw = archive.read(name)
        for encoding in ("utf-8", "euc-kr", "cp949"):
            try:
                texts.append(raw.decode(encoding))
                break
            except UnicodeDecodeError:
                continue
    text = sprint.html_to_text(" ".join(texts))
    parsed = sprint.parse_prelim_text(text)
    parsed["tableText"] = sprint.table_region(text)
    parsed["served"] = "ZIP"
    parsed["bytes"] = len(blob)
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--first-confirmed-per-unit", action="store_true",
                        help="per (corp, quarter) fetch in receipt order and stop at the first filing that states that quarter")
    args = parser.parse_args(argv)
    key = os.environ.get("DART_API_KEY")
    if not key:
        print("DART_API_KEY missing", file=sys.stderr)
        return 2
    raw_plan = Path(args.plan).read_bytes()
    plan = json.loads(gzip.decompress(raw_plan) if raw_plan[:2] == b"\x1f\x8b" else raw_plan)

    def one(item):
        record = dict(item)
        try:
            blob = fetch(key, item["rcept_no"])
        except OSError as error:  # kept and reported, never read as "no earnings stated"
            record.update({"served": "FETCH_ERROR", "error": type(error).__name__})
            return record
        if blob.lstrip().startswith(b"{") or blob.lstrip().startswith(b"<?xml") and b"<status>" in blob[:300]:
            record.update({"served": "DART_STATUS", "head": blob[:200].decode("utf-8", "replace")})
            if b"020" in blob[:200] or b"010" in blob[:200] or b"011" in blob[:200]:
                raise SystemExit(f"DART refused: {blob[:200]!r}")
            return record
        record["sha256"] = hashlib.sha256(blob).hexdigest()
        record.update(parse_payload(blob))
        return record

    if args.first_confirmed_per_unit:
        units: dict[tuple[str, str], list[dict]] = {}
        for item in plan["sample"]:
            units.setdefault((item["corp"], item["quarter"]), []).append(item)

        def unit_walk(items):
            fetched = []
            for item in sorted(items, key=lambda r: r["rcept_no"]):
                record = one(item)
                fetched.append(record)
                quarter = sprint.stated_quarter(record) if record.get("served") == "ZIP" else None
                if quarter is not None and quarter.isoformat() == item["quarter"]:
                    break
            return fetched

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            records = [r for batch in pool.map(unit_walk, list(units.values())) for r in batch]
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            records = list(pool.map(one, plan["sample"]))
    records.sort(key=lambda r: r["rcept_no"])
    with gzip.GzipFile(args.out, "wb", mtime=0) as handle:
        for record in records:
            handle.write((json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    print(json.dumps({"fetched": len(records), "zip": sum(r["served"] == "ZIP" for r in records)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
