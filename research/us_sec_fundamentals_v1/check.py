"""Compare existing cash-profitability coverage with and without the SEC asset input."""
from __future__ import annotations

import argparse
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path

from pipeline import us_cash_profitability as cp
from pipeline.us_total_assets_source import normalize_cik
from scripts.audit_finnhub_balance_sheet_coverage import LAST_AS_OF, MEMBERSHIP, read_store
from .assets import features_as_of, load_assets, with_sec_assets

SECTORS = MEMBERSHIP.parent.parent / "data/research/us-capital-allocation-alpha-v1/sp500-snapshot-sectors.json.gz"
FEATURES = ("cashOperatingProfitability", "accrualsToAssets", "operatingProfitabilityToAssets")


def measure(store: Path) -> dict:
    records, shards = read_store(store)
    if not records:
        raise ValueError(f"No Finnhub filing shards in {store}")
    assets = load_assets()
    by_ticker = defaultdict(list)
    attached = set()
    for record in records:
        by_ticker[record["ticker"]].append(record)
        if with_sec_assets(record, assets, LAST_AS_OF) is not record:
            attached.add((record["cik"], record["accession"]))
    as_of = LAST_AS_OF.isoformat()
    snapshot = json.loads(gzip.decompress(MEMBERSHIP.read_bytes()))["snapshots"][-1]
    members = sorted(ticker for ticker in snapshot["members"] if ticker in by_ticker)
    sectors = json.loads(gzip.decompress(SECTORS.read_bytes()))["snapshots"]
    identity = next(row["rows"] for row in sectors if row["date"] == snapshot["date"])
    before, after, legacy = Counter(), Counter(), Counter()
    member_ciks = 0
    for ticker in members:
        values = by_ticker[ticker]
        old = cp.features_as_of(values, as_of)
        legacy.update(feature for feature in FEATURES if old[feature] is not None)
        cik = normalize_cik(identity.get(ticker, {}).get("cik"))
        if not cik:
            continue
        member_ciks += 1
        issuer_records = [record for record in values if normalize_cik(record.get("cik")) == cik]
        original = cp.features_as_of(issuer_records, as_of)
        supplemented = features_as_of(values, as_of, assets, cik=cik)
        for feature in FEATURES:
            before[feature] += original[feature] is not None
            after[feature] += supplemented[feature] is not None
            if original[feature] is not None and original[feature] != supplemented[feature]:
                raise ValueError(f"SEC overlay changed an existing value: {ticker}/{feature}")
    return {
        "asOf": as_of, "membershipSnapshot": snapshot["date"], "memberCount": len(members),
        "filingRows": len(records), "sourceShards": shards,
        "secAssetRows": len(assets), "uniqueFilingsSupplementedByDate": len(attached),
        "memberCountWithDatedCik": member_ciks, "legacyTickerOnlyCounts": dict(legacy),
        "featureCountsBefore": dict(before), "featureCountsWithSec": dict(after),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", required=True, type=Path, help="Directory containing the existing Finnhub JSONL gzip shards")
    args = parser.parse_args()
    print(json.dumps(measure(args.store), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
