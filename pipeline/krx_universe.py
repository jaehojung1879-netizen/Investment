"""Turning KRX daily per-issue trading rows into a dated Korean universe.

WHY THIS EXISTS. `dataIntegrity` reports KR `membershipCoveragePct` 0.0 and
`survivorshipRisk` HIGH, because `build_universe_history.py` deliberately
writes no Korean rows. That refusal was right for the sources it had: the two
things tried before — every name in `KRX-DELISTING`, and today's names with no
lower bound — both read as KNOWN membership while describing a Korean
cross-section the file had invented.

WHAT CHANGED. Probes run #4 measured the KRX Open API's
`sto/stk_bydd_trd` (유가증권 일별매매정보) under a subscribed key and it
answered POINT_IN_TIME:

    2013-01-02 vs 2026-09-01   77.42% overlap, 210 issues departed, 223 joined
    2013-01-02  930 issues     2016-01-04  887     2020-01-02  916
    columns carry ISU_CD, ISU_NM, MKTCAP, LIST_SHRS

Below 100% overlap with departed names present is the exact pair
`membership_evidence` requires, and the run reached the oldest date asked for
(2013-01-02) rather than stopping short. So the dated cross-section exists, it
is per-issue, and it carries market capitalisation.

WHAT THIS MODULE DOES AND DOES NOT DECIDE. It is the pure half: parsing,
ranking, date arithmetic, membership. No network, no files. The collector
brings the bytes; `build_universe_history.py` brings the current universe.

The one thing worth stating plainly is WHERE THE POLICY LIVES. The collector
writes what KRX said — code, name, market cap, listed shares, and the rank
market cap puts each issue at that day. It applies no universe rule at all,
because a rule baked into a collected artifact cannot be changed without
re-collecting it. `members_on_date` holds the rule, so it is inspectable and
testable, and a different rule is a re-derivation rather than a re-fetch.

THE RULE, AND WHY IT HAS TWO HALVES.

    members(D) = (the `size` largest issues by market cap on D)
                 UNION
                 (today's configured KR names that actually traded on D)

The first half is not an approximation of the universe — it IS the universe's
own rule. `pipeline/universe._kr_kospi` sorts the KOSPI listing by market cap
and takes `head(universe_size)`; `members_on_date` does the same thing to the
same exchange on an older date. That is the half which ADDS BACK the names
that were large in 2013 and have since shrunk out, and that set is the
survivorship gap itself: 210 issues traded on 2013-01-02 and are gone today.

The second half exists because the first, alone, would quietly DELETE names.
`UniverseHistory.snapshot` drops any name whose row says it was delisted, so
a configured name that is not in today's top-`size` — a preferred share, say,
which trades at a fraction of its common's cap — would be given a `delisted`
date and vanish from the live cross-section. Shrinking the universe the system
actually trades is not a survivorship fix; it is a second bias pointed the
other way. A configured name is therefore a member on every date it traded,
and the ranking decides only who ELSE is.

Both halves are bounded by what traded: a name absent from D's response is not
a member on D, whichever half would otherwise have claimed it.
"""
from __future__ import annotations

import datetime as _dt

# Columns that carry the issue code, the name, and the two figures that make a
# dated market-cap universe possible. KRX has shipped more than one spelling
# for some of these, so each is a list and the first present one is taken.
# Checked by presence, never assumed: an issue with no readable market cap is
# reported as unranked rather than silently ranked last, because "we could not
# read it" and "it is the smallest company on the exchange" are not the same
# statement about a company.
CODE_KEYS = ("ISU_SRT_CD", "ISU_CD", "ISU_SRT_CD7")
NAME_KEYS = ("ISU_ABBRV", "ISU_NM", "ISU_KOR_NM")
MKTCAP_KEYS = ("MKTCAP", "MKT_CAP", "MKTCAP_AMT")
SHARES_KEYS = ("LIST_SHRS", "LIST_SHRS_CNT")
DATE_KEYS = ("BAS_DD", "TRD_DD")

