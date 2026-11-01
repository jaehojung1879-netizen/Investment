"""Run industry-information-transfer-v1 (H1, outcome-blind H2 information measures, H3 diagnostics).

Reads only: the preliminary-earnings tables PR #308 already fetched, the DART
disclosure index PR #308 collected, PIT Top120 snapshots, DART issuer identity,
the v4 industry intervals, and KRX daily closes up to each forecast origin (for
the sector-momentum diagnostic). No stock return after a forecast origin is read
and no DART call is made.

    python research/industry_information_transfer_v1/run.py \
        --signal-history-dir <dir with ledger/universe/kr, collection-universe.json, ledger/prices/kr> \
        --out research/industry_information_transfer_v1
"""
from __future__ import annotations

import argparse
import csv
import glob
import gzip
import hashlib
import json
import random
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SPRINT = ROOT / "research" / "alpha_mechanism_sprint_v1"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(SPRINT))
sys.path.insert(0, str(ROOT))
import sprint  # noqa: E402  (PR #308 parser v3, reused unchanged)
import transfer as T  # noqa: E402

PR308_COMMIT = "f48b6f29993cf572d191f9724d19d2543f375f6c"
SIGNAL_HISTORY_COMMIT = "5d187ec16dca29c68161060f4002227297ebd632"
PERMUTATIONS, SEED = 200, 20261101
MOMENTUM_SESSIONS, LIMIT_MOVE = 63, 0.30
B0, B1, B2 = ("own",), ("own", "mkt"), ("own", "mkt", "ind")


def sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_jsonl_gz(path):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


# --------------------------------------------------------------------------- inputs
def load_sessions() -> T.Sessions:
    from pipeline import replay_calendar
    return T.Sessions([ts.date() for ts in replay_calendar.sessions("2012-10-01", "2026-10-31", "KR")])


def load_industry():
    from pipeline import kr_industry_anatomy
    intervals = json.load(gzip.open(ROOT / "data/kr-industry-membership-foundation-v4/state/intervals.json.gz", "rt"))
    crosswalk = json.loads((ROOT / "research_specs/kr-industry-membership-foundation-v4/crosswalk.json").read_text())
    return lambda ticker, day: kr_industry_anatomy.industry_of(intervals, crosswalk, ticker, day)[0]


def load_universe(src: Path):
    snaps = defaultdict(dict)  # date -> code -> (rank, marketCap)
    for f in sorted(glob.glob(str(src / "ledger/universe/kr/krx-universe-*.jsonl.gz"))):
        for r in read_jsonl_gz(f):
            snaps[r["date"]][r["code"]] = (r.get("rank"), r.get("marketCap"))
    return dict(sorted(snaps.items()))


def snapshot_on_or_before(snaps: dict, day: str):
    keys = [d for d in snaps if d <= day]
    return snaps[keys[-1]] if keys else {}


def corp_tickers(collection: dict) -> dict[str, list[str]]:
    out = {}
    for issuer in collection["issuers"]:
        secs = sorted(issuer["securities"], key=lambda s: (not s["stockCode"].endswith("0"), s["stockCode"]))
        out[issuer["corpCode"]] = [s["ticker"] for s in secs]
    return out


def parsed_docs():
    """(corp -> quarter -> earliest confirmed observation) from PR #308's stored result tables."""
    records = read_jsonl_gz(SPRINT / "data/prelim-docs-member-units.jsonl.gz")
    best = {}
    for rec in records:
        if rec.get("served") != "ZIP":
            continue
        p = sprint.parse_prelim_text(rec.get("tableText", ""))
        q = sprint.stated_quarter(p)
        if q is None:
            continue
        key = (rec["corp"], q)
        cand = (rec["rcept_dt"], rec["rcept_no"], p, rec)
        if key not in best or cand[:2] < best[key][:2]:
            best[key] = cand
    return best, len(records)


