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

# `freq=quarterly` returns 10-Q only — measured, not assumed: the first slice
# stored 4,971 filings and every one of them was a 10-Q. That matters because a
# trailing-twelve-month figure built by rollforward needs the ANNUAL filing as
# its anchor, and Q4 exists nowhere else (it is the year minus the nine-month
# cumulative). So both frequencies are collected.
QUARTERLY = "quarterly"
ANNUAL = "annual"
FREQUENCIES = (QUARTERLY, ANNUAL)

# finnhub emits the filer's US-GAAP tag under TWO spellings, and which one
# arrives varies by filing: the first slice carried `Assets` 및 `us-gaap_Assets`,
# `NetIncomeLoss` and `us-gaap_NetIncomeLoss`, and so on down the list. A reader
# that knows one spelling reports the other as absent — the third time this
# repository has met that shape, after FMP's `fillingDate` and polygon's
# normalised keys. The raw tag is what gets STORED; this is for reading.
NAMESPACE_SEPARATORS = ("_", ":")
KNOWN_NAMESPACES = ("us-gaap", "usgaap", "dei", "srt", "ifrs-full", "invest")


def strip_namespace(concept: str | None) -> str:
    """`us-gaap_Assets` and `Assets` are the same account, so they compare equal.

    Only a KNOWN namespace is stripped. A filer's own extension tag can contain
    an underscore too, and collapsing `AcmeCorp_SpecialCharge` to
    `SpecialCharge` would merge two accounts that are not the same thing.
    """
    if not concept:
        return ""
    text = str(concept)
    for separator in NAMESPACE_SEPARATORS:
        head, found, tail = text.partition(separator)
        if found and head.lower() in KNOWN_NAMESPACES and tail:
            return tail
    return text


# Eight spellings arrived in the first slice for what are really three units:
# `usd` 388,484 · `_usd` 36,280 · `usdollar` 3,128 · `usd/shares` 8,789 ·
# `usd/share` 5,976 · `_usd_/_shares` 1,372 · `shares` 7,725 · `unit12` 7,185.
# A derivation that filtered on `unit == "usd"` would have dropped 39,408
# currency values without a word. `unit12` is deliberately NOT guessed at — it
# gets its own class so it stays visible until someone measures what it is.
CURRENCY = "currency"
PER_SHARE = "perShare"
SHARES = "shares"
UNCLASSIFIED = "unclassified"


def unit_class(unit: str | None) -> str:
    """Which of the three units a spelling means, or that we do not know.

    Per-share is tested before currency on purpose: `usd/shares` contains
    `usd`, and classifying it as currency would turn an EPS into a dollar
    amount that nothing downstream could tell apart from one.
    """
    if not unit:
        return UNCLASSIFIED
    text = "".join(ch for ch in str(unit).lower() if ch.isalnum() or ch == "/")
    if "/" in text or text.endswith("pershare") or text.endswith("pershares"):
        left, _, right = text.partition("/")
        if right.startswith("share") and left.startswith(("usd", "usdollar")):
            return PER_SHARE
        return PER_SHARE if right.startswith("share") else UNCLASSIFIED
    if text.startswith("share"):
        return SHARES
    if text.startswith("usd") or text.startswith("usdollar"):
        return CURRENCY
    return UNCLASSIFIED


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
              done: set[tuple[str, str, str, str]],
              frequencies: tuple[str, ...] = FREQUENCIES
              ) -> list[tuple[str, str, str, str]]:
    """(ticker, window start, window end, freq) still to fetch.

    Oldest window first, and ANNUAL before quarterly within a window. Both
    orderings are about what a spent budget leaves behind: the early
    cross-sections are the ones the replay cannot score at all, and the annual
    filing is the anchor a rollforward needs — a store full of quarters with no
    year in it cannot produce a single trailing-twelve-month figure, so the
    cheap half (one 10-K a year) is bought first.
    """
    order = {ANNUAL: 0, QUARTERLY: 1}
    return [(ticker, start, end, freq)
            for start, end in spans
            for freq in sorted(frequencies, key=lambda f: order.get(f, 9))
            for ticker in sorted(tickers)
            if (ticker, start, end, freq) not in done]


