"""Outcome-blind selection diagnostics of the REGISTERED v1 rule, plus a labeled latest-week dry run.

    python scripts/audit_us_capital_allocation_selection_diagnostics.py --workspace <dir> [--extract]

Reuses the committed coverage audit's loaders and the SAME `classify_member` / `member_evaluation` the weekly observation uses, so
the diagnostics describe exactly the registered rule. It reads no return, no price level, no label, no NAV, and it varies no
threshold: the registered v1 constants are imported, never edited. Per-date selected names are NOT written (a list of historical
picks is one `pandas.merge` away from a backtest, which this program has ruled out); only aggregates are.
"""
from __future__ import annotations

import argparse
import gzip
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import alpha_opportunity_v3_survivorship as V3      # noqa: E402
from pipeline import regional_alpha_features as RAF               # noqa: E402
from pipeline import replay_calendar as RC                        # noqa: E402
from pipeline import us_capital_allocation_coverage as C          # noqa: E402
from pipeline import us_capital_allocation_diagnostics as DG      # noqa: E402
from pipeline import us_capital_allocation_policy as POL          # noqa: E402
from pipeline import us_capital_allocation_receipts as RCPT       # noqa: E402
from pipeline import us_shareholder_distribution as U             # noqa: E402

_spec = importlib.util.spec_from_file_location("cov_audit", ROOT / "scripts/audit_us_capital_allocation_coverage.py")
A = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = A
_spec.loader.exec_module(A)

OUT = ROOT / "docs/us-readiness/us-capital-allocation-v1-selection-diagnostics-v1.json"
COMMITTED_COVERAGE = ROOT / "docs/us-readiness/us-capital-allocation-weekly-coverage-v1.json"
MEASURED_GATES = (None, POL.GATES[5], POL.GATES[6])


def build_context(workspace: Path):
    grouped, ciks, _, _ = A.load_filings(workspace, A.FUNDAMENTALS_COMMIT)
    source, _ = A.source_metadata(grouped)
    committed = json.loads(A.COMMITTED_220.read_text())
    if source.cumulative_evidence != committed["sourceMetadata"]["cumulativeEvidence"]:
        raise ValueError("SOURCE_METADATA_DIFFERS_FROM_THE_COMMITTED_220_AUDIT")
    engines = {t: U.FeatureEngine(t, rows, source) for t, rows in grouped.items()}
    prices, _ = A.load_price_presence()
    membership = RAF.MembershipSnapshots(json.loads(gzip.decompress(A.MEMBERSHIP.read_bytes()))["snapshots"])
    payload = json.loads(gzip.decompress(A.SECTORS.read_bytes()))
    category, malformed, renames, ambiguous = A.identity_tables()
    ctx = C.WeekContext(engines=engines, prices=prices, sectors=C.SectorBook(payload["snapshots"]), ciks=ciks, category=category,
                        malformed=malformed, renames=renames, ambiguous=ambiguous)
    dates = V3.weekly_grid(RC.sessions(RC.ORIGIN, "2026-09-25", "US"), A.THROUGH)
    return ctx, membership, dates


def measured_row(member, evaluation):
    f = member.snapshot.features
    pick = lambda name: f[name].value if f[name].state.value in ("VALID", "REPORTED_ZERO") else None     # noqa: E731
    return {"ticker": member.symbol, "sector": member.sector, "gate": evaluation["gate"], "score": evaluation["score"],
            "growth": f["totalCashDistributionChangeYoY"].value, "ratio": f["distributionToOCF"].value,
            "distribution": f["totalCashDistributionTTM"].value, "ocf": f["operatingCashFlowTTM"].value,
            "dividends": pick("cashDividendsPaidTTM"), "repurchases": pick("commonStockRepurchasesTTM"),
            "dividendYoY": pick("cashDividendsPaidTTMChangeYoY"), "repurchaseYoY": pick("repurchasesTTMChangeYoY")}


