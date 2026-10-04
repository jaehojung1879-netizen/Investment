#!/usr/bin/env python3
"""Seal research_specs/kr-industry-opportunity-anatomy-v1.json. Writes the frozen definitions, computes every dependency hash from the
import closure plus the sealed data inputs, and writes the SHA-256 sidecar. Reads no price, return or outcome."""
from __future__ import annotations

import gzip
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import kr_industry_anatomy as I  # noqa: E402
from pipeline.alpha_opportunity_v3_spec import import_closure  # noqa: E402
from pipeline.kr_model_portfolio_execution import digest, file_hash  # noqa: E402

STUDY = I.STUDY
ENTRY_POINTS = ["pipeline/kr_industry_anatomy_execution.py", "pipeline/kr_industry_anatomy.py"]
V4 = "data/kr-industry-membership-foundation-v4"
MEMBERSHIP_FILES = [V4 + "/state/intervals.json.gz", V4 + "/state/audit.json.gz", "research_specs/kr-industry-membership-foundation-v4/crosswalk.json",
                    "research_specs/kr-industry-membership-foundation-v4/crosswalk.json.sha256", "research_specs/kr-industry-membership-foundation-v4/protocol.json",
                    "research_specs/kr-industry-membership-foundation-v4/protocol.json.sha256"]
SEALED = sorted(set(MEMBERSHIP_FILES + [
    ".github/workflows/kr-industry-opportunity-anatomy-v1.yml", "docs/kr-industry-opportunity-anatomy-v1-design.md", "scripts/run_kr_industry_anatomy_v1.py",
    "scripts/build_kr_industry_anatomy_spec.py", "research_specs/kr-factor-anatomy-v1.json", "research_specs/kr-factor-anatomy-v1.sha256",
    "research_specs/kr-top120-regime-review-v1.json", "research_specs/kr-top120-regime-review-v1.sha256",
    "research_specs/kr-model-overlay-portfolio-v1.json", "research_specs/kr-model-overlay-portfolio-v1.sha256",
    "data/kr-industry-membership-foundation-v1/identity-inventory.json", "data/kr-industry-membership-foundation-v1/identity-provenance.json",
    "data/kr-industry-membership-foundation-v1/top120-inputs.json"]))