def normalise_done(entries) -> set[tuple[str, str, str, str]]:
    """Windows already asked for, read from a file that may predate `freq`.

    The first slice stored three-item entries and every one of them was a
    quarterly call. Dropping them would re-buy 1,500 windows; guessing they
    covered both frequencies would skip 1,500 annual calls that never happened.
    So a three-item entry means exactly what it did: the quarterly pass.
    """
    done: set[tuple[str, str, str, str]] = set()
    for entry in entries or []:
        if not isinstance(entry, (list, tuple)):
            continue
        if len(entry) == 3:
            done.add((str(entry[0]), str(entry[1]), str(entry[2]), QUARTERLY))
        elif len(entry) == 4:
            done.add(tuple(str(part) for part in entry))       # type: ignore[arg-type]
    return done


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


def build_record(ticker: str, filing: dict, collected_at: str,
                 freq: str = QUARTERLY) -> tuple[dict | None, str]:
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
        # Which pass fetched it. The same 10-K can come back from both
        # frequencies, and `filing_id` already dedupes on the accession, so
        # this is a note about provenance rather than part of the identity.
        "requestedFreq": freq,
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
    per_freq: Counter = Counter()
    forms_by_freq: dict[str, Counter] = {}
    raw_concepts: dict[str, Counter] = {"bs": Counter(), "ic": Counter(), "cf": Counter()}
    collapsed: dict[str, Counter] = {"bs": Counter(), "ic": Counter(), "cf": Counter()}
    units: Counter = Counter()
    unit_classes: Counter = Counter()
    resolved_classes: Counter = Counter()
    unclassified_units: Counter = Counter()
    missing_days = 0
    for record in records:
        form = str(record.get("form") or "?")
        freq = str(record.get("requestedFreq") or "?")
        days = record.get("periodDays")
        bucket = period_bucket(days)
        if days is None:
            missing_days += 1
        per_form.setdefault(form, Counter())[bucket] += 1
        per_freq[freq] += 1
        forms_by_freq.setdefault(freq, Counter())[form] += 1
        # Units are counted twice on purpose: once as the label reads on its
        # own, and once resolved inside this filing. The gap between the two is
        # how many values a label-only reading would drop.
        resolved = resolve_units(record)
        for section, entries in (record.get("statements") or {}).items():
            for entry in entries or []:
                concept = entry.get("concept")
                if concept:
                    raw_concepts.setdefault(section, Counter())[concept] += 1
                    collapsed.setdefault(section, Counter())[strip_namespace(concept)] += 1
                unit = entry.get("unit")
                if unit:
                    units[str(unit)] += 1
                    kind = unit_class(unit)
                    unit_classes[kind] += 1
                    settled = resolved.get(str(unit), UNCLASSIFIED)
                    resolved_classes[settled] += 1
                    if settled == UNCLASSIFIED:
                        unclassified_units[str(unit)] += 1
    return {
        "filings": len(records),
        "periodLengthByForm": {form: dict(counts.most_common())
                               for form, counts in sorted(per_form.items())},
        "filingsWithNoPeriodLength": missing_days,
        # Which pass produced which form. `freq=quarterly` returned nothing but
        # 10-Q in the first slice, and that is the fact the annual pass exists
        # to change — so it is reported rather than assumed to have changed.
        "filingsByFreq": dict(per_freq.most_common()),
        "formsByFreq": {freq: dict(counts.most_common())
                        for freq, counts in sorted(forms_by_freq.items())},
        "conceptsBySection": {section: len(counts) for section, counts in raw_concepts.items()},
        # The same count after `us-gaap_Assets` and `Assets` stop being two
        # accounts. The gap between the two numbers IS the double-spelling.
        "conceptsBySectionCollapsed": {section: len(counts)
                                       for section, counts in collapsed.items()},
        "topConcepts": {section: [c for c, _ in counts.most_common(12)]
                        for section, counts in raw_concepts.items()},
        "topConceptsCollapsed": {section: [c for c, _ in counts.most_common(12)]
                                 for section, counts in collapsed.items()},
        "units": dict(units.most_common(12)),
        "unitClasses": dict(unit_classes.most_common()),
        # What the labels mean once each filing settles its own: 259 filings in
        # the first annual pass state their amounts under the filer's own XBRL
        # unit ids, and a label-only reading drops them.
        "unitClassesResolved": dict(resolved_classes.most_common()),
        # Anything the classifier could not place, kept by name so it stays a
        # question someone can answer instead of a silently dropped value.
        "unclassifiedUnits": dict(unclassified_units.most_common(8)),
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


# ---------------------------------------------------------------------------
# Is a 10-Q's income statement the quarter, or the year to date?
# ---------------------------------------------------------------------------
# The first slice answered half of this: every 10-Q states a FILING period, and
# those periods fall into three near-equal groups — 1,801 at a quarter, 1,615 at
# a half, 1,553 at three quarters. That is the signature of a period running
# from the fiscal year start, not of three independent quarters.
#
# But `report.ic` entries carry no dates of their own, so the filing's period
# being cumulative is evidence about the VALUES, not proof. DART faced exactly
# this and settled it by value ratios over 84 companies rather than by field
# presence. The same method applies here and the stored filings already support
# it: if the values are cumulative, the half-year figure is about twice the
# first quarter's and the nine-month figure about three times it. If they are
# independent quarters, all three are about equal.
#
# The median across many companies is the statistic, never one company's ratio:
# no single firm earns evenly through the year, and a seasonal one would
# "disprove" whichever reading it happened to contradict.
Q1, Q2, Q3, FY = "Q1", "Q2", "Q3", "FY"

CUMULATIVE = "CUMULATIVE"
DISCRETE_QUARTERS = "DISCRETE_QUARTERS"
INCONCLUSIVE = "INCONCLUSIVE"

# Flow accounts only. A balance-sheet level is a stock at a date and its ratio
# across quarters says nothing about period semantics.
FLOW_CONCEPTS = {
    "netIncome": ("NetIncomeLoss", "ProfitLoss"),
    "revenue": ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                "SalesRevenueNet", "RevenueFromContractWithCustomerIncludingAssessedTax"),
    "operatingIncome": ("OperatingIncomeLoss",),
    "operatingCashFlow": ("NetCashProvidedByUsedInOperatingActivities",
                          "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"),
}
SECTION_OF = {"netIncome": "ic", "revenue": "ic", "operatingIncome": "ic",
              "operatingCashFlow": "cf"}

