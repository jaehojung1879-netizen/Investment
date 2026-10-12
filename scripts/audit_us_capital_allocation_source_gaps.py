"""Source-gap diagnosis for the 17.9% joint-coverage limit. Outcome-blind, research-only, no new acquisition.

    python scripts/audit_us_capital_allocation_source_gaps.py --workspace <dir> [--limit-dates N]

Reads the same pinned `signal-history` Finnhub shards as the committed coverage audit and the sealed price/membership/identity
inputs. It computes no return and reads no label. It answers three questions with counts:

1. WHERE do the member-dates go? Why a feature is not measured (the first blocking feature, its state, and the filing-level reason).
2. WHICH legitimate source repair exists? A candidate VIEW (`pipeline/us_capital_allocation_source_views.py`) accepts a documented,
   narrower set of filing contexts; the SAME #220 engine and the SAME weekly classifier then re-measure coverage. v1 is untouched.
3. WHAT cannot be repaired from this store? Departed-member price panels, period-end share counts, SEC XBRL contexts.

Nothing is filled with zero. A candidate view's improvement is an UPPER BOUND until the SEC XBRL contexts are verified.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import finnhub_fundamentals as FF                   # noqa: E402
from pipeline import regional_alpha_features as RAF               # noqa: E402
from pipeline import us_capital_allocation_coverage as C          # noqa: E402
from pipeline import us_capital_allocation_source_views as V      # noqa: E402
from pipeline import us_shareholder_distribution as U             # noqa: E402

_spec = importlib.util.spec_from_file_location("cov_audit", ROOT / "scripts/audit_us_capital_allocation_coverage.py")
A = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = A
_spec.loader.exec_module(A)

OUT = ROOT / "docs/us-readiness/us-capital-allocation-source-gap-diagnosis-v1.json"

# Concepts whose per-year availability is reported. Section is where Finnhub's flattened statement carries it.
CONCEPT_GROUPS = {
    "cashDividendsExactCommon": ("cf", {"PaymentsOfDividendsCommonStock"}),
    "cashDividendsGeneral": ("cf", {"PaymentsOfDividends"}),
    "cashDividendsOrdinary": ("cf", {"PaymentsOfOrdinaryDividends"}),
    "repurchasesExactCommon": ("cf", {"PaymentsForRepurchaseOfCommonStock"}),
    "repurchasesEquityGeneral": ("cf", {"PaymentsForRepurchaseOfEquity"}),
    "operatingCashFlowExact": ("cf", {"NetCashProvidedByUsedInOperatingActivities"}),
    "operatingCashFlowContinuingOnly": ("cf", {"NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"}),
    "capexExact": ("cf", {"PaymentsToAcquirePropertyPlantAndEquipment"}),
    "periodEndCommonShares": ("bs", {"CommonStockSharesOutstanding"}),
    "weightedAverageDilutedShares": ("ic", {"WeightedAverageNumberOfDilutedSharesOutstanding"}),
    "weightedAverageBasicShares": ("ic", {"WeightedAverageNumberOfSharesOutstandingBasic", "WeightedAverageNumberOfBasicSharesOutstanding"}),
    "epsDiluted": ("ic", {"EarningsPerShareDiluted"}),
    "epsBasic": ("ic", {"EarningsPerShareBasic"}),
    "revenue": ("ic", {"Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet",
                       "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueGoodsNet"}),
    "operatingIncome": ("ic", {"OperatingIncomeLoss"}),
    "netIncome": ("ic", {"NetIncomeLoss", "ProfitLoss"}),
    "stockholdersEquity": ("bs", {"StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"}),
    "totalAssets": ("bs", {"Assets"}),
    "dividendPerShareDeclared": ("ic", {"CommonStockDividendsPerShareDeclared", "CommonStockDividendsPerShareCashPaid"}),
}
DIVIDEND_NAMES = re.compile(r"ividend", re.I)
REPURCHASE_NAMES = re.compile(r"repurchase|treasurystock|buyback|retirement", re.I)


def iter_raw(workspace: Path):
    """Raw shard records, blob-hash verified exactly as the coverage audit's loader does."""
    declared = json.loads((workspace / "source-manifest.json").read_text())
    if declared["commit"] != A.FUNDAMENTALS_COMMIT:
        raise ValueError("SOURCE_COMMIT_MISMATCH")
    expected = {Path(f["path"]).name: f for f in declared["files"]}
    for path in sorted(workspace.glob("finnhub-*.jsonl.gz")):
        blob = path.read_bytes()
        if hashlib.sha1(b"blob " + str(len(blob)).encode() + b"\0" + blob).hexdigest() != expected[path.name]["gitBlob"]:
            raise ValueError("SOURCE_BLOB_MISMATCH: " + path.name)
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    yield json.loads(line)


