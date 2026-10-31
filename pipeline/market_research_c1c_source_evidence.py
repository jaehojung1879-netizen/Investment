"""Market C (#289) source-evidence admission for the 069500.KS funded total-return accounting and KRW cash.

READ-ONLY OVER RETAINED, HASH-PINNED FILES. It computes no REENTRY/BASE/C0/C1 return, fits nothing, collects nothing and
changes no registered rule, threshold, calendar, cost or sealed result. Every sensitivity below is expressed PER 100% OF A
WEIGHT (ETF or cash), so its effect on any contrast is that coefficient times the mean-weight gap between two arms, and no
arm return is needed to state it. They are approximate accounting sensitivities, never corrections.

Four kinds of statement are kept apart in the output:
  confirmedSourceFacts      read from a retained official file and checked by this module
  approximateAccounting     a bound or coefficient that rests on a stated assumption
  missingHistoricalEvidence what no retained file supplies
  ownerOnlyDecisions        licensing, convention and threshold choices the code cannot make

`admission()` is fail-closed: it reads READY only when every record carries an official payment date AND every owner
decision is recorded, and today it reads BLOCKED with the exact counts.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .kr_integrated_alpha_portfolio import CASH_YIELD, cash_variant_rate, policy_rate_in_force

STUDY = "market-research-c1c-source-evidence-v1"
ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs" / "audits" / "kr-alpha-atlas-phase-c-integrity"
OUTPUT = ROOT / "docs" / "research-program" / "proposals" / "market-research-c1c-source-evidence-v1.json"

PINS = {
    "docs/audits/kr-alpha-atlas-phase-c-integrity/benchmark-reconciliation-corrected.json":
        "58580c4370ec2c5afa124f849afbc4fa7b5c879012e75ebbd48ee7c7a0e659a9",
    "docs/audits/kr-alpha-atlas-phase-c-integrity/sources/issuer-dividends.json":
        "3f23e3a8ce9c34506e1316bc8b6263c85cfa78086c3725743e02a3d653eeb0df",
    "data/bok-policy-rates.json": "a7edf0e532c7b54da9d962ebf12ff2552c90c783439fef99d7c761c5b9ea69ff",
    "data/kr-market-risk-anatomy-v1/sources/FDR_KS200/normalized.csv":
        "729a94b81dd45d1c5d1ab2ff692ec249bd5c9c4f24598d648d7f88010f193478",
    "docs/audits/kr-alpha-atlas-phase-c-integrity/sources/issuer-standard.xls":
        "cbdd7a0ce340228ddcfc714de637c512f73c2d691d84ae59a28cfb406d8437b9",
}
# Measured once at build time with xlrd (not a CI dependency): the as-traded close rebuilt from the corrected index and the 46
# cash amounts against the issuer's own close, every session. Recomputed by a test only where xlrd is installed, and read by
# nothing that gates admission.
RECORDED_ISSUER_CLOSE_CROSS_CHECK = {"sessions": 3612, "maxAbsRelativeDifference": 0.0, "tool": "xlrd",
                                     "status": "RECORDED_AT_BUILD_NOT_RECOMPUTED_IN_CI_WITHOUT_XLRD"}
STUDY_WINDOW = ("2012-01-02", "2026-09-14")
LAGS_SESSIONS_AFTER_EX = tuple(range(2, 11))
STATUTORY_TAX_RATE_PCT = 15.4  # NOT retained from an official source in this repository; a stated assumption only


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_pins():
    """Every input file is pinned by exact bytes; a moved file raises rather than being re-read silently."""
    for rel in PINS:
        if sha256(ROOT / rel) != PINS[rel]:
            raise ValueError("SOURCE_EVIDENCE_INPUT_CHANGED:" + rel)


def load_chain(path=None):
    """(total-return quotes indexed by session, 46-record distribution chain, official as-traded endpoint quote)."""
    report = json.loads(Path(path or ROOT / next(iter(PINS))).read_text())
    quotes = pd.Series({q["date"]: float(q["Close"]) for q in report["correctedBenchmarkQuotes"]})
    quotes.index = pd.to_datetime(quotes.index)
    chain = pd.DataFrame(report["distributions"])
    chain["ex"] = pd.to_datetime(chain.exDate)
    chain["record"] = pd.to_datetime(chain.recordDate)
    chain["cash"] = chain.cashKrwPerUnit.astype(float)
    return quotes.sort_index(), chain.sort_values("ex").reset_index(drop=True), float(report["independentEndpoint"]["officialRawQuote"])


def load_official_payments(path=None):
    """Issuer API rows: record date, ACTUAL payment date, cash and the per-unit taxable base."""
    rows = json.loads(Path(path or ROOT / list(PINS)[1]).read_text())["dividList"]
    out = pd.DataFrame([{"record": pd.to_datetime(r["basicD"]), "pay": pd.to_datetime(r["payD"]),
                         "cash": float(r["dividA"]), "taxBase": float(r["taxDividA"])} for r in rows])
    if out.record.duplicated().any():
        raise ValueError("DUPLICATE_OFFICIAL_RECORD_DATE")
    return out.sort_values("record").reset_index(drop=True)


def as_traded_prices(quotes, chain, endpoint_raw):
    """Invert the once-only gross reinvestment: the as-traded close implied by the total-return index and the cash chain.

    On an ex-date the index ratio is (P_ex + D) / P_prev, so P_prev = (P_ex + D) / ratio and the adjustment factor is
    constant between ex-dates. Anchored on the issuer's official raw endpoint quote."""
    k = endpoint_raw / quotes.iloc[-1]
    price = quotes * k
    sessions = quotes.index
    for ex, cash in sorted(zip(chain.ex, chain.cash), reverse=True):
        i = sessions.get_loc(ex)
        ratio = quotes.iloc[i] / quotes.iloc[i - 1]
        previous = (quotes.iloc[i] * k + cash) / ratio
        k = previous / quotes.iloc[i - 1]
        price.iloc[:i] = quotes.values[:i] * k
    return price


