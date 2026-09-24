"""Per-stock investor-type net trading (외국인/기관/개인), stored raw.

WHAT THIS IS FOR. `alpha-information-inventory-v1` named Korean investor-type
flow as real, official and free — and as the one candidate axis this line has
not yet built a collector for. This module is that collector's raw layer,
mirroring `dart_fundamentals.py`'s discipline: raw in, derived later; a stable
natural key; nothing invented for a field the source did not answer.

THE SOURCE, MEASURED RATHER THAN ASSUMED. The KRX Open API this repository
already holds a subscribed key for (`sto/stk_bydd_trd`, used by
`krx_prices.py`/`krx_universe.py`) does not carry this. A third-party package
that documents the Open API's own catalogue end to end
(`seokhoonj/krx-openapi`, WebFetched 2026-09-24) states plainly, of its own
survey of the service: "API 미제공 데이터: 투자자별 거래실적, 외국인 보유량,
공매도" — per-stock investor-type trading, foreign holdings and short-selling
are each things the Open API does not serve. That is a third party's own
characterization, not KRX's, so it corroborates rather than settles the
question — but it agrees with what this repository's own probe already found
when it tried the Open API's endpoint list (`probe_krx_index_membership.py`
tried six `sto/`/`idx/` paths and none of them is an investor-type breakdown).

So the route is KRX's PUBLIC STATISTICS PORTAL
(`data.krx.co.kr/comm/bldAttendant/getJsonData.cmd`), the same generic
JSON-loader mechanism `pykrx` is built on. `scripts/probe_krx_index_membership.py`
already tried this exact endpoint once, bare, and every date came back
`HTTP 400 LOGOUT` — read there and confirmed again by researching `pykrx`'s
own source (WebFetched 2026-09-24, `pykrx/website/comm/webio.py`): the portal
is a session-backed screen-scrape target. A bare POST with no session state is
read by the server as a logged-out request regardless of its parameters, which
is a fact about the earlier attempt's transport, not about whether the data
exists. `pykrx` reaches it with a `requests.Session()`, a `Referer` header
naming the screen the data is displayed on, and `X-Requested-With:
XMLHttpRequest` — none of which the bare attempt sent. `scripts/
probe_kr_investor_flow.py` is the first attempt that sends them.

THE BLD CODES. `pykrx`'s source names the individual-stock, daily,
investor-type screens as `dbms/MDC/STAT/standard/MDCSTAT02302` (general —
foreign/institution/individual net buy) and `MDCSTAT02303` (detailed —
institution split into its own sub-categories: 금융투자/보험/투신/사모/은행/
기타금융/연기금/기타법인), each read with `strtDd`/`endDd`/`isuCd`/`trdVolVal`/
`askBid` parameters. This module's parser is built against those field
shapes; the probe is what confirms they still answer that way today.

WHY THIS NEEDS NO POINT-IN-TIME DISCIPLINE THE OTHER MODULES DO. Every other
new module here (`dart_ownership_events`, `kr_short_selling`) carries an
`availableFrom` distinct from the event date, because a filing or a report is
submitted after the fact. Investor-type net trading is not: it is KRX's own
END-OF-DAY SETTLEMENT of that day's trades, published the same evening with no
restatement mechanism the source documents. So `availableFrom` here IS the
trading date — stated explicitly, once, rather than left to be assumed the way
a silent field would be.

APPEND-ONLY. A record's id is ticker x date. A record already on disk is never
refetched or overwritten; if KRX is ever found to revise a settled day (not
observed, and not expected of an end-of-day settlement figure), the fix is a
new collector-side reconciliation pass, never an in-place overwrite of a row
that was already published as this ticker's number for that date.
"""
from __future__ import annotations

import re

REGION = "KR"

# The KRX portal's own screen ids for this data, read from `pykrx`'s own
# source (see module docstring) rather than guessed. `_DETAIL` carries the
# institution sub-category breakdown the general screen does not.
BLD_GENERAL = "dbms/MDC/STAT/standard/MDCSTAT02302"
BLD_DETAIL = "dbms/MDC/STAT/standard/MDCSTAT02303"

