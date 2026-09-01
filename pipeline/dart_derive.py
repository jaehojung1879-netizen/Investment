"""Raw DART filings into the factor inputs production actually reads.

WHAT THIS TURNS INTO WHAT. `dart_fundamentals` stores filings as DART states
them. `longterm.score_cross_section` reads ratios and per-share numerators.
This is the step between, and it is separate on purpose: a derivation found
wrong has to be fixable without re-fetching a backfill that took fourteen hours.

THE COLUMN SEMANTICS, MEASURED RATHER THAN ASSUMED. The collector's field
inventory, split by report code and statement, settled how each figure has to be
read. From 2,927 filings:

    보고서    제표    당기      당기누계    누계/당기
    1분기     IS      1,875     1,874       99.9%
    3분기     IS      1,985     1,985      100.0%
    사업      IS      2,017         0        0.0%
    1분기     CF     12,726         0        0.0%
    3분기     CF     15,847         0        0.0%

So the income statement carries BOTH columns on quarterly reports and only the
period column on the annual one: `thstrm_amount` is that quarter alone,
`thstrm_add_amount` the year to date. The cash flow statement carries one column
at every report — which leaves what it means unresolved by field presence, so it
was resolved by value over 84 companies in 2023:

    Q3 / 연간            중앙값 0.68     누적이면 9/12 = 0.75
    (Q1+H1+Q3) / 연간    중앙값 1.31     독립 분기면 0.75. 중복 계상 = 누적

The single cash-flow column is the report period's cumulative figure. Income and
cash flow therefore follow DIFFERENT rules, and reading a Q3 operating cash flow
as three months — then annualising it — would have inflated free cash flow four
times over, with nothing raising an error.

TTM IS A ROLLFORWARD, NOT AN ANNUALISATION. Multiplying a nine-month figure by
4/3 invents a quarter nobody reported. The trailing twelve months ending at a
quarterly filing is last year's annual, minus last year's same year-to-date,
plus this year's:

    TTM(Y, Q3) = FY(Y-1) - cum(Y-1, Q3) + cum(Y, Q3)

which needs both prior-year filings. When either is missing the answer is None:
a factor that is absent costs coverage, and a factor that is invented costs the
whole claim.

BALANCE SHEET ITEMS ARE NOT TTM. Equity and debt are levels at a date, and
averaging or rolling them forward would answer a question nobody asked. They are
taken from the filing as stated.
"""
from __future__ import annotations

from . import dart_fundamentals as DF

ANNUAL = "11011"

# Statement divisions whose quarterly figures are stated for the quarter alone,
# with the year-to-date total in a second column. Everything else states one
# column and it is the report period's cumulative figure.
PERIOD_AND_CUMULATIVE_STATEMENTS = ("IS", "CIS")

# How a derived figure was arrived at, published beside it. A rollforward and a
# directly stated annual figure are both trustworthy; they are not the same
# thing, and a reader comparing two companies deserves to know which they have.
BASIS_ANNUAL = "ANNUAL_AS_FILED"
BASIS_ROLLFORWARD = "TTM_ROLLFORWARD"
BASIS_INCOMPLETE = "INCOMPLETE_CHAIN"


def cumulative_amount(record: dict, account: str) -> float | None:
    """The figure covering this filing's whole reporting period.

    Q1 covers three months, the half-year six, Q3 nine and the annual twelve —
    so "the period" differs per report, and the column that states it differs
    per statement. Choosing the wrong one is silent: a Q3 income figure read
    from the period column is one quarter being treated as three.
    """
    entry = (record.get("accounts") or {}).get(account)
    if not entry:
        return None
    amounts = entry.get("amounts") or {}
    if str(record.get("reportCode")) == ANNUAL:
        return amounts.get("thstrm_amount")
    if str(entry.get("statement")) in PERIOD_AND_CUMULATIVE_STATEMENTS:
        return amounts.get("thstrm_add_amount")
    return amounts.get("thstrm_amount")