# How far from the ideal a median may sit and still decide. Cumulative predicts
# 2.0 and 3.0; independent quarters predict 1.0 and 1.0. The bands are wide
# because real firms are seasonal, and they do not overlap, so a median inside
# one is outside the other.
CUMULATIVE_BAND = ((1.6, 2.4), (2.4, 3.6))
DISCRETE_BAND = ((0.7, 1.3), (0.7, 1.3))


def concept_value(record: dict, concept_key: str) -> float | None:
    """One flow account from one filing, under either tag spelling.

    Only currency units are accepted: an EPS carries the same account name in
    some filings and dividing a per-share figure by a dollar one would produce
    a ratio that means nothing.
    """
    section = SECTION_OF.get(concept_key)
    wanted = FLOW_CONCEPTS.get(concept_key, ())
    if not section:
        return None
    # Resolved inside the filing, not from the label alone: 259 filings state
    # their amounts under the filer's own unit ids, and reading only the labels
    # a table knows drops 17,573 values that are ordinary dollar figures.
    resolved = resolve_units(record)
    for entry in (record.get("statements") or {}).get(section) or []:
        if strip_namespace(entry.get("concept")) not in wanted:
            continue
        if value_class(record, entry, resolved) != CURRENCY:
            continue
        value = entry.get("value")
        if isinstance(value, (int, float)):
            return float(value)
    return None


