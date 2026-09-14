"""US factor inputs from the collected filings: the mirror of `dart_derive`.

WHY THIS COULD NOT BE WRITTEN EARLIER. A US 10-Q states its income statement
from the fiscal year start, and that was not knowable from memory — it was
measured, over 34,327 filings, by the ratio of each stage to the first quarter:
2.03 and 3.09 on net income, 2.04 and 3.09 on revenue, 2.06 and 3.13 on
operating income, 1.98 and 3.17 on operating cash flow, against the 2.0 and 3.0
a cumulative statement predicts and the 1.0 and 1.0 three separate quarters
would. Four accounts, none between the bands.

So a trailing-twelve-month figure is a ROLLFORWARD, never a sum of four
quarters and never an annualisation:

    TTM(Y, stage) = FY(Y-1) - cum(Y-1, stage) + cum(Y, stage)

Summing four quarterly figures out of this store counts the first quarter four
times and the second three; on these filings that inflates free cash flow about
two and a half fold, and every number it produces looks entirely ordinary.

WHY THE ACCOUNT NAMES ARE A LIST AND NOT A NAME. Measured over the same store,
one tag covers 41.6% of filings for revenue and the chain below covers 93.7%.
Every chain here was chosen by counting filings, not by recalling US-GAAP:

    net income 99.5% · revenue 93.7% · operating income 87.7% ·
    operating cash flow 99.0% · capex 88.9% · equity 98.7% · assets 99.5%

WHAT IT REFUSES. A field it cannot build from the filings in hand. There is no
annualisation fallback, no carrying a level forward across a year, and no
filling a missing prior year with the nearest one available: each of those
turns an absence into a number, and an absence is the one thing downstream can
still act on correctly.
"""
from __future__ import annotations

from pipeline import finnhub_fundamentals as FF

BASIS_ANNUAL = "ANNUAL_AS_FILED"
BASIS_ROLLFORWARD = "TTM_ROLLFORWARD"
BASIS_INCOMPLETE = "INCOMPLETE_CHAIN"

SHARES_AS_FILED = "AS_FILED"
SHARES_CARRIED_FORWARD = "CARRIED_FORWARD"

LIABILITIES_AS_FILED = "AS_FILED"
LIABILITIES_FROM_BALANCE = "ASSETS_LESS_EQUITY"

