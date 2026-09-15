"""KOSPI bars from KRX, including the names that are no longer there.

WHY THIS EXISTS. Korean membership is now collected (`krx_universe`), and it
says 139 of the 260 names that were ever in the top-120 universe have left it —
38 to 41% of every cross-section from 2013 to 2017. Membership alone does not
put them back. `UniverseHistory.snapshot` keeps only names the price panel can
serve, and `unvouched` is the UNION of "membership unknown" and "was listed and
could not be priced", so a described name with no bars is still a hole:

    KR unvouched today            100%   (all of it membership-unknown)
    with membership, prices as-is  ~25%  (FinanceDataReader serves 34.55% of
                                          delisted Korean names — measured)

The same endpoint that answered the membership question answers this one.
`sto/stk_bydd_trd` carries `TDD_OPNPRC`, `TDD_HGPRC`, `TDD_LWPRC`,
`TDD_CLSPRC` and `ACC_TRDVOL` for every issue that traded that day — delisted
ones included, because it lists what TRADED, not what survives. Coverage is not
34.55% there; it is whatever actually changed hands.

THE BASIS, WHICH IS THE ONLY SUBTLE PART. `price_adjustment.to_total_return`
takes a SPLIT-ADJUSTED, dividend-unadjusted frame — Yahoo unadjusted, or
FinanceDataReader's Korean bars — and multiplies each session by the splits
that come AFTER it, which undoes the vendor's adjustment and recovers the price
that printed. KRX quotes the price that printed already. Handing its bars over
as they come would undo an adjustment nobody made, inflating every pre-split
session by the split ratio.

So this module converts the other way: `to_vendor_basis` divides each session
by the same future-split factor, producing exactly what FinanceDataReader
would have published, and hands that over with a `Stock Splits` column. The
proven adjustment path then runs unchanged, and the round trip is exact — which
is what `test_krx_prices.py` pins, because a silent factor-of-50 in one name's
pre-2018 history would look like a spectacular momentum signal rather than
like a bug.

WHAT KRX DOES NOT CARRY, STATED PLAINLY. Dividends. The index built from these
bars is a PRICE return, not a total return, for every name sourced here. That
understates the departed names' performance by their dividend yield — which is
the conservative direction for a survivorship correction, since it makes the
names that left look slightly worse rather than slightly better, but it is a
real limitation and not a rounding detail.

WHERE THE SPLITS COME FROM. Not from a vendor's event feed; there isn't one on
this endpoint. `LIST_SHRS` is on every row, and a split is the one corporate
action that multiplies the share count while dividing the price by the same
factor — market capitalisation is unchanged across it. A rights issue also
raises `LIST_SHRS`, and does NOT divide the price, so requiring BOTH movements
separates them. `detect_splits` demands the corroboration; a share count that
moves alone is recorded as not a split.
"""
from __future__ import annotations

import datetime as _dt

import numpy as np
import pandas as pd

from .krx_universe import (CODE_KEYS, DATE_KEYS, ROWS_KEYS, SHARES_KEYS,  # noqa: F401
                           _first, parse_number, to_pipeline_ticker)

OPEN_KEYS = ("TDD_OPNPRC", "OPNPRC")
HIGH_KEYS = ("TDD_HGPRC", "HGPRC")
LOW_KEYS = ("TDD_LWPRC", "LWPRC")
CLOSE_KEYS = ("TDD_CLSPRC", "CLSPRC")
VOLUME_KEYS = ("ACC_TRDVOL", "TRDVOL")

REGION = "KR"

# How far the share-count jump and the price drop may disagree and still be one
# split. A 1:10 split prints a share ratio of exactly 10.0 and a price ratio of
# 10.0 times that session's own market move, so the tolerance has to cover an
# ordinary day's return with room to spare — and stay far enough below 1.0 that
# a rights issue, where the price ratio is ~1 against a share ratio of 1.2 or
# more, can never be mistaken for one.
SPLIT_CORROBORATION_TOL = 0.20