def payment_facts(quotes, chain, official):
    """Per-record payment status. A date is OFFICIAL only when the issuer row matches on record date AND cash; never inferred."""
    sessions = quotes.index
    merged = chain.merge(official, on="record", how="left", suffixes=("", "Official"))
    matched = merged.pay.notna()
    cash_ok = bool((merged.loc[matched, "cash"] == merged.loc[matched, "cashOfficial"]).all())
    rec = merged[matched]
    lag_rec = [sessions.searchsorted(p) - sessions.searchsorted(r) for p, r in zip(rec.pay, rec.record)]
    lag_ex = [sessions.searchsorted(p) - sessions.searchsorted(e) for p, e in zip(rec.pay, rec.ex)]
    cal = (rec.pay - rec.record).dt.days
    unresolved = merged[~matched]
    return {
        "records": int(len(merged)), "officialPaymentDate": int(matched.sum()), "paymentDateUnresolved": int((~matched).sum()),
        "officialCashEqualsChainCash": cash_ok,
        "exDateIsSessionAndRecordIsNextSession": bool(all(
            e in sessions and sessions[sessions.searchsorted(e) + 1] == r for e, r in zip(chain.ex, chain.record))),
        "paymentSessionsAfterRecord": sorted({int(x) for x in lag_rec}), "paymentSessionsAfterEx": sorted({int(x) for x in lag_ex}),
        "paymentCalendarDaysAfterRecord": {"min": int(cal.min()), "max": int(cal.max())},
        "firstUnresolved": {"exDate": str(unresolved.ex.iloc[0].date()), "recordDate": str(unresolved.record.iloc[0].date())},
        "lastUnresolvedExDate": str(unresolved.ex.iloc[-1].date()),
        "firstOfficialExDate": str(rec.ex.iloc[0].date()),
        "unresolvedExDatesByYear": {str(k): int(v) for k, v in unresolved.groupby(unresolved.ex.dt.year).size().items()},
    }


def years_between(a, b):
    return (pd.Timestamp(b) - pd.Timestamp(a)).days / 365.25


