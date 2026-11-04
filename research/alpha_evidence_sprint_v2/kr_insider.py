"""kr-insider-open-market-purchase-v1 — deterministic construction (no outcome is read here).

Information: DART 임원ㆍ주요주주특정증권등소유상황보고서 (Capital Markets Act s.173 report by
an executive or a major shareholder of a change in their holding). The original filing's
세부변동내역 table carries, per transaction, machine attributes that this module reads
instead of free text:

    <TU AUNIT="RPT_RSN" AUNITVALUE="..">장내매수(+)</TU>     reason (label kept verbatim)
    <TU AUNIT="MDF_DM"  AUNITVALUE="YYYYMMDD">..</TU>        transaction date
    <TU AUNIT="STR_KND" AUNITVALUE="1">보통주</TU>           security kind
    <TE ACODE="MDF_STK_CNT">-3,584</TE>                        signed share change
    <TE ACODE="ACI_AMT2">23,558</TE>                           acquisition/disposal price (KRW)

Only rows whose reason label is exactly 장내매수(+) or 장내매도(-) and whose security kind
label is exactly 보통주 count as open-market trades; every other row (grants, inheritance,
gifts, option exercise, new appointment, rights issues, off-market) is recorded and NEVER
counted. A reason CODE is stored next to its label but no code is ever translated on its own
(AGENTS.md v2.25: a raw enum is not translated on a guess).

Point in time: a filing becomes usable at the close of the first KRX session STRICTLY AFTER
its DART receipt date (a filing received after the close cannot be traded that day).
"""
from __future__ import annotations

import bisect
import re
from dataclasses import dataclass

BUY_LABEL = "장내매수(+)"
SELL_LABEL = "장내매도(-)"
COMMON_LABEL = "보통주"
INSIDER_REPORT = "임원ㆍ주요주주특정증권등소유상황보고서"
TRAILING_SESSIONS = 63
STATES = ("NET_BUYER", "NET_SELLER", "NO_OPEN_MARKET_TRADE")

_ROW = re.compile(r"<TR\b[^>]*>(.*?)</TR>", re.S)
_TU = re.compile(r'<TU\b[^>]*AUNIT="([A-Z_]+)"[^>]*AUNITVALUE="([^"]*)"[^>]*>(.*?)</TU>', re.S)
_TE = re.compile(r'<TE\b[^>]*ACODE="([A-Z_0-9]+)"[^>]*>(.*?)</TE>', re.S)
_GROUP = re.compile(r'<TABLE-GROUP\b[^>]*ACLASS="RPT_RSN"[^>]*>(.*?)</TABLE-GROUP>', re.S)


class ParseError(ValueError):
    pass