def census(workspace: Path):
    """One pass over the raw filings: timestamps, concept availability by year, concept-name inventory, view decisions, view groups."""
    cutoff = U.parse_day(A.CUTOFF)
    years = defaultdict(lambda: Counter())
    names = {"dividend": Counter(), "repurchase": Counter()}
    lags, accept_gap = [], []
    dividend_codes, ocf_codes = Counter(), Counter()
    dividend_codes_by_year = defaultdict(Counter)
    totals = Counter()
    base_grouped, view_grouped, alias_only = defaultdict(list), defaultdict(list), defaultdict(list)
    ciks = defaultdict(list)
    prepare_errors = Counter()
    forms = Counter()
    for record in iter_raw(workspace):
        available, accepted = U.parse_day(record.get("availableFrom")), U.parse_day(record.get("acceptedDate"))
        visible = max(available, accepted) if available and accepted else available
        if not visible or visible >= cutoff:
            continue
        year = str(visible.year)
        totals["filings"] += 1
        totals["withAcceptedDate"] += bool(accepted)
        forms[str(record.get("form"))] += 1
        if accepted and available:
            accept_gap.append((accepted - available).days)
        end = U.parse_day(record.get("periodEnd"))
        if end:
            lags.append((visible - end).days)
        years[year]["filings"] += 1
        for group, (section, concepts) in CONCEPT_GROUPS.items():
            present = any(FF.strip_namespace(e.get("concept")) in concepts for e in record.get("statements", {}).get(section, []))
            years[year][group] += bool(present)
        for e in record.get("statements", {}).get("cf", []):
            concept = FF.strip_namespace(e.get("concept")) or ""
            if DIVIDEND_NAMES.search(concept):
                names["dividend"][concept] += 1
            if REPURCHASE_NAMES.search(concept):
                names["repurchase"][concept] += 1
        view, codes = V.candidate_view(record)
        dividend_codes[codes["dividends"]] += 1
        dividend_codes_by_year[year][codes["dividends"]] += 1
        ocf_codes[codes["ocf"]] += 1
        projected = A.A220._project(record)
        base_grouped[record["ticker"]].append(projected)
        view_projected = A.A220._project(view)
        view_grouped[record["ticker"]].append(view_projected)
        if codes["dividends"] == V.DIVIDEND_ACCEPT:
            alias_only[record["ticker"]].append(view_projected)
        if record.get("cik"):
            ciks[record["ticker"]].append((visible, str(int(record["cik"]))))
        prepared = U._prepare(projected)
        if prepared is not None and prepared.error:
            prepare_errors[prepared.error] += 1
        elif prepared is None:
            prepare_errors["UNDATED"] += 1
    return dict(years=years, names=names, lags=lags, accept_gap=accept_gap, dividend_codes=dividend_codes, ocf_codes=ocf_codes,
                dividend_codes_by_year=dividend_codes_by_year, totals=totals, base=base_grouped, view=view_grouped, alias_only=alias_only,
                ciks=ciks, prepare_errors=prepare_errors, forms=forms)


def quantiles(values):
    import numpy as np
    if not values:
        return None
    a = np.asarray(values, dtype=float)
    return {"n": int(len(a)), "min": int(a.min()), "p10": float(np.quantile(a, .1)), "median": float(np.median(a)),
            "p90": float(np.quantile(a, .9)), "max": int(a.max())}


