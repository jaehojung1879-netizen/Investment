"""Point-in-time (PIT) data access — the layer that makes a replay honest.

The rule this module enforces is narrow and absolute:

    A replay evaluated as of date T may only read values that a market
    participant could actually have read on T.

Not "values that are approximately right for T", and not "today's value applied
retroactively". Every accessor here either returns data that was visible on T or
returns nothing and records *why* — it never silently substitutes a current
snapshot for a historical one.

Four separate leak channels are handled separately because they fail
differently:

``prices``       A price series is genuinely point-in-time as published (splits
                 and dividends are the caveat, see ``PriceView``). Truncation at
                 T is therefore sufficient and exact.
``fundamentals`` A filing has three distinct dates — the period it describes,
                 the day it was filed, and the day the data vendor made it
                 readable. Only the last one licenses use. Yahoo's free feed
                 publishes *none* of them, so historical fundamentals are
                 reported ``CURRENT_SNAPSHOT_ONLY`` and WITHHELD from replay
                 rather than back-applied.
``macro``        FRED serves the latest revision of history, not the number
                 printed at the time. A fixed release lag prevents the crudest
                 leak (using a print before it existed) but cannot undo a
                 revision, so vintage-less series are marked
                 ``REVISED_HISTORY`` and carry a reduced evidence weight.
``universe``     Screening only names that exist today is survivorship bias.
                 Without a historical constituent file the honest output is
                 ``SURVIVORSHIP_BIAS_UNRESOLVED``, recorded on every affected
                 observation, not a silent assumption.

Nothing in this module fabricates a value it does not have.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

# --------------------------------------------------------------------------- #
# PIT quality vocabulary
# --------------------------------------------------------------------------- #
# Ordered best -> worst. The weight is how much a feature sourced this way is
# allowed to contribute to the PIT coverage score that gates calibration.
PIT_EXACT = "PIT_EXACT"                      # observed value, timestamped, unrevised
PIT_APPROXIMATE = "PIT_APPROXIMATE"          # visible-by construction (fixed release lag)
REVISED_HISTORY = "REVISED_HISTORY"          # right date, but a later revision of the value
CURRENT_SNAPSHOT_ONLY = "CURRENT_SNAPSHOT_ONLY"  # only today's value exists — unusable in the past
UNAVAILABLE = "UNAVAILABLE"                  # no value at all

PIT_STATUSES = (PIT_EXACT, PIT_APPROXIMATE, REVISED_HISTORY,
                CURRENT_SNAPSHOT_ONLY, UNAVAILABLE)

PIT_WEIGHT = {
    PIT_EXACT: 1.0,
    PIT_APPROXIMATE: 0.85,
    REVISED_HISTORY: 0.5,
    CURRENT_SNAPSHOT_ONLY: 0.0,
    UNAVAILABLE: 0.0,
}

# Coverage -> label. These thresholds also drive the calibration gate: an
# observation below MIN_CALIBRATION_COVERAGE never reaches Kelly.
PIT_QUALITY_BANDS = ((0.85, "HIGH"), (0.6, "MEDIUM"), (0.0, "LOW"))
MIN_CALIBRATION_COVERAGE = 0.6

SURVIVORSHIP_UNRESOLVED = "SURVIVORSHIP_BIAS_UNRESOLVED"
# The universe identity of a replay that resolved its names from today's
# constituent list. Every generation written before membership history
# existed was this, whether or not it said so.
SURVIVORS_ONLY_FINGERPRINT = "survivors-only"
# How a generation resolved its cross-section. The distinction that
# actually decides whether two records are comparable.
SURVIVORS_ONLY = "survivors-only"
PIT_MEMBERSHIP = "pit-membership"


def _safe_number(value):
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


class LookAheadError(RuntimeError):
    """Raised when code asks a point-in-time view for data it cannot have.

    This is deliberately an exception and not a warning: a replay that reads the
    future is not a degraded replay, it is a void one.
    """


def quality_label(coverage: float | None) -> str:
    if coverage is None:
        return "LOW"
    for floor, label in PIT_QUALITY_BANDS:
        if coverage >= floor:
            return label
    return "LOW"


# --------------------------------------------------------------------------- #
# Prices
# --------------------------------------------------------------------------- #
class PriceView:
    """Read-only price access truncated at ``as_of``.

    The view owns the truncation so callers cannot forget it. ``close`` and
    ``frame`` return copies that physically end at ``as_of``; asking for a later
    date raises rather than returning a clipped answer, because a caller that
    wanted the future has a bug and should be told.

    Adjusted-close caveat: vendor history is adjusted for splits and dividends
    known *today*, so a 2015 close read now is not byte-identical to the 2015
    print. That affects levels, not the ordering of the ratio-based features
    this pipeline uses, and it cannot import information about the future
    direction of a stock. It is recorded as ``PIT_APPROXIMATE`` rather than
    claimed as exact.
    """

    price_pit_status = PIT_APPROXIMATE

    def __init__(self, frames: dict[str, pd.DataFrame], as_of):
        self.as_of = pd.Timestamp(as_of).normalize()
        self._frames = frames or {}
        self._cache: dict[str, pd.DataFrame] = {}

    def __contains__(self, ticker: str) -> bool:
        return ticker in self._frames

    def tickers(self) -> list[str]:
        return sorted(self._frames)

    def frame(self, ticker: str) -> pd.DataFrame | None:
        if ticker in self._cache:
            return self._cache[ticker]
        raw = self._frames.get(ticker)
        if raw is None:
            return None
        cut = raw.loc[raw.index <= self.as_of]
        self._cache[ticker] = cut
        return cut

    def close(self, ticker: str) -> pd.Series | None:
        frame = self.frame(ticker)
        if frame is None or "Close" not in frame:
            return None
        return frame["Close"].dropna()

    def last_close(self, ticker: str) -> float | None:
        series = self.close(ticker)
        if series is None or series.empty:
            return None
        return float(series.iloc[-1])

    def has_history(self, ticker: str, min_rows: int) -> bool:
        frame = self.frame(ticker)
        return frame is not None and len(frame.dropna(how="all")) >= min_rows

    def require(self, date) -> None:
        """Assert that ``date`` is inside the visible window."""
        stamp = pd.Timestamp(date).normalize()
        if stamp > self.as_of:
            raise LookAheadError(
                f"point-in-time view as of {self.as_of.date()} asked for {stamp.date()}")


def assert_no_future(series_or_frame, as_of, label: str = "series") -> None:
    """Fail loudly if an index carries an observation after ``as_of``."""
    if series_or_frame is None or not len(series_or_frame):
        return
    index = getattr(series_or_frame, "index", None)
    if index is None or not len(index):
        return
    latest = pd.Timestamp(index.max())
    cutoff = pd.Timestamp(as_of).normalize()
    if latest.normalize() > cutoff:
        raise LookAheadError(f"{label} extends to {latest.date()} beyond as-of {cutoff.date()}")


# --------------------------------------------------------------------------- #
# Fundamentals
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class FundamentalRecord:
    """One filing, with its three dates kept apart on purpose.

    ``report_period``  the fiscal period the numbers describe
    ``filing_date``    the day the company filed
    ``available_from`` the day the data was actually readable by us

    Use is licensed by ``available_from`` only. A filing dated 2020-03-31 that
    a vendor published on 2020-05-14 is invisible on 2020-04-01.
    """

    ticker: str
    report_period: str
    available_from: str
    fields: dict
    report_date: str | None = None
    filing_date: str | None = None
    publication_date: str | None = None
    currency: str | None = None
    source: str | None = None
    source_as_of: str | None = None
    revision_status: str | None = None
    pit_status: str = PIT_EXACT

    def visible_on(self, as_of) -> bool:
        return pd.Timestamp(self.available_from) <= pd.Timestamp(as_of)


class FundamentalStore:
    """Publication-aware fundamentals.

    ``visible_as_of`` returns the newest record whose ``available_from`` has
    passed — never a later filing, never today's snapshot stamped with an old
    date. An empty store returns nothing and reports ``CURRENT_SNAPSHOT_ONLY``
    so the caller can decide (the replay engine's decision is: omit the value
    and let factor coverage fall).
    """

    REQUIRED_SOURCE_FIELDS = (
        "trailingPE", "forwardPE", "bookValue", "bookYield", "fcf", "fcfYield",
        "roe", "operatingMargin", "profitMargin", "debtToEquity", "earningsGrowth",
        # Per-share numerators. A filing can state these; it cannot state a
        # yield, because a yield needs a price and the price moves every day
        # after the filing. Supplying the numerator lets the consumer divide by
        # the price it is actually standing on. See PRICE_RELATIVE_NUMERATORS.
        "epsTtm", "bookValuePerShare", "fcfPerShare",
    )
    SOURCE_FIELD_ALIASES = {"FCF": "fcf", "FCFYield": "fcfYield", "ROE": "roe"}

    def __init__(self, records: dict[str, list[FundamentalRecord]] | None = None,
                 diagnostics: dict | None = None):
        self._records: dict[str, list[FundamentalRecord]] = {}
        for ticker, rows in (records or {}).items():
            self._records[ticker] = sorted(rows, key=lambda r: str(r.available_from))
        self.diagnostics = diagnostics or {
            "contract": "PIT_FUNDAMENTALS_V1", "rowsRead": len(self),
            "rowsAccepted": len(self), "rowsRejected": 0, "errors": [],
        }

    def __len__(self) -> int:
        return sum(len(v) for v in self._records.values())

    @property
    def available(self) -> bool:
        return bool(self._records)

    def tickers(self) -> list[str]:
        return sorted(self._records)

    def visible_as_of(self, ticker: str, as_of) -> tuple[dict, str]:
        """Return (fields, pit_status) for the newest visible filing."""
        rows = self._records.get(ticker)
        if not rows:
            return {}, (CURRENT_SNAPSHOT_ONLY if not self.available else UNAVAILABLE)
        cutoff = pd.Timestamp(as_of)
        visible = [r for r in rows if pd.Timestamp(r.available_from) <= cutoff]
        if not visible:
            return {}, UNAVAILABLE
        latest = visible[-1]
        return dict(latest.fields), latest.pit_status

    def snapshot(self, as_of, tickers: list[str] | None = None) -> tuple[dict[str, dict], dict[str, str]]:
        """PIT fundamentals for a whole cross-section at once."""
        names = tickers if tickers is not None else self.tickers()
        fields: dict[str, dict] = {}
        statuses: dict[str, str] = {}
        for ticker in names:
            values, status = self.visible_as_of(ticker, as_of)
            statuses[ticker] = status
            if values:
                fields[ticker] = values
        return fields, statuses

    @classmethod
    def from_jsonl(cls, path: str | Path | None) -> "FundamentalStore":
        """Load a PIT fundamentals store.

        Expected one JSON object per line following ``PIT_FUNDAMENTALS_V1``:
        ticker, fiscal/report period and date, publication/available dates,
        currency, nullable source fields, source/sourceAsOf and revisionStatus.
        A missing file is not an error — it is the current reality of the
        free-data stack, and it yields an empty store whose status is
        CURRENT_SNAPSHOT_ONLY.
        """
        if not path:
            return cls({}, {"contract": "PIT_FUNDAMENTALS_V1", "rowsRead": 0,
                            "rowsAccepted": 0, "rowsRejected": 0,
                            "errors": ["pit_fundamentals_path_not_configured"]})
        file = Path(path)
        if not file.exists():
            return cls({}, {"contract": "PIT_FUNDAMENTALS_V1", "rowsRead": 0,
                            "rowsAccepted": 0, "rowsRejected": 0,
                            "errors": ["pit_fundamentals_file_missing"]})
        grouped: dict[str, list[FundamentalRecord]] = {}
        errors = []
        rows_read = accepted = 0
        for line_number, line in enumerate(file.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            rows_read += 1
            try:
                row = json.loads(line)
            except ValueError:
                errors.append(f"line_{line_number}:invalid_json")
                continue
            ticker, available = row.get("ticker"), row.get("availableFrom")
            if not ticker or not available:
                errors.append(f"line_{line_number}:ticker_or_availableFrom_missing")
                continue
            report_period = row.get("fiscalPeriod") or row.get("reportPeriod")
            report_date = row.get("reportDate")
            publication = row.get("publicationDate") or row.get("filingDate")
            source = row.get("source")
            source_as_of = row.get("sourceAsOf")
            revision_status = row.get("revisionStatus") or row.get("revision status")
            if (not report_period or not report_date or not publication or not source
                    or not row.get("currency") or not source_as_of or not revision_status):
                errors.append(
                    f"line_{line_number}:fiscalPeriod_reportDate_publicationDate_currency_"
                    "source_sourceAsOf_or_revisionStatus_missing")
                continue
            try:
                report_stamp = pd.Timestamp(report_date)
                publication_stamp = pd.Timestamp(publication)
                available_stamp = pd.Timestamp(available)
                pd.Timestamp(source_as_of)
                if publication_stamp < report_stamp:
                    errors.append(f"line_{line_number}:publicationDate_before_reportDate")
                    continue
                if available_stamp < publication_stamp:
                    errors.append(f"line_{line_number}:availableFrom_before_publicationDate")
                    continue
            except Exception:
                errors.append(f"line_{line_number}:invalid_date")
                continue
            fields = dict(row.get("fields") or {})
            for key in cls.REQUIRED_SOURCE_FIELDS:
                if key in row and key not in fields:
                    fields[key] = row.get(key)
            for source_key, internal_key in cls.SOURCE_FIELD_ALIASES.items():
                if source_key in row and internal_key not in fields:
                    fields[internal_key] = row.get(source_key)
                if source_key in fields and internal_key not in fields:
                    fields[internal_key] = fields.pop(source_key)
            fields = {k: v for k, v in fields.items() if v is not None}
            trailing_pe = _safe_number(fields.get("trailingPE"))
            forward_pe = _safe_number(fields.get("forwardPE"))
            if trailing_pe and trailing_pe > 0 and "earningsYield" not in fields:
                fields["earningsYield"] = 1.0 / trailing_pe
            if forward_pe and forward_pe > 0 and "fwdEarningsYield" not in fields:
                fields["fwdEarningsYield"] = 1.0 / forward_pe
            grouped.setdefault(ticker, []).append(FundamentalRecord(
                ticker=ticker,
                report_period=str(report_period),
                report_date=str(report_date),
                available_from=str(available),
                filing_date=row.get("filingDate"),
                publication_date=str(publication),
                currency=row.get("currency"),
                fields=fields,
                source=source,
                source_as_of=source_as_of,
                revision_status=revision_status,
                pit_status=row.get("pitStatus") or PIT_EXACT,
            ))
            accepted += 1
        return cls(grouped, {
            "contract": "PIT_FUNDAMENTALS_V1", "rowsRead": rows_read,
            "rowsAccepted": accepted, "rowsRejected": rows_read - accepted,
            "errors": errors[:50],
            "availabilityRule": "availableFrom <= replayDate",
            "currentSnapshotBackfillAllowed": False,
            "schema": [
                "ticker", "fiscalPeriod", "reportDate", "publicationDate",
                "availableFrom", "currency", "trailingPE", "forwardPE",
                "bookValue", "bookYield", "FCF", "FCFYield", "ROE",
                "operatingMargin", "profitMargin", "debtToEquity", "earningsGrowth",
                "epsTtm", "bookValuePerShare", "fcfPerShare",
                "source", "sourceAsOf", "revisionStatus",
            ],
        })


# Yield -> the per-share numerator that produces it once divided by a price.
# The replay holds the point-in-time close; the filing holds the numerator.
# Keeping them apart until the moment of use is what makes the value sleeve
# point-in-time rather than "stale by up to a quarter".
PRICE_RELATIVE_NUMERATORS = {
    "earningsYield": "epsTtm",
    "bookYield": "bookValuePerShare",
    "fcfYield": "fcfPerShare",
}

# Production derives these from vendor ratios, and the vendor withholds a ratio
# whose denominator is non-positive: trailingPE is absent for a loss-making
# company, priceToBook for negative book value. Free cash flow carries no such
# guard and is allowed to be negative. The replay mirrors that exactly, so a
# name is scored the same way in both places rather than only in the backtest.
POSITIVE_ONLY_NUMERATORS = ("epsTtm", "bookValuePerShare")


def derive_price_relative(fields: dict, price) -> dict:
    """Fill in price-relative fields from per-share numerators and ``price``.

    An explicitly supplied yield always wins — the caller may have a vendor
    ratio that is better than anything reconstructable here. Nothing is
    derived without a usable positive price.
    """
    out = dict(fields or {})
    close = _safe_number(price)
    if not close or close <= 0:
        return out
    for yield_key, numerator_key in PRICE_RELATIVE_NUMERATORS.items():
        if out.get(yield_key) is not None:
            continue
        numerator = _safe_number(out.get(numerator_key))
        if numerator is None or numerator == 0:
            continue
        if numerator_key in POSITIVE_ONLY_NUMERATORS and numerator <= 0:
            continue
        out[yield_key] = numerator / close
    return out


# --------------------------------------------------------------------------- #
# Macro vintages
# --------------------------------------------------------------------------- #
def vintage_column(releases: pd.DataFrame, as_of) -> pd.Series:
    """One series as it stood on ``as_of``, from its release history.

    ``releases`` is long-form: ``date`` (the period being described),
    ``realtime_start`` (when that number was first published) and ``value``.
    A print is usable only once published, so releases after ``as_of`` are
    dropped before, for each period, the newest surviving print is taken.
    That is the difference between the number they had and the number we have.
    """
    if releases is None or not len(releases):
        return pd.Series(dtype=float)
    frame = releases.dropna(subset=["date", "realtime_start"]).copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["realtime_start"] = pd.to_datetime(frame["realtime_start"], errors="coerce")
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    cutoff = pd.Timestamp(as_of).normalize()
    frame = frame[(frame["realtime_start"] <= cutoff) & (frame["date"] <= cutoff)]
    frame = frame.dropna(subset=["date", "realtime_start"])
    if frame.empty:
        return pd.Series(dtype=float)
    frame = frame.sort_values(["date", "realtime_start"])
    latest = frame.groupby("date", sort=True)["value"].last()
    return latest.dropna()


class MacroVintageView:
    """Macro series with an explicit vintage claim.

    Two different things are being tracked and they must not be conflated:

    1. *Was this print public on T?* Handled by the fixed release lags already
       encoded in ``pipeline.regime``; that gets us PIT_APPROXIMATE.
    2. *Is this the number they printed, or a later revision?* Without ALFRED
       vintages the answer is "a later revision", i.e. REVISED_HISTORY. GDP and
       payrolls in particular are revised enough that a regime label built from
       revised history is easier than the one available at the time.

    A series listed in ``vintage_series`` is treated as genuinely vintaged;
    everything else degrades to REVISED_HISTORY.

    ``vintages`` supplies the evidence for that claim: one long frame per
    series with ``date`` (the period observed), ``realtime_start`` (the day
    that value was first published) and ``value``. Given it, ``as_of`` rebuilds
    each column out of the prints that had actually been published by then,
    instead of the revised series everyone can see today.
    """

    def __init__(self, macro: pd.DataFrame | None, vix: pd.Series | None = None,
                 vintage_series: set[str] | None = None,
                 vintages: dict | None = None):
        self._macro = macro
        self._vix = vix
        self._vintages = {name: frame for name, frame in (vintages or {}).items()
                          if frame is not None and len(frame)}
        # A name only counts as vintaged if releases were actually supplied for
        # it; listing it without evidence would be the over-claim this guards.
        self._vintage_series = (set(vintage_series) & set(self._vintages)
                                if vintage_series is not None
                                else set(self._vintages))

    @property
    def vintage_series(self) -> set[str]:
        return set(self._vintage_series)

    @property
    def available(self) -> bool:
        return self._macro is not None and len(self._macro) > 0

    def as_of(self, as_of) -> tuple[pd.DataFrame | None, pd.Series | None]:
        """Truncate both frames at ``as_of`` (release lags applied downstream)."""
        cutoff = pd.Timestamp(as_of).normalize()
        macro = None
        if self._macro is not None and len(self._macro):
            macro = self._macro.loc[self._macro.index <= cutoff]
            if macro.empty:
                macro = None
            elif self._vintage_series:
                macro = macro.copy()
                for name in sorted(self._vintage_series):
                    if name not in macro.columns:
                        continue
                    column = vintage_column(self._vintages[name], cutoff)
                    macro[name] = column.reindex(macro.index) if len(column) else float("nan")
        vix = None
        if self._vix is not None and len(self._vix):
            vix = self._vix.loc[self._vix.index <= cutoff]
            if vix.empty:
                vix = None
        return macro, vix

    def pit_status(self, series_name: str | None = None) -> str:
        if not self.available:
            return UNAVAILABLE
        if series_name is not None:
            return PIT_EXACT if series_name in self._vintage_series else REVISED_HISTORY
        if not self._vintage_series:
            return REVISED_HISTORY
        # The aggregate is only EXACT when nothing in the panel is still a
        # later revision. One vintaged series among many is APPROXIMATE, and
        # the integrity gate asks for EXACT.
        columns = set(self._macro.columns) if self._macro is not None else set()
        missing = columns - self._vintage_series
        return PIT_APPROXIMATE if missing else PIT_EXACT


# --------------------------------------------------------------------------- #
# Universe / survivorship
# --------------------------------------------------------------------------- #
@dataclass
class UniverseSnapshot:
    """Who was investable on a date, and how confident we are about that."""

    as_of: str
    by_region: dict[str, list[str]]
    survivorship_risk: str
    notes: list[str] = field(default_factory=list)
    reconstructed: bool = False
    # Members the membership file says were listed on this date, against those
    # we could actually price. A name that was in the index and has no price
    # history here is precisely the name survivorship bias deletes, so the two
    # counts are kept apart instead of being assumed equal.
    expected_members: int = 0
    missing_prices: list[str] = field(default_factory=list)
    # Two different gaps, kept apart because they have different causes and
    # different fixes. `missing_prices` is "the file says it was listed and we
    # could not price it". These are "the file says nothing about this name at
    # all" — a region the membership file does not cover.
    membership_known: int = 0
    membership_unknown: int = 0

    @property
    def size(self) -> int:
        return sum(len(v) for v in self.by_region.values())

    @property
    def coverage_pct(self) -> float | None:
        """Of the names the file says were listed, the share we could price."""
        if not self.reconstructed or not self.expected_members:
            return None
        return 100.0 * (self.expected_members - len(self.missing_prices)) / self.expected_members

    @property
    def membership_coverage_pct(self) -> float | None:
        """Of the cross-section, the share whose membership was actually known.

        Separate from `coverage_pct`: a file covering one region can price every
        name it knows about and still leave the other region entirely unresolved.
        """
        total = self.membership_known + self.membership_unknown
        return round(self.membership_known / total * 100, 4) if total else None


class UniverseHistory:
    """Historical membership, when it can be established.

    ``memberships`` maps ticker -> {"listed": date, "delisted": date|None,
    "region": str}. With that file a replay can include names that later died
    and exclude names that did not yet exist. Without it, a replay can only see
    names that survived to today, and every observation carries
    SURVIVORSHIP_BIAS_UNRESOLVED — recorded, never assumed away.
    """

    def __init__(self, memberships: dict[str, dict] | None = None):
        self._memberships = memberships or {}

    @property
    def available(self) -> bool:
        return bool(self._memberships)

    @property
    def memberships(self) -> dict[str, dict]:
        """Read-only view of ticker -> {listed, delisted, region}.

        The replay needs it to widen the DOWNLOAD list: `snapshot` can only put
        a former member back into the cross-section if the price panel can serve
        it, so the caller has to know which names to fetch.
        """
        return dict(self._memberships)

    @property
    def fingerprint(self) -> str:
        """Exact content hash of the universe definition. Diagnostic only.

        CI rebuilds the membership file on every replay run and the index gains
        and loses names every month, so this moves legitimately. It is recorded
        and reported; what is ENFORCED is `signature`.
        """
        if not self._memberships:
            return SURVIVORS_ONLY_FINGERPRINT
        canonical = json.dumps(
            {t: {k: row.get(k) for k in ("listed", "delisted", "region")}
             for t, row in sorted(self._memberships.items())},
            sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
        return f"pit-{len(self._memberships)}-{digest}"

    @property
    def signature(self) -> dict:
        """The universe properties a generation's records depend on.

        Adding a name to a date's cross-section re-ranks every other name on
        that date: `alphaPercentile` is a rank within the cross-section and
        selection applies a floor to it. So a record produced against 281 US
        names in 2013 and one produced against the real 500 are not the same
        measurement, and pooling them is not an extension of the evidence —
        it is a contamination of it.

        But not every change to the file is that. The index gains and loses
        members every month and the file is rebuilt on every run, so an exact
        hash would refuse the second run and every run after it. What actually
        breaks comparability is a change of KIND — survivors-only becoming
        point-in-time, a region gaining or LOSING membership coverage — so
        that is what the signature carries, with the hash alongside it as a
        recorded detail rather than a gate.
        """
        regions: dict[str, int] = {}
        for row in self._memberships.values():
            region = row.get("region")
            if region:
                regions[region] = regions.get(region, 0) + 1
        return {
            "mode": PIT_MEMBERSHIP if self._memberships else SURVIVORS_ONLY,
            "regions": dict(sorted(regions.items())),
            "fingerprint": self.fingerprint,
        }

    @classmethod
    def from_json(cls, path: str | Path | None) -> "UniverseHistory":
        if not path:
            return cls({})
        file = Path(path)
        if not file.exists():
            return cls({})
        try:
            raw = json.loads(file.read_text(encoding="utf-8"))
        except ValueError:
            return cls({})
        if not isinstance(raw, dict):
            return cls({})
        return cls({str(k): dict(v) for k, v in raw.items() if isinstance(v, dict)})

    def _listed_on(self, ticker: str, as_of: pd.Timestamp) -> bool | None:
        """True/False when membership is known, None when the file says nothing.

        The distinction is load-bearing. Returning False for an unknown ticker
        silently deletes every name the file does not cover — a US-only
        membership file empties the entire KR cross-section, and the replay
        carries on reporting a Korean sleeve made of nothing.
        """
        row = self._memberships.get(ticker)
        if not row:
            return None
        listed = row.get("listed")
        delisted = row.get("delisted")
        if listed and pd.Timestamp(listed) > as_of:
            return False
        if delisted and pd.Timestamp(delisted) <= as_of:
            return False
        return True

    def snapshot(self, as_of, current_universe: dict[str, list[str]],
                 view=None, min_history: int = 0) -> UniverseSnapshot:
        """Membership on ``as_of``.

        Even with no membership file we can remove the crudest anachronism: a
        ticker with no price history before T did not trade on T, so it is
        dropped. That is a partial fix, not a cure, and the snapshot says so.

        ``view`` is anything exposing ``has_history(ticker, min_rows)`` truncated
        at ``as_of`` — the replay engine passes a NumPy-backed probe so this stays
        cheap when called once per replay date.
        """
        cutoff = pd.Timestamp(as_of).normalize()
        notes: list[str] = []
        by_region: dict[str, list[str]] = {}
        rows = max(int(min_history or 0), 1)

        def tradable(ticker: str) -> bool:
            return view is None or bool(view.has_history(ticker, rows))

        if self.available:
            expected = 0
            missing: list[str] = []
            known = unknown = 0
            for region in sorted(current_universe):
                today = set(current_universe.get(region, []))
                members = set(today)
                members |= {t for t, row in self._memberships.items()
                            if row.get("region") == region}
                listed = []
                for ticker in sorted(members):
                    state = self._listed_on(ticker, cutoff)
                    if state is True:
                        known += 1
                    elif state is None and ticker in today:
                        # Membership unknown. Dropping it erases the name;
                        # asserting membership invents history. Keep it only
                        # because today's list proves it exists, and count it
                        # against membership coverage so the gap stays visible.
                        unknown += 1
                    else:
                        continue
                    listed.append(ticker)
                priced = [t for t in listed if tradable(t)]
                expected += len(listed)
                missing.extend(t for t in listed if t not in set(priced))
                by_region[region] = priced
            notes.append("historical_constituents_reconstructed_from_membership_file")
            # Holding a membership file is not the same as having the prices to
            # replay it. A name listed then and unpriceable now is dropped, and
            # dropping it silently would reinstate the bias the file was meant
            # to remove — under a LOW risk label, which is worse than HIGH.
            share_missing = (len(missing) / expected) if expected else 0.0
            if missing:
                notes.append("listed_members_without_price_history_excluded")
            if unknown:
                notes.append(f"membership_unknown_for_{unknown}_names_kept_from_today")
            share_unknown = (unknown / (known + unknown)) if (known + unknown) else 0.0
            # The worse of the two gaps decides. Either one alone reinstates the
            # bias the file was meant to remove, and a LOW label on that is worse
            # than an honest HIGH.
            worst = max(share_missing, share_unknown)
            risk = "LOW" if worst <= 0 else "MEDIUM" if worst < 0.05 else "HIGH"
            return UniverseSnapshot(cutoff.strftime("%Y-%m-%d"), by_region, risk, notes,
                                    True, expected, sorted(set(missing)), known, unknown)

        for region in sorted(current_universe):
            by_region[region] = sorted(t for t in current_universe.get(region, []) if tradable(t))
        notes.append(SURVIVORSHIP_UNRESOLVED)
        notes.append("names_without_price_history_before_as_of_excluded")
        return UniverseSnapshot(cutoff.strftime("%Y-%m-%d"), by_region, "HIGH", notes, False)


# --------------------------------------------------------------------------- #
# PIT quality scoring
# --------------------------------------------------------------------------- #
def coverage_score(statuses: dict[str, str], weights: dict[str, float] | None = None) -> float:
    """Weighted share of the inputs a score *actually used* that were point-in-time.

    The weighting is over sources that contributed, not over every source that
    could conceivably exist. This distinction matters and was worth getting
    right: if no fundamentals were available, the value and quality sleeves did
    not enter the alpha at all, so the alpha that came out is pure
    point-in-time price data. Scoring that as "40% PIT coverage" would be
    measuring the absence of a sleeve, not a leak.

    A missing sleeve is a real weakness — it just is not *this* weakness. It is
    already carried by ``evidenceCoverage`` on the alpha itself and by the
    ``fundamentals_not_point_in_time`` discount in
    ``historical_calibration.evidence_weight``. Charging it here as well would
    penalize the same defect three times and would leave a price-only Phase 1
    replay permanently below the calibration floor, which is exactly the
    "wait a year for new data" failure this project exists to remove.
    """
    if not statuses:
        return 0.0
    weights = weights or {}
    total = 0.0
    scored = 0.0
    for group, status in statuses.items():
        if status == UNAVAILABLE:
            continue           # did not contribute; not evidence of a leak
        w = float(weights.get(group, 1.0))
        if w <= 0:
            continue
        total += w
        scored += w * PIT_WEIGHT.get(status, 0.0)
    return round(scored / total, 4) if total else 0.0


def quality_report(statuses: dict[str, str], *, survivorship_risk: str,
                   look_ahead_passed: bool = True,
                   weights: dict[str, float] | None = None) -> dict:
    """The PIT block stamped on every replay observation."""
    coverage = coverage_score(statuses, weights)
    return {
        "pitCoverage": coverage,
        "pitQuality": quality_label(coverage),
        "lookAheadCheckPassed": bool(look_ahead_passed),
        "survivorshipRisk": survivorship_risk,
        "sourceStatus": dict(sorted(statuses.items())),
        "usableForCalibration": bool(look_ahead_passed and coverage >= MIN_CALIBRATION_COVERAGE),
    }


def usable_for_calibration(observation: dict) -> bool:
    """Gate used before an observation may influence Kelly.

    A low-PIT observation is still recorded — it is evidence about the
    machinery — but it must not price a position.
    """
    pit = (observation or {}).get("pit") or {}
    if pit.get("lookAheadCheckPassed") is False:
        return False
    if "usableForCalibration" in pit:
        return bool(pit["usableForCalibration"])
    return float(pit.get("pitCoverage") or 0.0) >= MIN_CALIBRATION_COVERAGE
