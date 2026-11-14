"""Small derived tables for the report: state-variable availability and per-year sleeve choices (reads the run outputs only)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cocktail as C  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", required=True)
    a = ap.parse_args(argv)
    ev = pd.read_pickle(Path(a.scratch) / "cocktail-eval.pkl")
    st = ev["states"]
    avail = {}
    lag = {**{k: 0 for k in C.KR_STATES}, "UST10_LEVEL": 4, "UST10_CHG_63": 4, "CURVE_10Y2Y": 4, "CURVE_CHG_63": 4, "BROAD_DOLLAR_CHG_63": 8,
           "USDKRW_CHG_63": 8, "USDKRW_VOL_63": 8, "VIX_LEVEL": 4, "VIX_CHG_63": 4, "CORR_KR_USDKRW_126": 8, "CORR_KR_UST10_126": 4}
    for c in C.ALL_STATES:
        s = st[c]
        first = s.first_valid_index()
        avail[c] = {"firstVisibleKrSession": str(first.date()) if first is not None else None, "lagCalendarDays": lag[c],
                    "coverage2014to2026": round(float(s.loc["2014":].notna().mean()), 4), "coverage2018to2026": round(float(s.loc["2018":].notna().mean()), 4)}
    choices = {}
    for n in ("SLEEVE_MOMENTUM_SWITCH", "A1_MOMENTUM_CRASH_GUARD", "B1_RIDGE_ALL_STATES", "B2_LGBM_ALL_STATES", "B3_RIDGE_KR_ONLY", "A2_INVERSE_VOL_RISK_BUDGET"):
        w = pd.DataFrame(ev["weights"][n]).T.fillna(0.0)
        w.index = pd.to_datetime(w.index)
        choices[n] = {int(y): {k: round(float(v), 3) for k, v in g.mean().items()} for y, g in w.groupby(w.index.year)}
    out = {"stateAvailability": avail, "meanSleeveWeightsByYear": choices}
    (HERE / "results" / "summary-tables.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=0)[:3500])


if __name__ == "__main__":
    main()
