"""Reproduce the ec9a221-authorized one-cell FISV repair into a new copy."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import pickle

import numpy as np
import pandas as pd

from pipeline.price_adjustment import DIVIDEND, SPLIT, to_total_return
from pipeline.us_dual_benchmark_data import SOURCE_COMMIT, SealedReader
from research.us_selection_value_v1.features import ny_date

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL_CLOSE_SHA = "17b4dbcc534caa31302a8e7d29fcdc9b036a77f9072f2898063ccbd4e74b6c7e"
RAW_SHA = "b525ca5ecee2c73f59c504cc6424e3ac23ac8e40b1dcc0442e3ea43a4d76bb91"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", type=Path, required=True)
    ap.add_argument("--inputs", type=Path, required=True)
    a = ap.parse_args(argv)
    a.inputs.mkdir(parents=True, exist_ok=True)
    assert sha(a.private / "close.pkl") == ORIGINAL_CLOSE_SHA
    features_sha = sha(a.private / "features.pkl")
    with (a.private / "close.pkl").open("rb") as f:
        original = pickle.load(f)
    price = original["close"]
    raw = gzip.decompress((a.private / "yahoo-raw/FISV.response.json.gz").read_bytes())
    capture = json.loads((a.private / "yahoo-raw/FISV.receipt.json").read_text())
    assert hashlib.sha256(raw).hexdigest() == RAW_SHA == capture["responseSha256"]
    x = json.loads(raw)["chart"]["result"][0]
    frame = pd.DataFrame({"Close": x["indicators"]["quote"][0]["close"]},
                         index=pd.to_datetime([ny_date(t) for t in x["timestamp"]]))
    reader = SealedReader(ROOT)
    manifest = reader.manifest()
    events, refs = [], []
    for name, items in manifest["components"].items():
        if not name.startswith("corporate-events/20"):
            continue
        for ref in items:
            for row in reader.component(ref):
                if row["ticker"] == "FISV":
                    events.append(row)
                    refs.append(ref)
    assert events and all((r.get("dividend") or 0) == 0 for r in events)
    e = pd.DataFrame({DIVIDEND: [0. for _ in events], SPLIT: [r.get("split") or 1. for r in events]},
                     index=pd.to_datetime([r["date"] for r in events]))
    rebuilt, _ = to_total_return(frame, e)
    comparison = pd.DataFrame({"originalTR": price.FISV, "cachedYahooClose": frame.Close, "reconstructedTR": rebuilt.Close})
    known = comparison.originalTR.notna() & comparison.reconstructedTR.notna()
    comparison["relativeError"] = np.where(known, (comparison.originalTR / comparison.reconstructedTR - 1).abs(), np.nan)
    when = pd.Timestamp("2025-11-12")
    assert list(price.FISV.index[price.FISV.isna()]) == [when]
    value = float(rebuilt.at[when, "Close"])
    assert value == 257.5199890136719 and comparison.relativeError.max() <= 1e-8
    repaired = dict(original)
    repaired["close"] = price.copy(deep=True)
    repaired["close"].at[when, "FISV"] = value
    same = repaired["close"].eq(price) | (repaired["close"].isna() & price.isna())
    assert int((~same).sum().sum()) == 1
    repaired["inputRepair"] = {"authorizationCommit": "ec9a221", "sourceRepairReceipt": str(a.inputs / "fisv-repair-applied.json"),
                               "ticker": "FISV", "date": str(when.date()), "newValue": value, "originalInputIdentityPreserved": True}
    dest = a.inputs / "close-repaired.pkl"
    with dest.open("wb") as f:
        pickle.dump(repaired, f)
    receipt = {"status": "APPLIED_TO_NEW_COPY_ONLY", "ticker": "FISV", "date": str(when.date()), "originalValue": None,
               "proposedForwardTotalReturnClose": value, "cachedYahooClose": float(frame.at[when, "Close"]),
               "sourceCommit": SOURCE_COMMIT, "replayManifestSha256": manifest["sha256"], "sourceYahooResponseSha256": RAW_SHA,
               "sourceYahooReceipt": str(a.private / "yahoo-raw/FISV.receipt.json"), "sealedFISVEvents": events,
               "sealedCorporateEventObjectRefs": sorted(set(refs)), "originalFunction": "pipeline.price_adjustment.to_total_return",
               "originalFunctionModuleSha256": sha(ROOT / "pipeline/price_adjustment.py"),
               "overlapNonNullOriginalClosesCompared": int(known.sum()),
               "maximumAbsoluteRelativeErrorAcrossComparedExistingCloses": float(comparison.relativeError.max()),
               "originalNonNullClosesOutsideCachedYahooRange": int((comparison.originalTR.notna() & comparison.reconstructedTR.isna()).sum()),
               "outsideRangeOriginalClosesUntouched": True, "allOtherCellsIncludingOtherTickersUnchanged": True,
               "changedCellCountInProposedCopy": 1, "originalClosePklSha256": ORIGINAL_CLOSE_SHA,
               "originalClosePklModified": False, "featuresModified": False, "noPerformanceComputed": True,
               "authorizationCommit": "ec9a221", "repairedClosePklPath": str(dest), "repairedClosePklSha256": sha(dest),
               "originalClosePklSha256After": sha(a.private / "close.pkl"), "featuresSha256BeforeAndAfter": sha(a.private / "features.pkl")}
    assert receipt["originalClosePklSha256After"] == ORIGINAL_CLOSE_SHA
    assert receipt["featuresSha256BeforeAndAfter"] == features_sha
    comparison.to_csv(a.inputs / "fisv-reconstruction-comparison.csv.gz", compression={"method": "gzip", "mtime": 0})
    (a.inputs / "fisv-repair-applied.json").write_text(json.dumps(receipt, indent=1, allow_nan=False) + "\n")
    print(json.dumps({"changedCells": 1, "maximumOverlapRelativeError": receipt["maximumAbsoluteRelativeErrorAcrossComparedExistingCloses"],
                      "repairedClosePklSha256": receipt["repairedClosePklSha256"]}))


if __name__ == "__main__":
    main()