def reason_of(snapshot):
    """First blocking required feature: (feature, state, filing-level reason)."""
    for name in C.REQUIRED:
        feature = snapshot.features[name]
        if feature.value is None:
            return name, feature.state.value, feature.reason
    if snapshot.features["operatingCashFlowTTM"].value <= 0:
        return "operatingCashFlowTTM", "NONPOSITIVE_OCF", "NONPOSITIVE_OCF"
    return None


def build_engines(grouped, source):
    return {t: U.FeatureEngine(t, rows, source) for t, rows in grouped.items()}


def weekly_pass(ctx_base, ctx_view, membership, dates):
    members_last = set(membership.snapshots[-1]["members"])
    base, view = Counter(), Counter()
    by_year = defaultdict(lambda: {"base": Counter(), "view": Counter()})
    reasons_base, reasons_view = Counter(), Counter()
    newly = Counter()
    newly_by_year, newly_by_sector, newly_companies = Counter(), Counter(), set()
    price_gap = {"departed": Counter(), "current": Counter()}
    ambiguous_reasons = Counter()
    eligible_not_measured = Counter()
    for date in dates:
        snapshot = membership.on(date)
        year = date[:4]
        for raw in snapshot["members"]:
            b = C.classify_member(ctx_base, snapshot, date, raw)
            v = C.classify_member(ctx_view, snapshot, date, raw)
            base[b.status] += 1
            view[v.status] += 1
            by_year[year]["base"][b.status] += 1
            by_year[year]["view"][v.status] += 1
            if b.status == C.NO_PRICE_PANEL:
                price_gap["current" if b.symbol in members_last else "departed"][year] += 1
            if b.status == C.IDENTITY_AMBIGUOUS:
                ambiguous_reasons[b.reason] += 1
            if b.status == C.FEATURES_NOT_MEASURED and b.snapshot is not None:
                reasons_base[reason_of(b.snapshot)] += 1
            if v.status == C.FEATURES_NOT_MEASURED and v.snapshot is not None:
                reasons_view[reason_of(v.snapshot)] += 1
            if b.status == C.JOINT_MEASURED and v.status != C.JOINT_MEASURED:
                newly["LOST_UNDER_VIEW"] += 1
            if v.status == C.JOINT_MEASURED and b.status != C.JOINT_MEASURED:
                newly["GAINED"] += 1
                newly_by_year[year] += 1
                newly_by_sector[b.sector] += 1
                newly_companies.add(b.symbol)
                if b.status == C.FEATURES_NOT_MEASURED and b.snapshot is not None:
                    newly["gainedFirstBlocker:%s:%s" % reason_of(b.snapshot)[:2]] += 1
            if b.status in (C.FEATURES_NOT_MEASURED, C.JOINT_MEASURED, C.REPORT_STALE):
                eligible_not_measured[b.status] += 1
    return dict(base=base, view=view, by_year=by_year, reasons_base=reasons_base, reasons_view=reasons_view, newly=newly,
                newly_by_year=newly_by_year, newly_by_sector=newly_by_sector, newly_companies=newly_companies,
                price_gap=price_gap, ambiguous=ambiguous_reasons, filing_eligible=sum(eligible_not_measured.values()))