def build():
    regime = json.loads((ROOT / "research_specs/kr-top120-regime-review-v1.json").read_text())
    anatomy = json.loads((ROOT / "research_specs/kr-factor-anatomy-v1.json").read_text())
    audit = json.loads(gzip.decompress((ROOT / V4 / "state/audit.json.gz").read_bytes()))
    crosswalk = json.loads((ROOT / "research_specs/kr-industry-membership-foundation-v4/crosswalk.json").read_text())
    pin = regime["input"]
    spec = {
        "studyId": STUDY, "scientificStatus": I.SCIENTIFIC_STATUS, "phase": "PROTOCOL_AND_HARNESS_ONLY_NO_OUTCOME_COMPUTED",
        "question": "Do observable industry states at signal date t show a stable historical association with the subsequent benchmark-relative industry return?",
        "boundary": {"isAnAlphaModel": False, "isStockSelection": False, "isAPortfolio": False, "isAProductionRecommendation": False,
                     "isEvidenceOfProspectivePredictability": False, "passFailSemantics": "NONE", "mayChooseABestFeature": False,
                     "mayChangeTaxonomyFromOutcomes": False, "mayRelabelV4Decision": False,
                     "outcomeExecutionInThisChange": False, "pullRequestMayRun": ["verify", "readiness", "synthetic tests"]},
        "region": "KR", "benchmark": I.BENCHMARK, "returnBasis": I.RETURN_BASIS, "horizons": list(I.HORIZONS), "primaryHorizon": I.PRIMARY_HORIZON,
        "developmentCutoff": anatomy["developmentCutoff"],
        "returnDefinition": {"entry": "next KR session strictly after the signal date", "exit": "H sessions after entry, repository session calendar, exact endpoints only",
                             "basis": "adjusted index with partial observed distributions; never called total shareholder return",
                             "cohort": "membership and weights frozen at the signal date for the whole forward window",
                             "completeness": "a lens is MATURED only if every cohort member has a matured return under the accepted terminal discipline; no survivor renormalisation"},
        "lenses": {"CAP_WEIGHTED": "PRIMARY economic lens; weights are signal-date market caps; any member without a cap makes the lens INELIGIBLE",
                   "EQUAL_WEIGHT": "ROBUSTNESS / breadth lens; roles fixed before outcomes"},
        "targets": {"primary": "CAP_WEIGHTED H126 industry return minus same-window benchmark return",
                    "secondary": ["CAP_WEIGHTED H63", "CAP_WEIGHTED H252", "EQUAL_WEIGHT H63", "EQUAL_WEIGHT H126", "EQUAL_WEIGHT H252"]},
        "constants": {"horizons": list(I.HORIZONS), "primaryHorizon": I.PRIMARY_HORIZON, "minMembers": I.MIN_MEMBERS, "minCrossSection": I.MIN_CROSS_SECTION,
                      "minTercileCrossSection": I.MIN_TERCILE_CROSS_SECTION, "minFundamentalShare": I.MIN_FUNDAMENTAL_SHARE,
                      "minFundamentalCount": I.MIN_FUNDAMENTAL_COUNT, "stratumTop1ShareCutoff": I.STRATUM_TOP1_SHARE_CUTOFF,
                      "minStratumCrossSection": I.MIN_STRATUM_CROSS_SECTION},
        "eligibility": {"taxonomy": "the frozen v4 14-group economic crosswalk, unmodified", "eligibleMembershipStatuses": list(I.ELIGIBLE_MEMBERSHIP_STATUSES),
                        "minimumClassifiedMembers": I.MIN_MEMBERS, "unknownFill": "never", "survivorSubstitution": "never",
                        "ineligible": "stays INELIGIBLE with a reason, never zero or neutral",
                        "coverageReported": ["constituent count", "classified coverage", "top-1 and top-2 cap share", "HHI", "missing cap share", "eligible and ineligible industry-dates"]},
        "features": {"names": list(I.FEATURES), "pastOnly": True, "windows": {"trailing": list(I.TRAILING), "breadth": I.BREADTH_WINDOW, "risk": I.RISK_WINDOW},
                     "definitions": {"REL_MOM_h": "cap-weighted trailing h-session return of the frozen cohort minus the benchmark's, closes at or before t",
                                     "BREADTH_POSITIVE_126": "fraction of members with positive trailing 126-session return",
                                     "BREADTH_ABOVE_MA_126": "fraction of members whose close at t exceeds the mean of the last 126 closes ending at t",
                                     "BREADTH_REL_MOM_POSITIVE_126": "fraction of members whose trailing 126 return exceeds the benchmark's",
                                     "DOWNSIDE_VOL_126": "sqrt(mean(min(r,0)^2))*sqrt(252) of the fixed-weight industry daily series over 126 sessions",
                                     "CONSTITUENT_DISPERSION_126": "population standard deviation of members' trailing 126 returns",
                                     "TOP1_CAP_SHARE / TOP2_CAP_SHARE / CONSTITUENT_COUNT": "signal-date cap shares and member count",
                                     "MEDIAN_LOG_ADV60": "median of member logAdv60 under the fundamental coverage rule",
                                     "MEDIAN_<fundamental>": "median of the member PIT accounting ratio under the coverage rule; missing is NaN, never zero"},
                     "fundamentalColumns": list(I.FUNDAMENTAL_COLUMNS),
                     "marketState": "riskMultiplier is constant across industries on a date: descriptive conditioning only, never a cross-sectional feature",
                     "excluded": ["ECOS or FRED revised macro history", "any series without a historical knowledge timestamp", "industry-specific cycle data"]},
        "statistics": {"primary": ["per-date Spearman(feature, H126 CAP_WEIGHTED relative target): mean, median, sign fraction, valid dates, year table",
                                   "top-minus-bottom tercile spread, k=floor(n/3), n>=9, ordering (feature, industry id), tie across a boundary invalidates the date"],
                       "secondary": ["H63 and H252", "cap vs equal weight and their per-date rank agreement", "outcome-window slices", "descriptive HAC standard error, lag ceil(h/5), labelled descriptive"],
                       "regimeSlices": list(I.SLICES), "slicesDecidedBy": "outcome window entry and exit dates, boundaries 2025-01-01 and 2026-01-01 fixed here",
                       "noBinaryEconomicThreshold": True, "noFeatureSelection": True, "multiplicity": "none applied; no isolated p-value is confirmation"},
        "sensitivities": {"names": list(I.SENSITIVITIES), "excludedMegaCaps": list(I.EXCLUDED_MEGA_CAPS),
                          "strata": {"names": list(I.STRATA), "top1ShareCutoff": I.STRATUM_TOP1_SHARE_CUTOFF},
                          "role": "diagnostics only; none is an alternative strategy-selection route"},
        "fundamentalImprovement": "absolute industry return, benchmark-relative industry return and cross-sectional peer position are never conflated",
        "missingness": {"noUnknownToZero": True, "noMissingIndustryToNeutral": True, "noSurvivorRenormalisation": True,
                        "reportedPerFeatureAndTarget": ["eligible industry-dates", "ineligible industry-dates", "constituent count", "membership coverage", "feature coverage"]},
        "membership": {"files": {rel: file_hash(ROOT / rel) for rel in MEMBERSHIP_FILES}, "crosswalkPath": "research_specs/kr-industry-membership-foundation-v4/crosswalk.json",
                       "coarseGroups": len(crosswalk["groups"]), "mappedRawLabels": len(crosswalk["mapping"]),
                       "v4Decision": audit["decision"],
                       "v4Facts": {k: audit[k] for k in ("everTop120Securities", "signalDates", "nameDates", "classifiedNameDates", "unknownNameDates", "rawIndustryCount",
                                                         "coarseIndustryCount", "terminal", "conflictIntervals")},
                       "limitation": "22 terminal common securities have no historical industry; most classified name-dates rest on a no-change reconstruction; not PIT exact"},
        "input": {"artifactName": pin["artifactName"], "artifactId": pin["artifactId"], "producingRunId": pin["producingRunId"], "artifactArchiveSha256": pin["artifactArchiveSha256"],
                  "identitySha256": pin["identitySha256"], "krxCacheSha256": pin["krxCacheSha256"], "recollect": False,
                  "pinnedFrom": {"regimeReviewInput": pin, "overlaySpec": "research_specs/kr-model-overlay-portfolio-v1.json"},
                  "downloadRule": "execution downloads this exact artifact (name, run id, artifact id and archive digest checked through the Actions API) and verifies the input identity before any outcome is computed"},
        "readiness": {"minimumNamesWithMarketCapPerDate": 3, "failedGateEffect": "writes gates-failed.json; no lock, no outcome read, no budget spent",
                      "gates": ["non-empty PIT name-dates", "no duplicate (date, ticker)", "signal-time columns exist", "signal dates and PIT Top120 equal the v4 membership calendar and universe",
                                "signal-date market cap available", "membership reconstruction exists"]},
        "lifecycle": {"resultPath": RESULT, "markerPath": MARKER,
                      "executionLock": "refs/tags/" + STUDY + "-execution-lock (study level, atomic POST /git/refs) plus -<specSha256>; any existing ref refuses; post-lock failure consumes the study",
                      "sequence": ["protocol PR merges", "human dispatches execute once", "identities and gates pass", "durable lock before the first outcome", "result artifact", "seal commit", "later attempts fail closed"]},
        "outcomeAccess": {"counters": ["targetCalls", "labelCalls", "outcomeColumnCalls", "analysisCalls", "markerWrites"], "inThisChange": "NONE", "verifyAndReadinessRequireAllZero": True},
        "limitations": ["Outcome-exposed single historical sample; exploratory only", "Industry history is a reconstruction (DATA_FOUNDATION_INSUFFICIENT_V4), not PIT exact",
                        "About 14 coarse industries: small cross-sections, no stock-style deciles", "Weekly signals overlap; few independent observations",
                        "Top-120 large caps only", "Return basis has partial distributions; banks and high-dividend names are unreliable",
                        "No multiplicity correction; no isolated p-value is confirmation", "Terminal common securities are unclassified, so some industry-dates are INELIGIBLE or UNRESOLVED"],
        "entryPoints": ENTRY_POINTS, "sealedDataInputs": SEALED,
    }
    closure = sorted(set(import_closure(ENTRY_POINTS, ROOT)) | set(SEALED))
    spec["dependencyHashes"] = {rel: file_hash(ROOT / rel) for rel in closure}
    return spec


RESULT = "docs/results/" + STUDY + "-result.json"
MARKER = "docs/results/" + STUDY + "-execution-started.json"

if __name__ == "__main__":
    spec = build()
    path = ROOT / "research_specs" / (STUDY + ".json")
    path.write_text(json.dumps(spec, sort_keys=True, indent=2, ensure_ascii=False) + "\n")
    # `digest` hashes the parsed document, matching load_spec; the sidecar is that digest.
    path.with_suffix(".sha256").write_text(digest(json.loads(path.read_text())) + "\n")
    print(digest(spec))
