"""Content-addressed, deterministic monthly input shards with an immutable prefix.

The manifest is committed only after every component passes. A recovered or revised
past value requires a new DATA_VERSION AND a separate replay directory. --full is
not an escape hatch. No adjusted-close panels are spliced across fetch vintages.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from .market_dates import normalize_daily_frame
from . import historical_store as HS
from . import pit_data

SCHEMA = "REPLAY_INPUTS_V1"


class InputVersionConflict(RuntimeError):
    pass


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":"), default=str).encode()


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def frame_rows(frame, through: str) -> list[dict]:
    if frame is None:
        return []
    if isinstance(frame, pd.Series):
        frame = frame.to_frame("value")
    clean = normalize_daily_frame(frame).loc[:through].copy()
    clean.index = clean.index.strftime("%Y-%m-%d")
    # pandas' JSON conversion maps NaN to null, never a fabricated zero.
    return json.loads(clean.rename_axis("date").reset_index().to_json(orient="records", double_precision=15))


def rows_frame(rows: list[dict], series=False):
    if not rows:
        return None
    result = pd.DataFrame(rows).set_index("date")
    result.index = pd.to_datetime(result.index)
    return result["value"] if series else result


class InputStore:
    def __init__(self, ledger, replay_version: str, data_version: str):
        self.ledger = Path(ledger)
        self.root = self.ledger / "replay-inputs"
        self.path = self.ledger / "historical" / replay_version / "inputs.json"
        self.replay_version, self.data_version = replay_version, data_version

    def manifest(self):
        if not self.path.exists():
            return None
        value = json.loads(self.path.read_text())
        if value["replayVersion"] != self.replay_version or value["dataVersion"] != self.data_version:
            raise InputVersionConflict("DATA_VERSION changed inside an existing replay generation; use a new REPLAY_VERSION")
        if digest({k:v for k,v in value.items() if k != "sha256"}) != value["sha256"]:
            raise InputVersionConflict("input manifest hash mismatch")
        return value

    def _read(self, ref):
        raw = gzip.decompress((self.root / "objects" / (ref + ".json.gz")).read_bytes())
        if hashlib.sha256(raw).hexdigest() != ref:
            raise InputVersionConflict("input object hash mismatch: " + ref)
        return json.loads(raw)

    def load(self, manifest=None, *, valuation_only=False):
        manifest = manifest or self.manifest()
        if not manifest:
            raise InputVersionConflict("no frozen inputs in this generation; first run must acquire inputs")
        result = {}
        for name, refs in manifest["components"].items():
            if valuation_only and not name.startswith(("price/", "benchmark/", "fx/", "risk-free/")):
                continue
            rows = []
            for ref in refs:
                part = self._read(ref)
                if valuation_only and name.startswith(("price/", "benchmark/")):
                    part = [{k:r[k] for k in ("date", "ticker", "Close")} for r in part]
                rows.extend(part)
            result[name] = rows
        return result

    def commit(self, components: dict[str, list[dict]], *, through: str, policy: dict):
        prior = self.manifest()
        if prior:
            if through < prior["through"]:
                raise InputVersionConflict("input cutoff cannot move backwards")
            old = self.load(prior)
            if policy != prior["policy"]:
                raise InputVersionConflict("replay policy changed; new DATA_VERSION/REPLAY_VERSION required")
            for key in sorted(set(old) | set(components)):
                # Undated/static inputs are frozen whole; dated inputs may only
                # append beyond the global sealed cutoff. Missing rows are sealed too.
                prefix = [r for r in components.get(key, [])
                          if str(r.get("date") or "") <= prior["through"]]
                if digest(prefix) != digest(old.get(key, [])):
                    raise InputVersionConflict(f"{key}: published input prefix changed/recovered; new DATA_VERSION/REPLAY_VERSION required")
        refs = {}
        objects = {}
        for key, rows in sorted(components.items()):
            months = {}
            for row in rows:
                months.setdefault(str(row.get("date") or "static")[:7], []).append(row)
            refs[key] = []
            for month, part in sorted(months.items()):
                raw = canonical(part)
                sha = hashlib.sha256(raw).hexdigest()
                packed = gzip.compress(raw, mtime=0)
                if len(packed) >= HS.MAX_SHARD_BYTES:
                    raise InputVersionConflict(f"input shard too large: {key}/{month}; shard finer")
                refs[key].append(sha)
                objects[sha] = packed
        manifest = {"schema": SCHEMA, "replayVersion": self.replay_version,
                    "dataVersion": self.data_version, "through": through,
                    "policy": policy, "components": refs,
                    "componentHashes": {k:digest(v) for k,v in refs.items()}}
        manifest["sha256"] = digest(manifest)
        folder = self.root / "objects"
        folder.mkdir(parents=True, exist_ok=True)
        for sha, packed in objects.items():
            path = folder / (sha + ".json.gz")
            if not path.exists():
                path.write_bytes(packed)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Preserve every manifest revision without copying any unchanged payload.
        history = self.path.parent / "input-manifests"
        history.mkdir(exist_ok=True)
        text = canonical(manifest).decode() + "\n"
        (history / (manifest["sha256"] + ".json")).write_text(text)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(text)
        temp.replace(self.path)
        return manifest


def pack(*, prices, benchmarks, universe, universe_history, fundamentals, macro,
         vix, vintages, fx, rates, through, calendar_rows):
    components = {}
    for name, frame in sorted(prices.items()):
        kind = "benchmark" if name in benchmarks.values() else "price"
        for row in frame_rows(frame, through):
            components.setdefault(f"{kind}/{row['date'][:7]}", []).append({"ticker":name, **row})
    components["macro"] = frame_rows(macro, through)
    components["vix"] = frame_rows(vix, through)
    components["fx/USD_KRW"] = frame_rows(fx, through)
    components["risk-free/KRW"] = [r for r in rates["events"] if r["date"] <= through]
    components["risk-free/source"] = [{k:v for k,v in rates.items() if k not in ("events", "verifiedThrough")}]
    components["risk-free/coverage"] = [{"date":d.strftime("%Y-%m-%d")} for d in
        pd.date_range("2011-01-01", min(through, rates["verifiedThrough"]))]
    components["universe"] = [{"universe":universe, "memberships":universe_history.memberships}]
    components["fundamentals"] = sorted([
        {"date":r.available_from, "record":asdict(r)}
        for records in fundamentals._records.values() for r in records if r.available_from <= through],
        key=lambda r:(r["date"], canonical(r)))
    for name, frame in sorted((vintages or {}).items()):
        rows = []
        for record in frame.to_dict("records"):
            release = pd.Timestamp(record["realtime_start"]).strftime("%Y-%m-%d")
            if release <= through:
                rows.append({"date":release, "observationDate":pd.Timestamp(record["date"]).strftime("%Y-%m-%d"),
                             "value":float(record["value"]) if pd.notna(record["value"]) else None})
        components["macro-vintage/"+name] = sorted(rows, key=lambda r:(r["date"],r["observationDate"]))
    components["calendar"] = calendar_rows
    return components


def unpack(components):
    prices, vintages, by_ticker = {}, {}, {}
    for name, rows in components.items():
        if name.startswith(("price/", "benchmark/")):
            for row in rows:
                by_ticker.setdefault(row["ticker"], []).append({k:v for k,v in row.items() if k != "ticker"})
        elif name.startswith("macro-vintage/") and rows:
            vintages[name.split("/",1)[1]] = pd.DataFrame([
                {"date":pd.Timestamp(r["observationDate"]), "realtime_start":pd.Timestamp(r["date"]), "value":r["value"]}
                for r in rows])
    prices = {ticker:rows_frame(rows) for ticker,rows in by_ticker.items()}
    records = {}
    for row in components.get("fundamentals", []):
        record = pit_data.FundamentalRecord(**row["record"])
        records.setdefault(record.ticker, []).append(record)
    fundamentals = pit_data.FundamentalStore(records)
    universe = components.get("universe", [{"universe":{}, "memberships":{}}])[0]
    return {"prices":prices, "macro":rows_frame(components.get("macro", [])),
            "vix":rows_frame(components.get("vix", []), series=True), "macro_vintages":vintages,
            "fx":rows_frame(components["fx/USD_KRW"], series=True),
            "risk_free":components["risk-free/KRW"],
            "risk_free_source":{**components["risk-free/source"][0],
                                "verifiedThrough":components["risk-free/coverage"][-1]["date"] if components["risk-free/coverage"] else "1900-01-01"},
            "universe":universe["universe"],
            "universe_history":pit_data.UniverseHistory(universe["memberships"]),
            "fundamental_store":fundamentals}
