"""Phase 5: the latest industry-cycle state on the last decision date in the data (descriptive; no trading signal).

    python -m research.investment_decision_alpha_v1.current_state --private <#353-corrected dir>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from research.investment_decision_alpha_v1 import s1_industry_cycle as S1
from research.us_selection_value_v1 import evaluate as EV

HERE = Path(__file__).resolve().parent


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", required=True)
    a = ap.parse_args(argv)
    _, feats, _, _ = EV.load(Path(a.private) / "us")
    feats["date"] = pd.to_datetime(feats["date"])
    last = sorted(feats["date"].unique())[-60:]
    sic = S1.sic_map(HERE / "inputs" / "us-sic.csv")
    desc = pd.read_csv(HERE / "inputs" / "us-sic.csv", dtype=str).set_index("ticker")["sicDescription"].to_dict()
    st = S1.states(feats[feats["date"].isin(last)], sic)
    d = max(st)
    s = st[d]
    def row(k):
        r = s.loc[k]
        top = sorted(r["caps"].items(), key=lambda kv: -kv[1])[:5]
        return {"industry": k, "label": desc.get(top[0][0], "") if top else "", "sector": r["sector"], "capexGrowth": round(float(r["capexG"]), 3),
                "revenueGrowth": None if pd.isna(r["revG"]) else round(float(r["revG"]), 3), "momentum252": round(float(r["mom"]), 3),
                "capexTercile": int(r["capexQ"]), "momTercile": int(r["momQ"]), "largestMembers": [t for t, _ in top]}
    out = {"label": "DESCRIPTIVE_CURRENT_STATE_NOT_A_SIGNAL", "date": str(d.date()), "industries": int(len(s)),
           "BOOM": [row(k) for k in s.index[s["BOOM"]]],
           "CUT_and_low_momentum": [row(k) for k in s.index[s["CUT"] & (s["momQ"] == 0)]],
           "semiconductor_367_history": [{"date": str(x.date()), **row_hist} for x in sorted(st)[-26:] for row_hist in
                                         ([{"capexGrowth": round(float(st[x].at["367", "capexG"]), 3), "revenueGrowth": round(float(st[x].at["367", "revG"]), 3),
                                            "momentum252": round(float(st[x].at["367", "mom"]), 3), "BOOM": bool(st[x].at["367", "BOOM"]),
                                            "capexTercile": int(st[x].at["367", "capexQ"])}] if "367" in st[x].index else [])]}
    (HERE / "results" / "current-state-us.json").write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str) + "\n")
    print(json.dumps({k: out[k] for k in ("date", "industries")}), "BOOM", [(r["label"], r["largestMembers"][:3]) for r in out["BOOM"]])
    print("CUT_lowmom", [(r["label"], r["largestMembers"][:3]) for r in out["CUT_and_low_momentum"]])
    print("semis last", out["semiconductor_367_history"][-1:])


if __name__ == "__main__":
    main()
