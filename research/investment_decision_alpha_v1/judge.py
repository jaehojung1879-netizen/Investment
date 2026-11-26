"""Apply PREREGISTRATION.md: S1 family (IC-A, IC-1..IC-4) and S2 family (four T1 claims), Holm within each family.

    python -m research.investment_decision_alpha_v1.judge
"""
from __future__ import annotations

import json
from pathlib import Path

from research.alpha_search_round6_v1 import common as CM

R = Path(__file__).resolve().parent / "results"


def load(n):
    p = R / n
    return json.loads(p.read_text()) if p.exists() else None


def p_of(cell, two):
    if cell is None or cell.get("pOneSided") is None:
        return None
    p = cell["pOneSided"]
    if two:
        return cell.get("pTwoSided", min(1.0, 2 * min(p, 1 - p)))
    return p


def verdict(full, halves, holm_p, expect_sign, two):
    m = full.get("mean")
    if m is None:
        return "NOT_EVALUABLE"
    sign = 1 if m > 0 else -1
    same = all(h.get("mean") is not None and ((h["mean"] > 0) == (sign > 0)) for h in halves)
    agrees = expect_sign is None or sign == expect_sign
    if same and agrees and holm_p < 0.05:
        return "SUPPORTED"
    if same and agrees:
        return "DIRECTIONAL_ONLY"
    if same and not agrees and two and holm_p < 0.05:
        return "SUPPORTED_OPPOSITE_DIRECTION"
    return "NOT_SUPPORTED"


def family(claims):
    """claims: name -> (full, [halves], expected_sign or None, two_sided)."""
    ps = {}
    for k, (full, _, exp, two) in claims.items():
        p = p_of(full, two)
        if p is not None and exp == -1 and not two:
            p = 1 - p
        ps[k] = p
    adj = CM.holm(ps)
    out = {}
    for k, (full, halves, exp, two) in claims.items():
        out[k] = {"mean": full.get("mean"), "ci": full.get("ci"), "n": full.get("n"), "independentBlocks": full.get("independentBlocks"),
                  "p": ps[k], "holmP": adj[k], "halves": [h.get("mean") for h in halves], "expectedSign": exp, "twoSided": two,
                  "verdict": verdict(full, halves, adj[k], exp, two)}
    return out


def main(argv=None):
    """--corrected: read the 2026-11-22 corrected outputs (S1 on US input v3, S2 v2, S3 v2) into judgement-corrected.json;
    the original judgement.json is left as it was."""
    import sys
    corrected = "--corrected" in (argv if argv is not None else sys.argv[1:])
    suffix = {"s1": "-v3input", "s2": "-v2", "s3": "-v2"} if corrected else {"s1": "", "s2": "", "s3": ""}
    res = {}
    s1 = load(f"s1-industry-cycle{suffix['s1']}.json")
    if s1:
        a = s1["IC_A"]["dProf"]
        c = s1["126"]
        claims = {"IC-A": (a["all"], [a["BEFORE_2023"], a["FROM_2023"]], -1, True),
                  "IC-1": (c["IC_1"]["all"], [c["IC_1"]["BEFORE_2023"], c["IC_1"]["FROM_2023"]], 1, False),
                  "IC-2": (c["IC_2"]["all"], [c["IC_2"]["BEFORE_2023"], c["IC_2"]["FROM_2023"]], 1, False),
                  "IC-3": (c["IC_3"]["all"], [c["IC_3"]["BEFORE_2023"], c["IC_3"]["FROM_2023"]], 1, False)}
        if "IC_4" in s1:
            b = s1["IC_4"]["126"]
            claims["IC-4"] = (b["exclMinusBase"], [b["BEFORE_2023"], b["FROM_2023"]], 1, False)
        res["S1"] = family(claims)
    s2 = {}
    for m, books in (("us", ("BASE", "U1", "SUE_TOP")), ("kr", ("S2",))):
        x = load(f"s2-entry-timing-{m}{suffix['s2']}.json")
        if not x:
            continue
        for b in books:
            c = x[f"{b}|126"]["P1"]
            s2[f"T1-{m.upper()}-{b}"] = (c["all"], [c["BEFORE_2023"], c["FROM_2023"]], None, True)
    if s2:
        res["S2"] = family(s2)
    s3 = load(f"s3-trim{suffix['s3']}.json")
    if s3:
        # the decision itself (trim vs hold) is the one S3 claim; random and proportional trims are its controls
        c = s3["trimMinusHold"]
        claims = {"T2-US-BASE-trimVsHold": (c["all"], [c["BEFORE_2023"], c["FROM_2023"]], None, True)}
        res["S3"] = family(claims)
        res["S3_controls"] = {k: {"mean": s3[k]["all"]["mean"], "ci": s3[k]["all"].get("ci"),
                                  "halves": [s3[k]["BEFORE_2023"]["mean"], s3[k]["FROM_2023"]["mean"]]}
                              for k in ("trimMinusRandom", "trimMinusProp", "randomMinusHold", "trimmedNameAfterMinusSpy")}
    (R / ("judgement-corrected.json" if corrected else "judgement.json")).write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
    for fam, v in ((f, x) for f, x in res.items() if not f.endswith("_controls")):
        for k, c in v.items():
            print(fam, k, c["verdict"], round((c["mean"] or 0) * 100, 3), c["ci"], "holm", round(c["holmP"], 4), c["halves"])


if __name__ == "__main__":
    main()