def formal_dates() -> dict:
    out = {}
    for f in sorted(glob.glob(str(SPRINT / "data/dart-list/*-A.jsonl.gz"))):
        corp = Path(f).name.split("-")[0]
        for (family, q), row in sprint.first_originals(read_jsonl_gz(f)).items():
            if family == sprint.FORMAL:
                out[(corp, q)] = sprint.parse_ymd(row["rcept_dt"])
    return out


def load_closes(src: Path, tickers: set[str]) -> dict[str, dict[str, float]]:
    closes = defaultdict(dict)
    needles = tuple(f'"ticker": "{t}"' for t in tickers)
    for f in sorted(glob.glob(str(src / "ledger/prices/kr/krx-prices-*.jsonl.gz"))):
        with gzip.open(f, "rt", encoding="utf-8") as handle:
            for line in handle:
                if not any(n in line for n in needles):
                    continue
                r = json.loads(line)
                if r.get("close") and r["close"] > 0 and r.get("volume", 0) > 0:
                    closes[r["ticker"]][r["date"]] = float(r["close"])
    return closes


# --------------------------------------------------------------------------- panel
def build_obs(best, corp_ticker, industry_at, snaps):
    obs = []
    for (corp, q), (rcept_dt, rcept_no, p, rec) in sorted(best.items()):
        tickers = corp_ticker.get(corp, [])
        industry = None
        for t in tickers:
            industry = industry_at(t, q.isoformat())
            if industry:
                break
        disclosed = sprint.parse_ymd(rcept_dt)
        snap = snapshot_on_or_before(snaps, disclosed.isoformat())
        cap = None
        for t in tickers:
            entry = snap.get(t.split(".")[0])
            if entry and entry[1]:
                cap = entry[1]
                break
        obs.append(T.Obs(
            corp=corp, quarter=q, disclosed=disclosed,
            y=T.revenue_growth(p.get("revenue"), p.get("revenuePriorYear")),
            y_op=T.op_change(p.get("operatingIncome"), p.get("operatingIncomePriorYear"), p.get("revenuePriorYear")),
            industry=industry, market_cap=cap,
            extra={"rcept_no": rcept_no, "consolidated": bool(p.get("consolidated")) or "연결" in rec.get("report_nm", ""),
                   "revenue": p.get("revenue"), "revenuePriorYear": p.get("revenuePriorYear"),
                   "operatingIncome": p.get("operatingIncome"), "ticker": tickers[0] if tickers else None,
                   "reportName": rec.get("report_nm")}))
    return obs


def attach_indmom(rows, obs, snaps, industry_at, closes, sessions):
    """Median 63-session as-traded close return of the target's industry Top120 members up to the origin."""
    ticker_of = {o.corp: o.extra.get("ticker") for o in obs}
    cache = {}
    days = sessions.days
    for r in rows:
        key = (r.industry, r.origin, r.corp)
        if key in cache:
            r.indmom = cache[key]
            continue
        end_i = days.index(r.origin)
        window = [d.isoformat() for d in days[max(0, end_i - MOMENTUM_SESSIONS): end_i + 1]]
        snap = snapshot_on_or_before(snaps, r.origin.isoformat())
        own = ticker_of.get(r.corp)
        rets = []
        for code, (rank, _) in snap.items():
            if rank is None or rank > 120:
                continue
            ticker = f"{code}.KS"
            if ticker == own or industry_at(ticker, r.origin.isoformat()) != r.industry:
                continue
            series = closes.get(ticker, {})
            values = [series.get(d) for d in window]
            if len(values) != MOMENTUM_SESSIONS + 1 or any(v is None for v in values):
                continue
            if any(abs(b / a - 1) > LIMIT_MOVE for a, b in zip(values, values[1:])):
                continue
            rets.append(values[-1] / values[0] - 1)
        r.indmom = statistics.median(rets) if len(rets) >= 2 else None
        cache[key] = r.indmom


