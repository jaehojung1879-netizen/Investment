"""Accounting-quality ratios the value/quality sleeves never asked for.

WHY THIS IS A SEPARATE MODULE, NOT A CHANGE TO `dart_derive`/`finnhub_derive`.
Those two modules define `PIT_FUNDAMENTALS_V1` — the exact field set
`longterm.score_cross_section` reads. Adding fields there would be safe for
scoring (nothing reads a key it does not name), but it would also make the
production derivation harder to audit for the one thing it exists to get
right: the ratios that decide today's alpha. This module reuses their
already-measured, already-tested primitives (`trailing_twelve_months`,
`level_amount`/`amount`, `carried_shares`) rather than re-deriving TTM/column
semantics a second time, and produces a SEPARATE, additive field set that no
production path reads. `alpha-information-inventory-v1`'s data map already
found the raw ingredients for every ratio below sitting in the collected
filings and never exposed past a ratio or a per-share numerator — this module
is the exposure, not a new collection.

WHAT IS DELIBERATELY NOT HERE. Receivables growth, inventory growth, and any
working-capital metric need line items (receivables, inventory, current
assets/liabilities, payables) that are not in `dart_fundamentals.WANTED_ACCOUNTS`
or `finnhub_derive.FLOWS`/`EQUITY`/`LIABILITIES`/`ASSETS` — confirmed by
reading those account lists, not assumed. No field for them is invented here;
they stay a documented gap in
`docs/alpha-data-foundation-v2-gaps.md` (`NOT_FEASIBLE_DATA_MISSING`).

WHAT COUNTS AS "GROWTH" HERE. Asset and debt levels are compared at the SAME
report stage a year apart (`year, code` vs `year-1, code`) — never quarter
against annual — for the same reason `earningsGrowth` already does this in
both derive modules: a nine-month figure is not comparable to a twelve-month
one, and neither is a Q3 balance-sheet level to a fiscal-year-end one from a
different point in the year.

NO FORWARD-RETURN RELATIONSHIP IS COMPUTED OR CONSUMED HERE. This module
produces PIT-safe accounting-quality fields from already-visible filings; it
is read by nothing in the alpha-scoring path and is not wired into
`longterm.py`, `build.py`, or any challenger study.
"""
from __future__ import annotations

from . import dart_derive as KR
from . import dart_fundamentals as DF
from . import finnhub_derive as US
from . import finnhub_fundamentals as FF

CONTRACT = "ACCOUNTING_QUALITY_V1"

# Reused verbatim from the two derive modules so a basis label can never
# silently diverge in meaning between regions.
BASIS_ANNUAL = KR.BASIS_ANNUAL
BASIS_ROLLFORWARD = KR.BASIS_ROLLFORWARD
BASIS_INCOMPLETE = KR.BASIS_INCOMPLETE
assert BASIS_ANNUAL == US.BASIS_ANNUAL
assert BASIS_ROLLFORWARD == US.BASIS_ROLLFORWARD
assert BASIS_INCOMPLETE == US.BASIS_INCOMPLETE

FIELD_NAMES = (
    "ocfToNetIncomePct", "fcfToNetIncomePct", "assetGrowthPct",
    "debtGrowthPct", "capexIntensityPct", "shareCountChangePct",
)


def _pct(numerator: float | None, denominator: float | None) -> float | None:
    """A ratio expressed in percent, or `None` where it cannot mean one.

    Mirrors `dart_derive._ratio`/`finnhub_derive._ratio`: the denominator must
    be able to carry a sign-preserving ratio, so a zero or (for a
    positive-only denominator) negative value returns `None` rather than an
    infinity or a sign flip.
    """
    if numerator is None or denominator is None or denominator == 0:
        return None
    return 100.0 * numerator / denominator


def _growth_pct(current: float | None, prior: float | None) -> float | None:
    """Percent change between two same-stage levels a year apart.

    `None` unless the PRIOR level is strictly positive — a growth rate off a
    zero or negative base is not a percentage of anything.
    """
    if current is None or prior is None or prior <= 0:
        return None
    return 100.0 * (current - prior) / prior


