"""POST-HOC diagnostics on the one supported increment (B), added AFTER the pre-registered results were seen. They change no verdict.

    python -m research.active_fund_disclosure_v1.posthoc --private <dir> --out research/active_fund_disclosure_v1/results

1. MATCHED: each book's picks against same-sector nearest-cap unheld names (evaluate_us.matched); the increment of
   (PRICE_CONFIRMED_OW - its control) over (PRICE_CONFIRMED - its control) is the part sector and size do not explain.
2. CAP_FILTER: the same top-half filter on market cap instead of OW_BREADTH; if it gives the same increment, size explains B.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from research.active_fund_disclosure_v1 import evaluate_us as E
from research.alpha_search_round6_v1 import common as CM
from research.alpha_search_round6_v1 import us as R6
from research.us_selection_value_v1 import evaluate as EV
from research.us_selection_value_v1 import followup as FU
from research.us_selection_value_v1 import restored_compare as RCMP


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    P, OUT = Path(a.private), Path(a.out)
    close, feats, qqq, _ = EV.load(P / "us")
    secs = RCMP.sections_of(feats)
    meta, active = E.filing_active(P)
    books = {k: {} for k in ("BASE", "BASE_CTRL", "OW", "OW_CTRL", "CAP", "CAP_CTRL")}
    for d in sorted(secs):
        x = secs[d].copy()
        ow, _ = E.ow_breadth(meta, active, d, x.index)
        if ow is None:
            continue
        x["OW"] = ow.reindex(x.index).fillna(0.0)
        picks = {"BASE": EV.book(x, "PRICE_CONFIRMED", "TOP5"),
                 "OW": EV.book(E.masked(x, x["OW"].rank(pct=True, method="average") >= 0.5), "PRICE_CONFIRMED", "TOP5"),
                 "CAP": EV.book(E.masked(x, x["marketCap"].astype(float).rank(pct=True, method="average") >= 0.5), "PRICE_CONFIRMED", "TOP5")}
        ctrl = {k: E.matched(x, v) if v else [] for k, v in picks.items()}
        if any(c is None for c in ctrl.values()):
            continue
        for k in picks:
            books[k][d] = E.eq(picks[k])
            books[f"{k}_CTRL"][d] = E.eq(ctrl[k])
    out = {"label": "POST_HOC_DIAGNOSTIC_AFTER_PREREGISTERED_RESULTS", "fixed": {}}
    for H in (126, 252):
        rows = []
        for d in sorted(books["BASE"]):
            cs = {k: R6.cohort_w(close, qqq, b[d], d, H) for k, b in books.items()}
            if any(v is None or "unresolved" in v for v in cs.values()):
                continue
            rows.append({"date": d, "entry": cs["BASE"]["entry"], **{k: v["net"] for k, v in cs.items()}})
        df = pd.DataFrame(rows)
        block = FU.spec_block(H)
        cell = {}
        for nm, s in {"FULL": df, "BEFORE_2023": df[df["entry"] < E.AI_LED], "AI_LED_FROM_2023": df[df["entry"] >= E.AI_LED]}.items():
            cell[nm] = {"cohorts": int(len(s)),
                        "owIncrement": CM.boot((s["OW"] - s["BASE"]).tolist(), block),
                        "capFilterIncrement": CM.boot((s["CAP"] - s["BASE"]).tolist(), block),
                        "owMinusCapFilter": CM.boot((s["OW"] - s["CAP"]).tolist(), block),
                        "baseVsMatched": CM.boot((s["BASE"] - s["BASE_CTRL"]).tolist(), block),
                        "owVsMatched": CM.boot((s["OW"] - s["OW_CTRL"]).tolist(), block),
                        "owIncrementNetOfMatched": CM.boot(((s["OW"] - s["OW_CTRL"]) - (s["BASE"] - s["BASE_CTRL"])).tolist(), block)}
        out["fixed"][str(H)] = cell
        print(H, {n: {k: round(v["mean"] * 100, 2) for k, v in c.items() if isinstance(v, dict)} for n, c in cell.items()}, flush=True)
    (OUT / "us-posthoc.json").write_text(json.dumps(out, indent=1, sort_keys=True, default=str) + "\n")


if __name__ == "__main__":
    main()
