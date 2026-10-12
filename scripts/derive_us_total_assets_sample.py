"""Derive the FIXED sample the total-assets source diagnostic is judged on, from the stored Finnhub shards only. Offline: no vendor, no key.

    python scripts/derive_us_total_assets_sample.py --from-git origin/signal-history [--output PATH]
    python scripts/derive_us_total_assets_sample.py --store DIR      # DIR holds finnhub-*.jsonl.gz

The sample is chosen by a hash of the ticker, never by what any vendor returns or by an outcome, so no source is favoured by its selection:

  RECENTLY_MISSING     the latest filing of the ticker first served on/after 2026-10-01 with no `Assets` in its stored balance sheet
  RECENT_COMPLETE      the latest filing of the same ticker first served before that day with `Assets` and a 2026 period end (the "previously complete" side)
  HISTORICAL_EARLIEST  the ticker's earliest stored filing that has `Assets` (does the source reach the replay's first years?)
  HISTORICAL_ANNUAL    the ticker's 10-K with `Assets` closest to 2019-12-31 (an annual control, mid-history)

Eight tickers that have all four; if fewer than eight do, the shortfall is recorded rather than filled from a looser rule. Amendment forms (10-K/A,
10-Q/A) do not exist in the stored population, so correction-versus-original is tested on what the SEC facts carry, and that is said in the output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from audit_finnhub_balance_sheet_coverage import extract_from_git, read_store  # noqa: E402
from probe_us_total_assets_sources import digest_of  # noqa: E402

OUTPUT = ROOT / "docs/us-readiness/us-total-assets-source-sample-v1.json"
CONTRACT = "US_TOTAL_ASSETS_SOURCE_SAMPLE_V1"
SPLIT = "2026-10-01"
TICKERS = 8


def assets_of(record: dict) -> float | None:
    for entry in (record.get("statements") or {}).get("bs") or []:
        if entry.get("concept") == "us-gaap_Assets" and isinstance(entry.get("value"), (int, float)):
            return float(entry["value"])
    return None


def row(record: dict, group: str) -> dict:
    return {"id": record["id"], "group": group, "ticker": record["ticker"], "cik": str(int(record["cik"])) if record.get("cik") else None,
            "accession": record["accession"], "form": record.get("form"), "periodEnd": record["periodEnd"],
            "fiscalYear": record.get("fiscalYear"), "fiscalQuarter": record.get("fiscalQuarter"), "availableFrom": record["availableFrom"],
            "acceptedDate": record.get("acceptedDate"), "storedAssets": assets_of(record), "storedCollectedAt": record.get("collectedAt")}


def derive(records: list[dict], store_commit: str | None, shards: list[dict]) -> dict:
    by_ticker: dict[str, list[dict]] = {}
    for record in records:
        if record.get("cik"):
            by_ticker.setdefault(record["ticker"], []).append(record)
    chosen, shortfall = [], []
    for ticker in sorted(by_ticker, key=lambda t: hashlib.sha256(t.encode()).hexdigest()):
        rows = sorted(by_ticker[ticker], key=lambda r: (r["periodEnd"], r["accession"]))
        missing = [r for r in rows if r.get("collectedAt", "")[:10] >= SPLIT and assets_of(r) is None]
        complete_recent = [r for r in rows if r.get("collectedAt", "")[:10] < SPLIT and assets_of(r) is not None and r["periodEnd"] >= "2026-01-01"]
        complete = [r for r in rows if assets_of(r) is not None]
        annual = [r for r in complete if r.get("form") == "10-K" and "2017-01-01" <= r["periodEnd"] <= "2021-12-31"]
        if not (missing and complete_recent and complete and annual):
            continue
        parts = [row(missing[-1], "RECENTLY_MISSING"), row(complete_recent[-1], "RECENT_COMPLETE"), row(complete[0], "HISTORICAL_EARLIEST"),
                 row(min(annual, key=lambda r: abs((int(r["periodEnd"][:4]) - 2019) * 366 + (int(r["periodEnd"][5:7]) - 12) * 31)), "HISTORICAL_ANNUAL")]
        if len({p["id"] for p in parts}) < 4:
            continue
        chosen.append((ticker, parts))
        if len(chosen) == TICKERS:
            break
    if len(chosen) < TICKERS:
        shortfall.append(f"only {len(chosen)} tickers have all four filing groups")
    filings = [p for _, parts in chosen for p in parts]
    sample = {"contract": CONTRACT, "storeCommit": store_commit, "split": SPLIT, "selection": "sha256(ticker) order; first tickers having all four groups",
              "probeTickers": [{"ticker": t, "cik": parts[0]["cik"]} for t, parts in chosen], "filings": filings, "shortfall": shortfall,
              "shards": shards,
              "populationFacts": {"storedFilings": len(records), "recentlyMissing": sum(1 for r in records if r.get("collectedAt", "")[:10] >= SPLIT and assets_of(r) is None),
                                  "amendmentForms": sum(1 for r in records if str(r.get("form") or "").endswith("/A")),
                                  "formsPresent": sorted({str(r.get("form")) for r in records})}}
    sample["digest"] = digest_of(sample)
    return sample


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-git")
    parser.add_argument("--store", type=Path)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    if bool(args.from_git) == bool(args.store):
        parser.error("exactly one of --from-git / --store")
    commit = None
    if args.from_git:
        with tempfile.TemporaryDirectory() as tmp:
            commit = extract_from_git(args.from_git, Path(tmp))
            records, shards = read_store(Path(tmp) / "ledger/fundamentals/us")
    else:
        records, shards = read_store(args.store)
    sample = derive(records, commit, shards)
    args.output.write_text(json.dumps(sample, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{len(sample['filings'])} filings over {len(sample['probeTickers'])} tickers; digest {sample['digest'][:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