# The portal's own institution sub-category labels, as `pykrx` and the
# screen's own column headers name them. Kept as a tuple of the exact Korean
# strings rather than translated, so a parser matching against a live response
# is matching the source's own words and not a translation that could drift.
INSTITUTION_SUBCATEGORIES: tuple[str, ...] = (
    "금융투자", "보험", "투신", "사모", "은행", "기타금융", "연기금", "기타법인",
)

# What the general (MDCSTAT02302) screen's row is expected to carry, by the
# portal's own column semantics: net buy value, by investor type, for one
# ticker on one date. Column keys are a hypothesis until the probe confirms
# them against a live response — see `scripts/probe_kr_investor_flow.py`.
GENERAL_FIELDS: dict[str, tuple[str, ...]] = {
    "foreignNet": ("FORN_NETBID_TRDVAL", "FRGN_NETBID_TRDVAL"),
    "institutionNet": ("ORGN_NETBID_TRDVAL",),
    "individualNet": ("PRSN_NETBID_TRDVAL",),
    # Program trading is a separate KRX screen entirely (차익/비차익 PGM), not
    # a column of this one. Left absent rather than guessed at, per this
    # module's own no-fabrication rule.
}

_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")


def parse_amount(text) -> float | None:
    """KRX portal figures, comma-thousands, minus-sign negatives, or None.

    Unlike DART's accounting-parenthesis convention, the KRX portal's own
    screens use a leading minus sign for a net sell. A blank or a dash means
    the cell carried nothing, which is never read as a zero net flow: a
    genuine zero net buy and an unreported cell are different facts, and
    collapsing them would let a missing day look like a flat one.
    """
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    raw = str(text).strip().replace(",", "").replace(" ", "")
    if raw in ("", "-", "—", "–"):
        return None
    if not _NUMBER.match(raw):
        return None
    return float(raw)


def record_id(ticker: str, date: str) -> str:
    """One ticker, one trading date — the natural key this collection uses.

    Same discipline as the ledger and the DART store: the id carries the
    identity, so a re-run recognises what it already holds and never appends
    a second row for a day that already has one.
    """
    return f"kr-investor-flow:{date}:{ticker}"


def build_record(*, ticker: str, date: str, row: dict, detail_row: dict | None,
                 collected_at: str) -> tuple[dict | None, str]:
    """One stored record from one portal response row, or (None, reason).

    ``row`` is the general (MDCSTAT02302) screen's row for this ticker/date;
    ``detail_row`` is the matching MDCSTAT02303 row, when the same date's
    detailed breakdown was also collected. Either may be absent — a date the
    general screen answers but the detailed one does not (or vice versa)
    still yields a usable record, with the missing half's fields left `None`
    rather than fabricated.
    """
    if not row and not detail_row:
        return None, "EMPTY_RESPONSE"

    flows: dict[str, float | None] = {}
    for canonical, aliases in GENERAL_FIELDS.items():
        value = None
        for alias in aliases:
            value = parse_amount((row or {}).get(alias))
            if value is not None:
                break
        flows[canonical] = value
    if all(v is None for v in flows.values()):
        return None, "NO_FLOW_FIELDS"

    institution_breakdown: dict[str, float | None] = {}
    if detail_row:
        for label in INSTITUTION_SUBCATEGORIES:
            institution_breakdown[label] = parse_amount(detail_row.get(label))
        if all(v is None for v in institution_breakdown.values()):
            institution_breakdown = {}

    return {
        "id": record_id(ticker, date),
        "date": date,
        "region": REGION,
        "ticker": ticker,
        # An end-of-day settlement figure, published the same evening with no
        # documented restatement mechanism — so the trading date IS the
        # visibility date, stated explicitly rather than left implicit.
        "availableFrom": date,
        "foreignNetBuy": flows.get("foreignNet"),
        "institutionNetBuy": flows.get("institutionNet"),
        "individualNetBuy": flows.get("individualNet"),
        # Absent entirely, never a dict of zeros, when the detailed screen was
        # not collected for this date or answered nothing readable.
        "institutionBreakdown": institution_breakdown or None,
        "programTrading": None,
        "currency": "KRW",
        "source": "KRX:data-portal:MDCSTAT02302"
                  + ("+MDCSTAT02303" if institution_breakdown else ""),
        "collectedAt": collected_at,
    }, ""


