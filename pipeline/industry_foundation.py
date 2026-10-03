"""Outcome-blind membership contracts; return mathematics are synthetic-only in v1.

No price loader, target engine, model, network, or production consumer is imported.
Date-only releases become usable the NEXT calendar day. Economic intervals and
knowledge intervals are separate, so a later correction cannot rewrite an earlier
signal's peer group. Tickers are display aliases; security_id is the join key.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date
import hashlib
import json
import math
import re

VERSION = "market-industry-stock-data-foundation-v1"
SCHEMA = "PIT_INDUSTRY_MEMBERSHIP_V1"
BASES = {"PRICE_RETURN", "ADJUSTED_INDEX_RETURN_PARTIAL_DISTRIBUTIONS", "TOTAL_SHAREHOLDER_RETURN"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def day(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("INVALID_ISO_DATE")
    date.fromisoformat(value)
    return value


def _number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def _synthetic(scope):
    if scope != "SYNTHETIC":
        raise ValueError("HISTORICAL_RETURN_EXECUTION_NOT_AUTHORIZED")


@dataclass(frozen=True)
class Membership:
    security_id: str
    ticker: str
    region: str
    taxonomy_id: str
    taxonomy_version: str
    industry_id: str
    valid_from: str
    valid_to: str | None
    source_date: str
    release_date: str
    known_to: str | None
    source: str
    source_sha256: str
    evidence_kind: str
    identity_provenance: str

    def __post_init__(self):
        for key in ("security_id", "ticker", "taxonomy_id", "taxonomy_version", "industry_id",
                    "source", "identity_provenance"):
            if not isinstance(getattr(self, key), str) or not getattr(self, key).strip():
                raise ValueError("MEMBERSHIP_PROVENANCE_REQUIRED: " + key)
        if self.region not in {"KR", "US"}:
            raise ValueError("UNKNOWN_REGION")
        for key in ("valid_from", "source_date", "release_date"):
            day(getattr(self, key))
        if self.valid_to is not None and day(self.valid_to) <= self.valid_from:
            raise ValueError("INVALID_VALIDITY_INTERVAL")
        if self.known_to is not None and day(self.known_to) <= self.release_date:
            raise ValueError("INVALID_KNOWLEDGE_INTERVAL")
        if self.source_date > self.release_date:
            raise ValueError("SOURCE_DATE_AFTER_RELEASE")
        if not re.fullmatch(r"[0-9a-f]{64}", self.source_sha256):
            raise ValueError("SOURCE_DIGEST_REQUIRED")
        if self.evidence_kind not in {"DATED_ASSIGNMENT", "CURRENT_SNAPSHOT_ONLY"}:
            raise ValueError("UNSUPPORTED_CLASSIFICATION_EVIDENCE")
        if self.evidence_kind == "CURRENT_SNAPSHOT_ONLY" and self.valid_from < self.source_date:
            raise ValueError("CURRENT_CLASSIFICATION_BACKFILL_REFUSED")

    def visible(self, signal_date):
        day(signal_date)
        return (self.evidence_kind == "DATED_ASSIGNMENT"
                and self.release_date < signal_date
                and (self.known_to is None or signal_date <= self.known_to)
                and self.valid_from <= signal_date
                and (self.valid_to is None or signal_date < self.valid_to))


def verify_source(row, raw):
    if hashlib.sha256(raw).hexdigest() != row.source_sha256:
        raise ValueError("CLASSIFICATION_SOURCE_IDENTITY_CHANGED")


def membership_at(rows, security_id, signal_date, *, region, taxonomy_id, taxonomy_version):
    candidates = [r for r in rows if r.security_id == security_id and r.region == region
                  and r.taxonomy_id == taxonomy_id and r.taxonomy_version == taxonomy_version
                  and r.visible(signal_date)]
    if len(candidates) > 1:
        raise ValueError("AMBIGUOUS_PIT_MEMBERSHIP")
    return candidates[0] if candidates else None


def membership_identity(rows):
    records = [asdict(r) for r in rows]
    ordered = sorted(records, key=lambda r: json.dumps(r, sort_keys=True))
    if len({json.dumps(r, sort_keys=True) for r in records}) != len(records):
        raise ValueError("DUPLICATE_MEMBERSHIP_RECORD")
    return digest(ordered)


@dataclass(frozen=True)
class Cohort:
    region: str
    taxonomy_id: str
    taxonomy_version: str
    industry_id: str
    signal_date: str
    security_ids: tuple[str, ...]
    missing_classification: tuple[str, ...]
    membership_sha256: str
    universe_sha256: str
    minimum_constituents: int

    def __post_init__(self):
        day(self.signal_date)
        if self.region not in {"KR", "US"} or any(not value for value in (
                self.taxonomy_id, self.taxonomy_version, self.industry_id)):
            raise ValueError("INVALID_COHORT_NAMESPACE")
        if type(self.minimum_constituents) is not int or self.minimum_constituents < 2:
            raise ValueError("EXPLICIT_MINIMUM_GROUP_SIZE_REQUIRED")
        for names in (self.security_ids, self.missing_classification):
            if (not isinstance(names, tuple) or tuple(sorted(set(names))) != names
                    or any(not isinstance(n, str) or not n for n in names)):
                raise ValueError("INVALID_COHORT_SECURITY_IDENTITIES")
        if set(self.security_ids) & set(self.missing_classification):
            raise ValueError("CLASSIFIED_AND_MISSING_IDENTITY_OVERLAP")
        if any(not re.fullmatch(r"[0-9a-f]{64}", sha) for sha in (
                self.membership_sha256, self.universe_sha256)):
            raise ValueError("COHORT_INPUT_IDENTITY_REQUIRED")

    @property
    def ready(self):
        return not self.missing_classification and len(self.security_ids) >= self.minimum_constituents


def freeze_cohort(rows, universe, signal_date, *, region, taxonomy_id, taxonomy_version,
                  industry_id, minimum_constituents):
    """Freeze against the FULL caller-supplied PIT universe, including unclassified names.

    No global minimum for future statistical inference is invented here. A caller
    must specify its rule; 2 is only the mechanical minimum for a peer comparison.
    """
    day(signal_date)
    rows = tuple(rows)
    if type(minimum_constituents) is not int or minimum_constituents < 2:
        raise ValueError("EXPLICIT_MINIMUM_GROUP_SIZE_REQUIRED")
    names = tuple(sorted(universe))
    if not names or len(set(names)) != len(names) or any(not isinstance(n, str) or not n for n in names):
        raise ValueError("INVALID_FULL_PIT_UNIVERSE")
    members, missing = [], []
    for security in names:
        row = membership_at(rows, security, signal_date, region=region, taxonomy_id=taxonomy_id,
                            taxonomy_version=taxonomy_version)
        if row is None:
            missing.append(security)
        elif row.industry_id == industry_id:
            members.append(security)
    return Cohort(region, taxonomy_id, taxonomy_version, industry_id, signal_date,
                  tuple(members), tuple(missing), membership_identity(rows), digest(names), minimum_constituents)


def coverage_audit(rows, schedule, *, region, taxonomy_id, taxonomy_version):
    """Membership/count/continuity audit only. schedule maps dates to full PIT universes.

    No numeric price/return input exists. Coverage excludes NO source-universe name.
    Switching samples is reported, never used to choose a taxonomy automatically.
    """
    rows = tuple(rows)
    identity = membership_identity(rows)
    dates, previous, changes = [], {}, []
    for stamp, universe in sorted(schedule.items()):
        day(stamp)
        names = sorted(universe)
        if len(set(names)) != len(names) or not names:
            raise ValueError("INVALID_FULL_PIT_UNIVERSE")
        groups, absent, current = Counter(), [], {}
        for security in names:
            row = membership_at(rows, security, stamp, region=region, taxonomy_id=taxonomy_id,
                                taxonomy_version=taxonomy_version)
            if row is None:
                absent.append(security)
            else:
                groups[row.industry_id] += 1
                current[security] = row.industry_id
                if security in previous and previous[security] != row.industry_id:
                    changes.append({"date": stamp, "securityId": security})
        dates.append({"date": stamp, "universeCount": len(names), "classifiedCount": len(current),
                      "coverageFraction": len(current) / len(names), "missingSecurityIds": absent,
                      "groupCounts": dict(sorted(groups.items()))})
        previous = current
    return {"membershipSha256": identity,
            "scheduleSha256": digest({stamp: sorted(names) for stamp, names in schedule.items()}), "dates": dates,
            "observedAdjacentDateChanges": changes,
            "status": "DATA_FOUNDATION_REQUIRED" if not dates or any(d["missingSecurityIds"] for d in dates) else "READY",
            "taxonomyChosen": False}


@dataclass(frozen=True)
class Capitalization:
    value: float | None
    observation_date: str
    release_date: str
    currency: str
    source_sha256: str


def _weights(cohort, weighting, capitalizations, currency):
    names = cohort.security_ids
    if weighting == "EQUAL_WEIGHT":
        return {n: 1 / len(names) for n in names}, []
    if weighting != "MARKET_CAP_WEIGHT":
        raise ValueError("UNKNOWN_WEIGHTING")
    bad, values = [], {}
    for security in names:
        cap = capitalizations.get(security)
        if (not isinstance(cap, Capitalization) or not _number(cap.value) or cap.value <= 0
                or day(cap.observation_date) > cohort.signal_date
                or day(cap.release_date) >= cohort.signal_date
                or cap.observation_date > cap.release_date or cap.currency != currency
                or not re.fullmatch(r"[0-9a-f]{64}", cap.source_sha256)):
            bad.append(security)
        else:
            values[security] = cap.value
    if bad:
        return {}, bad
    total = math.fsum(values[n] for n in names)
    if not math.isfinite(total):
        return {}, list(names)
    return {n: values[n] / total for n in names}, []


@dataclass(frozen=True)
class ReturnObservation:
    value: float | None
    entry_date: str
    exit_date: str
    currency: str
    basis: str
    source_sha256: str
    terminal_status: str = "NOT_TERMINATED"
    distribution_status: str = "PARTIAL"

    def valid(self):
        return (_number(self.value) and self.value >= -1 and self.basis in BASES
                and day(self.entry_date) < day(self.exit_date)
                and self.terminal_status in {"NOT_TERMINATED", "RESOLVED"}
                and bool(self.currency) and bool(re.fullmatch(r"[0-9a-f]{64}", self.source_sha256))
                and self.distribution_status in {"PARTIAL", "COMPLETE", "EXCLUDED_PRICE_BASIS"}
                and (self.basis != "TOTAL_SHAREHOLDER_RETURN" or self.distribution_status == "COMPLETE")
                and (self.basis != "PRICE_RETURN" or self.distribution_status == "EXCLUDED_PRICE_BASIS"))


def aggregate_industry(cohort, observations, *, weighting, scope, entry_date, exit_date,
                       basis, currency, capitalizations=None):
    """One fixed-cohort buy-and-hold block. No fetching or historical execution.

    Entrants/reclassifications cannot change this cohort until the NEXT rebalance.
    An unresolved exit stays in the denominator and blocks the whole block. Exits
    resolved as cash retain cash (zero yield convention) to the exact endpoint.
    """
    _synthetic(scope)
    if day(entry_date) <= cohort.signal_date or day(exit_date) <= entry_date:
        raise ValueError("INVALID_POST_SIGNAL_INTERVAL")
    if basis not in BASES or not currency:
        raise ValueError("INVALID_RETURN_CONTRACT")
    result = {"status": "DATA_INSUFFICIENT", "return": None, "scope": scope,
              "industryId": cohort.industry_id, "signalDate": cohort.signal_date,
              "entryDate": entry_date, "exitDate": exit_date, "basis": basis, "currency": currency,
              "weighting": weighting, "constituentCount": len(cohort.security_ids),
              "missingClassification": list(cohort.missing_classification),
              "cohortSha256": digest(asdict(cohort)), "missingConstituents": [], "missingCaps": [],
              "observationSha256": None, "constituentObservationHashes": {}}
    if not cohort.ready:
        return result
    weights, bad_caps = _weights(cohort, weighting, capitalizations or {}, currency)
    result["missingCaps"] = bad_caps
    for security in cohort.security_ids:
        row = observations.get(security)
        if (not isinstance(row, ReturnObservation) or not row.valid()
                or (row.entry_date, row.exit_date, row.currency, row.basis) != (entry_date, exit_date, currency, basis)):
            result["missingConstituents"].append(security)
    if bad_caps or result["missingConstituents"]:
        return result
    value = math.fsum(weights[n] * observations[n].value for n in cohort.security_ids)
    result.update(status="READY", **{"return": value},
                  observationSha256=digest({n: asdict(observations[n]) for n in cohort.security_ids}),
                  constituentObservationHashes={n: digest(asdict(observations[n])) for n in cohort.security_ids})
    return result


def decompose(cohort, stock_id, stock, industry, market, *, scope):
    """Exact arithmetic gaps for the SAME endpoints, currency and return definition."""
    _synthetic(scope)
    if stock_id not in cohort.security_ids or not cohort.ready:
        raise ValueError("STOCK_NOT_IN_SIGNAL_DATE_INDUSTRY")
    if industry.get("scope") != scope or industry.get("cohortSha256") != digest(asdict(cohort)):
        raise ValueError("INDUSTRY_COHORT_IDENTITY_CHANGED")
    if not isinstance(stock, ReturnObservation) or not isinstance(market, ReturnObservation):
        raise ValueError("RETURN_OBSERVATION_REQUIRED")
    if not stock.valid() or not market.valid() or industry.get("status") != "READY" or not _number(industry.get("return")):
        return {"status": "DATA_INSUFFICIENT", "components": None}
    if industry.get("constituentObservationHashes", {}).get(stock_id) != digest(asdict(stock)):
        raise ValueError("STOCK_OBSERVATION_IDENTITY_CHANGED")
    fields = ("entry_date", "exit_date", "currency", "basis")
    key = tuple(getattr(stock, n) for n in fields)
    if key != tuple(getattr(market, n) for n in fields) or key != tuple(
            industry.get(n) for n in ("entryDate", "exitDate", "currency", "basis")):
        raise ValueError("RETURN_CONTRACT_MISMATCH")
    if stock.entry_date <= cohort.signal_date:
        raise ValueError("INVALID_POST_SIGNAL_INTERVAL")
    rs, ri, rm = stock.value, industry["return"], market.value
    return {"status": "READY", "scope": scope, "industryId": cohort.industry_id,
            "cohortSha256": digest(asdict(cohort)),
            "components": {"market_return": rm, "industry_excess_return": ri - rm,
                           "stock_within_industry_return": rs - ri,
                           "stock_market_relative_return": rs - rm},
            "selfInclusion": "FULL_INDUSTRY_INCLUDES_SUBJECT; not a leave-one-out causal residual"}