# --------------------------------------------------------------------------- H2 information measures
def h2_information(obs, formal, sessions, h1_primary) -> dict:
    by_key = {(o.corp, o.quarter): o for o in obs}
    leads, missing_formal, after = [], 0, 0
    for o in obs:
        f = formal.get((o.corp, o.quarter))
        if f is None:
            missing_formal += 1
            continue
        a, b = sessions.next_after(o.disclosed), sessions.next_after(f)
        if a is None or b is None:
            continue
        if b < a:
            after += 1
            continue
        leads.append(sessions.count_between(a, b))
    per_q = defaultdict(list)
    for o in obs:
        prev = by_key.get((o.corp, T.quarter_from_index(T.quarter_index(o.quarter) - 1)))
        if o.y is not None and prev is not None and prev.y is not None:
            per_q[o.quarter].append((o.y, prev.y))
    rhos = [T.spearman([a for a, _ in v], [b for _, b in v]) for v in per_q.values() if len(v) >= 20]
    rhos = [r for r in rhos if r is not None]
    r2 = h1_primary.get("oosR2Challenger")
    return {
        "unitsWithPrelim": len(obs), "unitsWithoutFormalOriginal": missing_formal, "formalBeforePrelim": after,
        "leadSessions": {"n": len(leads), "median": statistics.median(leads) if leads else None,
                         "p25": T.np.percentile(leads, 25).item() if leads else None,
                         "p75": T.np.percentile(leads, 75).item() if leads else None,
                         "shareAtMost5": round(sum(1 for x in leads if x <= 5) / len(leads), 4) if leads else None},
        "rankCorrWithOwnPreviousQuarter": {"quarters": len(rhos), "mean": round(sum(rhos) / len(rhos), 4) if rhos else None,
                                           "min": min(rhos) if rhos else None, "max": max(rhos) if rhos else None},
        "oosR2OfBestPreDisclosureForecastB2": r2,
        "varianceShareNotForecastByB2": (1 - r2) if r2 is not None else None,
        "prelimVsFormalFromPR308": {"revenueWithin1PctShare": 97.5, "operatingIncomeWithin1PctShare": 95.09,
                                    "prelimAmendmentRowShare": 4.75, "source": "research/alpha_mechanism_sprint_v1/results.json at f48b6f2"},
    }


# --------------------------------------------------------------------------- evidence tables
def evidence_tables(out_dir: Path, rows, primary, obs, formal, sessions):
    by_q = {p["quarter"]: p for p in primary["perQuarter"]}
    leads_by_q = defaultdict(list)
    for o in obs:
        f = formal.get((o.corp, o.quarter))
        a = sessions.next_after(o.disclosed)
        b = sessions.next_after(f) if f else None
        if a and b and b >= a:
            leads_by_q[o.quarter.isoformat()].append(sessions.count_between(a, b))
    eligible_by_q = Counter(r.quarter.isoformat() for r in rows)
    units_by_q = Counter(o.quarter.isoformat() for o in obs)
    target_by_q = defaultdict(list)
    for o in obs:
        if o.y is not None:
            target_by_q[o.quarter.isoformat()].append(o.y)
    path = out_dir / "evidence-per-quarter.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        w = csv.writer(handle)
        w.writerow(["quarter", "prelimUnits", "eligibleH1", "evaluatedH1", "medianLeadSessionsPrelimToFormal",
                    "medianRevenueLogGrowthYoY", "mseB1", "mseB2", "deltaB1minusB2", "incrementalRankIC"])
        for q in sorted(units_by_q):
            p = by_q.get(q, {})
            w.writerow([q, units_by_q[q], eligible_by_q.get(q, 0), p.get("n", 0),
                        statistics.median(leads_by_q[q]) if leads_by_q[q] else "",
                        round(statistics.median(target_by_q[q]), 4) if target_by_q[q] else "",
                        _r(p.get("mseBase")), _r(p.get("mseChallenger")), _r(p.get("delta")), _r(p.get("incrementalRankIC"))])
    return path


def _r(x, k=6):
    return "" if x is None else round(x, k)