def shard_path(root, year: int):
    from pathlib import Path
    return Path(root) / f"kr-investor-flow-{int(year):04d}.jsonl.gz"


# --------------------------------------------------------------------------- #
# Derivation: backward-looking, PIT-safe cumulative flow and agreement.
# No forward-return use anywhere in this module — it reads only rows already
# on or before the date it is deriving for.
# --------------------------------------------------------------------------- #

def index_by_ticker(rows: list[dict]) -> dict[str, list[dict]]:
    """One ticker's flow rows, oldest first, ready for a rolling derivation."""
    by_ticker: dict[str, list[dict]] = {}
    for row in rows:
        ticker = row.get("ticker")
        if ticker:
            by_ticker.setdefault(ticker, []).append(row)
    for ticker in by_ticker:
        by_ticker[ticker].sort(key=lambda r: str(r.get("date")))
    return by_ticker


def _sum_window(series: list[float | None], end_index: int, window: int) -> float | None:
    """Sum of the last ``window`` values ending at ``end_index``, inclusive.

    None if the window is not fully covered or any value inside it is
    unmeasured — a partial sum silently understates the flow it claims to
    total, which is the same defect a fabricated zero would be.
    """
    start = end_index - window + 1
    if start < 0:
        return None
    segment = series[start:end_index + 1]
    if any(v is None for v in segment):
        return None
    return sum(segment)


def cumulative_flow(rows: list[dict], windows: tuple[int, ...] = (5, 20)) -> list[dict]:
    """5D/20D cumulative net flow per ticker, backward-looking only.

    Each row's derived figure uses only that row's own date and earlier ones
    for that same ticker — nothing here reaches forward, matching the
    signal-persistence invariants' own smoother discipline one level up.
    """
    out: list[dict] = []
    for ticker, series in index_by_ticker(rows).items():
        foreign = [r.get("foreignNetBuy") for r in series]
        institution = [r.get("institutionNetBuy") for r in series]
        for i, row in enumerate(series):
            derived = dict(row)
            cumulative: dict[str, float | None] = {}
            for window in windows:
                cumulative[f"foreignNet{window}d"] = _sum_window(foreign, i, window)
                cumulative[f"institutionNet{window}d"] = _sum_window(institution, i, window)
            derived["cumulativeFlow"] = cumulative
            out.append(derived)
    return out


def flow_acceleration(rows: list[dict], window: int = 20) -> list[dict]:
    """Change in the ``window``-day cumulative flow versus the prior window.

    A name whose foreign buying is accelerating carries a different signal
    than one buying steadily at the same pace, and neither is visible in the
    level alone. Requires two full non-overlapping windows of history; short
    of that the row's acceleration fields are `None`, never zero.
    """
    out: list[dict] = []
    for ticker, series in index_by_ticker(rows).items():
        foreign = [r.get("foreignNetBuy") for r in series]
        institution = [r.get("institutionNetBuy") for r in series]
        for i, row in enumerate(series):
            derived = dict(row)
            current_f = _sum_window(foreign, i, window)
            prior_f = _sum_window(foreign, i - window, window) if i - window >= 0 else None
            current_i = _sum_window(institution, i, window)
            prior_i = _sum_window(institution, i - window, window) if i - window >= 0 else None
            derived["flowAcceleration"] = {
                "foreignNetAccel": (current_f - prior_f)
                                   if current_f is not None and prior_f is not None else None,
                "institutionNetAccel": (current_i - prior_i)
                                       if current_i is not None and prior_i is not None else None,
                "window": window,
            }
            out.append(derived)
    return out


def foreign_institution_agreement(row: dict) -> str | None:
    """Whether foreign and institution net flow point the same way, that day.

    A label, not a score: `SAME_DIRECTION`, `OPPOSITE_DIRECTION`, or `None`
    when either side is unmeasured for the date. Zero on either side is its
    own third state (`FLAT`) rather than being forced into a sign.
    """
    foreign = row.get("foreignNetBuy")
    institution = row.get("institutionNetBuy")
    if foreign is None or institution is None:
        return None
    if foreign == 0 or institution == 0:
        return "FLAT"
    return "SAME_DIRECTION" if (foreign > 0) == (institution > 0) else "OPPOSITE_DIRECTION"
