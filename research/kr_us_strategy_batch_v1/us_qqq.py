"""Secondary QQQ comparison, kept outside the preregistered SPY claim families."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from research.kr_us_strategy_batch_v1 import common as C
from research.kr_us_strategy_batch_v1 import us


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", type=Path, required=True)
    a = ap.parse_args()
    out = us.HERE / "results/US"
    s = json.loads((out / "summary.json").read_text())
    result = {"role": "SECONDARY_NOT_IN_PRIMARY_SPY_CLAIM_FAMILIES", "fixed": {}, "ledgers": {}}
    for h in (126, 252):
        f = pd.read_csv(out / f"cohorts-net-{h}.csv.gz", index_col=0, parse_dates=True)
        grid = [k for k, v in us.REG["grid"].items() if v["market"] == "US" and k in f]
        mask = f[grid].notna().all(axis=1) & f["US:QQQ"].notna()
        result["fixed"][str(h)] = {}
        for config in f:
            if config == "US:QQQ":
                continue
            cmask = mask.copy()
            if config in us.POLICIES:
                cmask &= f.index >= pd.Timestamp(s["postWarmupStart"])
            result["fixed"][str(h)][config] = C.stats(f[config] - f["US:QQQ"], h, cmask)
    _, _, qqq, meta = us.EV.load(a.private)
    first = pd.Timestamp(s["signalDates"][0])
    prices = qqq.loc[first:].to_frame("QQQ")
    benchmark = us.UP.simulate(prices, {prices.index[1]: {"QQQ": 1.0}})["nav"]
    result["benchmarkAdjustments"] = meta
    for interval, by in s.get("ledgers", {}).items():
        result["ledgers"][interval] = {}
        for config, cell in by.items():
            path = out / (f"NAV-{interval}-" + config.replace(":", "_") + ".csv.gz")
            if not path.exists() or "full" not in cell:
                result["ledgers"][interval][config] = {"status": "NOT_ESTIMABLE"}
                continue
            nav = pd.read_csv(path, index_col=0, parse_dates=True).nav
            result["ledgers"][interval][config] = C.nav_window(nav, benchmark)
    us.save(out / "qqq-secondary.json", result)
    print("QQQ secondary comparisons", len(result["fixed"]["126"]), {k: len(v) for k, v in result["ledgers"].items()})


if __name__ == "__main__":
    main()
