"""Invented deterministic market. Synthetic evidence never describes real returns."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.kr_alpha_atlas_catalogue import CATALOGUE
from pipeline.replay_calendar import sessions
from .contract import canonical, digest
from .executor import execute, persist
from .labels import Counters, StudyData, build_labels, synthetic_permit


def market(*, end="2019-12-30", names=48, missing=False, regime_reversal=False):
    days = sessions("2013-01-01", end, "KR")
    from pipeline.alpha_opportunity_v3_survivorship import weekly_grid

    extended = sessions("2013-01-01", (pd.Timestamp(end) + pd.Timedelta(days=14)).strftime("%Y-%m-%d"), "KR")
    dates = weekly_grid(extended, end)
    tickers = [f"SYN{i:03}" for i in range(names)]
    # Orthogonal name components, repeated evenly within each invented industry.
    x = np.tile(np.linspace(-1, 1, 8), int(np.ceil(names / 8)))[:names]
    z = np.tile(np.array([-1, 1, 1, -1, -1, 1, 1, -1]), int(np.ceil(names / 8)))[:names]
    noise = np.tile(np.array([1, -1, 1, -1, -1, 1, -1, 1]), int(np.ceil(names / 8)))[:names]
    industry = np.arange(names) // 8
    state = np.where(np.arange(len(days)) // 504 % 2 == 0, 1.0, -1.0)
    daily = (
        0.00015
        + 0.00025 * x[None, :]
        + 0.00020 * z[None, :] * (state[:, None] if regime_reversal else 1)
        + 0.000012 * industry[None, :]
    )
    daily = daily + 0.000002 * np.sin(np.arange(len(days))[:, None] / 17) * noise[None, :]
    close = 100 * np.cumprod(1 + daily, axis=0)
    benchmark = 100 * np.cumprod(np.full(len(days), 1.00015))
    records = []
    values = []
    availability = []
    for date in dates:
        before = (pd.Timestamp(date) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        pos = int(days.searchsorted(date))
        regime = 2.0 if state[pos] > 0 else 0.0
        for j, ticker in enumerate(tickers):
            records.append(
                {
                    "date": date,
                    "ticker": ticker,
                    "pitSnapshotDate": before,
                    "industry": f"IND{industry[j]}",
                    "liquidityTier": ["LOW", "MID", "HIGH"][j % 3],
                    "tradableAtSignal": True,
                    "b08Confirmed": int(z[j] > 0),
                    "b08State": "READY",
                    "marketCap": 1e12 + 1e9 * j,
                }
            )
            v = {fid: float(np.sin((j + 1) * (k + 3)) + 0.04 * np.cos(pos / 21 + k)) for k, fid in enumerate(CATALOGUE)}
            for fid in (
                "A05_relative126",
                "A07_momentum12_1",
                "A11_distance52wHigh",
                "B01_bookToMarket",
                "B02_earningsYield",
                "C01_returnOnAssets",
                "C05_ocfToAssets",
                "D02_logVolumeShock60",
                "E01_amihudIlliquidity60",
                "E02_logAdv60",
                "H01_industryRelMom126",
            ):
                v[fid] = float(x[j])
            v.update(
                A10_residualMomentum126=float(x[j]),
                A12_momentumPersistence=float(x[j]),
                D07_volumePriceAlignment=float(z[j]),
                A04_return63d=float(noise[j]),
                I01_kospiTrendVolState=regime,
                E03_capacityMedianTradedValue60=10e9 * (1 + j / names),
                E04_tradabilityGuard20=20.0,
                J01_periodicFilingEvent=float(j % 2),
                B05_industryRelativeValue=float(x[j]),
                B08_valueBusinessConfirmation=float(x[j]),
                D05_turnoverToMarketCap60=float(z[j]),
                F01_totalVolatility63=float(x[j]),
                A09_industryRelativeMomentum126=float(z[j]),
            )
            if regime_reversal:
                v["A05_relative126"] = float(z[j])
            values.append(v)
            availability.append({fid: before for fid in CATALOGUE})
    rows = pd.DataFrame(records)
    v = pd.DataFrame(values, dtype=float)
    if missing:
        coverage_order = (np.arange(len(v)) * 127) % len(v)
        v.loc[coverage_order >= round(len(v) * 0.443), "B01_bookToMarket"] = np.nan
    available = pd.DataFrame(availability)
    reasons = pd.DataFrame(np.where(v.notna(), "", "SYNTHETIC_MISSING_FEATURE"), columns=v.columns)
    return StudyData(
        rows,
        v,
        available,
        days,
        {t: close[:, j].copy() for j, t in enumerate(tickers)},
        {t: np.full(len(days), 1e6) for t in tickers},
        benchmark,
        "SYNTHETIC_FIXTURE",
        reasons=reasons,
    )


def smoke(spec):
    data = market(end="2013-06-28")
    data.validate_features(spec)
    counters = Counters()
    permit = synthetic_permit(data)
    labels = build_labels(data, 21, spec["developmentCutoff"], permit, counters)
    first = labels.table[labels.table.state.eq("VALID")].iloc[0]
    if not np.isfinite(first.gross) or counters.realOutcomeReads or counters.realLabels:
        raise ValueError("SYNTHETIC_PREFLIGHT_FAILED")
    from .models import Transformer, ridge_fit, date_weights
    from .statistics import percentiles

    x = percentiles(data, ["A05_relative126"])
    ids = labels.table.index[labels.table.state.eq("VALID")]
    tr = Transformer().fit(x.loc[ids], data.rows.loc[ids, "date"])
    ridge_fit(
        tr.transform(x.loc[ids]),
        labels.table.loc[ids, "benchmarkRelative"].to_numpy(float),
        date_weights(data.rows.loc[ids, "date"]),
        1.0,
    )
    from .economics import block

    row = labels.table.loc[ids[0]]
    b = block(data, labels, row.date, {}, "CASH", spec)
    if b["status"] == "BLOCKED" or b["selectedCount"] != 0:
        raise ValueError("SYNTHETIC_EMPTY_PORTFOLIO_FAILED")
    return {"passed": True, "realOutcomeReads": 0, "labels": counters.syntheticLabels}


def complete_study(spec, output=None):
    data = market(missing=True, names=32)
    result = execute(data, spec, synthetic_permit(data))
    if output is not None:
        persist(result, Path(output) / "synthetic", {"mode": "SYNTHETIC", "input": "INVENTED", "realOutcomeReads": 0})
    return {
        "status": "SYNTHETIC_ONLY",
        "canonicalSha256": digest(result),
        "featureHorizonTests": len(result["level1"]),
        "familyComparisons": result["multiplicity"]["level2Slots"],
        "interactions": len(result["level3"]),
        "modelFits": result["compute"]["predictiveFits"],
        "counters": result["counters"],
        "noRealInvestmentEvidence": True,
    }


def synthetic_contract(spec):
    """Not a real registration. Only permits deterministic low-depth unit fixtures."""
    out = deepcopy(spec)
    out["level1"]["minDates"] = 1
    out["level1"]["minEvaluableShare"] = 0.0
    return out


def write_fixture(data, path):
    """Actual safe file loader exercise, no pickle or external execution."""
    obj = {
        "sourceIdentity": data.source_identity,
        "rows": data.rows.to_dict("records"),
        "values": data.values.astype(object).where(data.values.notna(), None).to_dict("records"),
        "available": data.available.to_dict("records"),
        "days": [str(d.date()) for d in data.days],
        "closes": {t: p.tolist() for t, p in data.closes.items()},
        "volumes": {t: p.tolist() for t, p in data.volumes.items()},
        "benchmark": data.benchmark_close.tolist(),
    }
    Path(path).write_bytes(canonical(obj) + b"\n")


def read_fixture(path):
    import json

    obj = json.loads(Path(path).read_text())
    if obj["sourceIdentity"] != "SYNTHETIC_FIXTURE" or not all(t.startswith("SYN") for t in obj["closes"]):
        raise ValueError("NON_SYNTHETIC_FIXTURE_FILE")
    data = StudyData(
        pd.DataFrame(obj["rows"]),
        pd.DataFrame(obj["values"], dtype=float),
        pd.DataFrame(obj["available"]),
        pd.DatetimeIndex(obj["days"]),
        {t: np.array(p) for t, p in obj["closes"].items()},
        {t: np.array(p) for t, p in obj["volumes"].items()},
        np.array(obj["benchmark"]),
        obj["sourceIdentity"],
    )
    return data
