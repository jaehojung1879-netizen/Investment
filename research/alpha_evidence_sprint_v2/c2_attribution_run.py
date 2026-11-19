"""Runner for c2-fixed-exposure-attribution-v1.

    python research/alpha_evidence_sprint_v2/c2_attribution_run.py readiness --out <file>
    python research/alpha_evidence_sprint_v2/c2_attribution_run.py execute <ledger_dir> --out <file>

``readiness`` is OUTCOME-FREE: from the saved C2 ledger it reads only dates, tickers and
TARGET weights (never a NAV, a return or a terminal weight), plus file hashes and source
coverage dates. It may run at any time.

``execute`` reads realised C2 outcomes and pre-signal prices. It refuses unless
``research/alpha_evidence_sprint_v2/AUTHORIZATION-c2.json`` exists, was committed by the
owner, and states exactly::

    APPROVE KR_PHASE_D_EXCEPTION c2-fixed-exposure-attribution-v1 <spec sha256>

together with the sha256 of this file and of ``c2_attribution.py``. The Phase D closure
(docs/kr-alpha-research-final-development-assessment.md §7) forbids new KR historical
outcome work without such an owner decision; this runner cannot bypass it.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from research.alpha_evidence_sprint_v2 import c2_attribution as A  # noqa: E402

SPEC = HERE / "c2-fixed-exposure-attribution-v1.json"
AUTH = HERE / "AUTHORIZATION-c2.json"
STANDALONE = ROOT / "docs/results/regional-standalone-paths.json.gz"
REPLAY = ROOT / "docs/weekly-decision/weekly-passive-first-v1-replay-corrected-benchmark.json"
BASIS = ROOT / "docs/weekly-decision/weekly-passive-first-v1-benchmark-basis-protocol.json"
BOK = ROOT / "data/bok-policy-rates.json"
TERMINATED = ROOT / "docs/results/kr-termination-inventory.json"
ETF = "069500.KS"
# Only these keys of a saved block are read in readiness mode. Everything else in the
# row (NAVs, returns, terminal weights, costs) is an outcome and is not touched.
READINESS_KEYS = ("date", "endDate", "signalDate", "weights", "selectedTickers", "corporateActionsApplied")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_rows(projection=None):
    data = json.loads(gzip.decompress(STANDALONE.read_bytes()))
    rows = data["regional"]["KR"]
    if projection:
        rows = [{k: r.get(k) for k in projection} for r in rows]
    return rows


# --------------------------------------------------------------------------- #
# readiness (outcome-free)
# --------------------------------------------------------------------------- #
def readiness() -> dict:
    rows = load_rows(READINESS_KEYS)
    replay = json.loads(REPLAY.read_text())
    basis = json.loads(BASIS.read_text())["correctedSeries"]
    corrected = ROOT / basis["file"]
    bok = json.loads(BOK.read_text())
    terminated = {s["code"]: s for s in json.loads(TERMINATED.read_text())["securities"]}
    calendar = replay["calendar"]
    held = {}
    stock_blocks = 0
    for r in rows:
        if r["weights"]:
            stock_blocks += 1
        for t in r["weights"]:
            held.setdefault(t, []).append(r["date"])
    held_terminated = {t: {"blocks": len(d), "firstHeld": d[0], "lastHeld": d[-1],
                           "lastTradingDate": terminated[t].get("lastTradingDate"),
                           "terminationType": terminated[t].get("terminationType"),
                           "terminalConsiderationResolved":
                               (terminated[t].get("completeness") or {}).get("terminalConsiderationResolved")}
                       for t, d in sorted(held.items()) if t in terminated}
    names_per_block = [len(r["weights"]) for r in rows]
    stock_weight = [round(sum(r["weights"].values()), 6) for r in rows]
    return {
        "study": "c2-fixed-exposure-attribution-v1",
        "mode": "READINESS_OUTCOME_FREE",
        "readKeysOnly": list(READINESS_KEYS),
        "inputs": {
            "regionalStandalonePaths": {"path": str(STANDALONE.relative_to(ROOT)), "sha256": sha256(STANDALONE)},
            "weeklyReplay": {"path": str(REPLAY.relative_to(ROOT)), "sha256": sha256(REPLAY),
                             "inputManifestSha256": replay["inputManifestSha256"],
                             "regionalPathsSha256": replay["regionalPathsSha256"]},
            "correctedEtfSeries": {"path": basis["file"], "pinnedSha256": basis["sha256"],
                                   "actualSha256": sha256(corrected) if corrected.exists() else None,
                                   "definition": basis["definition"]},
            "bokPolicyRate": {"path": str(BOK.relative_to(ROOT)), "sha256": sha256(BOK), "basis": bok["basis"],
                              "verifiedThrough": bok["verifiedThrough"], "events": len(bok["events"]),
                              "firstEvent": bok["events"][0]["date"]},
            "terminationInventory": {"path": str(TERMINATED.relative_to(ROOT)), "sha256": sha256(TERMINATED)},
        },
        "blocks": len(rows),
        "calendarBlocks": calendar["blocks"],
        "calendarFirst": calendar["first"], "calendarLast": calendar["last"],
        "blocksWithStocks": stock_blocks,
        "namesPerBlock": {str(n): names_per_block.count(n) for n in sorted(set(names_per_block))},
        "targetStockWeight": {"min": min(stock_weight), "max": max(stock_weight)},
        "distinctNamesHeld": len(held),
        "heldTickers": sorted(held),
        "heldTerminatedSecurities": held_terminated,
        "blocksWithCorporateActionsApplied": sum(1 for r in rows if r["corporateActionsApplied"]),
        "returnsRead": 0, "navValuesRead": 0, "terminalWeightsRead": 0,
    }


# --------------------------------------------------------------------------- #
# execute (owner-gated)
# --------------------------------------------------------------------------- #
def authorization_ok(spec_sha: str) -> tuple[bool, str]:
    if not AUTH.exists():
        return False, "NO_OWNER_AUTHORIZATION_FILE"
    auth = json.loads(AUTH.read_text())
    phrase = f"APPROVE KR_PHASE_D_EXCEPTION c2-fixed-exposure-attribution-v1 {spec_sha}"
    if auth.get("phrase") != phrase:
        return False, "AUTHORIZATION_PHRASE_MISMATCH"
    want = {"c2_attribution.py": sha256(HERE / "c2_attribution.py"),
            "c2_attribution_run.py": sha256(Path(__file__))}
    if auth.get("codeSha256") != want:
        return False, "AUTHORIZED_CODE_HASH_MISMATCH"
    return True, "AUTHORIZED"


def returns_from_closes(closes):
    out = []
    for a, b in zip(closes[:-1], closes[1:]):
        ok = a is not None and b is not None and math.isfinite(a) and math.isfinite(b) and a > 0 and b > 0
        out.append(b / a - 1.0 if ok else None)
    return out


def cash_growth(row) -> dict:
    """Registered cash scenarios for one saved block. BOK_POLICY_PROXY is the replay's own
    ACT/365 daily policy-rate path (``dailyRiskFreeNav``); +100bp adds simple ACT/365 accrual."""
    from datetime import date as _d
    rf = float(row["dailyRiskFreeNav"][-1])
    days = (_d.fromisoformat(row["dailyDates"][-1]) - _d.fromisoformat(row["dailyDates"][0])).days
    return {"ZERO": 1.0, "BOK_POLICY_PROXY": rf, "BOK_POLICY_PLUS_100BP": rf * (1.0 + 0.01 * days / 365.0)}


def window_closes(series_by_ticker, sessions, ticker, signal_date):
    """253 KR-session closes ending at the last KR session <= signal date; None for a gap.

    ``series_by_ticker[t]`` is a ``{iso_date: close}`` mapping; ``sessions`` the sorted KR
    session list. Nothing after the signal date is ever indexed.
    """
    import bisect
    i = bisect.bisect_right(sessions, signal_date) - 1
    if i < A.BETA_WINDOW_RETURNS:
        return []
    window = sessions[i - A.BETA_WINDOW_RETURNS:i + 1]
    source = series_by_ticker.get(ticker) or {}
    return [source.get(d) for d in window]


def build_blocks(saved_rows, etf_close, pre_signal_closes, cash_growth_fn):
    """Assemble ``A.Block`` inputs from saved rows (outcome-reading; execute mode only).

    ``etf_close(date) -> float`` reads the pinned corrected ETF series.
    ``pre_signal_closes(ticker, signal_date) -> (stock_closes, etf_closes)`` returns the
    253 aligned KR-session closes ending ON the signal date (None where no quote).
    ``cash_growth_fn(row) -> {scenario: 1 + R_F}``.
    Returns ``(blocks, failures)``; a saved row that fails the buy-and-hold identity (e.g. a
    corporate-action successor) is a failure with its reason, never a renormalised block.
    """
    blocks, failures = [], []
    for row in saved_rows:
        weights = {t: float(w) for t, w in row["weights"].items()}
        cash_w = 1.0 - sum(weights.values())
        rf_growth = float(row["dailyRiskFreeNav"][-1])
        try:
            growth = A.growth_from_terminal(weights, row.get("terminalWeights") or {}, row["grossReturn"],
                                            cash_w, rf_growth) if weights else {}
        except A.AttributionError as error:
            failures.append({"date": row["date"], "reason": str(error)})
            blocks.append(None)
            continue
        betas = {}
        for t in weights:
            s_closes, e_closes = pre_signal_closes(t, row["signalDate"])
            if len(s_closes) != A.BETA_WINDOW_RETURNS + 1 or len(e_closes) != A.BETA_WINDOW_RETURNS + 1:
                betas[t] = None
                continue
            betas[t], _ = A.ols_beta(returns_from_closes(s_closes), returns_from_closes(e_closes))
        etf_growth = etf_close(row["endDate"]) / etf_close(row["date"])
        days = len(row["dailyDates"])
        blocks.append(A.Block(row["date"], row["endDate"], row["signalDate"], weights, growth, betas,
                              etf_growth, cash_growth_fn(row), days / 252.0))
    return blocks, failures


def attribute_all(blocks):
    results = []
    for b in blocks:
        results.append(A.BlockResult("?", "SAVED_ROW_IDENTITY_FAILED") if b is None else A.attribute_block(b))
    return results


def path_returns(blocks, results, cost_fn, multiplier=1.0):
    """Net block returns for C2 (stocks + ETF residual) and each control, costs charged as the
    replay's ``account`` charges them: on the drifted prior book, before the block's growth."""
    c2_net, ctrl_net = [], {k: [] for k in A.CASH_SCENARIOS}
    prior_c2, prior_ctrl = {}, {k: {} for k in A.CASH_SCENARIOS}
    for b, r in zip(blocks, results):
        if b is None or r.c2_gross is None:
            # an unattributable block breaks every compounded path from here on
            c2_net.append(math.nan)
            for k in A.CASH_SCENARIOS:
                ctrl_net[k].append(math.nan)
            prior_c2, prior_ctrl = {}, {k: {} for k in A.CASH_SCENARIOS}
            continue
        s = sum(b.weights.values())
        target = {**b.weights, ETF: 1.0 - s} if 1.0 - s > 1e-12 else dict(b.weights)
        cost = A.trade_cost(prior_c2, target, ETF, cost_fn, b.date, multiplier)
        gross = r.c2_gross if r.c2_gross is not None else math.nan
        c2_net.append((1 - cost) * (1 + gross) - 1)
        end = {t: target[t] * (b.growth.get(t, b.etf_growth) if t != ETF else b.etf_growth) for t in target}
        total = sum(end.values())
        prior_c2 = {t: v / total for t, v in end.items()} if total > 0 else {}
        for k in A.CASH_SCENARIOS:
            if k not in r.by_cash:
                ctrl_net[k].append(math.nan)
                continue
            eq = r.control_equity
            tgt = {ETF: eq} if eq > 1e-12 else {}
            ccost = A.trade_cost(prior_ctrl[k], tgt, ETF, cost_fn, b.date, multiplier)   # cash leg free
            ctrl_net[k].append((1 - ccost) * (1 + r.by_cash[k]["control"]) - 1)
            g = 1 + r.by_cash[k]["control"]
            prior_ctrl[k] = {ETF: eq * b.etf_growth / g} if g > 0 and eq > 1e-12 else {}
    return c2_net, ctrl_net


def analyse(saved_rows, etf_close, pre_signal_closes, cost_fn, years_total):
    """Pure core of ``execute`` (tested on synthetic rows): attribution at cost 1x/2x/3x."""
    blocks, failures = build_blocks(saved_rows, etf_close, pre_signal_closes, cash_growth)
    results = attribute_all(blocks)
    etf_net = [b.etf_growth - 1.0 if b else math.nan for b in blocks]
    per_cost, verdict_input = {}, {}
    for m in A.COST_MULTIPLIERS:
        c2_net, ctrl_net = path_returns(blocks, results, cost_fn, m)
        per_cost[f"{m:g}x"] = A.summarize(results, c2_net, ctrl_net, etf_net, years_total,
                                          len(saved_rows) / years_total)
    for k in A.CASH_SCENARIOS:
        one = per_cost["1x"]["scenarios"][k]["selectionAnnualized"]
        two = per_cost["2x"]["scenarios"][k]["selectionAnnualized"]
        verdict_input[k] = {"mean": one["mean"], "ci95": one["ci95"], "mean2x": two["mean"]}
    # SELECTION is gross of cost by construction; the 2x requirement reads the net c2-vs-control gap
    for k in A.CASH_SCENARIOS:
        gap = per_cost["2x"]["scenarios"][k]["c2VsControl"]
        verdict_input[k]["mean2x"] = None if gap is None else gap["arithmeticActive"]
    return {"failures": failures, "byCost": per_cost,
            "clipped": sum(1 for r in results if r.clip),
            "verdict": A.verdict(verdict_input)}


def execute(ledger: Path) -> dict:  # pragma: no cover - owner-gated, never run in CI
    spec_sha = sha256(SPEC)
    ok, reason = authorization_ok(spec_sha)
    if not ok:
        raise SystemExit(f"REFUSED: {reason}")
    from pipeline import provenance, replay_calendar as RC, replay_inputs as RI, replay_valuation as RV
    from pipeline import weekly_decision as W
    spec = json.loads(SPEC.read_text())
    store = RI.InputStore(ledger, provenance.REPLAY_VERSION, provenance.DATA_VERSION)
    manifest = store.manifest()
    if manifest["sha256"] != spec["pinnedInputs"]["replayInputManifestSha256"]:
        raise SystemExit("REFUSED: REPLAY_INPUT_MANIFEST_MISMATCH")
    for item in spec["pinnedInputs"]["files"]:
        if sha256(ROOT / item["path"]) != item["sha256"]:
            raise SystemExit("REFUSED: PINNED_FILE_CHANGED " + item["path"])
    frozen = RI.unpack(store.load(manifest, valuation_only=True))
    prices = {t: {d.strftime("%Y-%m-%d"): float(v) for d, v in RV.normalize_daily_series(p["Close"]).items()}
              for t, p in frozen["prices"].items() if p is not None and "Close" in p}
    basis = json.loads(BASIS.read_text())["correctedSeries"]
    etf = {r["date"][:10]: float(r["Close"]) for r in json.loads((ROOT / basis["file"]).read_text())[basis["field"]]}
    sessions = [d.strftime("%Y-%m-%d") for d in RC.sessions("2011-01-01", manifest["through"], "KR")]
    rows = load_rows()

    def pre(ticker, signal):
        return (window_closes(prices, sessions, ticker, signal), window_closes({ETF: etf}, sessions, ETF, signal))

    def cost(as_of, side, is_etf):
        return W.trade_cost_fraction("KR", as_of, is_benchmark=is_etf, side=side)

    from datetime import date as _d
    years = (_d.fromisoformat(rows[-1]["endDate"]) - _d.fromisoformat(rows[0]["date"])).days / 365.25
    out = analyse(rows, lambda d: etf[d], pre, cost, years)
    out.update(study="c2-fixed-exposure-attribution-v1", specSha256=spec_sha,
               evidenceClass="POST_OUTCOME_EXPOSED_DESCRIPTIVE_ATTRIBUTION_OF_FIXED_SAVED_PATH",
               promotionEligible=False)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="mode", required=True)
    r = sub.add_parser("readiness")
    r.add_argument("--out", required=True)
    e = sub.add_parser("execute")
    e.add_argument("ledger")
    e.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    if args.mode == "readiness":
        out = readiness()
        Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
        print(json.dumps({k: out[k] for k in ("blocks", "blocksWithStocks", "distinctNamesHeld")}))
        return 0
    out = execute(Path(args.ledger))
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True, default=str) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