def pct(n, d):
    return round(100.0 * n / d, 4) if d else None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--extract", action="store_true")
    parser.add_argument("--limit-dates", type=int)
    args = parser.parse_args(argv)
    if args.extract:
        A.extract(args.workspace, A.FUNDAMENTALS_COMMIT)
    cen = census(args.workspace)
    source, _ = A.source_metadata(cen["base"])
    committed = json.loads(A.COMMITTED_220.read_text())
    if source.cumulative_evidence != committed["sourceMetadata"]["cumulativeEvidence"]:
        raise ValueError("SOURCE_METADATA_DIFFERS_FROM_THE_COMMITTED_220_AUDIT")
    # Does the accepted general-dividend alias behave like a cumulative fiscal-YTD flow, as the exact concept does?
    alias_semantics = A.A220._semantics(cen["alias_only"]) if cen["alias_only"] else {}
    prices, _ = A.load_price_presence()
    membership = RAF.MembershipSnapshots(json.loads(gzip.decompress(A.MEMBERSHIP.read_bytes()))["snapshots"])
    payload = json.loads(gzip.decompress(A.SECTORS.read_bytes()))
    category, malformed, renames, ambiguous = A.identity_tables()
    common = dict(prices=prices, sectors=C.SectorBook(payload["snapshots"]), ciks=cen["ciks"], category=category, malformed=malformed,
                  renames=renames, ambiguous=ambiguous)
    ctx_base = C.WeekContext(engines=build_engines(cen["base"], source), **common)
    ctx_view = C.WeekContext(engines=build_engines(cen["view"], source), **common)
    from pipeline import alpha_opportunity_v3_survivorship as V3
    from pipeline import replay_calendar as RC
    dates = V3.weekly_grid(RC.sessions(RC.ORIGIN, "2026-09-25", "US"), A.THROUGH)
    if args.limit_dates:
        dates = dates[::max(1, len(dates) // args.limit_dates)][:args.limit_dates]
    wk = weekly_pass(ctx_base, ctx_view, membership, dates)
    n = sum(wk["base"].values())
    v3 = json.loads(A.V3_AUDIT.read_text())["regions"]["US"]
    coverage_by_year = {}
    for year, item in sorted(cen["years"].items()):
        f = item["filings"]
        coverage_by_year[year] = {"filings": f, **{g: pct(item[g], f) for g in CONCEPT_GROUPS}}
    result = {
        "id": "us-capital-allocation-source-gap-diagnosis-v1", "evidenceClass": "OUTCOME_BLIND_SOURCE_GAP_DIAGNOSIS",
        "readsReturns": False, "readsLabels": False, "fitsModels": False, "newAcquisition": False,
        "inputs": {"fundamentalsCommit": A.FUNDAMENTALS_COMMIT, "cutoff": A.CUTOFF, "filingsVisible": cen["totals"]["filings"],
                   "formCensus": dict(cen["forms"]), "weeksEvaluated": len(dates), "memberDates": n,
                   "limited": bool(args.limit_dates)},
        "baselineFunnel": dict(wk["base"]), "baselineJointMeasuredPct": pct(wk["base"][C.JOINT_MEASURED], n),
        "baselineJointMeasuredOfFilingEligiblePct": pct(wk["base"][C.JOINT_MEASURED], wk["filing_eligible"]),
        "whyNotMeasured": {"firstBlockingFeature": {"%s | %s | %s" % k: v for k, v in wk["reasons_base"].most_common(25)},
                           "memberDatesNotMeasured": wk["base"][C.FEATURES_NOT_MEASURED]},
        "timestamps": {"filingsWithAcceptedDate": cen["totals"]["withAcceptedDate"], "filings": cen["totals"]["filings"],
                       "acceptedDatePct": pct(cen["totals"]["withAcceptedDate"], cen["totals"]["filings"]),
                       "periodEndToVisibleDays": quantiles(cen["lags"]), "acceptedMinusAvailableFromDays": quantiles(cen["accept_gap"]),
                       "visibilityRule": "max(availableFrom, acceptedDate), strictly before the signal date; a missing acceptedDate falls back to availableFrom",
                       "engineRejectedFilings": dict(cen["prepare_errors"])},
        "conceptAvailabilityByVisibleYearPct": coverage_by_year,
        "conceptNameInventory": {"dividendLikeCashFlowConcepts": dict(cen["names"]["dividend"].most_common(15)),
                                 "repurchaseLikeCashFlowConcepts": dict(cen["names"]["repurchase"].most_common(15))},
        "candidateView": {
            "version": V.CANDIDATE_VERSION, "evidence": V.EVIDENCE_LABEL, "frozenV1Untouched": True,
            "rules": {"dividends": "PaymentsOfDividends is read as the common-stock total ONLY when the cash flow has no preferred/non-controlling/"
                                   "partnership dividend line, the line label names no other holder, no preferred stock is outstanding on any face statement, "
                                   "and no conflicting general concept exists. PaymentsOfOrdinaryDividends alone is rejected (excludes special dividends).",
                      "operatingCashFlow": "The continuing-operations total is read as operating cash flow ONLY when the filing has no discontinued-operations "
                                           "operating line. Everything else stays AMBIGUOUS_ACCOUNTING."},
            "dividendDecisions": dict(cen["dividend_codes"]), "operatingCashFlowDecisions": dict(cen["ocf_codes"]),
            "dividendDecisionsByYear": {y: dict(c) for y, c in sorted(cen["dividend_codes_by_year"].items())},
            "aliasCumulativeSemantics": alias_semantics,
            "coverageUnderView": {"funnel": dict(wk["view"]), "jointMeasuredPct": pct(wk["view"][C.JOINT_MEASURED], n),
                                  "gainedMemberDates": wk["newly"]["GAINED"], "lostMemberDates": wk["newly"]["LOST_UNDER_VIEW"],
                                  "gainedCompanies": len(wk["newly_companies"]), "gainedByYear": dict(sorted(wk["newly_by_year"].items())),
                                  "gainedBySector": dict(wk["newly_by_sector"].most_common()),
                                  "gainedFirstBlockerInBaseline": {k.split(":", 1)[1]: v for k, v in wk["newly"].items() if k.startswith("gainedFirstBlocker")},
                                  "remainingFirstBlockingFeature": {"%s | %s | %s" % k: v for k, v in wk["reasons_view"].most_common(15)},
                                  "byYear": {y: {"baselineJointPct": pct(d["base"][C.JOINT_MEASURED], sum(d["base"].values())),
                                                 "viewJointPct": pct(d["view"][C.JOINT_MEASURED], sum(d["view"].values()))}
                                             for y, d in sorted(wk["by_year"].items())}},
            "reading": "an upper bound on source repair: the view is store evidence, not SEC context verification, and it is a NEW versioned definition, not a v1 fix",
        },
        "priceAndIdentity": {
            "noPricePanelMemberDates": {"departedMembers": sum(wk["price_gap"]["departed"].values()), "currentMembers": sum(wk["price_gap"]["current"].values()),
                                        "byYearDeparted": dict(sorted(wk["price_gap"]["departed"].items()))},
            "identityAmbiguousMemberDates": sum(wk["ambiguous"].values()), "identityAmbiguousReasons": dict(wk["ambiguous"].most_common()),
            "sealedSurvivorshipAudit": {k: v3["sampleSurvivorship"][k] for k in ("noPanelDeparted", "noPanelCurrent", "departedPricedByOwnHistory",
                                                                                 "departedPricedViaVerifiedRename", "departedExitIdentityUnresolved")},
            "terminations": v3["terminations"], "membershipSnapshots": v3["membershipSnapshots"],
            "reading": "every missing price panel is a departed member: the sealed price source (Yahoo) does not serve delisted US tickers, so exactly the "
                       "names that later failed or were acquired are absent. This is a survivorship-correlated gap that no filing-side repair can fix",
        },
        "blocked": {"secXbrlContext": "BLOCKED_NETWORK_POLICY: data.sec.gov and www.sec.gov return 403 at the proxy; no instance-level context (dimension members, "
                                      "period-end share counts, share class) can be read here",
                    "periodEndShareCounts": "BLOCKED: %s%% of visible filings carry a period-end common-share fact in the flattened store; the cover-page (dei) "
                                            "count and the XBRL class/split context are absent" % pct(
                                                sum(c["periodEndCommonShares"] for c in cen["years"].values()), cen["totals"]["filings"]),
                    "dilutionFeature": "BLOCKED for every ticker pair: no SharesBasisEvidence"},
    }
    if args.limit_dates:
        print(json.dumps({k: result[k] for k in ("baselineJointMeasuredPct", "candidateView")}, indent=1)[:2500])
        return 0
    OUT.write_text(json.dumps(result, indent=1, sort_keys=True, allow_nan=False, ensure_ascii=False) + "\n", encoding="utf-8")
    print("member-dates %d baseline joint %s%% view joint %s%% -> %s" % (
        n, result["baselineJointMeasuredPct"], result["candidateView"]["coverageUnderView"]["jointMeasuredPct"], OUT.relative_to(ROOT)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