def derive_kr_fields(by_key: dict[tuple[int, str], dict], year: int, code: str,
                     shares: float | None = None,
                     prior_shares: float | None = None) -> tuple[dict, dict]:
    """Accounting-quality fields for one DART filing.

    Reuses `dart_derive`'s own TTM rollforward and level readers so a filing
    is described once, not twice — a second implementation is a second place
    for the two to silently disagree on a figure `longterm.py` also depends on.
    """
    current = by_key.get((year, code))
    if current is None:
        return {}, {}

    net_income, ni_basis = KR.trailing_twelve_months(by_key, year, code, "당기순이익")
    revenue, rev_basis = KR.trailing_twelve_months(by_key, year, code, "매출액")
    cash_flow, cf_basis = KR.trailing_twelve_months(by_key, year, code, "영업활동현금흐름")
    capex, capex_basis = KR.trailing_twelve_months(by_key, year, code, "유형자산의취득")

    assets = KR.level_amount(current, "자산총계")
    debt = KR.level_amount(current, "부채총계")
    prior_filing = by_key.get((year - 1, code))
    prior_assets = KR.level_amount(prior_filing, "자산총계") if prior_filing else None
    prior_debt = KR.level_amount(prior_filing, "부채총계") if prior_filing else None

    free_cash_flow = (cash_flow - abs(capex)
                      if cash_flow is not None and capex is not None else None)

    fields = {
        "ocfToNetIncomePct": _pct(cash_flow, net_income),
        "fcfToNetIncomePct": _pct(free_cash_flow, net_income),
        "assetGrowthPct": _growth_pct(assets, prior_assets),
        "debtGrowthPct": _growth_pct(debt, prior_debt),
        "capexIntensityPct": _pct(capex, revenue) if capex is not None else None,
        "shareCountChangePct": _growth_pct(shares, prior_shares),
    }
    basis = {
        "netIncome": ni_basis, "revenue": rev_basis, "cashFlow": cf_basis,
        "capex": capex_basis,
        "assetsAvailable": assets is not None,
        "priorAssetsAvailable": prior_assets is not None,
        "debtAvailable": debt is not None,
        "priorDebtAvailable": prior_debt is not None,
        "freeCashFlowAvailable": free_cash_flow is not None,
        "sharesAvailable": bool(shares and shares > 0),
        "priorSharesAvailable": bool(prior_shares and prior_shares > 0),
    }
    return {k: v for k, v in fields.items() if v is not None}, basis


def derive_us_fields(by_key: dict[tuple[int, str], dict], year: int, stage: str,
                     shares: float | None = None,
                     prior_shares: float | None = None) -> tuple[dict, dict]:
    """Accounting-quality fields for one Finnhub filing. Mirrors `derive_kr_fields`."""
    current = by_key.get((year, stage))
    if current is None:
        return {}, {}
    resolved = FF.resolve_units(current)

    net_income, ni_basis = US.trailing_twelve_months(by_key, year, stage, "netIncome")
    revenue, rev_basis = US.trailing_twelve_months(by_key, year, stage, "revenue")
    cash_flow, cf_basis = US.trailing_twelve_months(by_key, year, stage, "operatingCashFlow")
    capex, capex_basis = US.trailing_twelve_months(by_key, year, stage, "capex")

    assets = US.amount(current, "bs", US.ASSETS, resolved)
    debt, debt_basis = US.total_liabilities(current, resolved)
    prior_filing = by_key.get((year - 1, stage))
    prior_assets = prior_debt = None
    if prior_filing is not None:
        prior_resolved = FF.resolve_units(prior_filing)
        prior_assets = US.amount(prior_filing, "bs", US.ASSETS, prior_resolved)
        prior_debt, _ = US.total_liabilities(prior_filing, prior_resolved)

    free_cash_flow = (cash_flow - abs(capex)
                      if cash_flow is not None and capex is not None else None)

    fields = {
        "ocfToNetIncomePct": _pct(cash_flow, net_income),
        "fcfToNetIncomePct": _pct(free_cash_flow, net_income),
        "assetGrowthPct": _growth_pct(assets, prior_assets),
        "debtGrowthPct": _growth_pct(debt, prior_debt),
        "capexIntensityPct": _pct(capex, revenue) if capex is not None else None,
        "shareCountChangePct": _growth_pct(shares, prior_shares),
    }
    basis = {
        "netIncome": ni_basis, "revenue": rev_basis, "cashFlow": cf_basis,
        "capex": capex_basis,
        "assetsAvailable": assets is not None,
        "priorAssetsAvailable": prior_assets is not None,
        "debtAvailable": debt is not None,
        "priorDebtAvailable": prior_debt is not None,
        "freeCashFlowAvailable": free_cash_flow is not None,
        "sharesAvailable": bool(shares and shares > 0),
        "priorSharesAvailable": bool(prior_shares and prior_shares > 0),
    }
    if debt_basis:
        basis["liabilitiesBasis"] = debt_basis
    return {k: v for k, v in fields.items() if v is not None}, basis


