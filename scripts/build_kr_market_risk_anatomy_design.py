#!/usr/bin/env python3
"""Write research_specs/kr-market-risk-anatomy-v1-design.json — the PRE-SOURCE FREEZE of the scientific design — and its SHA-256 sidecar.

The design is built from the module registries so the document cannot drift from the code. It reads no source, price, return or outcome.
After the pre-source freeze commit this file is never edited: a later spec only references its digest."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import kr_market_risk_anatomy as M  # noqa: E402
from pipeline import kr_market_risk_sources as S  # noqa: E402
from pipeline.kr_model_portfolio_execution import digest  # noqa: E402

PATH = ROOT / "research_specs" / (M.STUDY + "-design.json")


def build():
    S.validate_registry()
    design = {
        "studyId": M.STUDY, "kind": "PRE_SOURCE_FREEZE_SCIENTIFIC_DESIGN",
        "scientificStatus": M.SCIENTIFIC_STATUS, "scientificStatusMeaning": list(M.SCIENTIFIC_STATUS_MEANING),
        "phase": "ANATOMY_SOURCE_FOUNDATION_AND_HARNESS_ONLY_NO_OUTCOME_COMPUTED",
        "architectureRole": {"layer": "MARKET", "question": "how much equity risk should be taken",
                             "mustNot": ["rank stocks", "rank industries", "predict the exact crash date", "search for the best market-timing rule", "size or backtest a portfolio"],
                             "laterStudy": "kr-market-risk-model-v1 owns risk-budget backtesting and optimisation"},
        "objective": "Determine whether information observable at time t identifies elevated KR equity-market downside vulnerability and/or detects a developing large drawdown "
                     "early enough to reduce a meaningful part of the remaining loss.",
        "conceptualSequence": ["SLOW VULNERABILITY", "TRANSITION / FINANCIAL STRESS", "FAST MARKET BREAK", "eventual future risk-budget decision (not this study)"],
        "boundary": {"isAMarketRiskModel": False, "isAPortfolioStudy": False, "isStockSelection": False, "isIndustrySelection": False, "isAProductionRecommendation": False,
                     "isEvidenceOfProspectivePredictability": False, "passFailSemantics": "NONE", "mayChooseABestFeature": False, "mayChooseABestTrigger": False,
                     "mayOptimiseAThreshold": False, "mayAddAFeatureAfterOutcomes": False, "mayChangeHorizonsOrCutoffsAfterOutcomes": False,
                     "mayChangeEpisodeAlgorithmAfterOutcomes": False, "mayNameEpisodesByHand": False, "outcomeExecutionInThisChange": False},
        "tiers": {
            "CORE_LONG_HISTORY": {"purpose": "span several stress regimes including 2008", "inputs": "KR benchmark price index plus market-observed Treasury, policy-rate, credit, VIX and USD/KRW series",
                                  "neverTruncatedTo": "the start of EXTENDED_KR_INTERNALS", "requiredByDecision": True},
            "EXTENDED_KR_INTERNALS": {"purpose": "cross-sectional KR market internals where a PIT universe exists", "starts": "materially later (PIT Top120 membership from 2015-01-02)",
                                      "requiredByDecision": False, "neverReconstructedFrom": "today's constituents"}},
        "everyResultStates": ["actual sample start", "actual sample end", "coverage", "exact valid-date counts", "exact event counts"],
        "primaryReference": {
            "rule": "Walk the KOSPI 200 routes in REFERENCE_PRIORITY and take the first that passes every identity/coverage/semantics test; only if none passes may the KOSPI composite price index be chosen, and the decision says so. "
                    "No splice, no silent substitution, never chosen on result quality.",
            "priority": list(S.REFERENCE_PRIORITY), "familyOrder": list(S.PRIMARY_FAMILY_ORDER), "robustnessReference": S.ROBUSTNESS_REFERENCE,
            "basis": "PRICE INDEX LEVEL; never described as total shareholder return; the ETF robustness reference is the as-traded close, dividends not reinvested",
            "freeze": ["exact instrument identity", "source", "calendar (XKRX sessions of the pinned repository calendar)", "currency", "basis", "first and last usable date", "missing-date semantics (a missing session is missing; no fill)"],
            "tests": {"firstDateNoLaterThan": S.REFERENCE_FIRST_DATE_NO_LATER_THAN, "sessionCoverage": S.REFERENCE_SESSION_COVERAGE, "fullRangeCoverage": S.REFERENCE_FULL_RANGE_COVERAGE,
                      "maxConsecutiveMissingSessions": S.REFERENCE_MAX_CONSECUTIVE_MISSING, "maxDroppedRowShare": S.REFERENCE_MAX_DROPPED_SHARE, "freshnessDays": S.REFERENCE_FRESHNESS_DAYS,
                      "windows": {k: list(v) for k, v in S.CORE_WINDOWS.items()}},
            "vendorCrossCheck": {"relativeTolerance": S.VENDOR_CONFLICT_REL_TOLERANCE, "maxConflictShare": S.VENDOR_CONFLICT_MAX_SHARE, "minCommonDates": S.VENDOR_CONFLICT_MIN_COMMON_DATES,
                                 "effect": "a CONFLICT against another route to the same index blocks the choice"}},
        "pitDiscipline": {
            "classes": {"MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY": "an unrevised market quote with a conservative availability lag; usable, never called PIT_EXACT",
                        "PIT_EXACT": "only with retained release evidence", "REVISED_HISTORY": "never backdated, never a primary predictor", "NOT_AVAILABLE": "not built"},
            "approximateLagsNeverUpgradeAClass": True, "missingStaysMissing": True, "noBackfill": True, "noFutureInterpolation": True, "noCurrentValueStampedOnHistory": True,
            "lagCalendarDays": dict(M.LAG_CALENDAR_DAYS), "staleCarryForwardDays": M.FRED_DAILY_STALE_DAYS,
            "rule": "a feature at KR session t sees the latest observation whose availableFrom (observation date + lag) is <= t",
            "ecos": "ECOS-derived series are REVISED_HISTORY by the repository contract and are excluded as predictors",
            "currentEcosLeadingIndexIsNeverAPrimaryPredictor": True},
        "sources": {k: v for k, v in S.SOURCES.items()},
        "rolePriority": {k: list(v) for k, v in S.ROLE_PRIORITY.items()},
        "rolePriorityRule": "the primary route unless it fails the weekly known-coverage gate in the 2007-2009 window; then the secondary; never both",
        "features": {k: {"family": v[0], "tier": v[1], "definition": v[2], "orientation": "higher = more downside risk"} for k, v in M.FEATURES.items()},
        "baselineTriggers": dict(M.BASELINE_TRIGGERS), "slowWarnings": dict(M.SLOW_WARNINGS),
        "existingOverlayReference": {"module": "pipeline/kr_market_risk_overlay.py", "rule": "close < mean of the last 200 closes; annualised vol63 > 25%; multipliers 1.0 / 0.7 / 0.4",
                                     "role": "frozen BASELINE to measure, not the answer; reproduced exactly by a literal replica proven equal to state_at"},
        "cadence": {"SLOW_VULNERABILITY": "monthly: last KR session of the month", "TRANSITION_FINANCIAL_STRESS": "weekly: last KR session of the week",
                    "FAST_MARKET_BREAK": "daily state for event timing; weekly snapshots for statistical tables", "KR_MARKET_INTERNALS": "weekly snapshots",
                    "slowerSeriesCarriedForward": "latest KNOWN observation only; carried daily rows are never independent evidence", "byFamily": dict(M.CADENCE),
                    "stepSessions": dict(M.CADENCE_STEP_SESSIONS)},
        "horizons": {"byFamily": {k: list(v) for k, v in M.HORIZONS.items()}, "common": list(M.COMMON_HORIZONS)},
        "targets": {
            "definitions": {"forwardReturn": "close[p+H]/close[p]-1", "forwardWorstLossFromSignal": "min(close[p+1..p+H])/close[p]-1 (positive when the path never falls below the signal value)",
                            "futureMaxDrawdown": "min over the path close[p..p+H] of close[j]/running max(close[p..j]) - 1 (<= 0; the signal-date value may be the peak)",
                            "futureRealizedVol": "std (ddof 1) of the H daily returns x sqrt(252)"},
            "status": {"MATURED": "window inside the data", "PENDING": "window past the last session", "UNRESOLVED_MISSING_SESSION": "any missing or non-positive close in the path (never filled)"},
            "downsideEventLabels": [f"forward worst loss <= {c:.0%}" for c in M.LOSS_CUTS], "cutsFrozen": list(M.LOSS_CUTS)},
        "drawdownEpisodes": {
            "algorithm": "running peak P = the latest close >= every earlier close; a close >= P ends any open episode as a recovery and restarts the peak at that date; a close < P opens an episode "
                         "(peak = the date P was last set) whose trough is the FIRST lowest close; depth = trough/peak-1; an episode open at the last observation is right-censored; missing "
                         "sessions are skipped (episodes use observed closes only)",
            "thresholds": list(M.EPISODE_THRESHOLDS), "primaryThreshold": M.PRIMARY_EPISODE_THRESHOLD, "namedEpisodes": "never; episodes are algorithmic only",
            "record": ["peak date", "trough date", "peak-to-trough drawdown", "recovery date or right-censored status"],
            "landmarks": {"peakOffsetsSessions": list(M.LANDMARK_OFFSETS), "firstDrawdowns": list(M.LANDMARK_DRAWDOWNS), "also": ["peak", "trough"]},
            "latestKnownStateAtLandmarks": ["yield-curve state", "policy direction", "credit-spread state and change", "VIX", "USD/KRW", "trend", "realised and downside volatility", "available internals"]},
        "earlyDamage": {"triggerWindow": "[peak, trough]; a state already on at the peak gives delay 0 and loss 0 and is flagged",
                        "metrics": ["LossAtTrigger = close[trigger]/close[peak]-1", "DamageFractionAtTrigger = |LossAtTrigger|/|depth|", "RemainingDrawdownAfterTrigger = close[trough]/close[trigger]-1",
                                    "TriggerDelaySessions = trigger-peak"],
                        "statuses": ["TRIGGERED", "MISSED", "ACTIVATED_AFTER_TROUGH", "STATE_UNAVAILABLE"], "reportsContinuousDistribution": True,
                        "fixedCuts": list(M.DAMAGE_CUTS), "slowWarnings": "pre-peak lead time reported separately (active at peak with streak onset; on-then-off; never on); never mixed with a fast trigger"},
        "falseAlarmsAndRecovery": {"perTrigger": ["activations", "share of valid sessions adverse", "share of ON (and OFF) sessions followed within H63/H126 by -10/-15/-20% worst loss",
                                                 "activation streaks with no -10% drawdown within H63", "after each trough: sessions until the trigger's own off-state and the return missed meanwhile"],
                                   "noReentryOptimisation": True, "riskBudgetBacktestingBelongsTo": "kr-market-risk-model-v1"},
        "statistics": {"unit": "one market time series (not a cross-sectional IC)", "oriented": "higher = more risk",
                       "perFeature": ["time-series Spearman versus loss severity (-worst loss)", "versus max-drawdown severity", "versus future realised volatility",
                                      "event rates at -10/-15/-20 unconditional and when the past-only percentile state is high (>= %.2f)" % M.HIGH_STATE_PERCENTILE,
                                      "AUROC when >= %d events and >= %d non-events" % (M.MIN_EVENTS_FOR_AUROC, M.MIN_NONEVENTS_FOR_AUROC),
                                      "descriptive Newey-West standard error of the rank correlation (lag ceil(H/step))", "calendar-year table", "exact valid dates and event counts", "start and end"],
                       "noWinner": True, "noValidatedOrPredictiveLanguage": True, "multiplicity": "none applied; no isolated statistic is evidence"},
        "normalisation": {"method": "expanding past-only percentile (#less + 0.5 #equal)/n including t", "minimumObservations": dict(M.MIN_NORMALISATION_OBS),
                          "missing": "NaN, never imputed", "fullSampleZScoreForbidden": True,
                          "invariance": "the state at t is identical whether the data end at t or in 2026 (tested)"},
        "hypotheses": {
            "H1": "Yield-curve inversion / near-term policy-path weakness is primarily a slow vulnerability signal and should carry more information at H126/H252 than at H21.",
            "H2": "A policy-rate cut alone is not necessarily adverse; risk may be greater when easing follows prior curve vulnerability AND financial stress is worsening.",
            "H3": "Widening credit spreads / worsening external financial conditions contain transition information before or during large KR equity drawdowns.",
            "H4": "Fast trend/volatility deterioration may not predict the ultimate crisis in advance but may identify the early portion of a developing drawdown.",
            "H5": "The existing SMA200 + Vol63 overlay may reduce remaining drawdown, but its false-alarm and recovery-delay costs must be measured.",
            "H6": "KR market breadth/internal deterioration may add information beyond the index itself in the shorter PIT-safe extended sample.",
            "H7": "A slow-warning -> transition -> fast-break sequence may be economically more useful than any one signal; this study does not optimise or select a combination.",
            "status": "hypotheses, not truths; none is a result"},
        "literatureMotivation": {"role": "motivation only, never a result of this study",
                                 "references": ["Estrella and Mishkin (1996, 1998): term spread and recessions", "Engstrom and Sharpe (2019): near-term forward spread as a leading indicator",
                                                "Federal Reserve staff work comparing term spreads and recession probabilities", "Gilchrist and Zakrajsek (2012): credit spreads and business cycle fluctuations",
                                                "Favara, Gilchrist, Lewis and Zakrajsek (2016): recession risk and the excess bond premium (EBP is revised modern data and is not used)"]},
        "readiness": {"decisions": ["READY_FOR_MARKET_RISK_ANATOMY_EXECUTION", "DATA_BLOCKED_BEFORE_MARKET_RISK_ANATOMY"],
                      "coreGates": {"windows": {k: list(v) for k, v in S.CORE_WINDOWS.items()},
                                    "reference": S.REFERENCE_SESSION_COVERAGE, "fast": S.FAMILY_FAST_COVERAGE, "slow": S.FAMILY_SLOW_COVERAGE, "transition": S.FAMILY_TRANSITION_COVERAGE,
                                    "rule": "READY only if the primary reference, at least one slow family, one transition family and one fast benchmark-derived family are covered in 2007-2009, and "
                                            "usable coverage exists around 2020; not every candidate feature must cover the period; each missing candidate keeps its own coverage table"},
                      "transitionGateFeatures": "market-stress features only (HY/IG spread, VIX, USD/KRW); policy-only easing flags are tabulated but are not a gate",
                      "transitionGatePrefixes": list(S.TRANSITION_GATE_PREFIXES), "extendedTierRequiredForDecision": False, "failureReturns": "DATA_BLOCKED_BEFORE_MARKET_RISK_ANATOMY with exact blockers; the study is never quietly redefined as 2015+"},
        "sourceDiscipline": {"preSourceFreezeCommit": "contains this design, the pure algorithms and synthetic tests, before any source value is acquired",
                             "afterFreezeMay": ["verify source identity", "freeze raw bytes", "verify hashes", "verify date coverage", "verify missingness and timestamp integrity", "verify units and semantics"],
                             "afterFreezeMustNot": ["compute forward returns", "compute drawdowns", "identify crisis episodes", "generate result tables or plots", "tune thresholds, horizons or features",
                                                   "change hypotheses from observed values"],
                             "integrityRepair": "may only repair identity, parsing or transport and never the scientific design; a scientific change after outcome-containing history was inspected is a new version"},
        "lifecycle": {"resultPath": "docs/results/" + M.STUDY + "-result.json", "markerPath": "docs/results/" + M.STUDY + "-execution-started.json",
                      "executionLock": "refs/tags/" + M.STUDY + "-execution-lock plus -<specSha256>, atomic POST /git/refs; any existing ref refuses; failure before the lock spends nothing, after it consumes v1",
                      "sequence": ["merged current main", "committed exact spec", "exact frozen input identities", "no prior result", "no prior study lock", "label-free readiness gates",
                                   "durable lock", "first outcome or episode computation", "result artifact"]},
        "constants": {k: (list(v) if isinstance(v, tuple) else v) for k, v in {
            "annualisation": M.ANNUALISATION, "highStatePercentile": M.HIGH_STATE_PERCENTILE, "stressWorseningPercentile": M.STRESS_WORSENING_PERCENTILE,
            "easingThresholdPp": M.EASING_THRESHOLD_PP, "easingLookbackSessions": M.EASING_LOOKBACK_SESSIONS, "inversionLookbackSessions": M.INVERSION_LOOKBACK_SESSIONS,
            "overlayVolThreshold": M.OVERLAY_VOL_THRESHOLD, "overlayMultipliers": M.OVERLAY_MULTIPLIERS, "drawdownTriggerCut": M.DRAWDOWN_TRIGGER_CUT, "minTsObs": M.MIN_TS_OBS,
            "minYearObs": M.MIN_YEAR_OBS, "minEventsForAuroc": M.MIN_EVENTS_FOR_AUROC, "minNonEventsForAuroc": M.MIN_NONEVENTS_FOR_AUROC, "lossCuts": M.LOSS_CUTS,
            "episodeThresholds": M.EPISODE_THRESHOLDS, "primaryEpisodeThreshold": M.PRIMARY_EPISODE_THRESHOLD, "landmarkOffsets": M.LANDMARK_OFFSETS,
            "landmarkDrawdowns": M.LANDMARK_DRAWDOWNS, "damageCuts": M.DAMAGE_CUTS, "minNormalisationObs": M.MIN_NORMALISATION_OBS, "lagCalendarDays": M.LAG_CALENDAR_DAYS,
            "fredDailyStaleDays": M.FRED_DAILY_STALE_DAYS, "commonHorizons": M.COMMON_HORIZONS, "allHorizons": M.ALL_HORIZONS}.items()},
        "limitations": ["One market time series with a handful of independent stress episodes: every statistic is descriptive and heavily autocorrelated",
                        "The sample is historically known to the researchers; a preregistration does not make it independent",
                        "Availability dates are conservative approximations; no release timestamps are retained, so no source is PIT_EXACT",
                        "A price index excludes dividends; drawdowns are price drawdowns, not shareholder total return",
                        "KR policy rate, KR term spread, Near-Term Forward Spread and the Excess Bond Premium are not available as defensible historical predictors",
                        "Extended internals start in 2015 and depend on the preserved raw input artifact",
                        "No multiplicity correction; no feature or trigger is validated or predictive"],
    }
    return design


if __name__ == "__main__":
    design = build()
    PATH.write_text(json.dumps(design, sort_keys=True, indent=2, ensure_ascii=False) + "\n")
    PATH.with_suffix(".sha256").write_text(digest(json.loads(PATH.read_text())) + "\n")
    print(digest(design))
