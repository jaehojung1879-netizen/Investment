"""Reproduce compact PUBLIC SPY inputs from SHA-pinned original SEC reports.

No strategy outcome is calculated. Existing raw cache is preferred; --fetch only
retrieves the 28 original N-PORT reports, never the missing 7.4 GB N-PORT archive.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import urllib.request

import pandas as pd

from research.us_rank_independent_check_v1.crosscheck import norm
from research.us_rank_independent_check_v1.snapshot import parse_nport, UA
from research.us_selection_value_v1 import evaluate as EV

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SOURCE = ROOT / "docs/us-readiness/us-etf-sec-holdings-cross-check-v1.json"
MAPPING = ROOT / "research/us_rank_independent_check_v1/inputs/openfigi-cusip-map.json"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", type=Path, required=True)
    ap.add_argument("--inputs", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=HERE / "inputs/US")
    ap.add_argument("--fetch", action="store_true")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    cache = a.inputs / "sec-spy"
    cache.mkdir(parents=True, exist_ok=True)
    existing_receipts = {}
    if (cache / "source-manifest.json").exists():
        existing_receipts = {r["accession"]: r for r in json.loads((cache / "source-manifest.json").read_text())["receipts"]}
    source = [r for r in json.loads(SOURCE.read_text())["results"] if r["ticker"] == "SPY" and r["form"] == "NPORT-P"]
    assert len(source) == 28
    figi = json.loads(MAPPING.read_text())
    close, _, _, _ = EV.load(a.private)
    bynorm = {norm(t): t for t in close}
    assert len(bynorm) == len(close.columns)
    rows, reports, receipts = [], [], []
    for r in sorted(source, key=lambda r: (r["as_of"], r["accession"])):
        path = cache / (r["accession"] + ".xml.gz")
        receipt = existing_receipts.get(r["accession"], {})
        if path.exists():
            raw = gzip.decompress(path.read_bytes())
        else:
            if not a.fetch:
                raise FileNotFoundError(f"Missing exact SEC raw {path}; pass --fetch to retrieve the pinned URL")
            request = urllib.request.Request(r["url"], headers={"User-Agent": UA})
            observed = datetime.now(timezone.utc).isoformat()
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read()
                status = response.status
            if status != 200:
                raise ValueError("SEC_HTTP_STATUS_NOT_200")
            receipt = {"httpStatus": status, "capturedAtUTC": observed, "capture": "FETCHED"}
            path.write_bytes(gzip.compress(raw, mtime=0))
        actual = hashlib.sha256(raw).hexdigest()
        if actual != r["source_sha256"]:
            raise ValueError("SEC_PINNED_SOURCE_SHA256_MISMATCH: " + r["accession"])
        # Existing exact raw has an original successful capture receipt; fail if absent.
        assert receipt.get("httpStatus") == 200
        meta, holdings = parse_nport(raw)
        assert meta["repPdDate"] == r["as_of"]
        net, assets = float(meta["netAssets"]), float(meta["totAssets"])
        equity = sum(x["valueUsd"] for x in holdings if x["assetCat"] == "EC")
        category = {}
        for i, h in enumerate(holdings):
            original = figi.get(h["cusip"])
            candidate = bynorm.get(norm(original), original)
            weight = h["valueUsd"] / net
            rows.append({"accession": r["accession"], "holdingAsOf": r["as_of"], "publicFrom": r["filed"], "line": i,
                         **{k: h[k] for k in ("name", "title", "lei", "cusip", "isin", "assetCat", "valueUsd")},
                         "netAssetsWeight": weight, "reportedPctNav": h["pctNav"],
                         "equityNormalizedWeight": h["valueUsd"] / equity if h["assetCat"] == "EC" else None,
                         "candidateTickerFromExistingMapRaw": original, "candidateTickerFromExistingMap": candidate,
                         "tickerPunctuationNormalized": original != candidate,
                         "tickerMappingBasis": "EXISTING_CURRENT_OPENFIGI_CUSIP_MAP_NOT_NEW_PIT_IDENTITY_PROOF" if candidate else "UNMAPPED"})
            category[h["assetCat"]] = category.get(h["assetCat"], 0) + weight
        reports.append({"accession": r["accession"], "holdingAsOf": r["as_of"], "publicFrom": r["filed"],
                        "sourceSha256": actual, "netAssetsUsd": net, "totalAssetsUsd": assets, "equityValueUsd": equity,
                        "equityLines": sum(h["assetCat"] == "EC" for h in holdings), "allLines": len(holdings),
                        "assetCategoryNetWeights": category, "equityNetWeight": equity / net,
                        "nonEquityReportedNetWeight": sum(w for c, w in category.items() if c != "EC"),
                        "netAssetsLessReportedLinesFraction": 1 - sum(category.values())})
        receipts.append({k: v for k, v in {**r, **receipt, "actualSha256": actual, "bytes": len(raw), "status": "VERIFIED",
                         "rawCacheBasename": path.name}.items() if k != "rawPath"})
    normalized = a.out / "spy-normalized-holdings.csv.gz"
    pd.DataFrame(rows).to_csv(normalized, index=False, compression={"method": "gzip", "mtime": 0})
    (a.out / "spy-reports.json").write_text(json.dumps(reports, indent=1, allow_nan=False) + "\n")
    manifest = {"purpose": "PUBLIC_NORMALIZED_INPUT_NOT_STRATEGY_RESULTS", "reports": len(reports),
                "sourceRecord": str(SOURCE.relative_to(ROOT)), "sourceRecordSha256": sha(SOURCE),
                "existingCurrentCusipMap": str(MAPPING.relative_to(ROOT)), "existingCurrentCusipMapSha256": sha(MAPPING),
                "normalizedSha256": sha(normalized), "parser": "Original snapshot.parse_nport",
                "parserModuleSha256": sha(ROOT / "research/us_rank_independent_check_v1/snapshot.py"), "receipts": receipts,
                "mappingLimitation": "Current composite CUSIP map is not a dated identity source; only unique punctuation is normalized. Unknown lines are retained.",
                "scriptSha256": sha(Path(__file__))}
    (a.out / "spy-source-manifest.json").write_text(json.dumps(manifest, indent=1, allow_nan=False) + "\n")
    # Source-only coverage was computed before outcomes, and is kept verbatim.
    for source_name, output_name in (("coverage-summary.json", "spy-coverage-summary.json"),
                                     ("coverage-by-decision.csv", "spy-source-coverage-by-decision.csv"),
                                     ("latest-known-report-by-decision.csv", "spy-publication-by-decision.csv")):
        path = cache / source_name
        if path.exists():
            (a.out / output_name).write_bytes(path.read_bytes())
    print(json.dumps({"reports": len(reports), "normalizedRows": len(rows), "normalizedSha256": sha(normalized)}))


if __name__ == "__main__":
    main()
