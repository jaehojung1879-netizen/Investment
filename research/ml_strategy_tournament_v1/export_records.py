"""Export compact reproducibility records into results/ (no model is refit, no metric recomputed).

    python research/ml_strategy_tournament_v1/export_records.py --scratch <dir>

  fold-records.json             every strategy x fold: training rows/dates, last training-label exit, first test signal, features, in/out-of-sample IC, fit seconds
  holdings-all.json.gz          every strategy, both views: post-trade weights at each of the 140 executions (ETF = residual)
  predictions-rebalance-pctile.npz   every strategy's within-date score percentile (x1000, int16; -1 = unscored) on the 140 rebalance signal dates
  trades-<view>-<subject>.csv / round-trips-<view>-<subject>.csv   for each dissected strategy
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import pickle
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import evaluate as E  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", required=True)
    a = ap.parse_args(argv)
    s = Path(a.scratch)
    res = HERE / "results"
    blob, df, preds, folds = E.load(s)
    (res / "fold-records.json").write_text(json.dumps(folds, indent=0, sort_keys=True) + "\n")
    hold = {}
    for view in ("gated", "forced"):
        ev = pickle.loads((s / f"eval-{view}.pkl").read_bytes())
        hold[view] = {sid: p["holdings"] for sid, p in ev["paths"].items()}
    (res / "holdings-all.json.gz").write_bytes(gzip.compress(json.dumps(hold, sort_keys=True).encode(), mtime=0))
    rdates = E.rebalance_dates(df)
    sub = df[df["date"].isin(rdates)]
    out = {"dates": sub["date"].dt.strftime("%Y-%m-%d").to_numpy().astype("U10"), "tickers": sub["ticker"].to_numpy().astype("U12")}
    for sid, sc in sorted(preds.items()):
        x = sub.assign(_s=sc[sub.index]).groupby("date")["_s"].rank(pct=True)
        out[sid] = np.where(x.notna(), np.round(x.fillna(0) * 1000), -1).astype(np.int16)
    np.savez_compressed(res / "predictions-rebalance-pctile.npz", **out)
    for p in sorted(res.glob("winner-analysis-*.json")):
        w = json.loads(p.read_text())
        tag = p.stem.replace("winner-analysis-", "")
        tag = tag if "-" in tag else f"{tag}-{w['subject']}"
        for key, name in (("trades", "trades"), ("roundTrips", "round-trips")):
            rows = w["anatomy"][key]
            if not rows:
                continue
            cols = sorted({k for r in rows for k in r})
            with open(res / f"{name}-{tag}.csv", "w", newline="") as fh:
                wr = csv.DictWriter(fh, fieldnames=cols)
                wr.writeheader()
                wr.writerows(rows)
    print(sorted(x.name for x in res.iterdir()))


if __name__ == "__main__":
    main()
