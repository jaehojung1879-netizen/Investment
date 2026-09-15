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

WHERE THE SPLITS COME FROM, AND WHAT THE FIRST VERSION GOT WRONG. There is no
event feed on this endpoint. `LIST_SHRS` is on every row, and a split is the
one corporate action that multiplies the share count while dividing the price
by the same factor — market capitalisation is unchanged across it.

The first version asked only that the two movements corroborate, within 20%.
Run #3 collected 3,364 sessions and the audit showed what that admits: 302
"splits", most of them like `017800.KS 2013-01-10, x1.12113` — a 12.1% share
issuance on a day the price rose 2.2%. A RELATIVE tolerance of 20% around a
share ratio of 1.12 covers "the price did not move at all", so every issuance
under a fifth was being booked as a split and every session before it divided
by 1.12.

What the first version missed is that a split RATIO IS NOT ARBITRARY. Korean
액면분할 and 액면병합 change the par value between standard denominations —
5,000 to 500 is ten-for-one, 5,000 to 100 is fifty — so the ratio is an integer
or one over an integer. 1.12113 is not a split ratio and never could be.
`detect_splits` now requires the share ratio to sit on one of those, and the
price ratio to sit on the SAME one. That took 302 detections to 87.

WHAT NO SHARE COUNT CAN DESCRIBE. A capital reduction (감자), a re-listing, and
a re-referenced price out of a long suspension all move the printed price
without a matching share movement — `001260.KS` on 2013-02-15 printed a price
ratio of 34 against a share ratio of 0.37. There is no feed here that explains
them, so they are REFUSED rather than adjusted: `unexplained_moves` names the
sessions, `panel_from_rows` drops those tickers, and the audit counts them. A
fabricated +3,300% return in a momentum signal is far worse than a named gap.

Three things it must NOT refuse, because all three are real returns:

  * a move across a trading HALT. KRX carries the last close forward for a
    suspended issue, at `ACC_TRDVOL` zero, so those rows are not sessions and
    `frame_from_rows` drops them — after which the surrounding sessions can be
    months apart and a large move between them is a genuine cumulative one.
  * 정리매매, the liquidation trading that runs for about a fortnight before a
    delisting, where the daily price limit is lifted entirely. 한진해운 printed
    -68% there. That is not an artifact; it is the survivorship signal itself.
  * anything within the daily limit, which is what the limit is for.
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

# The ratios a par-value change can actually produce. Korean 액면분할 and
# 액면병합 move the par value between standard denominations, so the share count
# is multiplied by an integer or divided by one. Requiring the ratio to LAND ON
# one of these is what separates a split from an issuance: the first version
# asked only that the share and price movements agree within a fifth, which
# admitted every share issuance under 20% on a day the price barely moved.
CLEAN_SPLIT_RATIOS = tuple(sorted(
    {float(n) for n in (2, 3, 4, 5, 6, 8, 10, 20, 25, 40, 50, 100)}
    | {1.0 / n for n in (2, 3, 4, 5, 6, 8, 10, 20, 25, 40, 50, 100)}))

# How far from a clean ratio a movement may sit. Applied in log space. The
# nearest clean ratios are a factor apart, so this can be tight without being
# brittle — and note what it implies: the smallest clean ratio is 2, so at this
# tolerance a candidate session has to move at least 42.5%, which no ordinary
# session can. Every candidate is already a corporate action; the share count
# only says WHICH one.
SPLIT_RATIO_TOL = 0.15

# How long `LIST_SHRS` may lag the price. This was the second thing run #3
# disproved. `064960.KS` went ex-split on 2025-01-24 — the close halved from
# 51,000 to 25,500 — and the share count did not move until 2025-02-26,
# THIRTY-THREE DAYS LATER, because the field is a registry figure that updates
# when the new shares are formally listed rather than when the price goes ex.
# Same-session corroboration cannot see that at all, which is why the first
# version refused 150 tickers it should have adjusted.
#
# The confirming move need not equal the split ratio either: 064960 printed
# 1.815, not 2.0, because an issuance settled in the same window. So the test is
# whether the share count moved TOWARDS the ratio the price implies — closer to
# it than to no change at all — rather than onto it exactly.
SHARE_REGISTRY_LAG_DAYS = 75

# KRX's daily price limit. This is a DETECTOR for corporate actions the share
# counts did not describe, not a compliance check: the moves it is looking for
# are 900%, 1,900%, 3,300%. The limit was ±15% before 2015-06-15 and ±30% after,
# and the looser figure is used throughout on purpose — tightening it for the
# early years would flag 관리종목 and 정리매매 sessions, which are real.
DAILY_LIMIT_PCT = 30.0

