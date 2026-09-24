"""Per-stock short-sale volume/value and net short position, stored raw.

THE SOURCE, RESEARCHED RATHER THAN GUESSED (WebSearch, 2026-09-24 — KRX's own
`data.krx.co.kr` domain is blocked from this sandbox's WebFetch, so this is
built from search-result descriptions of KRX's own published screens, and
every figure below is a research finding to be CONFIRMED, not an assumption).
KRX's statistics portal publishes short-selling through (at least) three
screens, all under `data.krx.co.kr/comm/srt/srtLoader/index.cmd`, a sibling
loader to the `comm/bldAttendant/getJsonData.cmd` mechanism
`kr_investor_flow.py` uses rather than the same one:

  * `MDCSTAT301` — 개별종목 공매도 거래현황 (daily short-sale TRADING volume and
    value per stock). KRX's own screen documentation, per the search result
    that surfaced it, states regular-market same-day figures are available
    after 15:40 KST and the full day's after 18:10 KST — an intraday
    publication lag, not a multi-day one.
  * `MDCSTAT305` — 개별종목 공매도 순보유잔고 (net short POSITION holdings by
    stock), built from investor-side regulatory reports rather than exchange
    trade prints: a holder must report within T+2 of a net short position
    reaching 0.01% of listed shares (or KRW 1bn notional), so this series
    carries its own, LONGER publication lag than the trading-volume screen —
    "confirmable up to two days before today", per the search result that
    described it. The two screens are DIFFERENT QUANTITIES on DIFFERENT
    lags and are never blended into one field.
  * `MDCSTAT300` — described as a combined "종합정보" (comprehensive info)
    screen; not yet resolved to a distinct bld code of its own and not relied
    on separately by this module.

WHAT IS AND IS NOT CONFIRMED. The screen ids (301/305) and their described
publication-lag behaviour are corroborated by a search-engine description of
KRX's own page, which is not the same as having read KRX's page directly or
called the underlying JSON endpoint. The exact `bld=` code each screen's AJAX
call uses (by the convention `krx_investor_flow`'s confirmed codes follow,
likely something in the `dbms/MDC/STAT/srt/...` family) is NOT confirmed —
`scripts/probe_kr_short_selling.py` is what resolves it against a live
response, and this module's field aliases are written broadly enough to be
checked against whatever the probe actually receives.

THE THREE REGIMES, NEVER READ AS ONE CONTINUOUS SERIES. `AGENTS.md`'s own
research task for this module is explicit that Korean short-selling spans
full-market bans (~2020-03 to ~2021-05, and 2023-11-05 to 2025-03-31, the
second paired with a structural reporting overhaul) during which the
variable is either illegal to observe or measured under a materially
different microstructure. `regime_label` is not a derived convenience field —
it is a REQUIRED classification every stored row carries, because a factor
built on this series that pools across a ban silently mixes "no shorting
happened" with "shorting happened and was measured", which are opposite
facts about market structure wearing the same zero.

APPEND-ONLY, KEYED BY (TICKER, DATE, METRIC). A short-sale trading row and a
net-position row for the same ticker and date are two different records with
two different natural keys, because they come from two different screens on
two different lags and neither should ever silently overwrite the other.
"""
from __future__ import annotations

import datetime as _dt
import re

REGION = "KR"

BLD_TRADING = None   # MDCSTAT301's own bld code — unresolved, see module docstring
BLD_NET_POSITION = None  # MDCSTAT305's own bld code — unresolved, see module docstring
SCREEN_TRADING = "MDCSTAT301"
SCREEN_NET_POSITION = "MDCSTAT305"

# Regime labels. A row's regime is decided from its own date against these
# windows, never inferred from whether a value happened to be present — a
# banned period with no reportable position is still BANNED, not NORMAL with
# a hole in it.
REGIME_NORMAL = "NORMAL"
REGIME_BANNED_COVID = "BANNED_COVID"
REGIME_BANNED_STRUCTURAL = "BANNED_STRUCTURAL"

# (start, end) inclusive, per AGENTS.md's own dates for this study.
_BAN_WINDOWS: tuple[tuple[str, str, str], ...] = (
    ("2020-03-16", "2021-05-02", REGIME_BANNED_COVID),
    ("2023-11-05", "2025-03-31", REGIME_BANNED_STRUCTURAL),
)

_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")


def parse_amount(text) -> float | None:
    """Same grammar as `kr_investor_flow.parse_amount` — comma thousands,
    minus-sign negatives, blank/dash means unstated rather than zero."""
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


def regime_label(date: str) -> str:
    """Which short-selling regime a date falls in — always one of three.

    A full-market ban is a fact about the market, published here whether or
    not this module ever collects a row for the date: `regime_for_dates`
    below can enumerate the banned calendar without any network access at
    all, which is what makes it usable for auditing an already-collected
    store for a silently-invented zero.
    """
    for start, end, label in _BAN_WINDOWS:
        if start <= str(date) <= end:
            return label
    return REGIME_NORMAL


def is_banned(date: str) -> bool:
    return regime_label(date) != REGIME_NORMAL


def trading_record_id(ticker: str, date: str) -> str:
    return f"kr-short-trading:{date}:{ticker}"


def net_position_record_id(ticker: str, date: str) -> str:
    return f"kr-short-netpos:{date}:{ticker}"


