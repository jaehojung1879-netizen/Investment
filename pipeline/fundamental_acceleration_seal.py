"""Prospective sealing of fundamental-acceleration signal records.

WHAT THIS IS
------------
An append-only record of the acceleration reading for a name-date, written
BEFORE its outcome is knowable, so that a genuinely prospective (non-replay
-contaminated) validation becomes possible once its horizon matures. This is
the primary validation split
``docs/challenger-2-fundamental-acceleration-v1-design.md`` pre-registered
-- the discovery study on ``replay-v16`` (``fundamental_acceleration
_discovery.py``) is explicitly the bridge, never the confirmatory evidence.

Uses :mod:`pipeline.fundamental_acceleration` for the PIT filing-pair
resolution and delta computation -- the identical function the historical
discovery study calls, so the two never drift into two different
definitions of "acceleration".

APPEND-ONLY CONTRACT
---------------------
A record is keyed by ``(sealVersion, ticker, asOfDate)``. Once written, a
key is never overwritten, regenerated, or silently skipped-and-replaced --
:func:`append_seal` refuses any batch that collides with an existing key
rather than merging or updating it. This mirrors the ledger's own
append-only signal discipline (see AGENTS.md's "Ledger signals are
append-only and identified by date, region, ticker, and model version").

Each record carries a ``digest`` -- a SHA-256 over its own canonical content
(every field except the digest itself, dumped with sorted keys) -- so a
downstream reader can verify a row was not altered after being sealed
without needing to trust the file's mtime or git history alone.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import fundamental_acceleration as FA
from . import longterm
from . import pit_data
from . import provenance

SEAL_VERSION = "fundamental-acceleration-seal-v1"


def _canonical_json(row: dict) -> str:
    return json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False)


def digest_row(row: dict) -> str:
    """SHA-256 over the row's own canonical content, excluding `digest`."""
    payload = {k: v for k, v in row.items() if k != "digest"}
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def build_candidate_rows(candidates: list[dict], store: pit_data.FundamentalStore,
                         as_of) -> pd.DataFrame:
    """One row per candidate (ticker, region, sector, qualityPercentile) with
    its raw acceleration reading -- the live-data analogue of
    :func:`fundamental_acceleration_discovery.build_readings`, for exactly
    ONE as-of date's candidate cross-section rather than a whole ledger.
    """
    rows = []
    for candidate in candidates:
        ticker = candidate.get("ticker")
        region = candidate.get("region")
        if not ticker or not region:
            continue
        reading = FA.acceleration_reading(store, ticker, region, as_of)
        rows.append({
            "ticker": ticker, "region": region,
            "sector": candidate.get("sector") or "Unclassified",
            "qualityPercentile": (candidate.get("factorPercentiles") or {}).get("quality"),
            "status": reading["status"],
            "dataSufficient": reading["dataSufficient"],
            "primaryFieldsPresent": reading["primaryFieldsPresent"],
            "currentReportPeriod": reading["currentReportPeriod"],
            "currentAvailableFrom": reading["currentAvailableFrom"],
            "previousReportPeriod": reading["previousReportPeriod"],
            "previousAvailableFrom": reading["previousAvailableFrom"],
            "deltaRoe": reading["deltas"].get("roe"),
            "deltaOperatingMargin": reading["deltas"].get("operatingMargin"),
            "deltaProfitMargin": reading["deltas"].get("profitMargin"),
            "deltaEarningsGrowth": reading["deltas"].get("earningsGrowth"),
            "deltaDebtToEquity": reading["deltas"].get("debtToEquity"),
        })
    return pd.DataFrame(rows)