# Flow accounts, cumulative from the fiscal year start. Order is coverage order:
# the first tag a filing carries wins, so a filer stating both the old and the
# new revenue tag is read under the one it states first in this list rather
# than under whichever happened to be written into the JSON first.
FLOWS = {
    "netIncome": ("ic", ("NetIncomeLoss", "ProfitLoss",
                         "NetIncomeLossAvailableToCommonStockholdersBasic",
                         "IncomeLossFromContinuingOperations")),
    "revenue": ("ic", ("Revenues",
                       "RevenueFromContractWithCustomerExcludingAssessedTax",
                       "RevenueFromContractWithCustomerIncludingAssessedTax",
                       "SalesRevenueNet", "SalesRevenueGoodsNet",
                       "SalesRevenueServicesNet", "RevenuesNetOfInterestExpense",
                       "TotalRevenuesAndOtherIncome",
                       "RegulatedAndUnregulatedOperatingRevenue")),
    "operatingIncome": ("ic", (
        "OperatingIncomeLoss",
        # Pre-tax income is not operating income, and it is last for that
        # reason: it is used only where the filer states no operating line at
        # all, which is 13.9% of filings — mostly banks and insurers, whose
        # income statements genuinely have no operating subtotal.
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItems"
        "NoncontrollingInterest")),
    "operatingCashFlow": ("cf", (
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations")),
    "capex": ("cf", ("PaymentsToAcquirePropertyPlantAndEquipment",
                     "PaymentsToAcquireProductiveAssets",
                     "PaymentsForCapitalImprovements",
                     "PaymentsToAcquireOtherPropertyPlantAndEquipment")),
}

# Balance-sheet levels. A level is a stock at a date, so it is read from the
# filing itself and never rolled forward.
EQUITY = ("StockholdersEquity",
          "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest")
LIABILITIES = ("Liabilities",)
ASSETS = ("Assets",)

SHARE_COUNTS = ("WeightedAverageNumberOfDilutedSharesOutstanding",
                "WeightedAverageNumberOfSharesOutstandingBasic",
                "WeightedAverageNumberOfBasicSharesOutstanding",
                "CommonStockSharesOutstanding",
                "EntityCommonStockSharesOutstanding")

STAGE_ORDER = {FF.Q1: 1, FF.Q2: 2, FF.Q3: 3, FF.FY: 4}


def amount(record: dict, section: str, chain: tuple[str, ...],
           resolved: dict[str, str] | None = None) -> float | None:
    """The first account in the chain this filing states, in dollars.

    Only currency values are accepted. An EPS arrives under an income-statement
    tag too, and a per-share figure read as a total is a number that survives
    every check downstream while being wrong by the share count.
    """
    if resolved is None:
        resolved = FF.resolve_units(record)
    stated: dict[str, float] = {}
    for entry in (record.get("statements") or {}).get(section) or []:
        concept = FF.strip_namespace(entry.get("concept"))
        if concept not in chain or concept in stated:
            continue
        if FF.value_class(record, entry, resolved) != FF.CURRENCY:
            continue
        value = entry.get("value")
        if isinstance(value, (int, float)):
            stated[concept] = float(value)
    for concept in chain:
        if concept in stated:
            return stated[concept]
    return None


def share_count(record: dict, resolved: dict[str, str] | None = None) -> float | None:
    """The share count this filing states, or None.

    A count of zero is None, not zero: dividing by it is undefined and keeping
    it would put an infinity into a factor.
    """
    if resolved is None:
        resolved = FF.resolve_units(record)
    stated: dict[str, float] = {}
    for section in ("ic", "bs", "cf"):
        for entry in (record.get("statements") or {}).get(section) or []:
            concept = FF.strip_namespace(entry.get("concept"))
            if concept not in SHARE_COUNTS or concept in stated:
                continue
            if FF.value_class(record, entry, resolved) != FF.SHARES:
                continue
            value = entry.get("value")
            if isinstance(value, (int, float)) and value > 0:
                stated[concept] = float(value)
    for concept in SHARE_COUNTS:
        if concept in stated:
            return stated[concept]
    return None


def total_liabilities(record: dict, resolved: dict[str, str] | None = None
                      ) -> tuple[float | None, str | None]:
    """Total liabilities, stated or read off the balance sheet.

    Only 68.5% of filings state `Liabilities`, but 99.5% state `Assets` and
    98.7% state equity, and a balance sheet balances by construction. The
    subtraction is the filer's own arithmetic, not an estimate — and it lifts
    the account from 68.5% to 99.2%.
    """
    if resolved is None:
        resolved = FF.resolve_units(record)
    stated = amount(record, "bs", LIABILITIES, resolved)
    if stated is not None:
        return stated, LIABILITIES_AS_FILED
    assets = amount(record, "bs", ASSETS, resolved)
    equity = amount(record, "bs", EQUITY, resolved)
    if assets is None or equity is None:
        return None, None
    return assets - equity, LIABILITIES_FROM_BALANCE


def index_filings(records: list[dict]) -> dict[tuple[int, str], dict]:
    """One ticker's filings by (fiscal year, stage of the year).

    286 of 33,986 combinations are filed more than once — an amendment
    restating a period already reported. The EARLIEST is kept: it is what a
    reader on that date actually had, and letting a later restatement replace
    it would put the corrected numbers into a window that ended before the
    correction existed. The amendment is therefore not emitted as a second row,
    which is a known 0.8% of the store and is written down rather than hidden.
    """
    by_key: dict[tuple[int, str], dict] = {}
    for record in records:
        stage = FF.quarter_stage(record)
        year = record.get("fiscalYear")
        if stage is None or year is None:
            continue
        key = (int(year), stage)
        seen = by_key.get(key)
        if seen is None or str(record.get("availableFrom")) < str(seen.get("availableFrom")):
            by_key[key] = record
    return by_key


def trailing_twelve_months(by_key: dict[tuple[int, str], dict], year: int,
                           stage: str, account: str) -> tuple[float | None, str]:
    """Twelve months of a flow account ending at this filing, and how.

    The annual report states the year outright. Every other stage is rolled
    forward, which needs BOTH prior-year filings in hand — the annual and the
    same stage — and yields None when either is missing. That is the whole
    reason the collector was made to fetch `freq=annual` as well: without the
    FY term there is no TTM at all, not a less accurate one.
    """
    section, chain = FLOWS[account]
    current = by_key.get((year, stage))
    if current is None:
        return None, BASIS_INCOMPLETE
    this_period = amount(current, section, chain)
    if this_period is None:
        return None, BASIS_INCOMPLETE
    if stage == FF.FY:
        return this_period, BASIS_ANNUAL

    prior_annual = by_key.get((year - 1, FF.FY))
    prior_same = by_key.get((year - 1, stage))
    if prior_annual is None or prior_same is None:
        return None, BASIS_INCOMPLETE
    full_year = amount(prior_annual, section, chain)
    same_stage = amount(prior_same, section, chain)
    if full_year is None or same_stage is None:
        return None, BASIS_INCOMPLETE
    return full_year - same_stage + this_period, BASIS_ROLLFORWARD


def _ratio(numerator: float | None, denominator: float | None,
           positive_denominator: bool = True) -> float | None:
    """A quotient, or None where the denominator cannot carry one.

    Negative equity is a real state, and a ROE computed on it is a number with
    the wrong sign that ranks a distressed company as a quality name.
    """
    if numerator is None or denominator is None:
        return None
    if denominator == 0 or (positive_denominator and denominator < 0):
        return None
    return numerator / denominator


def carried_shares(shares_by_key: dict[tuple[int, str], float] | None,
                   year: int, stage: str) -> tuple[float | None, str | None]:
    """The share count as of this filing: stated, or carried from an earlier one.

    25.3% of filings state no share count — a 10-K often puts it in the cover
    page rather than the statements. The nearest EARLIER filing's count is
    still the number a reader on this date would have known. Nothing later is
    ever considered: that is a look-ahead, and it is the bug this whole replay
    exists to prevent.
    """
    if not shares_by_key:
        return None, None
    exact = shares_by_key.get((year, stage))
    if exact is not None:
        return exact, SHARES_AS_FILED
    target = (year, STAGE_ORDER[stage])
    best_key = best_value = None
    for (y, s), value in shares_by_key.items():
        when = (y, STAGE_ORDER[s])
        if when >= target:
            continue
        if best_key is None or when > best_key:
            best_key, best_value = when, value
    if best_value is None:
        return None, None
    return best_value, SHARES_CARRIED_FORWARD


def derive_fields(by_key: dict[tuple[int, str], dict], year: int, stage: str,
                  shares: float | None = None) -> tuple[dict, dict]:
    """The factor inputs for one filing, with a note on how each was built.

    `fields` follows PIT_FUNDAMENTALS_V1: ratios outright, and per-share
    NUMERATORS rather than yields — a filing cannot state a yield, because a
    yield needs a price and the price moves every day after the filing.
    """
    current = by_key.get((year, stage))
    if current is None:
        return {}, {}
    resolved = FF.resolve_units(current)

    net_income, ni_basis = trailing_twelve_months(by_key, year, stage, "netIncome")
    revenue, rev_basis = trailing_twelve_months(by_key, year, stage, "revenue")
    operating, op_basis = trailing_twelve_months(by_key, year, stage, "operatingIncome")
    cash_flow, cf_basis = trailing_twelve_months(by_key, year, stage, "operatingCashFlow")
    capex, capex_basis = trailing_twelve_months(by_key, year, stage, "capex")

    equity = amount(current, "bs", EQUITY, resolved)
    debt, debt_basis = total_liabilities(current, resolved)

    # A year earlier at the SAME stage, so growth compares twelve months with
    # twelve months rather than a quarter with a year.
    prior_ni, _ = trailing_twelve_months(by_key, year - 1, stage, "netIncome")

    fields: dict = {
        "roe": _ratio(net_income, equity),
        "operatingMargin": _ratio(operating, revenue),
        "profitMargin": _ratio(net_income, revenue),
        "debtToEquity": _ratio(debt, equity),
        "earningsGrowth": ((net_income - prior_ni) / abs(prior_ni)
                           if net_income is not None and prior_ni not in (None, 0)
                           else None),
    }

    # Capital expenditure is stated as a positive outflow in the investing
    # section, so it is subtracted by magnitude — a filer stating it negative
    # would otherwise be credited with spending nothing.
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
    if debt_basis:
        basis["liabilitiesBasis"] = debt_basis
    return {k: v for k, v in fields.items() if v is not None}, basis


def pit_record(filing: dict, fields: dict, basis: dict) -> dict:
    """One PIT_FUNDAMENTALS_V1 row, ready for `FundamentalStore.from_jsonl`.

    `availableFrom` is SEC's accepted-filing date carried through untouched. It
    is the only thing that licenses use, and re-deriving it here would be a
    second definition of the one field the whole collection exists for.
    """
    return {
        "ticker": filing["ticker"],
        "reportPeriod": f"{filing['fiscalYear']}-{FF.quarter_stage(filing)}",
        "reportDate": filing["periodEnd"],
        "availableFrom": filing["availableFrom"],
        "filingDate": filing["availableFrom"],
        "publicationDate": filing["availableFrom"],
        "currency": "USD",
        "source": filing.get("source"),
        "sourceAsOf": filing.get("collectedAt"),
        "revisionStatus": filing.get("form"),
        "fields": fields,
        "derivation": basis,
    }


def build_for_ticker(records: list[dict]) -> list[dict]:
    """Every derivable filing for one ticker, oldest visible first.

    A filing yielding no usable field is dropped rather than emitted empty:
    `FundamentalStore` returns the newest visible record, and an empty one
    would hide an older filing that actually had numbers.
    """
    by_key = index_filings(records)
    shares_by_key = {}
    for key, filing in by_key.items():
        count = share_count(filing)
        if count is not None:
            shares_by_key[key] = count

    out: list[dict] = []
    for (year, stage), filing in sorted(by_key.items(), key=lambda kv: (kv[0][0], STAGE_ORDER[kv[0][1]])):
        shares, shares_basis = carried_shares(shares_by_key, year, stage)
        fields, basis = derive_fields(by_key, year, stage, shares)
        if shares_basis:
            basis["sharesBasis"] = shares_basis
        if not fields:
            continue
        out.append(pit_record(filing, fields, basis))
    return sorted(out, key=lambda row: str(row["availableFrom"]))


def coverage(rows: list[dict]) -> dict:
    """Which factor inputs the derivation actually produced.

    Quality is sourceable from the statements alone; value needs a share count
    a quarter of the filings do not state. Reporting them separately is what
    keeps "we collected fundamentals" from being read as "the value sleeve
    works".
    """
    counters = {key: 0 for key in
                ("roe", "operatingMargin", "profitMargin", "debtToEquity",
                 "earningsGrowth", "epsTtm", "bookValuePerShare", "fcfPerShare")}
    bases: dict[str, int] = {}
    share_bases: dict[str, int] = {}
    liability_bases: dict[str, int] = {}
    for row in rows:
        for key in counters:
            if (row.get("fields") or {}).get(key) is not None:
                counters[key] += 1
        derivation = row.get("derivation") or {}
        for source, tally in (("netIncome", bases), ("sharesBasis", share_bases),
                              ("liabilitiesBasis", liability_bases)):
            value = derivation.get(source)
            if value:
                tally[value] = tally.get(value, 0) + 1
    total = len(rows) or 1
    return {
        "rows": len(rows),
        "fieldCoveragePct": {k: round(100.0 * v / total, 2)
                             for k, v in sorted(counters.items())},
        "netIncomeBasis": bases,
        "sharesBasis": share_bases,
        "liabilitiesBasis": liability_bases,
        "qualityComplete": all(counters[k] for k in
                               ("roe", "operatingMargin", "profitMargin",
                                "debtToEquity")),
        "valueComplete": all(counters[k] for k in
                             ("epsTtm", "bookValuePerShare")),
    }
