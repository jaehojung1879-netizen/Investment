"""Outcome-free registration, exact identity checks and bounded computation plan."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pipeline import kr_alpha_atlas_registry as REG
from pipeline import kr_alpha_atlas_readiness as RD
from pipeline import replay_calendar as RC
from pipeline.benchmark_alpha import REALISTIC_COSTS
from pipeline.alpha_opportunity_v3_spec import import_closure

ROOT = Path(__file__).resolve().parents[2]
STUDY = "kr-alpha-atlas-phase-c-v1"
SPEC = "research_specs/" + STUDY + ".json"
SIDECAR = "research_specs/" + STUDY + ".sha256"
MANIFEST = "docs/results/kr-alpha-atlas-phase-b-phase-c-manifest.json"
REGISTRY = "research_specs/kr-alpha-atlas-registry-v1.json"
RESULT_SCHEMA = "research_specs/kr-alpha-atlas-phase-c-result-schema-v1.json"
WORKFLOW = ".github/workflows/kr-alpha-atlas-phase-c.yml"
ENTRY = ["scripts/run_kr_alpha_atlas_phase_c.py"]
EVIDENCE = "EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY"
VERDICTS = [
    "BLOCKED",
    "NO_DEVELOPMENT_EVIDENCE",
    "UNSTABLE",
    "REDUNDANT",
    "NOT_ECONOMIC",
    "INDEPENDENT_DEVELOPMENT_SUPPORT",
]


def canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def digest(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read(root, rel):
    return json.loads((Path(root) / rel).read_text())


def model_groups(spec):
    baselines = spec["baselines"]
    b4 = baselines["B4_COMBINED_SIMPLE"]
    features = spec["eligibleFeatures"]
    out = {}
    for h in spec["horizons"]:
        groups = {k: list(v) for k, v in baselines.items()}
        # Full eligible set includes controls used by B4; construction/context never enter.
        full = sorted(set(b4) | {f["featureId"] for f in features})
        groups["FULL"] = full
        for family in sorted({f["family"] for f in features if h in f["registeredHorizons"]}):
            ids = {f["featureId"] for f in features if f["family"] == family}
            groups["ADD_" + family] = sorted(set(b4) | ids)
            groups["REMOVE_" + family] = sorted(set(full) - ids)
        out[h] = groups
    return out


def build(root=ROOT):
    root = Path(root)
    manifest, registry = read(root, MANIFEST), read(root, REGISTRY)
    REG.validate(registry)
    features = [
        {**f, "registeredHorizons": [h for h in f["registeredHorizons"] if h is not None], "role": "ALPHA_CANDIDATE"}
        for f in manifest["eligibleFeatures"]
    ]
    # Directions follow economic mechanisms, never returns. Unsigned exploratory relationships
    # are measured two-sided; a wrong economic sign cannot advance to a long-only assessment.
    negative = {
        "A01_return1d",
        "A02_return5d",
        "A03_return21d",
        "C09_assetGrowth",
        "C10_liabilityGrowth",
        "C11_shareDilution",
        "D09_abnormalVolumeDownClose",
        "F01_totalVolatility63",
        "F03_beta252",
        "F04_idiosyncraticVol",
    }
    for f in features:
        f["expectedDirection"] = -1 if f["featureId"] in negative else 1
    spec = {
        "studyId": STUDY,
        "version": 1,
        "evidenceClass": EVIDENCE,
        "question": "Which observable information adds stable stock-selection information beyond B4 and survives realistic long-only economics?",
        "confirmation": "NONE: reused KR history through cutoff is development; only genuinely prospective preregistered receipts can confirm.",
        "developmentCutoff": registry["developmentCutoff"],
        "benchmark": registry["benchmark"],
        "universe": manifest["referenceUniverse"],
        "eligibleFeatures": features,
        "roles": {
            "baselineControl": manifest["baselineAndControlFeatures"],
            "contextOnly": manifest["contextConditioningFeatures"],
            "constructionOnly": manifest["constructionAndEligibilityFeatures"],
        },
        "excludedFeatures": manifest["excludedFeatures"],
        "featureStatusLedger": manifest["featureStatusLedger"],
        "alreadyTested": {
            "policy": manifest["alreadyTestedPolicy"],
            "sealedReferences": {
                f["featureId"]: f["priorEvidenceReference"]
                for f in registry["features"]
                if f["readinessStatus"] == "ALREADY_TESTED"
            },
        },
        "phaseBIdentity": manifest["identity"],
        "primaryFrozenSnapshot": "PHASE_B_GIT_PINNED_PROXY_SNAPSHOT: exact inputs identity 3e4d7aa35e2c4b273e4ecef0e2e8ea7a8a27077f0de14bb3d5ea6a696a97f1a5; original Actions official market bytes are not selected",
        "frozenArtifact": {
            "requiredForThisStudy": False,
            "role": "PRESERVED_LINEAGE_ONLY_NOT_SELECTED_INPUT",
            "artifactName": "kr-model-raw-inputs-36844599518",
            "artifactId": 11157875265,
            "producingRunId": 36844599518,
            "archiveSha256": "42eeb18b7a5c88816629036f472a93057b6a9be4768ad47292ba0d2750b4cce7",
            "inputIdentitySha256": "233df37ed205cc6b48828121e711417ccf961301dc58aa252430b343db9666a7",
            "krxCacheSha256": "3419d9d201f942b3c89be146b8f696679c8105a5f00d8adb0dd2c5a655a80037",
        },
        "tradingValueBasis": "PROXY_ASTRADED_CLOSE_X_VOLUME",
        "proxyLimitation": "Close times volume is not official ACC_TRDVAL. Capacity is a proxy-based research assumption, never a measured intraday execution claim.",
        "horizons": [21, 63, 126, 252],
        "familyHorizons": manifest["horizons"],
        "calendar": {
            "version": RC.CALENDAR_VERSION,
            "signal": "LAST_KR_SESSION_OF_COMPLETED_WEEK",
            "entry": "NEXT_KR_SESSION_CLOSE",
            "exit": "H_KR_SESSIONS_AFTER_ENTRY_CLOSE",
            "signalInformationFinalAt": "18:00 KST",
            "maturity": manifest["eligibleDateRange"]["lastMaturableSignalDate"],
        },
        "targets": {
            "basis": "BENCHMARK_RELATIVE_ADJUSTED_INDEX_RETURN_PARTIAL_DISTRIBUTIONS",
            "gross": "Close[exit]/Close[entry]-1; replay split-continuous dividend-forward accumulated index, not complete shareholder total return",
            "benchmarkRelative": "gross-stock minus gross-069500.KS on identical sessions",
            "industryRelative": "stock minus signal-cap-weighted leave-one-out industry; >=5 classified members, all peers valid, no renormalization over missing outcomes",
            "modelTarget": "within-date demeaned benchmarkRelative; common valid outcome mask; benchmark same-date intercept cannot affect ordering",
        },
        "baselines": registry["levelTwoBaselines"],
        "chronology": {
            "trainingStart": "2013-01-04",
            "evaluationYears": list(range(2016, 2027)),
            "refit": "ANNUAL_EXPANDING",
            "purge": "target exit strictly before training cutoff",
            "embargoSessions": 21,
            "cutoff": "21 KR sessions before first registered weekly signal of evaluation year",
            "minTrainingDates": 104,
            "minNamesPerTrainingDate": 30,
            "outcomeSelection": False,
        },
        "preprocessing": {
            "percentiles": "within full signal-date measured cross-section; average ties; fixed before validity gates",
            "imputation": "training-only date-balanced median percentile; all-missing training column inactive at evaluation",
            "missingIndicators": "one per registered feature, always present; no missing target imputation",
            "scaling": "training-only date-balanced mean and population SD; zero variance column scaled by 1",
            "evaluationMask": "common outcome-valid rows, >=one measured B4 column; augmented model cannot select a different population",
        },
        "linearModel": {
            "family": "DATE_BALANCED_RIDGE",
            "penalty": 1.0,
            "objective": "weighted mean squared error + penalty * sum(beta^2); intercept unpenalized",
            "dateWeight": "each training date weight 1/nDates; each eligible row 1/nNamesOnDate",
            "hyperparameterSearch": False,
        },
        "level1": {
            "statistics": [
                "rankIC",
                "withinIndustryRankIC",
                "tercileSpread",
                "withinIndustryTercileSpread",
                "topExcess",
            ],
            "primary": "direction-oriented raw top-minus-bottom tercile spread",
            "calibratedGate": "primary calibrated SN lower bound >0 in addition to BY q<=0.10",
            "ranksBeforeOutcomeGate": True,
            "binaryEventGroups": "J01 uses its frozen0/1 values for raw/within-industry groups, not arbitrary tied percentile cuts",
            "minMeasuredNames": 30,
            "minIndustryMembers": 5,
            "minGroupNames": 3,
            "minDates": 52,
            "minEvaluableShare": 0.80,
            "minYearDates": 13,
            "stability": ["year", "chronologicalHalves", "I01_marketState", "liquidityTier"],
            "positiveYearShare": 0.60,
            "halves": "both direction-oriented spread estimates strictly positive",
        },
        "level2": {
            "comparisons": [
                "standaloneBaselines",
                "addOneFamily",
                "leaveOneFamilyOut",
                "residualizedInformation",
                "conditionalSlopes",
                "trainingOnlyRedundancy",
            ],
            "incrementalMetrics": ["pairedMseImprovement", "pairedRankWeightedSpreadImprovement"],
            "redundancy": "training-only within-date Spearman, equal mean across dates with >=30 paired names; absolute rho>=0.8 connected components",
            "primaryP": "max(two two-sided calendar-time SN p-values); both estimates must be positive",
            "residualization": "per signal date OLS projection of candidate percentile on B4 percentiles/indicators, without outcomes; slope with same B4 controls",
            "conditionalSlopes": "date OLS with B4 controls and fixed 0.5 imputation/indicators; non-identifiable candidate slope withheld; outcomes common-mask only",
            "residualVariationFloor": 1e-10,
            "residualGate": "at least52 dates and80% scheduled share with positive oriented residual spread; exact/numerical B4 duplication cannot piggyback a family increment; no extra significance claim",
            "conditionalSlopeErrors": "Newey-West lag ceil(H/5)-1 on date slopes; DESCRIPTIVE, never gates",
            "identicalPredictions": "qualified identical common-sample forecasts are structurally REDUNDANT; zero self-normalizer is not claimed significant",
            "commonSample": "one validity mask and identical row identities for paired metrics, no complete-case comparison",
        },
        "interactions": [
            {**ix, "readiness": manifest["interactions"][ix["interactionId"]]}
            for ix in registry["levelThreeInteractions"]
        ],
        "level3": {
            "cells": "Phase B average-rank terciles; X1 rows.b08Confirmed binary; X6 I01<1 stressed, >=1 normal, across dates",
            "contrast": "(HH-HL)-(LH-LL); X1 confirmation spread cheap vs expensive; X3 stock spread leading vs lagging",
            "negativeControls": "X2 permute momentum, X5 permute liquidity with seed/date hash; X6 last weekly regime at or before date minus one year; X4 blocked and proxy never substituted",
            "seed": 20261009,
            "minCell": 3,
            "minNames": 30,
            "minDatesPerState": 52,
            "familyP": "X1/X3 primary four-corner contrast already subtracts the expensive/lagging control once; X2/X5 max(primary and primary-minus-permuted-control SN p); X6 descriptive",
            "nomination": "X1-X5 require corrected interaction support and Levels 1-2 for an untested component; X6 descriptive regime contrast cannot nominate",
        },
        "inference": {
            "engine": "pipeline.alpha_inference_calibration_v4.calendar_time_sn_interval",
            "criticalValue": 66.57,
            "nearZeroTolerance": 1e-12,
            "inferentialHorizons": [21, 126],
            "descriptiveHorizons": [63, 252],
            "minCalendarWeeks": {"21": 78, "126": 312},
            "attribution": "exact telescoping per-session increments; sum calendar contribution equals sum signal-date statistic to 1e-9",
            "pValue": "scalar SN Brownian-bridge limit tail: 2/pi integral_0^(pi/2) sqrt(a/sinh(a)) dtheta, a=sqrt(pivot)/sin(theta)",
            "pValueLimit": "asymptotic development p, NOT finite-sample tail calibration; no Gaussian t substitution for SN; X6 unequal state contrasts descriptive",
            "rankIC": "DESCRIPTIVE_NW_ONLY",
            "portfolioBootstrap": {"blockSessions": 126, "draws": 499, "seed": 20261009, "role": "descriptive only"},
        },
        "multiplicity": {
            "level1": {
                "method": "BY",
                "q": 0.10,
                "scope": "within family over every inferential feature-horizon primary spread; unavailable p=1 retained",
            },
            "level2": {
                "method": "HOLM",
                "alpha": 0.05,
                "scope": "all registered add/remove family-horizon comparisons; descriptive/blocked slots p=1 retained",
            },
            "level3": {
                "method": "HOLM",
                "alpha": 0.05,
                "scope": "six registered hypotheses, including blocked X4 and descriptive X6 p=1",
            },
        },
        "terminalPolicy": {
            "basisPolicyFunction": "pipeline.alpha_opportunity_v4_eligibility.label_eligibility",
            "uniformEvidenceRule": "all securities evaluated identically from own completeness evidence, never a future-termination flag",
            "knownBasisGap": "withhold every observation whose security has unresolved audited distribution basis; unknown unaudited basis explicitly qualified",
            "unknownConsideration": "invalid window, NEVER zero payoff, last-price exit, successor guess or unilateral model exclusion",
            "resolvedExchange": "requires cited cash/stock consideration and full successor distribution-adjusted path; unavailable pinned chain blocks",
            "portfolioRule": "select on signal information BEFORE label mask; any selected or reference constituent unpriceable blocks the whole paired portfolio comparison",
            "statisticalRule": "symmetric valid-name mask; qualified surviving-sample development associations allowed; no unconditional delisting-risk claim",
            "disclosures": [
                "affectedSecurities",
                "affectedNameDateHorizon",
                "referenceUniverseShare",
                "lostByYear",
                "lostByIndustry",
                "preGate",
                "evaluable",
            ],
        },
        "economics": {
            "conditionalPolicies": {
                "X1": "cheap B05 top tercile AND b08Confirmed=1; rank B05",
                "X2": "A05 top tercile AND D05 bottom tercile; rank A05",
                "X5": "F01 bottom tercile AND E01 bottom tercile (liquid); rank negative F01",
                "forecast": "existing FULL H126, no new fitted model",
                "trigger": "interaction Holm passes AND any previously untested component passes primary Levels1/2/residual/stability gates",
                "X3": "control-only components: earlier untested-component gate unavailable; conditional economics NOT_TRIGGERED",
                "X4": "SOURCE_BLOCKED",
                "X6": "DESCRIPTIVE_ONLY_NOT_TRIGGERED",
            },
            "basket": "equal-weight direction-oriented top tercile, diagnostic only",
            "slots": {"maximum": 5, "weight": 0.20, "maxPerIndustry": 2},
            "fallbacks": ["CASH", "PASSIVE_BENCHMARK"],
            "cashReturn": 0.0,
            "cashMeaning": "zero-yield KRW accounting assumption",
            "entryRule": "positive OOF date-centered forecast greater than stock+fallback round-trip costs, top oriented tercile and signal tradable/capacity gates",
            "exAnteCosts": "entry eligibility uses signal-date tax and fees only; realized exit uses exit-date effective tax, never future tax information for selection",
            "capitalKrw": 50_000_000,
            "capitalEvolution": "initial capital compounded by prior valid net block returns; unpriceable prior NAV blocks every later block, no fixed-capital capacity fiction",
            "feeFinancing": "20% slots are cash budgets inclusive of entry fees; executed asset weight=budget/(1+entry fee), including passive fallback and reference; no borrowing",
            "pairedPolicies": "identical predetermined anchors; any unpriceable policy blocks the joint policy comparison; valid isolated diagnostics retain explicit boundaries",
            "orderShareMedianValue": 0.01,
            "medianWindow": 60,
            "rebalance": "nonoverlapping H-session blocks anchored to first registered evaluation signal within feature usable range, no data-dependent rescheduling",
            "roundTrips": "fully liquidate every registered block, charge dated entry and exit, no leverage or optimizer",
            "liquidity": "ALL/HIGH/LOW in both diagnostic and slot policies, both fallbacks; only ALL/HIGH gate; top/bottom halves of signal-date E03; E03 only capacity, E01 only alpha; never double count cost savings",
            "decomposition": [
                "A_marketExposure",
                "B_industryAllocation",
                "C_stockSelection",
                "D_riskFactorExposure",
                "E_cost",
                "F_fallback",
                "G_residual",
            ],
            "attributionIdentity": "gross=A+B+C+F+G; net adds E; D is a descriptive nested explanation of C, not a second additive credit",
            "riskFactorColumns": sorted(
                set(registry["levelTwoBaselines"]["B4_COMBINED_SIMPLE"]) | {"F01_totalVolatility63"}
            ),
            "riskExposure": "descriptive block excess and C regressions on B4 columns plus registered F01 factor-mimicking rank spreads; intercepts cannot establish alpha",
            "support": "net top basket excess positive in both fallbacks and high liquidity half; slot stock-selection positive; reconciled benchmark required",
        },
        "costs": {
            "commissionBps": 5.0,
            "quotedSpreadBps": 12.0,
            "benchmarkEachWayBps": 15.0,
            "commissionSpreadSource": "docs/kr-alpha-atlas-methodology.md",
            "sellTaxSource": "pipeline/benchmark_alpha.py REALISTIC_COSTS[KR].sellTaxSchedule",
            "sellTaxSchedule": [
                {"effectiveFrom": r["effectiveDate"], "sellTaxBps": r["sellTaxBps"]}
                for r in REALISTIC_COSTS["KR"]["sellTaxSchedule"]
            ],
            "benchmarkCostIsAssumption": True,
        },
        "benchmarkIntegrity": {
            "status": manifest["benchmark"]["reconciliationStatus"],
            "claimGate": "BLOCKED_UNVERIFIED",
            "externalCheck": "authoritative definition-compatible same-session annual total return differences <=0.005 in every year",
            "frozenDecision": "no compatible external input pinned: absolute economic claims blocked for this run; rankings and within-date contrasts retained",
        },
        "decision": {
            "verdicts": VERDICTS,
            "order": VERDICTS,
            "level4Trigger": "primary family horizon Level1 BY passes + stability + Level2 ADD family Holm passes; interactions also need Holm and controls",
            "noCandidateAllowed": True,
            "supportMeaning": "independent of simpler factors in DEVELOPMENT, never independent confirmation or promotion",
        },
        "sourceLimitations": manifest["knownLimitations"],
        "untestedQuestion": "Inflation/growth-conditioned CPI or labor-market sign reversals: untested, PIT macro unavailable; prospective or later US program only. X6 is market trend/volatility.",
        "compute": {
            "workers": 1,
            "threads": 1,
            "wallSeconds": 5400,
            "memoryBytes": 8 * 1024**3,
            "maxRows": 85680,
            "maxSignalDates": 714,
            "maxPriceCells": 1_100_000,
            "maxProjectionFits": 73 * 714,
            "maxConditionalSlopeFits": 73 * 714,
            "maxEconomicPolicies": 41 * 12,
            "maxBootstrapDraws": 41 * 12 * 499,
            "noSearch": True,
            "failure": "resource limit before lock engineering blocker; after lock consumed failure, durable attempt, no retry",
        },
        "runtime": {
            "python": "3.11.16",
            "numericalExtras": {"threadpoolctl": "3.7.0", "joblib": "1.6.0"},
            "packages": {
                line.split("==")[0]: line.split("==")[1]
                for line in (root / "requirements.txt").read_text().splitlines()
                if "==" in line
            },
            "environment": {"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"},
        },
        "lifecycle": {
            "authorizationPath": "research_specs/kr-alpha-atlas-phase-c-execution-authorization.json",
            "authorizationPresent": False,
            "lockPrefix": "refs/tags/" + STUDY + "-execution-lock",
            "resultPath": "docs/results/" + STUDY + "-result.json",
            "artifactPrefix": STUDY + "-results-",
            "order": [
                "actualMergedMain",
                "explicitCommittedHumanAuthorization",
                "specAndCodeHashes",
                "noPreviousResult",
                "noLock",
                "retrieveExactSnapshot",
                "verifyEveryInput",
                "outcomeFreeReadiness",
                "runtime",
                "syntheticChecks",
                "permanentAtomicLock",
                "firstOutcomeAccess",
                "oneIntegratedStudy",
                "durablePersistence",
                "STOP",
            ],
            "postLockFailure": "consumed, no unlock/retry/re-fit/rethreshold; only exact-byte recovery of already-written files/logs is permitted",
            "postOutcomeDiagnostic": "requires separate explicit authorization, labelled EXPLORATORY_POST_OUTCOME, cannot change result",
        },
        "stopping": [
            "one formal execution only",
            "structured partial results retain unaffected comparisons",
            "zero candidates valid",
            "Phase D closes KR history regardless of outcome",
        ],
    }
    groups = model_groups(spec)
    # Mechanical calendar-only refit schedule: H252 in 2016 has just 99 past
    # matured weekly targets (below 104), and 2026 has none to evaluate.
    from pipeline.alpha_opportunity_v3_survivorship import weekly_grid
    from .labels import window_sessions

    days = RC.sessions("2013-01-01", spec["developmentCutoff"], "KR")
    dates = weekly_grid(RC.sessions("2013-01-01", "2026-12-31", "KR"), spec["developmentCutoff"])
    schedule = []
    model_fits = 0
    for h, g in groups.items():
        for year in spec["chronology"]["evaluationYears"]:
            first = min(d for d in dates if d.startswith(str(year)))
            cutoff_pos = int(days.searchsorted(first)) - spec["chronology"]["embargoSessions"]
            history = [
                d
                for d in dates
                if (lambda w: w[2] is None and w[1] < cutoff_pos)(
                    window_sessions(days, d, h, spec["developmentCutoff"])
                )
            ]
            mature = any(
                d.startswith(str(year)) and window_sessions(days, d, h, spec["developmentCutoff"])[2] is None
                for d in dates
            )
            planned = len(history) >= 104 and mature
            schedule.append(
                {
                    "horizon": h,
                    "year": year,
                    "calendarPastTargets": len(history),
                    "models": len(g) if planned else 0,
                    "status": "PLANNED_SUBJECT_TO_VALID_TRAINING_ROWS" if planned else "CALENDAR_BLOCKED_NO_FIT",
                }
            )
            model_fits += len(g) if planned else 0
    residual_fits = sum(10 if h == 252 else 11 for f in features for h in f["registeredHorizons"])
    spec["compute"].update(
        featureHorizonTests=sum(len(f["registeredHorizons"]) for f in features),
        standaloneBaselineCells=5 * 4,
        fullModelCells=4,
        familyComparisonCells=sum(len(g) - 6 for g in groups.values()),
        registeredInteractions=6,
        executableInteractions=5,
        modelGroups={str(h): list(g) for h, g in groups.items()},
        plannedPredictiveFits=model_fits,
        calendarRefitSchedule=schedule,
        maxPredictiveFits=model_fits,
        residualCrossSectionFits="at most 73*714 outcome-free projections",
        conditionalSlopeFits="at most 73*714 descriptive date regressions",
        annualPreprocessingFits=model_fits,
        annualResidualEquivalentBudget=residual_fits,
        estimatedMinutes={"featurePreparation": 30, "labelsAnalysisModelsEconomics": 45, "persistenceMargin": 15},
    )
    safe_inputs = [
        "AGENTS.md",
        ".github/workflows/tests.yml",
        "docs/workflow-inventory-addendum.md",
        "docs/kr-alpha-atlas-phase-c.md",
        "docs/kr-alpha-atlas-phase-c-readiness-ko.md",
        MANIFEST,
        REGISTRY,
        RESULT_SCHEMA,
        WORKFLOW,
        "requirements.txt",
        "requirements-dev.txt",
        "requirements-kr-alpha-atlas-phase-c.txt",
        "docs/results/kr-alpha-atlas-phase-b-readiness.json",
        "docs/results/kr-alpha-atlas-phase-b-source-feasibility.json",
        "docs/kr-alpha-atlas-methodology.md",
        "docs/kr-alpha-atlas-execution-roadmap.md",
        "docs/results/kr-terminal-action-reconstruction-v2.json",
        "tests/test_kr_alpha_atlas_phase_c.py",
    ]
    package_files = [str(p.relative_to(root)) for p in (root / "pipeline/kr_alpha_atlas_phase_c").glob("*.py")]
    closure = set(import_closure(ENTRY + package_files, root))
    closure.update(package_files)
    closure.update(safe_inputs)
    spec["dependencyHashes"] = {p: file_hash(root / p) for p in sorted(closure)}
    # Never parse a sealed outcome. Opaque hashes protect existing bytes, no optimization.
    spec["protectedHashes"] = {
        str(p.relative_to(root)): file_hash(p)
        for folder in ("research_specs", "docs/results")
        for p in sorted((root / folder).rglob("*"))
        if p.is_file() and "kr-alpha-atlas-phase-c" not in p.name
    }
    return spec


def validate(spec, root=ROOT):
    expected = build(root)
    if spec != expected:
        raise ValueError("INCOMPLETE_MUTATED_OR_UNSUPPORTED_REGISTRATION")
    assert spec["compute"]["featureHorizonTests"] == 73
    assert spec["compute"]["plannedPredictiveFits"] == 574
    assert spec["compute"]["familyComparisonCells"] == 30
    ids = {f["featureId"] for f in spec["eligibleFeatures"]}
    if ids & set(spec["roles"]["constructionOnly"]):
        raise ValueError("CONSTRUCTION_FEATURE_AS_ALPHA")
    for f in spec["eligibleFeatures"]:
        if f["pitSafetyVerdict"] != "PIT_SAFE":
            raise ValueError("PIT_UNSAFE_FEATURE")
    return spec


def load(root=ROOT):
    root = Path(root)
    raw = (root / SPEC).read_bytes()
    if file_hash(root / SPEC) != (root / SIDECAR).read_text().strip():
        raise ValueError("SPEC_DIGEST_CHANGED")
    spec = json.loads(raw)
    validate(spec, root)
    return spec


def calendar_facts(spec):
    days = RC.sessions("2013-01-01", spec["developmentCutoff"], "KR")
    from pipeline.alpha_opportunity_v3_survivorship import weekly_grid

    dates = weekly_grid(RC.sessions("2013-01-01", "2026-12-31", "KR"), spec["developmentCutoff"])
    actual = {f"H{h}": RD.last_maturable_signal_date(dates, h, spec["developmentCutoff"]) for h in spec["horizons"]}
    if actual != spec["calendar"]["maturity"] or len(dates) != 714:
        raise ValueError("CALENDAR_MATURITY_MISMATCH")
    return {
        "sessionCount": len(days),
        "weeklyDates": len(dates),
        "maturity": actual,
        "calendarSha256": digest([str(d.date()) for d in days]),
        "outcomeReads": 0,
    }
