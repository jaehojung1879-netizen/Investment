"""Run the ONE authorized MVMA-v1 Phase 2 execution (US, H1-US-TRAILING and H2-US-VM1T). Refuses a second run.

Before any return is read it checks, and refuses on any failure:
* the result file does not exist yet (one-shot; a substantive result is never re-run),
* `authorization-phase2.json` exists and every code and input hash it pins equals the bytes on disk,
* `protocol.load_protocol()` passes, i.e. the frozen protocol and its sidecar are byte-identical to PR #357,
* the signal ledger rebuilt from the preserved inputs equals the committed readiness report.

Usage::

    python -m research.market_valuation_macro_overlay_v1.execute_phase2
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

from . import bil_total_return as BT
from . import build_signals as BS
from . import phase2 as P2
from . import protocol as PR
from . import signals as S

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
AUTHORIZATION = HERE / "authorization-phase2.json"
RESULT = HERE / "results/phase2-us-result.json"
MONTHLY = HERE / "results/phase2-us-monthly.csv"


class ExecutionRefused(RuntimeError):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_authorization() -> tuple[dict, dict]:
    if RESULT.exists():
        raise ExecutionRefused("ONE_SHOT_ALREADY_SPENT: " + RESULT.name)
    if not AUTHORIZATION.exists():
        raise ExecutionRefused("NO_AUTHORIZATION_FILE")
    auth = json.loads(AUTHORIZATION.read_text())
    if auth.get("scope", {}).get("hypotheses") != ["H1-US-TRAILING", "H2-US-VM1T"]:
        raise ExecutionRefused("AUTHORIZATION_SCOPE_MISMATCH")
    for rel, expected in {**auth["codeSha256"], **auth["inputSha256"]}.items():
        actual = sha256(REPO / rel)
        if actual != expected:
            raise ExecutionRefused(f"PINNED_FILE_CHANGED: {rel} {actual} != {expected}")
    spec = PR.load_protocol()
    if sha256(PR.PROTOCOL_PATH) != auth["protocolSha256"]:
        raise ExecutionRefused("PROTOCOL_NOT_THE_AUTHORIZED_ONE")
    rebuilt = BS.build(HERE / "data")
    rebuilt.pop("rows")
    committed = json.loads((HERE / "evidence/us-signal-readiness.json").read_text())
    if json.loads(json.dumps(rebuilt, sort_keys=True, default=str)) != committed:
        raise ExecutionRefused("SIGNAL_LEDGER_DOES_NOT_REPRODUCE")
    return spec, auth


def load_markets() -> tuple[list[str], dict, dict, dict]:
    from pipeline import replay_calendar  # noqa: PLC0415 - pinned XNYS calendar
    sessions = [d.date().isoformat() for d in replay_calendar.sessions("2011-12-01", "2026-09-14", "US")]
    spy_dates, spy_tr, _ = P2.load_spy()
    have = set(spy_dates)
    missing = [s for s in sessions if s not in have]
    if missing:
        raise ExecutionRefused(f"SPY_SESSION_MISSING: {len(missing)} first {missing[:3]}")
    bil = BT.build(P2.BIL_CHART, P2.BIL_ISSUER, sessions)
    return sessions, spy_tr, bil["index"], {k: v for k, v in bil.items() if k != "index"}


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


def robustness(ledger, sessions, spy, bil, spec, primary) -> dict:
    out = {"costStress": {}, "executionDelay": {}}
    for stress in (2.0, 3.0):
        r = P2.analyze(ledger, sessions, spy, bil, spec, cost_stress=stress, with_inference=False)
        out["costStress"][f"x{int(stress)}"] = {
            "VM1TAnnualTimingNetOfCost": r["decomposition"]["VM1T"]["annualTimingNetOfCost"],
            "netCagr": {p: r["policies"][p]["net"]["cagr"] for p in P2.POLICIES}}
    r = P2.analyze(ledger, sessions, spy, bil, spec, delay=2, with_inference=False)
    out["executionDelay"]["plusOneSession"] = {
        "VM1TAnnualTimingNetOfCost": r["decomposition"]["VM1T"]["annualTimingNetOfCost"],
        "netCagr": {p: r["policies"][p]["net"]["cagr"] for p in P2.POLICIES}}

    rows = primary["_rows"]
    n = len(rows)
    excess = primary["_h1Excess12"]
    cheap = np.array([r["cheap"] for r in rows], dtype=bool)
    timing = primary["decomposition"]["VM1T"]["_netTimingSeries"]
    years = np.array([int(r["decisionDate"][:4]) for r in rows])
    lag = spec["inference"]["hac"]["lag12M"]

    def h1_on(mask):
        return P2.hac_ols(excess[mask], cheap[mask], lag)

    yearly_timing = {int(y): float(timing[years == y].sum()) for y in sorted(set(years))}
    yearly_h1 = {int(y): float(excess[years == y].mean()) for y in sorted(set(years))}
    best_t, worst_t = max(yearly_timing, key=yearly_timing.get), min(yearly_timing, key=yearly_timing.get)
    best_h, worst_h = max(yearly_h1, key=yearly_h1.get), min(yearly_h1, key=yearly_h1.get)
    covid = np.array([not ("2020-03" <= r["decisionDate"][:7] <= "2020-12") for r in rows])
    out["dropYears"] = {
        "H1": {"dropBestYear": {"year": best_h, **_h1_view(h1_on(years != best_h))},
               "dropWorstYear": {"year": worst_h, **_h1_view(h1_on(years != worst_h))},
               "dropCovid2020": _h1_view(h1_on(covid))},
        "H2": {"dropBestYear": {"year": best_t, "annual": float(12 * timing[years != best_t].mean())},
               "dropWorstYear": {"year": worst_t, "annual": float(12 * timing[years != worst_t].mean())},
               "dropCovid2020": {"annual": float(12 * timing[covid].mean())}},
    }
    # PE5 as a median rather than a mean: recompute VALUATION_CHEAP from the recorded PE values, then H1 and VM1T.
    window_first = spec["calendar"]["evaluationWindowUS"]["firstDecision"]
    pe_all = [r["pe"] for r in ledger]
    offset = next(i for i, r in enumerate(ledger) if r["decisionDate"] >= window_first)
    median_cheap = [P2.median_cheap(pe_all, offset + i) for i in range(n)]
    states = [{**r, "cheap": c} for r, c in zip(rows, median_cheap)]
    vm1t = S.target_path("VM1", states)["targets"]
    d = P2.MT.decompose(vm1t, primary["_rE"], primary["_rF"], 2 * spec["costs"]["US"]["oneWayBps"] / 1e4,
                        2 * spec["costs"]["US"]["oneWayBps"] / 1e4)
    mc = np.array([bool(c) for c in median_cheap])
    out["pe5Median"] = {"cheapDecisions": int(mc.sum()), "agreementWithMean": float((mc == cheap).mean()),
                        "H1": _h1_view(P2.hac_ols(excess, mc, lag)),
                        "VM1TAnnualTimingNetOfCost": 12 * d["timingNetOfCost"]}
    out["notComputed"] = {
        "2000 and 2008 crises": "outside the registered window (2012-01..2024-08); no change of window",
        "2026 drawdown": "after the window; prospective only",
        "trend x valuation table": "no trend rule is registered in protocol.json; building one after outcomes is forbidden",
        "mega-cap concentration, USD vs KRW": "no registered measure; left to a separate study"}
    return out


def _h1_view(ols):
    return {"difference": ols["slope"], "se": ols["se"], "pTwoSided": ols["pTwoSided"], "n": ols["n"]}


def state_and_regime_tables(primary, spec) -> dict:
    rows = primary["_rows"]
    excess = primary["_h1Excess12"]
    minimum = spec["preOutcomeReadiness"]["MIN_STATE_CELL_DECISIONS"]
    cells = defaultdict(list)
    for r, y in zip(rows, excess):
        if r["cheap"] is None or r["earningsStable"] is None or r["creditStress"] is None:
            key = "UNDETERMINED"
        else:
            env = ("GOOD" if (r["earningsStable"] and not r["creditStress"]) else
                   "BAD" if (not r["earningsStable"] and r["creditStress"]) else "MIXED")
            key = ("CHEAP_" if r["cheap"] else "NOT_CHEAP_") + env
        cells[key].append(float(y))
    state = {k: {"n": len(v), "meanForward12MExcess": float(np.mean(v)),
                 "status": "DESCRIPTIVE_ONLY_BELOW_MIN_CELL" if len(v) < minimum else "DESCRIPTIVE"}
             for k, v in sorted(cells.items())}
    years = np.array([int(r["decisionDate"][:4]) for r in rows])
    r_e, r_f = primary["_rE"], primary["_rF"]
    regime = {}
    for y in sorted(set(years)):
        m = years == y
        regime[int(y)] = {
            "months": int(m.sum()),
            "spyMinusBil": float(np.prod(1 + r_e[m]) - np.prod(1 + r_f[m])),
            **{f"{p}NetTiming": float(primary["decomposition"][p]["_netTimingSeries"][m].sum()) for p in P2.DYNAMIC},
            "VM1TMinusB0Net": float(np.prod(1 + primary["_blocks"]["VM1T"]["_monthlyNet"][m])
                                    - np.prod(1 + primary["_blocks"]["B0"]["_monthlyNet"][m])),
            "cheapShare": float(np.mean([rows[i]["cheap"] for i in np.where(m)[0]])),
        }
    return {"stateTable2x2": state, "byYear": regime}


def comparisons(primary, spec) -> dict:
    blocks, lag = primary["_blocks"], spec["inference"]["hac"]["lagMonthlyPolicy"]
    out = {}
    for a, b in (("VM1T", "V1"), ("VM1T", "M1T"), ("VM1T", "B0"), ("VM1T", "B1"), ("V1", "B0"), ("D1", "B1")):
        diff = blocks[a]["_monthlyNet"] - blocks[b]["_monthlyNet"]
        nw = P2.MT.newey_west_mean(diff, lag)
        out[f"{a}-{b}"] = {"annualMeanNetDifference": 12 * nw["mean"], "seAnnual": 12 * nw["se"],
                           "pTwoSided": P2.normal_two_sided_p(nw["mean"] / nw["se"]) if nw["se"] else None,
                           "role": "DESCRIPTIVE_NOT_IN_HOLM_FAMILY"}
    return out


def verdicts(primary, spec) -> dict:
    alpha = primary["holm"]["alpha"]
    adj = primary["holm"]["adjusted"]
    h1 = primary["H1"]["H12M"]
    h2 = primary["H2"]
    d = primary["decomposition"]["VM1T"]
    p = primary["policies"]
    threshold = spec["economicThresholds"]["level2MinAnnualTimingPp"] / 100
    level1 = h1["difference"] > 0 and adj["H1-US-TRAILING"] < alpha
    level2_stat = h2["annualTimingNetOfCost"] > 0 and adj["H2-US-VM1T"] < alpha
    level2_econ = h2["annualTimingNetOfCost"] >= threshold
    static_net = d["exposureMatchedStatic"]["net"]
    r_e, r_f = primary["_rE"], primary["_rF"]
    vm_vol = float(primary["_blocks"]["VM1T"]["_monthlyNet"].std(ddof=1))
    w_eq = P2.equal_volatility_weight(r_e, r_f, vm_vol)
    eq_static = w_eq * r_e + (1 - w_eq) * r_f
    growth = np.cumprod(1 + eq_static)
    eq_worst12 = float((growth[11:] / np.concatenate([[1.0], growth[:-12]]) - 1).min())
    alpha_path = p["VM1T"]["net"]["cagr"] > p["B0"]["net"]["cagr"] and p["VM1T"]["net"]["cagr"] > static_net["cagr"]
    risk_path = (p["VM1T"]["net"]["maxDrawdown"] > p["B0"]["net"]["maxDrawdown"]
                 and p["VM1T"]["net"]["worst12Months"] > p["B0"]["net"]["worst12Months"]
                 and p["VM1T"]["net"]["maxDrawdown"] > P2.MT.max_drawdown(eq_static)
                 and p["VM1T"]["net"]["worst12Months"] > eq_worst12)
    return {
        "H1-US-TRAILING": ("SUPPORTED_EXPLORATORY" if level1 else "NOT_SUPPORTED"),
        "H2-US-VM1T": ("SUPPORTED_EXPLORATORY" if level2_stat else "NOT_SUPPORTED"),
        "level1MarketPredictability": "MET_EXPLORATORY" if level1 else "NOT_MET",
        "level2PureTiming": ("MET_EXPLORATORY" if (level2_stat and level2_econ) else
                             "ECONOMICALLY_LARGE_NOT_SIGNIFICANT" if level2_econ else
                             "SIGNIFICANT_BELOW_ECONOMIC_THRESHOLD" if level2_stat else "NOT_MET"),
        "level3AlphaPath": ("CANDIDATE_PENDING_PROSPECTIVE_CONFIRMATION" if alpha_path else "NOT_MET"),
        "level3RiskPath": ("CANDIDATE_PENDING_PROSPECTIVE_CONFIRMATION" if risk_path else "NOT_MET"),
        "equalVolatilityStaticWeight": w_eq,
        "equalVolatilityStaticMaxDrawdownMonthly": P2.MT.max_drawdown(eq_static),
        "equalVolatilityStaticWorst12Months": eq_worst12,
        "evidenceClass": spec["evidenceClassification"],
        "promotionEligible": False,
        "note": "Nothing here is promoted: every US date in the window is outcome-exposed and only the prospective "
                "record can confirm.",
    }


def dca(primary, spec) -> dict:
    rows, execs = primary["_rows"], primary["_execsAll"][:primary["periods"] + 1]
    one_way = spec["costs"]["US"]["oneWayBps"] / 1e4
    frac = spec["dca"]["parkedFraction"]
    spy, bil = primary["_spy"], primary["_bil"]
    out = {"role": "SEPARATE_DESCRIPTIVE_STUDY_NOT_IN_HOLM_FAMILY", "contributionDates": [execs[0], execs[-2]],
           "valuationDate": execs[-1]}
    for rule, key in (("DCA-A", None), ("DCA-B", "cheap"), ("DCA-C", "deepDrawdown")):
        triggers = [bool(r[key]) if key else False for r in rows]
        out[rule] = P2.run_dca(rule, triggers, execs, spy, bil, one_way, frac)
    return out


def monthly_csv(primary) -> str:
    rows, execs = primary["_rows"], primary["_execsAll"]
    text = io.StringIO()
    w = csv.writer(text, lineterminator="\n")
    header = ["decisionDate", "execStart", "execEnd", "spyReturn", "bilReturn", "forward12MExcess"]
    header += [f"target{p}" for p in P2.DYNAMIC] + [f"net{p}" for p in P2.POLICIES]
    w.writerow(header)
    for i, r in enumerate(rows):
        w.writerow([r["decisionDate"], execs[i], execs[i + 1], repr(float(primary["_rE"][i])),
                    repr(float(primary["_rF"][i])), repr(float(primary["_h1Excess12"][i]))]
                   + [r["target" + p] for p in P2.DYNAMIC]
                   + [repr(float(primary["_blocks"][p]["_monthlyNet"][i])) for p in P2.POLICIES])
    return text.getvalue()


def main(argv=None) -> int:
    spec, auth = verify_authorization()
    sessions, spy, bil, bil_meta = load_markets()
    ledger = P2.load_ledger()
    primary = P2.analyze(ledger, sessions, spy, bil, spec)
    primary["_spy"], primary["_bil"] = spy, bil
    report = {
        "study": spec["studyId"], "stage": "PHASE_2_US_EXPLORATORY_EXECUTION",
        "evidenceClass": spec["evidenceClassification"], "authorization": auth["authorizationId"],
        "protocolSha256": auth["protocolSha256"], "promotionEligible": False, "productionChange": False,
        "bilTotalReturn": bil_meta,
        "primary": strip(primary), "verdicts": verdicts(primary, spec), "comparisons": comparisons(primary, spec),
        "tables": state_and_regime_tables(primary, spec), "robustness": robustness(ledger, sessions, spy, bil, spec, primary),
        "dca": dca(primary, spec),
    }
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    MONTHLY.write_text(monthly_csv(primary))
    RESULT.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"verdicts": report["verdicts"], "holm": report["primary"]["holm"]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
