"""Write the frozen Stage 2 protocol (protocol-stage2.json + .sha256) from the code constants, the outcome-free
readiness and power evidence, and SHA-256 pins of every code and input file the Stage 3 harness reads.

    python -m research.market_risk_discovery_v1.stage2_protocol
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from . import stage3_execute as X

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
BASE = "research/market_risk_discovery_v1"

CODE = [f"{BASE}/__init__.py", f"{BASE}/stage2_design.py", f"{BASE}/panels.py", f"{BASE}/baseline_census.py",
        f"{BASE}/label_census.py", f"{BASE}/stage3_execute.py",
        "research/market_valuation_macro_overlay_v1/__init__.py",
        "research/market_valuation_macro_overlay_v1/features.py"]
INPUTS = [f"{BASE}/data/raw/yahoo-SPY-chart-20261110.json.gz", f"{BASE}/data/ssga-SPY-distributions.csv",
          f"{BASE}/data/alfred-BAA-asof-month-ends.csv", f"{BASE}/data/alfred-GS10-asof-month-ends.csv"]
EVIDENCE = [f"{BASE}/evidence/stage2-readiness.json", f"{BASE}/evidence/stage2-power.json",
            f"{BASE}/evidence/stage2-power-revision0-with-bootstrap-gate.json"]


def sha(rel: str) -> str:
    return hashlib.sha256((REPO / rel).read_bytes()).hexdigest()


def min_detectable(power: dict) -> dict:
    ok = [(float(d), v) for d, v in power["byDelta"].items() if float(d) > 0 and v["supportVerdictRate"] >= 0.8]
    if not ok:
        return {"delta": None}
    d, v = min(ok, key=lambda x: x[0])
    return {"delta": d, "medianRelativeRisk": v["medianRelativeRisk"], "supportVerdictRate": v["supportVerdictRate"],
            "meanEpisodeHitShare": v["meanEpisodeHitShare"]}


def build() -> dict:
    ready = json.loads((HERE / "evidence/stage2-readiness.json").read_text())
    power = json.loads((HERE / "evidence/stage2-power.json").read_text())
    return {
        "study": "market-risk-discovery-v1",
        "stage": "STAGE_2_PREREGISTRATION",
        "basedOn": {"pr": 363, "commit": "7c7fe4707e142ead70124231946567810b4c70de"},
        "evidenceClass": "EXPLORATORY_ON_OUTCOME_EXPOSED_HISTORY",
        "promotionEligible": False,
        "creditLabelJoinsWhileWritingThis": 0,
        "hypothesis": {
            "id": "P1",
            "statement": "At US month-end decisions where the existing price/volatility model is normal (FAST = 0), the "
                         "real-time credit signal WIDEN_3M_ABOVE_EXPANDING_P80 improves the 126-session first -15% "
                         "passage probability over a model using the continuous price information in the normal state.",
            "nullHypothesis": "Given gap200 and vol63, the credit flag carries no information about the label.",
            "direction": "one-sided: M2 better than M1"},
        "decisionTiming": {
            "decision": "after the close of the last XNYS session of each calendar month (US/Eastern)",
            "priceInputs": "SPY split-adjusted raw close through the decision close",
            "creditInputs": "ALFRED vintage in force on the calendar day BEFORE the decision session (H.15/Moody's "
                            "values released on the decision day arrive after the close); latest observation in it",
            "labelWindow": "sessions t+1 .. t+126 (the first tradable session after a month-end decision is t+1)",
            "etfExecutionForAnyLaterAllocationStudy": "next XNYS session close after the decision (t+1); a month-end "
                                                       "close is never used as the execution price of its own decision"},
        "signal": {
            "name": "WIDEN_3M_ABOVE_EXPANDING_P80",
            "selectedIn": "Stage 1, by alarm budget and coverage only, before any credit-label relation was read",
            "spread": "BAA - GS10 from the two month-end as-of ledgers; missing when either leg is missing or the two "
                      "legs' observation months differ (BAA stall 2016-11..2017-02 is missing, never filled)",
            "change": "as-of spread(decision month m) - as-of spread(m - 3); each value from its own decision's vintage",
            "flag": "change > numpy linear-interpolated 0.80 quantile of ALL strictly earlier defined changes; at least "
                    "12 earlier defined changes; otherwise undefined",
            "firstDefined": "1998-03", "definedMonths": 337,
            "undefinedHandling": "rows with an undefined flag are excluded from BOTH M1 and M2 (common sample)"},
        "baselineFAST": {
            "definition": "count of {close < 200-session mean incl. today, 63-session log-return std (ddof 1) x sqrt(252) "
                          "> 0.25} on SPY split-adjusted raw close; FAST = 0 is normal",
            "basis": "price (inherited unchanged); events use total return",
            "basisMismatch": ready["basis"]["fastPriceVsTotalReturn"],
            "m1Features": {"gap200": "close / mean(close over 200 sessions incl. today) - 1",
                           "vol63": "the same 63-session realised volatility FAST thresholds"}},
        "event": {
            "index": "SPY total return = raw close + SSGA issuer distributions reinvested at the ex-date close",
            "firstPassage": "first session with TR / running peak - 1 <= -0.15 while no episode is active",
            "episodeEnd": "first later session regaining the running peak recorded at the start",
            "riskSet": "sessions not inside an episode",
            "label": "1 if an episode starts in (t, t+126]; 0 if not and 126 sessions remain; else censored (None)",
            "episodesTotalReturn": ready["basis"]["episodesTotalReturn"],
            "episodesPriceBasisForComparison": ready["basis"]["episodesPrice"]},
        "sample": {
            "commonSample": "month-end decisions >= 1997-01-31, in the risk set, FAST = 0, flag defined",
            "structure": ready["structure"]["gate"], "commonSampleRows": ready["structure"]["commonSampleRows"],
            "censoredRows": ready["structure"]["censoredRows"]},
        "models": {
            "M0": "Jeffreys base rate (k + 0.5) / (n + 1) of matured training labels",
            "M1": "ridge logistic, intercept + standardised [gap200, vol63], lambda 1.0, intercept unpenalised",
            "M2": "M1 + standardised credit flag, same lambda and standardisation (training-window mean/sd; a "
                  "zero-variance column is set to 0)",
            "sameRowsRefitsAndTrainingSet": True,
            "noTuning": "no hyperparameter search; lambda, horizon, thresholds and windows are fixed here"},
        "walkForward": {
            "refit": "once a year at the first month-end session of the year (from the calendar)",
            "training": "common-sample rows whose 126-session label window ended on or before the refit session; an "
                        "early-resolved positive is not used early",
            "evaluationStart": "first year whose training set has >= 20 rows and positives from >= 2 episodes "
                               "(observed: 2001)",
            "evaluationRows": "labelled common-sample rows from the evaluation start"},
        "primary": {
            "statistic": "dBrier = mean(Brier(M1) - Brier(M2)) over evaluation rows",
            "null": "circular rotation of the defined credit-flag sequence (337 months), shifts 12..325 (314); M2 "
                    "refitted per shift; one-sided p = (1 + #{null >= observed}) / (1 + 314)",
            "exchangeability": "assumes the flag process is stationary enough that its alignment with the calendar is "
                               "exchangeable under H0; preserves persistence, FAST mask, labels and M1 exactly",
            "limitations": ["tests independence of the flag from the label process, which is stronger than "
                            "conditional independence given M1; a flag correlated with gap/vol but uninformative "
                            "beyond them is still a valid null case because it is re-fitted with M1 present",
                            "rotation joins regimes across the wrap point; the expanding-percentile flag is not "
                            "exactly stationary (its first years are noisier)",
                            "the minimum attainable p is 1/315"]},
        "corroboration": {
            "leaveOneEpisodeOut": "GATED: evaluation-side, no refit: dBrier with each evaluation episode's positive "
                                  "rows removed must stay > 0 for every episode",
            "blockBootstrap": "REPORTED ONLY: moving blocks of 12 evaluation rows, 9999 draws, seed 20261123, 95% "
                              "percentile interval of mean dBrier"},
        "preOutcomeRevisions": [{
            "id": "REVISION_1_BOOTSTRAP_NOT_GATED",
            "basis": "synthetic power only (evidence/stage2-power-revision0-with-bootstrap-gate.json); no real credit "
                     "value met any label",
            "change": "the block-bootstrap lower bound > 0 condition was removed from the support verdict and kept "
                      "as a reported interval",
            "reason": "with about 11 blocks over 5 evaluation episodes the bound passed 3.5% of null worlds and only "
                      "35% of worlds with a planted relative risk of about 6.6, where rotation passed 82% and "
                      "leave-one-episode-out 72.5%; it was the binding gate and an unreliable instrument at this "
                      "sample size. Rotation + leave-one-episode-out keeps the null support rate at 4.5%."}],
        "verdictRules": {
            "DATA_INSUFFICIENT": "the outcome-free structure gate fails (fewer than 3 evaluation episodes, 100 "
                                 "evaluation rows or 100 rotations)",
            "EXPLORATORY_INCREMENTAL_SUPPORT": "dBrier > 0 AND rotation p <= 0.05 AND dBrier > 0 with every single "
                                               "evaluation episode removed",
            "DIRECTIONAL_NOT_SEPARATED": "dBrier > 0 and either other condition fails",
            "NOT_DETECTED_UNDERPOWERED": "dBrier <= 0; never reported as evidence that credit has no effect",
            "ceiling": "no verdict is confirmatory; confirmation requires prospective receipts"},
        "holdConditions": {
            "rule": "a non-support verdict is a statement about this design's power, not about credit: the frozen "
                    "design detects only large effects (see powerSummary); any verdict other than support is reported "
                    "as 'not detected at this power'",
            "minimumDetectable": "smallest planted effect with support-verdict rate >= 0.8 in powerSummary; if none, "
                                 "the design cannot establish support at 80% power for any simulated effect",
            "measured": min_detectable(power)},
        "secondaryNotRealTime": "purged leave-one-episode-out cross-validation over all labelled common-sample rows "
                                "(7 episodes), descriptive dBrier only; it trains on the future and decides nothing",
        "auxiliary": ["log loss and its rotation p", "event hits per evaluation episode, lead sessions, false-alarm "
                      "share, and the hit count's rotation p (opportunity- and persistence-aware null)",
                      "calibration bins (0, .05, .10, .20, .40, 1)", "Brier skill of M1 and M2 vs M0"],
        "eventLevelNull": {k: ready["opportunityNull"][k] for k in (
            "evaluationEpisodeNullHitProbability", "nullHitDistribution", "criticalHitsAt5pct",
            "stage1BinomialCriticalHitsAt5pct", "tailProbabilityOfStage1CriticalUnderOpportunityNull")},
        "flagPersistence": ready["flagPersistence"],
        "powerSummary": power,
        "frozenConstants": X.frozen_constants(),
        "pins": {"code": {f: sha(f) for f in CODE}, "inputs": {f: sha(f) for f in INPUTS},
                 "evidence": {f: sha(f) for f in EVIDENCE}},
        "stage3Authorization": {
            "file": f"{BASE}/authorization-stage3.json",
            "requiredFields": ["protocolSha256", "pins", "approvedBy", "approvalQuote", "approvedAtUtc", "scope"],
            "verifyCommand": "python -m research.market_risk_discovery_v1.stage3_execute --verify-only",
            "executeCommand": "python -m research.market_risk_discovery_v1.stage3_execute --execute",
            "oneShot": "marker written before the first real credit value meets a label; any failure after it "
                       "consumes the study; no rerun, reseed or threshold change"},
    }


def main() -> int:
    spec = build()
    text = json.dumps(spec, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    X.PROTOCOL.write_text(text)
    digest = hashlib.sha256(text.encode()).hexdigest()
    X.PROTOCOL_SHA.write_text(f"{digest}  protocol-stage2.json\n")
    print(digest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
