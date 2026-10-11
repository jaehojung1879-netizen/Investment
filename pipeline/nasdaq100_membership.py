"""Nasdaq-100 point-in-time membership: a representation and its refusals.

Using QQQ as a benchmark needs QQQ's price. Researching stocks that were
ELIGIBLE for the Nasdaq-100 on a past date needs that date's membership, as it
could have been known then. This module holds the second, and it is built to
say "not reconstructible" rather than to fill a gap:

* Membership is only ever produced FORWARD from an evidenced base snapshot by
  applying evidenced events. With no base snapshot there is no membership —
  today's list is never pushed back in time, and trading on Nasdaq never
  implies index membership.
* An event changes membership on its ``effectiveDate``. It can be USED on a
  signal date only if its ``announcementDate`` is not later than that date: an
  effective-in-the-past change that was announced afterwards is not something
  the research could have known. Announced-but-not-yet-effective changes are
  returned separately as pending, never merged.
* Each security carries the ticker valid AT THE EVENT and its share class. A
  present-day ticker is never assumed to be the same security; an unresolved
  identity is ``AMBIGUOUS`` and is reported, not guessed.
* Years with no evidenced event are gaps, listed by date range.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

STATUS_CONFIRMED = "CONFIRMED"
STATUS_AMBIGUOUS = "AMBIGUOUS"
STATUS_UNVERIFIED = "UNVERIFIED_LEAD"

READY = "READY"
PARTIAL = "PARTIAL"
BLOCKED = "BLOCKED"
NOT_RECONSTRUCTIBLE = "NOT_RECONSTRUCTIBLE"


@dataclass(frozen=True)
class Security:
    tickerAtEvent: str
    issuer: str
    shareClass: str | None = None
    identifier: str | None = None          # CUSIP / CIK / FIGI when evidenced
    identityStatus: str = STATUS_CONFIRMED


@dataclass(frozen=True)
class MembershipEvent:
    eventId: str
    sourceId: str
    sourceSha256: str | None
    announcementDate: str | None
    effectiveDate: str
    added: tuple = ()
    removed: tuple = ()
    kind: str = "ANNUAL_RECONSTITUTION"   # or REPLACEMENT, SPECIAL_REBALANCE, METHODOLOGY
    status: str = STATUS_CONFIRMED
    note: str = ""

    def __post_init__(self):
        if self.announcementDate and pd.Timestamp(self.effectiveDate) < pd.Timestamp(self.announcementDate):
            raise ValueError(f"EFFECTIVE_BEFORE_ANNOUNCEMENT {self.eventId}")

    @property
    def knowableFrom(self) -> str:
        """Announcement when evidenced; otherwise the effective date.

        An index change is always announced before it takes effect, so falling
        back to the effective date can only make a change knowable LATER than
        it really was — it loses the pending window, never adds foresight.
        """
        return self.announcementDate or self.effectiveDate


@dataclass(frozen=True)
class BaseSnapshot:
    sourceId: str
    sourceSha256: str | None
    asOfDate: str            # membership the snapshot describes
    publishedDate: str       # when it became knowable
    members: tuple = field(default_factory=tuple)   # Security


def _key(security: Security) -> tuple:
    return (security.tickerAtEvent, security.shareClass)


def membership_knowable_on(signal_date: str, base: BaseSnapshot | None,
                           events: list[MembershipEvent]) -> dict:
    """Members effective on ``signal_date`` using only what was published by then."""
    date = pd.Timestamp(signal_date)
    if base is None:
        return {"status": NOT_RECONSTRUCTIBLE, "reason": "NO_EVIDENCED_BASE_SNAPSHOT",
                "members": None, "pending": []}
    if pd.Timestamp(base.publishedDate) > date or pd.Timestamp(base.asOfDate) > date:
        return {"status": NOT_RECONSTRUCTIBLE, "reason": "BASE_SNAPSHOT_NOT_YET_KNOWABLE",
                "members": None, "pending": []}
    members = {_key(s): s for s in base.members}
    ambiguous, unverified, pending = [], [], []
    ordered = sorted(events, key=lambda e: (e.effectiveDate, e.announcementDate, e.eventId))
    for event in ordered:
        announced = pd.Timestamp(event.knowableFrom)
        effective = pd.Timestamp(event.effectiveDate)
        if effective <= pd.Timestamp(base.asOfDate):
            continue
        if announced > date:
            continue                                   # not knowable yet
        if effective > date:
            pending.append(event.eventId)              # knowable, not yet effective
            continue
        if event.status == STATUS_UNVERIFIED:
            unverified.append(event.eventId)
            continue
        for security in event.removed:
            members.pop(_key(security), None)
        for security in event.added:
            members[_key(security)] = security
        for security in (*event.added, *event.removed):
            if security.identityStatus != STATUS_CONFIRMED:
                ambiguous.append(security.tickerAtEvent)
    status = READY if not (ambiguous or unverified) else PARTIAL
    return {"status": status, "members": sorted(k[0] for k in members),
            "memberCount": len(members), "pending": pending,
            "ambiguousIdentities": sorted(set(ambiguous)), "unverifiedEvents": unverified}


def annual_gaps(events: list[MembershipEvent], first_year: int, last_year: int) -> list[dict]:
    """Calendar years with no evidenced annual reconstitution."""
    covered = {pd.Timestamp(e.effectiveDate).year for e in events
               if e.kind == "ANNUAL_RECONSTITUTION" and e.status == STATUS_CONFIRMED}
    # December reconstitutions are effective the following Monday, which can
    # fall in late December; both years are checked by effective date only.
    return [{"year": y, "gap": "NO_EVIDENCED_ANNUAL_RECONSTITUTION"}
            for y in range(first_year, last_year + 1) if y not in covered]


def classify_reconstruction(base: BaseSnapshot | None, events: list[MembershipEvent],
                            first_year: int, last_year: int) -> dict:
    """READY only with an evidenced base AND every year AND no open identity."""
    gaps = annual_gaps(events, first_year, last_year)
    open_ids = sorted({s.tickerAtEvent for e in events for s in (*e.added, *e.removed)
                       if s.identityStatus != STATUS_CONFIRMED})
    if base is None:
        status = NOT_RECONSTRUCTIBLE
    elif gaps or open_ids or any(e.status != STATUS_CONFIRMED for e in events):
        status = PARTIAL
    else:
        status = READY
    return {"status": status, "baseSnapshot": None if base is None else base.sourceId,
            "events": len(events), "yearGaps": gaps, "openIdentities": open_ids}


# --------------------------------------------------------------------------- #
# The n100tickers yearly files (MIT, derived from the public change record)
# --------------------------------------------------------------------------- #
def parse_yearly_yaml(text: str) -> dict:
    """The strictyaml subset the n100tickers files use, without a YAML dependency.

    ``year: N``, ``tickers_on_Jan_1:`` list, ``changes:`` mapping of quoted
    dates to ``union`` / ``difference`` lists. Comments directly above a date
    are kept as that change's note, because the maintainers record renames and
    known omissions there.
    """
    out = {"year": None, "tickers_on_Jan_1": [], "changes": {}, "notes": {}}
    section = date = op = None
    pending_comment: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped == "---":
            continue
        indent = len(line) - len(line.lstrip())
        if stripped.startswith("#"):
            if section == "changes":
                pending_comment.append(stripped.lstrip("# ").strip())
            continue
        if indent == 0:
            key, _, value = stripped.partition(":")
            section = key
            if key == "year":
                out["year"] = int(value.strip())
            continue
        if section == "tickers_on_Jan_1" and stripped.startswith("- "):
            out["tickers_on_Jan_1"].append(stripped[2:].strip())
        elif section == "changes":
            if stripped.endswith(":") and not stripped.startswith("- ") and indent <= 2:
                date = stripped[:-1].strip().strip("'\"")
                out["changes"][date] = {}
                if pending_comment:
                    out["notes"][date] = " ".join(pending_comment)
                pending_comment = []
            elif stripped in ("union:", "difference:"):
                op = stripped[:-1]
                out["changes"][date][op] = []
            elif stripped.startswith("- "):
                out["changes"][date][op].append(stripped[2:].strip())
            else:
                raise ValueError(f"UNPARSED_LINE {raw!r}")
    if out["year"] is None:
        raise ValueError("YEAR_MISSING")
    return out


def apply_year(doc: dict, through: str | None = None) -> set:
    members = set(doc["tickers_on_Jan_1"])
    for date in sorted(doc["changes"]):
        if through is not None and date > through:
            break
        ops = doc["changes"][date]
        members |= set(ops.get("union", []))
        members -= set(ops.get("difference", []))
    return members


def chain_consistency(docs: dict[int, dict]) -> list[dict]:
    """Applying year y's changes to its 1 January list must give year y+1's."""
    out = []
    for year in sorted(docs):
        if year + 1 not in docs:
            continue
        derived = apply_year(docs[year])
        stated = set(docs[year + 1]["tickers_on_Jan_1"])
        out.append({"year": year, "consistent": derived == stated,
                    "onlyDerived": sorted(derived - stated), "onlyStated": sorted(stated - derived)})
    return out


def events_from_yearly(docs: dict[int, dict], source_id: str, sha_by_year: dict[int, str]) -> list[MembershipEvent]:
    events = []
    for year in sorted(docs):
        for date in sorted(docs[year]["changes"]):
            ops = docs[year]["changes"][date]
            added = tuple(Security(t, issuer="", identityStatus=STATUS_CONFIRMED) for t in ops.get("union", []))
            removed = tuple(Security(t, issuer="", identityStatus=STATUS_CONFIRMED) for t in ops.get("difference", []))
            big_december = date[5:7] == "12" and len(added) + len(removed) >= 4
            events.append(MembershipEvent(
                eventId=f"n100tickers:{date}", sourceId=source_id, sourceSha256=sha_by_year.get(year),
                announcementDate=None, effectiveDate=date, added=added, removed=removed,
                kind="ANNUAL_RECONSTITUTION" if big_december else "REPLACEMENT_OR_CORPORATE_ACTION",
                status=STATUS_CONFIRMED, note=docs[year]["notes"].get(date, "")))
    return events


def membership_intervals(docs: dict[int, dict], start: str, end: str) -> dict[str, list[list[str]]]:
    """Effective-date membership spans per ticker inside [start, end]."""
    first_year, last_year = int(start[:4]), int(end[:4])
    if first_year not in docs:
        raise ValueError(f"NO_BASE_FOR_{first_year}")
    current = apply_year(docs[first_year], through=start)
    spans: dict[str, list[list[str]]] = {t: [[start, None]] for t in current}
    for year in range(first_year, last_year + 1):
        for date in sorted(docs[year]["changes"]):
            if date <= start or date > end:
                continue
            ops = docs[year]["changes"][date]
            for ticker in ops.get("difference", []):
                if ticker in current:
                    spans[ticker][-1][1] = date
                    current.discard(ticker)
            for ticker in ops.get("union", []):
                if ticker not in current:
                    spans.setdefault(ticker, []).append([date, None])
                    current.add(ticker)
    return spans
