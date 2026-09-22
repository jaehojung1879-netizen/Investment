"""Extract today's fundamental-acceleration candidate list from the live
build's own output.

`data/site-data.json`'s `longTerm.regions.<region>.researchTable` is the
live long-term opportunity scan's own candidate universe -- the same
~20-30 names per region `longterm.score_cross_section` ranks, each row
already carrying `ticker`, `region`, `sector` and `factorPercentiles`.
This script reads that table and writes exactly the JSONL shape
`fundamental_acceleration_seal.build_candidate_rows`/
`scripts/seal_fundamental_acceleration_signal.py` expect
(`ticker`/`region`/`sector`/`factorPercentiles.quality`), so the
prospective sealing script has a real candidate source rather than a
placeholder.

Reads only; writes no production output.
"""
from __future__ import annotations

import argparse
import json


def extract_candidates(site_data: dict) -> list[dict]:
    candidates: list[dict] = []
    regions = ((site_data.get("longTerm") or {}).get("regions")) or {}
    for region, payload in regions.items():
        for row in payload.get("researchTable") or []:
            ticker = row.get("ticker")
            if not ticker:
                continue
            candidates.append({
                "ticker": ticker,
                "region": row.get("region") or region,
                "sector": row.get("sector"),
                "factorPercentiles": {"quality": (row.get("factorPercentiles") or {}).get("quality")},
            })
    return candidates


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site_data", help="Path to data/site-data.json")
    parser.add_argument("--output", required=True, help="Output candidates JSONL path")
    args = parser.parse_args(argv)

    with open(args.site_data, encoding="utf-8") as handle:
        site_data = json.load(handle)
    candidates = extract_candidates(site_data)

    with open(args.output, "w", encoding="utf-8") as handle:
        for candidate in candidates:
            handle.write(json.dumps(candidate, ensure_ascii=False) + "\n")
    print(f"{len(candidates)} candidates extracted to {args.output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
