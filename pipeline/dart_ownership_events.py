"""Korean 5%-rule ownership events (지분공시 종합정보, 대량보유상황보고), stored raw.

WHAT THIS IS FOR. `alpha-information-inventory-v1` named DART's large-holdings
disclosure (API group `DS004`) as the lowest-effort new Korean data source in
its entire inventory, precisely because it is the SAME vendor, the SAME key
and the SAME receipt-date PIT mechanism `dart_fundamentals.py` already
implements — there is no second authentication path or second point-in-time
question to answer, only a second endpoint.

THE ENDPOINT, AS RESEARCHED (WebFetch of OpenDART's own developer guide was
blocked by this sandbox's egress; researched instead via WebFetch/WebSearch of
third-party libraries that wrap the same documented endpoint — `dart-fss`'s
own source and `FinanceData/OpenDartReader`'s README, both citing the field
set consistently, 2026-09-24). The endpoint is `majorstock.json`, under API
group DS004 (지분공시 종합정보), taking `corp_code` (the same DART corp code
`dart_fundamentals.corp_code_map` already resolves) and returning one row per
report per filer per holding. Response fields corroborated across both
sources: `rcept_no` (접수번호), `rcept_dt` (접수일자), `corp_code`, `corp_name`,
`report_tp` (보고구분: observed values include "신규" and "변동"), `repror`
(대표보고자 — the filer/holder name), `stkqy` (보유주식등의수), `stkqy_irds`
(변동수량), `stkrt` (보유비율), `stkrt_irds` (변동비율). NOT independently
confirmed and therefore NOT read by this module: whether the endpoint states a
"before" holding percentage as its own field or only the post-report ratio
plus the delta (`stkrt` and `stkrt_irds` together would let a caller
reconstruct "before" as `stkrt - stkrt_irds`, but this module does not do that
arithmetic itself — a subtraction performed on an unconfirmed field pair is a
number invented rather than a number read).

`dart_fundamentals.receipt_date` IS REUSED, NOT REIMPLEMENTED. The receipt
number's first eight digits are the visibility date on every DART endpoint,
by construction of the number itself — that is a fact about DART's numbering,
not about the statement endpoint specifically, so importing the existing
function is correct rather than convenient. `PIT fundamentals invariants
(v2.9)`'s rule applies exactly as written: a row whose receipt date cannot be
read is refused, never stored with a substitute.

REPORT TYPE, TRANSLATED WITHOUT INVENTING VALUES NOT YET OBSERVED. DART's
`report_tp` is a free Korean label whose only two values corroborated above
are "신규" (new 5%+ holder) and "변동" (a change in an existing holding). This
module maps exactly those two and passes anything else through UNCHANGED
under `reportTypeRaw` — the finer distinctions the task asked for
(INCREASE / DECREASE / EXIT_BELOW_THRESHOLD) are DERIVED from the sign of
`stkrt_irds` and from whether `stkrt` crossed below 5%, never read as if DART
stated them directly, because that mapping was not independently verified
against a live response.

APPEND-ONLY, KEYED BY RECEIPT NUMBER. A restatement or a correction to an
already-filed report arrives at DART as its own filing with its own
`rcept_no` and its own receipt date — never as an edit to the row already on
file. `amendmentFlag` records whether a given (filer, holder) pair had an
earlier receipt number for what looks like the same underlying holding change,
so a reader can see the amendment history without this module ever
overwriting what was visible before it.
"""
from __future__ import annotations

from . import dart_fundamentals as DF

# Reused directly. Recomputing "the first eight digits of the receipt number"
# a second time in this module is exactly the second-implementation risk
# `alpha-risk-separation-v1`'s invariants warn against one level up: a control
# that is called is safer than a control that is reproduced.
receipt_date = DF.receipt_date

# The two `report_tp` values corroborated across independent sources
# researching this endpoint (see module docstring). Anything else DART
# returns is passed through under `reportTypeRaw` rather than forced into one
# of these two.
REPORT_TYPE_NEW = "NEW_5PCT_HOLDER"
REPORT_TYPE_CHANGE = "CHANGE"
_REPORT_TYPE_MAP = {"신규": REPORT_TYPE_NEW, "변동": REPORT_TYPE_CHANGE}

# The 5% line the report family is named for. A holding percentage crossing
# below this on a CHANGE report is read as an exit signal — DERIVED, because
# no source consulted confirmed DART states "exited" as its own value.
DISCLOSURE_THRESHOLD_PCT = 5.0


