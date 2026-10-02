"""Outcome-free KR context. Independent axes; no labels, score or allocation.

Adapters supply explicit knowledge records. A revised historical value is
usable only after the retained fetch made that exact value known, never at
an estimated historical publication date. Release lag cannot supply vintage.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math

from .kr_market_risk_overlay import state_at as equity_risk_state

AXES = {
    "domesticGrowth": ("IndustrialProduction", "Exports", "LeadingIndex"),
    "inflation": ("CPI", "CoreCPI"),
    "domesticRates": ("BaseRate", "Korea_3M", "Korea_10Y", "KR_TermSpread"),
    "domesticLiquidityCredit": ("M2", "KTB_3Y", "CorpBond_3Y", "KR_CreditSpread"),
    "externalFinancialConditions": ("USD_KRW", "Broad_Dollar", "Real_10Y", "FedFunds",
                                    "Treasury_2Y", "Treasury_10Y", "HY_Spread", "VIX"),
    "equityMarketState": ("KODEX200_TrendAdverse", "KODEX200_Vol63", "Breadth", "Concentration"),
}
INPUTS = frozenset(n for names in AXES.values() for n in names)
VINTAGES = {"PIT_EXACT", "PIT_APPROXIMATE", "REVISED_HISTORY", "CURRENT_SNAPSHOT_ONLY"}


def stamp(value):
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


@dataclass(frozen=True)
class Observation:
    name: str
    value: float | None
    observed_through: str
    available_from: str
    fetched_at: str
    source: str
    vintage_status: str
    published_at: str | None = None
    source_status: str = "DATA_LINEAGE_UNRESOLVED"
    unit: str | None = None
    vintage_evidence: str | None = None

    def __post_init__(self):
        if self.name not in INPUTS or self.vintage_status not in VINTAGES:
            raise ValueError("UNKNOWN_CONTEXT_INPUT_OR_VINTAGE")
        if self.value is not None and not math.isfinite(self.value):
            raise ValueError("NONFINITE_VALUE")
        if stamp(self.observed_through) > stamp(self.available_from):
            raise ValueError("AVAILABILITY_BEFORE_OBSERVATION")
        if self.published_at and stamp(self.published_at) > stamp(self.available_from):
            raise ValueError("AVAILABILITY_BEFORE_PUBLICATION")
        if self.vintage_status == "PIT_EXACT" and not self.vintage_evidence:
            raise ValueError("VINTAGE_EVIDENCE_REQUIRED")
        if self.source.startswith("ECOS") and self.vintage_status != "REVISED_HISTORY":
            raise ValueError("ECOS_IS_REVISED_HISTORY")

    def visible(self, date):
        known = stamp(self.available_from)
        if self.vintage_status in {"REVISED_HISTORY", "CURRENT_SNAPSHOT_ONLY"}:
            known = max(known, stamp(self.fetched_at))
        return known <= stamp(date) and stamp(self.observed_through) <= stamp(date)


def ecos_records(frame, config, *, fetched_at):
    """Adapt the existing native ECOS frame; no fetching or historical backdating.

    Period end is a conservative observation endpoint. Incomplete advertised
    periods are omitted rather than moved before their actual endpoint.
    """
    from calendar import monthrange
    output = []
    if frame is None:
        return output
    for name in frame.columns:
        spec = config.get(name, {})
        if name not in INPUTS or spec.get("sourceStatus") != "LIVE_VALIDATED_SOURCE" or not spec.get("unit"):
            continue
        cycle = spec.get("cycle")
        for period, value in frame[name].items():
            if value is None or not math.isfinite(float(value)):
                continue
            text = str(period)
            if cycle == "D":
                endpoint = f"{text[:4]}-{text[4:6]}-{text[6:8]}"
            elif cycle in {"M", "Q", "A"}:
                year = int(text[:4])
                month = int(text[4:6]) if cycle == "M" else int(text[-1])*3 if cycle == "Q" else 12
                endpoint = f"{year:04d}-{month:02d}-{monthrange(year,month)[1]:02d}"
            else:
                continue
            if stamp(endpoint) > stamp(fetched_at):
                continue
            source = "ECOS:" + "/".join(str(spec.get(k, "")) for k in ("seriesId", "itemCode", "itemCode2", "itemCode3", "itemCode4"))
            output.append(Observation(name, float(value), endpoint, fetched_at, fetched_at,
                source, "REVISED_HISTORY", source_status="LIVE_VALIDATED_SOURCE", unit=spec["unit"]))
    return output


def _measurement(name, records, date, window):
    visible = [r for r in records if r.name == name and r.visible(date) and r.value is not None]
    # Newest available vintage of each observation; conflicting same identities fail closed.
    by_period = {}
    for row in sorted(visible, key=lambda r: (stamp(r.available_from), stamp(r.fetched_at))):
        old = by_period.get(row.observed_through)
        if old and (old.available_from, old.fetched_at) == (row.available_from, row.fetched_at) and old != row:
            raise ValueError("AMBIGUOUS_CONTEXT_OBSERVATION")
        by_period[row.observed_through] = row
    rows = sorted(by_period.values(), key=lambda r: stamp(r.observed_through))
    if not rows:
        return {"value": None, "change": None, "acceleration": None, "direction": None,
                "status": "DATA_INSUFFICIENT", "coverage": {"visibleObservations": 0},
                "source": None, "sourceStatus": "NOT_AVAILABLE", "observedThrough": None,
                "publishedAt": None, "availableFrom": None, "vintageStatus": None}
    latest = rows[-1]
    # Mixing units/source semantics would manufacture a change.
    same = all((r.source, r.unit, r.vintage_status) == (latest.source, latest.unit, latest.vintage_status) for r in rows)
    change = latest.value - rows[-1-window].value if same and len(rows) > window else None
    acceleration = (change - (rows[-1-window].value - rows[-1-2*window].value)
                    if same and len(rows) > 2*window else None)
    return {"value": latest.value, "change": change, "acceleration": acceleration,
            "direction": None if change is None else ("UP" if change > 0 else "DOWN" if change < 0 else "FLAT"),
            "unit": latest.unit, "status": "OBSERVED", "source": latest.source,
            "sourceStatus": latest.source_status, "observedThrough": latest.observed_through,
            "publishedAt": latest.published_at, "availableFrom": latest.available_from,
            "fetchedAt": latest.fetched_at, "knownFrom": max(latest.available_from, latest.fetched_at, key=stamp)
            if latest.vintage_status in {"REVISED_HISTORY", "CURRENT_SNAPSHOT_ONLY"} else latest.available_from,
            "vintageStatus": latest.vintage_status,
            "confirmatoryHistoricalEligible": latest.vintage_status == "PIT_EXACT",
            "coverage": {"visibleObservations": len(rows), "changeWindowNativeObservations": window}}


def _spread(left, right):
    # Do not subtract asynchronous last readings (OECD monthly vs ECOS daily).
    if (left["value"] is None or right["value"] is None
            or left["observedThrough"] != right["observedThrough"] or not left.get("unit")
            or left.get("unit") != right.get("unit")):
        return {"value": None, "change": None, "acceleration": None, "direction": None,
                "status": "DATA_INSUFFICIENT", "sourceStatus": "DATA_LINEAGE_UNRESOLVED",
                "source": None, "observedThrough": None, "publishedAt": None,
                "availableFrom": None, "knownFrom": None, "vintageStatus": None,
                "coverage": {"inputs": 0, "requiredInputs": 2}, "confirmatoryHistoricalEligible": False}
    exact = all(r["vintageStatus"] == "PIT_EXACT" for r in (left, right))
    return {"value": left["value"] - right["value"], "change": None, "acceleration": None,
            "direction": None, "status": "DERIVED", "source": [left["source"], right["source"]],
            "sourceStatus": "DERIVED_FROM_VISIBLE_INPUTS", "observedThrough": left["observedThrough"],
            "publishedAt": None, "availableFrom": max(left["availableFrom"], right["availableFrom"], key=stamp),
            "knownFrom": max(left["knownFrom"], right["knownFrom"], key=stamp),
            "vintageStatus": "PIT_EXACT" if exact else "REVISED_HISTORY",
            "confirmatoryHistoricalEligible": exact, "coverage": {"inputs": 2}}


def state_at(date, records=(), *, windows=None, benchmark=None, benchmark_available_from=None):
    """Six separate measurement maps. Dates use explicit UTC instants (date-only = midnight).

    windows counts native observations, never silently forward-filled days.
    Callers choose windows before outcome study; default adjacent observation.
    Benchmark risk state reuses the existing past-only KODEX implementation;
    its risk multiplier is not exported as a context score.
    """
    windows = windows or {}
    if any(n not in INPUTS or not isinstance(w, int) or w < 1 for n, w in windows.items()):
        raise ValueError("INVALID_CONTEXT_WINDOW")
    records = tuple(records)
    measurements = {n: _measurement(n, records, date, windows.get(n, 1)) for n in INPUTS}
    measurements["KR_TermSpread"] = _spread(measurements["Korea_10Y"], measurements["Korea_3M"])
    measurements["KR_CreditSpread"] = _spread(measurements["CorpBond_3Y"], measurements["KTB_3Y"])
    if benchmark is not None and benchmark_available_from is not None and stamp(benchmark_available_from) <= stamp(date):
        risk = equity_risk_state(benchmark, str(date)[:10])
        if risk["status"] == "READY":
            for name, key in (("KODEX200_TrendAdverse", "trendAdverse"), ("KODEX200_Vol63", "benchmarkVol63")):
                measurements[name] = {"value": float(risk[key]), "status": "OBSERVED",
                    "source": "kr_market_risk_overlay.state_at:069500.KS", "sourceStatus": "CALLER_SUPPLIED_PRICE_HISTORY",
                    "observedThrough": risk["availableThrough"], "availableFrom": benchmark_available_from,
                    "publishedAt": None, "vintageStatus": "DATA_LINEAGE_UNRESOLVED",
                    "change": None, "acceleration": None, "direction": None,
                    "coverage": {"requiredKRSessions": 201}, "confirmatoryHistoricalEligible": False}
    axes = {}
    for axis, names in AXES.items():
        values = {n: measurements[n] for n in names}
        axes[axis] = {"measurements": values, "coverage": {
            "observed": sum(v["value"] is not None for v in values.values()), "expected": len(names)}}
    return {"contract": "KR_MARKET_CONTEXT_V1", "date": str(date), "region": "KR", "axes": axes}
