"""Phase 0 lineage audit: did #354's US inputs carry #353's verified share-count corrections?

    python -m research.investment_decision_alpha_v1.lineage_353_354 --private $S --work $S/corr

1. Hash the feature file #354 actually read, and join #353's 943 corrected rows
   (`kr_us_public_buys_v1/results/WAT/corrected-caps.csv`) to it.
2. Write a corrected copy OUTSIDE git (only `marketCap` replaced on those rows;
   value yields and size terciles are recomputed downstream by the unchanged loader).
3. Re-run #354's unchanged US analysis on that copy into `results/354-us-corrected/`.
   #354's committed results are never touched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
FIX = ROOT / "research/kr_us_public_buys_v1/results/WAT/corrected-caps.csv"


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def audit(private: Path, work: Path) -> dict:
    src = private / "us" / "features.pkl"
    f = pd.read_pickle(src)
    f["date"] = pd.to_datetime(f["date"])
    fix = pd.read_csv(FIX, parse_dates=["date"])
    m = fix.merge(f[["date", "ticker", "marketCap"]], on=["date", "ticker"], how="left", validate="one_to_one")
    found = int(m["marketCap"].notna().sum())
    uncorrected = int(np.isclose(m["marketCap"], m["previousMarketCap"], rtol=1e-9).sum())
    already = int(np.isclose(m["marketCap"], m["correctedMarketCap"], rtol=1e-9).sum())
    key = f.set_index(["date", "ticker"]).index
    pos = key.get_indexer(pd.MultiIndex.from_frame(fix[["date", "ticker"]]))
    assert (pos >= 0).all()
    g = f.copy()
    g.iloc[pos, g.columns.get_loc("marketCap")] = fix["correctedMarketCap"].to_numpy()
    (work / "us").mkdir(parents=True, exist_ok=True)
    out = work / "us" / "features.pkl"
    g.to_pickle(out)
    ratio = (m["correctedMarketCap"] / m["previousMarketCap"]).describe().to_dict()
    return {"featuresReadBy354": str(src.name), "featuresSha256": sha(src), "correctionFile": str(FIX.relative_to(ROOT)),
            "correctionFileSha256": sha(FIX), "correctionRows": len(fix), "rowsFoundIn354Input": found,
            "rowsStillUncorrectedIn354Input": uncorrected, "rowsAlreadyCorrected": already,
            "tickers": fix.groupby("ticker").size().to_dict(), "correctedOverOriginalRatio": ratio,
            "correctedCopySha256": sha(out), "correctedCopyLocation": "outside git (private scratch)"}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--skip-rerun", action="store_true")
    a = ap.parse_args(argv)
    P, W = Path(a.private), Path(a.work)
    for name in ("close.pkl", "filings.pkl"):
        dst = W / "us" / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            dst.symlink_to(P / "us" / name)
    (W / "ee").mkdir(parents=True, exist_ok=True)
    shutil.copy(P / "ee" / "us-8k-202.json", W / "ee" / "us-8k-202.json")
    res = audit(P, W)
    R = HERE / "results"
    R.mkdir(exist_ok=True)
    (R / "lineage-353-354.json").write_text(json.dumps(res, indent=1, sort_keys=True, default=str) + "\n")
    print(json.dumps({k: v for k, v in res.items() if k != "tickers"}, default=str))
    if not a.skip_rerun:
        from research.kr_us_earnings_expectations_v1 import analysis
        out = R / "354-us-corrected"
        out.mkdir(exist_ok=True)
        analysis.main(["--market", "us", "--private", str(W), "--out", str(out)])


if __name__ == "__main__":
    main()
