"""Preserve every executed US book's date/name contribution from frozen prices."""
from __future__ import annotations

import argparse
from pathlib import Path
import pickle

import numpy as np
import pandas as pd

from research.kr_us_strategy_batch_v1 import us


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", type=Path, required=True)
    a = ap.parse_args()
    out = us.HERE / "results/US"
    with (a.private / "close.pkl").open("rb") as f:
        close = pickle.load(f)["close"]
    b = pd.read_csv(out / "books.csv.gz", parse_dates=["date"], low_memory=False)
    by_date = {d: g for d, g in b.groupby("date")}
    check = {}
    for h in (126, 252):
        dates = pd.read_csv(out / f"cohort-dates-{h}.csv.gz", index_col=0, parse_dates=[0, 1, 2])
        fixed = pd.read_csv(out / f"cohorts-net-{h}.csv.gz", index_col=0, parse_dates=True)
        chunks = []
        for d, g in by_date.items():
            e, x = dates.loc[d, ["entry", "exit"]]
            if pd.isna(e) or pd.isna(x):
                continue
            gross = close.loc[x] / close.loc[e] - 1
            net = us.EV.net(gross)
            g = g.loc[g.config.map(fixed.loc[d]).notna()].copy()
            g["horizon"] = h
            g["entryYear"] = e.year
            g["assetNetReturn"] = g.ticker.map(net)
            g["netContribution"] = g.weight * (g.assetNetReturn - net["SPY"])
            g["grossContribution"] = g.weight * (g.ticker.map(gross) - gross["SPY"])
            g["namedMega"] = g.ticker.isin(us.MEGA)
            chunks.append(g)
        result = pd.concat(chunks, ignore_index=True)
        assert np.isfinite(result.netContribution).all()
        observed = result.groupby(["date", "config"]).netContribution.sum().unstack("config")
        expected = fixed.subtract(fixed[us.ETF], axis=0).reindex(columns=observed.columns, index=observed.index)
        error = float((observed - expected).abs().max().max())
        assert error < 1e-10
        us.csv(out, f"pername-cohort-{h}", result)
        check[str(h)] = {"rows": len(result), "maxSumError": error, "books": observed.shape[1]}
    us.save(out / "pername-export-verification.json", check)
    print(check)


if __name__ == "__main__":
    main()