def _timing_term(price, ex, cash, lag):
    """First-order value of buying at the close `lag` sessions after the ex-date instead of at the ex-date close."""
    sessions = price.index
    i = sessions.get_loc(ex)
    j = min(i + lag, len(sessions) - 1)
    return cash / price.iloc[i] * (price.iloc[j] / price.iloc[i] - 1.0)


def timing_sensitivity(price, chain, official):
    """Payment-timing effect per 100% ETF weight, pp/yr: the 20 official payments FIXED at their observed dates, the unresolved
    26 bounded EVENT BY EVENT over `LAGS_SESSIONS_AFTER_EX`.

    The bound is the mixed-lag envelope: the total lies in [known + sum_i min_L d_i(L), known + sum_i max_L d_i(L)]. The
    common-lag figure (one L for every unresolved event) is reported as a SCENARIO only: max_L sum_i |d_i(L)| is not an upper
    bound when different events can have different lags. The lag range itself is an assumption for the 26: all 20 observed
    payments are exactly 3 sessions after the ex-date, nothing retained shows the earlier ones were paid on the same rule."""
    sessions = price.index
    years = years_between(sessions[0], sessions[-1])
    paid = chain.merge(official[["record", "pay"]], on="record", how="left")
    known, unknown = paid[paid.pay.notna()], paid[paid.pay.isna()]
    known_total = sum(_timing_term(price, r.ex, r.cash, sessions.get_loc(r.pay) - sessions.get_loc(r.ex)) for r in known.itertuples())
    grid = np.array([[_timing_term(price, r.ex, r.cash, lag) for lag in LAGS_SESSIONS_AFTER_EX] for r in unknown.itertuples()])
    lower, upper = known_total + grid.min(axis=1).sum(), known_total + grid.max(axis=1).sum()
    scale = 100 / years
    common = {str(lag): {"signedPpPerYear": round(float(grid[:, k].sum() * scale), 5),
                         "sumOfAbsolutePpPerYear": round(float(np.abs(grid[:, k]).sum() * scale), 5)}
              for k, lag in enumerate(LAGS_SESSIONS_AFTER_EX)}
    return {"unit": "percentage points per year per 100% ETF weight", "knownOfficialEvents": int(len(known)),
            "unresolvedEvents": int(len(unknown)),
            "knownEventsFixedAtObservedDatesPpPerYear": round(float(known_total * scale), 5),
            "mixedLagSignedInterval": {"lowerPpPerYear": round(float(lower * scale), 5), "upperPpPerYear": round(float(upper * scale), 5)},
            "boundOnAbsoluteEffectPpPerYear": round(float(max(abs(lower), abs(upper)) * scale), 5),
            "sumOfPerEventWorstAbsolute": round(float((np.abs(known_total) + np.abs(grid).max(axis=1).sum()) * scale), 5),
            "lagRangeSessionsAfterEx": [LAGS_SESSIONS_AFTER_EX[0], LAGS_SESSIONS_AFTER_EX[-1]],
            "lagRangeStatus": "ASSUMPTION_FOR_THE_UNRESOLVED_EVENTS_OBSERVED_LAG_IS_3_ON_ALL_20_OFFICIAL",
            "commonLagScenarioNotABound": common}


def _funded_scenario(price, chain, official, quotes, assumed_lag):
    sessions = price.index
    years = years_between(sessions[0], sessions[-1])
    paid = chain.merge(official[["record", "pay"]], on="record", how="left")
    last = len(sessions) - 1
    schedule, lags = {}, []
    for r in paid.itertuples():
        i = sessions.get_loc(r.ex)
        j = sessions.get_loc(r.pay) if pd.notna(r.pay) else min(i + assumed_lag, last)
        schedule[i] = (r.cash, j)
        lags.append(j - i)
    units_a = units_b = 1.0
    buys = {}
    for i in range(len(sessions)):
        if i in buys:
            units_b += buys.pop(i) / price.iloc[i]
        if i in schedule:
            cash, pay_i = schedule[i]
            units_a += cash * units_a / price.iloc[i]
            buys[pay_i] = buys.get(pay_i, 0.0) + cash * units_b
    value_a, value_b = units_a * price.iloc[-1], units_b * price.iloc[-1] + sum(buys.values())
    identity = value_a / price.iloc[0] / (quotes.iloc[-1] / quotes.iloc[0]) - 1.0
    exact = ((value_b / value_a) ** (1 / years) - 1) * 100
    first_order = sum(_timing_term(price, r.ex, r.cash, lag) for r, lag in zip(paid.itertuples(), lags)) / years * 100
    return exact, first_order, identity


