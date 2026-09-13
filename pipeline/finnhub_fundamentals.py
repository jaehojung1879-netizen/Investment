"""What a finnhub `financials-reported` response means, decided once.

WHY THIS FILE EXISTS SEPARATELY FROM THE COLLECTOR. The Korean half is built
in three pieces — `dart_fundamentals` says what a filing IS, the collector
fetches, `dart_derive` turns filings into factor inputs — because a derivation
found wrong has to be fixable without re-running the fetch. The US half is
built the same way, and this is the first piece.

WHAT IS DELIBERATELY NOT HERE YET: the derivation. `dart_derive` could only be
written after the collector's field inventory had MEASURED, over 2,927
filings, whether a Q3 income figure was three months or nine — and reading a
cumulative cash flow as a quarterly one would have inflated free cash flow
four times over with nothing raising an error. The same question is open for
finnhub and the answer is not in anyone's memory: a US 10-Q's income statement
is filed with both a three-month and a year-to-date context, and which one a
vendor flattens into `report.ic` is a fact about the vendor. So this run
collects and REPORTS that distribution; the derivation is written against the
answer.

WHAT A FILING MUST CARRY TO BE STORED. `filedDate`. Point-in-time is the whole
reason the collection exists, and a row that cannot say when it became visible
would sit in the store looking like coverage while being unusable — the same
rule the Korean collector applies to DART's receipt date.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

# One year before the replay's first session. A trailing-twelve-month figure at
# 2013-01 needs the four quarters behind it, so the collection has to start
# earlier than the replay does or the first year of US value and quality is
# structurally absent.
FIRST_YEAR = 2012

# How wide a window to ask for per call. finnhub's `financials-reported` takes
# `from`/`to`; the probe was served 5-7 filings for an eighteen-month window,
# so this is chosen to stay clear of any per-response cap rather than to
# minimise calls. If a window ever comes back exactly full, that is the shape
# of a truncated download — see `window_looks_capped`.
WINDOW_MONTHS = 18

# What the vendor is documented to allow per minute is not what this measures.
# The collector paces at this and reports any rate-limit refusal it still gets,
# because polygon's free tier refused three of four samples in probe run #2
# while the probe was pacing at a third of a second and calling it coverage.
PACE_SECONDS = 1.1

# A refusal that says "slow down" is not a finding about the vendor's history.
# It means ask again, later, and it must never be counted as an absence.
RATE_LIMIT_MARKERS = (
    "exceeded the maximum requests",
    "rate limit",
    "too many requests",
    "api limit reached",
)

NO_FILING_DATE = "NO_FILING_DATE"
NO_ACCESSION = "NO_ACCESSION"
NO_PERIOD = "NO_PERIOD"


def is_rate_limited(status: int | None, body_text: str) -> bool:
    """Did the vendor ask us to slow down, rather than answer about the data?"""
    if status == 429:
        return True
    lowered = (body_text or "").lower()
    return any(marker in lowered for marker in RATE_LIMIT_MARKERS)


def windows(from_year: int = FIRST_YEAR, through: str | None = None,
            months: int = WINDOW_MONTHS) -> list[tuple[str, str]]:
    """Consecutive half-open windows covering the whole collection span.

    Deterministic and gapless: two runs build the same list, and the work list
    below is keyed off it, so a resumed run cannot silently ask for a different
    span than the one already stored.
    """
    start = date(from_year, 1, 1)
    end_bound = date.fromisoformat(through) if through else date.today()
    out: list[tuple[str, str]] = []
    while start <= end_bound:
        # Add `months` by advancing whole months, then step back one day so
        # consecutive windows abut without overlapping — an overlap would fetch
        # the same filing twice and pay for it twice.
        month_index = start.month - 1 + months
        stop = date(start.year + month_index // 12, month_index % 12 + 1, 1) \
            - timedelta(days=1)
        out.append((start.isoformat(), min(stop, end_bound).isoformat()))
        start = stop + timedelta(days=1)
    return out


def work_list(tickers: list[str], spans: list[tuple[str, str]],
              done: set[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    """(ticker, window start, window end) still to fetch, oldest window first.

    Oldest first on purpose. The early cross-sections are the ones the replay
    cannot currently score at all, and a budget that runs out should have spent
    itself on the years that are dark rather than on the years prices already
    cover.
    """
    return [(ticker, start, end)
            for start, end in spans
            for ticker in sorted(tickers)
            if (ticker, start, end) not in done]


def filing_id(ticker: str, accession: str) -> str:
    """Identity of one filing. The accession number is SEC's own, so two
    windows that both return a filing agree on it and it is stored once."""
    return f"{ticker}|{accession}"


def period_days(start: str | None, end: str | None) -> int | None:
    """How long the period actually is, from the filing's own dates.

    This is the number the derivation turns on, and US filings state it —
    unlike DART, where quarterly semantics had to be recovered from value
    ratios over 84 companies. Stating it is not the same as it being right, so
    it is reported as a distribution rather than trusted per row.
    """
    if not start or not end:
        return None
    try:
        return (date.fromisoformat(str(end)[:10]) - date.fromisoformat(str(start)[:10])).days
    except ValueError:
        return None


def build_record(ticker: str, filing: dict, collected_at: str) -> tuple[dict | None, str]:
    """One raw filing, stored as the vendor stated it, or a refusal reason.

    Nothing is derived here. The concepts are kept under the filer's own
    US-GAAP tags, because a normalisation applied at collection time cannot be
    revisited without re-fetching, and probe run #2 is a standing reminder that
    a tag vocabulary is a thing to measure rather than to assume.
    """
    accession = str(filing.get("accessNumber") or "").strip()
    if not accession:
        return None, NO_ACCESSION
    filed = str(filing.get("filedDate") or "")[:10]
    if not filed:
        return None, NO_FILING_DATE
    end = str(filing.get("endDate") or "")[:10]
    if not end:
        return None, NO_PERIOD

    report = filing.get("report") or {}
    statements = {section: [
        {"concept": entry.get("concept"), "label": entry.get("label"),
         "unit": entry.get("unit"), "value": entry.get("value")}
        for entry in (report.get(section) or []) if isinstance(entry, dict)
    ] for section in ("bs", "ic", "cf")}

    return {
        "id": filing_id(ticker, accession),
        "ticker": ticker,
        "accession": accession,
        "cik": str(filing.get("cik") or "") or None,
        "form": str(filing.get("form") or "") or None,
        "fiscalYear": filing.get("year"),
        "fiscalQuarter": filing.get("quarter"),
        "periodStart": str(filing.get("startDate") or "")[:10] or None,
        "periodEnd": end,
        "periodDays": period_days(filing.get("startDate"), filing.get("endDate")),
        # `availableFrom` is the field the whole collection exists for, and it
        # is SEC's accepted-filing date carried through untouched. `acceptedDate`
        # is kept beside it rather than instead of it: it is a timestamp, and a
        # replay licenses by date.
        "availableFrom": filed,
        "acceptedDate": str(filing.get("acceptedDate") or "") or None,
        "statements": statements,
        "source": "finnhub/financials-reported",
        "collectedAt": collected_at,
    }, ""


def shard_year(record: dict) -> int:
    """Which yearly shard a filing belongs to — by the period it reports on,
    not by when it was filed, so a January filing about last year sits with the
    year it describes."""
    year = record.get("fiscalYear")
    if isinstance(year, int) and year > 1900:
        return year
    return int(str(record.get("periodEnd") or "1900")[:4])


def inventory(records: list[dict]) -> dict:
    """What the vendor actually sent, split the way the derivation needs it.

    Pooled counts cannot answer the question that matters. "12% of rows carry a
    year-to-date column" told the Korean collector nothing about WHICH rows, and
    whether a Q3 revenue figure is three months or nine is exactly what a TTM is
    built from. So period length is counted PER FORM, in buckets a reader can
    map onto quarters, and the concepts are counted per statement section.
    """
    per_form: dict[str, Counter] = {}
    concepts: dict[str, Counter] = {"bs": Counter(), "ic": Counter(), "cf": Counter()}
    units: Counter = Counter()
    missing_days = 0
    for record in records:
        form = str(record.get("form") or "?")
        days = record.get("periodDays")
        bucket = period_bucket(days)
        if days is None:
            missing_days += 1
        per_form.setdefault(form, Counter())[bucket] += 1
        for section, entries in (record.get("statements") or {}).items():
            for entry in entries or []:
                if entry.get("concept"):
                    concepts.setdefault(section, Counter())[entry["concept"]] += 1
                if entry.get("unit"):
                    units[str(entry["unit"])] += 1
    return {
        "filings": len(records),
        "periodLengthByForm": {form: dict(counts.most_common())
                               for form, counts in sorted(per_form.items())},
        "filingsWithNoPeriodLength": missing_days,
        "conceptsBySection": {section: len(counts) for section, counts in concepts.items()},
        "topConcepts": {section: [c for c, _ in counts.most_common(12)]
                        for section, counts in concepts.items()},
        "units": dict(units.most_common(8)),
    }


def period_bucket(days: int | None) -> str:
    """A period length as something a reader can act on.

    The boundaries are wide because fiscal quarters are not 91 days and nobody
    should have to know that to read the report.
    """
    if days is None:
        return "unstated"
    if days <= 45:
        return "<=45d"
    if days <= 135:
        return "quarter (46-135d)"
    if days <= 225:
        return "half (136-225d)"
    if days <= 315:
        return "three quarters (226-315d)"
    if days <= 400:
        return "year (316-400d)"
    return ">400d"


def progress(collected: int, pending: int) -> dict:
    total = collected + pending
    return {"collected": collected, "pending": pending, "total": total,
            "completePct": round(100.0 * collected / total, 2) if total else 100.0}
