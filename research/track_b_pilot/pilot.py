"""Track B pilot: three documented shocks, what was observable at the shock and what was observed afterwards.

Reads only inputs already preserved in the repository (no network, no model, no statistic):

* SPY total return (Stage 1 #363), VIX / VIX3M (exp1, #367), DFII10 / T10YIE (#361), ALFRED as-of BAA - GS10
  month-ends (Stage 1), SPF median corporate-profit forecasts (#361), JK monetary/information shocks (#361),
  Shiller earnings (MVMA #357, vintage 2024-09).

EX ANTE = values dated strictly before the market's first reaction to the anchor (`last_pre`), the as-of credit
value of the month-end decision before the anchor, and the last SPF survey whose release precedes the anchor.
EX POST = everything after; it is reported in separate fields and never used to describe the ex-ante state.

SPF release timing: surveys are released in the middle of the quarter's second month (Feb/May/Aug/Nov). This file
uses the 15th of that month as the release date -- an approximation, stated as one.

    python -m research.track_b_pilot.pilot
"""
from __future__ import annotations

import csv
import datetime as dt
import gzip
import io
import json
import sys
from pathlib import Path

from research.market_causal_transmission_v1 import spf_reader as SPF
from research.market_risk_discovery_v1 import baseline_census as B
from research.market_risk_discovery_v1 import exp1_inputs as I
from research.market_risk_discovery_v1 import label_census as L

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
MCT_RAW = REPO / "research/market_causal_transmission_v1/data/raw"
SHILLER = REPO / "research/market_valuation_macro_overlay_v1/data/shiller-monthly-20240904.csv"

EVENTS = {
    "2008_credit": {"anchor": "2007-08-09", "firstReaction": "2007-08-09", "minus15": "2008-01-18",
                    "cause": "credit/funding: BNP Paribas froze three funds citing subprime valuation (2007-08-09)"},
    "2020_pandemic": {"anchor": "2020-02-24", "firstReaction": "2020-02-24", "minus15": "2020-03-09",
                      "cause": "exogenous real shock: COVID-19 spread outside China; liquidity stress in March"},
    "2025_tariff": {"anchor": "2025-04-02", "firstReaction": "2025-04-03", "minus15": "2025-04-04",
                    "cause": "trade policy: broad US tariff announcement after the close on 2025-04-02"},
}
HORIZONS = {"1m": 21, "3m": 63, "6m": 126, "12m": 252}


def fred(path: Path, col: str) -> dict[str, float]:
    out = {}
    for row in csv.DictReader(io.StringIO(gzip.decompress(path.read_bytes()).decode())):
        v = row[col].strip()
        if v and v != ".":
            out[row["observation_date"]] = float(v)
    return out


def last_pre(series: dict[str, float], date: str) -> tuple[str, float] | None:
    keys = [k for k in series if k < date]
    return (max(keys), series[max(keys)]) if keys else None


def at_or_after(series: dict[str, float], date: str) -> tuple[str, float] | None:
    keys = [k for k in series if k >= date]
    return (min(keys), series[min(keys)]) if keys else None


def spf_release(year: int, q: int) -> str:
    return dt.date(year, 3 * q - 1, 15).isoformat()


def spf_table() -> list[dict]:
    rows = []
    for r in SPF.load_spf_stdlib():
        rows.append({**r, "release": spf_release(r["year"], r["quarter"])})
    return sorted(rows, key=lambda r: r["release"])


def target(year: int, q: int, ahead: int) -> tuple[int, int]:
    n = year * 4 + (q - 1) + ahead
    return n // 4, n % 4 + 1


def spf_view(anchor: str) -> dict:
    """Last survey before the anchor (ex ante) and the same-target forecast in the next four surveys (ex post).
    Target = the quarter forecast 4 quarters ahead (CPROF6) at the pre survey; later surveys forecast that same
    quarter with CPROF5 (3 ahead), CPROF3 (1 ahead) and CPROF2 (current quarter)."""
    tab = spf_table()
    pre = [r for r in tab if r["release"] < anchor][-1]
    tgt = target(pre["year"], pre["quarter"], 4)
    col_by_ahead = {4: "CPROF6", 3: "CPROF5", 1: "CPROF3", 0: "CPROF2"}
    path = []
    for r in [x for x in tab if x["release"] >= anchor][:4]:
        k = (tgt[0] * 4 + tgt[1] - 1) - (r["year"] * 4 + r["quarter"] - 1)
        col = col_by_ahead.get(k)
        v = r.get(col) if col else None
        path.append({"survey": f"{r['year']}Q{r['quarter']}", "releaseApprox": r["release"], "aheadQuarters": k,
                     "forecastOfTarget": v,
                     "revisionVsPre": (v / pre["CPROF6"] - 1) if (v is not None and pre.get("CPROF6")) else None})
    return {"preSurvey": f"{pre['year']}Q{pre['quarter']}", "preReleaseApprox": pre["release"],
            "targetQuarter": f"{tgt[0]}Q{tgt[1]}", "preForecastOfTarget": pre.get("CPROF6"),
            "preCurrentQuarter": pre.get("CPROF2"), "postSurveys": path}


