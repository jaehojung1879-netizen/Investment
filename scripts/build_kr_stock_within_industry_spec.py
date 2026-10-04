#!/usr/bin/env python3
"""Seal research_specs/kr-stock-within-industry-anatomy-v1.json. Writes the frozen definitions, computes every dependency hash from the
import closure plus the sealed data inputs, and writes the SHA-256 sidecar. Reads no price, return or outcome."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import kr_stock_within_industry_anatomy as S  # noqa: E402
from pipeline.alpha_opportunity_v3_spec import import_closure  # noqa: E402
from pipeline.kr_model_portfolio_execution import digest, file_hash  # noqa: E402

STUDY = S.STUDY
ENTRY_POINTS = ["pipeline/kr_stock_within_industry_anatomy_execution.py", "pipeline/kr_stock_within_industry_anatomy.py"]
RESULT = "docs/results/" + STUDY + "-result.json"
MARKER = "docs/results/" + STUDY + "-execution-started.json"
PRIOR_RESULTS = ["docs/results/kr-factor-anatomy-v1-result.json", "docs/results/kr-industry-opportunity-anatomy-v1-result.json",
                 "docs/results/kr-model-overlay-portfolio-v1-result.json"]
SEALED = sorted(set(PRIOR_RESULTS + [
    ".github/workflows/kr-stock-within-industry-anatomy-v1.yml", "docs/kr-stock-within-industry-anatomy-v1-design.md",
    "scripts/run_kr_stock_within_industry_anatomy_v1.py", "scripts/build_kr_stock_within_industry_spec.py",
    "research_specs/kr-industry-opportunity-anatomy-v1.json", "research_specs/kr-industry-opportunity-anatomy-v1.sha256",
    "research_specs/kr-factor-anatomy-v1.json", "research_specs/kr-factor-anatomy-v1.sha256",
    "research_specs/kr-top120-regime-review-v1.json", "research_specs/kr-top120-regime-review-v1.sha256",
    "research_specs/kr-model-overlay-portfolio-v1.json", "research_specs/kr-model-overlay-portfolio-v1.sha256",
    "data/kr-industry-membership-foundation-v1/identity-inventory.json", "data/kr-industry-membership-foundation-v1/identity-provenance.json",
    "data/kr-industry-membership-foundation-v1/top120-inputs.json"]
    + list(json.loads((ROOT / "research_specs/kr-industry-opportunity-anatomy-v1.json").read_text())["membership"]["files"])))


def build():
    industry = json.loads((ROOT / "research_specs/kr-industry-opportunity-anatomy-v1.json").read_text())
    anatomy = json.loads((ROOT / "research_specs/kr-factor-anatomy-v1.json").read_text())
    spec = {
        "studyId": STUDY, "scientificStatus": S.SCIENTIFIC_STATUS, "phase": "PROTOCOL_AND_HARNESS_ONLY_NO_OUTCOME_COMPUTED",
        "question": "After the contemporaneous industry component is removed, do the stock-factor associations previously read against the market "
                    "benchmark keep their sign and size when the target is the stock's return minus the return of its OWN industry's other members?",
        "decomposition": {"identity": "stock - market = (industry - market) + (stock - industry), an identity on returns, asserted on every matured row",
                          "studied": "stock - leave-one-out industry (the evaluated stock is excluded from the industry cohort AND the industry weights)",
                          "alsoReportedForSeparation": ["leave-one-out industry - market", "stock - market on the SAME sample"],
                          "rankCorrelationsAreNotAdditive": True},
        "boundary": {"isAnAlphaModel": False, "isStockSelection": False, "isAPortfolio": False, "isAProductionRecommendation": False,
                     "isEvidenceOfProspectivePredictability": False, "passFailSemantics": "NONE", "mayChooseABestFeature": False,
                     "mayCallAnyFeatureValidatedOrPredictive": False, "mayChangeTaxonomyFromOutcomes": False, "mayAddFeaturesAfterOutcomes": False,
                     "mayAlterOrReinterpretSealedResults": False, "outcomeExecutionInThisChange": False,
                     "pullRequestMayRun": ["verify", "readiness", "synthetic tests"]},
        "region": "KR", "benchmark": S.BENCHMARK, "returnBasis": S.RETURN_BASIS, "horizons": list(S.HORIZONS), "primaryHorizon": S.PRIMARY_HORIZON,
        "developmentCutoff": anatomy["developmentCutoff"],
        "returnDefinition": {"entry": "next KR session strictly after the signal date", "exit": "H sessions after entry, repository session calendar, exact endpoints only",
                             "basis": "adjusted index with partial observed distributions; never called total shareholder return",
                             "cohort": "peer membership and peer weights frozen at the signal date for the whole forward window",
                             "completeness": "a target is MATURED only if the stock AND every peer have a matured return under the accepted terminal discipline; no survivor renormalisation"},
        "targets": {"primary": "stock forward return minus leave-one-out CAP_WEIGHTED industry forward return, H126",
                    "robustness": "stock forward return minus leave-one-out EQUAL_WEIGHT industry forward return",
                    "secondary": ["H63", "H252"],
                    "peerWeights": "signal-date market caps of the PEERS only, normalised over the peers; the evaluated stock's own cap is never used",
                    "capLensIneligibleWhen": "any peer lacks a finite positive signal-date market cap",
                    "neverDo": ["use an industry return that contains the evaluated stock", "fill UNKNOWN names into a cohort", "substitute a survivor or successor",
                                "renormalise over surviving peers", "treat a missing peer return as zero"]},
        "eligibility": {"taxonomy": "the frozen v4 14-group economic crosswalk, unmodified", "eligibleMembershipStatuses": list(S.ELIGIBLE_MEMBERSHIP_STATUSES),
                        "minimumIndustryMembers": S.MIN_INDUSTRY_MEMBERS, "minimumOtherPeers": S.MIN_PEERS,
                        "unknownFill": "never", "survivorSubstitution": "never",
                        "ineligible": "stays in the denominator with a status and a reason, never zero or neutral",
                        "statuses": ["ELIGIBLE", "INELIGIBLE_UNCLASSIFIED", "INELIGIBLE_BELOW_MINIMUM_INDUSTRY_MEMBERS", "EXCLUDED_BY_SENSITIVITY"],
                        "targetStatuses": ["MATURED", "PENDING", "INELIGIBLE_INDUSTRY_DATE", "INELIGIBLE_FEWER_THAN_FOUR_PEERS",
                                           "INELIGIBLE_CAP_WEIGHT_UNAVAILABLE", "UNRESOLVED_OWN_RETURN", "UNRESOLVED_PEER_RETURN",
                                           "UNRESOLVED_BENCHMARK_OR_OWN_RETURN", "INELIGIBLE_STOCK_DATE"]},
        "features": {"names": list(S.FEATURES), "source": "pipeline/kr_value_quality_catalyst.py (feature_at), signal-date values from the sealed v1 `prepare`",
                     "definitions": [{k: f[k] for k in ("name", "family", "orientation", "plain", "caveat")} for f in anatomy["factors"]],
                     "lenses": {"RAW": "the registered feature value itself, ranked across the whole same-date eligible cross-section by the Spearman",
                                "WITHIN_INDUSTRY_RANK": "the average-rank percentile (r-0.5)/n among the finite values of the SAME signal date and the stock's OWN industry"},
                     "withinIndustryTransform": {"peers": "classified members of the stock's industry at the signal date after any registered sensitivity exclusion, the stock included",
                                                 "minimumFinitePeers": S.MIN_RANK_PEERS, "ties": "average percentile (order independent)",
                                                 "belowMinimum": "NaN, never zero or neutral", "usesOnlyDate": "signal date t",
                                                 "frozenBeforeOutcomes": True, "rankedBeforeAnyOutcomeIsAttached": True},
                     "commonSample": "both feature lenses and all three components are evaluated on the SAME name-dates: eligible, matured target for the lens, finite raw value, finite within-industry rank",
                     "relative126Note": "relative126 minus a within-date constant is the stock's own trailing return, so its within-industry rank is a within-industry price-momentum rank",
                     "contextVariable": "within-industry percentile of signal-date market cap, used only as the size stratifier of logAdv60; not one of the registered features",
                     "noFeatureSelection": True, "noNewSignals": True},
        "statistics": {"primary": "per signal date, Spearman(within-industry feature rank, H126 stock - leave-one-out CAP_WEIGHTED industry return) across the common-sample stocks of that date; reports mean, median, sign fraction, valid dates, annual values, descriptive HAC standard error",
                       "secondary": {"industryDateGroups": {"groups": "top and bottom k = floor(n/3) stocks by feature inside ONE industry-date", "minimumGroupSize": S.MIN_GROUP_SIZE,
                                                            "minimumIndustryN": S.MIN_GROUP_INDUSTRY_N, "ordering": "(feature, ticker)",
                                                            "ties": "a feature value tied across a group boundary invalidates the industry-date; ties inside a group are harmless",
                                                            "withinGroup": "stocks equal-weighted",
                                                            "aggregation": "equal weight per industry within a date (at least %d industries), then equal weight per date" % S.MIN_INDUSTRIES_PER_DATE,
                                                            "noStockStyleDecilesWhereGroupsAreTooSmall": True},
                                     "equalIndustryRankCorrelation": "per industry-date Spearman (n >= %d), equal weight per industry then per date; invariant to the within-industry transform so reported once" % S.MIN_GROUP_INDUSTRY_N,
                                     "horizons": "H63 and H252 beside H126",
                                     "weightLensRobustness": "CAP_WEIGHTED versus EQUAL_WEIGHT leave-one-out benchmark",
                                     "components": list(S.COMPONENTS), "sizeControlForLogAdv60": "pooled within-industry association inside the lower and upper half of within-industry size, and the rank overlap of the two",
                                     "benchmarkStates": "kr_market_risk_overlay riskMultiplier (1.0 / 0.7 / 0.4) at the signal date, the only market-state split"},
                       "aggregation": "per date first; dates equal-weighted; summaries from pipeline.kr_industry_anatomy.summarize",
                       "minimumCrossSection": S.MIN_DATE_CROSS_SECTION, "noBinaryEconomicThreshold": True, "noFeatureSelection": True,
                       "multiplicity": "none applied; no isolated p-value is confirmation; weekly signals overlap so effective dates are far fewer than valid dates"},
        "comparisonToSealedStockAnatomy": {"reference": "mean per-date rank correlation of the SEALED kr-factor-anatomy-v1 (stock minus market, V1_TERMINAL_DISCIPLINE, PIT Top120), read from its result file and never recomputed",
                                           "horizons": [126, 252], "interpretiveOnly": True,
                                           "alsoReported": "the same-sample stock-minus-market reading of THIS study, so a sample difference is not read as an industry effect",
                                           "shiftClasses": ["SURVIVES", "WEAKENS_MATERIALLY", "LARGELY_ABSORBED", "ABSORBED_TO_NEAR_ZERO", "CHANGES_SIGN", "REFERENCE_NEAR_ZERO", "DATA_INSUFFICIENT"],
                                           "conventions": {"nearZeroIc": S.NEAR_ZERO_IC, "survivesRatio": S.SURVIVES_RATIO, "weakensRatio": S.WEAKENS_RATIO,
                                                           "minimumValidDates": S.MIN_VALID_DATES_FOR_LABEL},
                                           "stability": "sign of the pooled mean over the registered views; SIGN_DEPENDS_ON_VIEW is the instability reading",
                                           "mayNotSay": ["validated", "predictive", "confirmed", "best", "recommended"]},
        "sensitivities": {"names": list(S.SENSITIVITIES), "excludedMegaCaps": list(S.EXCLUDED_MEGA_CAPS),
                          "exclusionRule": "removed BEFORE industry cohorts, within-industry ranks and peer weights are formed",
                          "slices": list(S.SLICES), "slicesDecidedBy": "outcome window entry and exit dates, boundary 2025-01-01 fixed here",
                          "weightLenses": list(S.WEIGHT_LENSES), "role": "diagnostics only; none is an alternative strategy-selection route and none is promoted"},
        "questions": {k: {"features": list(v)} for k, v in S.QUESTIONS.items()},
        "registry": {"weightLenses": list(S.WEIGHT_LENSES), "components": list(S.COMPONENTS), "featureLenses": list(S.FEATURE_LENSES),
                     "sensitivities": list(S.SENSITIVITIES), "slices": list(S.SLICES), "benchmarkStates": list(S.BENCHMARK_STATES),
                     "signViews": [list(v) for v in S.SIGN_VIEWS], "questions": {k: list(v) for k, v in S.QUESTIONS.items()}},
        "constants": {"horizons": list(S.HORIZONS), "primaryHorizon": S.PRIMARY_HORIZON, "minIndustryMembers": S.MIN_INDUSTRY_MEMBERS, "minPeers": S.MIN_PEERS,
                      "minRankPeers": S.MIN_RANK_PEERS, "minDateCrossSection": S.MIN_DATE_CROSS_SECTION, "minStratumCrossSection": S.MIN_STRATUM_CROSS_SECTION,
                      "minGroupSize": S.MIN_GROUP_SIZE, "minGroupIndustryN": S.MIN_GROUP_INDUSTRY_N, "minIndustriesPerDate": S.MIN_INDUSTRIES_PER_DATE,
                      "minSliceDates": S.MIN_SLICE_DATES, "minValidDatesForLabel": S.MIN_VALID_DATES_FOR_LABEL, "nearZeroIc": S.NEAR_ZERO_IC,
                      "survivesRatio": S.SURVIVES_RATIO, "weakensRatio": S.WEAKENS_RATIO, "annualMinDates": S.ANNUAL_MIN_DATES, "minSignViews": S.MIN_SIGN_VIEWS},
        "missingness": {"noUnknownToZero": True, "noMissingIndustryToNeutral": True, "noSurvivorRenormalisation": True, "noUnknownFill": True,
                        "reportedPerFeatureAndTarget": ["stock-dates", "eligible stock-dates", "matured targets", "raw finite", "within-industry rank finite", "common sample"]},
        "membership": industry["membership"], "input": industry["input"], "readiness": industry["readiness"],
        "priorSealed": {"resultFiles": {rel: file_hash(ROOT / rel) for rel in PRIOR_RESULTS},
                        "referenceResult": "docs/results/kr-factor-anatomy-v1-result.json",
                        "neverRerun": ["kr-model-overlay-portfolio-v1", "kr-factor-anatomy-v1", "kr-top120-regime-review-v1", "kr-industry-opportunity-anatomy-v1"],
                        "role": "pinned by hash; only the factor-anatomy result is read, once, at execution, as an interpretive reference"},
        "lifecycle": {"resultPath": RESULT, "markerPath": MARKER,
                      "executionLock": "refs/tags/" + STUDY + "-execution-lock (study level, atomic POST /git/refs) plus -<specSha256>; any existing ref refuses; post-lock failure consumes the study",
                      "sequence": ["protocol PR merges", "human dispatches execute once", "identities and gates pass", "durable lock before the first outcome",
                                   "result artifact", "seal commit", "later attempts fail closed"]},
        "outcomeAccess": {"counters": ["targetCalls", "labelCalls", "outcomeColumnCalls", "analysisCalls", "markerWrites", "priorResultReads"],
                          "inThisChange": "NONE", "verifyAndReadinessRequireAllZero": True},
        "limitations": ["Outcome-exposed single historical sample; exploratory only", "Industry history is a reconstruction (DATA_FOUNDATION_INSUFFICIENT_V4), not PIT exact",
                        "About 14 coarse industries with five to a few dozen members: thin peer sets make the leave-one-out benchmark noisy",
                        "Weekly signals overlap; few independent observations", "Top-120 large caps only",
                        "Return basis has partial distributions; banks and high-dividend names are unreliable",
                        "Issue-cap accounting proxies; whole-entity accounts over one quoted issue's market cap",
                        "No multiplicity correction; no isolated p-value is confirmation",
                        "Terminal common securities are unclassified, so their stock-dates are INELIGIBLE and any peer without a matured return makes the target UNRESOLVED",
                        "A within-industry rank removes industry composition, not size, mega-cap or sector-cycle effects inside an industry"],
        "entryPoints": ENTRY_POINTS, "sealedDataInputs": SEALED,
    }
    closure = sorted(set(import_closure(ENTRY_POINTS, ROOT)) | set(SEALED))
    spec["dependencyHashes"] = {rel: file_hash(ROOT / rel) for rel in closure}
    return spec


if __name__ == "__main__":
    spec = build()
    path = ROOT / "research_specs" / (STUDY + ".json")
    path.write_text(json.dumps(spec, sort_keys=True, indent=2, ensure_ascii=False) + "\n")
    path.with_suffix(".sha256").write_text(digest(json.loads(path.read_text())) + "\n")
    print(digest(spec))
