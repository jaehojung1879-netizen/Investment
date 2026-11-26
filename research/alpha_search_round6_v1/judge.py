"""Apply PREREGISTRATION.md section 3 to the round-6 result files: Holm over the five primary claims, then the checks.

    python -m research.alpha_search_round6_v1.judge
"""
from __future__ import annotations

import json
from pathlib import Path

from research.alpha_search_round6_v1 import common as CM

R = Path(__file__).resolve().parent / "results"


def main():
    kf = json.loads((R / "kr-fixed.json").read_text())["fixed"]["126"]
    kl = json.loads((R / "kr-ledgers.json").read_text())["ledgers"]
    us = json.loads((R / "us.json").read_text())
    uf, ul = us["fixed"]["126"], us["ledgers"]
    claims = {}
    for k in ("K1_TOP5_CAP_NEUTRAL", "K2_CAP_OVER_EQUAL_GATE"):
        l26 = kl[f"L26|FULL|{k}"]
        claims[k] = {"full": kf["FULL"][k]["vsETF"]["mean"], "p": kf["FULL"][k]["vsETF"]["pOneSided"],
                     "halves": [kf["TO_2021"][k]["vsETF"]["mean"], kf["FROM_2022"][k]["vsETF"]["mean"]],
                     "l26Excess": l26["excess"], "l26Mdd": l26["mdd"], "etfMdd": l26["etfMdd"],
                     "exSemiLed": kf["EX_SEMI_LED"][k]["vsETF"]["mean"]}
    for k in ("U1_TOP5_CAP_NEUTRAL", "U2_CAP_OVER_EQUAL_GATE", "U3_SECTOR_DISPERSION_TILT"):
        l26 = ul[f"L26|FULL|{k}"]
        claims[k] = {"full": uf["FULL"][k]["vsSPY"]["mean"], "p": uf["FULL"][k]["vsSPY"]["pOneSided"],
                     "halves": [uf["EXIT_BY_2022"][k]["vsSPY"]["mean"], uf["ENTRY_FROM_2023"][k]["vsSPY"]["mean"]],
                     "l26Excess": l26.get("excess"), "l26Mdd": l26.get("mdd"), "etfMdd": l26.get("spyMdd"), "exSemiLed": "NA"}
    adj = CM.holm({k: c["p"] for k, c in claims.items()})
    out = {"studyId": "alpha-search-round6-v1", "label": "EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_HISTORY",
           "familySize": len(claims), "claims": {k: {**c, **CM.judge(c, adj[k])} for k, c in claims.items()}}
    (R / "judgement.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    for k, c in out["claims"].items():
        print(k, c["verdict"], round(c["full"] * 100, 2), "p", c["p"], "holm", round(c["holmP"], 4), c["checks"])


if __name__ == "__main__":
    main()
