"""Derive reproducible public source requests; preserve existing request files."""
from pathlib import Path
import argparse
import json

from research.us_topk_market_cap_v1.inputs import read

ROOT = Path(__file__).resolve().parents[2]


def create(path, rows):
    if path.exists():
        return
    path.write_text(json.dumps(rows, indent=2) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", type=Path, required=True)
    ap.add_argument("--uploaded", type=Path, required=True)
    ap.add_argument("--phase", choices=["targets", "classes", "extension"], required=True)
    args = ap.parse_args()
    args.private.mkdir(parents=True, exist_ok=True, mode=0o700)
    if args.private.resolve().is_relative_to(ROOT):
        raise ValueError("PRIVATE_SOURCE_REQUESTS_MUST_BE_OUTSIDE_GIT_CHECKOUT")
    if args.phase == "targets":
        source = read(ROOT / "data/research/us-capital-allocation-alpha-v1/sp500-snapshot-sectors.json.gz")
        targets = {int(r["cik"]) for s in source["snapshots"] for r in s["rows"].values() if r.get("cik")}
        create(args.private / "cik-targets.json", sorted(targets))
    elif args.phase == "classes":
        missing = []
        for receipt in read(args.private / "sec-companyfacts-receipts.json"):
            if receipt["status"] != 200:
                continue
            source = read(args.private / receipt["object"])
            facts = []
            for ns, tag in [("dei", "EntityCommonStockSharesOutstanding"), ("us-gaap", "CommonStockSharesOutstanding")]:
                facts += source["facts"].get(ns, {}).get(tag, {}).get("units", {}).get("shares", [])
            if not any("2022-01-01" < r["filed"] < "2026-09-11" for r in facts):
                missing.append({"cik": source["cik"], "name": source["entityName"]})
        create(args.private / "no-standard-shares.json", missing)
    else:
        source = read(args.uploaded / "historical-issuer-candidates.json")
        ciks = {int(r["cik"]) for r in source if any(r["first_week"] <= f"{y}-12-31" and r["last_week"] >= f"{y}-01-01" for y in (2018, 2020, 2022))}
        create(args.private / "extension-cik-targets.json", sorted(c for c in ciks if not (args.private / "sec-companyfacts" / f"{c}.json.gz").exists()))


if __name__ == "__main__":
    main()