def dated_example(rows, obs, primary_preds) -> dict | None:
    """A deterministic named example: ELECTRONICS_ELECTRICAL target with the most early peers in 2024Q1."""
    names = {o.corp: (o.extra.get("ticker"), o.extra.get("reportName")) for o in obs}
    cands = [r for r in rows if r.industry == "ELECTRONICS_ELECTRICAL" and r.quarter == date(2024, 3, 31)
             and abs(r.y) < T.CLIP_REVENUE]  # an unclipped target, so the example is not a parse artefact
    if not cands:
        return None
    r = sorted(cands, key=lambda r: (-r.n_ind, r.corp))[0]
    return {
        "target": {"corp": r.corp, "ticker": names[r.corp][0], "quarter": r.quarter.isoformat(),
                   "forecastOriginSessionClose": r.origin.isoformat()},
        "knownAtOrigin": {
            "ownPreviousQuarterRevenueLogGrowth": round(r.own, 4),
            "marketEarlyReporters": {"n": r.n_mkt, "meanRevenueLogGrowth": round(r.mkt, 4)},
            "industryEarlyReporters": [{"corp": c, "ticker": names.get(c, (None,))[0], "disclosed": d,
                                        "usableFromNextSessionClose": True, "revenueLogGrowth": round(v, 4)}
                                       for c, d, v in r.peers],
        },
        "eventualTarget": {"revenueLogGrowth": round(r.y, 4), "note": "disclosed after the origin; not available at the origin"},
        "predictions": primary_preds.get((r.corp, r.quarter.isoformat())),
    }


def predictions_for(rows, base, challenger, quarter_iso):
    """Re-run the expanding fit for one quarter to show the two forecasts behind the example."""
    usable = [r for r in rows if all(getattr(r, c) is not None for c in set(base) | set(challenger))]
    qi = T.quarter_index(date.fromisoformat(quarter_iso))
    train = [r for r in usable if T.quarter_index(r.quarter) <= qi - T.TRAIN_GAP_QUARTERS]
    test = [r for r in usable if r.quarter.isoformat() == quarter_iso]
    out = {}
    y = T.np.array([r.y for r in train])
    fits = {n: T.ols_fit(T.np.array([[getattr(r, c) for c in f] for r in train]), y)
            for n, f in (("B1", base), ("B2", challenger))}
    for r in test:
        out[(r.corp, quarter_iso)] = {n: round(float(T.ols_predict(fits[n], T.np.array([[getattr(r, c) for c in f]]))[0]), 4)
                                      for n, f in (("B1", base), ("B2", challenger))}
        out[(r.corp, quarter_iso)]["coefficientsB2"] = [round(float(c), 4) for c in fits["B2"]]
    return out