# Share counts drift by fractions of a percent through employee grants and
# small conversions. A split is a discrete event and never looks like that, so
# anything under this is not even a candidate.
MIN_SPLIT_MOVE = 0.10


def parse_bars(payload: dict) -> tuple[list[dict], str | None]:
    """(bars, error). One daily response becomes one session's bars.

    Shares the refusal/holiday distinction with `krx_universe.parse_issues`: a
    payload with no rows key was not understood, an empty list is a closed
    exchange, and reading the first as the second would record a refused
    request as a day the market did not open.
    """
    if not isinstance(payload, dict):
        return [], f"payload was {type(payload).__name__}, not an object"
    key = next((k for k in ROWS_KEYS if k in payload), None)
    if key is None:
        return [], f"no rows key in payload keys {sorted(payload)[:8]}"
    rows = payload.get(key)
    if not isinstance(rows, list):
        return [], f"payload key {key!r} was {type(rows).__name__}, not a list"

    bars: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = _first(row, CODE_KEYS)
        if not code or code in seen:
            continue
        close = parse_number(_first(row, CLOSE_KEYS))
        # A row with no close is not a session. Keeping it would put a NaN bar
        # into the panel, and `has_history` counts rows, not finite closes.
        if close is None:
            continue
        seen.add(code)
        bars.append({
            "code": code,
            "open": parse_number(_first(row, OPEN_KEYS)),
            "high": parse_number(_first(row, HIGH_KEYS)),
            "low": parse_number(_first(row, LOW_KEYS)),
            "close": close,
            "volume": parse_number(_first(row, VOLUME_KEYS)),
            "listedShares": parse_number(_first(row, SHARES_KEYS)),
        })
    return bars, None


def bar_rows(date: str, bars: list[dict], keep: set[str] | None = None) -> list[dict]:
    """Bars as store records, one row per issue per session.

    ``keep`` is a set of pipeline tickers, and it is the ONE policy this side
    applies: a storage bound, not a judgement about the data. The endpoint
    answers with the whole exchange — about 930 issues — and a decade of that
    at daily grain is hundreds of megabytes in a branch that has to stay
    clonable. The membership file names the only 260 tickers that can ever
    enter the cross-section, so those are what is kept. Widening it is a flag,
    and the call count does not change either way.
    """
    out = []
    for bar in bars:
        ticker = to_pipeline_ticker(bar["code"])
        if keep is not None and ticker not in keep:
            continue
        out.append({
            "id": f"krx-price:{date}:{bar['code']}",
            "date": date,
            "region": REGION,
            "ticker": ticker,
            "open": bar.get("open"),
            "high": bar.get("high"),
            "low": bar.get("low"),
            "close": bar.get("close"),
            "volume": bar.get("volume"),
            "listedShares": bar.get("listedShares"),
        })
    return out


def shard_year(date: str) -> int:
    return int(str(date)[:4])


def calendar_days(start: str, end: str) -> list[str]:
    """Every calendar day in [start, end].

    Daily, and every day asked including the closed ones — unlike the monthly
    membership walk, which steps forward off a holiday to find the nearest open
    session. There is no nearest session to find here: a day the exchange was
    shut simply has no bars, the response says so, and stepping forward would
    collect the next day twice.
    """
    first = _dt.date.fromisoformat(str(start))
    last = _dt.date.fromisoformat(str(end))
    out: list[str] = []
    cursor = first
    while cursor <= last:
        # Weekends are never trading days on KRX and asking about them would
        # spend 2 calls in 7 on a certain answer.
        if cursor.weekday() < 5:
            out.append(cursor.isoformat())
        cursor += _dt.timedelta(days=1)
    return out


def frame_from_rows(rows: list[dict]) -> pd.DataFrame:
    """One ticker's rows as an as-traded OHLCV frame, oldest session first."""
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame([{
        "Date": pd.Timestamp(row["date"]),
        "Open": row.get("open"), "High": row.get("high"),
        "Low": row.get("low"), "Close": row.get("close"),
        "Volume": row.get("volume"), "ListedShares": row.get("listedShares"),
    } for row in rows]).set_index("Date").sort_index()
    return frame[~frame.index.duplicated(keep="first")]


