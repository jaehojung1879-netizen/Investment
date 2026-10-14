"""Build the US factor research reboot inventory and roadmap from the repository's committed evidence.

    python scripts/build_us_factor_research_reboot.py [--check]

Outcome-blind and deterministic. Every measured number below is READ from a committed report (path + JSON pointer + the file's
SHA-256 are written next to it), never typed in; a factor without a committed measurement says UNMEASURED and names its blocker.
Writes `docs/us-readiness/us-factor-inventory-v1.json` and `docs/us-readiness/us-multifactor-research-roadmap-v1.json`.
`--check` rebuilds in memory and fails if either committed file differs (used by the tests).

Nothing here reads a price, a return, a label, a model output or a portfolio, and nothing here authorizes anything.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
READY = ROOT / "docs/us-readiness"
INVENTORY = READY / "us-factor-inventory-v1.json"
ROADMAP = READY / "us-multifactor-research-roadmap-v1.json"
BASE_MAIN = "0a9fb1d96219f4402d9eb341cabbb616f786e52d"

R = {
    "multifactor": "docs/us-readiness/us-multifactor-pit-readiness-v1.json",
    "phase3": "docs/us-readiness/us-alpha-phase3-readiness-v1.json",
    "unique": "docs/us-readiness/us-factor-unique-variation-v1.json",
    "capalloc": "docs/us-readiness/us-capital-allocation-feature-overlap-v1.json",
    "source": "docs/us-readiness/us-source-readiness-v1.json",
    "universe": "docs/us-readiness/us-universe-coverage-gap-v1.json",
    "survivorship": "docs/results/alpha-opportunity-model-v3-survivorship-audit.json",
    "fourfactor": "docs/results/four-factor-signal-attribution-audit-report.json",
    "acceleration": "docs/results/fundamental-acceleration-discovery-report.json",
    "benchmarkAlpha": "docs/results/benchmark-alpha-report.json",
    "p4readiness": "docs/us-readiness/us-cash-profitability-exploratory-readiness-v2.json",
    "h63": "docs/us-readiness/us-h63-inference-calibration-v1-result.json",
    "h63supplement": "docs/us-readiness/us-h63-inference-calibration-v1-supplement-result.json",
    "integration": "docs/us-readiness/us-factor-integration-readiness-v1.json",
}
_CACHE: dict[str, dict] = {}


def doc(key: str) -> dict:
    if key not in _CACHE:
        _CACHE[key] = json.loads((ROOT / R[key]).read_text(encoding="utf-8"))
    return _CACHE[key]


def get(key: str, pointer: str):
    node = doc(key)
    for part in pointer.strip("/").split("/"):
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


def m(key: str, pointer: str, denominator: str) -> dict:
    """A measured value with its provenance and its denominator."""
    return {"value": get(key, pointer), "source": R[key], "pointer": pointer, "denominator": denominator}


def sha(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


NONFIN_55 = "eligible non-financial S&P 500 member-dates on the 55 fixed sample dates (18,469; survivor-conditioned)"
ALL_55 = "price- and identity-eligible S&P 500 member-dates on the 55 fixed sample dates (23,160; survivor-conditioned)"
WEEKLY_ALL = "all S&P 500 member-dates on 715 weekly signal dates (359,526), including departed members without a price panel"


def uv(feature: str) -> dict:
    """Unique-variation reading of a feature from the Phase C measurement."""
    u = get("unique", "/uniqueVariationNonFinancial/" + feature)
    return {"source": R["unique"], "pointer": "/uniqueVariationNonFinancial/" + feature,
            "controlR2Mean": u["controlR2"]["mean"] if u["controlR2"] else None, "uniqueShareMean": u["uniqueShareMean"],
            "noiseFloorR2": u.get("noiseFloorR2"),
            "sectorR2SameRows": u["sectorR2SameRows"]["mean"] if u["sectorR2SameRows"] else None,
            "ownFamilyR2": u["ownFamilyR2"]["mean"] if u["ownFamilyR2"] else None,
            "ownFamilyPeers": u["ownFamilyPeers"], "medianNamesPerDate": u["controlR2"]["medianNamesPerDate"] if u["controlR2"] else None}


def avail(feature: str) -> dict:
    return m("unique", "/availabilityNonFinancialPct/%s/pct" % feature, NONFIN_55)


def rho(a: str, b: str) -> dict:
    pw = doc("multifactor")["featureRedundancy"]["pairwiseMeanRankCorrelation"]
    if b in pw.get(a, {}):
        return {"pair": [a, b], "meanRho": pw[a][b]["meanRho"], "source": R["multifactor"],
                "pointer": "/featureRedundancy/pairwiseMeanRankCorrelation/%s/%s" % (a, b)}
    return {"pair": [a, b], "meanRho": pw[b][a]["meanRho"], "source": R["multifactor"],
            "pointer": "/featureRedundancy/pairwiseMeanRankCorrelation/%s/%s" % (b, a)}


def rho3(a: str, b: str) -> dict:
    o = doc("phase3")["orderingOverlapMeanSpearman"][a][b]
    return {"pair": [a, b], "meanRho": o["meanRho"], "source": R["phase3"], "pointer": "/orderingOverlapMeanSpearman/%s/%s" % (a, b)}


UNMEASURED = {"status": "UNMEASURED"}

# Outcome-exposure shorthands. Each names the study and what it can and cannot support.
EXP_31 = {"status": "TESTED_OUTCOME_EXPOSED", "studies": ["regional-alpha-model-v1"],
          "note": "inside the 31-feature US model (Ridge/HGBR, annual walk-forward, H126 rank target); model-level NO_MODEL_EVIDENCE, "
                  "no per-feature reading was committed. Class C also covers positive-but-unstable patterns, so it is not evidence "
                  "against the feature. Re-testing it on the same history is not a new hypothesis."}
EXP_FF = {"status": "EXPLORATORY_INCONCLUSIVE", "studies": ["four-factor-signal-attribution-audit-v1"],
          "note": "read only as part of the production sleeve composite (sleeve percentile), H126, survivor-conditioned; every US "
                  "95% CI contains zero"}
NOT_TESTED = {"status": "NOT_TESTED", "studies": [],
              "note": "no committed study has related this characteristic to a later US return"}
ACCEL = {"status": "EVIDENCE_AGAINST_SPECIFIC_HYPOTHESIS", "studies": ["fundamental-acceleration-discovery-v1", "regional-alpha-model-v1"],
         "note": "pre-registered Case D on the composite of the four deltas: US standalone H126 IC -0.0056, 95% CI [-0.0295, +0.0183], "
                 "on the survivor-conditioned sample. Against the stated composite hypothesis only, not against every change signal."}

SURV = "SURVIVOR_CONDITIONED"


def f(fid, family, name, formula, *, units, direction, code, source, observable, pit, corp, sectors, hist, prosp, coverage,
      missing, adjusted, departed, identity, exposure, mechanism, confounders, redundancy, feasibility, measured_rank=None):
    return {"id": fid, "family": family, "name": name, "formula": formula, "units": units,
            "directionConvention": direction, "codePath": code, "dataSource": source, "publiclyObservableFrom": observable,
            "pitRequirements": pit, "corporateActionAndShareCountDependencies": corp, "sectorApplicability": sectors,
            "availability": {"historical": hist, "prospective": prosp}, "measuredCoverage": coverage, "missingReasonCodes": missing,
            "adjustedPriceDependency": adjusted, "departedSecurityDependency": departed, "identityRisk": identity,
            "outcomeExposure": exposure, "economicMechanism": mechanism, "majorConfounders": confounders,
            "measuredRedundancy": redundancy, "uniqueVariation": measured_rank, "feasibility": feasibility}


PRICE_PIT = "closes up to and including the signal date from the sealed replay-v16 total-return panel; a future price raises LookAheadError"
FILING_PIT = ("filing visible only strictly after max(availableFrom, acceptedDate) (SEC acceptance via Finnhub), latest visible period "
              "end, withheld when that period ended more than 180 days earlier; TTM is the finnhub_derive rollforward, never an annualisation")
PRICE_DEP = "needs a price panel for the name; 212 departed identities have none (survivor-conditioned history)"
FILING_DEP = "needs the name's price panel for eligibility; departed names without a panel are absent"
PROSP_PRICE = ("BLOCKED_PENDING_OWNER_APPROVAL: no persistent US daily price ledger runs on signal-history yet "
               "(owner-gated collector, docs/us-persistent-daily-collection-v1.md)")
PROSP_BS = ("BLOCKED_SOURCE: Finnhub financials-reported omits the balance sheet on filings first served from 2026-10-07; total assets "
            "unresolved (docs/us-finnhub-balance-sheet-coverage-ko.md, docs/us-total-assets-source-rescue-ko.md)")
SECTORS_NONFIN = "economically meaningful outside Financials and Real Estate; banks, insurers and REITs have no comparable operating line"
SECTORS_ALL = "all sectors"
TICKER_REUSE = "29 symbols were reused by a different issuer and 30 panel symbols do not carry the member's own history (v3 survivorship audit)"


def factors() -> list[dict]:
    out = []
    # ---------------- A. VALUATION ----------------
    for fid, name, num in (("A01", "earningsYield", "epsTtm"), ("A02", "bookYield", "bookValuePerShare"), ("A03", "fcfYield", "fcfPerShare")):
        cov_key = {"earningsYield": "valueEarnings", "bookYield": "valueBook", "fcfYield": "valueFcf"}[name]
        out.append(f(fid, "A_VALUATION", name, "%s / reconstructed as-traded close on the signal date" % num, units="ratio (1/yr of price)",
                     direction="higher = cheaper", code="pipeline/us_multifactor_inputs.py:value_yields",
                     source="sealed Finnhub PIT per-share field (finnhub_derive) / replay-v16 total-return close divided by the rebuilt dividend-split step",
                     observable="filing acceptance (strict next day) and the signal-date close", pit=FILING_PIT,
                     corp="numerator per-share figure uses a WEIGHTED-AVERAGE share count whose basis is not context-verified (SEC blocked); a split between filing and observation withholds the yield",
                     sectors="defined in all sectors; book yield is the conventional metric for banks, earnings/FCF yield is not comparable for them",
                     hist="AVAILABLE_WITH_CAVEATS", prosp=PROSP_PRICE,
                     coverage={"allSectors": m("multifactor", "/availabilityOverallPct/" + cov_key, ALL_55), "nonFinancial": avail(name)},
                     missing=["NO_VISIBLE_FILING", "REPORT_STALE", "NON_POSITIVE_NUMERATOR", "SPLIT_BETWEEN_FILING_AND_OBSERVATION", "NO_PRICE"],
                     adjusted="REQUIRES the as-traded price; the sealed close is a total-return index, so the price is reconstructed (round-trip exact on synthetic series)",
                     departed=PRICE_DEP, identity=TICKER_REUSE,
                     exposure={**EXP_FF, "note": EXP_FF["note"] + "; excluded from the 31-feature model (price basis unresolved)"},
                     mechanism="risk compensation for distress/duration and mispricing correction of extrapolated expectations",
                     confounders=["sector (book yield 25% of rank variance is sector)", "profitability (bookYield vs roe -0.68)", "momentum (-0.2)", "share-count basis"],
                     redundancy=[rho("earningsYield", "bookYield"), rho("earningsYield", "fcfYield"), rho("bookYield", "roe")],
                     feasibility="computable now with a disclosed reconstructed-price and share-basis caveat; a VERIFIED value family needs period-end share counts (SEC)",
                     measured_rank=uv(name)))
    out.append(f("A04", "A_VALUATION", "evToEbitda", "(market cap + net debt) / EBITDA TTM", units="ratio", direction="lower = cheaper",
                 code="NOT_IMPLEMENTED", source="needs PIT market cap, debt and cash detail, D&A", observable="n/a", pit="n/a",
                 corp="needs verified shares outstanding", sectors=SECTORS_NONFIN, hist="NOT_IMPLEMENTED", prosp="NOT_IMPLEMENTED", coverage=UNMEASURED,
                 missing=["NO_DEPRECIATION_CHAIN_IN_FINNHUB_DERIVE", "NO_DEBT_OR_CASH_DETAIL", "MARKET_CAP_PIT_UNRESOLVED"], adjusted="as-traded price",
                 departed=PRICE_DEP, identity=TICKER_REUSE, exposure=NOT_TESTED,
                 mechanism="capital-structure-neutral valuation", confounders=["leverage", "sector"], redundancy=[UNMEASURED],
                 feasibility="blocked: finnhub_derive.FLOWS has no D&A, the store has total liabilities only, and market cap needs verified shares"))
    out.append(f("A05", "A_VALUATION", "evToEbit", "(market cap + net debt) / operating income TTM", units="ratio", direction="lower = cheaper",
                 code="NOT_IMPLEMENTED", source="operating income TTM exists; EV does not", observable="n/a", pit="n/a",
                 corp="needs verified shares outstanding", sectors=SECTORS_NONFIN, hist="NEEDS_SOURCE_OR_IDENTITY_VERIFICATION", prosp="NOT_IMPLEMENTED",
                 coverage=UNMEASURED, missing=["MARKET_CAP_PIT_UNRESOLVED", "NO_DEBT_OR_CASH_DETAIL"], adjusted="as-traded price", departed=PRICE_DEP,
                 identity=TICKER_REUSE, exposure=NOT_TESTED, mechanism="capital-structure-neutral valuation", confounders=["leverage"],
                 redundancy=[UNMEASURED], feasibility="blocked on verified market cap and net debt"))
    out.append(f("A06", "A_VALUATION", "salesYield", "revenue TTM / market cap", units="ratio", direction="higher = cheaper", code="NOT_IMPLEMENTED",
                 source="revenue TTM (finnhub_derive) / share-count x as-traded close proxy", observable="filing acceptance", pit=FILING_PIT,
                 corp="market-cap proxy rests on an unverified weighted-average share basis", sectors=SECTORS_NONFIN,
                 hist="NEEDS_SOURCE_OR_IDENTITY_VERIFICATION", prosp=PROSP_PRICE,
                 coverage={"marketCapProxy": m("phase3", "/overall/logMarketCapProxyPct", NONFIN_55)},
                 missing=["SHARES_NOT_STATED", "SPLIT_BETWEEN_FILING_AND_OBSERVATION"], adjusted="as-traded price", departed=PRICE_DEP,
                 identity=TICKER_REUSE, exposure=NOT_TESTED, mechanism="valuation robust to negative earnings",
                 confounders=["margin level", "sector"], redundancy=[UNMEASURED],
                 feasibility="only with the market-cap PROXY as a declared sensitivity; never a primary value measure"))
    out.append(f("A07", "A_VALUATION", "sectorRelativeValuation", "within-sector percentile of A01-A03", units="percentile",
                 direction="higher = cheaper than sector peers", code="transform of A01-A03 using the dated S&P 500 snapshot sectors",
                 source="data/research/us-capital-allocation-alpha-v1/sp500-snapshot-sectors.json.gz", observable="as A01-A03", pit=FILING_PIT,
                 corp="as A01-A03", sectors="within-sector by construction", hist="AVAILABLE_WITH_CAVEATS", prosp=PROSP_PRICE,
                 coverage={"note": "as A01-A03"}, missing=["as A01-A03", "UNCLASSIFIED sector"], adjusted="as A01-A03", departed=PRICE_DEP,
                 identity=TICKER_REUSE, exposure=NOT_TESTED, mechanism="removes sector-level valuation bets",
                 confounders=["sector history exists only for the 195 dated snapshots"], redundancy=[{"note": "a normalisation of A01-A03, not new information"}],
                 feasibility="a design choice for A01-A03, not a separate hypothesis"))
    out.append(f("A08", "A_VALUATION", "valuationChange", "change in A01-A03 over a trailing window", units="ratio change",
                 direction="positive = re-rated cheaper", code="NOT_IMPLEMENTED", source="A01-A03 history", observable="as A01-A03", pit=FILING_PIT,
                 corp="as A01-A03", sectors="as A01-A03", hist="NOT_IMPLEMENTED", prosp="NOT_IMPLEMENTED", coverage=UNMEASURED,
                 missing=["as A01-A03"], adjusted="as A01-A03", departed=PRICE_DEP, identity=TICKER_REUSE, exposure=NOT_TESTED,
                 mechanism="re-rating", confounders=["price momentum mechanically enters the change in a price-denominated yield"],
                 redundancy=[{"note": "docs/us-alpha-research-design-v1.md candidate E: orthogonality to value and momentum is the open question"}],
                 feasibility="derivable; low priority because its price leg duplicates momentum"))
    out.append(f("A09", "A_VALUATION", "forwardEarningsYield", "consensus forward EPS / price", units="ratio", direction="higher = cheaper",
                 code="NOT_IMPLEMENTED", source="historical consensus", observable="n/a", pit="vintage-stamped consensus required", corp="n/a",
                 sectors=SECTORS_ALL, hist="UNAVAILABLE", prosp="UNAVAILABLE", coverage=UNMEASURED, missing=["HISTORICAL_CONSENSUS_UNAVAILABLE"],
                 adjusted="n/a", departed="n/a", identity="n/a", exposure=NOT_TESTED, mechanism="expectations-based value",
                 confounders=["analyst coverage"], redundancy=[UNMEASURED], feasibility="paid source (Finnhub historical estimates tier)"))

    # ---------------- B. PROFITABILITY AND QUALITY ----------------
    for fid, name, formula in (("B01", "roe", "net income TTM / equity (positive equity only)"),
                               ("B02", "operatingMargin", "operating income TTM / revenue TTM"),
                               ("B03", "profitMargin", "net income TTM / revenue TTM")):
        out.append(f(fid, "B_PROFITABILITY_QUALITY", name, formula, units="ratio", direction="higher = more profitable",
                     code="pipeline/finnhub_derive.py:derive_fields (sealed PIT_FUNDAMENTALS_V1)", source="Finnhub financials-reported (SEC XBRL as filed)",
                     observable="SEC acceptance", pit=FILING_PIT, corp="none (dollar amounts from one filing chain)", sectors=SECTORS_NONFIN if name != "roe" else SECTORS_ALL,
                     hist=SURV, prosp=PROSP_BS if name == "roe" else "AVAILABLE_WITH_CAVEATS: income statement still served; prospective price ledger still needed for eligibility",
                     coverage={"nonFinancial": avail(name)}, missing=["NO_VISIBLE_FILING", "REPORT_STALE_OVER_180_DAYS", "TTM_INCOMPLETE_CHAIN", "DENOMINATOR_NON_POSITIVE"],
                     adjusted="none", departed=FILING_DEP, identity=TICKER_REUSE, exposure={**EXP_31, "studies": EXP_31["studies"] + EXP_FF["studies"]},
                     mechanism="persistent profitability is under-priced / quality premium", confounders=["sector", "leverage (roe)", "size"],
                     redundancy=[rho("roe", "operatingMargin"), rho3("cashOperatingProfitability", "roe")], feasibility="computable now",
                     measured_rank=uv(name)))
    out.append(f("B04", "B_PROFITABILITY_QUALITY", "operatingProfitabilityToAssets", "operating income TTM / total assets", units="ratio",
                 direction="higher = more profitable", code="pipeline/us_cash_profitability.py:features_as_of", source="Finnhub financials-reported",
                 observable="SEC acceptance", pit=FILING_PIT, corp="none", sectors=SECTORS_NONFIN, hist=SURV, prosp=PROSP_BS,
                 coverage={"nonFinancial": m("phase3", "/overall/operatingProfitabilityToAssetsPct", NONFIN_55)},
                 missing=["OPERATING_INCOME_TTM_INCOMPLETE_CHAIN", "REPORT_STALE_OVER_180_DAYS", "NO_VISIBLE_FILING", "ASSETS_NOT_STATED", "ASSETS_NON_POSITIVE"],
                 adjusted="none", departed=FILING_DEP, identity=TICKER_REUSE, exposure=NOT_TESTED,
                 mechanism="accrual-based operating profitability (Novy-Marx / Ball et al. family)", confounders=["sector", "asset intensity"],
                 redundancy=[rho3("cashOperatingProfitability", "operatingProfitabilityToAssets")], feasibility="computable now; P4 control",
                 measured_rank=uv("operatingProfitabilityToAssets")))
    out.append(f("B05", "B_PROFITABILITY_QUALITY", "cashOperatingProfitability", "operating cash flow TTM / total assets", units="ratio",
                 direction="higher = more cash profitable", code="pipeline/us_cash_profitability.py:features_as_of (US_CASH_PROFITABILITY_CANDIDATE_V1)",
                 source="Finnhub financials-reported", observable="SEC acceptance", pit=FILING_PIT, corp="none", sectors=SECTORS_NONFIN, hist=SURV, prosp=PROSP_BS,
                 coverage={"nonFinancial": m("phase3", "/overall/cashOperatingProfitabilityPct", NONFIN_55)},
                 missing=list(get("phase3", "/missingReasons/cashOperatingProfitability")), adjusted="none", departed=FILING_DEP, identity=TICKER_REUSE,
                 exposure={"status": "NOT_TESTED", "studies": ["us-cash-profitability-signal-v1 (P4 frozen, not executed)"],
                           "note": "P3 synthetic calibration PASS; the one-shot exploratory P4 has not read an outcome"},
                 mechanism="cash earnings are harder to manage; investors overweight the accrual component",
                 confounders=["accrual operating profitability (rank rho 0.77)", "book yield (-0.56)", "sector (18% of rank variance)"],
                 redundancy=[rho3("cashOperatingProfitability", "operatingProfitabilityToAssets"), rho3("cashOperatingProfitability", "accrualsToAssets"),
                             rho3("cashOperatingProfitability", "bookYield")],
                 feasibility="computable now historically; prospectively blocked on total assets", measured_rank=uv("cashOperatingProfitability")))
    out.append(f("B06", "B_PROFITABILITY_QUALITY", "accrualsToAssets", "(net income TTM - operating cash flow TTM) / total assets", units="ratio",
                 direction="higher = more accrual-heavy (lower earnings quality)", code="pipeline/us_cash_profitability.py:features_as_of",
                 source="Finnhub financials-reported", observable="SEC acceptance", pit=FILING_PIT, corp="none", sectors=SECTORS_NONFIN, hist=SURV, prosp=PROSP_BS,
                 coverage={"nonFinancial": m("phase3", "/overall/accrualsToAssetsPct", NONFIN_55)}, missing=list(get("phase3", "/missingReasons/accrualsToAssets")),
                 adjusted="none", departed=FILING_DEP, identity=TICKER_REUSE, exposure=NOT_TESTED, mechanism="accrual anomaly (Sloan)",
                 confounders=["growth (accruals rise with expansion)", "asset growth"], redundancy=[rho3("accrualsToAssets", "operatingProfitabilityToAssets")],
                 feasibility="computable now", measured_rank=uv("accrualsToAssets")))
    for fid, name, field, pct_key in (("B07", "cashConversion", "ocfToNetIncomePct", "OCF / NI"), ("B08", "fcfToNetIncome", "fcfToNetIncomePct", "FCF / NI")):
        out.append(f(fid, "B_PROFITABILITY_QUALITY", name, pct_key + " (positive net income only)", units="percent", direction="higher = more cash-backed earnings",
                     code="pipeline/accounting_quality.py:derive_us_fields (%s)" % field, source="Finnhub financials-reported", observable="SEC acceptance",
                     pit=FILING_PIT, corp="none", sectors=SECTORS_NONFIN, hist=SURV, prosp="AVAILABLE_WITH_CAVEATS: income and cash-flow statements still served",
                     coverage={"note": "AGENTS.md v2.24 reports %s on 97.39%% / 87.00%% of US FILINGS (store-level, not member-date); not measured on the weekly member-date grid" % field},
                     missing=["NON_POSITIVE_NET_INCOME", "TTM_INCOMPLETE_CHAIN"], adjusted="none", departed=FILING_DEP, identity=TICKER_REUSE, exposure=NOT_TESTED,
                     mechanism="earnings quality", confounders=["undefined when NI <= 0, so the measured set is selected on profitability"],
                     redundancy=[{"note": "same information as B05/B06 in ratio form; not measured on the grid"}], feasibility="computable now; redundant with B05/B06 by construction"))
    out.append(f("B09", "B_PROFITABILITY_QUALITY", "fcfConversion", "(OCF - capex) / OCF, OCF > 0", units="ratio", direction="higher = less reinvestment need",
                 code="pipeline/us_shareholder_distribution.py (PR #220 engine)", source="Finnhub financials-reported", observable="SEC acceptance", pit=FILING_PIT,
                 corp="none", sectors=SECTORS_NONFIN, hist=SURV, prosp="AVAILABLE_WITH_CAVEATS", coverage={"allSectors": m("multifactor", "/availabilityOverallPct/cashFlow", ALL_55)},
                 missing=["EXACT_CONCEPT_NOT_REPORTED", "AMBIGUOUS_ACCOUNTING"], adjusted="none", departed=FILING_DEP, identity=TICKER_REUSE, exposure=NOT_TESTED,
                 mechanism="capital intensity / cash confirmation", confounders=["capex intensity"], redundancy=[rho("fcfConversion", "fcfYield")],
                 feasibility="computable at lower coverage than B05 (strict exact-concept rule)"))
    out.append(f("B10", "B_PROFITABILITY_QUALITY", "grossProfitability", "(revenue - COGS) TTM / total assets", units="ratio", direction="higher = more profitable",
                 code="NOT_IMPLEMENTED", source="raw XBRL may state GrossProfit / CostOfRevenue but finnhub_derive.FLOWS derives neither", observable="SEC acceptance",
                 pit=FILING_PIT, corp="none", sectors=SECTORS_NONFIN, hist="NOT_IMPLEMENTED", prosp=PROSP_BS, coverage=UNMEASURED,
                 missing=["NO_GROSS_PROFIT_CHAIN"], adjusted="none", departed=FILING_DEP, identity=TICKER_REUSE, exposure=NOT_TESTED,
                 mechanism="Novy-Marx gross profitability", confounders=["B04/B05"], redundancy=[UNMEASURED],
                 feasibility="needs a new concept chain plus a raw-concept coverage audit; expected to overlap B04/B05 heavily"))
    out.append(f("B11", "B_PROFITABILITY_QUALITY", "roic", "NOPAT / invested capital", units="ratio", direction="higher = better", code="NOT_IMPLEMENTED",
                 source="needs debt, cash, tax detail", observable="n/a", pit="n/a", corp="none", sectors=SECTORS_NONFIN, hist="NOT_IMPLEMENTED", prosp="NOT_IMPLEMENTED",
                 coverage=UNMEASURED, missing=["NO_DEBT_OR_CASH_DETAIL", "NO_TAX_CHAIN"], adjusted="none", departed=FILING_DEP, identity=TICKER_REUSE, exposure=NOT_TESTED,
                 mechanism="capital efficiency", confounders=["B01/B04"], redundancy=[UNMEASURED], feasibility="blocked on line items the store does not derive"))
    out.append(f("B12", "B_PROFITABILITY_QUALITY", "operatingMarginStability", "dispersion of the own last 4 operatingMargin readings", units="ratio",
                 direction="lower = more stable", code="pipeline/accounting_quality.py:operating_margin_stability (function exists; not wired for US)",
                 source="sealed operatingMargin history", observable="SEC acceptance", pit=FILING_PIT, corp="none", sectors=SECTORS_NONFIN,
                 hist="AVAILABLE_WITH_CAVEATS", prosp="AVAILABLE_WITH_CAVEATS", coverage=UNMEASURED, missing=["FEWER_THAN_WINDOW_OWN_READINGS"], adjusted="none",
                 departed=FILING_DEP, identity=TICKER_REUSE, exposure=NOT_TESTED, mechanism="earnings stability / quality",
                 confounders=["volatility", "size"], redundancy=[UNMEASURED], feasibility="computable; coverage not yet measured on the grid"))
    out.append(f("B13", "B_PROFITABILITY_QUALITY", "debtToEquity", "total liabilities / equity", units="ratio", direction="higher = more levered",
                 code="pipeline/finnhub_derive.py:derive_fields", source="Finnhub financials-reported", observable="SEC acceptance", pit=FILING_PIT, corp="none",
                 sectors="not comparable for Financials/Utilities/Real Estate (production masks them)", hist=SURV, prosp=PROSP_BS,
                 coverage={"nonFinancial": avail("debtToEquity")}, missing=["NO_VISIBLE_FILING", "EQUITY_NON_POSITIVE"], adjusted="none", departed=FILING_DEP,
                 identity=TICKER_REUSE, exposure={**EXP_31, "studies": EXP_31["studies"] + EXP_FF["studies"]}, mechanism="distress risk / balance-sheet resilience",
                 confounders=["sector", "buybacks shrink equity"], redundancy=[rho("debtToEquity", "earningsYield")], feasibility="computable now",
                 measured_rank=uv("debtToEquity")))

    # ---------------- C. GROWTH AND CHANGE ----------------
    out.append(f("C01", "C_GROWTH_CHANGE", "earningsGrowth", "net income TTM vs same stage a year earlier", units="ratio", direction="higher = faster growth",
                 code="pipeline/finnhub_derive.py:derive_fields", source="Finnhub financials-reported", observable="SEC acceptance", pit=FILING_PIT, corp="none",
                 sectors=SECTORS_ALL, hist=SURV, prosp="AVAILABLE_WITH_CAVEATS", coverage={"nonFinancial": avail("earningsGrowth")},
                 missing=["NO_PRIOR_YEAR_FILING", "NON_POSITIVE_BASE"], adjusted="none", departed=FILING_DEP, identity=TICKER_REUSE,
                 exposure={**EXP_31, "studies": EXP_31["studies"] + EXP_FF["studies"]}, mechanism="slow incorporation of fundamental momentum",
                 confounders=["base effects", "price momentum"], redundancy=[rho("earningsGrowth", "delta_roe")], feasibility="computable now",
                 measured_rank=uv("earningsGrowth")))
    out.append(f("C02", "C_GROWTH_CHANGE", "revenueGrowthTTM", "revenue TTM / revenue TTM same stage one year earlier - 1 (earlier TTM > 0)", units="ratio",
                 direction="higher = faster growth", code="scripts/audit_us_factor_unique_variation.py:extra_accounting (finnhub_derive.trailing_twelve_months; one new ratio)",
                 source="Finnhub financials-reported", observable="SEC acceptance", pit=FILING_PIT, corp="none", sectors=SECTORS_NONFIN, hist=SURV,
                 prosp="AVAILABLE_WITH_CAVEATS", coverage={"nonFinancial": avail("revenueGrowthTTM")}, missing=["REVENUE_TTM_INCOMPLETE_CHAIN", "NON_POSITIVE_BASE", "REPORT_STALE"],
                 adjusted="none", departed=FILING_DEP, identity=TICKER_REUSE, exposure=NOT_TESTED, mechanism="growth persistence vs extrapolation",
                 confounders=["M&A inflates revenue growth", "earningsGrowth"], redundancy=[{"note": "see uniqueVariation"}],
                 feasibility="computable now (measurement-only definition; not a registered feature)", measured_rank=uv("revenueGrowthTTM")))
    for fid, name in (("C03", "delta_roe"), ("C04", "delta_operatingMargin"), ("C05", "delta_profitMargin"), ("C06", "delta_earningsGrowth")):
        out.append(f(fid, "C_GROWTH_CHANGE", name, "field at the current filing minus the field at the previous consecutive filing",
                     units="ratio change", direction="positive = improving", code="pipeline/fundamental_acceleration.py:resolve_filing_pair/compute_deltas",
                     source="Finnhub financials-reported", observable="SEC acceptance of the CURRENT filing", pit=FILING_PIT, corp="none", sectors=SECTORS_ALL,
                     hist=SURV, prosp="AVAILABLE_WITH_CAVEATS", coverage={"usFilingPairs": m("acceleration", "/coverage/byRegion/US/dataSufficientRatio", "US signal name-dates (300,646)")},
                     missing=["NOT_CONSECUTIVE", "NO_PREVIOUS_FILING", "NO_FILING_VISIBLE"], adjusted="none", departed=FILING_DEP, identity=TICKER_REUSE, exposure=ACCEL,
                     mechanism="financial inflection / acceleration", confounders=["earningsGrowth", "seasonality"],
                     redundancy=[rho("delta_roe", "earningsGrowth")] if name == "delta_roe" else [{"note": "see uniqueVariation where measured"}],
                     feasibility="closed as a composite hypothesis; do not re-test the same composite",
                     measured_rank=uv(name) if name in ("delta_roe", "delta_operatingMargin") else None))
    out.append(f("C07", "C_GROWTH_CHANGE", "operatingCashFlowGrowth", "OCF TTM vs same stage a year earlier", units="ratio", direction="higher = faster",
                 code="NOT_IMPLEMENTED (derivable from finnhub_derive.trailing_twelve_months)", source="Finnhub financials-reported", observable="SEC acceptance", pit=FILING_PIT,
                 corp="none", sectors=SECTORS_NONFIN, hist="NOT_IMPLEMENTED", prosp="AVAILABLE_WITH_CAVEATS", coverage=UNMEASURED, missing=["NON_POSITIVE_BASE"], adjusted="none",
                 departed=FILING_DEP, identity=TICKER_REUSE, exposure=NOT_TESTED, mechanism="cash-flow momentum", confounders=["C01", "B05"], redundancy=[UNMEASURED],
                 feasibility="derivable; expected to overlap C01 and B05"))

    # ---------------- D. MOMENTUM AND TREND ----------------
    for fid, name, formula in (("D01", "mom121", "return from t-252 to t-21 sessions"), ("D02", "relative126", "126-session return minus SPY's"),
                               ("D03", "high52Distance", "close / trailing 252-session high - 1"), ("D04", "relativeStrengthBreadth52w", "share of 52 completed weeks beating SPY")):
        out.append(f(fid, "D_MOMENTUM_TREND", name, formula, units="ratio" if name != "relativeStrengthBreadth52w" else "share", direction="higher = stronger trend",
                     code="pipeline/regional_alpha_features.py:price_features / weekly_breadth", source="replay-v16 sealed total-return closes", observable="signal-date close",
                     pit=PRICE_PIT, corp="total-return index absorbs splits and dividends", sectors=SECTORS_ALL, hist=SURV, prosp=PROSP_PRICE,
                     coverage={"allSectors": m("multifactor", "/availabilityOverallPct/priceMomentum", ALL_55)}, missing=["PRICE_HISTORY_INSUFFICIENT", "NO_PRICE_PANEL"],
                     adjusted="total-return close (correct for return features)", departed=PRICE_DEP, identity=TICKER_REUSE,
                     exposure={**EXP_31, "studies": EXP_31["studies"] + (EXP_FF["studies"] if name == "mom121" else [])},
                     mechanism="slow information diffusion / underreaction", confounders=["market beta in up/down regimes", "sector momentum"],
                     redundancy=[rho("mom121", "relative126"), rho("high52Distance", "relative126"), rho("mom121", "relativeStrengthBreadth52w")],
                     feasibility="computable now; closed as a standalone discovery (31-feature model)", measured_rank=uv(name)))
    out.append(f("D05", "D_MOMENTUM_TREND", "multiHorizonReturns", "21/63/126/252-session returns, ma200Distance, rsi14", units="ratio", direction="higher = stronger",
                 code="pipeline/regional_alpha_features.py:price_features", source="replay-v16", observable="signal-date close", pit=PRICE_PIT, corp="total-return index",
                 sectors=SECTORS_ALL, hist=SURV, prosp=PROSP_PRICE, coverage={"note": "100% wherever a panel with 273+ sessions exists"}, missing=["PRICE_HISTORY_INSUFFICIENT"],
                 adjusted="total-return close", departed=PRICE_DEP, identity=TICKER_REUSE, exposure=EXP_31, mechanism="momentum/reversal at several horizons",
                 confounders=["D01-D04"], redundancy=[{"note": "the nonlinear 31-feature model could already form acceleration/reversal from these"}],
                 feasibility="closed"))
    out.append(f("D06", "D_MOMENTUM_TREND", "sectorRelativeStrength", "stock return minus its dated-sector median return", units="ratio", direction="higher = beating sector",
                 code="NOT_IMPLEMENTED (the 31-feature model excluded sector for lack of dated provenance; dated snapshot sectors now exist)",
                 source="replay-v16 + sp500-snapshot-sectors (195 hash-verified snapshots)", observable="signal-date close", pit=PRICE_PIT + "; sector from the latest snapshot strictly before the date",
                 corp="total-return index", sectors=SECTORS_ALL, hist="AVAILABLE_WITH_CAVEATS", prosp=PROSP_PRICE, coverage=UNMEASURED,
                 missing=["UNCLASSIFIED", "sector stale up to 767 days between snapshots"], adjusted="total-return close", departed=PRICE_DEP + "; sector medians computed on survivors",
                 identity=TICKER_REUSE, exposure=NOT_TESTED, mechanism="separates stock-specific from industry momentum", confounders=["D02"], redundancy=[UNMEASURED],
                 feasibility="derivable; a re-expression of closed momentum information rather than a new family"))

    # ---------------- E. RISK AND STABILITY ----------------
    for fid, name in (("E01", "vol252"), ("E02", "downsideVol252"), ("E03", "beta252"), ("E04", "maxDD252")):
        out.append(f(fid, "E_RISK_STABILITY", name, {"vol252": "252-session return volatility", "downsideVol252": "252-session downside semideviation",
                                                       "beta252": "252-session beta to SPY", "maxDD252": "252-session maximum drawdown"}[name],
                     units="ratio", direction="higher = riskier", code="pipeline/regional_alpha_features.py:price_features", source="replay-v16", observable="signal-date close",
                     pit=PRICE_PIT, corp="total-return index", sectors=SECTORS_ALL, hist=SURV, prosp=PROSP_PRICE,
                     coverage={"allSectors": m("multifactor", "/availabilityOverallPct/priceRisk", ALL_55)}, missing=["PRICE_HISTORY_INSUFFICIENT"],
                     adjusted="total-return close", departed=PRICE_DEP + " — departed names are disproportionately the high-risk ones", identity=TICKER_REUSE,
                     exposure={**EXP_31, "studies": EXP_31["studies"] + (EXP_FF["studies"] if name == "vol252" else [])},
                     mechanism="low-risk anomaly (leverage constraints, lottery demand)", confounders=["size", "sector", "momentum crash risk"],
                     redundancy=[rho("vol252", "beta252"), rho("vol252", "maxDD252")], feasibility="computable now; closed as standalone; useful as a control and risk input",
                     measured_rank=uv(name)))
    out.append(f("E05", "E_RISK_STABILITY", "logTradedValue63", "log median as-traded dollar volume over 63 sessions (withheld across a split)", units="log USD",
                 direction="higher = more liquid / larger", code="scripts/audit_us_alpha_phase3_readiness.py:traded_value_median", source="replay-v16 close x volume (reconstructed as-traded)",
                 observable="signal-date close", pit=PRICE_PIT, corp="split inside window withholds", sectors=SECTORS_ALL, hist=SURV, prosp=PROSP_PRICE,
                 coverage={"nonFinancial": m("phase3", "/overall/logTradedValue63Pct", NONFIN_55)}, missing=["SPLIT_IN_WINDOW", "INSUFFICIENT_SESSIONS"],
                 adjusted="as-traded price reconstructed", departed=PRICE_DEP, identity=TICKER_REUSE, exposure=NOT_TESTED,
                 mechanism="size/liquidity control and trading-cost input; not proposed as alpha", confounders=["market cap"],
                 redundancy=[{"pair": ["logTradedValue63", "logMarketCapProxy"], "meanRho": get("phase3", "/sizeProxyAgreement/meanRho"), "source": R["phase3"], "pointer": "/sizeProxyAgreement"}],
                 feasibility="computable now; primary size control", measured_rank=uv("logTradedValue63")))
    out.append(f("E06", "E_RISK_STABILITY", "logMarketCapProxy", "log(weighted-average shares x as-traded close)", units="log USD", direction="higher = larger",
                 code="pipeline/us_cash_profitability.py:market_cap_proxy", source="Finnhub share count + reconstructed price", observable="filing acceptance + close", pit=FILING_PIT,
                 corp="weighted-average, not period-end, shares; split between filing and observation withholds", sectors=SECTORS_ALL,
                 hist="NEEDS_SOURCE_OR_IDENTITY_VERIFICATION", prosp="NEEDS_SOURCE_OR_IDENTITY_VERIFICATION",
                 coverage={"nonFinancial": m("phase3", "/overall/logMarketCapProxyPct", NONFIN_55)}, missing=list(get("phase3", "/missingReasons/logMarketCapProxy")),
                 adjusted="as-traded price reconstructed", departed=PRICE_DEP, identity=TICKER_REUSE, exposure=NOT_TESTED, mechanism="size",
                 confounders=["share basis"], redundancy=[{"note": "agrees with traded value at mean rank rho 0.72"}],
                 feasibility="sensitivity only; verified market cap needs period-end shares (SEC)", measured_rank=uv("logMarketCapProxy")))
    out.append(f("E07", "E_RISK_STABILITY", "earningsStability", "dispersion of own TTM earnings/margins", units="ratio", direction="lower = more stable",
                 code="see B12", source="sealed fundamentals", observable="SEC acceptance", pit=FILING_PIT, corp="none", sectors=SECTORS_NONFIN, hist="AVAILABLE_WITH_CAVEATS",
                 prosp="AVAILABLE_WITH_CAVEATS", coverage=UNMEASURED, missing=["FEWER_THAN_WINDOW_OWN_READINGS"], adjusted="none", departed=FILING_DEP, identity=TICKER_REUSE,
                 exposure=NOT_TESTED, mechanism="quality / safety", confounders=["vol252"], redundancy=[UNMEASURED], feasibility="same as B12"))

    # ---------------- F. SHAREHOLDER RETURNS AND CAPITAL ALLOCATION ----------------
    for fid, name in (("F01", "totalCashDistributionChangeYoY"), ("F02", "distributionToOCF"), ("F03", "incrementalDistributionOverOCF")):
        out.append(f(fid, "F_CAPITAL_ALLOCATION", name, {"totalCashDistributionChangeYoY": "(common dividends + repurchases) TTM vs same stage a year earlier - 1",
                                                          "distributionToOCF": "(common dividends + repurchases) TTM / positive OCF TTM",
                                                          "incrementalDistributionOverOCF": "year-on-year change in distributions / OCF"}[name],
                     units="ratio", direction="higher = more cash returned", code="pipeline/us_shareholder_distribution.py (US_SHAREHOLDER_DISTRIBUTION_V1)",
                     source="Finnhub financials-reported, EXACT concepts only", observable="SEC acceptance", pit=FILING_PIT,
                     corp="buybacks reduce shares; dilution cannot be verified (period-end shares 1.8% of filings)", sectors=SECTORS_NONFIN, hist="AVAILABLE_WITH_CAVEATS",
                     prosp="REGISTERED_PENDING_OWNER_APPROVAL (us-capital-allocation-alpha-v1, REGISTERED_AUTHORIZATION = None)",
                     coverage={"core4Joint": m("multifactor", "/availabilityOverallPct/distributionCore4", ALL_55),
                               "weeklyJointNote": "17.915% of all 359,526 weekly member-dates (docs/us-capital-allocation-phase2-v1.md, §1 row 3)"},
                     missing=["CONCEPT_NOT_REPORTED", "AMBIGUOUS_ACCOUNTING / RELATED_CONCEPT_IS_NOT_AN_ALIAS", "MISSING_FISCAL_CHAIN"], adjusted="none", departed=FILING_DEP,
                     identity=TICKER_REUSE, exposure={"status": "NOT_TESTED", "studies": ["us-capital-allocation-alpha-v1 (prospective registration, no historical outcome read)"],
                                                     "note": "measured set is non-random: lower volatility (0.451 vs 0.515 pct) and higher ROE (0.545 vs 0.489)"},
                     mechanism="payout signals management confidence; buyback timing", confounders=["profitability (distributionToOCF vs roe 0.36)", "low volatility"],
                     redundancy=[rho("incrementalDistributionOverOCF", "totalCashDistributionChangeYoY"), rho("distributionToOCF", "roe")],
                     feasibility="computable at low, non-random coverage; an alias view (to 30.6%) stays blocked until SEC context verification"))
    out.append(f("F04", "F_CAPITAL_ALLOCATION", "dividendYield", "trailing 12-month dividends from sealed corporate events / as-traded close", units="ratio",
                 direction="higher = more income", code="NOT_IMPLEMENTED (events exist: scripts/audit_us_multifactor_pit_readiness.py:load_events)",
                 source="replay-v16 sealed corporate events (Yahoo actions) + reconstructed close", observable="ex-date and signal-date close", pit=PRICE_PIT,
                 corp="split-adjust dividends to the as-traded basis", sectors=SECTORS_ALL, hist="AVAILABLE_WITH_CAVEATS", prosp=PROSP_PRICE, coverage=UNMEASURED,
                 missing=["NO_PRICE_PANEL"], adjusted="as-traded price reconstructed", departed=PRICE_DEP + "; departed names also lack dividend lineage",
                 identity=TICKER_REUSE, exposure=NOT_TESTED, mechanism="income / value tilt", confounders=["value", "low volatility", "sector (utilities, staples)"],
                 redundancy=[UNMEASURED], feasibility="derivable from data already sealed; a generic dividend tag is NOT treated as common-share dividends"))
    out.append(f("F05", "F_CAPITAL_ALLOCATION", "netShareCountChange", "period-end shares outstanding vs a year earlier", units="ratio", direction="negative = net buyback",
                 code="pipeline/accounting_quality.py:derive_us_fields (shareCountChangePct uses WEIGHTED-AVERAGE counts)", source="needs period-end / cover-page shares",
                 observable="SEC acceptance", pit=FILING_PIT, corp="splits must be neutralised", sectors=SECTORS_ALL, hist="NEEDS_SOURCE_OR_IDENTITY_VERIFICATION",
                 prosp="NEEDS_SOURCE_OR_IDENTITY_VERIFICATION", coverage={"dilution": m("multifactor", "/availabilityOverallPct/dilution", ALL_55)},
                 missing=["PERIOD_END_SHARES_NOT_STATED (SEC context blocked)"], adjusted="none", departed=FILING_DEP, identity=TICKER_REUSE, exposure=NOT_TESTED,
                 mechanism="issuance anomaly / dilution", confounders=["M&A share issuance"], redundancy=[UNMEASURED],
                 feasibility="blocked: weighted-average counts are not verified share-count change"))
    out.append(f("F06", "F_CAPITAL_ALLOCATION", "netPayoutYield", "(dividends + buybacks - issuance) / market cap", units="ratio", direction="higher = more returned",
                 code="NOT_IMPLEMENTED", source="F01 components / market cap", observable="n/a", pit=FILING_PIT, corp="needs verified market cap", sectors=SECTORS_NONFIN,
                 hist="NEEDS_SOURCE_OR_IDENTITY_VERIFICATION", prosp="NEEDS_SOURCE_OR_IDENTITY_VERIFICATION", coverage=UNMEASURED, missing=["MARKET_CAP_PIT_UNRESOLVED"],
                 adjusted="as-traded price", departed=PRICE_DEP, identity=TICKER_REUSE, exposure=NOT_TESTED, mechanism="payout yield (Boudoukh et al.)",
                 confounders=["value"], redundancy=[UNMEASURED], feasibility="blocked on market cap and issuance"))
    out.append(f("F07", "F_CAPITAL_ALLOCATION", "assetGrowthPct", "total assets vs same stage a year earlier - 1", units="percent", direction="higher = faster investment",
                 code="pipeline/accounting_quality.py:derive_us_fields (ACCOUNTING_QUALITY_V1), evaluated on the cash-profitability visibility rule",
                 source="Finnhub financials-reported balance sheet", observable="SEC acceptance", pit=FILING_PIT, corp="M&A steps up assets without organic investment",
                 sectors="defined everywhere; a different economic meaning for banks (balance-sheet growth)", hist=SURV, prosp=PROSP_BS,
                 coverage={"nonFinancial": avail("assetGrowthPct"), "financialAndRealEstate": m("unique", "/availabilityFinancialAndRealEstatePct/assetGrowthPct/pct", "Financials and Real Estate member-dates on the 55 dates (4,684)")},
                 missing=["ASSETS_NOT_STATED", "NO_PRIOR_SAME_STAGE_FILING", "REPORT_STALE"], adjusted="none", departed=FILING_DEP, identity=TICKER_REUSE, exposure=NOT_TESTED,
                 mechanism="investment factor: high asset growth predicts lower returns (empire building, q-theory)", confounders=["acquisitions", "accruals", "revenue growth"],
                 redundancy=[{"note": "see uniqueVariation (ownFamily R2 vs capex intensity near zero)"}], feasibility="computable now historically; prospectively blocked on total assets",
                 measured_rank=uv("assetGrowthPct")))
    out.append(f("F08", "F_CAPITAL_ALLOCATION", "capexIntensityPct", "capex TTM / revenue TTM", units="percent", direction="higher = more reinvestment",
                 code="pipeline/accounting_quality.py:derive_us_fields", source="Finnhub financials-reported", observable="SEC acceptance", pit=FILING_PIT, corp="none",
                 sectors=SECTORS_NONFIN, hist=SURV, prosp="AVAILABLE_WITH_CAVEATS", coverage={"nonFinancial": avail("capexIntensityPct")}, missing=["CAPEX_CHAIN_INCOMPLETE", "REVENUE_TTM_INCOMPLETE"],
                 adjusted="none", departed=FILING_DEP, identity=TICKER_REUSE, exposure=NOT_TESTED, mechanism="reinvestment vs distribution",
                 confounders=["sector (26% of rank variance)"], redundancy=[{"note": "see uniqueVariation"}], feasibility="computable now",
                 measured_rank=uv("capexIntensityPct")))
    out.append(f("F09", "F_CAPITAL_ALLOCATION", "debtGrowthPct", "total liabilities vs same stage a year earlier - 1", units="percent", direction="higher = levering up",
                 code="pipeline/accounting_quality.py:derive_us_fields", source="Finnhub balance sheet", observable="SEC acceptance", pit=FILING_PIT, corp="M&A",
                 sectors=SECTORS_NONFIN, hist="AVAILABLE_WITH_CAVEATS", prosp=PROSP_BS, coverage=UNMEASURED, missing=["LIABILITIES_NOT_STATED", "NO_PRIOR_SAME_STAGE_FILING"],
                 adjusted="none", departed=FILING_DEP, identity=TICKER_REUSE, exposure=NOT_TESTED, mechanism="external financing anomaly",
                 confounders=["F07"], redundancy=[UNMEASURED], feasibility="computable; coverage not measured on the grid"))

    # ---------------- G. CATALYSTS AND EVENTS ----------------
    blocked = [("G01", "earningsSurpriseVsConsensus", "actual EPS - consensus at announcement", "HISTORICAL_CONSENSUS_UNAVAILABLE (paid)"),
               ("G02", "estimateRevisions", "change in consensus over a trailing window", "HISTORICAL_ESTIMATES_PAID_TIER"),
               ("G03", "corporateEvents8K", "8-K item events", "SEC data.sec.gov blocked from Actions egress (HTTP 403, byte-identical across header sets)"),
               ("G04", "guidanceChanges", "management guidance revisions", "no source in the repository")]
    for fid, name, formula, why in blocked:
        out.append(f(fid, "G_CATALYSTS_EVENTS", name, formula, units="varies", direction="n/a", code="NOT_IMPLEMENTED", source="none reachable", observable="n/a",
                     pit="vintage-stamped event feed required", corp="n/a", sectors=SECTORS_ALL, hist="UNAVAILABLE", prosp="UNAVAILABLE", coverage=UNMEASURED, missing=[why],
                     adjusted="n/a", departed="n/a", identity="n/a", exposure=NOT_TESTED, mechanism="expectation shocks / drift", confounders=["momentum"],
                     redundancy=[UNMEASURED], feasibility="blocked: " + why))
    out.append(f("G05", "G_CATALYSTS_EVENTS", "standardizedUnexpectedEarnings", "seasonal random-walk EPS surprise from filings (no consensus)", units="z-score",
                 direction="higher = positive surprise", code="NOT_IMPLEMENTED", source="Finnhub financials-reported quarterly EPS chain", observable="10-Q/10-K ACCEPTANCE, which lags the earnings announcement (8-K blocked)",
                 pit=FILING_PIT, corp="per-share basis", sectors=SECTORS_ALL, hist="AVAILABLE_WITH_CAVEATS", prosp="AVAILABLE_WITH_CAVEATS", coverage=UNMEASURED,
                 missing=["QUARTERLY_CHAIN_INCOMPLETE"], adjusted="none", departed=FILING_DEP, identity=TICKER_REUSE, exposure=NOT_TESTED,
                 mechanism="post-earnings-announcement drift", confounders=["the announcement return is already in price momentum by acceptance date"],
                 redundancy=[UNMEASURED], feasibility="derivable but measured LATE relative to the event; overlaps C01/C03"))
    out.append(f("G06", "G_CATALYSTS_EVENTS", "indexMembershipChange", "addition to / deletion from the S&P 500", units="event", direction="n/a", code="NOT_IMPLEMENTED",
                 source="research_specs/alpha-opportunity-model-v1-us-membership.json.gz (195 snapshots)", observable="snapshot commit date, not announcement date",
                 pit="snapshot usable the day after its commit", corp="n/a", sectors=SECTORS_ALL, hist="NEEDS_SOURCE_OR_IDENTITY_VERIFICATION", prosp="NEEDS_SOURCE_OR_IDENTITY_VERIFICATION",
                 coverage={"snapshotAge": m("unique", "/membershipSnapshotAge", "715 weekly signal dates")}, missing=["SNAPSHOT_GAP"], adjusted="n/a",
                 departed="departures are exactly the unpriced names", identity=TICKER_REUSE, exposure=NOT_TESTED, mechanism="index demand shocks",
                 confounders=["size", "momentum"], redundancy=[UNMEASURED], feasibility="blocked: event timing unknown to within the snapshot gap (median 54, max 767 days)"))

    # ---------------- H. OWNERSHIP, FLOW, SENTIMENT ----------------
    for fid, name, formula, status, why in (
            ("H01", "institutional13FChange", "change in 13F-reported holders/shares", "UNAVAILABLE", "SEC blocked; 13F is quarter-end holdings filed up to 45 days later, never contemporaneous"),
            ("H02", "insiderTransactions", "Form 4 net insider buying", "UNAVAILABLE", "SEC blocked; no free alternate vendor"),
            ("H03", "shortInterest", "short interest / float", "UNAVAILABLE", "NOT_PROBED in this repository"),
            ("H04", "fundFlows", "mutual fund / ETF flow pressure", "UNAVAILABLE", "no source"),
            ("H05", "newsSentiment", "stock-level news or search sentiment", "UNAVAILABLE", "no source; pipeline/sentiment.py is market-level price/breadth, not stock news")):
        out.append(f(fid, "H_OWNERSHIP_FLOW_SENTIMENT", name, formula, units="varies", direction="n/a", code="NOT_IMPLEMENTED", source="none reachable", observable="n/a",
                     pit="filing/publication timestamp required", corp="n/a", sectors=SECTORS_ALL, hist=status, prosp=status, coverage=UNMEASURED, missing=[why], adjusted="n/a",
                     departed="n/a", identity="n/a", exposure=NOT_TESTED, mechanism="informed trading / demand pressure", confounders=["size", "momentum"],
                     redundancy=[UNMEASURED], feasibility="blocked: " + why))
    out.append(f("H06", "H_OWNERSHIP_FLOW_SENTIMENT", "volumeSurge5_60", "5-session / 60-session volume ratio", units="ratio", direction="higher = abnormal attention",
                 code="pipeline/regional_alpha_features.py:price_features", source="replay-v16 split-normalised volume", observable="signal-date close", pit=PRICE_PIT,
                 corp="split-normalised", sectors=SECTORS_ALL, hist=SURV, prosp=PROSP_PRICE, coverage={"note": "wherever a panel exists"}, missing=["INSUFFICIENT_SESSIONS"],
                 adjusted="split-normalised volume", departed=PRICE_DEP, identity=TICKER_REUSE, exposure=EXP_31, mechanism="attention / volume anomalies",
                 confounders=["earnings dates"], redundancy=[UNMEASURED], feasibility="closed inside the 31-feature model"))
    return out


def study_ledger() -> list[dict]:
    ff = "/primaryTable/%s/byRegion/US"
    return [
        {"studyId": "four-factor-signal-attribution-audit-v1", "universe": "replay-v16 S&P 500 point-in-time snapshots (priced members only) + KR top-120",
         "period": "2013-2026 weekly signals", "replay": "replay-v16", "features": "production sleeve percentiles: momentum, value, quality, lowvol",
         "horizon": "H126 primary; H21/H63/H252 descriptive", "target": "within-date Spearman rank IC vs SPY-relative return", "method": "HAC (Newey-West), Holm over 4",
         "outcomesRead": True, "survivorConditioned": True, "terminalOutcomesHandled": "NO (no departed name has a panel)", "untouchedValidation": False,
         "result": {s: {"meanIC": get("fourfactor", ff % s + "/mean"), "ci95": get("fourfactor", ff % s + "/ci95"),
                        "effectiveIndependentDates": get("fourfactor", ff % s + "/effectiveIndependentDates")} for s in ("momentum", "value", "quality", "lowvol")},
         "resultSource": R["fourfactor"], "economicSignificance": "NOT_MEASURED (no portfolio, no costs)",
         "limitations": ["sleeve composites, not individual inputs", "27 effective independent dates at H126", "survivor-conditioned", "value on reconstructed basis"],
         "justified": "no US sleeve shows a rank relationship distinguishable from zero on this sample; CIs are about +/-0.04 to +/-0.07 wide",
         "notJustified": "that value, quality, momentum or low risk carry no information in the US",
         "status": "EXPLORATORY_INCONCLUSIVE", "futureWorkIs": "NEW_EXPLORATION_ON_EXPOSED_HISTORY (not a replication)"},
        {"studyId": "regional-alpha-model-v1 (US leg)", "universe": "dated S&P 500 CSV snapshots, priced members", "period": "annual walk-forward fits 2016-2026",
         "replay": "replay-v16", "features": "31 price/trend/risk + fundamental level + fundamental change features (no valuation, no market cap, no sector)",
         "horizon": "H126", "target": "within-date percentile rank of 126D return minus SPY", "method": "Ridge + HGBR, date-level Spearman IC, HAC",
         "outcomesRead": True, "survivorConditioned": True, "terminalOutcomesHandled": "missing endpoints unmeasurable, never relabelled", "untouchedValidation": False,
         "result": {"classification": "NO_MODEL_EVIDENCE", "evidence": "AGENTS.md v2.24 (Actions run 35826122755, job log); full 179MB artifact never committed"},
         "economicSignificance": "NOT_MEASURED (gross Top10 diagnostic only)",
         "limitations": ["per-feature and per-fold numbers not in the repository", "one-shot budget spent", "survivor-conditioned"],
         "justified": "an ML re-ranking over those 31 features did not establish stable out-of-sample ordering",
         "notJustified": "evidence against any single feature; class C includes positive-but-unstable patterns",
         "status": "TESTED_OUTCOME_EXPOSED", "futureWorkIs": "CLOSED for this feature set; any reuse is a new study"},
        {"studyId": "fundamental-acceleration-discovery-v1 (US leg)", "universe": "S&P 500 priced members", "period": "2013-2026", "replay": "replay-v16",
         "features": "sector-neutral composite of four consecutive-filing deltas", "horizon": "H126", "target": "rank IC, standalone and incremental to quality",
         "method": "HAC, 2-hypothesis Holm", "outcomesRead": True, "survivorConditioned": True, "terminalOutcomesHandled": "NO", "untouchedValidation": False,
         "result": {"standaloneUS": {"mean": get("acceleration", "/standalone/byRegion/US/mean"), "ci95": get("acceleration", "/standalone/byRegion/US/ci95")},
                    "incrementalUS": {"mean": get("acceleration", "/incremental/byRegion/US/mean"), "ci95": get("acceleration", "/incremental/byRegion/US/ci95")},
                    "case": get("acceleration", "/classification/case")}, "resultSource": R["acceleration"],
         "economicSignificance": "NOT_MEASURED", "limitations": ["survivor-conditioned", "composite only"],
         "justified": "the pre-registered acceleration composite failed its own routing on a clean-coverage US read (81.79%)",
         "notJustified": "that all fundamental-change information is useless", "status": "EVIDENCE_AGAINST_SPECIFIC_HYPOTHESIS",
         "futureWorkIs": "re-testing the same composite is forbidden; a different change construct would be new exploration"},
        {"studyId": "alpha-opportunity-model-v1/v2/v3 (US leg)", "universe": "S&P 500 PIT snapshots", "period": "2013-2026", "replay": "replay-v16",
         "features": "inherited 31-feature family + benchmark outside option", "horizon": "H21/H126", "target": "expected net alpha vs benchmark",
         "method": "Ridge/Logistic heads (design)", "outcomesRead": False, "survivorConditioned": True, "terminalOutcomesHandled": "audited: 0 of 615 priced panels ever terminate",
         "untouchedValidation": False,
         "result": {"v1": "US leg could only return DATA_INSUFFICIENT (whole-date voiding)", "v2": "READY but never run; must not be run (survivor-only US sample)",
                    "v3": get("survivorship", "/verdicts/US")}, "resultSource": R["survivorship"], "economicSignificance": "NOT_MEASURED",
         "limitations": ["the US sample contains no failed or acquired company"], "justified": "the US historical sample is survivor-conditioned by construction",
         "notJustified": "any direction or size of the survivorship bias", "status": "DATA_QUALITY_BLOCKED", "futureWorkIs": "needs a repaired snapshot and a new version"},
        {"studyId": "benchmark-relative-alpha-v1 and the replay-v16 portfolio-construction ladder (alpha-reliability, signal-persistence, switch-hurdle, "
                    "alpha-risk-separation, dynamic-breadth, region-quota-removal, entry-selection-separation, lowvol-alpha-separation, alpha-calibration-resolution)",
         "universe": "COMBINED KR + US 5-name book", "period": "155 x 21-session blocks", "replay": "replay-v16", "features": "production four-factor alpha + calibration",
         "horizon": "21-session blocks, H126 calibration", "target": "net excess vs matched regional benchmark after realistic costs",
         "method": "paired block bootstrap; selection-value decomposition", "outcomesRead": True, "survivorConditioned": True, "terminalOutcomesHandled": "partial",
         "untouchedValidation": False,
         "result": {"decision": "BENCHMARK_NOT_BEATEN", "combinedChampionGrossVsMatchedBenchmarkPp": -1.730, "costDragPp": 1.463,
                    "note": "every ladder rung's paired interval contains zero except the confidence axis, separated in the WRONG direction (AGENTS v2.13)"},
         "resultSource": R["benchmarkAlpha"], "economicSignificance": "MEASURED: the gross picks trail the matched index; costs add ~1.4pp/yr",
         "limitations": ["KR and US pooled in one book: no US-only reading", "calibration occupies two buckets, so ties decide the margin", "survivor-conditioned US half"],
         "justified": "the PRODUCTION ranking + construction did not beat its benchmark gross of costs; construction choices (turnover, caps, ties) are first-order",
         "notJustified": "a US-specific conclusion, or that a better ranking could not beat the benchmark", "status": "TESTED_OUTCOME_EXPOSED",
         "futureWorkIs": "portfolio-construction lessons transfer; numbers do not"},
        {"studyId": "weekly-passive-first-v1 (US sleeve) and operational calibration", "universe": "production long-term research sleeve",
         "period": "155 blocks + weekly replay", "replay": "replay-v16", "features": "production alpha percentile + historical_calibration buckets",
         "horizon": "H126 calibration", "target": "net edge vs SPY after switching costs", "method": "historical_calibration.calibrate ordering gate",
         "outcomesRead": True, "survivorConditioned": True, "terminalOutcomesHandled": "SURVIVORSHIP_BIASED_PARTIAL", "untouchedValidation": False,
         "result": {"usOrderingTStat": 0.61, "usPath": "the rule never held a US stock; identical to SPY (docs/weekly-passive-first-v1.md)"},
         "economicSignificance": "the decision layer correctly defaulted to passive", "limitations": ["descriptive, outcome-exposed"],
         "justified": "the production US alpha percentile does not establish ordering under the calibration gate", "notJustified": "that no US ranking can",
         "status": "EXPLORATORY_INCONCLUSIVE", "futureWorkIs": "the passive default is the correct baseline B0"},
        {"studyId": "us-capital-allocation-alpha-v1", "universe": "S&P 500 non-financial", "period": "prospective only", "replay": "n/a",
         "features": "four exact-concept distribution features", "horizon": "H126", "target": "rank IC and 5-name book vs SPY/QQQ (prospective)",
         "method": "registered; REGISTERED_AUTHORIZATION = None", "outcomesRead": False, "survivorConditioned": "n/a (prospective)", "terminalOutcomesHandled": "registered rule",
         "untouchedValidation": True, "result": {"status": "REGISTERED_PENDING_OWNER_APPROVAL"}, "economicSignificance": "NOT_MEASURED",
         "limitations": ["17.9% weekly joint coverage, non-random", "always selects 5 names (no expected-return hurdle)"],
         "justified": "nothing about returns yet", "notJustified": "any alpha claim", "status": "NOT_TESTED", "futureWorkIs": "owner decision"},
        {"studyId": "us-cash-profitability-signal-v1 (H63, P3/P4)", "universe": "S&P 500 non-financial, priced", "period": "715 weekly signals, 692 matured cohorts",
         "replay": "replay-v16", "features": "cashOperatingProfitability residualised on sector + 4 controls", "horizon": "H63",
         "target": "return-unit residual-weighted spread", "method": "CT_SN, one-sided 95%", "outcomesRead": False, "survivorConditioned": True,
         "terminalOutcomesHandled": "UNRESOLVED cohort rule (0 unresolved on the survivor panel)", "untouchedValidation": False,
         "result": {"P3": get("h63", "/p3Status"), "supplement": get("h63supplement", "/verdict/supplementStatus"),
                    "P4": get("p4readiness", "/executionReadiness"), "P4BlockedBy": get("p4readiness", "/executionBlockedBy")},
         "resultSource": R["p4readiness"], "economicSignificance": "NOT_MEASURED", "limitations": ["331-371 names/date upper geometry uncalibrated", "survivor-conditioned"],
         "justified": "the inference method keeps nominal coverage on synthetic data of this geometry", "notJustified": "anything about alpha",
         "status": "NOT_TESTED", "futureWorkIs": "one-shot exploratory futility screen, owner-gated"},
        {"studyId": "outcome-blind source and PIT readiness audits", "universe": "S&P 500 PIT snapshots", "period": "2013-2026", "replay": "replay-v16 + Finnhub 704d7db6",
         "features": "availability, reasons, redundancy", "horizon": "n/a", "target": "n/a", "method": "counts and within-date rank correlations",
         "outcomesRead": False, "survivorConditioned": True, "terminalOutcomesHandled": "n/a", "untouchedValidation": "n/a",
         "result": {"reports": [R["source"], R["multifactor"], R["phase3"], R["universe"], R["capalloc"], R["unique"]]},
         "economicSignificance": "n/a", "limitations": ["55 fixed sample dates for redundancy"], "justified": "what exists, at what coverage, and how distinct",
         "notJustified": "any predictive claim", "status": "NOT_TESTED", "futureWorkIs": "measurement, reusable"},
    ]


def inventory() -> dict:
    surv = doc("survivorship")["regions"]["US"]
    return {
        "id": "us-factor-inventory-v1", "evidenceClass": "OUTCOME_BLIND_FACTOR_INVENTORY", "baseMainSha": BASE_MAIN,
        "readsReturns": False, "readsLabels": False, "fitsModels": False, "forwardPricesRead": False, "authorizes": "NOTHING",
        "productionEffect": "NONE",
        "categories": {
            "availability": {"READY_VERIFIED_PIT": "point-in-time, provenance verified, no survivorship conditioning (no historical US factor qualifies today)",
                             "AVAILABLE_WITH_CAVEATS": "computable PIT with a disclosed approximation or unverified basis",
                             "SURVIVOR_CONDITIONED": "computable PIT, but only on names that survived to have a price panel",
                             "NEEDS_SOURCE_OR_IDENTITY_VERIFICATION": "rests on a basis (share count, timing, identity) that is not yet verified",
                             "UNAVAILABLE": "no reachable PIT source", "NOT_IMPLEMENTED": "a source exists or may exist but no derivation exists"},
            "outcomeExposure": {"NOT_TESTED": "no committed study related it to a later US return",
                                "TESTED_OUTCOME_EXPOSED": "used in a study that read US outcomes; reuse on the same history is not independent",
                                "EXPLORATORY_INCONCLUSIVE": "read individually or as a sleeve; interval contains zero",
                                "EVIDENCE_AGAINST_SPECIFIC_HYPOTHESIS": "a pre-registered test's own failure criterion fired, scoped to that hypothesis",
                                "DATA_QUALITY_BLOCKED": "a study could not be evaluated because of input integrity",
                                "PROSPECTIVELY_VALIDATED": "confirmed on signals dated after a registration (none in the US)"}},
        "sharedLimitations": {
            "survivorship": {"departedMembers": surv["universe"]["departedMembers"], "departedWithoutUsablePanel": surv["sampleSurvivorship"]["noPanelDeparted"],
                             "currentWithoutPanel": surv["sampleSurvivorship"]["noPanelCurrent"], "terminatedPanels": surv["terminations"]["terminatedInPanel"],
                             "departedOnlyNoPanelPctByYear": {y: v["departedOnlyNoPanelPct"] for y, v in surv["memberDatesByYear"].items()},
                             "source": R["survivorship"],
                             "codexRecovery": "a separate effort is recovering departed-security prices; NOT assumed successful here (see roadmap dataQualityGate)"},
            "membershipSnapshots": m("unique", "/membershipSnapshotAge", "715 weekly signal dates"),
            "identity": {"tickerReuseDifferentIssuer": surv["identity"]["categoryCounts"]["TICKER_REUSE_DIFFERENT_ISSUER"],
                         "panelSymbolNotMemberHistory": len(surv["_sets"]["notOwnHistory"]), "verifiedRenames": surv["identity"]["categoryCounts"]["SAME_SECURITY_RENAME"],
                         "cikAvailableFrom": get("survivorship", "/inputs/usIdentityEvidence/firstSnapshotWithCik"), "source": R["survivorship"]},
            "secAccess": "data.sec.gov / www.sec.gov answer HTTP 403 from Actions egress: period-end shares, 8-K, Form 4, 13F unreachable",
            "liveVersusReplayFundamentals": "the live daily build reads Yahoo current-snapshot fundamentals (pipeline/fundamentals.py); PIT Finnhub fundamentals feed only the replay",
            "staleFilingSensitivity": m("unique", "/staleFilingSensitivity", NONFIN_55),
            "prospectiveBlockers": [PROSP_PRICE, PROSP_BS],
        },
        "jointAttrition": m("unique", "/jointAttritionNonFinancial", NONFIN_55),
        "studyEvidenceLedger": study_ledger(),
        "factors": factors(),
        "familyRedundancyReading": {
            "note": "R^2 of a feature's within-date rank on sector + one representative of every other family; uniqueShare = 1 - R^2. Pure-noise floor ~0.08.",
            "source": R["unique"],
            "highlyOverlappingAcrossFamilies": ["roe", "operatingProfitabilityToAssets", "cashOperatingProfitability", "bookYield"],
            "withinFamilyDuplicates": ["vol252 / downsideVol252 / beta252 / maxDD252", "operatingMargin / profitMargin", "relative126 / high52Distance / mom121",
                                       "incrementalDistributionOverOCF / totalCashDistributionChangeYoY (rho 0.95)"],
            "mostDistinctComputable": ["assetGrowthPct", "delta_roe", "delta_operatingMargin", "logTradedValue63", "debtToEquity", "earningsGrowth",
                                       "relativeStrengthBreadth52w", "accrualsToAssets"],
        },
        "references": {k: {"path": p, "sha256": sha(p)} for k, p in sorted(R.items())},
    }


def roadmap() -> dict:
    return {
        "id": "us-multifactor-research-roadmap-v1", "status": "PROPOSED_NOT_REGISTERED", "authorization": "NOT_AUTHORIZED", "authorizes": "NOTHING",
        "baseMainSha": BASE_MAIN, "productionEffect": "NONE", "readsReturns": False,
        "dependsOn": {"codexDepartedPriceRecovery": {
            "assumedVerdict": None, "possibleVerdicts": ["FULL", "PARTIAL", "INSUFFICIENT"],
            "rule": "no experiment below is registered until the recovery verdict is published and audited by dataQualityGate",
            "observedCandidateEvidence": {
                "pullRequest": get("integration", "/pr241Evidence/pullRequest"), "commit": get("integration", "/pr241Evidence/commit"),
                "state": get("integration", "/pr241Evidence/state"), "headline": m("integration", "/pr241Evidence/headline", "missing member sessions of the 212 no-panel identifiers"),
                "verdictStatus": "CANDIDATE_EVIDENCE_NOT_A_DATASET_VERDICT: no session is admitted until datasetAdmissionGate passes",
                "integrationReadiness": R["integration"]}}},
        "datasetAdmissionGate": {
            "id": "US_MF1_DATASET_ADMISSION_V1", "appliesBefore": "ANY forward-return reading for US-MF-1 (and US-MF-2/3 on a repaired snapshot)",
            "principle": "independent of whoever produced the candidate data; every check is outcome-free and measurable, and none chooses a tolerance from results",
            "checks": [
                {"id": "AD1_FROZEN_SNAPSHOT", "rule": "the admitted panel is one content-addressed input manifest (new replay generation); replay-v16, its manifest and #241's candidate files are read, never edited",
                 "measure": "manifest SHA-256 recorded; a second build reproduces it byte for byte"},
                {"id": "AD2_IDENTITY", "rule": "a session is admitted only if its security is tied to the member issuer by filing CIK, explicit '(Previously X)' or identical name at the switch; identity holds and ticker-only matches stay out",
                 "measure": "per-identifier status ADMITTED / IDENTITY_HOLD / NAME_ONLY / NONE with counts that reproduce #241's 5 / 170 / 37 before any reclassification"},
                {"id": "AD3_SINGLE_BASIS", "rule": "each feature and label reads ONE publisher basis per security; no splicing; back-adjusted-only or rounded-close-only sessions never feed as-traded features",
                 "measure": "per-session basis class published (public evidence gives it per identifier only: of 175 covered, D/F 59 / A-only 113 / E-only 3); zero rows combine bases"},
                {"id": "AD4_LINEAGE", "rule": "split and distribution events dated and cited for every admitted security; total-return labels use them once, never twice",
                 "measure": "count of admitted securities with event lineage; adjusted-vs-rebuilt level check per security"},
                {"id": "AD5_TERMINAL", "rule": "every H63 window that runs past a security's last observation is UNRESOLVED unless a cited terminal consideration exists",
                 "measure": "share of label windows UNRESOLVED by year, computed from observation EXISTENCE only, before any return"},
                {"id": "AD6_FUNDAMENTALS_LINK", "rule": "a filing is used only if its CIK maps to the member issuer during membership",
                 "measure": "per-identifier filing link status (currently 160 visible during membership, 41 none, 11 outside, 30 tickers with several CIKs)"},
                {"id": "AD7_RESIDUAL_SURVIVORSHIP", "rule": "publish the remaining no-admitted-panel member-date share by year after AD2-AD6; 2024-2026 improvement is 0 and is stated",
                 "measure": "per-year residual shares; DQ5 dual reading becomes binding wherever a residual is non-zero"},
                {"id": "AD8_NO_OUTCOME_ACCESS", "rule": "the admission build imports no label, return, model or portfolio module",
                 "measure": "counters zero and a spy test that fails on any outcome call"}],
            "result": "ADMITTED_FOR_DEVELOPMENT_ONLY or NOT_ADMITTED; never PROSPECTIVE, never PROMOTION_ELIGIBLE"},
        "dataQualityGate": {
            "id": "US_SURVIVORSHIP_DQ_GATE_V1", "appliesBefore": "registration of any historical (development) experiment below",
            "checks": [
                {"id": "DQ1_IDENTITY", "rule": "every recovered panel is tied to the departed member by same-CIK, explicit '(Previously X)' or identical name at the switch; "
                                               "ticker-only matches are rejected; a reused ticker's later issuer is never joined"},
                {"id": "DQ2_PROVENANCE", "rule": "recovered panels are a NEW hashed input snapshot (new replay generation); replay-v16 and its manifest stay frozen"},
                {"id": "DQ3_SAMPLE_SURVIVORSHIP", "rule": "publish departed-only no-panel member-date share by year before and after recovery; no tolerance is chosen, the residual is reported"},
                {"id": "DQ4_ENDPOINT_SURVIVORSHIP", "rule": "every held or ranked name whose label window crosses its last session carries cited terminal economics or is UNRESOLVED; "
                                                            "UNRESOLVED is never zero and never the last price"},
                {"id": "DQ5_BOUNDING", "rule": "every primary statistic is reported twice: unresolved dropped, and unresolved assigned the date's worst plausible outcome; "
                                               "a claim survives only if both readings agree in sign"},
                {"id": "DQ6_EXPOSURE_LABEL", "rule": "results on 2013-2026 are EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_US_HISTORY even with recovered names"}],
            "routing": {"FULL": "run development experiments on the repaired snapshot under DQ1-DQ6",
                        "PARTIAL": "run them with DQ5 bounding as the binding reading; publish which years remain unvouched",
                        "INSUFFICIENT": "do not wait: historical results stay SURVIVOR_CONDITIONED development evidence and the program moves to prospective collection"}},
        "researchBudget": {"primaryClaimsTotal": 3, "multiplicity": "Holm across the three primary claims if all are executed; descriptive readings carry no verdict",
                           "noParameterSweeps": True, "noFeatureSearch": True, "noNewMonteCarloUnlessAStatisticRequiresIt": True},
        "layers": {"layer1": "factor discovery: raw IC (descriptive), partial rank association (descriptive), return-unit residual spread (primary), never pooled",
                   "layer2": "selection: expected excess from expanding calibration, uncertainty, <=5 names, zero allowed, sector/liquidity caps, costs, SPY/QQQ comparison"},
        "comparisons": {"B0": "SPY held (passive default) / cash policy", "B1": "pre-specified interpretable price-only score: equal-weight ranks of mom121 and -vol252",
                        "B2": "B1 plus family-balanced accounting families (equal weight per FAMILY, not per feature)",
                        "B3": "Ridge on exactly the B2 features (regional_alpha_model Ridge config), walk-forward; descriptive only",
                        "B4": "investable: production select_portfolio_by_scores, <=5 names, sector cap 2, zero names when no net-of-cost edge, realistic regional costs"},
        "experiments": [
            {"id": "US-MF-1", "priority": 1, "name": "Family-balanced multifactor selection value",
             "hypothesis": "Within S&P 500 non-financials, a fixed equal-weight composite of FAMILY representatives (cash quality, accrual profitability, investment [-asset growth], "
                           "leverage [-D/E], value [earnings yield, reconstructed]) improves the H63 ordering of names beyond price-only information (B1), at the margin a <=5-name selector uses",
             "whyNewInformation": "cash quality, investment and leverage were never related to US outcomes; asset growth is 82% unique of the other families; the 31-feature model had no value or investment",
             "requiredPitFields": ["cashOperatingProfitability", "operatingProfitabilityToAssets", "assetGrowthPct", "debtToEquity", "earningsYield", "mom121", "vol252", "logTradedValue63", "sector"],
             "dataReadiness": "historical joint complete-case: 77.7% of non-financial member-dates through leverage, 55.1% once every family including reconstructed value is required "
                              "(jointAttrition, which also requires earningsGrowth; the exact US-MF-1 set is not separately measured); 2013 is mostly dark; prospectively blocked on total assets and the daily price ledger",
             "dataRecoveryDependency": "dataQualityGate routing",
             "horizon": {"primary": "H63", "descriptive": ["H21", "H126", "H252"],
                         "why": "the only US horizon with a calibrated inference geometry (US_H63_INFERENCE_CALIBRATION_V1)"},
             "baseline": "B1 (and B0 for the economic reading)",
             "primaryOutcome": "mean over weekly signal dates of the top-quintile-minus-universe H63 excess of the B2 composite MINUS the same for B1, within sector, paired by date (return units)",
             "method": "linear in returns, so calendar-time attribution + CT_SN; one-sided 95%",
             "calibration": "REQUIRED before registration: the paired top-quintile difference is not the statistic P3 calibrated; reuse the US H63 engine on this exact statistic only",
             "decisionReadings": ["B4 vs B0 after costs (descriptive on history; primary only prospectively)", "permutation null of B2 within the same construction (selection_null)",
                                  "names held, turnover split into replaced vs retargeted, cost drag"],
             "falsification": "upper one-sided 95% bound <= 0 under either DQ5 reading -> the accounting families do not improve the selection margin on this sample",
             "contributesToDecision": "directly: it is the ranking the <=5-name selector would consume, measured where the selector cuts",
             "forwardReturnReadingBlockedUntil": ["datasetAdmissionGate = ADMITTED_FOR_DEVELOPMENT_ONLY", "OD6 calibration of this exact statistic", "owner registration and authorization"],
             "exactTestAfterAdmission": {
                 "sample": "weekly signal dates (last US session of each completed week); S&P 500 members from the latest snapshot strictly before the date; Financials and Real Estate excluded; admitted sessions only",
                 "B1": "within-sector percentile of mean(rank(mom121), rank(-vol252))",
                 "B2": "within-sector percentile of the equal-weight mean of SIX family scores: price (= B1), cash quality rank(cashOperatingProfitability), accrual profitability "
                       "rank(operatingProfitabilityToAssets), investment rank(-assetGrowthPct), leverage rank(-debtToEquity), value rank(earningsYield)",
                 "missing": "complete case on every family (no imputation, no zero); attrition by year published; value is missing wherever the basis cannot give an as-traded price",
                 "label": "total return from the close of the first session after the signal date over 63 sessions, minus SPY over the same window (SPY cancels in the statistic)",
                 "statistic": "D_t = [mean H63 excess of the B2 top quintile within each sector - sector-universe mean] - [same for B1], averaged across sectors with names-per-sector weights",
                 "inference": "mean of D_t over dates; calendar-time attribution + CT_SN one-sided 95%; reported under both DQ5 readings",
                 "verdicts": {"SUPPORTED_DEVELOPMENT": "lower bound > 0 under both readings (development evidence only)",
                              "NOT_SUPPORTED": "upper bound <= 0 under either reading", "INCONCLUSIVE": "otherwise"},
                 "decisionObjective": "the 0-5-name book: B4 on B2 vs B4 on B1 vs SPY after realistic costs, zero names allowed, read descriptively on history and as the primary claim only prospectively"},
             "ownerAuthorizationRequired": True,
             "estimatedCost": {"featureBuild": "ESTIMATE ~40-45 min single-threaded for all 715 weekly dates (MEASURED: 55 sample dates took 4.4-4.6 min, ~1.5 min of it loading; per-date part scaled 13x)",
                               "calibration": "~1 h on 4 workers (US H63 P3 measured ~58 min)", "evaluation": "< 1 h", "money": "0 (GitHub Actions)"}},
            {"id": "US-MF-2", "priority": 2, "name": "Cash-confirmed profitability H63 (existing P4 lineage)",
             "hypothesis": "OCF/assets residualised on sector, size, momentum, volatility and accrual profitability orders H63 SPY-relative returns",
             "whyNewInformation": "never outcome-exposed in the US; but 70% of its rank is carried by the other families, so only the cash-vs-accrual residual is at stake",
             "requiredPitFields": ["cashOperatingProfitability", "logTradedValue63", "mom121", "vol252", "operatingProfitabilityToAssets", "sector"],
             "dataReadiness": "historical 83.4% primary-complete, median 285 names/date; prospectively blocked on total assets",
             "dataRecoveryDependency": "P4-v1 is frozen on replay-v16; a repaired snapshot would be a NEW version (P4-v2), never an edit of P4-v1",
             "horizon": {"primary": "H63"}, "baseline": "B0 controls (sector + 4 control ranks)",
             "primaryOutcome": "as frozen in docs/us-readiness/us-cash-profitability-study-protocol-v1.json", "method": "CT_SN one-sided 95% (P3 PASS; supplement PASS 150-244)",
             "calibration": "DONE for 150-330 names/date; 331-371 is uncalibrated and needs an explicit owner disposition",
             "falsification": "development upper bound <= 0 -> abandon before prospective collection",
             "contributesToDecision": "indirectly: decides whether the cash family enters US-MF-1's composite on its own merit", "ownerAuthorizationRequired": True,
             "resumeRule": {"INSUFFICIENT_recovery": "run P4-v1 as frozen (its survivorship is disclosed; waiting buys nothing)",
                            "FULL_or_PARTIAL_recovery": "owner chooses: run P4-v1 as frozen, OR retire it unexecuted and register P4-v2 = identical definitions + repaired snapshot + DQ gate; "
                                                        "never both (two looks at one hypothesis)"},
             "estimatedCost": {"execution": "minutes once authorized (machinery merged in #240)", "money": "0"}},
            {"id": "US-MF-3", "priority": 3, "name": "Investment and payout policy (asset growth, capex intensity, distributions)",
             "hypothesis": "Firms growing assets fastest earn lower subsequent H63 SPY-relative returns than peers, beyond profitability, size and momentum",
             "whyNewInformation": "assetGrowthPct is the most distinct computable characteristic measured (unique share 0.82, own-family R2 with capex 0.005) and was never in any US study",
             "requiredPitFields": ["assetGrowthPct", "capexIntensityPct", "operatingProfitabilityToAssets", "logTradedValue63", "mom121", "vol252", "sector"],
             "dataReadiness": "historical 92.0% of non-financial member-dates; prospectively blocked on total assets (same blocker as US-MF-2)",
             "dataRecoveryDependency": "dataQualityGate routing; acquisitions inflate asset growth, and acquired companies are exactly the departed names",
             "horizon": {"primary": "H63", "descriptive": ["H126", "H252"]}, "baseline": "B0 controls + accrual profitability",
             "primaryOutcome": "return-unit residual-weighted spread of -assetGrowthPct, the statistic form P3 calibrated", "method": "CT_SN one-sided 95%",
             "calibration": "covered by P3 only if names/date and control structure match the calibrated geometry; otherwise a targeted calibration",
             "falsification": "upper bound <= 0 under either DQ5 reading", "contributesToDecision": "supplies a candidate family for US-MF-1; standalone it is discovery only",
             "ownerAuthorizationRequired": True, "estimatedCost": {"featureBuild": "ESTIMATE ~40-45 min (same builder as US-MF-1)", "evaluation": "< 1 h", "money": "0"}}],
        "evidenceTiers": {
            "HISTORICAL_EXPLORATORY": {"window": "signals 2013-01 to the end of sealed prices", "label": "EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_US_HISTORY",
                                       "whyNotUnseen": ["the 615 already-priced panels carry most member-dates (69.7% in 2013, >97% from 2024) and were read by the four-factor audit, the 31-feature model, "
                                                        "fundamental acceleration, benchmark-alpha and weekly-passive-first",
                                                        "US-MF-1's families and horizon were chosen after those results were known",
                                                        "a repaired-names-only reading would be an outcome-defined subset (names that left the index), not a random holdout",
                                                        "the repair changes the sample, not the researcher's exposure to it"],
                                       "canSupport": "abandon-or-continue decisions and a bounded estimate of survivorship's effect", "cannotSupport": "promotion, liveValidated, capital allocation"},
            "PROSPECTIVE_PAPER": {"window": "signals dated after the merge that registers a frozen protocol", "label": "PROSPECTIVE_CONFIRMATORY",
                                  "prerequisites": ["persistent US daily price ledger (owner-gated)", "a total-assets source (Finnhub balance sheet omitted since 2026-10-07)",
                                                    "weekly membership capture", "append-only receipts before outcomes exist"],
                                  "currentState": "NOT_STARTED: no US prospective receipt exists", "canSupport": "the only confirmatory evidence this program can produce"},
            "rule": "a repaired historical panel is never described as unseen, out-of-sample or holdout data"},
        "nextImplementationTask": {
            "id": "US_DEPARTED_DATASET_ADMISSION_AUDIT_V1",
            "startsAfter": ("#241 is merged to main AND the owner restores the withheld candidate observations to durable, owner-controlled non-public "
                            "storage (#241 publishes aggregate findings only); this task never copies, edits or republishes them"),
            "what": "outcome-blind per-identifier and per-session admission table built from #241's candidate panel, the sealed identity evidence and the pinned Finnhub filings, implementing AD1-AD8",
            "acceptanceCriteria": [
                "reproduces #241 exactly before reclassifying: 212 identifiers, 186,910 covered and 69,492 missing member sessions, FULL/PARTIAL/NONE = 5/170/37",
                "every session carries exactly one of ADMITTED, IDENTITY_HOLD, NAME_ONLY, BASIS_UNRESOLVED, NO_OBSERVATION; counts sum to 256,402",
                "per-identifier basis classes reproduce 59 / 113 / 3 of the 175 covered identifiers; per-session basis counts are published for the first time",
                "zero rows splice two publisher bases; a test feeds a spliced series and expects refusal",
                "every H63 window that crosses a last observation without cited terminal consideration is UNRESOLVED; per-year UNRESOLVED shares published",
                "filing-to-issuer link status for all 212 identifiers; no filing with a non-matching CIK is admitted",
                "residual no-admitted-panel member-date share by year, 2013-2026, beside #241's before/after",
                "label/return/model/portfolio counters all zero and a spy test proves it; two runs byte-identical",
                "replay-v16, P4 files, #241 candidate files and sealed results byte-unchanged"],
            "doesNotDo": ["read a return", "admit a price without AD2-AD6", "register US-MF-1", "run P4", "Monte Carlo"]},
        "notBuiltYet": ["any new production model or selector", "a fitted factor-weight search", "EV/EBITDA, gross profitability, ROIC (no derivation or source)",
                        "13F, Form 4, short interest, consensus, 8-K (blocked)", "a broader-than-S&P 500 universe", "a new Monte Carlo campaign",
                        "any P4 authorization or lock", "dashboards or UI"],
        "ownerDecisions": [
            {"id": "OD1", "decision": "Which Codex recovery verdict triggers which route in dataQualityGate.routing (accept or amend the routing)"},
            {"id": "OD2", "decision": "P4: run P4-v1 as frozen, or retire it unexecuted for a P4-v2 on the repaired snapshot (US-MF-2.resumeRule)"},
            {"id": "OD3", "decision": "P4 upper geometry 331-371 names/date: require calibration or accept exploratory extrapolation"},
            {"id": "OD4", "decision": "Primary universe: S&P 500 non-financials (recommended) vs a broader liquid universe (needs new price, identity and fundamentals collection)"},
            {"id": "OD5", "decision": "Approve the persistent US daily price ledger and a total-assets source decision; without both, no US prospective evidence can accrue"},
            {"id": "OD6", "decision": "Authorize the targeted calibration of the US-MF-1 statistic (synthetic only; no outcome read)"},
            {"id": "OD7", "decision": "Merge or reject #241; only after it is on main can the dataset admission audit start and #242 be rebased onto main"},
            {"id": "OD8", "decision": "Confirm the redistribution/recurring-use rights of #241's public archives before any admitted panel is used beyond research"}],
        "universeRecommendation": {
            "primary": "dated S&P 500 snapshot members, Financials and Real Estate excluded for accounting families, priced and identity-verified",
            "why": "the only US universe with dated membership, PIT fundamentals for ~all members and (after recovery) bounded survivorship; a concentrated personal book needs liquid names",
            "notAutomatic": "a broader universe adds names, not independent dates: the four-factor audit's per-date IC variance is mostly common-factor exposure, so effective dates stay ~27 at H126",
            "expansionOptions": [m("universe", "/summary/union", "S&P 500 + Nasdaq-100 union symbols 2013-2026")],
            "snapshotCaveat": m("unique", "/membershipSnapshotAge", "715 weekly signal dates")},
        "references": {k: {"path": p, "sha256": sha(p)} for k, p in sorted(R.items())},
    }


def render(obj: dict) -> str:
    return json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    outputs = {INVENTORY: render(inventory()), ROADMAP: render(roadmap())}
    if args.check:
        stale = [str(p.relative_to(ROOT)) for p, text in outputs.items() if not p.exists() or p.read_text(encoding="utf-8") != text]
        if stale:
            print("STALE:", ", ".join(stale))
            return 1
        print("up to date")
        return 0
    for path, text in outputs.items():
        path.write_text(text, encoding="utf-8")
        print("wrote", path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