# --------------------------------------------------------------------------- main
def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--signal-history-dir", required=True)
    parser.add_argument("--out", default=str(HERE))
    parser.add_argument("--permutations", type=int, default=PERMUTATIONS)
    args = parser.parse_args(argv)
    src, out_dir = Path(args.signal_history_dir), Path(args.out)

    sessions = load_sessions()
    industry_at = load_industry()
    snaps = load_universe(src)
    collection = json.loads((src / "ledger/dart-ownership-events/collection-universe.json").read_text())
    corp_ticker = corp_tickers(collection)
    best, n_docs = parsed_docs()
    obs = build_obs(best, corp_ticker, industry_at, snaps)
    formal = formal_dates()

    attrition = {}
    rows = T.build_rows(obs, sessions, attrition=attrition)
    primary = T.oos_compare(rows, B1, B2)
    market = T.oos_compare(rows, B0, B1)
    op_rows = [r for r in rows if r.y_op is not None and r.own_op is not None and r.mkt_op is not None and r.ind_op is not None]
    op_secondary = T.oos_compare(op_rows, ("own_op", "mkt_op"), ("own_op", "mkt_op", "ind_op"), target="y_op")

    stale_rows = [r for r in rows if r.stale is not None]
    stale = T.oos_compare(stale_rows, B1, ("own", "mkt", "stale"))
    real_on_stale = T.oos_compare(stale_rows, B1, B2)
    both = T.oos_compare(stale_rows, ("own", "mkt", "stale"), ("own", "mkt", "stale", "ind"))

    ex_rows = [r for r in rows if r.ind_ex_largest is not None]
    ex_largest = T.oos_compare(ex_rows, B1, ("own", "mkt", "ind_ex_largest"))
    real_on_ex = T.oos_compare(ex_rows, B1, B2)

    tickers = {o.extra["ticker"] for o in obs if o.extra.get("ticker")}
    for snap in snaps.values():
        tickers |= {f"{c}.KS" for c, (rank, _) in snap.items() if rank is not None and rank <= 120}
    closes = load_closes(src, tickers)
    attach_indmom(rows, obs, snaps, industry_at, closes, sessions)
    mom_rows = [r for r in rows if r.indmom is not None]
    momentum = {"B1p_vs_B1": T.oos_compare(mom_rows, B1, ("own", "mkt", "indmom")),
                "B2p_vs_B1p": T.oos_compare(mom_rows, ("own", "mkt", "indmom"), ("own", "mkt", "indmom", "ind")),
                "B2_vs_B1_sameRows": T.oos_compare(mom_rows, B1, B2)}

    caps = sorted(r.market_cap for r in rows if r.market_cap)
    cut1, cut2 = (caps[len(caps) // 3], caps[2 * len(caps) // 3]) if caps else (None, None)
    size = {}
    for label, pred in (("small", lambda c: c < cut1), ("mid", lambda c: cut1 <= c < cut2), ("large", lambda c: c >= cut2)):
        size[label] = T.oos_compare([r for r in rows if r.market_cap and pred(r.market_cap)], B1, B2)
    by_industry = {}
    for g in sorted({r.industry for r in rows}):
        sub = [r for r in rows if r.industry == g]
        # industry-level delta = mean over evaluated rows of (e_B1^2 - e_B2^2), fits on the full sample
        by_industry[g] = industry_delta(rows, g)
        by_industry[g]["eligibleRows"] = len(sub)
    total = sum(v["sumSquaredErrorReduction"] for v in by_industry.values())
    for v in by_industry.values():
        v["shareOfTotalReduction"] = round(v["sumSquaredErrorReduction"] / total, 4) if total else None

    rng = random.Random(SEED)
    perm_deltas = []
    for _ in range(args.permutations):
        override = T.permuted_industries(obs, rng)
        prow = T.build_rows(obs, sessions, industry_override=override)
        perm_deltas.append(T.oos_compare(prow, B1, B2)["delta"]["mean"])
    observed = primary["delta"]["mean"]
    valid = [d for d in perm_deltas if d is not None]
    perm_p = (1 + sum(1 for d in valid if d >= observed)) / (len(valid) + 1) if observed is not None else None

    family = T.holm({"H1_B2_vs_B1": primary["delta"]["p"], "H2_return_contrast_H126": None})
    decision_h1 = T.decide_h1(primary, perm_p, stale["delta"]["mean"] if stale["delta"]["mean"] is not None else None,
                              family["H1_B2_vs_B1"])
    # the stale comparison is made on the stale-eligible subset against the real signal on the same rows
    stale_check = {"realOnSameRows": real_on_stale["delta"]["mean"], "stale": stale["delta"]["mean"],
                   "realExceedsStale": (real_on_stale["delta"]["mean"] or 0) > (stale["delta"]["mean"] or 0)}
    if decision_h1 == "KEEP" and not stale_check["realExceedsStale"]:
        decision_h1 = "INCONCLUSIVE"

    early_late = early_vs_late(obs, rows)
    h2 = h2_information(obs, formal, sessions, primary)
    preds = predictions_for(rows, B1, B2, "2024-03-31")
    example = dated_example(rows, obs, preds)
    table_path = evidence_tables(out_dir, rows, primary, obs, formal, sessions)
    contract_path = HERE / "h2_return_contract.json"

    results = {
        "studyId": "industry-information-transfer-v1",
        "evidenceClass": "OUTCOME_BLIND_FUNDAMENTAL_FORECASTING_ON_EXPOSED_KR_DISCLOSURES",
        "stockReturnsRead": 0, "dartCallsMade": 0,
        "pricesReadOnlyThroughForecastOrigin": True,
        "inputs": {"pr308Commit": PR308_COMMIT, "signalHistoryCommit": SIGNAL_HISTORY_COMMIT,
                   "preliminaryDocumentsRead": n_docs, "issuerQuartersWithConfirmedPrelim": len(obs),
                   "hashes": source_hashes(src)},
        "panel": panel_counts(obs, rows, attrition),
        "H1": {"primary_B2_vs_B1_revenue": strip(primary), "secondary_B2_vs_B1_operatingIncome": strip(op_secondary),
               "permutation": {"R": len(valid), "seed": SEED, "observedMeanDelta": observed,
                               "nullMean": statistics.mean(valid) if valid else None,
                               "nullP95": float(T.np.percentile(valid, 95)) if valid else None, "p": perm_p},
               "stalePlacebo": {"stale_vs_B1": strip(stale), "B2_vs_B1_sameRows": strip(real_on_stale),
                                "ind_given_stale": strip(both), "check": stale_check},
               "decision": decision_h1},
        "H2": {"information": h2, "returnContrast": {"status": "NOT_EXECUTED_PHASE_D_AUTHORIZATION_ABSENT",
                                                     "contract": str(contract_path.relative_to(ROOT)),
                                                     "contractSha256": sha256(contract_path) if contract_path.exists() else None,
                                                     "authorizationFilePresent": (HERE / "AUTHORIZATION.json").exists()},
               "decision": "DATA_BLOCKED"},
        "H3": {"marketWide_B1_vs_B0": strip(market), "sectorPriceMomentum": {k: strip(v) for k, v in momentum.items()},
               "largestPeerExcluded": {"exLargest_vs_B1": strip(ex_largest), "B2_vs_B1_sameRows": strip(real_on_ex)},
               "byTargetSizeTercile": {k: strip(v) for k, v in size.items()}, "byIndustry": by_industry,
               "earlyVsLateReporters": early_late},
        "family": family,
        "datedExample": example,
        "evidenceTable": table_path.name,
    }
    (out_dir / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1, sort_keys=True, default=str) + "\n")
    print(json.dumps({"H1": decision_h1, "delta": primary["delta"], "perm_p": perm_p, "holm": family}, default=str, indent=1))
    return 0


def strip(res: dict) -> dict:
    return {k: v for k, v in res.items() if k != "perQuarter"} | {
        "yearlyDeltaMean": yearly(res.get("perQuarter", []))}


def yearly(per_quarter):
    by = defaultdict(list)
    for p in per_quarter:
        by[p["quarter"][:4]].append(p["delta"])
    return {y: round(sum(v) / len(v), 6) for y, v in sorted(by.items())}


def industry_delta(rows, industry):
    usable = [r for r in rows if all(getattr(r, c) is not None for c in B2)]
    sq = []
    for q in sorted({r.quarter for r in usable}):
        qi = T.quarter_index(q)
        train = [r for r in usable if T.quarter_index(r.quarter) <= qi - T.TRAIN_GAP_QUARTERS]
        if len({r.quarter for r in train}) < T.MIN_TRAIN_QUARTERS:
            continue
        test = [r for r in usable if r.quarter == q and r.industry == industry]
        if not test:
            continue
        y = T.np.array([r.y for r in train])
        f1 = T.ols_fit(T.np.array([[getattr(r, c) for c in B1] for r in train]), y)
        f2 = T.ols_fit(T.np.array([[getattr(r, c) for c in B2] for r in train]), y)
        for r in test:
            e1 = r.y - float(T.ols_predict(f1, T.np.array([[getattr(r, c) for c in B1]]))[0])
            e2 = r.y - float(T.ols_predict(f2, T.np.array([[getattr(r, c) for c in B2]]))[0])
            sq.append(e1 * e1 - e2 * e2)
    return {"evaluatedRows": len(sq), "meanSquaredErrorReduction": round(sum(sq) / len(sq), 6) if sq else None,
            "sumSquaredErrorReduction": round(sum(sq), 6),
            "shareRowsImproved": round(sum(1 for x in sq if x > 0) / len(sq), 4) if sq else None}


def early_vs_late(obs, rows):
    """Within each quarter, early = first half of reporters by receipt date. Coverage and size only."""
    by_q = defaultdict(list)
    for o in obs:
        by_q[o.quarter].append(o)
    early_caps, late_caps, early_ind, late_ind = [], [], Counter(), Counter()
    for members in by_q.values():
        members = sorted(members, key=lambda o: (o.disclosed, o.corp))
        half = len(members) // 2
        for i, o in enumerate(members):
            (early_caps if i < half else late_caps).append(o.market_cap or 0)
            (early_ind if i < half else late_ind)[o.industry or "UNKNOWN"] += 1
    eligible = Counter(r.industry for r in rows)
    return {"medianMarketCapEarlyKRW": statistics.median([c for c in early_caps if c]) if early_caps else None,
            "medianMarketCapLateKRW": statistics.median([c for c in late_caps if c]) if late_caps else None,
            "industryCountsEarlyHalf": dict(early_ind.most_common()), "industryCountsLateHalf": dict(late_ind.most_common()),
            "eligibleTargetsByIndustry": dict(eligible.most_common())}


def panel_counts(obs, rows, attrition):
    return {"issuerQuarters": len(obs), "issuers": len({o.corp for o in obs}),
            "quarters": len({o.quarter for o in obs}),
            "withIndustry": sum(1 for o in obs if o.industry), "industries": len({o.industry for o in obs if o.industry}),
            "withRevenueTarget": sum(1 for o in obs if o.y is not None),
            "revenueTargetAtClip": sum(1 for o in obs if o.y is not None and abs(o.y) >= T.CLIP_REVENUE),
            "attrition": attrition, "eligibleRows": len(rows), "eligibleIssuers": len({r.corp for r in rows}),
            "eligibleQuarters": len({r.quarter for r in rows}), "eligibleIndustries": len({r.industry for r in rows}),
            "medianIndustryPeersAtOrigin": statistics.median([r.n_ind for r in rows]) if rows else None,
            "medianMarketPeersAtOrigin": statistics.median([r.n_mkt for r in rows]) if rows else None}


def source_hashes(src: Path) -> dict:
    files = {
        "pr308/prelim-docs-member-units.jsonl.gz": SPRINT / "data/prelim-docs-member-units.jsonl.gz",
        "pr308/sprint.py": SPRINT / "sprint.py",
        "v4/intervals.json.gz": ROOT / "data/kr-industry-membership-foundation-v4/state/intervals.json.gz",
        "v4/crosswalk.json": ROOT / "research_specs/kr-industry-membership-foundation-v4/crosswalk.json",
        "signal-history/collection-universe.json": src / "ledger/dart-ownership-events/collection-universe.json",
    }
    out = {k: sha256(v) for k, v in files.items()}
    out["pr308/dart-list-A-files"] = hashlib.sha256(b"".join(
        Path(f).name.encode() + sha256(f).encode() for f in sorted(glob.glob(str(SPRINT / "data/dart-list/*-A.jsonl.gz"))))).hexdigest()
    for f in sorted(glob.glob(str(src / "ledger/universe/kr/*.jsonl.gz"))) + sorted(glob.glob(str(src / "ledger/prices/kr/*.jsonl.gz"))):
        out["signal-history/" + str(Path(f).relative_to(src))] = sha256(f)
    return out


if __name__ == "__main__":
    raise SystemExit(main())