def detect_splits(frame: pd.DataFrame) -> pd.Series:
    """Split ratio per session: 1.0 where nothing happened.

    A split multiplies `LIST_SHRS` by k and divides the printed price by the
    same k, leaving market capitalisation alone. A rights issue multiplies the
    share count and leaves the price roughly where it was. Only the first is a
    split, and demanding that the two movements CORROBORATE each other is what
    tells them apart — a share count moving on its own is recorded as 1.0.

    The ratio is reported the way `price_adjustment` consumes it: the factor
    the share count was multiplied by, so 50.0 for a one-for-fifty split and
    0.2 for a five-into-one consolidation.
    """
    if frame is None or not len(frame) or "ListedShares" not in frame:
        return pd.Series(1.0, index=getattr(frame, "index", pd.Index([])))
    shares = pd.to_numeric(frame["ListedShares"], errors="coerce")
    close = pd.to_numeric(frame["Close"], errors="coerce")

    share_ratio = shares / shares.shift(1)
    # The price moves the OTHER way, so its ratio is inverted to be compared
    # against the share ratio on the same scale.
    price_ratio = close.shift(1) / close

    ratios = pd.Series(1.0, index=frame.index)
    candidate = (share_ratio.notna() & price_ratio.notna()
                 & (share_ratio > 0) & (price_ratio > 0)
                 & ((share_ratio - 1.0).abs() >= MIN_SPLIT_MOVE))
    corroborated = candidate & (
        (share_ratio / price_ratio - 1.0).abs() <= SPLIT_CORROBORATION_TOL)
    ratios[corroborated] = share_ratio[corroborated]
    return ratios


def to_vendor_basis(frame: pd.DataFrame, ratios: pd.Series | None = None
                    ) -> pd.DataFrame:
    """As-traded KRX bars as the split-adjusted frame the adjuster expects.

    `to_total_return` multiplies each session by the product of the splits that
    come after it, to undo a vendor's back-adjustment. KRX never applied one,
    so this applies it: dividing by the same factor makes these bars identical
    in shape to FinanceDataReader's, and the round trip through
    `to_total_return` returns the printed prices exactly.

    `Dividends` is written as zeros rather than left absent. KRX publishes none
    on this endpoint, and an absent column and a column of zeros mean the same
    thing to the adjuster but not to a reader — the zeros say the question was
    asked.
    """
    from .price_adjustment import DIVIDEND, SPLIT, future_split_factor

    if frame is None or not len(frame) or "Close" not in frame:
        return frame
    if ratios is None:
        ratios = detect_splits(frame)
    after = future_split_factor(ratios)

    out = frame.copy()
    for column in ("Open", "High", "Low", "Close"):
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce").to_numpy(
                dtype=float) / after
    if "Volume" in out.columns:
        # Share counts move inversely to price through a split, so undoing the
        # price scaling scales the volume the other way.
        out["Volume"] = pd.to_numeric(out["Volume"], errors="coerce").to_numpy(
            dtype=float) * after
    out[DIVIDEND] = 0.0
    out[SPLIT] = np.asarray(ratios, dtype=float)
    return out.drop(columns=[c for c in ("ListedShares",) if c in out.columns])


def panel_from_rows(rows: list[dict]) -> dict[str, pd.DataFrame]:
    """Every ticker's bars, on the basis `datafeed` hands to `rebase_frames`."""
    by_ticker: dict[str, list[dict]] = {}
    for row in rows:
        ticker = row.get("ticker")
        if ticker:
            by_ticker.setdefault(ticker, []).append(row)
    out: dict[str, pd.DataFrame] = {}
    for ticker, ticker_rows in by_ticker.items():
        frame = frame_from_rows(ticker_rows)
        if len(frame):
            out[ticker] = to_vendor_basis(frame)
    return out