def quarter_stage(record: dict) -> str | None:
    """Which stage of the fiscal year this filing's period reaches.

    Read from the stated period length, and from nothing else. `fiscalQuarter`
    says which report it is; the form says what the SEC calls the document; what
    a rollforward needs to know is how much of the year the NUMBERS cover.

    The form was trusted here at first — a 10-K was taken to be a year by
    definition — and the first annual pass showed why that is wrong. Four of
    1,661 10-K filings state a period that is not a year: LYB's 91 days,
    TTWO's 89, DRI's 244, and one that states no span at all. Those are
    transition reports, filed when a company moves its fiscal year end. Feeding
    LYB's 91-day figure into `FY(Y-1) − cum(Y-1,Q) + cum(Y,Q)` as the annual
    term understates the year roughly fourfold, and produces a number that
    looks entirely ordinary on the way through.

    A period that is not one of the four stages returns None rather than a
    guess: a 0-day span and a >400-day one are as unusable as a missing one.
    """
    return {"quarter (46-135d)": Q1, "half (136-225d)": Q2,
            "three quarters (226-315d)": Q3,
            "year (316-400d)": FY}.get(period_bucket(record.get("periodDays")))


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def period_semantics(records: list[dict], concept_key: str = "netIncome") -> dict:
    """Cumulative or independent quarters, decided by value ratios.

    Ratios are taken WITHIN one ticker-year, so a company's size never enters.
    A year contributes only if the stage it needs is present and the first
    quarter is far enough from zero to divide by — a near-zero denominator
    produces an enormous ratio that would move a mean and does move a small
    median.
    """
    by_year: dict[tuple[str, object], dict[str, float]] = {}
    for record in records:
        stage = quarter_stage(record)
        value = concept_value(record, concept_key)
        if stage is None or value is None:
            continue
        key = (str(record.get("ticker")), record.get("fiscalYear"))
        # First writer wins, matching the store's own dedupe rule.
        by_year.setdefault(key, {}).setdefault(stage, value)

    half_over_first: list[float] = []
    three_over_first: list[float] = []
    three_over_year: list[float] = []
    for stages in by_year.values():
        first = stages.get(Q1)
        if first is None or abs(first) < 1.0:
            continue
        if stages.get(Q2) is not None:
            half_over_first.append(stages[Q2] / first)
        if stages.get(Q3) is not None:
            three_over_first.append(stages[Q3] / first)
        if stages.get(Q3) is not None and stages.get(FY) not in (None, 0):
            three_over_year.append(stages[Q3] / stages[FY])

    medians = {
        "halfOverFirst": _median(half_over_first),
        "threeQuartersOverFirst": _median(three_over_first),
        "threeQuartersOverYear": _median(three_over_year),
    }
    counts = {"halfOverFirst": len(half_over_first),
              "threeQuartersOverFirst": len(three_over_first),
              "threeQuartersOverYear": len(three_over_year),
              "tickerYears": len(by_year)}

    verdict, meaning = _read_ratios(medians, counts)
    return {"concept": concept_key, "medians": medians, "counts": counts,
            "verdict": verdict, "meaning": meaning,
            "expected": {"cumulative": {"halfOverFirst": 2.0,
                                        "threeQuartersOverFirst": 3.0,
                                        "threeQuartersOverYear": 0.75},
                         "discreteQuarters": {"halfOverFirst": 1.0,
                                              "threeQuartersOverFirst": 1.0,
                                              "threeQuartersOverYear": 0.25}}}


# A median of one ratio is one company. Below this the answer is not reported,
# because a verdict about how an entire vendor states its filings should not
# rest on a handful of firms that might all be in one industry.
MIN_RATIOS = 30


def _read_ratios(medians: dict, counts: dict) -> tuple[str, str]:
    half, three = medians["halfOverFirst"], medians["threeQuartersOverFirst"]
    if half is None or three is None:
        return INCONCLUSIVE, "비율을 만들 수 있는 티커-연도가 없습니다"
    if min(counts["halfOverFirst"], counts["threeQuartersOverFirst"]) < MIN_RATIOS:
        return INCONCLUSIVE, (f"비율 표본이 {MIN_RATIOS}개 미만입니다 — 수집을 더 "
                              f"채운 뒤에 다시 재십시오")
    (half_lo, half_hi), (three_lo, three_hi) = CUMULATIVE_BAND
    if half_lo <= half <= half_hi and three_lo <= three <= three_hi:
        return CUMULATIVE, ("반기가 1분기의 약 2배, 3분기 누계가 약 3배 — 회계연도 "
                            "시작부터의 누계입니다. TTM은 rollforward로 만들어야 "
                            "합니다: FY(Y-1) − cum(Y-1,Q) + cum(Y,Q)")
    (dhalf_lo, dhalf_hi), (dthree_lo, dthree_hi) = DISCRETE_BAND
    if dhalf_lo <= half <= dhalf_hi and dthree_lo <= three <= dthree_hi:
        return DISCRETE_QUARTERS, ("세 분기가 서로 비슷한 크기 — 각각 독립된 3개월 "
                                   "수치입니다. TTM은 네 분기 합입니다")
    return INCONCLUSIVE, (f"중앙값이 두 밴드 어디에도 들지 않습니다 "
                          f"(반기/1분기 {half:.2f}, 3분기/1분기 {three:.2f}) — "
                          f"단정하지 말고 원인을 보십시오")