def score_candidate_rows(rows: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional sector-neutral composite over ONE as-of date's
    candidates -- identical construction to
    ``fundamental_acceleration_discovery.build_composite``, specialised to a
    single (already one-date) candidate table rather than a multi-date
    ledger.
    """
    out = rows.copy()
    out["compositeZ"] = np.nan
    out["accelerationPercentile"] = np.nan
    if out.empty:
        return out
    delta_columns = ("deltaRoe", "deltaOperatingMargin", "deltaProfitMargin",
                     "deltaEarningsGrowth")
    for region, group in out.groupby("region", sort=False):
        eligible = group[group["dataSufficient"]]
        if eligible.empty:
            continue
        z_frames = []
        for column in delta_columns:
            values = eligible[column]
            if values.notna().sum() < 2:
                continue
            z_frames.append(longterm.sector_neutral_z(values, eligible["sector"], FA.WINSOR))
        if not z_frames:
            continue
        composite = pd.concat(z_frames, axis=1).mean(axis=1, skipna=True)
        out.loc[composite.index, "compositeZ"] = composite
        pct = composite.rank(pct=True) * 100.0
        out.loc[pct.index, "accelerationPercentile"] = pct
    return out


def seal_records(scored_rows: pd.DataFrame, as_of, *, generated_at: str | None = None) -> list[dict]:
    """Turn one as-of date's scored candidate table into immutable seal
    records, each carrying its own digest.
    """
    as_of_str = str(pd.Timestamp(as_of).normalize().date())
    stamp = generated_at or datetime.now(timezone.utc).isoformat()
    commit_sha = provenance.build_commit_sha()
    records = []
    for _, row in scored_rows.iterrows():
        record = {
            "sealVersion": SEAL_VERSION,
            "accelerationVersion": FA.VERSION,
            "generatedAt": stamp,
            "asOfDate": as_of_str,
            "ticker": row["ticker"],
            "region": row["region"],
            "sector": row["sector"],
            "status": row["status"],
            "dataSufficient": bool(row["dataSufficient"]),
            "primaryFieldsPresent": int(row["primaryFieldsPresent"]),
            "currentReportPeriod": row["currentReportPeriod"],
            "currentAvailableFrom": row["currentAvailableFrom"],
            "previousReportPeriod": row["previousReportPeriod"],
            "previousAvailableFrom": row["previousAvailableFrom"],
            "deltas": {
                "roe": _none_or_float(row["deltaRoe"]),
                "operatingMargin": _none_or_float(row["deltaOperatingMargin"]),
                "profitMargin": _none_or_float(row["deltaProfitMargin"]),
                "earningsGrowth": _none_or_float(row["deltaEarningsGrowth"]),
                "debtToEquity": _none_or_float(row["deltaDebtToEquity"]),
            },
            "compositeZ": _none_or_float(row["compositeZ"]),
            "accelerationPercentile": _none_or_float(row["accelerationPercentile"]),
            "qualityPercentile": _none_or_float(row["qualityPercentile"]),
            "buildCommitSha": commit_sha,
        }
        record["digest"] = digest_row(record)
        records.append(record)
    return records


def _none_or_float(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return float(value)


def existing_keys(path: Path) -> set[tuple[str, str, str]]:
    if not path.exists():
        return set()
    keys = set()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            keys.add((row["sealVersion"], row["ticker"], row["asOfDate"]))
    return keys


def append_seal(path: Path, records: list[dict]) -> int:
    """Append `records` to the JSONL at `path`. Refuses the whole batch if
    ANY record collides with an already-sealed `(sealVersion, ticker,
    asOfDate)` key -- an append-only store never silently overwrites or
    re-derives a prior reading.
    """
    path = Path(path)
    existing = existing_keys(path)
    new_keys = [(r["sealVersion"], r["ticker"], r["asOfDate"]) for r in records]
    collisions = sorted(set(new_keys) & existing)
    if collisions:
        raise ValueError(f"refusing to reseal already-sealed keys: {collisions[:10]}")
    if len(new_keys) != len(set(new_keys)):
        raise ValueError("duplicate (sealVersion, ticker, asOfDate) keys within this batch")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(_canonical_json(record) + "\n")
    return len(records)