# The rows key KRX answers with. A payload holding none of these was not
# understood, which is a different fact from a market where nothing traded.
ROWS_KEYS = ("OutBlock_1", "output", "OutBlock1")

# Every code this endpoint serves is a KOSPI issue, and the pipeline's KR
# tickers carry the suffix the price vendor answers to. `sto/stk_bydd_trd` is
# the 유가증권 (KOSPI) endpoint; KOSDAQ has its own path and is not collected,
# because the replay's Korean universe is entirely `.KS`.
MARKET_SUFFIX = ".KS"

REGION = "KR"


def to_pipeline_ticker(code: str) -> str:
    """`005930` -> `005930.KS`, the form `universe-history.json` is keyed by."""
    code = (code or "").strip()
    return code + MARKET_SUFFIX if code else ""


def _first(row: dict, keys) -> str | None:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return None


def parse_number(raw) -> float | None:
    """KRX's numeric strings, or None when the field says nothing.

    Figures arrive as `"1,234,567"` and a missing one as `"-"` or `""`. None
    is returned rather than 0.0: a zero market cap would rank an unreadable
    issue below every real company instead of leaving it out of the ranking.
    """
    if raw is None:
        return None
    text = str(raw).strip().replace(",", "").replace(" ", "")
    if not text or text in ("-", "--"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_issues(payload: dict) -> tuple[list[dict], str | None]:
    """(issues, error). One response becomes issues, or the reason it holds none.

    A payload with no rows key at all is a DIFFERENT fact from one holding an
    empty list: the first says the request was not understood, the second that
    nothing traded that date — a market holiday. Reading the first as zero
    issues would record a broken request as a closed exchange, and the
    collector would step past it looking for the next open day forever.
    """
    if not isinstance(payload, dict):
        return [], f"payload was {type(payload).__name__}, not an object"
    key = next((k for k in ROWS_KEYS if k in payload), None)
    if key is None:
        return [], f"no rows key in payload keys {sorted(payload)[:8]}"
    rows = payload.get(key)
    if not isinstance(rows, list):
        return [], f"payload key {key!r} was {type(rows).__name__}, not a list"

    issues: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = _first(row, CODE_KEYS)
        # First row for a code wins. Duplicates would otherwise be ranked twice
        # and push a real company out of the top `size`.
        if not code or code in seen:
            continue
        seen.add(code)
        issues.append({
            "code": code,
            "name": _first(row, NAME_KEYS) or "",
            "marketCap": parse_number(_first(row, MKTCAP_KEYS)),
            "listedShares": parse_number(_first(row, SHARES_KEYS)),
        })
    return issues, None


def served_date(payload: dict, requested: str) -> str:
    """The date KRX says it answered for, falling back to the one asked.

    A request for a market holiday may be answered with the nearest open
    session rather than with nothing, and recording it under the date we asked
    for would put two snapshots at one date and none at the other. The rows
    carry `BAS_DD`; that is what the snapshot is dated by.
    """
    key = next((k for k in ROWS_KEYS if k in (payload or {})), None)
    rows = (payload or {}).get(key) if key else None
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict):
                stamp = _first(row, DATE_KEYS)
                if stamp and len(stamp) == 8 and stamp.isdigit():
                    return f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:]}"
    return requested


def rank_issues(issues: list[dict], top: int | None = None) -> list[dict]:
    """Issues ordered largest market cap first, each stamped with its rank.

    Issues with no readable market cap are dropped, not ranked last — see
    `parse_number`. Ties break on code so the same response always produces the
    same ranking, which is what makes the written shard byte-deterministic.
    """
    ranked = sorted(
        (dict(issue) for issue in issues if issue.get("marketCap") is not None),
        key=lambda issue: (-float(issue["marketCap"]), issue["code"]),
    )
    for position, issue in enumerate(ranked, start=1):
        issue["rank"] = position
    if top is not None and top > 0:
        return ranked[:top]
    return ranked