# ---------------------------------------------------------------------------
# Units that only mean something inside the filing that used them
# ---------------------------------------------------------------------------
# The first annual pass turned up 5,353 values under labels that are not units
# at all: `unit12`, `unit1`, `unit13`, `u001`, `u002`, `unit14`, `unit15`. They
# are the filer's own XBRL unit ids, passed through untranslated, and the
# concepts underneath them are ordinary — `NetIncomeLoss`, `Assets`,
# `OperatingIncomeLoss`, `WeightedAverageNumberOfDilutedSharesOutstanding`.
#
# Two things were measured before writing this, and both matter:
#
#   * the same label means different things in different filings. `unit1`
#     carries dollars in one and a share count in another, so no table mapping
#     `unit1` to a meaning can exist. `unit_class` is right to refuse it.
#   * inside ONE filing the labels are consistent, and there are only two to
#     four of them. AMD's 2012 10-Q puts every dollar figure under `unit1` and
#     both EPS figures under `unit14`.
#
# So the label resolves per filing, from the concepts that carry it: a label
# holding `EarningsPerShareBasic` is that filing's per-share unit. 186 filings
# are entirely opaque this way and 133 partly; dropping them would lose those
# names from the US store for the periods involved.
#
# Where a label carries no anchor at all it stays unclassified. Guessing from
# how many values it holds, or from what the other labels turned out to be,
# would be inventing a unit for a number we would then treat as money.
UNIT_ANCHORS = {
    PER_SHARE: ("EarningsPerShareBasic", "EarningsPerShareDiluted",
                "EarningsPerShareBasicAndDiluted",
                "CommonStockDividendsPerShareDeclared",
                "IncomeLossFromContinuingOperationsPerBasicShare",
                "IncomeLossFromContinuingOperationsPerDilutedShare"),
    SHARES: ("WeightedAverageNumberOfSharesOutstandingBasic",
             "WeightedAverageNumberOfDilutedSharesOutstanding",
             "WeightedAverageNumberOfBasicSharesOutstanding",
             "CommonStockSharesOutstanding", "CommonStockSharesIssued",
             "EntityCommonStockSharesOutstanding"),
    CURRENCY: ("Assets", "Liabilities", "StockholdersEquity",
               "LiabilitiesAndStockholdersEquity", "NetIncomeLoss",
               "ProfitLoss", "Revenues", "OperatingIncomeLoss",
               "CashAndCashEquivalentsAtCarryingValue",
               "NetCashProvidedByUsedInOperatingActivities"),
}
# Per-share first, for the same reason `unit_class` tests it first: an EPS tag
# and a dollar tag can share a label only if one of them is wrong, and reading
# a per-share figure as money is the error that cannot be seen downstream.
ANCHOR_ORDER = (PER_SHARE, SHARES, CURRENCY)


def _looks_generated(label: str) -> bool:
    """Is this an XBRL unit id the filer made up, rather than a named unit?

    Every label the anchors promoted to currency across the first 6,632 filings
    was of the first kind — `unit12`, `unit1`, `u001`, `u002`, `unit13`,
    `unit14` — and every named one (`pure`, `number`, `store`, `eur`) was of
    the second. The digit is what separates them. It is a rule about the shape
    of the labels this vendor actually sends, not a law about XBRL, and it
    fails to the safe side: a named unit nobody recognises stays unclassified
    instead of becoming dollars.
    """
    return any(ch.isdigit() for ch in label)


def resolve_units(record: dict) -> dict[str, str]:
    """What each unit label means IN THIS FILING.

    Labels `unit_class` can read on their own are taken from it. The rest are
    decided by the anchors above, and left unclassified when no anchor carries
    them.
    """
    carried: dict[str, set[str]] = {}
    for section in ("bs", "ic", "cf"):
        for entry in (record.get("statements") or {}).get(section) or []:
            label = str(entry.get("unit") or "")
            carried.setdefault(label, set()).add(strip_namespace(entry.get("concept")))

    resolved: dict[str, str] = {}
    for label, concepts in carried.items():
        known = unit_class(label)
        if known != UNCLASSIFIED:
            resolved[label] = known
            continue
        for meaning in ANCHOR_ORDER:
            if not (concepts & set(UNIT_ANCHORS[meaning])):
                continue
            if meaning == CURRENCY and not _looks_generated(label):
                # An anchor says what KIND of quantity a label holds. It cannot
                # say which currency, and `CURRENCY` means US dollars
                # everywhere below this. `Revenues` under a label spelled `eur`
                # is a revenue figure, and adding it to dollars is the kind of
                # error that leaves every number looking ordinary. Per-share and
                # share counts have no denomination, so they promote freely.
                break
            resolved[label] = meaning
            break
        else:
            resolved[label] = UNCLASSIFIED
        resolved.setdefault(label, UNCLASSIFIED)
    return resolved


def value_class(record: dict, entry: dict,
                resolved: dict[str, str] | None = None) -> str:
    """One value's unit, resolved against the filing it came from."""
    if resolved is None:
        resolved = resolve_units(record)
    return resolved.get(str(entry.get("unit") or ""), UNCLASSIFIED)
