"""Point-in-time building blocks for a US multifactor readiness audit. Nothing here reads a future observation or a return label.

Two problems the previous regional model v1 left as `PER_SHARE_NUMERATOR_PRICE_BASIS_UNRESOLVED`:

1. The sealed US `Close` is a forward-accumulated total-return index, not the price that printed (`price_adjustment.to_total_return`
   anchors the index at the first observed session and multiplies in every later dividend and split). A per-share numerator
   (`epsTtm`, `bookValuePerShare`, `fcfPerShare`) is stated in as-traded dollars, so dividing it by the index mixes two bases
   and the mix drifts with the company's whole dividend history. `as_traded_from_total_return` inverts the SAME forward
   recursion, using the sealed dividend and split events, to recover the as-traded close.
2. A numerator stated before a split and a price observed after it are in different share units. `value_yields` therefore
   withholds a yield when a split falls between the filing's availability date and the observation date.

Missing is never zero: a non-positive earnings or book numerator yields no yield (`POSITIVE_ONLY`), exactly as
`pit_data.derive_price_relative` does.
"""
from __future__ import annotations

import numpy as np

NUMERATORS = {"earningsYield": "epsTtm", "bookYield": "bookValuePerShare", "fcfYield": "fcfPerShare"}
POSITIVE_ONLY = ("epsTtm", "bookValuePerShare")
MAX_FILING_AGE_DAYS = 180           # same freshness bound the registered distribution rule uses for a report


def as_traded_from_total_return(dates, tr_close, events):
    """Recover the as-traded close from the forward total-return index.

    `dates` strictly increasing datetime64; `tr_close` the index; `events` an iterable of (date, as_traded_dividend, split_ratio).
    Mirrors `price_adjustment.to_total_return`: a split multiplies the step by its ratio; a dividend multiplies it by
    1 / (1 - dividend / previous as-traded close) and is NOT applied on the first session or when it is not below the previous
    close. Events are placed on the first session at or after their date.
    """
    dates = np.asarray(dates, dtype="datetime64[ns]")
    tr = np.asarray(tr_close, dtype=float)
    if len(dates) != len(tr):
        raise ValueError("LENGTH_MISMATCH")
    steps = {}
    for stamp, dividend, split in sorted(events, key=lambda e: e[0]):
        index = int(np.searchsorted(dates, np.datetime64(stamp, "ns"), side="left"))
        if index >= len(dates):
            continue
        entry = steps.setdefault(index, [0.0, 1.0])
        entry[0] += float(dividend or 0.0)
        if split and split > 0 and split != 1.0:
            entry[1] *= float(split)
    cumulative = np.ones(len(tr))
    cum = 1.0
    last = 0
    for index in sorted(steps):
        cumulative[last:index] = cum
        dividend, split = steps[index]
        step = split
        previous = tr[index - 1] / cum if index > 0 else float("nan")
        if dividend > 0 and np.isfinite(previous) and previous > 0 and dividend < previous:
            step *= 1.0 / (1.0 - dividend / previous)
        cum *= step
        last = index
    cumulative[last:] = cum
    with np.errstate(divide="ignore", invalid="ignore"):
        out = tr / cumulative
    return out


def split_dates(events):
    return sorted(np.datetime64(stamp, "D") for stamp, _, split in events if split and split > 0 and split != 1.0)


def value_yields(fields: dict, price, available_from, as_of, splits=(), *, max_age_days: int = MAX_FILING_AGE_DAYS) -> dict:
    """{'earningsYield': x|None, ...} plus 'state'. `price` is the AS-TRADED close on `as_of`."""
    out = {name: None for name in NUMERATORS}
    state = {}
    avail = np.datetime64(str(available_from)[:10], "D")
    day = np.datetime64(str(as_of)[:10], "D")
    age = int((day - avail).astype(int))
    if age < 0:
        raise ValueError("FILING_NOT_VISIBLE_ON_THE_OBSERVATION_DATE")
    if not (isinstance(price, (int, float)) and np.isfinite(price) and price > 0):
        return {**out, "state": {n: "NO_PRICE" for n in NUMERATORS}}
    stale = age > max_age_days
    crossed = any(avail < s <= day for s in splits)
    for name, numerator in NUMERATORS.items():
        value = fields.get(numerator)
        if value is None or not isinstance(value, (int, float)) or not np.isfinite(value):
            state[name] = "NUMERATOR_ABSENT"
        elif stale:
            state[name] = "FILING_STALE"
        elif crossed:
            state[name] = "SPLIT_BETWEEN_FILING_AND_OBSERVATION"
        elif numerator in POSITIVE_ONLY and value <= 0:
            state[name] = "NON_POSITIVE_NUMERATOR"
        else:
            out[name] = float(value) / float(price)
            state[name] = "AVAILABLE"
    return {**out, "state": state}