def shiller_e() -> dict[str, float]:
    out = {}
    for r in csv.DictReader(SHILLER.open()):
        if r["E"] and r["partialMonth"] == "0":
            out[r["month"]] = float(r["E"])
    return out


def jk_window(anchor: str, months: int = 6) -> list[dict]:
    rows = list(csv.DictReader(io.StringIO(gzip.decompress((MCT_RAW / "jk-shocks-monthly.csv.gz").read_bytes()).decode())))
    a = dt.date.fromisoformat(anchor)
    out = []
    for r in rows:
        m = dt.date(int(r["year"]), int(r["month"]), 1)
        lag = (m.year - a.year) * 12 + m.month - a.month
        if -2 <= lag <= months:
            out.append({"month": m.isoformat()[:7], "MP_pm": float(r["MP_pm"]), "CBI_pm": float(r["CBI_pm"])})
    return out


def build() -> dict:
    dates, tr = L.load_tr()
    pos = {d: k for k, d in enumerate(dates)}
    trd = dict(zip(dates, tr))
    vix, vxv = I.load("VIXCLS"), I.load("VXVCLS")
    real, bei = fred(MCT_RAW / "fred-DFII10.csv.gz", "DFII10"), fred(MCT_RAW / "fred-T10YIE.csv.gz", "T10YIE")
    credit = B.credit_series()
    E = shiller_e()
    out = {"study": "track-b-pilot", "evidenceClass": "DESCRIPTIVE_CASE_STUDY_ON_EXPOSED_HISTORY",
           "noStatistics": True, "noInvestmentComputation": True, "events": {}}
    for name, ev in EVENTS.items():
        react = ev["firstReaction"]
        p0 = last_pre(trd, react)
        k0 = pos[p0[0]]
        month_before = (dt.date.fromisoformat(ev["anchor"]).replace(day=1) - dt.timedelta(days=1)).isoformat()[:7]
        ex_ante = {
            "priceDate": p0[0], "drawdownFromPeak": float(p0[1] / max(tr[:k0 + 1]) - 1),
            "vix": last_pre(vix, react), "vix3m": last_pre(vxv, react),
            "vixOverVix3m": (last_pre(vix, react)[1] / last_pre(vxv, react)[1]) if last_pre(vxv, react) else None,
            "realYield10y": last_pre(real, react), "breakeven10y": last_pre(bei, react),
            "creditSpreadAsOfPriorMonthEnd": {"decisionMonth": month_before, "baaMinusGs10": credit.get(month_before)},
            "spf": None}
        spf = spf_view(react)
        ex_ante["spf"] = {k: spf[k] for k in ("preSurvey", "preReleaseApprox", "targetQuarter", "preForecastOfTarget",
                                              "preCurrentQuarter")}
        post = {"spyTotalReturn": {}, "realYieldChange": {}, "breakevenChange": {}, "vix": {}}
        for h, n in HORIZONS.items():
            if k0 + n < len(dates):
                d = dates[k0 + n]
                post["spyTotalReturn"][h] = {"date": d, "value": float(tr[k0 + n] / tr[k0] - 1)}
                for key, s, base in (("realYieldChange", real, ex_ante["realYield10y"]),
                                     ("breakevenChange", bei, ex_ante["breakeven10y"])):
                    v = at_or_after(s, d)
                    post[key][h] = None if (v is None or base is None) else round(v[1] - base[1], 3)
                v = at_or_after(vix, d)
                post["vix"][h] = None if v is None else v[1]
        window = tr[k0:min(len(tr), k0 + 253)]
        post["maxDrawdownWithin12m"] = float(window.min() / tr[k0] - 1)
        post["creditSpreadMonthEnds"] = {m: credit.get(m) for m in sorted(credit)
                                         if month_before <= m <= (dt.date.fromisoformat(ev["anchor"]) + dt.timedelta(days=380)).isoformat()[:7]}
        post["spfSameTargetRevisions"] = spf["postSurveys"]
        a = dt.date.fromisoformat(ev["anchor"])
        e0 = E.get(month_before)
        post["shillerEarnings"] = {f"+{m}m": (E.get(f"{(a.year * 12 + a.month - 1 + m) // 12:04d}-{(a.month - 1 + m) % 12 + 1:02d}"))
                                   for m in (6, 12, 24)}
        post["shillerEarnings"]["base"] = e0
        post["jkShocks"] = jk_window(ev["anchor"]) or "NOT_AVAILABLE (series ends 2024-01)"
        out["events"][name] = {**ev, "exAnte": ex_ante, "exPost": post}
    return out


def main() -> int:
    out = build()
    (HERE / "track-b-pilot.json").write_text(json.dumps(out, indent=1, sort_keys=True, default=float) + "\n")
    print(json.dumps(out, indent=1, default=float)[:200])
    return 0


if __name__ == "__main__":
    sys.exit(main())