def level_amount(record: dict, account: str) -> float | None:
    """A balance at the filing date. No period, so no cumulative question."""
    entry = (record.get("accounts") or {}).get(account)
    if not entry:
        return None
    return (entry.get("amounts") or {}).get("thstrm_amount")


def index_filings(records: list[dict]) -> dict[tuple[int, str], dict]:
    """One ticker's filings by (fiscal year, report code)."""
    return {(int(r["fiscalYear"]), str(r["reportCode"])): r for r in records}


def trailing_twelve_months(by_key: dict[tuple[int, str], dict], year: int,
                           code: str, account: str) -> tuple[float | None, str]:
    """Twelve months of a flow account ending at this filing, and how.

    The annual report states it outright. A quarterly one is rolled forward
    from the prior year, which is why both prior-year filings have to be in
    hand — and why a missing one yields None rather than an annualisation.
    """
    current = by_key.get((year, code))
    if current is None:
        return None, BASIS_INCOMPLETE
    this_period = cumulative_amount(current, account)
    if this_period is None:
        return None, BASIS_INCOMPLETE
    if code == ANNUAL:
        return this_period, BASIS_ANNUAL

    prior_annual = by_key.get((year - 1, ANNUAL))
    prior_same = by_key.get((year - 1, code))
    if prior_annual is None or prior_same is None:
        return None, BASIS_INCOMPLETE
    full_year = cumulative_amount(prior_annual, account)
    same_stage = cumulative_amount(prior_same, account)
    if full_year is None or same_stage is None:
        return None, BASIS_INCOMPLETE
    return full_year - same_stage + this_period, BASIS_ROLLFORWARD


def _ratio(numerator: float | None, denominator: float | None,
           positive_denominator: bool = True) -> float | None:
    """A quotient, or None where the denominator cannot carry one.

    Negative equity is a real state and a ROE computed on it is a number with
    the wrong sign that ranks a distressed company as a quality name — so
    ratios whose denominator must be positive to mean anything say None
    instead.
    """
    if numerator is None or denominator is None:
        return None
    if denominator == 0 or (positive_denominator and denominator < 0):
        return None
    return numerator / denominator


def derive_fields(by_key: dict[tuple[int, str], dict], year: int, code: str,
                  shares: float | None = None) -> tuple[dict, dict]:
    """The factor inputs for one filing, with a note on how each was built.

    Returns (fields, basis). `fields` follows PIT_FUNDAMENTALS_V1: ratios
    outright, and per-share NUMERATORS rather than yields — a filing cannot
    state a yield, because a yield needs a price and the price moves every day
    after the filing. `pit_data.derive_price_relative` divides them by the
    close on the replay date.
    """
    current = by_key.get((year, code))
    if current is None:
        return {}, {}

    net_income, ni_basis = trailing_twelve_months(by_key, year, code, "당기순이익")
    revenue, rev_basis = trailing_twelve_months(by_key, year, code, "매출액")
    operating, op_basis = trailing_twelve_months(by_key, year, code, "영업이익")
    cash_flow, cf_basis = trailing_twelve_months(by_key, year, code, "영업활동현금흐름")
    capex, capex_basis = trailing_twelve_months(by_key, year, code, "유형자산의취득")

    equity = level_amount(current, "자본총계")
    debt = level_amount(current, "부채총계")

    # A year earlier, at the same stage of the year, so growth compares twelve
    # months with twelve months rather than a quarter with a year.
    prior_ni, _ = trailing_twelve_months(by_key, year - 1, code, "당기순이익")

    fields: dict = {
        "roe": _ratio(net_income, equity),
        "operatingMargin": _ratio(operating, revenue),
        "profitMargin": _ratio(net_income, revenue),
        # Leverage is a ratio of two levels; equity must be positive for it to
        # mean "times equity" rather than a sign flip.
        "debtToEquity": _ratio(debt, equity),
        "earningsGrowth": ((net_income - prior_ni) / abs(prior_ni)
                           if net_income is not None and prior_ni not in (None, 0)
                           else None),
    }

    # Free cash flow is operating cash flow less what was spent to stay in
    # business. `유형자산의취득` is reported as a positive outflow in the
    # investing section, so it is subtracted.
    free_cash_flow = (cash_flow - abs(capex)
                      if cash_flow is not None and capex is not None else None)

    if shares and shares > 0:
        fields["epsTtm"] = net_income / shares if net_income is not None else None
        fields["bookValuePerShare"] = equity / shares if equity is not None else None
        fields["fcfPerShare"] = (free_cash_flow / shares
                                 if free_cash_flow is not None else None)

    basis = {
        "netIncome": ni_basis, "revenue": rev_basis, "operating": op_basis,
        "cashFlow": cf_basis, "capex": capex_basis,
        "sharesAvailable": bool(shares and shares > 0),
        "freeCashFlowAvailable": free_cash_flow is not None,
    }
    return {k: v for k, v in fields.items() if v is not None}, basis