# A move between sessions further apart than this spans a suspension or a long
# holiday, so it is a cumulative return rather than one day's, and the daily
# limit does not describe it. Four days covers a weekend plus a holiday.
HALT_GAP_DAYS = 4

# 정리매매 — the liquidation trading that runs for roughly a fortnight before a
# delisting, with the daily price limit lifted entirely. A large move inside
# this window at the END of a ticker's series is the survivorship signal, not
# an adjustment failure.
LIQUIDATION_SESSIONS = 15


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


def frame_from_rows(rows: list[dict], traded_only: bool = True) -> pd.DataFrame:
    """One ticker's rows as an as-traded OHLCV frame, oldest session first.

    A suspended issue is not absent from the response: KRX carries its last
    close forward at `ACC_TRDVOL` zero, so `071970.KS` printed 2,765 on four
    consecutive days it did not trade and then 55,300 on four more. Keeping
    those rows puts flat bars into the panel and dumps the whole suspension
    into one printed return, which is what made run #3's audit report +1,900%.

    So a zero-volume row is not a session — the same rule `parse_bars` applies
    to a row with no close, which the first version applied to the price and
    not to the volume. The rows stay in the store either way: a suspension is
    itself a fact about the name, and dropping it at DERIVATION time keeps that
    record while leaving the panel to real sessions.
    """
    if traded_only:
        rows = [row for row in rows if (row.get("volume") or 0) > 0]
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame([{
        "Date": pd.Timestamp(row["date"]),
        "Open": row.get("open"), "High": row.get("high"),
        "Low": row.get("low"), "Close": row.get("close"),
        "Volume": row.get("volume"), "ListedShares": row.get("listedShares"),
    } for row in rows]).set_index("Date").sort_index()
    return frame[~frame.index.duplicated(keep="first")]


def nearest_clean_ratio(value: float) -> float | None:
    """The par-value ratio ``value`` is closest to, or None if it is not near one.

    Compared in log space so that 0.1 and 10 are the same distance from 1, which
    is what a ratio deserves: a fifty-for-one split and a one-for-fifty
    consolidation are the same event pointing opposite ways.
    """
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(value) or value <= 0:
        return None
    best = min(CLEAN_SPLIT_RATIOS, key=lambda k: abs(np.log(value / k)))
    return best if abs(np.log(value / best)) <= np.log(1 + SPLIT_RATIO_TOL) else None


def detect_splits(frame: pd.DataFrame) -> pd.Series:
    """Split ratio per session: 1.0 where nothing happened.

    PRICE-LED, share-confirmed. A split divides the printed price by a clean
    par-value ratio, so the candidates are the sessions whose price ratio lands
    on one — and since the smallest clean ratio is 2, a candidate is a move of
    at least 42.5%, which the daily limit forbids. The market cannot manufacture
    one; only a corporate action can.

    Which action is what `LIST_SHRS` decides. A split multiplies the share count
    by the same factor; a spin-off (인적분할) halves the price and leaves the
    count alone; a capital reduction moves the count with no matching price
    ratio. So a candidate is confirmed only if the share count moved TOWARDS the
    implied ratio — within `SHARE_REGISTRY_LAG_DAYS`, because the field lags the
    ex-date by weeks, and towards rather than onto, because an issuance can
    settle in the same window.

    Nothing is booked inside the liquidation window at the end of a series:
    정리매매 runs with no price limit, so a candidate there is more likely to be
    the delisting collapse than a split, and that collapse is the signal this
    whole exercise is for.

    The ratio is reported the way `price_adjustment` consumes it: the factor the
    share count was multiplied by, so 50.0 for a one-for-fifty split and 0.2 for
    a five-into-one consolidation.
    """
    if frame is None or not len(frame) or "ListedShares" not in frame:
        return pd.Series(1.0, index=getattr(frame, "index", pd.Index([])))
    shares = pd.to_numeric(frame["ListedShares"], errors="coerce").to_numpy(float)
    close = pd.to_numeric(frame["Close"], errors="coerce").to_numpy(float)
    index = frame.index
    total = len(frame)

    registry_moves = [
        (position, shares[position] / shares[position - 1])
        for position in range(1, total)
        if np.isfinite(shares[position]) and np.isfinite(shares[position - 1])
        and shares[position - 1] > 0 and shares[position] != shares[position - 1]
    ]

    ratios = np.ones(total)
    for position in range(1, total):
        if total - 1 - position < LIQUIDATION_SESSIONS:
            break
        if not (np.isfinite(close[position]) and np.isfinite(close[position - 1])
                and close[position] > 0):
            continue
        candidate = nearest_clean_ratio(close[position - 1] / close[position])
        if candidate is None:
            continue
        if _registry_confirms(registry_moves, index, position, candidate):
            ratios[position] = candidate
    return pd.Series(ratios, index=index)