def pit_record(filing: dict, fields: dict, basis: dict, *, region: str,
               report_date: str) -> dict:
    """One `ACCOUNTING_QUALITY_V1` row.

    `availableFrom` is carried through from the filing unchanged, exactly as
    `dart_derive.pit_record`/`finnhub_derive.pit_record` do — this module adds
    fields, it does not re-decide when a filing became visible.
    """
    return {
        "ticker": filing["ticker"],
        "region": region,
        "reportDate": report_date,
        "availableFrom": filing["availableFrom"],
        "fields": fields,
        "derivation": basis,
    }


def build_kr_for_ticker(records: list[dict],
                        shares_by_key: dict[tuple[int, str], float] | None = None
                        ) -> list[dict]:
    """Every derivable accounting-quality row for one KR ticker."""
    by_key = KR.index_filings(records)
    shares_by_key = shares_by_key or {}
    out: list[dict] = []
    prior_shares_by_key: dict[tuple[int, str], float] = {}
    for key in sorted(by_key):
        shares, _ = KR.carried_shares(shares_by_key, key[0], key[1])
        if shares is not None:
            prior_shares_by_key[key] = shares
    for (year, code), filing in sorted(by_key.items()):
        shares, _ = KR.carried_shares(shares_by_key, year, code)
        prior_shares = prior_shares_by_key.get((year - 1, code))
        fields, basis = derive_kr_fields(by_key, year, code, shares, prior_shares)
        if not fields:
            continue
        out.append(pit_record(filing, fields, basis, region="KR",
                              report_date=DF.period_end(year, code)))
    return sorted(out, key=lambda row: str(row["availableFrom"]))


def build_us_for_ticker(records: list[dict]) -> list[dict]:
    """Every derivable accounting-quality row for one US ticker."""
    by_key = US.index_filings(records)
    shares_by_key: dict[tuple[int, str], float] = {}
    for key, filing in by_key.items():
        count = US.share_count(filing)
        if count is not None:
            shares_by_key[key] = count
    prior_shares_by_key: dict[tuple[int, str], float] = {}
    for key in sorted(by_key):
        shares, _ = US.carried_shares(shares_by_key, key[0], key[1])
        if shares is not None:
            prior_shares_by_key[key] = shares
    out: list[dict] = []
    for (year, stage), filing in sorted(by_key.items(),
                                        key=lambda kv: (kv[0][0], US.STAGE_ORDER[kv[0][1]])):
        shares, _ = US.carried_shares(shares_by_key, year, stage)
        prior_shares = prior_shares_by_key.get((year - 1, stage))
        fields, basis = derive_us_fields(by_key, year, stage, shares, prior_shares)
        if not fields:
            continue
        out.append(pit_record(filing, fields, basis, region="US",
                              report_date=filing["periodEnd"]))
    return sorted(out, key=lambda row: str(row["availableFrom"]))


def operating_margin_stability(margin_series: list[tuple[str, float]],
                               window: int = 4) -> dict:
    """Dispersion of a ticker's own OWN prior `operatingMargin` readings.

    `margin_series` is `[(availableFrom, operatingMargin), ...]` already
    computed by `dart_derive`/`finnhub_derive` (production's own ratio, never
    recomputed here) and must already be sorted ascending by `availableFrom`
    by the caller — this function looks backward only, over a ticker's own
    trailing `window` filings, exactly the discipline
    `signal_persistence.PercentileSmoother` already uses: a name with fewer
    than `window` prior readings gets whatever history it has, and a name
    with none gets no reading at all (`None`, never an invented value).
    """
    if not margin_series:
        return {"stabilityPct": None, "observedFilings": 0}
    values = [v for _, v in margin_series[-window:]]
    n = len(values)
    if n < 2:
        return {"stabilityPct": None, "observedFilings": n}
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    return {"stabilityPct": variance ** 0.5, "observedFilings": n}


def coverage(rows: list[dict]) -> dict:
    """Which accounting-quality fields the derivation actually produced.

    Same discipline as `dart_derive.coverage`/`finnhub_derive.coverage`: a
    field's coverage is reported on its own, never averaged into a single
    "fundamentals collected" number.
    """
    counters = {key: 0 for key in FIELD_NAMES}
    for row in rows:
        for key in counters:
            if (row.get("fields") or {}).get(key) is not None:
                counters[key] += 1
    total = len(rows) or 1
    return {
        "rows": len(rows),
        "fieldCoveragePct": {k: round(100.0 * v / total, 2)
                             for k, v in sorted(counters.items())},
    }