def exact_funded_comparison(price, chain, official, quotes, assumed_lag=3):
    """Exact share-level comparison on the ETF alone, with no first-order approximation: reinvest each distribution at the
    ex-date close (A, the corrected index) versus hold it as cash earning nothing until the payment-date close (B).

    Official events use their real payment date, the unresolved ones `assumed_lag` (one common lag per scenario). SCENARIOS, not
    bounds: the first-order sum used in `timing_sensitivity` omits the compounding of the delayed units, and the size of that
    omission is shown for every common lag. Path A reproducing the corrected index validates the simulation itself."""
    exact, first_order, identity = _funded_scenario(price, chain, official, quotes, assumed_lag)
    by_lag = {}
    for lag in LAGS_SESSIONS_AFTER_EX:
        e, f, _ = _funded_scenario(price, chain, official, quotes, lag)
        by_lag[str(lag)] = {"exactPpPerYear": round(float(e), 5), "firstOrderPpPerYear": round(float(f), 5),
                            "approximationErrorPpPerYear": round(float(e - f), 5)}
    return {"scenario": f"official payment dates where known, {assumed_lag} sessions after ex otherwise",
            "exactPpPerYear": round(float(exact), 5), "firstOrderPpPerYear": round(float(first_order), 5),
            "approximationErrorPpPerYear": round(float(exact - first_order), 5),
            "byCommonLag": by_lag,
            "largestAbsoluteApproximationErrorPpPerYear": max(abs(v["approximationErrorPpPerYear"]) for v in by_lag.values()),
            "largestAbsoluteExactEffectPpPerYear": max(abs(v["exactPpPerYear"]) for v in by_lag.values()),
            "pathAReproducesCorrectedIndexRelativeResidual": float(f"{identity:.3e}"),
            "status": "SCENARIOS_NOT_A_BOUND_MIXED_LAGS_NOT_ENUMERATED"}


def tax_basis(price, chain, official):
    """Issuer-stated taxable base per unit on the official records, and the drag implied per 1 percentage point of tax rate."""
    sessions = price.index
    matched = chain.merge(official, on="record", suffixes=("", "Official"))
    previous = np.array([price.iloc[sessions.get_loc(e) - 1] for e in matched.ex])
    span = years_between(matched.ex.iloc[0] - pd.Timedelta(days=1), sessions[-1])
    share = matched.taxBase / matched.cashOfficial
    base_yield = float((matched.taxBase.values / previous).sum() / span * 100)
    gross_yield = float((matched.cash.values / previous).sum() / span * 100)
    return {"records": int(len(matched)), "taxableShareOfCash": {"min": round(float(share.min()), 4), "max": round(float(share.max()), 4),
                                                              "mean": round(float(share.mean()), 4)},
            "grossYieldPpPerYear": round(gross_yield, 4), "taxableBaseYieldPpPerYear": round(base_yield, 4),
            "dragPpPerYearPerOnePointOfTaxRate": round(base_yield / 100, 5),
            "dragAtAssumedStatutoryRatePpPerYear": round(base_yield * STATUTORY_TAX_RATE_PCT / 100, 4),
            "assumedStatutoryRatePct": STATUTORY_TAX_RATE_PCT,
            "rateStatus": "UNVERIFIED_ASSUMPTION_NOT_RETAINED_FROM_AN_OFFICIAL_SOURCE_IN_THIS_REPOSITORY",
            "coverage": "only the issuer's 20 most recent distributions state a taxable base; the other 26 are UNKNOWN, not zero",
            "coverageSpan": {"firstExDate": str(matched.ex.iloc[0].date()), "lastExDate": str(matched.ex.iloc[-1].date()),
                             "years": round(float(span), 3)},
            "scope": "the drag is measured over that sub-period only, not the 2012-2026 history, and is not a validated investor tax treatment",
            "unit": "percentage points per year per 100% ETF weight"}