def run(workspace: Path, limit_dates=None):
    ctx, membership, dates = build_context(workspace)
    if limit_dates:
        dates = dates[::max(1, len(dates) // limit_dates)][:limit_dates]
    weeks, status_totals = [], Counter()
    for date in dates:
        snapshot = membership.on(date)
        evaluations, rows = [], []
        for raw in snapshot["members"]:
            member = C.classify_member(ctx, snapshot, date, raw)
            status_totals[member.status] += 1
            evaluation = C.member_evaluation(member)
            if evaluation is None:
                continue
            evaluations.append(evaluation)
            if evaluation["gate"] in MEASURED_GATES and member.snapshot is not None:
                rows.append(measured_row(member, evaluation))
        decision = POL.select(evaluations)
        weeks.append({"date": date, "decision": decision, "rows": rows, "members": len(snapshot["members"])})
    return ctx, membership, weeks, status_totals


def sector_table(weeks):
    live = [w for w in weeks if w["decision"]["status"] != "BLOCKED"]
    measured, passers, picked = Counter(), Counter(), Counter()
    for w in live:
        measured.update(r["sector"] for r in w["rows"])
        passers.update(p["sector"] for p in w["decision"]["passers"])
        picked.update(s["sector"] for s in w["decision"]["selected"])
    tm, tp, ts = sum(measured.values()), sum(passers.values()), sum(picked.values())
    out = {}
    for sector in sorted(set(measured) | set(passers)):
        share_m = measured[sector] / tm if tm else 0
        out[sector] = {"meanMeasuredPerWeek": round(measured[sector] / len(live), 3), "meanPassersPerWeek": round(passers[sector] / len(live), 3),
                       "shareOfMeasured": round(share_m, 4), "shareOfPassers": round(passers[sector] / tp, 4) if tp else 0,
                       "shareOfSelectedSlots": round(picked[sector] / ts, 4) if ts else 0,
                       "selectedOverMeasuredShare": round((picked[sector] / ts) / share_m, 3) if ts and share_m else None}
    return out


def year_table(weeks):
    by = defaultdict(list)
    for w in weeks:
        by[w["date"][:4]].append(w)
    out = {}
    for year, items in sorted(by.items()):
        live = [w for w in items if w["decision"]["status"] != "BLOCKED"]
        counts = [len(w["decision"]["passers"]) for w in live]
        measured = [w["decision"]["funnel"]["measured"] for w in items]
        out[year] = {"weeks": len(items), "blockedWeeks": len(items) - len(live), "measuredNamesMedian": DG._stats(measured)["median"],
                     "passersPerLiveWeek": DG._stats(counts), "namesSelected": dict(sorted(Counter(len(w["decision"]["selected"]) for w in live).items()))}
    return out


def gate_table(weeks):
    live = [w for w in weeks if w["decision"]["status"] != "BLOCKED"]
    failed = Counter()
    for w in live:
        failed.update(w["decision"]["funnel"]["failedAt"])
    evaluated = sum(w["decision"]["funnel"]["evaluated"] for w in live)
    passed = sum(w["decision"]["funnel"]["passed"] for w in live)
    reach, out = evaluated, {}
    for gate in POL.GATES:
        out[gate] = {"reached": reach, "eliminated": failed[gate], "eliminatedShareOfReached": round(failed[gate] / reach, 4) if reach else None,
                     "shareOfAllEliminations": round(failed[gate] / (evaluated - passed), 4) if evaluated > passed else None}
        reach -= failed[gate]
    out["PASSED_EVERY_GATE"] = {"reached": reach, "shareOfEvaluated": round(passed / evaluated, 4) if evaluated else None}
    return out


class _AlwaysFresh:
    """Stand-in price book for ONE counterfactual question: were the price gate not binding, how ready is the fundamentals side?"""

    def status(self, ticker, date):
        return "OK", 10**6


def source_ages(ctx, membership, as_of, generated_on):
    import numpy as np
    day = np.datetime64(as_of)
    last_price = max(dates[-1] for dates in ctx.prices._dates.values())
    last_filing = max(f.visible_day for e in ctx.engines.values() for f in e._filings if f.visible_day < U.parse_day(as_of))
    snaps = membership.snapshots
    gaps = [(np.datetime64(b["date"]) - np.datetime64(a["date"])).astype(int) for a, b in zip(snaps, snaps[1:])]
    prior = membership.on(as_of)
    age = lambda d: int((day - np.datetime64(d)).astype(int))      # noqa: E731
    return {
        "asOfSession": as_of, "generatedOn": generated_on,
        "prices": {"lastObservedSession": last_price, "ageDays": age(last_price), "registeredMaxAgeDays": POL.MAX_PRICE_AGE_DAYS,
                   "status": "FRESH" if age(last_price) <= POL.MAX_PRICE_AGE_DAYS else "STALE",
                   "provenance": "replay-v16 sealed price panels (Yahoo unadjusted + actions); there is no in-repo US price collection after the seal"},
        "membership": {"snapshotUsed": prior["date"], "snapshotPublishedAt": prior.get("publishedAt"), "sourceCommit": prior["sourceCommit"],
                       "ageDays": age(prior["date"]), "historicalSnapshotGapDays": {"median": float(np.median(gaps)), "max": int(max(gaps))},
                       "status": "AGED_NO_REGISTERED_LIMIT",
                       "provenance": "research_specs/alpha-opportunity-model-v1-us-membership.json.gz (datasets/s-and-p-500-companies); no refresh job exists"},
        "fundamentals": {"latestVisibleFiling": str(last_filing), "ageDays": age(str(last_filing)), "status": "FRESH",
                         "provenance": "signal-history@%s Finnhub shards (collected daily by fundamentals.yml)" % A.FUNDAMENTALS_COMMIT[:8]},
    }


def current_input_attempt(ctx, membership, as_of, generated_on):
    """ONE bounded attempt to apply the registered rule to the latest completed session, with the inputs that actually exist."""
    import dataclasses
    ages = source_ages(ctx, membership, as_of, generated_on)
    snapshot = membership.on(as_of)

    def week(c):
        rows = [C.classify_member(c, snapshot, as_of, raw) for raw in snapshot["members"]]
        evaluations = [e for e in (C.member_evaluation(r) for r in rows) if e is not None]
        return rows, POL.select(evaluations)

    rows, decision = week(ctx)
    counts = Counter(r.status for r in rows)
    fresh_rows, fresh_decision = week(dataclasses.replace(ctx, prices=_AlwaysFresh()))
    return {
        "label": "CURRENT_INPUT_ATTEMPT_BLOCKED_NOT_A_SIGNAL" if decision["status"] == "BLOCKED" else "CURRENT_INPUT_DRY_RUN_NOT_A_SIGNAL",
        "notAReceipt": True, "notIndependentEvidence": True, "inputs": ages,
        "result": {"status": decision["status"], "reasons": decision["reasons"], "membersEvaluated": len(rows), "statusCounts": dict(sorted(counts.items())),
                   "measuredNames": decision["funnel"]["measured"], "selected": len(decision["selected"]), "weights": decision["weights"],
                   "residualSPYWeight": 1.0 if decision["weights"] is None else decision["fallbackWeight"]},
        "fundamentalsSideIfPricesWereFresh": {
            "question": "if the price-freshness gate were not binding, how many names would the fundamentals side measure on the as-of session?",
            "measuredNames": fresh_decision["funnel"]["measured"], "jointMeasured": sum(1 for r in fresh_rows if r.status == C.JOINT_MEASURED),
            "reportStale": sum(1 for r in fresh_rows if r.status == C.REPORT_STALE),
            "note": "a count only; no name is listed because no valid price evidence exists for this session"},
        "blocker": "NO_FRESH_US_PRICES: the newest sealed close is %s (%d days before the as-of session; the registered limit is %d). Using it as "
                   "though it were current would be the stale-input error AGENTS.md forbids." % (
                       ages["prices"]["lastObservedSession"], ages["prices"]["ageDays"], POL.MAX_PRICE_AGE_DAYS)
                   if ages["prices"]["status"] == "STALE" else None,
    }


def latest_sealed_week_counts(weeks):
    """Counts only for the last sealed week (2026-09-11). Not current, not a dry run, no names."""
    week = weeks[-1]
    decision = week["decision"]
    return {"label": "LATEST_SEALED_WEEK_COUNTS_NOT_CURRENT", "signalDate": week["date"], "status": decision["status"],
            "measuredNames": decision["funnel"]["measured"], "passers": len(decision["passers"]), "selected": len(decision["selected"])}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--extract", action="store_true")
    parser.add_argument("--limit-dates", type=int)
    parser.add_argument("--as-of", default="2026-10-09", help="the last completed US session before the run")
    parser.add_argument("--generated-on", default="2026-10-11")
    args = parser.parse_args(argv)
    if not RCPT.is_weekly_decision_session(args.as_of):
        raise ValueError("AS_OF_IS_NOT_A_COMPLETED_WEEKLY_DECISION_SESSION")
    if args.extract:
        A.extract(args.workspace, A.FUNDAMENTALS_COMMIT)
    ctx, membership, weeks, status_totals = run(args.workspace, args.limit_dates)
    decisions = [(w["date"], w["decision"]) for w in weeks]
    live_weeks = [w for w in weeks if w["decision"]["status"] != "BLOCKED"]
    committed = json.loads(COMMITTED_COVERAGE.read_text())["summary"]
    if not args.limit_dates:
        if dict(status_totals) != {k: v for k, v in committed["funnelCounts"].items() if v}:
            raise ValueError("FUNNEL_DIFFERS_FROM_THE_COMMITTED_COVERAGE_AUDIT")
    report = {
        "id": "us-capital-allocation-v1-selection-diagnostics-v1", "evidenceClass": "OUTCOME_BLIND_RULE_DIAGNOSTIC",
        "readsReturns": False, "readsLabels": False, "readsPriceLevels": False, "fitsModels": False, "variesThresholds": False,
        "registeredRule": {"policyVersion": POL.POLICY_VERSION, "designDigest": POL.design_digest()},
        "weeks": len(weeks), "funnelReproducesCommittedCoverageAudit": not args.limit_dates,
        "byYear": year_table(weeks), "bySector": sector_table(weeks), "gates": gate_table(weeks),
        "decisions": DG.decision_diagnostics(decisions), "margins": DG.margins(decisions),
        "scoreConstruction": DG.score_construction(weeks), "selectedComposition": DG.selected_composition(weeks),
        "passerPersistence": DG.passer_persistence(live_weeks), "accountingVsExpectedReturn": DG.explainer(),
        "latestSealedWeek": latest_sealed_week_counts(weeks),
        "currentInputAttempt": current_input_attempt(ctx, membership, args.as_of, args.generated_on),
        "noThresholdSweep": "no alternative threshold was evaluated; the registered v1 constants are the only ones used",
    }
    if args.limit_dates:
        print(json.dumps(report["currentInputAttempt"], indent=1))
        return 0
    OUT.write_text(json.dumps(report, indent=1, sort_keys=True, allow_nan=False, ensure_ascii=False) + "\n", encoding="utf-8")
    print("weeks %d, live %d, written %s" % (len(weeks), len(live_weeks), OUT.relative_to(ROOT)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
