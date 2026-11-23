"""Experiment 1 inputs: FRED VIXCLS (CBOE VIX close, 1990-) and VXVCLS (CBOE VIX3M close, 2007-12-04-), preserved
raw with retrieval time and SHA-256, plus a consistency check against the copy of VIXCLS that #198 preserved in the
repository. Both are exchange-published closing index levels; FRED serves them as recorded, so the current file is
treated as the value known at each close (documented assumption; it is checked, not assumed, on the #198 overlap).

    python -m research.market_risk_discovery_v1.exp1_inputs
"""
from __future__ import annotations

import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import sys
from pathlib import Path

from research.market_valuation_macro_overlay_v1 import source_probe as SP

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RAW = HERE / "data" / "raw"
SERIES = {"VIXCLS": "CBOE Volatility Index (VIX), daily close", "VXVCLS": "CBOE S&P 500 3-Month Volatility Index (VIX3M), daily close"}
REPO_198 = REPO / "data/kr-market-risk-anatomy-v1/sources/FRED_VIXCLS/normalized.csv"


def gz(raw: bytes) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as h:
        h.write(raw)
    return buf.getvalue()


def load(series: str) -> dict[str, float]:
    raw = gzip.decompress((RAW / f"fred-{series}.csv.gz").read_bytes()).decode()
    out = {}
    for row in csv.DictReader(io.StringIO(raw)):
        v = row[series].strip()
        if v and v != ".":
            out[row["observation_date"]] = float(v)
    return out


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    manifest = {"retrievedAtUtc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(), "series": {}}
    for s, desc in SERIES.items():
        r = SP.http(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={s}")
        if r.get("status") != 200:
            raise RuntimeError(f"{s}: HTTP {r.get('status')}")
        (RAW / f"fred-{s}.csv.gz").write_bytes(gz(r["raw"]))
        vals = load(s)
        manifest["series"][s] = {"description": desc, "url": f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={s}",
                                 "sha256Raw": hashlib.sha256(r["raw"]).hexdigest(), "observations": len(vals),
                                 "first": min(vals), "last": max(vals), "stored": f"data/raw/fred-{s}.csv.gz"}
    ours = load("VIXCLS")
    theirs = {}
    with REPO_198.open() as h:
        for row in csv.DictReader(h):
            keys = list(row)
            d, v = row[keys[0]], row[keys[1]]
            try:
                theirs[d[:10]] = float(v)
            except ValueError:
                pass
    common = sorted(set(ours) & set(theirs))
    diffs = [d for d in common if abs(ours[d] - theirs[d]) > 1e-9]
    manifest["vixRevisionCheckAgainst198"] = {"file": str(REPO_198.relative_to(REPO)), "overlapDays": len(common),
                                              "first": common[0] if common else None, "last": common[-1] if common else None,
                                              "differingDays": len(diffs), "examples": diffs[:5]}
    (HERE / "data" / "exp1-inputs-manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    print(json.dumps(manifest, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
