"""Write the two Lane B prospective contracts (PROPOSED, not registered, not authorized). Outcome-free.

    python -m research.master_research_program_v1.market_industry.build_contracts

Every rule-bearing value is IMPORTED from the sealed modules (mapping tables, levels, costs, windows) so the contract cannot drift
from them; `test_contracts.py` rebuilds both payloads and requires byte equality with the committed JSON.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = "37f8cbf6"
SIGNAL_HISTORY = "0b10f54dfefdafa09470b1c0855bc26bf3c58ea5"


def _sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def _canon(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _seal(payload):
    payload = dict(payload)
    payload["contractSha256"] = hashlib.sha256(_canon({k: v for k, v in payload.items() if k != "contractSha256"})).hexdigest()
    return payload


def market_timing_contract():
    from pipeline import kr_market_risk_model as K
    from pipeline import rp1_c1_us_exposure as US
    spec_path = "research_specs/kr-market-risk-model-v1.json"
    us_spec = "docs/research-program/specs/rp1-c1-us-exposure-ladder-replication-v1.json"
    lag = {"H126": 26, "H252": 51}
    return _seal({
        "contractId": "market-timing-prospective-v1",
        "status": "PROPOSED_NOT_REGISTERED_NOT_AUTHORIZED",
        "evidenceClass": "PROSPECTIVE_PAPER",
        "outcomeFree": True,
        "question": "Does moving the equity exposure by the sealed market-state machine add value AT MATCHED AVERAGE EXPOSURE (TIMING > 0), "
                    "net of the cost of the moves, against holding the regional ETF?",
        "notTheQuestion": ["drawdown reduction against the ETF (that is effect A, achievable by a lower constant exposure)",
                           "re-fitting any window, threshold, lag, level or mapping on history"],
        "regions": {
            "KR": {"etf": "069500.KS", "etfReturnBasis": "TOTAL_RETURN (repository's reconciled 069500.KS series; same vendor at scoring)",
                   "stateMachine": "pipeline/kr_market_risk_model.py (sealed; imported, never copied)",
                   "sealedSpec": {"path": spec_path + "@" + BASE, "specSha256": (ROOT / "research_specs/kr-market-risk-model-v1.sha256").read_text().strip(),
                                  "fileSha256": _sha(spec_path)},
                   "sealedResult": "docs/results/kr-market-risk-model-v1-result.json@" + BASE + " decision.developmentNomination = "
                                   "NO_CANDIDATE_NOMINATED_CONTROL_RETAINED (development evidence only)",
                   "costs": {"buy": K.BUY_COST, "sell": K.SELL_COST, "source": "kr_market_risk_model.BUY_COST / SELL_COST"},
                   "cash": {"primary": K.CASH_RATE, "sensitivity": "BOK_POLICY_RATE_PROXY (data/bok-policy-rates.json; not investable)",
                            "rule": "a TIMING claim must hold in sign under both cash readings"},
                   "stateInputs": {"FAST": "FDR_KS200 close (already recorded weekly by rp1-b-h1-state-v1 state.fast)",
                                   "SLOW": "FRED DGS10 - DGS3MO re-steepening flag, month-end, FRED lag " + str(K.FRED_LAG_DAYS) + "d",
                                   "TRANSITION": "FRED VIXCLS level vs its own past weekly history (top fifth, min " + str(K.TRANSITION_MIN_OBS) + " obs)"}},
            "US": {"etf": "SPY", "etfReturnBasis": "TOTAL_RETURN (economic reading of the US replication)",
                   "stateMachine": "pipeline/rp1_c1_us_exposure.py layer_states/decision_schedule with market='US' (sealed KR rules, US calendar)",
                   "sealedSpec": {"path": us_spec + "@" + BASE, "fileSha256": _sha(us_spec)},
                   "sealedResult": "docs/research-program/results/rp1-c1-us-exposure-formal-20261024/README.md@" + BASE
                                   + " NO_CANDIDATE_NOMINATED_CONTROL_RETAINED / REPLICATED_CONTROL_RETAINED",
                   "costs": {"buy": US.US_BUY_COST, "sell": US.US_SELL_COST, "source": "rp1_c1_us_exposure.US_BUY_COST / US_SELL_COST"},
                   "cash": {"primary": "FRED DTB3 per rp1_c1_us_exposure.CASH_RATE_DEFINITION", "sensitivity": "ZERO",
                            "rule": "a TIMING claim must hold in sign under both cash readings"},
                   "stateInputs": {"FAST": "S&P 500 price index close (FRED SP500 / ^GSPC per the US spec registry)",
                                   "SLOW": "same FRED spread rule as KR", "TRANSITION": "same VIX rule as KR"}},
        },
        "candidates": {
            "primary": ["C0", "C1"],
            "recordedNotClaimed": ["C2", "C3"],
            "definitions": {c: K.CANDIDATES[c]["name"] for c in K.CANDIDATE_ORDER},
            "levels": list(K.LEVELS),
            "mappingTables": {c: K.mapping_table(c) for c in K.CANDIDATE_ORDER},
            "missingState": "sealed rule: a multiplier is defined only when every completion of the missing layers agrees; otherwise hold "
                            "the previous target (counted)",
        },
        "recording": {
            "cadence": "weekly: KR decision = KR week-end session close (prospective_receipt_core.is_weekly_decision_session); US decision = "
                       "US week-end session close (rp1_c1_us_exposure.period_end_sessions(market='US'))",
            "execution": "next session close of the same market",
            "receiptFields": ["signalDate", "executionDate", "layer states (SLOW, TRANSITION, FAST) or None with reason",
                              "every candidate's multiplier and hold flag", "input identities (SHA-256)", "codeIdentity", "specSha256",
                              "createdAtUtc inside the window (after signal close, before next open)"],
            "ledger": "append-only JSONL with digest chain (prospective_receipt_core); one ledger per region; never backfilled",
            "existingPaths": {"KR_FAST": "rp1-b-h1-state-v1 (RECORDING since 2026-10-30; see market_receipts_status.json)",
                              "KR_SLOW_TRANSITION": "MISSING", "US_ALL": "MISSING"},
        },
        "decomposition": {
            "module": "research/master_research_program_v1/market_industry/market_timing.py",
            "period": "one weekly execution-to-execution interval; x_t = the candidate target executed at the start of the period",
            "identity": "mean(R_overlay - R_E) = LEVEL + TIMING; LEVEL = (xbar - 1) mean(R_E - R_F); TIMING = mean((x - xbar)(R_E - R_F))",
            "staticControl": "constant exposure xbar of the SAME window (exposure-matched); TIMING = mean(R_overlay - R_static)",
            "costTerm": "stress x (buy x increase + sell x decrease) of exposure, build uncharged; TIMING_NET = TIMING - mean(COST)",
            "driftResidual": "realised drifting-path return minus the per-period model return is reported as a residual, never folded into TIMING",
        },
        "horizons": {
            "windows": {"H126": "weekly periods whose execution session lies within the first 126 sessions after the cohort's execution",
                        "H252": "same with 252 sessions"},
            "cohort": "every weekly receipt starts a cohort; within each cohort window TIMING_t^h and its own xbar_t^h are computed",
            "primaryHorizon": "H252", "secondaryHorizon": "H126",
            "primaryStatistic": "mean over matured cohorts of TIMING_NET_t^H252 at cost stress 1x",
        },
        "inference": {
            "method": "Newey-West (Bartlett) HAC on the cohort series; lag in weekly observations = ceil(h / 5) sessions-per-week overlap",
            "lags": lag,
            "family": ["KR-C0-H252", "KR-C1-H252", "US-C0-H252", "US-C1-H252"],
            "multiplicity": "Holm, one-sided alpha 0.05 over the four primary claims; H126 claims are secondary and descriptive",
            "calibrationPrerequisite": "the rp1-inference-calibration cells (KR/US H252) calibrate a different, cross-sectional statistic; a "
                                       "calibration cell for THIS time-series statistic at the realised depth must be registered before the "
                                       "first confirmatory read, otherwise every read is DESCRIPTIVE_ONLY",
            "costStress": [1.0, 2.0, 3.0],
            "costRule": "a claim needs the Holm-adjusted lower bound > 0 at 1x AND a positive point estimate at 2x; 3x is reported",
        },
        "minimumAccrual": {
            "basis": "weekly receipts; H252 cohorts first mature about 52 weeks after the first receipt",
            "H252": "no read before 6 NON-OVERLAPPING matured H252 windows per region (about 6 years of receipts + 252 sessions)",
            "H126": "no read before 6 non-overlapping matured H126 windows per region (about 3 years + 126 sessions)",
            "exposureVariation": "at least 4 exposure changes inside the read window; otherwise NO_DYNAMIC_EXPOSURE_OBSERVED (not a fail)",
            "interimPublication": "state counts, exposure-change counts and receipt integrity only; no return-based number before the minimum",
        },
        "classification": {
            "B_TIMING_SUPPORTED": "Holm lower bound of TIMING_NET > 0 at 1x, positive at 2x, same sign under both cash readings",
            "A_ONLY_LEVEL_RISK_REDUCTION": "overlay drawdown shallower than ETF but NOT shallower than the exposure-matched static control, "
                                           "and TIMING interval contains zero",
            "TIMING_NEGATIVE": "upper bound of TIMING_NET < 0",
            "NO_TIMING_EVIDENCE_INTERVAL_CONTAINS_ZERO": "otherwise",
            "INSUFFICIENT_ACCRUAL": "minimum accrual not met",
            "NO_DYNAMIC_EXPOSURE_OBSERVED": "fewer than 4 exposure changes",
            "RECEIPT_INTEGRITY_FAILED": "missed weekly receipts > 10% of due sessions, a backfilled or rewritten row, or a broken chain",
        },
        "failureRules": [
            "no threshold, window, lag, level, mapping or candidate is re-optimised on history or on receipts",
            "a missed week is MISSED, never backfilled; a region whose missed share exceeds 10% cannot claim",
            "historical development numbers (KR 2007-2026, US 1993-2026) are never pooled with receipts",
            "C2/C3 are recorded but cannot be promoted into the primary family after the fact",
            "an unfavourable read closes this contract version; a successor is a new id with its own registration",
        ],
        "productionEffect": "NONE: the operating default stays 100% regional ETF; no read authorizes an exposure change",
        "prerequisites": [
            "KR: a writer for SLOW/TRANSITION + all candidate multipliers (pipeline/kr_market_risk_model_receipts.py has the contract, no writer)",
            "US: a state recorder and ledger (none exists)",
            "owner registration of this contract (spec + code hash) before the first counted receipt; receipts before registration do not count",
            "a calibration cell for the time-series TIMING statistic (see inference)",
        ],
        "evidenceRefs": ["research_specs/kr-market-risk-model-v1.json@" + BASE, "pipeline/kr_market_risk_model.py@" + BASE,
                         "pipeline/rp1_c1_us_exposure.py@" + BASE, "docs/research-program/rp1-b-h1-prospective-state-v1-ko.md@" + BASE,
                         "signal-history@" + SIGNAL_HISTORY + " ledger/research-strategies/rp1-b-h1-state-v1/"],
    })


def industry_contract():
    anatomy_report = "docs/results/kr-industry-opportunity-anatomy-v1-report.md"
    return _seal({
        "contractId": "industry-relative-prospective-v1",
        "status": "PROPOSED_NOT_REGISTERED_NOT_AUTHORIZED",
        "evidenceClass": "PROSPECTIVE_PAPER",
        "outcomeFree": True,
        "question": "Does an industry ranked high by a pre-existing industry signal at the signal date earn a positive 6-12 month "
                    "total return relative to the regional ETF, net of the cost of holding it through its constituents?",
        "regions": {
            "KR": {"universe": "PIT KRX Top120 at the signal date (ledger/universe/kr), common shares; preferred shares follow the v4 "
                               "PREFERRED_SHARE_OF_ANCHORED_COMMON rule",
                   "classification": {"source": "KRX/KIND industry label observed AT the signal date, mapped by the frozen v4 14-group crosswalk "
                                                "(research_specs/kr-industry-membership-foundation-v4/crosswalk.json)",
                                      "version": "KR_INDUSTRY_MEMBERSHIP_FOUNDATION_V4 crosswalk; KRICS (announced 2026-09-22) only via a new version",
                                      "historicalStatus": "DATA_FOUNDATION_INSUFFICIENT_V4 (see kr-industry-foundation-status-v1.json); "
                                                          "prospective labels are PIT by construction",
                                      "smallGroups": "an industry with < 5 eligible names at the signal date is RECORDED but UNRANKED"},
                   "etf": "069500.KS total return", "costs": "weekly_decision.trade_cost_fraction (dated KR sell tax)",
                   "megaCap": "top-2 signal-date caps of the universe (mechanical, not named) and each basket's top1/top2 cap share"},
            "US": {"universe": "S&P 500 members visible at the signal date (us_sector_membership.members_on)",
                   "classification": {"source": "datasets/s-and-p-500-companies sector column at the latest commit published before the "
                                                "signal date; the recorder pins that commit and its raw-CSV SHA-256",
                                      "version": "GICS sector level (11 sectors as published); sub-industry not used",
                                      "staleness": "the snapshot age in days is recorded; a snapshot older than 35 days makes the receipt "
                                                   "STALE_CLASSIFICATION (recorded, excluded from claims)",
                                      "rights": "dataset label, not an index-provider file; license not verified beyond internal research"},
                   "etf": "SPY total return", "costs": "benchmark_alpha.REALISTIC_COSTS['US']",
                   "megaCap": "top-2 signal-date caps of the universe and each basket's top1/top2 cap share"},
        },
        "signals": {
            "rule": "limited to pre-existing candidates with existing descriptive readings; definitions as in the sealed KR industry anatomy "
                    "(research_specs/kr-industry-opportunity-anatomy-v1.json@" + BASE + "); no new feature, no re-measurement here",
            "candidates": {
                "REL_MOM_126": {"existingReading": anatomy_report + "@" + BASE + " (KR CAP H126 IC and tercile spread, descriptive)"},
                "BREADTH_ABOVE_MA_126": {"existingReading": anatomy_report + "@" + BASE + " (KR CAP H126, descriptive)"},
                "MEDIAN_ocfYieldProxy": {"existingReading": anatomy_report + "@" + BASE
                                         + " and docs/research-program/07-market-industry-stock-portfolio-hierarchy-ko.md@" + BASE
                                         + " sec 2.2 (sign not stable across periods)"},
            },
            "usNote": "US has no historical reading of any of the three; the US leg is an independent prospective sample",
        },
        "construction": {
            "module": "research/master_research_program_v1/market_industry/industry_relative.py",
            "cohort": "membership and caps fixed at the signal date; returns from the next session close for H126 / H252 sessions",
            "baskets": "equal-weight AND cap-weight industry total return, each minus the ETF total return on identical dates",
            "missingConstituent": "basket = None and counted (no renormalisation); a refused basket is excluded from BOTH sides of a "
                                  "comparison on that date; > 10% refused baskets on a date makes the date unreadable",
            "terminations": "a constituent without terminal consideration makes its basket None (prospective_receipt_core terminal rule)",
            "ranking": "industries ranked within date by each signal; top tercile (ties by industry name) vs ETF; top-minus-bottom tercile reported",
        },
        "horizons": {"primary": "H252", "secondary": "H126", "cadence": "weekly signal dates; one cohort per week"},
        "inference": {"method": "Newey-West HAC on the weekly cohort series", "lags": {"H126": 26, "H252": 51},
                      "family": ["KR-REL_MOM_126", "KR-BREADTH_ABOVE_MA_126", "KR-MEDIAN_ocfYieldProxy",
                                 "US-REL_MOM_126", "US-BREADTH_ABOVE_MA_126", "US-MEDIAN_ocfYieldProxy"],
                      "multiplicity": "Holm one-sided alpha 0.05 over the six H252 claims (top-tercile EW basket - ETF, net 1x cost)",
                      "calibrationPrerequisite": "a calibration cell for this statistic at the realised depth before any confirmatory read"},
        "diagnostics": ["cap-weighted vs equal-weighted reading (both published)", "top1/top2 cap share per basket",
                        "reading without the universe's top-2 caps (mechanical)", "names REPLACED vs weights RETARGETED turnover",
                        "share of the signal explained by the market state (TIMING contract states recorded on the same dates)"],
        "minimumAccrual": {"H252": "6 non-overlapping matured H252 windows per region", "H126": "6 non-overlapping matured H126 windows",
                           "minIndustriesRanked": "at least 6 ranked industries per date (KR historical minimum observed 6 sufficient groups)"},
        "decision": {
            "SUPPORTED": "Holm lower bound > 0 at 1x cost AND positive at 2x AND same sign for EW and CAP baskets",
            "CONCENTRATION_DEPENDENT": "supported on CAP but not on EW, or vanishes without the top-2 caps",
            "NO_EVIDENCE": "interval contains zero", "NEGATIVE": "upper bound < 0",
            "INSUFFICIENT_ACCRUAL": "minimum accrual not met", "SOURCE_BLOCKED": "classification or price source unavailable for > 10% of dates",
        },
        "failureRules": ["no signal, window, tercile cut, group map or cost is changed after the first counted receipt",
                         "KR historical industry results (anatomy, Phase C, integrated v1) are never pooled with receipts",
                         "a negative or null read closes this version; KRICS or a new taxonomy is a new contract id"],
        "independenceFromStockTrack": ["reads no stock-track score, rank or selection", "own ledger path, own receipts",
                                       "stock-within-industry is out of scope; a hierarchy comparison needs its own registration"],
        "productionEffect": "NONE",
        "prerequisites": ["a KR industry receipt writer (none exists)", "a US sector receipt writer that pins the dataset commit (none exists)",
                          "owner decision on small-group handling for KR", "owner registration before the first counted receipt"],
    })


def main():
    for name, payload in (("market-timing-prospective-contract-v1.json", market_timing_contract()),
                          ("industry-relative-prospective-contract-v1.json", industry_contract())):
        (HERE / name).write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(name, payload["contractSha256"])


if __name__ == "__main__":
    main()