def decode(raw: bytes) -> str:
    """DART originals declare utf-8 but are often EUC-KR/cp949 (measured 2026-11-03)."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp949")


def _clean(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).replace("&cr;", "").strip()


def _int(text: str):
    t = _clean(text).replace(",", "").replace(" ", "")
    if t in ("", "-"):
        return None
    if not re.fullmatch(r"[+-]?\d+", t):
        raise ParseError(f"NOT_AN_INTEGER:{t[:20]}")
    return int(t)


def _price(text: str):
    """Price cells are free-form ('23,558', '139600(원)', '109374.16()'); the state never uses
    them. A leading number is read as KRW (decimals kept); anything else is None.

    Revision v2 (2026-11-03, outcome-blind): v1 parsed prices with the strict share-count rule
    and rejected 2 of 42 sampled originals on these two formats; share counts stay strict.
    """
    t = _clean(text).replace(",", "").replace(" ", "")
    m = re.match(r"^(\d+(?:\.\d+)?)", t)
    return float(m.group(1)) if m else None


def parse_transactions(document: str) -> list[dict]:
    """All detail rows of the 세부변동내역 table group, in document order.

    Raises ``ParseError`` if the table group is absent or a detail row is incomplete; a
    filing that cannot be read is never treated as a filing with no trades.
    """
    groups = _GROUP.findall(document)
    if not groups:
        raise ParseError("NO_DETAIL_TABLE")
    out = []
    for group in groups:
        for body in _ROW.findall(group):
            units = {unit: (code, _clean(label)) for unit, code, label in _TU.findall(body)}
            if "RPT_RSN" not in units:
                continue          # header or 합계 row
            values = {code: text for code, text in _TE.findall(body)}
            if "MDF_STK_CNT" not in values or "MDF_DM" not in units:
                raise ParseError("INCOMPLETE_DETAIL_ROW")
            change = _int(values["MDF_STK_CNT"])
            day = units["MDF_DM"][0]
            if not re.fullmatch(r"\d{8}", day or ""):
                raise ParseError("BAD_TRANSACTION_DATE")
            out.append({
                "reasonLabel": units["RPT_RSN"][1], "reasonCode": units["RPT_RSN"][0],
                "date": f"{day[:4]}-{day[4:6]}-{day[6:]}",
                "securityLabel": units.get("STR_KND", (None, None))[1],
                "securityCode": units.get("STR_KND", (None, None))[0],
                "shareChange": change,
                "price": _price(values["ACI_AMT2"]) if "ACI_AMT2" in values else None,
            })
    return out


def open_market_net(rows: list[dict]) -> dict:
    """Net open-market common-share trading in one filing (shares and KRW)."""
    buy_sh = sell_sh = 0
    buy_krw = sell_krw = 0.0
    priced = True
    for r in rows:
        if r["securityLabel"] != COMMON_LABEL or r["shareChange"] is None:
            continue
        if r["reasonLabel"] == BUY_LABEL and r["shareChange"] > 0:
            buy_sh += r["shareChange"]
            if r["price"] is None:
                priced = False
            else:
                buy_krw += r["shareChange"] * r["price"]
        elif r["reasonLabel"] == SELL_LABEL and r["shareChange"] < 0:
            sell_sh += -r["shareChange"]
            if r["price"] is None:
                priced = False
            else:
                sell_krw += -r["shareChange"] * r["price"]
    return {"buyShares": buy_sh, "sellShares": sell_sh, "netShares": buy_sh - sell_sh,
            "netKrw": (buy_krw - sell_krw) if priced else None, "allPriced": priced,
            "otherRows": sum(1 for r in rows if r["reasonLabel"] not in (BUY_LABEL, SELL_LABEL))}


def available_session(receipt_date: str, sessions: list[str]) -> str | None:
    """First KRX session strictly after the DART receipt date (``sessions`` sorted ISO dates)."""
    i = bisect.bisect_right(sessions, receipt_date)
    return sessions[i] if i < len(sessions) else None


@dataclass(frozen=True)
class Event:
    ticker: str
    receipt_no: str
    receipt_date: str
    available: str            # first session strictly after receipt
    net_shares: int
    net_krw: float | None


@dataclass(frozen=True)
class Quarantine:
    """A filing that never contributes to any state (owner rule, 2026-11-04, outcome-blind).

    A detail row dated AFTER the filing's own DART receipt date describes a transaction the
    filer could not yet have made when the report was received; the filing is internally
    inconsistent (observed: one sampled original carried a row 212 days after its receipt).
    Neither the row nor the rest of the filing is trusted, guessed or repaired.
    """
    ticker: str
    receipt_no: str
    receipt_date: str
    reason: str
    rows_after_receipt: int
    max_days_after_receipt: int


QUARANTINE_ROW_DATED_AFTER_RECEIPT = "DETAIL_ROW_DATED_AFTER_RECEIPT"


def _days(a: str, b: str) -> int:
    from datetime import date
    return (date.fromisoformat(a) - date.fromisoformat(b)).days


def build_event(ticker: str, receipt_no: str, receipt_date: str, rows: list[dict],
                sessions: list[str]) -> "Event | Quarantine | None":
    """The only constructor of a state-bearing ``Event`` from a parsed original filing.

    ``receipt_date`` is ISO (YYYY-MM-DD). Returns ``Quarantine`` when ANY detail row is dated
    later than the receipt date, ``None`` when no session follows the receipt yet (not usable),
    else an ``Event`` with the filing's open-market net. A quarantined filing contributes
    nothing to ``state_at``, whichever way its open-market rows point.
    """
    late = [_days(r["date"], receipt_date) for r in rows if r["date"] > receipt_date]
    if late:
        return Quarantine(ticker, receipt_no, receipt_date, QUARANTINE_ROW_DATED_AFTER_RECEIPT,
                          len(late), max(late))
    available = available_session(receipt_date, sessions)
    if available is None:
        return None
    net = open_market_net(rows)
    return Event(ticker, receipt_no, receipt_date, available, net["netShares"], net["netKrw"])


def split_events(built: list) -> tuple[list["Event"], dict]:
    """Keep Events, count Quarantines by reason (never silently dropped)."""
    events, quarantined = [], {}
    for item in built:
        if isinstance(item, Quarantine):
            quarantined[item.reason] = quarantined.get(item.reason, 0) + 1
        elif isinstance(item, Event):
            events.append(item)
    return events, {"quarantined": sum(quarantined.values()), "byReason": quarantined}


def state_at(events: list[Event], ticker: str, anchor: str, sessions: list[str],
             trailing=TRAILING_SESSIONS) -> str:
    """Issuer state on an anchor: net open-market insider shares over events AVAILABLE in the
    ``trailing`` sessions ending ON the anchor. Uses shares (price-free) so the state never
    reads a price; an amended filing is excluded upstream (originals only)."""
    if any(not isinstance(e, Event) for e in events):
        raise TypeError("STATE_TAKES_EVENTS_ONLY")   # a Quarantine can never reach a state
    i = bisect.bisect_right(sessions, anchor) - 1
    if i < 0:
        raise ValueError("ANCHOR_BEFORE_CALENDAR")
    start = sessions[max(0, i - trailing + 1)]
    net = sum(e.net_shares for e in events if e.ticker == ticker and start <= e.available <= anchor)
    if net > 0:
        return "NET_BUYER"
    if net < 0:
        return "NET_SELLER"
    return "NO_OPEN_MARKET_TRADE"


def anchor_spread(returns: dict, states: dict, eligible: set) -> dict:
    """Equal-weight NET_BUYER basket minus equal-weight NO_OPEN_MARKET_TRADE basket on one anchor.

    ``returns[t]`` is the label (H126 or H252 shareholder total return) or None if the label
    is ineligible; ineligible names are removed from BOTH baskets' denominators and counted.
    """
    buy = [returns[t] for t in eligible if states.get(t) == "NET_BUYER" and returns.get(t) is not None]
    none = [returns[t] for t in eligible if states.get(t) == "NO_OPEN_MARKET_TRADE" and returns.get(t) is not None]
    dropped = sum(1 for t in eligible if returns.get(t) is None)
    if not buy or not none:
        return {"spread": None, "buyers": len(buy), "controls": len(none), "labelIneligible": dropped}
    return {"spread": sum(buy) / len(buy) - sum(none) / len(none), "buyers": len(buy), "controls": len(none),
            "labelIneligible": dropped}
