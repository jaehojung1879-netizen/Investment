"""Research-only, daily PIT accounting features; no prices, labels or production hooks.

Raw Finnhub cash-flow statements are fiscal YTD. Validated scalar inputs are
transported through finnhub_derive.trailing_twelve_months, without changing its
registry. Different accounting concepts are never substituted across a chain.
Date-only availability is strictly BEFORE the signal day, including acceptance
date when supplied. Amendments replace a period only after becoming observable.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime
from enum import Enum
from typing import Iterable, Mapping

from pipeline import finnhub_derive as FD
from pipeline import finnhub_fundamentals as FF

FEATURE_VERSION = "US_SHAREHOLDER_DISTRIBUTION_V1"
SOURCE = "finnhub/financials-reported"


class State(str, Enum):
    VALID = "VALID"
    ZERO = "REPORTED_ZERO"
    NOT_REPORTED = "NOT_REPORTED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    INVALID = "INVALID"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    AMBIGUOUS = "AMBIGUOUS_ACCOUNTING"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class SharesBasisEvidence:
    prior_filing_id: str
    current_filing_id: str
    available_from: str
    description: str


@dataclass(frozen=True)
class SourceMetadata:
    """Caller-attested source contract, never a permission to infer missing facts.

    snapshot_id identifies the input snapshot. cumulative_evidence must name
    input-only evidence for fiscal-YTD semantics. A shares_basis_evidence entry
    must attest both period-end context and split/class comparability for THIS
    ticker and the exact pair of filing IDs; it is absent in the raw store.
    """
    source: str
    snapshot_id: str
    cumulative_evidence: str
    currency: str = "USD"
    cash_flow_convention: str = "FISCAL_YTD"
    shares_basis_evidence: tuple[SharesBasisEvidence, ...] = ()
    unverified_flow_concepts: tuple[str, ...] = ()


# Inventory includes related concepts that deliberately DO NOT act as aliases.
CONCEPT_FAMILIES = {
    "cashDividends": ("PaymentsOfDividendsCommonStock", "PaymentsOfDividends",
                      "PaymentsOfOrdinaryDividends", "PaymentsOfDividendsPreferredStockAndPreferenceStock"),
    "repurchases": ("PaymentsForRepurchaseOfCommonStock",),
    "shares": ("CommonStockSharesOutstanding", "EntityCommonStockSharesOutstanding",
               "WeightedAverageNumberOfDilutedSharesOutstanding",
               "WeightedAverageNumberOfSharesOutstandingBasic", "WeightedAverageNumberOfBasicSharesOutstanding"),
    "ocf": ("NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"),
    "capex": ("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets",
              "PaymentsForCapitalImprovements", "PaymentsToAcquireOtherPropertyPlantAndEquipment"),
    "cash": ("CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
             "RestrictedCashAndCashEquivalentsAtCarryingValue", "ShortTermInvestments"),
    "dividendPerShare": ("CommonStockDividendsPerShareDeclared", "CommonStockDividendsPerShareCashPaid"),
}
FLOW_CONCEPTS = {
    "cashDividendsPaidTTM": "PaymentsOfDividendsCommonStock",
    "commonStockRepurchasesTTM": "PaymentsForRepurchaseOfCommonStock",
    "operatingCashFlowTTM": "NetCashProvidedByUsedInOperatingActivities",
    "capitalExpendituresTTM": "PaymentsToAcquirePropertyPlantAndEquipment",
}
FEATURE_NAMES = (*FLOW_CONCEPTS, "cashDividendsPaidTTMChangeYoY", "repurchasesTTMChangeYoY",
                 "totalCashDistributionTTM", "totalCashDistributionChangeYoY", "distributionToOCF",
                 "distributionCoverageByOCF", "cashAndCashEquivalents", "sharesOutstandingChangeYoY",
                 "shareCountReductionIndicator")
FEATURE_UNITS = {name: "USD" if name in FLOW_CONCEPTS or name in {"totalCashDistributionTTM", "cashAndCashEquivalents"}
                 else "boolean" if name == "shareCountReductionIndicator" else "ratio" for name in FEATURE_NAMES}
_WANTED = {c for family in CONCEPT_FAMILIES.values() for c in family}
_ANCHORS = {c for cs in FF.UNIT_ANCHORS.values() for c in cs}
_HEADERS = ("id", "ticker", "source", "fiscalYear", "fiscalQuarter", "form", "periodStart",
            "periodEnd", "periodDays", "availableFrom", "acceptedDate")


def canonical_digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def parse_day(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


@dataclass(frozen=True)
class InputValue:
    filing_id: str
    source: str
    available_from: str
    accepted_at: str | None
    research_observed_at: str | None
    fiscal_year: int
    stage: str
    period_start: str
    period_end: str
    concept: str
    section: str
    unit: str | None
    value: float | None
    state: State
    reason: str | None = None


@dataclass(frozen=True)
class Feature:
    value: float | bool | None
    state: State
    unit: str
    basis: str
    inputs: tuple[InputValue, ...] = ()
    reason: str | None = None
    quality_evidence: tuple[SharesBasisEvidence, ...] = ()


@dataclass(frozen=True)
class FeatureSnapshot:
    ticker: str
    as_of: str
    feature_version: str
    source_metadata: SourceMetadata
    report_period: str | None
    features: Mapping[str, Feature]
    quality_warnings: tuple[str, ...]
    feature_digest: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class _Filing:
    raw: dict
    visible_day: date
    acceptance: str
    year: int | None
    stage: str | None
    error: str | None
    fingerprint: str
    scalars: Mapping[tuple[str, str], InputValue]


def _read_scalar(raw: dict, year: int, stage: str, section: str, concept: str,
                 resolved: dict) -> InputValue:
    entries = [e for e in raw["statements"].get(section, [])
               if FF.strip_namespace(e.get("concept")) == concept]
    base = dict(filing_id=str(raw["id"]), source=raw["source"], available_from=raw["availableFrom"],
                accepted_at=raw.get("acceptedDate") or None, research_observed_at=raw.get("collectedAt"),
                fiscal_year=year, stage=stage, period_start=raw["periodStart"], period_end=raw["periodEnd"],
                concept=concept, section=section)
    if not entries:
        return InputValue(**base, unit=None, value=None, state=State.NOT_REPORTED, reason="CONCEPT_NOT_REPORTED")
    expected = FF.SHARES if concept == "CommonStockSharesOutstanding" else FF.CURRENCY
    signatures = {(str(e.get("unit") or ""), str(e.get("value"))) for e in entries}
    unit = str(entries[0].get("unit") or "")
    if len(signatures) > 1:
        return InputValue(**base, unit=None, value=None, state=State.AMBIGUOUS, reason="CONFLICTING_CONCEPT_ROWS")
    value = entries[0].get("value")
    # Use the existing filing-local unit resolver; unlike value_class, a share
    # tag does not override an explicitly incompatible currency/per-share unit.
    words = set(FF.unit_words(unit))
    if (resolved.get(unit, FF.UNCLASSIFIED) != expected
            or words & {"eur", "gbp", "jpy", "cad", "aud", "cny", "krw", "million", "millions", "thousand", "thousands"}):
        return InputValue(**base, unit=unit, value=None, state=State.INVALID, reason="INVALID_OR_UNRESOLVED_UNIT")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return InputValue(**base, unit=unit, value=None, state=State.INVALID, reason="INVALID_NUMBER")
    value = float(value)
    if (concept != "NetCashProvidedByUsedInOperatingActivities" and value < 0) or (expected == FF.SHARES and value <= 0):
        return InputValue(**base, unit=unit, value=None, state=State.INVALID, reason="INVALID_SIGN_OR_SHARE_COUNT")
    return InputValue(**base, unit=unit, value=value, state=State.ZERO if value == 0 else State.VALID)


def _prepare(raw_input: Mapping) -> _Filing | None:
    # Explicit projection: unknown fields, including any label/return keys, are
    # neither read nor hashed. No filesystem or source fetch belongs here.
    raw = {k: raw_input.get(k) for k in _HEADERS}
    available = parse_day(raw["availableFrom"])
    if available is None:
        return None  # undated rows cannot license a historical observation
    accepted = raw.get("acceptedDate")
    acceptance, error = "", None
    if accepted:
        try:
            acceptance = datetime.fromisoformat(accepted.replace("Z", "+00:00")).isoformat()
        except (ValueError, AttributeError):
            error = "INVALID_ACCEPTANCE_TIMESTAMP"
    accepted_day = parse_day(acceptance)
    visible = max(available, accepted_day) if accepted_day else available
    start, end = parse_day(raw["periodStart"]), parse_day(raw["periodEnd"])
    year = raw["fiscalYear"]
    stage = FF.quarter_stage(raw) if isinstance(raw["periodDays"], (int, float)) else None
    quarter = raw["fiscalQuarter"]
    if isinstance(year, bool) or not isinstance(year, int) or not 1990 <= year <= 2100:
        year = None
    if (year is None
            or not stage or not start or not end or not raw["id"]):
        error = error or "INVALID_FISCAL_IDENTITY"
    elif (abs((end - start).days - raw["periodDays"]) > 1 or start >= end or end > available
          or (accepted_day is not None and accepted_day < end)
          or quarter != (0 if stage == FF.FY else FD.STAGE_ORDER[stage])
          or str(raw["form"]).removesuffix("/A") != ("10-K" if stage == FF.FY else "10-Q")):
        error = error or "INCOMPATIBLE_PERIOD_METADATA"
    raw["collectedAt"] = raw_input.get("collectedAt")
    raw["statements"] = {s: [{k: e.get(k) for k in ("concept", "unit", "value")}
                             for e in (raw_input.get("statements") or {}).get(s, [])
                             if FF.strip_namespace(e.get("concept")) in _WANTED
                             or FF.strip_namespace(e.get("concept")) in _ANCHORS]
                         for s in ("cf", "bs", "ic")}
    # Collection clock is observation metadata, not an amendment ordering key.
    identity = {k: raw[k] for k in _HEADERS}
    identity["statements"] = {s: sorted((str(e.get("concept")), str(e.get("unit")), str(e.get("value")))
                                         for e in rows) for s, rows in raw["statements"].items()}
    fingerprint = canonical_digest(identity)
    scalars = {}
    if error is None:
        resolved = FF.resolve_units(raw)
        for section, concept in [("cf", c) for c in FLOW_CONCEPTS.values()] + [
                ("bs", "CommonStockSharesOutstanding"), ("bs", "CashAndCashEquivalentsAtCarryingValue")]:
            scalars[section, concept] = _read_scalar(raw, year, stage, section, concept, resolved)
    return _Filing(raw, visible, acceptance, year, stage, error, fingerprint, scalars)


def _missing(state: State, reason: str, unit="USD", inputs=(), basis="UNAVAILABLE") -> Feature:
    return Feature(None, state, unit, basis, tuple(inputs), reason)


def _invalid_input(filing: _Filing, section: str, concept: str) -> InputValue:
    raw = filing.raw
    return InputValue(str(raw["id"]), str(raw["source"]), raw["availableFrom"], raw.get("acceptedDate"),
                      raw.get("collectedAt"), filing.year, filing.stage, raw.get("periodStart") or "",
                      raw.get("periodEnd") or "", concept, section, None, None, State.INVALID,
                      filing.error or "SOURCE_IDENTITY_MISMATCH")


def _number(value: float | bool, unit: str, basis: str, inputs: Iterable[InputValue]) -> Feature:
    if isinstance(value, float) and not math.isfinite(value):
        return _missing(State.INVALID, "NONFINITE_DERIVATION", unit, inputs, basis)
    return Feature(value, State.ZERO if value == 0 else State.VALID, unit, basis, tuple(inputs))


def _combine(a: Feature, b: Feature, operation: str) -> Feature:
    inputs = a.inputs + b.inputs
    for item in (a, b):
        if item.value is None:
            return _missing(item.state, item.reason or "MISSING_COMPONENT", "ratio" if operation != "sum" else "USD", inputs)
    if operation == "sum":
        return _number(a.value + b.value, "USD", "COMMON_DIVIDENDS_PLUS_EXECUTED_COMMON_REPURCHASES", inputs)
    if b.value <= 0:
        return _missing(State.NOT_APPLICABLE, "NONPOSITIVE_DENOMINATOR", "ratio", inputs)
    value = a.value / b.value if operation == "ratio" else (a.value - b.value) / b.value
    return _number(value, "ratio", "RATIO" if operation == "ratio" else "MATCHED_FISCAL_STAGE_YOY", inputs)


class FeatureEngine:
    """Prepare immutable scalar copies once; resolve visibility afresh per query."""
    def __init__(self, ticker: str, filings: Iterable[Mapping], metadata: SourceMetadata):
        if metadata.source != SOURCE or metadata.currency != "USD" or not metadata.snapshot_id:
            raise ValueError("explicit Finnhub USD snapshot metadata is required")
        self.ticker, self.metadata = ticker, metadata
        self._filings = tuple(p for r in filings if r.get("ticker") == ticker
                              if (p := _prepare(r)) is not None)

    def _index(self, cutoff: date) -> dict[tuple[int, str], _Filing]:
        visible = [r for r in self._filings if r.visible_day < cutoff]
        by_id: dict[str, list[_Filing]] = {}
        for filing in visible:
            by_id.setdefault(filing.raw["id"], []).append(filing)
        groups: dict[tuple[int, str], list[_Filing]] = {}
        for rows in by_id.values():
            # Exact duplicate records are idempotent. Conflicting copies of one
            # source ID are refused, never resolved by input order.
            conflict = len({r.fingerprint for r in rows}) > 1
            for filing in sorted(rows, key=lambda r: (r.visible_day, r.acceptance, r.fingerprint)):
                if filing.year is None or filing.stage is None:
                    continue
                if conflict:
                    filing = replace(filing, error="CONFLICTING_SOURCE_ID")
                groups.setdefault((filing.year, filing.stage), []).append(filing)
        index = {}
        for key, rows in groups.items():
            latest_day = max(r.visible_day for r in rows)
            same_day = [r for r in rows if r.visible_day == latest_day]
            latest = max((r.visible_day, r.acceptance) for r in rows)
            candidates = [r for r in rows if (r.visible_day, r.acceptance) == latest]
            selected = min(candidates, key=lambda r: (r.raw["id"], r.fingerprint, str(r.raw.get("collectedAt") or "")))
            if len({r.fingerprint for r in candidates}) > 1:
                selected = replace(selected, error="AMBIGUOUS_SAME_TIME_FILINGS")
            if len({r.fingerprint for r in same_day}) > 1 and any(not r.acceptance for r in same_day):
                selected = replace(selected, error="AMBIGUOUS_SAME_DAY_ACCEPTANCE_ORDER")
            if len({(r.raw["periodStart"], r.raw["periodEnd"]) for r in rows}) > 1:
                selected = replace(selected, error="CONFLICTING_FISCAL_PERIODS")
            index[key] = selected
        return index

    def _ttm(self, index: dict, year: int, stage: str, concept: str) -> Feature:
        keys = [(year, stage)] if stage == FF.FY else [(year, stage), (year - 1, FF.FY), (year - 1, stage)]
        terms, inputs = {}, []
        for key in keys:
            filing = index.get(key)
            if filing is None:
                return _missing(State.INSUFFICIENT_HISTORY, "MISSING_FISCAL_CHAIN", inputs=inputs)
            if filing.error or filing.raw["source"] != self.metadata.source:
                return _missing(State.INVALID, filing.error or "SOURCE_IDENTITY_MISMATCH",
                                inputs=[*inputs, _invalid_input(filing, "cf", concept)])
            scalar = filing.scalars["cf", concept]
            inputs.append(scalar)
            if scalar.value is None:
                related = {FF.strip_namespace(e.get("concept")) for e in filing.raw["statements"]["cf"]}
                alternatives = set(CONCEPT_FAMILIES["cashDividends" if concept == FLOW_CONCEPTS["cashDividendsPaidTTM"]
                                                   else "ocf" if concept == FLOW_CONCEPTS["operatingCashFlowTTM"]
                                                   else "capex" if concept == FLOW_CONCEPTS["capitalExpendituresTTM"]
                                                   else "repurchases"]) - {concept}
                if scalar.state == State.NOT_REPORTED and related & alternatives:
                    return _missing(State.AMBIGUOUS, "RELATED_CONCEPT_IS_NOT_AN_ALIAS", inputs=inputs)
                return _missing(scalar.state, scalar.reason, inputs=inputs)
            terms[key] = {"statements": {"cf": [{"concept": "NetCashProvidedByUsedInOperatingActivities",
                                                 "unit": "usd", "value": scalar.value}]}}
        current = index[year, stage]
        if (self.metadata.cash_flow_convention != "FISCAL_YTD" or not self.metadata.cumulative_evidence
                or concept in self.metadata.unverified_flow_concepts):
            return _missing(State.BLOCKED, "UNVERIFIED_CUMULATIVE_CONVENTION", inputs=inputs)
        if stage == FF.FY and not 350 <= current.raw["periodDays"] <= 380:
            return _missing(State.INVALID, "TRANSITION_ANNUAL_PERIOD", inputs=inputs)
        if stage != FF.FY:
            prior, annual = index[year - 1, stage], index[year - 1, FF.FY]
            if (not 350 <= annual.raw["periodDays"] <= 380
                    or abs((parse_day(current.raw["periodStart"]) - parse_day(annual.raw["periodEnd"])).days - 1) > 7
                    or abs((parse_day(prior.raw["periodStart"]) - parse_day(annual.raw["periodStart"])).days) > 7
                    or not 350 <= (parse_day(current.raw["periodEnd"]) - parse_day(prior.raw["periodEnd"])).days <= 380
                    or abs(current.raw["periodDays"] - prior.raw["periodDays"]) > 14):
                return _missing(State.INVALID, "INCOMPATIBLE_FISCAL_CHAIN", inputs=inputs)
        # Reuse the proven arithmetic, with a local scalar transport. No global
        # FLOWS mutation and no duplicate cumulative-quarter formula.
        value, basis = FD.trailing_twelve_months(terms, year, stage, "operatingCashFlow")
        if concept != FLOW_CONCEPTS["operatingCashFlowTTM"] and value < 0:
            return _missing(State.INVALID, "NEGATIVE_OUTFLOW_TTM", inputs=inputs, basis=basis)
        return _number(value, "USD", basis, inputs)

    def _yoy(self, current: Feature, prior: Feature) -> Feature:
        if current.value is not None and prior.value is not None:
            a, b = current.inputs[0], prior.inputs[0]
            if (not 350 <= (parse_day(a.period_end) - parse_day(b.period_end)).days <= 380
                    or abs((parse_day(a.period_end) - parse_day(a.period_start)).days
                           - (parse_day(b.period_end) - parse_day(b.period_start)).days) > 14
                    or (a.stage == FF.FY and abs((parse_day(a.period_start) - parse_day(b.period_end)).days - 1) > 7)):
                return _missing(State.INVALID, "INCOMPATIBLE_YOY_PERIODS", "ratio", current.inputs + prior.inputs)
        return _combine(current, prior, "growth")

    def as_of(self, as_of: str) -> FeatureSnapshot:
        cutoff = parse_day(as_of)
        if cutoff is None or as_of != cutoff.isoformat():
            raise ValueError("as_of must be an ISO calendar date")
        index = self._index(cutoff)
        features = {name: _missing(State.INSUFFICIENT_HISTORY, "NO_VISIBLE_FILING", FEATURE_UNITS[name]) for name in FEATURE_NAMES}
        period = None
        warnings = ["VENDOR_FLATTENED_CONTEXTS_NOT_INDEPENDENTLY_RECONCILED", "NO_DATED_SECTOR_CLASSIFICATION"]
        if index:
            year, stage = max(index, key=lambda k: (parse_day(index[k].raw["periodEnd"]) or date.min, k[0], FD.STAGE_ORDER[k[1]]))
            period = f"{year}-{stage}"
            current = index[year, stage]
            if (cutoff - (parse_day(current.raw["periodEnd"]) or date.min)).days > 180:
                warnings.append("STALE_REPORT_PERIOD_OVER_180_DAYS")
            for name, concept in FLOW_CONCEPTS.items():
                features[name] = self._ttm(index, year, stage, concept)
            for level, change in (("cashDividendsPaidTTM", "cashDividendsPaidTTMChangeYoY"),
                                  ("commonStockRepurchasesTTM", "repurchasesTTMChangeYoY")):
                prior = self._ttm(index, year - 1, stage, FLOW_CONCEPTS[level])
                features[change] = self._yoy(features[level], prior)
            distribution = _combine(features["cashDividendsPaidTTM"], features["commonStockRepurchasesTTM"], "sum")
            prior_distribution = _combine(self._ttm(index, year - 1, stage, FLOW_CONCEPTS["cashDividendsPaidTTM"]),
                                          self._ttm(index, year - 1, stage, FLOW_CONCEPTS["commonStockRepurchasesTTM"]), "sum")
            features["totalCashDistributionTTM"] = distribution
            features["totalCashDistributionChangeYoY"] = self._yoy(distribution, prior_distribution)
            features["distributionToOCF"] = _combine(distribution, features["operatingCashFlowTTM"], "ratio")
            ocf = features["operatingCashFlowTTM"]
            features["distributionCoverageByOCF"] = (_combine(ocf, distribution, "ratio")
                                                    if ocf.value is None or ocf.value > 0 or distribution.value is None else
                                                    _missing(State.NOT_APPLICABLE, "NONPOSITIVE_OCF", "ratio", ocf.inputs + distribution.inputs))
            cash = (current.scalars.get(("bs", "CashAndCashEquivalentsAtCarryingValue"))
                    if current.raw["source"] == self.metadata.source else None)
            features["cashAndCashEquivalents"] = (
                _number(cash.value, "USD", "PERIOD_END_LEVEL", [cash]) if cash and cash.value is not None
                else _missing(cash.state, cash.reason, inputs=[cash]) if cash
                else _missing(State.INVALID, current.error or "SOURCE_IDENTITY_MISMATCH",
                              inputs=[_invalid_input(current, "bs", "CashAndCashEquivalentsAtCarryingValue")]))
            prior = index.get((year - 1, stage))
            pair = (prior.raw["id"], current.raw["id"]) if prior else None
            proof = next((e for e in self.metadata.shares_basis_evidence
                          if (e.prior_filing_id, e.current_filing_id) == pair and e.description
                          and parse_day(e.available_from) is not None and parse_day(e.available_from) < cutoff), None)
            share_inputs = [r.scalars.get(("bs", "CommonStockSharesOutstanding"))
                            or _invalid_input(r, "bs", "CommonStockSharesOutstanding") for r in (current, prior) if r]
            share = _missing(State.BLOCKED, "SHARE_PERIOD_CONTEXT_SPLIT_AND_CLASS_BASIS_UNVERIFIED", "ratio", share_inputs)
            if proof and prior and not current.error and not prior.error and current.raw["source"] == prior.raw["source"] == self.metadata.source:
                a, b = current.scalars["bs", "CommonStockSharesOutstanding"], prior.scalars["bs", "CommonStockSharesOutstanding"]
                if not 350 <= (parse_day(a.period_end) - parse_day(b.period_end)).days <= 380:
                    share = _missing(State.INVALID, "INCOMPATIBLE_SHARE_PERIODS", "ratio", [a, b])
                else:
                    left = _number(a.value, "shares", "VERIFIED_PERIOD_END", [a]) if a.value is not None else _missing(a.state, a.reason, "shares", [a])
                    right = _number(b.value, "shares", "VERIFIED_PERIOD_END", [b]) if b.value is not None else _missing(b.state, b.reason, "shares", [b])
                    share = _combine(left, right, "growth")
                    share = replace(share, quality_evidence=(proof,))
            features["sharesOutstandingChangeYoY"] = share
            features["shareCountReductionIndicator"] = (
                replace(_number(share.value < 0, "boolean", "VERIFIED_SHARE_COUNT_CHANGE_LT_ZERO", share.inputs),
                        quality_evidence=share.quality_evidence)
                if share.value is not None else replace(share, unit="boolean"))
        else:
            warnings.append("NO_DATED_USABLE_FILING_VISIBLE")
        # Physical snapshot identity is provenance, not a feature definition:
        # appending future filings in a new snapshot must not alter the digest.
        contract = asdict(self.metadata)
        contract.pop("snapshot_id")
        contract.pop("shares_basis_evidence")
        contract["unverified_flow_concepts"] = sorted(set(contract["unverified_flow_concepts"]))
        body = dict(ticker=self.ticker, as_of=as_of, feature_version=FEATURE_VERSION,
                    source_contract=contract, report_period=period,
                    features={k: asdict(v) for k, v in features.items()}, quality_warnings=sorted(warnings))
        return FeatureSnapshot(self.ticker, as_of, FEATURE_VERSION, self.metadata, period,
                               features, tuple(sorted(warnings)), canonical_digest(body))


def derive_features(ticker: str, as_of: str, filings: Iterable[Mapping], metadata: SourceMetadata) -> FeatureSnapshot:
    return FeatureEngine(ticker, filings, metadata).as_of(as_of)
