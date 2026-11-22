"""US input lineage v3: the #343-#355 feature file + #353's 943 verified share counts + the CTVA split-basis repair.

    python -m research.investment_decision_alpha_v1.lineage_v3 --private $S --work $S/v3 [--rerun-354]

Why: two US feature lineages exist. Claude's (#343-#355, sha 49062dba...) was built from the 2026-11-15 Yahoo capture;
Codex's (#350-#353) re-captured on 2026-11-17 and then repaired CTVA (`kr_us_strategy_batch_v1/INPUT-REPAIR-ko.md`,
receipt `results/us-ctva-repair-receipt.json`). The capture's history ends 2026-09-09, so CTVA's 2026-10-01 6665:1000
split was missing and every historical as-traded close was 1/6.665 of the true level. Codex's whole-panel raw-inverse
comparison (627 tickers) found no other price-level outlier. Claude's file carries the same CTVA defect (verified here
before patching). v3 applies, outside git and without touching the original:
  1. the 943 #353 corrections (marketCap only), and
  2. CTVA: asTradedClose and marketCap x 6665/1000 on every row dated before the split (all decision dates).
The one admission difference Codex reported (one ticker OVERLAP_TOO_SHORT -> NOT_SERVED) is not reproduced: its ticker
is not named in any committed file.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from research.investment_decision_alpha_v1.lineage_353_354 import FIX, ROOT, sha

HERE = Path(__file__).resolve().parent
CTVA_RECEIPT = ROOT / "research/kr_us_strategy_batch_v1/results/us-ctva-repair-receipt.json"


def build(private: Path, work: Path) -> dict:
    src = private / "us" / "features.pkl"
    f = pd.read_pickle(src)
    f["date"] = pd.to_datetime(f["date"])
    g = f.copy()
    fix = pd.read_csv(FIX, parse_dates=["date"])
    key = g.set_index(["date", "ticker"]).index
    pos = key.get_indexer(pd.MultiIndex.from_frame(fix[["date", "ticker"]]))
    assert (pos >= 0).all()
    assert np.allclose(g["marketCap"].to_numpy()[pos], fix["previousMarketCap"].to_numpy(), rtol=1e-9), "353_BASE_MISMATCH"
    g.iloc[pos, g.columns.get_loc("marketCap")] = fix["correctedMarketCap"].to_numpy()
    rec = json.loads(CTVA_RECEIPT.read_text())
    ev = rec["event"]
    ratio = ev["numerator"] / ev["denominator"]
    split_day = pd.Timestamp(ev["date"], unit="s").normalize()
    m = g["ticker"].eq("CTVA") & (g["date"] < split_day)
    before = g.loc[m, ["asTradedClose", "marketCap"]].astype(float)
    # the defect check: CTVA's as-traded close must be ~1/ratio of its sealed (true-level) close on the same dates
    g.loc[m, "asTradedClose"] = before["asTradedClose"] * ratio
    g.loc[m, "marketCap"] = before["marketCap"] * ratio
    (work / "us").mkdir(parents=True, exist_ok=True)
    out = work / "us" / "features.pkl"
    g.to_pickle(out)
    for name in ("close.pkl", "filings.pkl"):
        dst = work / "us" / name
        if not dst.exists():
            dst.symlink_to(private / "us" / name)
    (work / "ee").mkdir(exist_ok=True)
    shutil.copy(private / "ee" / "us-8k-202.json", work / "ee" / "us-8k-202.json")
    changed = int((g["marketCap"].fillna(-1) != f["marketCap"].fillna(-1)).sum())
    return {"source": src.name, "sourceSha256": sha(src), "v3Sha256": sha(out), "v3Location": "outside git (private scratch)",
            "corrections353": int(len(fix)), "correction353Sha256": sha(FIX),
            "ctva": {"receipt": str(CTVA_RECEIPT.relative_to(ROOT)), "receiptSha256": sha(CTVA_RECEIPT), "ratio": ratio,
                     "splitDate": str(split_day.date()), "rowsRepaired": int(m.sum()),
                     "marketCapBeforeMedian": float(before["marketCap"].median()),
                     "marketCapAfterMedian": float(g.loc[m, "marketCap"].median())},
            "marketCapCellsChanged": changed,
            "notReproduced": "Codex's one-ticker admission change (OVERLAP_TOO_SHORT 13->12, NOT_SERVED 7->8); ticker not in committed files"}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--rerun-354", action="store_true")
    a = ap.parse_args(argv)
    P, W = Path(a.private), Path(a.work)
    res = build(P, W)
    (HERE / "results" / "lineage-v3.json").write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
    print(json.dumps(res))
    if a.rerun_354:
        from research.kr_us_earnings_expectations_v1 import analysis
        out = HERE / "results" / "354-us-v3"
        out.mkdir(exist_ok=True)
        analysis.main(["--market", "us", "--private", str(W), "--out", str(out)])


if __name__ == "__main__":
    main()