def snapshot_rows(date: str, issues: list[dict]) -> list[dict]:
    """Ranked issues as store records, one row per issue per date.

    One row per issue rather than one row per date holding a list, because
    `historical_store`'s sort key is (date, region, ticker, id) — at that grain
    the shard sorts and deduplicates itself, and a re-collected date merges
    with what is there instead of appending a second copy of the same day.
    """
    rows = []
    for issue in issues:
        code = issue["code"]
        rows.append({
            "id": f"krx-universe:{date}:{code}",
            "date": date,
            "region": REGION,
            "ticker": to_pipeline_ticker(code),
            "code": code,
            "name": issue.get("name") or "",
            "marketCap": issue.get("marketCap"),
            "listedShares": issue.get("listedShares"),
            "rank": issue.get("rank"),
        })
    return rows


def shard_year(date: str) -> int:
    return int(str(date)[:4])


def month_starts(start: str, end: str) -> list[str]:
    """The first calendar day of every month in [start, end].

    Monthly, not daily. `memberships_from_snapshots` reads a name's first
    absence as its removal date, so the snapshot spacing IS the error bound on
    the delisted side — a month here, against the seven months the US
    constituent history reaches between commits. Holding a departed name up to
    a month too long keeps it in the cross-section slightly past its exit,
    which is the same direction the US side already errs in and is recorded
    rather than smoothed over.

    Denser spacing is a larger `--frequency`, not a different mechanism.
    """
    first = _dt.date.fromisoformat(str(start)).replace(day=1)
    last = _dt.date.fromisoformat(str(end))
    out: list[str] = []
    cursor = first
    while cursor <= last:
        out.append(cursor.isoformat())
        cursor = (cursor.replace(day=28) + _dt.timedelta(days=7)).replace(day=1)
    return out


def week_starts(start: str, end: str) -> list[str]:
    """Every Monday in [start, end], for a run that wants the replay's own grid."""
    begin = _dt.date.fromisoformat(str(start))
    begin -= _dt.timedelta(days=begin.weekday())
    last = _dt.date.fromisoformat(str(end))
    out: list[str] = []
    cursor = begin
    while cursor <= last:
        if cursor >= _dt.date.fromisoformat(str(start)):
            out.append(cursor.isoformat())
        cursor += _dt.timedelta(days=7)
    return out


FREQUENCIES = {"monthly": month_starts, "weekly": week_starts}


def target_dates(start: str, end: str, frequency: str = "monthly") -> list[str]:
    try:
        builder = FREQUENCIES[frequency]
    except KeyError:
        raise ValueError(
            f"unknown frequency {frequency!r}; known: {sorted(FREQUENCIES)}") from None
    return builder(start, end)


def members_on_date(rows: list[dict], size: int,
                    current_universe: list[str] | None = None) -> set[str]:
    """Which tickers were in the investable universe on one date.

    The rule and its two halves are set out in this module's docstring: the
    `size` largest by market cap, plus any configured name that traded. A
    ticker absent from `rows` is absent from the result either way — the
    configured half can only readmit a name KRX says was trading.
    """
    configured = set(current_universe or ())
    traded = {row.get("ticker") for row in rows if row.get("ticker")}
    ranked = sorted(
        (row for row in rows if row.get("rank") is not None),
        key=lambda row: int(row["rank"]),
    )
    largest = {row["ticker"] for row in ranked[:max(int(size), 0)]
               if row.get("ticker")}
    return largest | (configured & traded)


def snapshots_from_rows(rows: list[dict], size: int,
                        current_universe: list[str] | None = None
                        ) -> list[tuple[str, set[str]]]:
    """(date, members) per collected date, oldest first.

    The shape `memberships_from_snapshots` already consumes for the US side.
    Dates are derived from the rows themselves, so a collection that skipped a
    month produces no snapshot for it rather than an empty one — an empty
    snapshot would delist the entire exchange for that date.
    """
    by_date: dict[str, list[dict]] = {}
    for row in rows:
        date = str(row.get("date") or "")
        if date:
            by_date.setdefault(date, []).append(row)
    return [(date, members_on_date(by_date[date], size, current_universe))
            for date in sorted(by_date)]
