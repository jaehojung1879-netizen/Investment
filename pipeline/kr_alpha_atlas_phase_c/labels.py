"""The one label engine; called only after a synthetic or formal outcome permit."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from pipeline.alpha_opportunity_v4_eligibility import label_eligibility
from .contract import digest

_TOKEN = object()


@dataclass
class Counters:
    realOutcomeReads: int = 0
    realLabels: int = 0
    realModelFits: int = 0
    syntheticOutcomeReads: int = 0
    syntheticLabels: int = 0
    syntheticModelFits: int = 0

    def increment(self, category, synthetic, count=1):
        name = ("synthetic" if synthetic else "real") + category
        setattr(self, name, getattr(self, name) + count)


@dataclass(frozen=True)
class OutcomePermit:
    synthetic: bool
    source_identity: str
    token: object = field(repr=False)

    def require(self):
        if self.token is not _TOKEN:
            raise ValueError("OUTCOME_ACCESS_NOT_PERMITTED")


def synthetic_permit(data):
    # A distinct invented-market path. No flag can relabel a real input as synthetic.
    if data.source_identity != "SYNTHETIC_FIXTURE" or not all(str(t).startswith("SYN") for t in data.rows.ticker):
        raise ValueError("REAL_INPUT_CANNOT_USE_SYNTHETIC_PERMIT")
    return OutcomePermit(True, data.source_identity, _TOKEN)


def formal_permit(source_identity, lock_receipt):
    from .lifecycle import VerifiedLock, _LOCK_PROOF

    if not isinstance(lock_receipt, VerifiedLock) or lock_receipt.proof is not _LOCK_PROOF:
        raise ValueError("PERMANENT_LOCK_REQUIRED")
    doc = lock_receipt.document
    if not doc.get("verified") or doc.get("ref") != "refs/tags/kr-alpha-atlas-phase-c-v1-execution-lock":
        raise ValueError("PERMANENT_LOCK_REQUIRED")
    return OutcomePermit(False, source_identity, _TOKEN)


@dataclass
class StudyData:
    rows: pd.DataFrame
    values: pd.DataFrame
    available: pd.DataFrame
    days: pd.DatetimeIndex
    closes: dict
    volumes: dict
    benchmark_close: np.ndarray
    source_identity: str
    completeness: dict = field(default_factory=dict)
    terminal_events: dict = field(default_factory=dict)
    reasons: pd.DataFrame | None = None

    def validate_features(self, spec):
        if not self.rows.index.equals(pd.RangeIndex(len(self.rows))):
            raise ValueError("CANONICAL_ROW_INDEX_REQUIRED")
        if not self.rows.index.equals(self.values.index) or not self.rows.index.equals(self.available.index):
            raise ValueError("MATRIX_ROW_ALIGNMENT")
        if not self.rows[["date", "ticker"]].equals(
            self.rows[["date", "ticker"]].sort_values(["date", "ticker"]).reset_index(drop=True)
        ):
            raise ValueError("CANONICAL_DATE_SECURITY_ORDER_REQUIRED")
        if self.rows[["date", "ticker"]].duplicated().any():
            raise ValueError("DUPLICATE_SECURITY_SIGNAL")
        if not self.days.is_unique or not self.days.is_monotonic_increasing:
            raise ValueError("INVALID_CALENDAR")
        if (self.rows.pitSnapshotDate >= self.rows.date).any():
            raise ValueError("MEMBERSHIP_LEAKAGE")
        if not set(pd.to_datetime(self.rows.date)).issubset(set(self.days)):
            raise ValueError("SIGNAL_NOT_IN_CALENDAR")
        for col in self.available:
            visible = self.available[col].notna() & self.values[col].notna()
            if (self.available.loc[visible, col] >= self.rows.loc[visible, "date"]).any():
                raise ValueError("FILING_TIMESTAMP_LEAKAGE")
        if len(self.rows) > spec["compute"]["maxRows"] or self.rows.date.nunique() > spec["compute"]["maxSignalDates"]:
            raise ValueError("PRE_OUTCOME_RESOURCE_LIMIT")
        if sum(len(x) for x in self.closes.values()) > spec["compute"]["maxPriceCells"]:
            raise ValueError("PRE_OUTCOME_PRICE_RESOURCE_LIMIT")
        required = {f["featureId"] for f in spec["eligibleFeatures"]}
        required |= {f for fs in spec["baselines"].values() for f in fs}
        if not required <= set(self.values):
            raise ValueError("REGISTERED_COLUMN_ABSENT")
        if np.isinf(self.values.to_numpy(float)).any():
            raise ValueError("INFINITE_FEATURE")
        if self.reasons is not None and (self.values.isna() & self.reasons.eq("")).any().any():
            raise ValueError("MISSING_FEATURE_REASON_ABSENT")
        return {
            "rows": len(self.rows),
            "signalDates": self.rows.date.nunique(),
            "columns": len(self.values.columns),
            "b4CompleteCaseShare": float(
                self.values[spec["baselines"]["B4_COMBINED_SIMPLE"]].notna().all(axis=1).mean()
            ),
        }


@dataclass
class LabelBook:
    table: pd.DataFrame
    gross_increments: np.ndarray
    relative_increments: np.ndarray
    entry_positions: np.ndarray
    horizon: int


def window_sessions(days, signal, horizon, cutoff):
    pos = int(days.searchsorted(pd.Timestamp(signal), side="right"))
    exit_pos = pos + horizon
    if exit_pos >= len(days) or str(days[exit_pos].date()) > cutoff:
        return pos, exit_pos, "NOT_MATURED_BY_CUTOFF"
    return pos, exit_pos, None


def economic_validity(evidence, crosses, event):
    # Reuse the existing identity-free security evidence policy. Audited basis gaps
    # apply to the whole security; identical evidence gets identical treatment.
    gate = label_eligibility(
        completeness=evidence,
        window_crosses_termination=crosses,
        total_return_series_available=bool(evidence and evidence.get("totalReturnSeriesBuilt") == "READY"),
    )
    if gate["status"] != "ELIGIBLE":
        return gate["reasonCode"]
    if crosses:
        # The frozen snapshot has no complete cited cash/successor distribution path.
        # A resolved flag alone never substitutes for economic marks/cash flows.
        if not event or not event.get("sourceReceiptNumber") or not event.get("wealthPathVerified"):
            return "TERMINAL_CONSIDERATION_UNRESOLVED"
        return "SUCCESSOR_DISTRIBUTION_PATH_NOT_PINNED"
    return None


def build_labels(data, horizon, cutoff, permit, counters):
    permit.require()
    if permit.source_identity != data.source_identity:
        raise ValueError("PERMIT_INPUT_IDENTITY_MISMATCH")
    n = len(data.rows)
    gross_inc = np.full((n, horizon), np.nan)
    relative_inc = np.full((n, horizon), np.nan)
    records, entries = [], np.zeros(n, dtype=int)
    for i, row in enumerate(data.rows.itertuples()):
        entry, exit_pos, invalid = window_sessions(data.days, row.date, horizon, cutoff)
        entries[i] = entry
        event = data.terminal_events.get(row.ticker)
        exit_day = str(data.days[exit_pos].date()) if exit_pos < len(data.days) else None
        crosses = bool(event and exit_day and row.date <= event["lastTradingDate"] < exit_day)
        if invalid is None:
            invalid = economic_validity(data.completeness.get(row.ticker), crosses, event)
        rec = {
            "row": i,
            "ticker": row.ticker,
            "securityIdentity": row.ticker,
            "date": row.date,
            "horizon": horizon,
            "entry": str(data.days[entry].date()) if entry < len(data.days) else None,
            "exit": exit_day,
            "sourceIdentity": data.source_identity,
            "corporateActionTreatment": "FROZEN_ADJUSTED_INDEX_PARTIAL_DISTRIBUTIONS_NO_TERMINAL_FABRICATION",
            "basisAudit": "UNKNOWN_UNAUDITED" if data.completeness.get(row.ticker) is None else "AUDITED",
            "state": "INVALID" if invalid else "VALID",
            "missingReason": invalid,
            "gross": None,
            "benchmark": None,
            "benchmarkRelative": None,
            "industryRelative": None,
            "looIndustry": None,
            "industryState": "BLOCKED",
            "industryReason": "INDUSTRY_NOT_EVALUABLE",
        }
        if invalid is None:
            counters.increment("OutcomeReads", permit.synthetic)
            close = data.closes.get(row.ticker)
            volume = data.volumes.get(row.ticker)
            stock = np.asarray(close[entry : exit_pos + 1], float) if close is not None else np.array([])
            bench = np.asarray(data.benchmark_close[entry : exit_pos + 1], float)
            if len(stock) != horizon + 1 or not np.isfinite(stock).all() or (stock <= 0).any():
                invalid = "MISSING_OR_INVALID_PRICE_WINDOW"
            elif len(bench) != horizon + 1 or not np.isfinite(bench).all() or (bench <= 0).any():
                invalid = "BENCHMARK_WINDOW_INVALID"
            elif (
                volume is None
                or not np.isfinite([volume[entry], volume[exit_pos]]).all()
                or min(volume[entry], volume[exit_pos]) <= 0
            ):
                invalid = "ENTRY_OR_EXIT_NOT_EXECUTABLE"
            if invalid:
                rec.update(state="INVALID", missingReason=invalid)
            else:
                gross_inc[i] = np.diff(stock) / stock[0]
                bi = np.diff(bench) / bench[0]
                relative_inc[i] = gross_inc[i] - bi
                rec.update(
                    gross=float(stock[-1] / stock[0] - 1),
                    benchmark=float(bench[-1] / bench[0] - 1),
                    benchmarkRelative=float(relative_inc[i].sum()),
                )
                counters.increment("Labels", permit.synthetic)
        records.append(rec)
    table = pd.DataFrame(records)
    # A common LOO cohort needs every signal-time member's outcome; an invalid peer
    # is never silently deleted and the remaining cap weights never renormalized.
    for (_, industry), group in data.rows.groupby(["date", "industry"], sort=True):
        ids = group.index.to_numpy(int)
        if len(ids) < 5 or not table.loc[ids, "state"].eq("VALID").all():
            table.loc[ids, "industryReason"] = "INCOMPLETE_OR_THIN_INDUSTRY_COHORT"
            continue
        caps = group.marketCap.to_numpy(float)
        if not np.isfinite(caps).all() or (caps <= 0).any():
            table.loc[ids, "industryReason"] = "INDUSTRY_CAP_UNAVAILABLE"
            continue
        ret = table.loc[ids, "gross"].to_numpy(float)
        total = float(caps @ ret)
        loo = (total - caps * ret) / (caps.sum() - caps)
        table.loc[ids, "looIndustry"] = loo
        table.loc[ids, "industryRelative"] = ret - loo
        table.loc[ids, "industryState"] = "VALID"
        table.loc[ids, "industryReason"] = None
    return LabelBook(table, gross_inc, relative_inc, entries, horizon)


def attrition(data, books):
    all_rows = []
    for h, book in books.items():
        t = book.table.copy()
        t["industry"] = data.rows.industry.fillna("UNCLASSIFIED").to_numpy()
        t["year"] = t.date.str[:4]
        matured = t.missingReason.ne("NOT_MATURED_BY_CUTOFF")
        lost = t[matured & t.state.ne("VALID")]
        all_rows.append(
            {
                "horizon": h,
                "preGate": int(matured.sum()),
                "evaluable": int((matured & t.state.eq("VALID")).sum()),
                "affectedSecurities": int(lost.ticker.nunique()),
                "affectedNameDateHorizon": len(lost),
                "referenceUniverseShare": len(lost) / int(matured.sum()) if matured.any() else None,
                "referenceUniverseSecurities": int(data.rows.ticker.nunique()),
                "affectedSecurityShare": int(lost.ticker.nunique()) / int(data.rows.ticker.nunique())
                if data.rows.ticker.nunique()
                else None,
                "auditedBasisAffectedSecurities": len(set(lost.ticker) & set(data.completeness)),
                "lostByYear": dict(Counter(lost.year)),
                "lostByIndustry": dict(Counter(lost.industry)),
                "missingReasons": dict(Counter(lost.missingReason)),
                "validityMaskSha256": digest(
                    t[["date", "ticker", "state", "missingReason"]].where(t.notna(), None).to_dict("records")
                ),
            }
        )
    return all_rows