def pit_record(filing: dict, fields: dict, basis: dict) -> dict:
    """One PIT_FUNDAMENTALS_V1 row, ready for `FundamentalStore.from_jsonl`.

    `availableFrom` is carried through untouched from the receipt date. It is
    the only thing that licenses use, and re-deriving it here would be a second
    definition of the one field the whole collection exists for.
    """
    return {
        "ticker": filing["ticker"],
        "reportPeriod": f"{filing['fiscalYear']}-{filing['reportCode']}",
        "availableFrom": filing["availableFrom"],
        "filingDate": filing["availableFrom"],
        "publicationDate": filing["availableFrom"],
        "currency": filing.get("currency") or "KRW",
        "source": filing.get("source"),
        "sourceAsOf": filing.get("collectedAt"),
        "revisionStatus": filing.get("fsDiv"),
        "fields": fields,
        "derivation": basis,
    }


def build_for_ticker(records: list[dict],
                     shares_by_key: dict[tuple[int, str], float] | None = None
                     ) -> list[dict]:
    """Every derivable filing for one ticker, oldest visible first.

    A filing that yields no usable field is dropped rather than emitted empty:
    `FundamentalStore` would return it as the newest visible record and hide
    the older one that actually had numbers.
    """
    by_key = index_filings(records)
    shares_by_key = shares_by_key or {}
    out: list[dict] = []
    for (year, code), filing in sorted(by_key.items()):
        fields, basis = derive_fields(by_key, year, code,
                                      shares_by_key.get((year, code)))
        if not fields:
            continue
        out.append(pit_record(filing, fields, basis))
    return sorted(out, key=lambda row: str(row["availableFrom"]))


def coverage(rows: list[dict]) -> dict:
    """Which factor inputs the derivation actually produced.

    Quality is sourceable from the statements alone; value needs a share count
    the statement endpoint does not carry. Reporting them separately is what
    keeps "we collected fundamentals" from being read as "the value sleeve
    works".
    """
    counters = {key: 0 for key in
                ("roe", "operatingMargin", "profitMargin", "debtToEquity",
                 "earningsGrowth", "epsTtm", "bookValuePerShare", "fcfPerShare")}
    bases: dict[str, int] = {}
    for row in rows:
        for key in counters:
            if (row.get("fields") or {}).get(key) is not None:
                counters[key] += 1
        basis = (row.get("derivation") or {}).get("netIncome")
        if basis:
            bases[basis] = bases.get(basis, 0) + 1
    total = len(rows) or 1
    return {
        "rows": len(rows),
        "fieldCoveragePct": {k: round(100.0 * v / total, 2)
                             for k, v in sorted(counters.items())},
        "netIncomeBasis": bases,
        "qualityComplete": all(counters[k] for k in
                               ("roe", "operatingMargin", "profitMargin",
                                "debtToEquity")),
        "valueComplete": all(counters[k] for k in
                             ("epsTtm", "bookValuePerShare")),
    }