def ks200_reconciliation(quotes, ks200):
    """Calendar-year excess of the corrected total-return index over the KS200 price index (committed FDR series)."""
    both = pd.concat({"tr": quotes, "ks": ks200}, axis=1).dropna()
    year_end = both.groupby(both.index.year).last()
    annual = (year_end / year_end.shift(1) - 1).dropna() * 100
    gap = (annual.tr - annual.ks)
    return {"annualExcessOfTotalReturnOverKs200PricePp": {str(k): round(float(v), 3) for k, v in gap.items()},
            "mean2017to2024": round(float(gap.loc[2017:2024].mean()), 3),
            "meaning": "a gross total-return index should exceed the price index by about the distribution yield; "
                       "no unexplained accrual is visible in this series (the replay-v16 069500 series applies each distribution about twice)"}


def cash_sensitivity(events, sessions):
    """BOK base-rate proxy over the study window, reusing the integrated study's frozen step function and variants.

    Per 100% CASH weight, pp/yr. NOT an investable KRW cash return; it brackets the choice between the registered ZERO
    scenario and the proxy."""
    sessions = [pd.Timestamp(s) for s in sessions]
    days, weighted = 0, {"ZERO": 0.0, "PROXY": 0.0, "PROXY_MINUS_HAIRCUT": 0.0}
    carried = 0
    for previous, current in zip(sessions[:-1], sessions[1:]):
        gap = (current - previous).days
        rate = policy_rate_in_force(events, str(previous.date()))
        for variant in weighted:
            weighted[variant] += cash_variant_rate(rate, variant) * gap
        days += gap
        carried += int(str(current.date()) > "2026-09-07")
    return {"unit": "percentage points per year per 100% cash weight", "series": CASH_YIELD["series"],
            "status": CASH_YIELD["status"],
            "meanRatePctPerYear": {k: round(v / days, 4) for k, v in weighted.items()},
            "sessionsCarriedFromLastVerified": carried, "fileVerifiedThrough": "2026-09-07"}


def contrast_coefficients(timing, tax, cash):
    """Effect on (arm A - arm B) per 10pp of mean weight gap, signed toward the MORE-EXPOSED arm. Illustrative sensitivity."""
    cash_effect = cash["meanRatePctPerYear"]["PROXY"] * 0.10
    haircut = cash["meanRatePctPerYear"]["PROXY_MINUS_HAIRCUT"] * 0.10
    tax_effect = -tax["dragAtAssumedStatutoryRatePpPerYear"] * 0.10
    return {"unit": "pp/yr per 10pp of mean ETF-weight gap between two arms; positive favours the MORE-EXPOSED arm",
            "zeroCashVersusBokProxy": round(cash_effect, 4),
            "zeroCashVersusBokProxyMinusHaircut": round(haircut, 4),
            "distributionTaxAtAssumedRate": round(tax_effect, 4),
            "paymentTimingMixedLagBoundAbs": round(timing["boundOnAbsoluteEffectPpPerYear"] * 0.10, 5),
            "status": "UNVERIFIED_SENSITIVITY_NOT_A_CORRECTION",
            "note": "cash and tax act in opposite directions; none of these is applied to any path"}


OWNER_DECISIONS = (
    "RIGHTS: retention and downstream research use of the KODEX/Samsung Asset Management distribution and quote files, of the "
    "FRED-served series (VIXCLS carries a Cboe 'reprinted with permission' notice that is not a downstream grant) and of the KS200 "
    "series; HTTP 200 or a retained checksum is not permission",
    "CASH: which investable KRW cash return (or the registered ZERO scenario) the economic reading uses; the BOK base "
    "rate is a non-investable proxy",
    "TOTAL_RETURN: accept ex-date-close gross reinvestment as the funded ETF basis with the documented payment-timing "
    "bound, or require pay-date reinvestment (needs 26 further payment dates), and pre-tax versus after-tax",
    "CRITERIA: economic tolerances, inference and multiplicity, first evaluation and support, exact-hash execution packet",
)


