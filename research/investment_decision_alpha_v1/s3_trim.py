"""S3 (PREREGISTRATION.md section 3, run because IC-2 kept its sign in both periods): trim on a late-boom signal, or hold?

    python -m research.investment_decision_alpha_v1.s3_trim --private <#353-corrected dir>

Each decision date's BASE book (five names at 20%, SPY for the rest) is bought at the next close and held 252 sessions
without rebalancing. Every 21 sessions a held name whose industry is BOOM on the latest decision date has half its
current value moved to SPY (once per name). Controls on the same book:
  HOLD  never trims;
  RAND  trims the same number of not-yet-trimmed names at the same checks, chosen at random (200 draws);
  PROP  trims every name by the same fraction so that the total value moved equals TRIM's at each check.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.alpha_search_round6_v1 import common as CM
from research.investment_decision_alpha_v1 import s1_industry_cycle as S1
from research.us_selection_value_v1 import evaluate as EV
from research.us_selection_value_v1 import restored_compare as RCMP

HERE = Path(__file__).resolve().parent
AI_LED = pd.Timestamp("2023-01-01")
H, STEP, DRAWS, SEED = 252, 21, 200, 20261121


def simulate(px, spy, w0, trims):
    """px: (T+1, n) prices from entry; trims: {check_index: {name_index: fraction}}. Returns final net value of 1."""
    units = (1 - EV.BUY) * np.asarray(w0, float) / px[0]
    spy_units = (1 - EV.BUY) * (1 - sum(w0)) / spy[0]
    for t in sorted(trims):
        for i, f in trims[t].items():
            moved = units[i] * f * px[t]
            units[i] *= (1 - f)
            spy_units += moved * (1 - EV.SELL) * (1 - EV.BUY) / spy[t]
    final = float((units * px[-1]).sum() * (1 - EV.SELL) + spy_units * spy[-1] * (1 - EV.SELL))
    return final - 1


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", required=True)
    ap.add_argument("--out", default=str(HERE / "results"))
    a = ap.parse_args(argv)
    P = Path(a.private)
    close, feats, qqq, _ = EV.load(P / "us")
    feats["date"] = pd.to_datetime(feats["date"])
    sic = S1.sic_map(HERE / "inputs" / "us-sic.csv")
    st = S1.states(feats, sic)
    st_dates = np.array(sorted(st), dtype="datetime64[ns]")
    boom = {d: {t for m in s.loc[s["BOOM"], "members"] for t in m} for d, s in st.items()}
    secs = RCMP.sections_of(feats)
    idx = close.index
    rows, rng_all = [], []
    for d in sorted(secs):
        if d not in st:
            continue
        names = EV.book(secs[d], "PRICE_CONFIRMED", "TOP5")
        if not names:
            continue
        pos = idx.get_loc(d) + 1
        if pos + H >= len(idx):
            continue
        px = close.iloc[pos:pos + H + 1][names].to_numpy(float)
        spy = close["SPY"].iloc[pos:pos + H + 1].to_numpy(float)
        if not np.isfinite(px).all():
            continue
        w0 = [0.2] * len(names)
        trims, done, schedule = {}, set(), []
        for t in range(STEP, H, STEP):
            s_day = st_dates[np.searchsorted(st_dates, np.datetime64(idx[pos + t]), side="right") - 1]
            hit = [i for i, nm in enumerate(names) if nm in boom[pd.Timestamp(s_day)] and i not in done]
            if hit:
                trims[t] = {i: 0.5 for i in hit}
                done |= set(hit)
            schedule.append((t, len(hit)))
        r_trim = simulate(px, spy, w0, trims)
        r_hold = simulate(px, spy, w0, {})
        # proportional: same value moved at each check, spread over all names (values measured on the untrimmed path)
        prop = {}
        for t, k in schedule:
            if k == 0:
                continue
            vals = px[t] * np.asarray(w0) / px[0]
            target = sum(0.5 * vals[i] for i in trims[t])
            prop[t] = {i: min(1.0, target / vals.sum()) for i in range(len(names))}
        r_prop = simulate(px, spy, w0, prop) if prop else r_hold
        rng = np.random.default_rng([SEED, int(d.strftime("%Y%m%d"))])
        rand = []
        for _ in range(DRAWS):
            left, tr = set(range(len(names))), {}
            for t, k in schedule:
                if k == 0:
                    continue
                pick = rng.choice(sorted(left), size=min(k, len(left)), replace=False)
                tr[t] = {int(i): 0.5 for i in pick}
                left -= set(int(i) for i in pick)
            rand.append(simulate(px, spy, w0, tr))
        spy_ret = (1 - EV.BUY) * spy[-1] / spy[0] * (1 - EV.SELL) - 1
        trimmed_after = [float(px[-1, i] / px[t, i] - spy[-1] / spy[t]) for t, m in trims.items() for i in m]
        rows.append({"date": d, "nTrims": int(sum(len(m) for m in trims.values())), "trim": r_trim, "hold": r_hold, "prop": r_prop,
                     "randMean": float(np.mean(rand)), "spy": spy_ret, "trimmedNameAfterMinusSpy": float(np.mean(trimmed_after)) if trimmed_after else np.nan})
        rng_all.append(rand)
    df = pd.DataFrame(rows).set_index("date")
    act = df[df["nTrims"] > 0]
    block = max(1, round(H / 5))
    out = {"studyId": "investment-decision-alpha-v1/S3", "label": "EXPLORATORY_ON_OUTCOME_EXPOSED_HISTORY", "books": int(len(df)),
           "booksWithAnyTrim": int(len(act)), "meanTrimsPerBook": float(df["nTrims"].mean())}
    for lab, s in (("trimMinusHold", act["trim"] - act["hold"]), ("trimMinusRandom", act["trim"] - act["randMean"]),
                   ("trimMinusProp", act["trim"] - act["prop"]), ("randomMinusHold", act["randMean"] - act["hold"]),
                   ("trimmedNameAfterMinusSpy", act["trimmedNameAfterMinusSpy"])):
        s = s.dropna()
        out[lab] = {"all": CM.boot(s.values, block), "BEFORE_2023": CM.boot(s[s.index < AI_LED].values, block),
                    "FROM_2023": CM.boot(s[s.index >= AI_LED].values, block)}
    trim_rank = [float((np.array(r) < t).mean()) for r, t in zip(rng_all, df["trim"]) if True]
    out["trimPercentileWithinRandom"] = {"mean": float(np.mean([x for x, n in zip(trim_rank, df["nTrims"]) if n > 0]))}
    out["holdMinusSpy"] = CM.boot((df["hold"] - df["spy"]).values, block)
    (Path(a.out) / "s3-trim.json").write_text(json.dumps(out, indent=1, sort_keys=True, default=str) + "\n")
    print(json.dumps({k: (v["all"]["mean"], v["all"].get("ci")) if isinstance(v, dict) and "all" in v else v for k, v in out.items()}, default=str))


if __name__ == "__main__":
    main()