def parse_percent(text) -> float | None:
    """A DART percentage string to a float, or None where nothing was stated.

    Reuses the amount grammar `dart_fundamentals.parse_amount` already
    established (comma thousands, accounting parentheses, blank-means-none)
    rather than writing a second parser for the same grammar.
    """
    return DF.parse_amount(text)


def direction_of_change(stkrt_irds: float | None, stkrt: float | None) -> str | None:
    """INCREASE / DECREASE / EXIT_BELOW_THRESHOLD / None, derived and labelled as such.

    Never confused with a value DART stated: `report_tp` is DART's own word,
    and this is this module's own reading of `stkrt`/`stkrt_irds`, published
    under a different field name so the two are never mistaken for each other.
    """
    if stkrt_irds is None:
        return None
    if stkrt is not None and stkrt < DISCLOSURE_THRESHOLD_PCT and stkrt_irds < 0:
        return "EXIT_BELOW_THRESHOLD"
    if stkrt_irds > 0:
        return "INCREASE"
    if stkrt_irds < 0:
        return "DECREASE"
    return None


def build_event(row: dict, *, ticker: str, collected_at: str) -> tuple[dict | None, str]:
    """One stored ownership-event row from one `majorstock.json` response row.

    Refused, never stored with a substitute, when the receipt date cannot be
    read — the same rule `dart_fundamentals.build_record` applies to a
    financial statement, for the same reason: a row that cannot say when it
    became visible is unusable in a point-in-time replay.
    """
    rcept_no = str(row.get("rcept_no") or "").strip()
    if not rcept_no:
        return None, "NO_RECEIPT_NO"
    available_from = receipt_date(rcept_no)
    if available_from is None:
        return None, "NO_RECEIPT_DATE"

    stkrt = parse_percent(row.get("stkrt"))
    stkrt_irds = parse_percent(row.get("stkrt_irds"))
    stkqy = parse_percent(row.get("stkqy"))
    stkqy_irds = parse_percent(row.get("stkqy_irds"))

    report_tp_raw = str(row.get("report_tp") or "").strip()
    report_type = _REPORT_TYPE_MAP.get(report_tp_raw)

    return {
        "id": f"dart-ownership:{rcept_no}",
        "ticker": ticker,
        "corpCode": row.get("corp_code"),
        "corpName": row.get("corp_name"),
        "filerName": row.get("repror"),
        "reportType": report_type,
        "reportTypeRaw": report_tp_raw or None,
        "changeDirection": direction_of_change(stkrt_irds, stkrt),
        "holdingPctAfter": stkrt,
        "holdingPctChange": stkrt_irds,
        # "Before" is NOT computed as `stkrt - stkrt_irds` here — see module
        # docstring. A caller that wants it may derive it explicitly, with
        # this comment as the reason it is not done implicitly.
        "holdingPctBefore": None,
        "shareCountAfter": stkqy,
        "shareCountChange": stkqy_irds,
        "reportDate": row.get("rcept_dt"),
        "availableFrom": available_from,
        "receiptNo": rcept_no,
        "currency": "KRW",
        "source": "DART:majorstock",
        "collectedAt": collected_at,
    }, ""


def amendment_flags(events: list[dict]) -> list[dict]:
    """Mark every event after the first one for the same (ticker, filer) pair.

    Not a claim that a later filing corrects the number an earlier one
    stated — DART issues a fresh receipt number for a genuinely new change in
    holdings just as readily as for a correction. This flag says only "this
    (ticker, filer) pair has an earlier receipt on file", so a reader can
    look at the sequence rather than assume any one row is definitive.
    """
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for event in sorted(events, key=lambda e: (e.get("ticker"), e.get("filerName"),
                                               str(e.get("availableFrom")), e.get("receiptNo"))):
        key = (event.get("ticker"), event.get("filerName"))
        marked = dict(event)
        marked["amendmentFlag"] = key in seen
        seen.add(key)
        out.append(marked)
    return out


def shard_path(root, year: int):
    from pathlib import Path
    return Path(root) / f"dart-ownership-{int(year):04d}.jsonl.gz"


def record_year(event: dict) -> int | None:
    """The shard year, from the receipt date — never from the report period.

    Sharding by visibility date (not by the fiscal year the report might be
    read as describing) keeps this module's shard boundary meaningful for an
    append-only, receipt-ordered collection the way `dart_fundamentals`
    shards by the fiscal year its records ARE about — the two collections
    shard on different axes because they answer different questions about a
    filing.
    """
    stamp = str(event.get("availableFrom") or "")
    return int(stamp[:4]) if len(stamp) >= 4 and stamp[:4].isdigit() else None