# Column aliases for the daily short-sale trading screen (MDCSTAT301). A
# hypothesis, not a confirmed field list — see module docstring. Kept as
# alias tuples in the same style `krx_universe.CODE_KEYS` etc. use, so a
# parser reading a live response one probe run away from now needs only new
# alias entries here, never a rewritten record shape.
TRADING_FIELDS: dict[str, tuple[str, ...]] = {
    "shortVolume": ("CVSRTSELL_TRDVOL", "SRTSELL_TRDVOL"),
    "shortValue": ("CVSRTSELL_TRDVAL", "SRTSELL_TRDVAL"),
    "totalVolume": ("ACC_TRDVOL",),
    "totalValue": ("ACC_TRDVAL",),
}


def build_trading_record(*, ticker: str, date: str, row: dict,
                         collected_at: str) -> tuple[dict | None, str]:
    """One daily short-sale trading row, from MDCSTAT301's own columns.

    The short-sale RATIO (short volume / total volume) is computed here only
    when both sides are present and the total is positive — never against a
    zero or missing total, which would either divide by zero or silently
    read "no trading that day" as "no short-selling that day", two different
    facts about the same missing denominator.
    """
    if not row:
        return None, "EMPTY_RESPONSE"

    values: dict[str, float | None] = {}
    for canonical, aliases in TRADING_FIELDS.items():
        value = None
        for alias in aliases:
            value = parse_amount(row.get(alias))
            if value is not None:
                break
        values[canonical] = value
    if all(v is None for v in values.values()):
        return None, "NO_TRADING_FIELDS"

    short_volume, total_volume = values.get("shortVolume"), values.get("totalVolume")
    ratio = (short_volume / total_volume
             if short_volume is not None and total_volume not in (None, 0) else None)

    return {
        "id": trading_record_id(ticker, date),
        "date": date, "region": REGION, "ticker": ticker,
        "availableFrom": date,   # published same evening; see module docstring
        "regimeLabel": regime_label(date),
        "shortSaleVolume": values.get("shortVolume"),
        "shortSaleValue": values.get("shortValue"),
        "totalVolume": values.get("totalVolume"),
        "totalValue": values.get("totalValue"),
        "shortSaleRatio": ratio,
        "currency": "KRW",
        "source": f"KRX:data-portal:{SCREEN_TRADING}",
        "collectedAt": collected_at,
    }, ""


NET_POSITION_FIELDS: dict[str, tuple[str, ...]] = {
    "netShortPositionPct": ("RATIO", "NET_SRT_RATIO"),
    "netShortShares": ("BAL_QTY", "NET_SRT_QTY"),
    "netShortValue": ("BAL_AMT", "NET_SRT_AMT"),
    "reportDate": ("RPT_DD",),
}

# The reporting lag the net-position screen itself documents (T+2 for the
# report to be due, per module docstring), used only to state the lag on the
# record — never to backdate `availableFrom`, which is read from the row's
# own reported date when the source states one.
NET_POSITION_REPORT_LAG_DAYS = 2


def build_net_position_record(*, ticker: str, date: str, row: dict,
                              collected_at: str) -> tuple[dict | None, str]:
    """One net short position row, from MDCSTAT305's own columns.

    `availableFrom` here is NOT the position date: a net short position
    disclosed as of date D is reportable up to two days later, so this
    module reads whichever visibility date the portal's own response states
    (`RPT_DD` or equivalent) and falls back to D + the documented lag only
    when the source states no visibility date of its own — the fallback is
    marked so a reader can tell an as-stated date from an assumed one.
    """
    if not row:
        return None, "EMPTY_RESPONSE"

    values: dict[str, float | None] = {}
    for canonical, aliases in NET_POSITION_FIELDS.items():
        if canonical == "reportDate":
            continue
        value = None
        for alias in aliases:
            value = parse_amount(row.get(alias))
            if value is not None:
                break
        values[canonical] = value
    if all(v is None for v in values.values()):
        return None, "NO_NET_POSITION_FIELDS"

    report_date = None
    for alias in NET_POSITION_FIELDS["reportDate"]:
        raw = row.get(alias)
        if raw:
            report_date = str(raw)
            break
    available_from_basis = "AS_STATED"
    if report_date is None:
        report_date = (_dt.date.fromisoformat(date)
                       + _dt.timedelta(days=NET_POSITION_REPORT_LAG_DAYS)).isoformat()
        available_from_basis = "ASSUMED_FROM_DOCUMENTED_LAG"

    return {
        "id": net_position_record_id(ticker, date),
        "date": date, "region": REGION, "ticker": ticker,
        "availableFrom": report_date,
        "availableFromBasis": available_from_basis,
        "regimeLabel": regime_label(date),
        "netShortPositionPct": values.get("netShortPositionPct"),
        "netShortShares": values.get("netShortShares"),
        "netShortValue": values.get("netShortValue"),
        "currency": "KRW",
        "source": f"KRX:data-portal:{SCREEN_NET_POSITION}",
        "collectedAt": collected_at,
    }, ""


def shard_path(root, year: int, kind: str = "trading"):
    from pathlib import Path
    prefix = "kr-short-trading" if kind == "trading" else "kr-short-netpos"
    return Path(root) / f"{prefix}-{int(year):04d}.jsonl.gz"


def banned_dates(start: str, end: str) -> list[tuple[str, str, str]]:
    """The banned windows overlapping [start, end], for audit use.

    Pure calendar arithmetic, no network — lets a caller check an
    already-collected store for a row silently sitting inside a ban window
    without re-deriving the dates from scratch each time.
    """
    out = []
    for ban_start, ban_end, label in _BAN_WINDOWS:
        if ban_end < start or ban_start > end:
            continue
        out.append((max(ban_start, start), min(ban_end, end), label))
    return out
