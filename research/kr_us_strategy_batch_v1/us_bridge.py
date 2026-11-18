"""Explain original-published -> new capture -> CTVA source-repaired baseline.

The archived invalid-input run is a source diagnostic, never a new contender.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import pickle
import shutil

import numpy as np
import pandas as pd

from research.kr_us_strategy_batch_v1 import us
from research.us_selection_value_v1 import evaluate as E
from research.us_selection_value_v1 import features as F


def ensure_archived_features(private):
    archive = private / "pre-ctva-split-fix"
    if (archive / "features.pkl").exists():
        return
    if not (archive / "CTVA.json.gz").exists():
        raise FileNotFoundError(str(archive / "CTVA.json.gz"))
    for name in ("close.pkl", "filings.pkl"):
        path = archive / name
        if not path.exists():
            path.symlink_to((private / name).resolve())
    destination = archive / "yahoo"
    destination.mkdir(exist_ok=True)
    for original in (private / "yahoo").glob("*.json.gz"):
        path = destination / original.name
        if not path.exists():
            if original.name == "CTVA.json.gz":
                shutil.copyfile(archive / original.name, path)
            else:
                path.symlink_to(original.resolve())
    F.main(["--private", str(archive)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=us.HERE / "results/us-source-bridge.json")
    a = ap.parse_args()
    ensure_archived_features(a.private)
    before = pd.read_pickle(a.private / "pre-ctva-split-fix/features.pkl")
    after = pd.read_pickle(a.private / "features.pkl")
    assert before.index.equals(after.index) and before.columns.equals(after.columns)
    changes, tickers = {}, set()
    for col in before:
        if not pd.api.types.is_numeric_dtype(before[col]):
            continue
        different = ~(before[col].eq(after[col]) | (before[col].isna() & after[col].isna()))
        if different.any():
            ts = sorted(before.loc[different, "ticker"].unique())
            tickers.update(ts)
            changes[col] = {"rows": int(different.sum()), "tickers": ts,
                            "maximumAbsoluteDifference": float((before.loc[different, col] - after.loc[different, col]).abs().max())}
    assert tickers <= {"CTVA"}, tickers
    with (a.private / "close.pkl").open("rb") as f:
        close = pickle.load(f)["close"]
    summary = json.loads((us.HERE / "results/US/summary.json").read_text())
    dates = pd.to_datetime(pd.read_csv(us.HERE / "results/US/cohort-dates-126.csv.gz", index_col=0).index)
    by = {pd.Timestamp(d): g for d, g in before.groupby("date")}
    rows = []
    changed = {s: 0 for s in ("COCKTAIL", "U1")}
    public = pd.read_csv(us.HERE / "results/US/books.csv.gz", parse_dates=["date"])
    now = {(d, c): dict(zip(g.ticker, g.weight, strict=True)) for (d, c), g in public.groupby(["date", "config"])}
    for d in dates:
        common = E.common(by[d])
        x = E.score(common)
        for selector in ("COCKTAIL", "U1"):
            w = us.native_book(x, selector, d)
            current = now[(d, "US:NATIVE_" + selector)]
            if any(abs(w.get(t, 0) - current.get(t, 0)) > 1e-12 for t in set(w) | set(current)):
                changed[selector] += 1
            pos = close.index.get_loc(d) + 1
            for h in (126, 252):
                if pos + h >= len(close):
                    continue
                e, z = close.index[pos], close.index[pos + h]
                ret = E.net(close.loc[z] / close.loc[e] - 1)
                if not np.isfinite(ret[list(w)]).all():
                    continue
                rows.append({"date": d, "horizon": h, "selector": selector,
                             "netExcessWithArchivedUncorrectedSource": sum(weight * ret[t] for t, weight in w.items()) - ret["SPY"]})
    f = pd.DataFrame(rows)
    f.to_csv(a.out.with_name("us-source-bridge-cohorts.csv.gz"), index=False,
             compression={"method": "gzip", "mtime": 0})
    bridge = {}
    for (h, selector), g in f.groupby(["horizon", "selector"]):
        original = summary["nativeBaselineDiff"][str(h)]["US:NATIVE_" + selector]
        uncorrected = float(g.netExcessWithArchivedUncorrectedSource.mean())
        bridge[f"{h}|{selector}"] = {"n": len(g), "published": original["originalMean"],
                                      "archivedUncorrectedCapture": uncorrected,
                                      "repairedCapture": original["currentMean"],
                                      "captureMinusPublished": uncorrected - original["originalMean"],
                                      "ctvaRepairEffect": original["currentMean"] - uncorrected}
    us.save(a.out, {"label": "SOURCE_REPRODUCTION_DIAGNOSTIC_INVALID_INPUT_NOT_A_STRATEGY_CANDIDATE",
                    "changedNumericFeatures": changes, "changedTickers": sorted(tickers),
                    "nativeBookChangedWeeks": changed, "bridge": bridge})
    print(json.dumps(bridge, indent=1))


if __name__ == "__main__":
    main()
