"""Outcome-free research contracts. No executor, price loader, learner or writer.

Study definitions remain owned by the Strategy Research Blueprint. This module
only validates information boundaries and references shared by A/B/C.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
import re

from . import industry_foundation as IF
from . import prospective_receipt_core as PRC

VERSION = "EXPERIMENT_WORKBENCH_FOUNDATION_V1"
HORIZONS = (63, 126, 252)
FAMILIES = {"price", "financial", "risk", "industry", "macro"}
MISSING = {"NO_SOURCE", "NOT_PUBLIC", "NOT_OBSERVED", "NOT_STATED", "STALE",
           "INCOMPLETE_CHAIN", "INVALID_DENOMINATOR", "IDENTITY_UNRESOLVED",
           "VINTAGE_UNRESOLVED", "BASIS_UNRESOLVED", "SOURCE_BLOCKED"}


def _sha(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("SHA256_REQUIRED")
    return value


def _utc(value):
    if value is None:
        raise ValueError("TIMESTAMP_REQUIRED")
    return PRC.utc(value)


@dataclass(frozen=True)
class Key:
    market: str
    signal_date: str
    security_identity: str

    def __post_init__(self):
        IF.day(self.signal_date)
        if self.market not in {"KR", "US"} or not self.security_identity:
            raise ValueError("SECURITY_KEY_REQUIRED")

    @property
    def sample_id(self):
        return IF.digest(asdict(self))


@dataclass(frozen=True)
class Source:
    reference: str               # pinned commit:path or content-addressed reference
    sha256: str
    vintage: str
    observed_at: str | None
    observation_gap: str | None  # collection time absent is an explicit fact

    def __post_init__(self):
        _sha(self.sha256)
        if not self.reference or not self.vintage:
            raise ValueError("SOURCE_VERSION_REQUIRED")
        if self.observed_at is None:
            if self.observation_gap != "NOT_RETAINED":
                raise ValueError("OBSERVATION_TIME_OR_GAP_REQUIRED")
        else:
            _utc(self.observed_at)
            if self.observation_gap is not None:
                raise ValueError("OBSERVATION_TIME_GAP_CONFLICT")


@dataclass(frozen=True)
class Cell:
    name: str                    # family.canonicalField; no targets or forecasts
    value: float | None
    unit: str
    available_at: str | None     # latest PUBLIC availability of every dependency
    source: Source
    missing_reason: str | None = None

    def __post_init__(self):
        if not isinstance(self.source, Source):
            raise ValueError("FEATURE_SOURCE_REQUIRED")
        if self.name.split(".")[0] not in FAMILIES or not self.unit:
            raise ValueError("FEATURE_DEFINITION_REQUIRED")
        PRC.scan_for_outcome_keys({self.name: self.value})
        if re.search(r"winner|target|prediction|(?:^|[._])h(?:63|126|252)(?:$|[._])", self.name, re.I):
            raise ValueError("OUTCOME_IN_FEATURES")
        if self.value is None:
            if self.missing_reason not in MISSING:
                raise ValueError("MISSING_REASON_REQUIRED")
        elif not PRC.finite(self.value) or self.missing_reason is not None:
            raise ValueError("INVALID_FEATURE_VALUE")
        if self.value is not None:
            _utc(self.available_at)


@dataclass(frozen=True)
class Observation:
    key: Key
    ticker: str
    issuer_id: str | None
    identity_status: str
    signal_at: str
    knowledge_policy: str        # PUBLIC_RECONSTRUCTION vs OBSERVED_PROSPECTIVE
    universe_source: Source
    universe_available_at: str
    investable: bool | None
    eligibility_reason: str | None
    industry_id: str | None
    industry_status: str         # DATED / RECONSTRUCTED / UNRESOLVED
    cells: tuple[Cell, ...]

    def __post_init__(self):
        if not isinstance(self.key, Key) or not isinstance(self.universe_source, Source):
            raise ValueError("OBSERVATION_PROVENANCE_REQUIRED")
        at = _utc(self.signal_at)
        tz = "Asia/Seoul" if self.key.market == "KR" else "America/New_York"
        if str(at.tz_convert(tz).date()) != self.key.signal_date:
            raise ValueError("SIGNAL_DATE_TIMESTAMP_MISMATCH")
        if self.knowledge_policy not in {"PUBLIC_RECONSTRUCTION", "OBSERVED_PROSPECTIVE"}:
            raise ValueError("KNOWLEDGE_POLICY_REQUIRED")
        if self.identity_status not in {"VERIFIED_SECURITY", "PROVISIONAL", "UNRESOLVED"}:
            raise ValueError("IDENTITY_STATUS_REQUIRED")
        if not self.ticker or (self.investable is not True and not self.eligibility_reason):
            raise ValueError("ELIGIBILITY_REASON_REQUIRED")
        if self.investable is not None and type(self.investable) is not bool:
            raise ValueError("INVALID_ELIGIBILITY")
        if self.industry_status not in {"DATED", "RECONSTRUCTED", "UNRESOLVED"}:
            raise ValueError("INDUSTRY_STATUS_REQUIRED")
        if (self.industry_id is None) != (self.industry_status == "UNRESOLVED"):
            raise ValueError("INDUSTRY_ABSENCE_MISMATCH")
        if not isinstance(self.cells, tuple) or len({c.name for c in self.cells}) != len(self.cells):
            raise ValueError("DUPLICATE_OR_MUTABLE_FEATURE_COLLECTION")
        if _utc(self.universe_available_at) > at:
            raise ValueError("UNIVERSE_NOT_PUBLIC")
        used = [self.universe_source]
        for cell in self.cells:
            if cell.value is not None:
                if _utc(cell.available_at) > at:
                    raise ValueError("FEATURE_NOT_PUBLIC")
                used.append(cell.source)
        if self.knowledge_policy == "OBSERVED_PROSPECTIVE":
            if any(s.observed_at is None or _utc(s.observed_at) > at for s in used):
                raise ValueError("SOURCE_NOT_OBSERVED_AT_SIGNAL")


def sample_identity(rows):
    """One explicit cross-section for A/B/C, including missing and ineligible rows."""
    keys = [r.key.sample_id for r in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("DUPLICATE_OBSERVATION_KEY")
    return IF.digest(sorted(keys))


@dataclass(frozen=True)
class Economics:
    """Evaluation prerequisites; the existing cost/benchmark engines do arithmetic."""
    market: str
    benchmark: str
    stock_return_definition: str
    benchmark_return_definition: str
    benchmark_verification: str
    cost_policy: Source
    cash_rate: Source | None

    def __post_init__(self):
        if not isinstance(self.cost_policy, Source) or (self.cash_rate is not None and not isinstance(self.cash_rate, Source)):
            raise ValueError("ECONOMIC_SOURCE_REQUIRED")
        if self.benchmark != {"KR": "069500.KS", "US": "SPY"}.get(self.market):
            raise ValueError("WRONG_MARKET_BENCHMARK")
        if not self.stock_return_definition or not self.benchmark_return_definition:
            raise ValueError("ECONOMIC_RETURN_DEFINITION_REQUIRED")
        if self.benchmark_verification not in {"VERIFIED", "UNRESOLVED"}:
            raise ValueError("BENCHMARK_VERIFICATION_REQUIRED")

    def blockers(self):
        return tuple(reason for condition, reason in (
            (self.stock_return_definition != self.benchmark_return_definition, "RETURN_BASIS_MISMATCH"),
            (self.benchmark_verification != "VERIFIED", "BENCHMARK_UNRESOLVED"),
            (self.cash_rate is None, "CASH_ALTERNATIVE_UNRESOLVED")) if condition)


def filing_prefix(records, market, signal_date):
    """Read-only connection to the EXISTING filing-visibility rules.

    Returns detached records so downstream derivation cannot mutate the ledger.
    Original store limitations remain; this does not upgrade vintage evidence.
    """
    IF.day(signal_date)
    if market == "KR":
        from .kr_value_quality_catalyst import visible_filings
        selected = visible_filings(records, signal_date, "KR")
    elif market == "US":
        from .us_cash_profitability import visible_records
        selected = visible_records(records, signal_date)
    else:
        raise ValueError("UNKNOWN_MARKET")
    return tuple(deepcopy(selected))


@dataclass(frozen=True)
class LabelReference:
    """Separate metadata only. No future price, return or winner value is held."""
    sample_id: str
    market: str
    horizon_sessions: int
    execution_at: str
    maturity_at: str
    available_at: str
    price_basis_status: str
    terminal_status: str
    reference: str

    def __post_init__(self):
        _sha(self.sample_id)
        if self.horizon_sessions not in HORIZONS or not self.reference:
            raise ValueError("HORIZON_REFERENCE_REQUIRED")
        if not _utc(self.execution_at) < _utc(self.maturity_at) <= _utc(self.available_at):
            raise ValueError("INVALID_LABEL_INTERVAL")
        from . import replay_calendar as RC
        tz = {"KR": "Asia/Seoul", "US": "America/New_York"}.get(self.market)
        if tz is None:
            raise ValueError("UNKNOWN_MARKET")
        entry = str(_utc(self.execution_at).tz_convert(tz).date())
        end = str(_utc(self.maturity_at).tz_convert(tz).date())
        days = RC.sessions(entry, end, self.market)
        if (len(days) != self.horizon_sessions + 1 or str(days[0].date()) != entry
                or str(days[-1].date()) != end):
            raise ValueError("LABEL_HORIZON_CALENDAR_MISMATCH")
        if self.market == "KR":
            if _utc(self.maturity_at) < PRC.maturity_close_utc(entry, self.horizon_sessions):
                raise ValueError("MATURITY_SESSION_NOT_FINAL")
        else:
            from .us_daily_market_data import completed_sessions
            if end not in completed_sessions(str(_utc(self.maturity_at))):
                raise ValueError("MATURITY_SESSION_NOT_FINAL")
        if self.price_basis_status not in {"VERIFIED", "UNRESOLVED"}:
            raise ValueError("PRICE_BASIS_STATUS_REQUIRED")
        if self.terminal_status not in {"NOT_TERMINATED", "CONSIDERATION_VERIFIED", "UNRESOLVED"}:
            raise ValueError("TERMINAL_STATUS_REQUIRED")


@dataclass(frozen=True)
class Fold:
    training_cutoff: str
    evaluation_start: str
    evaluation_end: str
    label_deadline: str          # explicit purging/embargo boundary, pinned by future spec
    role: str                   # VALIDATION or TEST, never a tuning flag

    def __post_init__(self):
        if not (_utc(self.label_deadline) <= _utc(self.training_cutoff)
                < _utc(self.evaluation_start) < _utc(self.evaluation_end)):
            raise ValueError("INVALID_WALK_FORWARD_BOUNDARIES")
        if self.role not in {"VALIDATION", "TEST"}:
            raise ValueError("EVALUATION_ROLE_REQUIRED")

    def training_reason(self, reference: LabelReference):
        if reference.price_basis_status != "VERIFIED" or reference.terminal_status == "UNRESOLVED":
            return "BLOCKED_OUTCOME_ECONOMICS"
        if _utc(reference.maturity_at) >= _utc(self.evaluation_start):
            return "OVERLAPPING_LABEL_INTERVAL"
        if _utc(reference.available_at) >= _utc(self.label_deadline):
            return "LABEL_NOT_RELEASED_BEFORE_DEADLINE"
        return None


def preview_manifest(*, strategy, strategy_sha256, code_sha256, data_versions, seed,
                     samples_sha256, result_path, created_at):
    """Explicit, deterministic preview metadata; never grants execution permission."""
    for sha in (strategy_sha256, code_sha256, samples_sha256, *data_versions.values()):
        _sha(sha)
    _utc(created_at)
    path = PurePosixPath(result_path)
    if (not strategy or not data_versions or type(seed) is not int or seed < 0
            or not path.is_absolute() or ".." in path.parts):
        raise ValueError("EXPLICIT_RUN_IDENTITY_REQUIRED")
    body = {"contract": VERSION, "status": "PREVIEW_ONLY", "strategy": strategy,
            "strategySha256": strategy_sha256, "codeSha256": code_sha256,
            "dataVersions": dict(sorted(data_versions.items())), "seed": seed,
            "samplesSha256": samples_sha256, "resultPath": str(path), "createdAt": created_at,
            "historicalExecutionAuthorized": False, "productionPromotion": False}
    return {**body, "digest": IF.digest(body)}
