"""Step 3: walk-forward fit every configuration of the frozen grid and store its out-of-sample scores.

    python research/ml_strategy_tournament_v1/run_tournament.py --scratch <dir> [--h252] [--workers 4]

Each configuration is refit once per outer year on labels that exited strictly before that year's first signal date, then scores every
signal date of that year. Scores, per-fold in-sample and out-of-sample rank IC and fit times go to <dir>/preds[-h252]/.
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
import sys
import time
from multiprocessing import get_context
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import numpy as np  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import tournament as T  # noqa: E402

STATE = {}


def _init(path):
    blob = pickle.loads(Path(path).read_bytes())
    df, layers = blob["df"], blob["layers"]
    cross = layers["company"] + layers["industry"]
    STATE.update(df=df, layers=layers, ranked=T.rank_transform(df, cross))


def _ic(frame, scores, h):
    f = frame[["date", f"y{h}"]].assign(s=scores)
    v = T.spearman_by_date(f, "s", f"y{h}")
    return float(v.mean()) if v.notna().any() else None


def run_config(cfg):
    df, layers, ranked = STATE["df"], STATE["layers"], STATE["ranked"]
    h = cfg["horizon"]
    scores = np.full(len(df), np.nan, dtype=np.float64)
    folds = []
    for year in T.CONFIG["walkForward"]["outerFoldYears"]:
        train, test = T.fold_split(df, year, h)
        if test.empty:
            continue
        t0 = time.time()
        if cfg["family"] == "RULE":
            name = cfg["id"][5:]
            s = T.rule_score(name, ranked.loc[test.index]).to_numpy()
            scores[test.index] = s
            folds.append({"year": year, "trainRows": 0, "oosIC": _ic(test, s, h)})
            continue
        pred, tr_pred, _, cols = T.fit_predict(cfg, train, test, ranked.loc[train.index], ranked.loc[test.index], layers, want_train_pred=True)
        scores[test.index] = pred
        folds.append({"year": year, "trainRows": int(len(train)), "trainDates": int(train["date"].nunique()),
                      "trainLastExit": str(train[f"exit{h}"].max().date()), "testFirst": str(test["date"].min().date()),
                      "isIC": _ic(train, tr_pred, h), "oosIC": _ic(test, pred, h), "seconds": round(time.time() - t0, 2), "nFeatures": len(cols)})
    return cfg["id"], scores.astype(np.float32), folds


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", required=True)
    ap.add_argument("--h252", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--only", default=None, help="comma-separated config ids (debug)")
    a = ap.parse_args(argv)
    s = Path(a.scratch)
    grid = T.grid_h252() if a.h252 else T.grid()
    if a.only:
        keep = set(a.only.split(","))
        grid = [g for g in grid if g["id"] in keep]
    out = s / ("preds-h252" if a.h252 else "preds")
    out.mkdir(exist_ok=True)
    todo = [g for g in grid if not (out / f"{g['id']}.npz").exists()]
    # Slow families first so the pool stays busy at the end.
    order = {"RF": 0, "ET": 0, "XGB": 1, "LGBM": 2, "ENET": 3, "RIDGE": 4, "RULE": 5}
    todo.sort(key=lambda g: order[g["family"]])
    print(json.dumps({"configs": len(grid), "todo": len(todo)}), flush=True)
    t0 = time.time()
    with get_context("fork").Pool(a.workers, initializer=_init, initargs=(str(s / "dataset.pkl"),)) as pool:
        for i, (cid, scores, folds) in enumerate(pool.imap_unordered(run_config, todo)):
            np.savez_compressed(out / f"{cid}.npz", scores=scores, folds=json.dumps(folds))
            ics = [f["oosIC"] for f in folds if f.get("oosIC") is not None]
            print(f"[{i + 1}/{len(todo)}] {cid} oosIC={np.mean(ics) if ics else float('nan'):.4f} t={time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
