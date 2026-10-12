"""Point-in-time cash-based profitability for the US research cross-section. CANDIDATE definition, not approved or registered.

Phase 3 of the US alpha research line (`docs/us-alpha-research-phase3-ko.md`) proposes cash-based operating profitability as the
first US hypothesis to test. This module defines the feature and the controls it needs so the readiness audit can measure them
without reading a return, label or model output. Nothing in production, the weekly decision path or any registered study reads it.

WHY A SEPARATE MODULE. `finnhub_derive` defines `PIT_FUNDAMENTALS_V1` (the fields `longterm.score_cross_section` reads),
`accounting_quality` defines `ACCOUNTING_QUALITY_V1`, and `us_shareholder_distribution` the registered capital-allocation v1
features. None of them is edited. This module reuses `finnhub_derive`'s primitives (`index_filings`, `trailing_twelve_months`,
`amount`, `share_count`) so TTM and unit semantics cannot drift from the sealed derivation.

Definitions (contract `US_CASH_PROFITABILITY_CANDIDATE_V1`):

* visibility: a filing is visible on `as_of` only when max(availableFrom, acceptedDate) is STRICTLY earlier (the rule PR #224
  verified on every amendment slot). Amendments are resolved by `finnhub_derive.index_filings` (earliest visible kept).
* current filing: the visible filing with the latest period end; stale when that period ended more than 180 days earlier.
* `cashOperatingProfitability` = operating cash flow TTM / total assets of the current filing (assets > 0).
* `accrualsToAssets` = (net income TTM - operating cash flow TTM) / total assets (assets > 0).
* `operatingProfitabilityToAssets` = operating income TTM / total assets: the ACCRUAL-based profitability on the same
  denominator, so "cash beyond accounting profitability" is tested against a like-for-like control. ROE is not used as the
  control because it is undefined for negative-equity firms, which would drop a systematic set of large repurchasers.
* `marketCapProxy` = share count of the current filing (weighted-average diluted first, `finnhub_derive.share_count`)
  x as-traded close. The count is the current filing's, or else CARRIED FORWARD from the nearest EARLIER visible filing
  that states one (at most 400 days older; never a later filing), and the basis is recorded. Withheld when a split falls
  between the count's filing and `as_of`. The share basis is NOT
  context-verified (period-end counts need SEC XBRL, which is blocked), so this is a PROXY for ranking, never a market value.

Missing is never zero: every absence carries one reason code from `REASONS`.
"""
from __future__ import annotations

import datetime as dt
import math

from . import finnhub_derive as US
from . import finnhub_fundamentals as FF

CONTRACT = "US_CASH_PROFITABILITY_CANDIDATE_V1"
MAX_REPORT_AGE_DAYS = 180

NO_VISIBLE_FILING = "NO_VISIBLE_FILING"
REPORT_STALE = "REPORT_STALE_OVER_180_DAYS"
OCF_TTM_INCOMPLETE = "OCF_TTM_INCOMPLETE_CHAIN"
NI_TTM_INCOMPLETE = "NET_INCOME_TTM_INCOMPLETE_CHAIN"
ASSETS_NOT_STATED = "ASSETS_NOT_STATED"
ASSETS_NON_POSITIVE = "ASSETS_NON_POSITIVE"
OI_TTM_INCOMPLETE = "OPERATING_INCOME_TTM_INCOMPLETE_CHAIN"
SHARES_NOT_STATED = "SHARES_NOT_STATED"
SHARES_AS_FILED = "AS_FILED"
SHARES_CARRIED_FORWARD = "CARRIED_FORWARD"
MAX_SHARE_CARRY_DAYS = 400
NO_PRICE = "NO_PRICE"
SPLIT_BETWEEN = "SPLIT_BETWEEN_FILING_AND_OBSERVATION"
AVAILABLE = "AVAILABLE"
REASONS = (NO_VISIBLE_FILING, REPORT_STALE, OCF_TTM_INCOMPLETE, NI_TTM_INCOMPLETE, OI_TTM_INCOMPLETE, ASSETS_NOT_STATED,
           ASSETS_NON_POSITIVE, SHARES_NOT_STATED, NO_PRICE, SPLIT_BETWEEN, AVAILABLE)


def _day(value) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def visible_day(record: dict) -> dt.date | None:
    """The first day on which a reader could have used this filing: max(availableFrom, acceptedDate)."""
    available, accepted = _day(record.get("availableFrom")), _day(record.get("acceptedDate"))
    if available and accepted:
        return max(available, accepted)
    return available or accepted


def visible_records(records: list[dict], as_of: str) -> list[dict]:
    """Filings strictly visible before `as_of`. A record with no visibility date is never visible."""
    day = _day(as_of)
    return [r for r in records if (v := visible_day(r)) is not None and v < day]


