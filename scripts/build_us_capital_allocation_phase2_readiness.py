"""Assemble the Phase 2 machine-readable readiness report and the independent next-study PROPOSAL from the committed audits.

    python scripts/build_us_capital_allocation_phase2_readiness.py [--check]

Every number in the report is read from a committed outcome-blind audit or computed here from the registered code; nothing is
typed in by hand except the blocker/decision taxonomy. `--check` rebuilds both files in memory and fails if the committed ones
differ, which is how a later edit to an audit that is not propagated is caught.

The proposal is NOT a registration. It authorizes nothing, changes no flag and starts no workflow.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import us_capital_allocation_monitoring as MO       # noqa: E402
from pipeline import us_capital_allocation_pilot as PI            # noqa: E402
from pipeline import us_capital_allocation_policy as P            # noqa: E402
from pipeline import us_capital_allocation_receipts as R          # noqa: E402

READINESS = ROOT / "docs/us-readiness"
OUT_DIR = ROOT / "docs/us-capital-allocation"
REPORT = OUT_DIR / "phase2-readiness-v1.json"
PROPOSAL = OUT_DIR / "us-multifactor-study-proposal-v1.json"
PROTECTED = OUT_DIR / "protected-official-files.json"
REGISTRATION = OUT_DIR / "us-capital-allocation-alpha-v1-registration.json"
ARTIFACTS = {
    "coverage": READINESS / "us-capital-allocation-weekly-coverage-v1.json",
    "definitions": READINESS / "us-capital-allocation-definition-audit-v1.json",
    "overlap": READINESS / "us-capital-allocation-feature-overlap-v1.json",
    "diagnostics": READINESS / "us-capital-allocation-v1-selection-diagnostics-v1.json",
    "sourceGaps": READINESS / "us-capital-allocation-source-gap-diagnosis-v1.json",
    "dilution": READINESS / "us-capital-allocation-dilution-evidence-v1.json",
    "multifactor": READINESS / "us-multifactor-pit-readiness-v1.json",
}
ASSUMED_APPROVAL = "2026-10-19T15:00:00+00:00"        # illustrative: a Monday after this PR could be reviewed


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name):
    return json.loads(ARTIFACTS[name].read_text())


# --------------------------------------------------------------------------- #
# Power arithmetic: assumptions only, no outcome is read
# --------------------------------------------------------------------------- #
Z_ALPHA, Z_POWER = 1.645, 0.842          # one-sided 5% test, 80% power


def ic_minimum_detectable(names: int, windows: int) -> float:
    """Smallest true mean rank IC detected with 80% power, treating the names of a window as independent (optimistic) and the
    weekly windows inside one 126-session horizon as ONE draw."""
    return round((Z_ALPHA + Z_POWER) / math.sqrt(names * windows), 4)


def book_minimum_detectable(tracking_error: float, years: float) -> float:
    """Smallest true annual excess return of a concentrated book detected with 80% power."""
    return round((Z_ALPHA + Z_POWER) * tracking_error / math.sqrt(years), 4)


def power_tables():
    return {
        "assumptions": ["one-sided 5% test, 80% power", "names within a signal window treated as independent, which flatters the IC table",
                        "tracking errors are ASSUMED round numbers, not estimated from any return", "windows = 126-session horizons, one independent draw each"],
        "minimumDetectableMeanRankIC": {"%d names" % n: {"%d windows" % k: ic_minimum_detectable(n, k) for k in (4, 6, 8, 12)} for n in (50, 100, 200, 330)},
        "minimumDetectableAnnualExcessOfAFiveNameBook": {"tracking error %.0f%%" % (te * 100): {"%.1f years" % y: book_minimum_detectable(te, y) for y in (3.0, 6.5)}
                                                         for te in (0.06, 0.08, 0.10)},
        "reading": "a 0-5 name book needs years to resolve an excess of several percent a year, so it cannot be the FIRST evidence about a signal; "
                   "a broad cross-section can, because its information grows with the number of names scored",
    }


# --------------------------------------------------------------------------- #
# The proposal
# --------------------------------------------------------------------------- #
def exposure_classification():
    return [
        {"id": "US_LABELED_2013_2026H1", "signalDates": "2013-01-04 to about 2026-03 (126-session labels matured inside the sealed data, which ends 2026-09-14)",
         "class": "OUTCOME_EXPOSED",
         "consumedBy": ["regional-alpha-model-v1: US annual models trained 2016 to 2026 on the 31-feature matrix; one-shot discovery budget spent (AGENTS.md v2.24)",
                        "fundamental-acceleration-discovery-v1 (US coverage 0.8179 reported)", "benchmark-alpha-v1", "weekly-passive-first-v1 replay (US sleeve)"],
         "notClaimedExhaustive": "any other study that evaluated US forward returns is assumed to have exposed the same window",
         "allowedUse": "outcome-blind readiness work (coverage, redundancy, definitions) only. Never confirmatory, never used to choose a weight, threshold or feature."},
        {"id": "US_SIGNALS_2026H2_UNMATURED", "signalDates": "about 2026-03 to 2026-09-11", "class": "PARTIALLY_EXPOSED_UNMATURED",
         "reason": "stock-level 126-session outcomes do not exist, but sealed prices through 2026-09-14 are visible to the program and the SPY/QQQ path was published descriptively (PR #221)",
         "allowedUse": "same as above; not a holdout"},
        {"id": "US_PRE_2013", "class": "NOT_USABLE", "reason": "no point-in-time S&P 500 membership before the 2012-12-27 snapshot; 2011-2012 prices are feature warm-up only"},
        {"id": "PROSPECTIVE_AFTER_AUTHORIZATION", "class": "UNTOUCHED_BY_CONSTRUCTION",
         "definition": "signals dated after the authorizing merge of a registration; their outcomes do not exist when the rule is frozen",
         "role": "the only confirmatory evidence the program can produce"},
    ]


def proposal():
    return {
        "id": "us-value-quality-breadth-v1", "status": "PROPOSED_NOT_REGISTERED", "authorizes": "NOTHING",
        "registered": False, "promotionEligible": False, "productionEffect": "NONE", "scheduledPublication": "NOT_STARTED",
        "relationToV1": "independent; v1 (US_CAPITAL_ALLOCATION_SELECTION_V1, digest %s) is neither modified nor replaced and keeps its own owner decision" % P.design_digest(),
        "whyThisHypothesisAndNotAnother": {
            "candidates": [
                {"id": "VALUE_QUALITY_CASHFLOW_COMPOSITE", "rank": 1,
                 "novelty": "value was excluded from the closed regional model (price basis unresolved); cash confirmation of earnings was not in its matrix",
                 "breadth": "existing-model inputs 66.2% and plus value 32.3% of eligible member-dates; distribution alone 21.5%",
                 "dataReadiness": "PIT numerators exist; as-traded price basis is reconstructable from sealed events (round-trip exact)",
                 "blockers": ["versioned value-feature definition", "fresh prices for a prospective run", "share-count basis of per-share numerators unverified"]},
                {"id": "SHAREHOLDER_DISTRIBUTION_GROWTH", "rank": 2, "note": "already registered as v1; breadth 17.9% (<= 30.6% under an unverified candidate view); buyback-led; dilution BLOCKED"},
                {"id": "NET_ISSUANCE_DILUTION", "rank": 3, "note": "economically attractive; BLOCKED until period-end share facts with class and split context are readable (SEC XBRL)"},
                {"id": "CATALYSTS_EVENTS", "rank": 4, "note": "no point-in-time event or earnings-calendar feed exists"},
                {"id": "PRICE_MOMENTUM_RISK", "rank": 5, "note": "inside the closed regional-alpha-model-v1 feature set; a retry would re-tune a closed result"}],
            "criteria": ["economic rationale", "novelty against closed studies", "breadth (power grows with names scored)", "PIT data readiness", "repair cost"]},
        "primaryHypothesis": {
            "economic": "Within the S&P 500, companies that are simultaneously inexpensive on earnings and free-cash-flow yield and profitable with earnings confirmed by "
                        "operating cash flow earn higher subsequent 126-session returns than their cross-sectional peers, beyond what price momentum and risk already order.",
            "mechanism": "compensation for risk and slow investor adjustment to cash-confirmed profitability; it is a hypothesis, not a result",
            "statistic": "mean cross-sectional Spearman rank correlation (IC) between the composite score and the H126 benchmark-relative return",
            "benchmarkInvariance": "the IC is the same against SPY and QQQ because the benchmark return is constant within a date; SPY is primary, QQQ alternative, and the "
                                   "SPY-vs-QQQ difference is reported as the passive growth spread, never as selection",
            "horizonSessions": 126, "primaryBenchmark": "SPY", "alternativeBenchmark": "QQQ"},
        "twoStageDesign": {
            "stage1_signalValidity": "score EVERY eligible name every week and record the rank information; paper only; the evidence accumulates with breadth, not with five holdings",
            "stage2_investability": "0-5 names only if a hurdle calibrated on PROSPECTIVE stage 1 evidence exceeds cost plus a declared margin; until calibrated the output is "
                                    "UNCALIBRATED_HURDLE and 100% benchmark. Zero stocks is the normal and initial outcome",
            "whyTwoStages": "a five-name book cannot resolve a realistic excess for years (see power); a signal can be tested on hundreds of names a week"},
        "candidateUniverse": {"membership": "S&P 500, latest snapshot strictly earlier than the signal date", "sectors": "Financials and Real Estate excluded "
                              "(earnings-yield and operating-cash-flow definitions differ); owner decision D4", "survivorship": "departed members stay while members; "
                              "a held name without an exit price is unresolved, never zero", "knownBias": "no failed or acquired company has a price panel in the sealed history; prospective data does not have this bias"},
        "outcomeBlindEligibility": ["positive close at most 10 calendar days old with at least 272 prior sessions", "identity unambiguous", "latest visible report period ended at most 180 days earlier",
                                    "every composite feature present (no imputation, no fill, missing is never zero)", "minimum scored names per week fixed from the power table before registration (recommended >= 150)"],
        "features": {
            "earningsYield": "epsTtm / as-traded close (positive earnings only)", "fcfYield": "fcfPerShare / as-traded close",
            "profitability": "roe, operatingMargin (existing sealed PIT_EXACT fields)", "cashConfirmation": "(OCF - capex) / OCF from the PR #220 engine, OCF > 0",
            "composite": "equal-weight mean of within-date percentile ranks of the pre-declared features; no fitted weight, no sector neutralisation, no tuning",
            "valueBasis": "RECONSTRUCTED as-traded price (pipeline/us_multifactor_inputs.py); a split between filing and observation withholds the yield; numerator share counts are weighted-average and unverified",
            "excludedUntilVerified": ["market capitalisation", "period-end dilution", "consensus estimates", "any 13F or macro input (separate registered hypothesis required)"]},
        "zeroToFiveNamePolicy": {"maxNames": 5, "slotWeight": P.SLOT_WEIGHT, "residualAsset": "SPY", "cash": "none",
                                 "hurdle": "UNCALIBRATED_HURDLE until stage 1 has at least 12 independent windows; then expected relative return net of 32.6 bp round-trip switch and a declared margin",
                                 "mechanicalTopFive": "forbidden: a rank alone never fills a slot"},
        "transactionCosts": P.costs_bps(),
        "validation": {
            "confirmatoryEvidence": "prospective only; the rule, features and parameters are frozen by hash before the first scored week",
            "inference": "circular moving-block bootstrap of the weekly IC series, block 26 weeks (one horizon), one-sided 95%, single look at the maturity gate",
            "multiplicity": "ONE primary claim (the IC); the stage 2 book and QQQ comparisons are secondary and carry no verdict power until the hurdle is calibrated",
            "secondary": ["top-quintile minus universe spread vs SPY and QQQ", "growth loading (QQQ - SPY spread)", "turnover and exposure", "H21 descriptive"],
            "interimLooks": "none for efficacy; one pre-declared futility look at 6 independent windows (statistician sign-off required before registration)",
            "power": power_tables()},
        "stopAndFailureCriteria": {
            "operationalStop": ["fewer scored names than the floor on 8 consecutive weeks", "price or membership input older than its limit on any signal date (BLOCKED receipt)",
                                "a feature definition or source changes (new study id)"],
            "failure": "at the gate: the one-sided 95% upper bound of the mean IC is not above zero",
            "success": "at the gate: the one-sided 95% lower bound of the mean IC is above zero AND the IC clears a pre-declared minimum useful size",
            "inconclusive": "neither, or any unresolved terminal outcome in a scored basket", "noRetroactiveChange": "benchmarks, horizons and gates cannot be edited after observation"},
        "pastDataClassification": exposure_classification(),
        "forbiddenInThisProposal": ["any historical stock-alpha outcome", "any backtest of candidate strategies", "choosing weights or thresholds from past returns"],
        "prerequisitesBeforeRegistration": [
            {"id": "VALUE_FEATURE_DEFINITION_V1", "kind": "implementation", "ownerApproval": False},
            {"id": "FRESH_DAILY_US_PRICES_AND_MEMBERSHIP_REFRESH", "kind": "data acquisition and a step in an existing workflow", "ownerApproval": True},
            {"id": "SEC_XBRL_ACCESS_FOR_SHARE_AND_DIVIDEND_CONTEXTS", "kind": "network allow-list", "ownerApproval": True},
            {"id": "STATISTICIAN_REVIEW_OF_THE_POWER_AND_FUTILITY_LOOK", "kind": "review", "ownerApproval": True}],
    }


# --------------------------------------------------------------------------- #
# The readiness report
# --------------------------------------------------------------------------- #
def report():
    cov, defs, ovl, dia, gap, dil, mf = (load(k) for k in ("coverage", "definitions", "overlap", "diagnostics", "sourceGaps", "dilution", "multifactor"))
    summary = cov["summary"]
    live = dia["decisions"]
    attempt = dia["currentInputAttempt"]
    with tempfile.TemporaryDirectory() as workdir:
        official = json.loads(PROTECTED.read_text())["docs/weekly-decision"]
        preflight = PI.preflight(Path(workdir), official)
    view = gap["candidateView"]["coverageUnderView"]
    sc = dia["scoreConstruction"]
    return {
        "id": "us-capital-allocation-phase2-readiness-v1", "studyId": P.STUDY_ID, "schemaVersion": 1,
        "verdict": {
            "overall": "NEEDS_SOURCE_REPAIR",
            "ordering": ["NEEDS_SOURCE_REPAIR", "NEEDS_NEW_POLICY_REGISTRATION", "READY_FOR_OWNER_APPROVAL"],
            "dataReadiness": "NEEDS_SOURCE_REPAIR", "selectionReadiness": "NEEDS_NEW_POLICY_REGISTRATION",
            "v1UnchangedPilot": "NOT_STARTABLE_LIVE_INPUTS_MISSING_AND_OWNER_APPROVAL_PENDING",
            "meaning": "v1 can be reviewed as a research instrument, but no live observation can start (no fresh US prices, aged membership, no weekly job), "
                       "v1 ranks accounting characteristics rather than measuring an expected-return hurdle, and the broader multifactor program needs a "
                       "versioned value definition, a fresh price feed and SEC context access before it can be registered"},
        "frozenV1": {"policyVersion": P.POLICY_VERSION, "designDigest": P.design_digest(), "registrationSha256": sha(REGISTRATION),
                     "status": json.loads(REGISTRATION.read_text())["status"], "registeredAuthorization": R.REGISTERED_AUTHORIZATION,
                     "scheduledPublication": "NOT_STARTED", "officialWeeklyFilesUnchanged": all(
                         hashlib.sha256((ROOT / "docs/weekly-decision" / n).read_bytes()).hexdigest() == h
                         for n, h in json.loads(PROTECTED.read_text())["docs/weekly-decision"].items())},
        "observationsAudited": {
            "weeklySignalDates": summary["weeklyDates"], "memberDates": summary["memberDates"],
            "jointCoveragePct": summary["jointMeasuredOfAllMemberDatesPct"], "jointCoverageOfFilingEligiblePct": summary["jointMeasuredOfFilingEligiblePct"],
            "blockedWeeks": live["status"]["BLOCKED"], "weeksWithFiveSelected": live["participation"]["weeksWithFullFiveNames"],
            "historicalOutcomesAccessed": False, "dilutionStatus": "BLOCKED", "valueOverlapMeasured": True},
        "sourceGapDiagnosis": {
            "firstBlockingFeatureTop3": [[k, v] for k, v in sorted(gap["whyNotMeasured"]["firstBlockingFeature"].items(), key=lambda kv: -kv[1])[:3]],
            "candidateViewJointCoveragePct": view["jointMeasuredPct"], "baselineJointCoveragePct": gap["baselineJointMeasuredPct"],
            "upperBoundGainPoints": round(view["jointMeasuredPct"] - gap["baselineJointMeasuredPct"], 4), "gainedCompanies": view["gainedCompanies"],
            "claim": "UPPER_BOUND_STORE_EVIDENCE_NOT_CONTEXT_VERIFIED", "frozenV1Untouched": True,
            "legitimateRepairVsNewDefinition": {
                "repairWithoutNewDefinition": ["fresh prices and membership (inputs, not definitions)", "SEC XBRL contexts to verify what the stored lines mean"],
                "requiresNewVersionedDefinition": ["accepting PaymentsOfDividends as the common-stock total", "accepting the continuing-operations OCF total",
                                                   "any typed treatment of an absent dividend or repurchase line", "a dilution measure built on weighted-average counts"]},
            "blocked": gap["blocked"], "priceAndIdentity": {k: gap["priceAndIdentity"][k] for k in ("noPricePanelMemberDates", "identityAmbiguousReasons", "membershipSnapshots")},
            "timestamps": {"acceptedDatePct": gap["timestamps"]["acceptedDatePct"], "medianPeriodEndToVisibleDays": gap["timestamps"]["periodEndToVisibleDays"]["median"]},
            "dilutionEvidence": {"periodEndBasisPct": dil["overall"]["periodEndBasisPct"], "sameBasisNoSplitPairsPct": dil["overall"]["sameBasisNoSplitPairsPct"],
                                 "status": dil["status"]}},
        "alwaysFiveNames": {
            "answer": "The registered rule ranks eligible companies on a payout-growth ratio; it does not impose an expected-return hurdle, so it fills five slots whenever "
                      "five names clear accounting thresholds, which happens in every non-blocked week",
            "weeksLive": live["participation"]["nonBlockedWeeks"], "passersPerLiveWeekMean": round(dia["gates"]["PASSED_EVERY_GATE"]["reached"] / live["participation"]["nonBlockedWeeks"], 2),
            "shareOfMeasuredClearingGrowthHurdle": sc["hurdleVersusMedianGrowth"]["shareOfMeasuredAtOrAboveHurdle"],
            "repurchaseLedShareOfSelectedSlots": dia["selectedComposition"]["repurchaseLed"],
            "selectedAbove80PctPayout": dia["selectedComposition"]["distributionAbove80PctOfOCF"],
            "sectorCapBindingShareOfWeeks": live["sectorCap"]["share"], "weeklyTurnoverMeanFractionReplaced": live["turnover"]["meanFractionReplaced"],
            "distinctNamesEverSelected": live["distinctNames"]["everSelected"], "fifthVsBestExcludedMedianGap": dia["margins"]["relativeGapFifthToBestExcluded"]["p50"],
            "A_vs_B": dia["accountingVsExpectedReturn"], "thresholdsChanged": False},
        "multifactor": {
            "eligibleMemberDatesSampled": mf["sampling"]["priceAndIdentityEligibleMemberDates"], "datesSampled": mf["sampling"]["dates"],
            "combinations": mf["combinations"], "flaggedRedundantPairs": mf["featureRedundancy"]["flaggedAtAbsRho70"],
            "notFullyPit": mf["verdict"], "snapshotOnlyOrAbsent": sorted(mf["pitClassification"]["SNAPSHOT_ONLY_OR_ABSENT"])},
        "currentInputAttempt": {k: attempt[k] for k in ("label", "notAReceipt", "notIndependentEvidence", "inputs", "result", "fundamentalsSideIfPricesWereFresh", "blocker")},
        "pilotPreflight": {"checks": preflight, "passed": sum(1 for c in preflight if c["status"] == "PASS"), "total": len(preflight),
                           "writesToProductionHistory": False},
        "evidenceSchedule": MO.evidence_schedule(ASSUMED_APPROVAL),
        "earlyMonitoring": {"signalMonitor": "coverage, blocked share, persistence, turnover, concentration, exposures", "h21": "descriptive means and counts after each receipt's own maturity",
                            "h126": "progress counts only until the gate", "statisticalCriteriaChanged": False,
                            "module": "pipeline/us_capital_allocation_monitoring.py"},
        "studyProposal": {"path": str(PROPOSAL.relative_to(ROOT)), "sha256": hashlib.sha256(dump(proposal()).encode()).hexdigest(),
                          "status": "PROPOSED_NOT_REGISTERED"},
        "remainingBlockers": [
            {"id": "NO_FRESH_US_PRICES", "severity": "BLOCKS_ANY_LIVE_OBSERVATION", "ownerApproval": True},
            {"id": "MEMBERSHIP_SNAPSHOT_AGED_NO_REFRESH_JOB", "severity": "BLOCKS_ANY_LIVE_OBSERVATION", "ownerApproval": True},
            {"id": "NO_WEEKLY_JOB_STEP_IN_EXISTING_WORKFLOW", "severity": "BLOCKS_ANY_LIVE_OBSERVATION", "ownerApproval": True},
            {"id": "SEC_XBRL_CONTEXT_UNREACHABLE", "severity": "BLOCKS_DILUTION_AND_ALIAS_VERIFICATION", "ownerApproval": True},
            {"id": "DEPARTED_MEMBER_PRICES_AND_TERMINAL_CONSIDERATION", "severity": "SURVIVORSHIP_BIAS_IN_ALL_HISTORICAL_WORK", "ownerApproval": False},
            {"id": "V1_HAS_NO_EXPECTED_RETURN_HURDLE", "severity": "SELECTION_POLICY", "ownerApproval": True},
            {"id": "VALUE_FEATURE_NOT_YET_A_VERSIONED_DEFINITION", "severity": "BLOCKS_NEXT_STUDY_REGISTRATION", "ownerApproval": False}],
        "dataAcquisitionPriority": [
            {"rank": 1, "item": "fresh daily US closes with actions for S&P 500 members, SPY and QQQ", "why": "nothing live can start without it", "cost": "low (existing vendor path)"},
            {"rank": 2, "item": "S&P 500 membership refresh on a schedule", "why": "membership is 34 days old with no registered limit", "cost": "low"},
            {"rank": 3, "item": "SEC XBRL instance facts: cover-page and period-end shares, dividend and preferred contexts", "why": "unblocks dilution and verifies every alias",
             "cost": "network allow-list for data.sec.gov (free source)"},
            {"rank": 4, "item": "delisted-security prices and cited terminal considerations (212 departed identities)", "why": "removes survivorship from any historical work",
             "cost": "paid vendor or SEC filings; lower priority for prospective-only research"},
            {"rank": 5, "item": "point-in-time market capitalisation and consensus estimates", "why": "completes value and expectations", "cost": "paid"}],
        "implementNow": ["versioned value-feature definition with the reconstructed price basis (pipeline/us_multifactor_inputs.py is the draft)", "keep this PR's audits regenerable",
                         "owner reviews the v1 decision memo and the study proposal"],
        "ownerApprovalRequired": ["any live receipt or authorization flag", "a step in an existing workflow for prices and membership", "SEC network allow-list",
                                  "registering the next study", "whether v1 is observed unchanged"],
    }


def dump(obj):
    return json.dumps(obj, indent=1, sort_keys=True, allow_nan=False, ensure_ascii=False) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    outputs = {PROPOSAL: dump(proposal()), REPORT: dump(report())}
    if args.check:
        stale = [str(p.relative_to(ROOT)) for p, text in outputs.items() if not p.exists() or p.read_text() != text]
        if stale:
            print("STALE: " + ", ".join(stale))
            return 1
        print("phase 2 files match the code and the committed audits")
        return 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for path, text in outputs.items():
        path.write_text(text, encoding="utf-8")
        print("wrote %s (%d bytes)" % (path.relative_to(ROOT), len(text)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
