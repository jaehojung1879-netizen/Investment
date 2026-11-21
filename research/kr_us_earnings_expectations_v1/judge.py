"""Apply PREREGISTRATION.md section 3: twelve primary claims, Holm, regime sign check, and the ETF rule.

    python -m research.kr_us_earnings_expectations_v1.judge
"""
from __future__ import annotations

import json
from pathlib import Path

from research.alpha_search_round6_v1 import common as CM

R = Path(__file__).resolve().parent / "results"


def load(name):
    p = R / name
    return json.loads(p.read_text()) if p.exists() else None


def claims_for(mkt):
    ev, bk = load(f"{mkt}-events.json"), load(f"{mkt}-books.json")
    out = {}
    if ev:
        a = ev["E_A_persistence"]
        out["E_A"] = (a["all"], [a["BEFORE_2023"], a["FROM_2023"]], False)
        b = ev["E_B_drift"]["strict126"]
        out["E_B"] = (b["topMinusBottom"], [b["BEFORE_2023"], b["FROM_2023"]], False)
        h = ev["E_H3_divergence"]
        out["E_H3"] = None if h.get("status") == "NOT_EVALUABLE" else (h["lowEarMinusHighEar"], [h["BEFORE_2023"], h["FROM_2023"]], True)
    if bk:
        f = bk["fixed"]["126"]
        for c in ("E_H1", "E_H2"):
            out[c] = (f["FULL"]["pairs"][c], [f["BEFORE_2023"]["pairs"][c], f["FROM_2023"]["pairs"][c]], False)
        i = bk["E_IND"]
        out["E_IND"] = (i["topMinusBottom"], [i["BEFORE_2023"], i["FROM_2023"]], False)
    return out


def main():
    allc = {}
    for m in ("kr", "us"):
        for k, v in claims_for(m).items():
            allc[f"{m.upper()}|{k}"] = v
    for m in ("KR", "US"):
        for k in ("E_A", "E_B", "E_H1", "E_H2", "E_H3", "E_IND"):
            allc.setdefault(f"{m}|{k}", None)
    ps = {}
    for k, v in allc.items():
        if v is None or v[0].get("pOneSided") is None:
            ps[k] = None
        else:
            ps[k] = v[0]["pTwoSided"] if v[2] else v[0]["pOneSided"]
    adj = CM.holm(ps)
    out = {}
    for k, v in allc.items():
        if v is None:
            out[k] = {"verdict": "NOT_EVALUABLE", "holmP": adj[k]}
            continue
        full, halves, two = v
        sign = 1 if full["mean"] > 0 else -1
        same = all(h.get("mean") is not None and (h["mean"] > 0) == (sign > 0) for h in halves)
        directional_ok = same and (two or sign > 0)
        verdict = "SUPPORTED" if directional_ok and adj[k] < 0.05 else "DIRECTIONAL_ONLY" if directional_ok else "NOT_SUPPORTED"
        out[k] = {"mean": full["mean"], "ci": full.get("ci"), "n": full.get("n"), "p": ps[k], "holmP": adj[k],
                  "halves": [h.get("mean") for h in halves], "twoSided": two, "verdict": verdict}
    etf = {}
    for m, books in (("kr", ("SUE_TOP", "S2_SUE", "S2")), ("us", ("SUE_TOP", "PC_SUE", "BASE", "U1"))):
        bk = load(f"{m}-books.json")
        if not bk or "ledgers" not in bk:
            continue
        for b in books:
            v = bk["fixed"]["126"]["FULL"]["vsETF"].get(b)
            led = bk["ledgers"].get(f"L26|{b}", {})
            etf[f"{m.upper()}|{b}"] = {"sixMonthMean": v["mean"], "ci": v["ci"], "l26Excess": led.get("excess"),
                                      "beatEtf": bool(v["ci"] and v["ci"][0] > 0 and (led.get("excess") or -1) > 0)}
    res = {"familySize": len(allc), "claims": out, "etfRule": etf}
    (R / "judgement.json").write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
    for k, v in sorted(out.items()):
        print(k, v["verdict"], round(v.get("mean", 0) or 0, 4), "holm", round(v["holmP"], 4))
    print(json.dumps(etf, indent=1))


if __name__ == "__main__":
    main()