def current_key(by_key: dict) -> tuple | None:
    """The (fiscal year, stage) whose filing ends latest; ties fall to the later stage."""
    best, best_rank = None, None
    for key, record in by_key.items():
        end = _day(record.get("periodEnd"))
        if end is None:
            continue
        rank = (end, key[0], US.STAGE_ORDER[key[1]])
        if best_rank is None or rank > best_rank:
            best, best_rank = key, rank
    return best


def features_as_of(records: list[dict], as_of: str, *, max_age_days: int = MAX_REPORT_AGE_DAYS) -> dict:
    """Candidate cash-profitability features for one ticker on `as_of`, using only filings visible before it."""
    out = {"cashOperatingProfitability": None, "accrualsToAssets": None, "operatingProfitabilityToAssets": None,
           "sharesForProxy": None, "sharesBasis": None, "sharesVisibleDay": None,
           "filingVisibleDay": None, "reportEnd": None, "reportAgeDays": None,
           "state": {"cashOperatingProfitability": NO_VISIBLE_FILING, "accrualsToAssets": NO_VISIBLE_FILING,
                     "operatingProfitabilityToAssets": NO_VISIBLE_FILING, "sharesForProxy": NO_VISIBLE_FILING}}
    by_key = US.index_filings(visible_records(records, as_of))
    key = current_key(by_key)
    if key is None:
        return out
    current = by_key[key]
    end = _day(current.get("periodEnd"))
    age = (_day(as_of) - end).days
    out.update(reportEnd=end.isoformat(), reportAgeDays=age, filingVisibleDay=visible_day(current).isoformat())
    if age > max_age_days:
        out["state"] = {name: REPORT_STALE for name in out["state"]}
        return out
    resolved = FF.resolve_units(current)
    assets = US.amount(current, "bs", US.ASSETS, resolved)
    ocf, _ = US.trailing_twelve_months(by_key, key[0], key[1], "operatingCashFlow")
    net_income, _ = US.trailing_twelve_months(by_key, key[0], key[1], "netIncome")
    operating, _ = US.trailing_twelve_months(by_key, key[0], key[1], "operatingIncome")

    def ratio(numerator, missing_reason):
        if numerator is None:
            return None, missing_reason
        if assets is None:
            return None, ASSETS_NOT_STATED
        if assets <= 0:
            return None, ASSETS_NON_POSITIVE
        return numerator / assets, AVAILABLE

    out["cashOperatingProfitability"], out["state"]["cashOperatingProfitability"] = ratio(ocf, OCF_TTM_INCOMPLETE)
    if ocf is None:
        out["state"]["accrualsToAssets"] = OCF_TTM_INCOMPLETE
    else:
        accrual = None if net_income is None else net_income - ocf
        out["accrualsToAssets"], out["state"]["accrualsToAssets"] = ratio(accrual, NI_TTM_INCOMPLETE)
    out["operatingProfitabilityToAssets"], out["state"]["operatingProfitabilityToAssets"] = ratio(operating, OI_TTM_INCOMPLETE)
    shares, basis, shares_record = carried_share_count(by_key, key)
    if shares is None:
        out["state"]["sharesForProxy"] = SHARES_NOT_STATED
    else:
        out.update(sharesForProxy=shares, sharesBasis=basis, sharesVisibleDay=visible_day(shares_record).isoformat())
        out["state"]["sharesForProxy"] = AVAILABLE
    return out


def carried_share_count(by_key: dict, key: tuple) -> tuple[float | None, str | None, dict | None]:
    """The current filing's share count, else the nearest EARLIER visible filing's within MAX_SHARE_CARRY_DAYS."""
    current = by_key[key]
    end = _day(current.get("periodEnd"))
    earlier = sorted(((_day(r.get("periodEnd")), k) for k, r in by_key.items() if _day(r.get("periodEnd")) is not None
                      and _day(r.get("periodEnd")) <= end), reverse=True)
    for when, k in earlier:
        if (end - when).days > MAX_SHARE_CARRY_DAYS:
            break
        count = US.share_count(by_key[k])
        if count and count > 0:
            return float(count), (SHARES_AS_FILED if k == key else SHARES_CARRIED_FORWARD), by_key[k]
    return None, None, None


def market_cap_proxy(shares, as_traded_price, filing_visible_day, as_of, split_days=()) -> tuple[float | None, str]:
    """Shares x as-traded close, withheld across a split. A ranking proxy, not a market value."""
    if not shares or shares <= 0:
        return None, SHARES_NOT_STATED
    if not (isinstance(as_traded_price, (int, float)) and math.isfinite(as_traded_price) and as_traded_price > 0):
        return None, NO_PRICE
    start, day = _day(filing_visible_day), _day(as_of)
    if any(start < _day(s) <= day for s in split_days):
        return None, SPLIT_BETWEEN
    return float(shares) * float(as_traded_price), AVAILABLE
