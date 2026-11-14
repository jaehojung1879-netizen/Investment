"""Offline accounting and private input checksum verification; no study run."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

from research.us_historical_market_recovery_v1.audit import read, canonical
from research.us_historical_market_recovery_v1.public_prices import PACKETS

REQUIRED = ("sealed-inputs-manifest.json", "baseline-bars.json.gz", "baseline-events.json.gz",
            "baseline-lineage.json.gz", "baseline-component-receipts.json", "original-input-eligible-cohorts.json",
            "repaired-input-eligible-cohorts.json", "baseline_reacquisition.json", "new_charts.json",
            "authenticated-responses.json.gz", "supplement-responses.json.gz", "holding-returns.json.gz", "new-source-series.json.gz",
            "mature-gap-tickers.json", "label_followup_charts.json")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--write-manifest", action="store_true")
    args = parser.parse_args(argv)
    private = args.private_root
    result = read(args.output / "results.json")
    assert result["collection_denominator"] == len(result["inventory"]) == 212
    assert len({r["security_audit_id"] for r in result["inventory"]}) == 212
    assert result["baseline_bytes_match"]
    source_rows = read(private / "baseline_reacquisition.json") + read(private / "new_charts.json") + read(private / "label_followup_charts.json") + read(private / "last-gap-public-charts.json")
    for r in source_rows:
        if r.get("object"):
            assert hashlib.sha256((private / r["object"]).read_bytes()).hexdigest() == r["sha256"]
    complete = "COMPLETE_ORIGINAL_RESEARCH_CONTRACT"
    labels = read(private / "holding-returns.json.gz")
    for horizon, summary in result["horizons"].items():
        for phase in ("before", "after"):
            rows = [r for r in labels if r["horizon"] == int(horizon) and r["phase"] == phase]
            assert len(rows) == summary["fixed_union_denominator"] == sum(summary[phase].values())
            assert Counter(r["status"] for r in rows) == summary[phase]
            assert len({(r["signal"], r["ticker"]) for r in rows}) == len(rows)
            for r in rows:
                if r["status"] == complete:
                    assert all(math.isfinite(r[k]) for k in ("gross_usd_total_return", "spy_gross_usd_total_return", "difference_vs_spy"))
                    assert abs(r["gross_usd_total_return"] - r["spy_gross_usd_total_return"] - r["difference_vs_spy"]) < 1e-12
                else:
                    assert r["gross_usd_total_return"] is None
    paths = [private / name for name in REQUIRED]
    paths += [private / name for name in ("last-gap-public-charts.json", "last-gap-account-attempts.json") if (private / name).exists()]
    paths += [private / name for name in PACKETS if (private / name).exists()]
    paths += sorted((private / "objects").iterdir()) + sorted((private / "identity-sources").iterdir())
    files = {str(p.relative_to(private)): {"sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size}
             for p in paths if p.is_file()}
    manifest = {"schema": "PRIVATE_MARKET_INPUT_BUNDLE_V1", "license": "PRIVATE_EXISTING_ACCESS_ONLY_NO_REDISTRIBUTION_GRANTED",
                "files": files, "public_results_sha256": hashlib.sha256((args.output / "results.json").read_bytes()).hexdigest()}
    target = private / "bundle-manifest.json"
    if args.write_manifest:
        target.write_bytes(canonical(manifest))
    else:
        assert read(target) == manifest, "PRIVATE_INPUT_OR_PUBLIC_REPORT_BYTES_CHANGED"
    print(json.dumps({"verified_private_files": len(files), "holding_phase_records": len(labels), "collection_identifiers": 212}))


if __name__ == "__main__":
    main()