def evidence():
    verify_pins()
    quotes, chain, endpoint = load_chain()
    official = load_official_payments()
    price = as_traded_prices(quotes, chain, endpoint)
    ks = pd.read_csv(ROOT / "data/kr-market-risk-anatomy-v1/sources/FDR_KS200/normalized.csv", parse_dates=["date"]).set_index("date").value
    events = json.loads((ROOT / "data/bok-policy-rates.json").read_text())["events"]
    window = quotes.index[(quotes.index >= STUDY_WINDOW[0]) & (quotes.index <= STUDY_WINDOW[1])]
    facts = payment_facts(quotes, chain, official)
    timing = timing_sensitivity(price, chain, official)
    funded = exact_funded_comparison(price, chain, official, quotes)
    tax = tax_basis(price, chain, official)
    cash = cash_sensitivity(events, window)
    return {
        "studyId": STUDY, "evidenceClass": "RETAINED_SOURCE_READ_ONLY_NO_STRATEGY_RETURN",
        "inputs": dict(PINS),
        "confirmedSourceFacts": {
            "distributions": facts,
            "asTradedPriceReconstruction": {
                "method": "invert the once-only gross reinvestment from the corrected index and the 46 cash amounts, anchored on the official raw endpoint quote",
                "sessions": int(len(price)), "endpointRawQuote": endpoint,
                "issuerAsTradedCloseCrossCheck": RECORDED_ISSUER_CLOSE_CROSS_CHECK,
            },
            "taxBasis": tax,
            "ks200Reconciliation": ks200_reconciliation(quotes, ks),
        },
        "approximateAccounting": {"paymentTiming": timing, "exactFundedComparison": funded, "cash": cash,
                                  "contrastPer10ppExposureGap": contrast_coefficients(timing, tax, cash)},
        "missingHistoricalEvidence": [
            f"{facts['paymentDateUnresolved']} of {facts['records']} distributions have no official payment date "
            f"(first: ex {facts['firstUnresolved']['exDate']}, record {facts['firstUnresolved']['recordDate']}); the retained annual reports list "
            "the record date only (지급기준일), and the issuer API serves the 20 most recent",
            "taxable base for the 26 earlier distributions",
            "any investable KRW cash-return series with dated source evidence (retained ECOS evidence covers the base rate 722Y001/0101000 "
            "and 3-year Treasuries only, status REVISED_HISTORY, no release vintage)",
            "release/vintage evidence for KS200, VIX and DGS inputs beyond the single 2012-01-03 H.15 release",
        ],
        "ownerOnlyDecisions": list(OWNER_DECISIONS),
    }


def admission(ev):
    """Fail-closed: READY only with every payment date official AND every owner decision recorded (none is, in code)."""
    facts = ev["confirmedSourceFacts"]["distributions"]
    reasons = []
    if facts["paymentDateUnresolved"]:
        reasons.append(f"PAYMENT_DATE_UNRESOLVED:{facts['paymentDateUnresolved']}_OF_{facts['records']}")
    if not facts["officialCashEqualsChainCash"]:
        reasons.append("OFFICIAL_CASH_DISAGREES_WITH_CHAIN")
    reasons.extend(["OWNER_DECISION_UNRECORDED:" + d.split(":")[0].replace(" ", "_") for d in ev["ownerOnlyDecisions"]])
    return {"etfDistributionFunding": "BLOCKED" if reasons else "READY_FOR_SEPARATE_APPROVAL", "reasons": reasons,
            "historicalExecution": "BLOCKED"}


def main():
    ev = evidence()
    ev["admission"] = admission(ev)
    text = json.dumps(ev, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    if OUTPUT.exists() and OUTPUT.read_text() != text:
        raise SystemExit("REFUSING_TO_OVERWRITE_DIFFERENT_COMMITTED_EVIDENCE")
    OUTPUT.write_text(text)
    print(text[:1500])


if __name__ == "__main__":
    main()