def _registry_confirms(moves, index, position: int, candidate: float) -> bool:
    """Did the share count move towards ``candidate`` near this session?"""
    for where, ratio in moves:
        if abs((index[where] - index[position]).days) > SHARE_REGISTRY_LAG_DAYS:
            continue
        if ratio > 0 and abs(np.log(ratio / candidate)) < abs(np.log(ratio)):
            return True
    return False


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


def unexplained_moves(vendor_frame: pd.DataFrame) -> list[dict]:
    """Sessions the adjustment cannot account for, with why each one qualifies.

    Run the frame through the same path the replay does and look at what is
    left. A session is unexplained only when all three of these hold:

      * the move exceeds the daily price limit, so the market cannot have
        produced it in one session;
      * the previous session is within `HALT_GAP_DAYS`, so it is not a
        cumulative return across a suspension;
      * it is more than `LIQUIDATION_SESSIONS` from the end of the series, so
        it is not 정리매매, where the limit is lifted on purpose.

    What survives all three is a capital reduction, a re-listing or a
    re-referenced price — corporate actions `LIST_SHRS` does not describe and
    this endpoint carries no feed for. They are reported, never adjusted away.
    """
    from .price_adjustment import to_total_return

    if vendor_frame is None or len(vendor_frame) < 2:
        return []
    rebased, _ = to_total_return(vendor_frame)
    if rebased is None or len(rebased) < 2:
        return []
    closes = pd.to_numeric(rebased["Close"], errors="coerce")
    returns = closes.pct_change()
    gaps = rebased.index.to_series().diff().dt.days
    total = len(rebased)

    out: list[dict] = []
    for position in range(1, total):
        move = returns.iloc[position]
        if not np.isfinite(move) or abs(move) * 100.0 <= DAILY_LIMIT_PCT:
            continue
        gap = gaps.iloc[position]
        if np.isfinite(gap) and gap > HALT_GAP_DAYS:
            continue
        if total - 1 - position < LIQUIDATION_SESSIONS:
            continue
        out.append({"date": str(rebased.index[position])[:10],
                    "movePct": round(float(move) * 100.0, 2),
                    "gapDays": int(gap) if np.isfinite(gap) else None})
    return out


def panel_from_rows(rows: list[dict], refuse_unexplained: bool = True
                    ) -> tuple[dict[str, pd.DataFrame], dict[str, list[dict]]]:
    """(panel, refused). Every usable ticker's bars, and why the rest are not.

    On the basis `datafeed` hands to `rebase_frames`. A ticker carrying a move
    the adjustment cannot account for is left OUT rather than passed on: it
    stays unvouched, which is the state it was already in, and the alternative
    is a fabricated return inside a momentum signal.
    """
    by_ticker: dict[str, list[dict]] = {}
    for row in rows:
        ticker = row.get("ticker")
        if ticker:
            by_ticker.setdefault(ticker, []).append(row)

    out: dict[str, pd.DataFrame] = {}
    refused: dict[str, list[dict]] = {}
    for ticker, ticker_rows in sorted(by_ticker.items()):
        frame = frame_from_rows(ticker_rows)
        if not len(frame):
            continue
        vendor = to_vendor_basis(frame)
        suspect = unexplained_moves(vendor) if refuse_unexplained else []
        if suspect:
            refused[ticker] = suspect
        else:
            out[ticker] = vendor
    return out, refused


def load_panel(store, tickers=None) -> tuple[dict[str, pd.DataFrame], dict[str, list[dict]]]:
    """(panel, refused) read from collected shards, filtered to ``tickers``.

    Filtered while READING, not after: the store is 1.7 million rows and the
    replay usually wants the handful its primary vendor could not serve, so
    building 624 frames to keep twenty is 90 seconds spent for nothing.
    """
    from pathlib import Path as _Path

    from . import historical_store as HS

    store = _Path(store)
    wanted = set(tickers) if tickers is not None else None
    rows: list[dict] = []
    for shard in sorted(store.glob("krx-prices-*.jsonl.gz")):
        for row in HS.read_jsonl(shard):
            if wanted is None or row.get("ticker") in wanted:
                rows.append(row)
    if not rows:
        return {}, {}
    return panel_from_rows(rows)
