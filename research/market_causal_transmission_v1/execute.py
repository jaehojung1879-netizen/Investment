"""MCT-v1 Stage C: the one authorized execution of H1, H2 and H3. Refuses a second run.

Order (lessons from the #359 audit of MVMA-v1):
1. refuse if `results/EXECUTION-STARTED.json` or the result exists; verify the authorization's hashes;
2. write the marker BEFORE the first outcome is read;
3. compute everything; write ONE result JSON through a temp file and rename.

Usage::

    python -m research.market_causal_transmission_v1.execute
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np

from research.market_valuation_macro_overlay_v1.vendor import market_timing_pr316 as MT

from . import models as M
from . import panel as P
from . import transmission as T

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PROTOCOL = HERE / "protocol.json"
AUTHORIZATION = HERE / "authorization.json"
MARKER = HERE / "results" / "EXECUTION-STARTED.json"
RESULT = HERE / "results" / "mct-v1-result.json"


class ExecutionRefused(RuntimeError):
    pass


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify() -> tuple[dict, dict]:
    for path in (MARKER, RESULT):
        if path.exists():
            raise ExecutionRefused("ONE_SHOT_ALREADY_SPENT: " + path.name)
    if not AUTHORIZATION.exists():
        raise ExecutionRefused("NO_AUTHORIZATION_FILE")
    auth = json.loads(AUTHORIZATION.read_text())
    for rel, expected in auth["pinnedSha256"].items():
        if sha(REPO / rel) != expected:
            raise ExecutionRefused("PINNED_FILE_CHANGED: " + rel)
    return json.loads(PROTOCOL.read_text()), auth


# ------------------------------------------------------------------ H2 / H3


def _loss(fwd: list[float | None], threshold: float) -> list[bool | None]:
    return [None if v is None else v <= threshold for v in fwd]


def _lagged(rows: list[dict], k: int) -> list[dict]:
    keys = ("highPe", "highCape", "earnDown", "creditStress", "trendDown", "volHigh")
    return [{**r, **{key: (rows[i - k][key] if i >= k else None) for key in keys}} for i, r in enumerate(rows)]


def forecast_block(spec: dict, rows: list[dict], fwd: dict, h: int, threshold: float, strength: float,
                   eval_ok=lambda m: True) -> dict:
    H2 = spec["H2"]
    a, b = H2["sample"]["evaluation"]
    loss = _loss(fwd[h], threshold)
    mask = [a <= r["month"] <= b and eval_ok(r["month"]) for r in rows]
    preds = {name: M.walk_forward(rows, loss, h, mask, model, strength, H2["logitL2"])
             for name, model in H2["models"].items()}
    idx = [i for i in range(len(rows)) if mask[i] and loss[i] is not None and preds["M0"][i] is not None]
    y = [float(loss[i]) for i in idx]
    scores = {}
    for name, p in preds.items():
        pi = [p[i] for i in idx]
        bs = M.brier(pi, y)
        scores[name] = {"brier": float(bs.mean()), "logLoss": M.log_loss(pi, y), "auc": M.auc(pi, y),
                        "_brier": bs}
    base = scores["M0"]["brier"]
    for s in scores.values():
        s["brierSkillVsM0"] = 1 - s["brier"] / base
    return {"n": len(idx), "lossRate": float(np.mean(y)), "first": rows[idx[0]]["month"], "last": rows[idx[-1]]["month"],
            "scores": scores, "_preds": preds, "_idx": idx, "_y": y}


def brier_test(block: dict, a: str, b: str, lag: int) -> dict:
    d = block["scores"][a]["_brier"] - block["scores"][b]["_brier"]
    r = M.nw_mean(d, lag)
    return {"meanDifference": r["mean"], "se": r["se"], "p": r["p"], "n": r["n"], "lag": lag,
            "reading": f"positive = {b} has the lower Brier score"}


def cell_table(rows: list[dict], fwd12: list[float | None], loss12: list[bool | None], first: str, last: str) -> dict:
    out = {}
    for i, r in enumerate(rows):
        if not (first <= r["month"] <= last) or fwd12[i] is None:
            continue
        parts = (r["highPe"], r["earnDown"], r["creditStress"])
        key = "MISSING" if None in parts else "PE{}_EARN{}_CREDIT{}".format(*["1" if v else "0" for v in parts])
        out.setdefault(key, []).append((fwd12[i], loss12[i]))
    return {k: {"n": len(v), "meanForward12MExcess": float(np.mean([x for x, _ in v])),
                "p10Forward12MExcess": float(np.percentile([x for x, _ in v], 10)),
                "lossFrequency": float(np.mean([bool(z) for _, z in v]))} for k, v in sorted(out.items())}


def allocation(spec: dict, rows: list[dict], block: dict, ff: dict, cost_stress: float = 1.0) -> dict:
    a, b = spec["H2"]["sample"]["evaluation"]
    months = [r["month"] for r in rows if a <= r["month"] <= b]
    pos = {r["month"]: i for i, r in enumerate(rows)}
    r_e = np.array([ff[P.shift(m, 1)][0] + ff[P.shift(m, 1)][1] for m in months])
    r_f = np.array([ff[P.shift(m, 1)][1] for m in months])
    cost = 2 * 2e-4 * cost_stress
    base = block["_preds"]["M0"]
    sources = {"HIST_MEAN": "M0", "VULN": "M_VULN8", "TV": "M_TV", "PE": "M_PE"}
    out = {"months": len(months), "first": months[0], "returnsThrough": P.shift(months[-1], 1),
           "B0": M.path_stats(r_e, r_f), "policies": {}}
    for name, model in sources.items():
        x, prev = [], 0.8
        for m in months:
            i = pos[m]
            prev = M.exposure_from_probability(block["_preds"][model][i], base[i], prev)
            x.append(prev)
        d = MT.decompose(x, r_e, r_f, cost, cost)
        gross = MT.overlay_returns(x, r_e, r_f)
        net = gross - MT.exposure_change_costs(x, cost, cost)
        xbar = float(np.mean(x))
        static = xbar * r_e + (1 - xbar) * r_f
        nw = M.nw_mean(d["netTimingSeries"], 0)
        out["policies"][name] = {
            "averageExposure": xbar, "exposureChanges": d["exposureChanges"],
            "timeAt": {str(w): float(np.mean(np.isclose(x, w))) for w in (0.6, 0.8, 1.0)},
            "annualLevel": 12 * d["level"], "annualTiming": 12 * d["timing"], "annualCost": 12 * d["meanCost"],
            "annualTimingNetOfCost": 12 * d["timingNetOfCost"], "timingNetSeAnnual": 12 * nw["se"], "timingNetP": nw["p"],
            "annualActiveNetVsB0": 12 * d["meanActiveNet"],
            "gross": M.path_stats(gross, r_f), "net": M.path_stats(net, r_f),
            "exposureMatchedStatic": M.path_stats(static, r_f), "_net": net, "_x": x}
    vul = out["policies"]["VULN"]
    w = M.equal_vol_weight(r_e, r_f, float(vul["_net"].std(ddof=1)))
    out["equalVolatilityStatic"] = {"weight": w, **M.path_stats(w * r_e + (1 - w) * r_f, r_f)}
    diff = vul["_net"] - out["policies"]["TV"]["_net"]
    r = M.nw_mean(diff, 0)
    out["VULNminusTV"] = {"annualMeanNetDifference": 12 * r["mean"], "seAnnual": 12 * r["se"], "p": r["p"]}
    return out


# ------------------------------------------------------------------ H1


def h1_block() -> dict:
    rows = T.shock_panel()
    outs = T.outcome_panel(rows)
    scale = T.shock_scale(rows, ["MP", "CBI", "MPS", "MPS_ORTH"])
    lp = lambda y, shocks, lag: T.local_projection(rows, y, shocks, lag, scale)  # noqa: E731
    res = {"scale": scale, "explanation": lp(outs["explain"], ["MP", "CBI"], 1), "prediction": {}, "channels": {},
           "bauerSwanson": {}}
    for h in T.HORIZONS:
        res["prediction"][str(h)] = lp(outs["pred"][h], ["MP", "CBI"], h)
        res["channels"][f"dRealYield_{h}"] = lp(outs["dReal"][h], ["MP", "CBI"], h)
        res["channels"][f"dBreakeven_{h}"] = lp(outs["dBei"][h], ["MP", "CBI"], h)
        res["channels"][f"dEbp_{h}"] = lp(outs["dEbp"][h], ["MP", "CBI"], h)
    res["channels"]["spfRevisionNextSurvey"] = lp(outs["spfNext"], ["MP", "CBI"], 3)
    res["channels"]["spfRevisionNext4Surveys"] = lp(outs["spfNext4"], ["MP", "CBI"], 12)
    res["channels"]["realisedEarnings12"] = lp(outs["earn12"], ["MP", "CBI"], 12)
    for key in ("MPS", "MPS_ORTH"):
        res["bauerSwanson"][f"prediction12_{key}"] = lp(outs["pred"][12], [key], 12)
        res["bauerSwanson"][f"explanation_{key}"] = lp(outs["explain"], [key], 1)
    return res


def strip(node):
    if isinstance(node, dict):
        return {k: strip(v) for k, v in node.items() if not str(k).startswith("_")}
    if isinstance(node, (list, tuple)):
        return [strip(v) for v in node]
    if isinstance(node, np.ndarray):
        return [float(v) for v in node]
    if isinstance(node, (np.floating, np.integer)):
        return node.item()
    return node


def run(spec: dict) -> dict:
    H2 = spec["H2"]
    rows = [r for r in P.signals() if r["month"] >= H2["sample"]["trainingStart"]]
    fwd = P.outcomes(rows, (6, 12))
    ff = P.load_ff()
    strength = H2["cellShrinkageStrength"]
    main12 = forecast_block(spec, rows, fwd, 12, -0.10, strength)
    main6 = forecast_block(spec, rows, fwd, 6, -0.10, strength)
    h2 = {"h12": main12, "h6": main6,
          "H2-P": brier_test(main12, "M_PE", "M_VULN8", 11),
          "secondary": {f"{a}_vs_M_VULN8_h12": brier_test(main12, a, "M_VULN8", 11)
                        for a in ("M0", "M_EARN", "M_CREDIT", "M_ADD", "M_CAPE")},
          "incremental": {"h12": brier_test(main12, "M_TV_LOGIT", "M_TV_PLUS", 11),
                          "h6": brier_test(main6, "M_TV_LOGIT", "M_TV_PLUS", 5)},
          "h6_PE_vs_VULN8": brier_test(main6, "M_PE", "M_VULN8", 5),
          "cellsOutOfSample": cell_table(rows, fwd[12], _loss(fwd[12], -0.10), *H2["sample"]["evaluation"]),
          "cellsTraining": cell_table(rows, fwd[12], _loss(fwd[12], -0.10), H2["sample"]["trainingStart"], "1989-12")}
    for label, lo, hi in (("1990-2007", "1990-01", "2007-12"), ("2008-2024", "2008-01", "2024-08")):
        sub = forecast_block(spec, rows, fwd, 12, -0.10, strength, lambda m, lo=lo, hi=hi: lo <= m <= hi)
        h2.setdefault("subPeriods", {})[label] = {"n": sub["n"], "lossRate": sub["lossRate"],
                                                  "PE_vs_VULN8": brier_test(sub, "M_PE", "M_VULN8", 11),
                                                  "skillVsM0": {k: v["brierSkillVsM0"] for k, v in sub["scores"].items()}}
    rob = {}
    rob["threshold_-0.15"] = brier_test(forecast_block(spec, rows, fwd, 12, -0.15, strength), "M_PE", "M_VULN8", 11)
    for s in (12, 48):
        rob[f"strength_{s}"] = brier_test(forecast_block(spec, rows, fwd, 12, -0.10, s), "M_PE", "M_VULN8", 11)
    rob["signalsLaggedOneMonth"] = brier_test(forecast_block(spec, _lagged(rows, 1), fwd, 12, -0.10, strength),
                                              "M_PE", "M_VULN8", 11)
    rob["exclude2008-09"] = brier_test(forecast_block(spec, rows, fwd, 12, -0.10, strength,
                                                      lambda m: not ("2008-01" <= m <= "2009-12")), "M_PE", "M_VULN8", 11)
    rob["exclude2020"] = brier_test(forecast_block(spec, rows, fwd, 12, -0.10, strength,
                                                   lambda m: not m.startswith("2020")), "M_PE", "M_VULN8", 11)
    h2["robustness"] = rob

    h3 = allocation(spec, rows, main12, ff)
    h3["costStress"] = {f"x{k}": {n: allocation(spec, rows, main12, ff, k)["policies"][n]["annualTimingNetOfCost"]
                                   for n in ("VULN", "TV", "PE")} for k in (2, 3)}
    h1 = h1_block()
    primary = {"H1-P": h1["prediction"]["12"]["mpMinusCbi"]["p"], "H2-P": h2["H2-P"]["p"],
               "H3-P": h3["policies"]["VULN"]["timingNetP"]}
    return {"H1": h1, "H2": h2, "H3": h3, "primaryRawP": primary, "holm": M.holm(primary)}


def main() -> int:
    spec, auth = verify()
    MARKER.parent.mkdir(parents=True, exist_ok=True)
    MARKER.write_text(json.dumps({"startedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
                                  "authorization": auth["authorizationId"], "protocolSha256": sha(PROTOCOL),
                                  "outcomeReadsBeforeThisMarker": 0}, indent=1) + "\n")
    result = run(spec)
    result.update({"study": spec["studyId"], "evidenceClass": spec["evidenceClassification"],
                   "promotionEligible": False, "authorization": auth["authorizationId"], "protocolSha256": sha(PROTOCOL)})
    tmp = RESULT.with_suffix(".tmp")
    tmp.write_text(json.dumps(strip(result), indent=1, sort_keys=True) + "\n")
    os.replace(tmp, RESULT)
    print(json.dumps({"primaryRawP": result["primaryRawP"], "holm": result["holm"]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
