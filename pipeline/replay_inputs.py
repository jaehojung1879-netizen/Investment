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
from . import price_adjustment as PA

SCHEMA = "REPLAY_INPUTS_V1"
# Dated price panels are keyed "price/<YYYY-MM>" and "benchmark/<YYYY-MM>", but
# one "benchmark/..." component is not a panel at all: this is the generation's
# static vendor lineage, and its rows carry neither a date nor a Close. Every
# prefix test over the panels has to exclude it BY NAME, or code written for
# panel rows walks straight into it. `unpack` was taught that when the lineage
# component was added and `load` was not, so the audit died with KeyError:
# 'date' on the first replay-v10 run — before it could write a report, which
# left the previous generation's report on disk to be read as this run's
# verdict. One predicate now serves both.
BENCHMARK_SOURCE = "benchmark/source"
PRICE_SOURCE = "price/source"
STATIC_SOURCES = (BENCHMARK_SOURCE, PRICE_SOURCE)


def is_price_panel(name: str) -> bool:
    """True for a dated price/benchmark panel, false for the static lineage."""
    return name.startswith(("price/", "benchmark/")) and name not in STATIC_SOURCES


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


def _by_ticker(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for row in rows:
        out.setdefault(row.get("ticker"), []).append(row)
    return out


def reconcile_prefix(name: str, sealed: list[dict], fresh: list[dict],
                     sealed_tickers: set) -> tuple[list[str], list[str]]:
    """Which tickers the vendor failed to serve, and which it served too many of.

    Raises if the vendor CONTRADICTS a sealed row, which is the only difference
    that means the published evidence would move.

    WHY THIS IS NOT A WEAKENING OF THE SEAL
    ---------------------------------------
    Yahoo answers differently on different days for the same delisted ticker.
    Measured across two production acquisitions of the same generation one hour
    apart, `constituentsWithoutPriceHistoryCount` moved 286 -> 282: four of the
    326 former index members flipped, with no code change between the runs. The
    errors are `YFTzMissingError('possibly delisted; no timezone found')` and
    `YFPricesMissingError(...)`, and they are intermittent.

    A ticker that vanishes takes its whole decade of rows out of every monthly
    shard it appeared in, so the byte-exact prefix check then refuses the run —
    replay-v14 run #55 died on `corporate-events/2015-03` for exactly that. The
    check was right that the bytes changed and wrong about what it meant: no
    published NUMBER moved, a vendor simply declined to repeat itself.

    Left unfixed this is the disease that killed v7 through v10 in a new form.
    A generation could be acquired once and never extended, because acquisition
    is how new replay dates enter, so the evidence base would be frozen at its
    first cutoff and every further date would need a fresh, incomparable
    generation.

    So within a generation the SEALED rows are the authority:

    * a sealed ticker the vendor did not serve is restored from the store — the
      rows are immutable, re-downloading them can only reproduce them;
    * a ticker that was never sealed contributes nothing before the cutoff, so
      it cannot write history it was absent from;
    * a sealed ticker whose values come back DIFFERENT is still a conflict, and
      still stops the run.

    The restored prefix is safe to splice onto a freshly fetched suffix only
    because of replay-v11: on the as-traded forward total-return basis a
    published value never moves, so the two vintages are on one basis. On
    Yahoo's back-anchored adjusted close it would have been wrong.
    """
    sealed_by, fresh_by = _by_ticker(sealed), _by_ticker(fresh)
    restored, ignored = [], []
    for ticker in sorted(set(sealed_by) | set(fresh_by), key=lambda t: (t is None, t)):
        if ticker not in sealed_tickers:
            ignored.append(ticker)
            continue
        if ticker not in fresh_by:
            restored.append(ticker)
            continue
        if digest(fresh_by[ticker]) != digest(sealed_by.get(ticker, [])):
            raise InputVersionConflict(
                f"{name}: {ticker} contradicts the sealed prefix; "
                f"new DATA_VERSION/REPLAY_VERSION required")
    return restored, ignored


# Components whose rows carry both a date and a ticker, and so can be
# reconciled per name. Everything else - macro, fx, calendar, the static
# lineages - is frozen whole, because a change there is a change of policy.
def is_reconcilable(name: str) -> bool:
    return is_price_panel(name) or (name.startswith("corporate-events/")
                                    and name != "corporate-events/source")


class InputStore:
    def __init__(self, ledger, replay_version: str, data_version: str):
        self.ledger = Path(ledger)
        self.root = self.ledger / "replay-inputs"
        self.path = self.ledger / "historical" / replay_version / "inputs.json"
        self.replay_version, self.data_version = replay_version, data_version
        # What the last commit had to repair, for the diagnostics to publish.
        self.reconciliation = {"restored": set(), "ignored": set(),
                               "components": []}

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
            if valuation_only and not (name.startswith(("price/", "benchmark/", "fx/", "risk-free/"))
                                       or name == "corporate-actions"):
                continue
            rows = []
            for ref in refs:
                part = self._read(ref)
                if valuation_only and is_price_panel(name):
                    part = [{k:r[k] for k in ("date", "ticker", "Close")} for r in part]
                rows.extend(part)
            result[name] = rows
        return result

    def load_component(self, name: str, manifest=None) -> list[dict]:
        """Load one component without inflating the full multi-GB snapshot."""
        manifest = manifest or self.manifest()
        if not manifest:
            raise InputVersionConflict("no frozen inputs in this generation; first run must acquire inputs")
        rows = []
        for ref in manifest["components"].get(name, []):
            rows.extend(self._read(ref))
        return rows

    def commit(self, components: dict[str, list[dict]], *, through: str, policy: dict):
        prior = self.manifest()
        if prior:
            if through < prior["through"]:
                raise InputVersionConflict("input cutoff cannot move backwards")
            old = self.load(prior)
            if policy != prior["policy"]:
                raise InputVersionConflict("replay policy changed; new DATA_VERSION/REPLAY_VERSION required")
            # The generation's universe, pinned at its first acquisition. A name
            # outside it cannot write rows into an already-published month.
            sealed_tickers = {row["ticker"] for name, rows in old.items()
                              if is_reconcilable(name)
                              for row in rows if row.get("ticker")}
            components = dict(components)
            for key in sorted(set(old) | set(components)):
                # Undated/static inputs are frozen whole; dated inputs may only
                # append beyond the global sealed cutoff. Missing rows are sealed too.
                rows = components.get(key, [])
                prefix = [r for r in rows
                          if str(r.get("date") or "") <= prior["through"]]
                sealed = old.get(key, [])
                if digest(prefix) == digest(sealed):
                    continue
                if not is_reconcilable(key):
                    raise InputVersionConflict(f"{key}: published input prefix changed/recovered; new DATA_VERSION/REPLAY_VERSION required")
                # A vendor that declines to repeat itself has not changed the
                # evidence. One that contradicts it has, and still raises here.
                restored, ignored = reconcile_prefix(key, sealed, prefix,
                                                     sealed_tickers)
                self.reconciliation["restored"].update(restored)
                self.reconciliation["ignored"].update(ignored)
                if restored or ignored:
                    self.reconciliation["components"].append(key)
                suffix = [r for r in rows
                          if str(r.get("date") or "") > prior["through"]]
                # pack() emits each month ticker-major, date-ascending; the
                # spliced month must come back in that same order or the next
                # run's byte-exact check fails on ordering alone.
                components[key] = sorted(
                    sealed + suffix,
                    key=lambda r: (str(r.get("ticker") or ""), str(r.get("date") or "")))
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
         vix, vintages, fx, rates, through, calendar_rows, fx_observations=None,
         fx_source_map=None, price_recovery=None, corporate_actions=None,
         benchmark_lineage=None, price_lineage=None):
    components = {}
    for name, frame in sorted(prices.items()):
        kind = "benchmark" if name in benchmarks.values() else "price"
        for row in frame_rows(frame, through):
            # The dividend and split that produced this session's total-return
            # level are evidence in their own right, and they are zero on all
            # but a handful of sessions. Sealing them sparsely in their own
            # component keeps the price shards the size the 100 MB blob limit
            # was sharded for, and makes the adjustment auditable row by row.
            event = {key: row.pop(key) for key in PA.EVENT_COLUMNS if key in row}
            components.setdefault(f"{kind}/{row['date'][:7]}", []).append({"ticker":name, **row})
            dividend = float(event.get(PA.DIVIDEND) or 0.0)
            split = float(event.get(PA.SPLIT) or 1.0)
            if dividend > 0 or split != 1.0:
                components.setdefault(f"corporate-events/{row['date'][:7]}", []).append(
                    {"date":row["date"], "ticker":name,
                     "dividend":dividend, "split":split})
    # Which vendor served each region's sessions, and how far the second vendor
    # disagreed on the ones they both quote. Static and generation-local, for
    # the same reason the benchmark lineage is: a later run may not quietly
    # re-source a region whose history is already sealed.
    components[PRICE_SOURCE] = sorted(
        price_lineage or [], key=lambda row: str(row.get("region", "")))
    components["corporate-events/source"] = [{
        "vendor":"YAHOO_UNADJUSTED_WITH_ACTIONS",
        "adjustment":PA.ADJUSTMENT_VERSION,
        "basis":"AS_TRADED_CLOSE_WITH_FORWARD_ACCUMULATED_TOTAL_RETURN",
        "anchor":"FIRST_OBSERVED_SESSION"}]
    # Static, generation-local identity.  Benchmark snapshots are shared as an
    # operational cache, so their global index cannot be the authority for an
    # already-started replay generation.
    components[BENCHMARK_SOURCE] = sorted(
        benchmark_lineage or [], key=lambda row: (row.get("region", ""), row.get("ticker", "")))
    components["macro"] = frame_rows(macro, through)
    components["vix"] = frame_rows(vix, through)
    components["fx/USD_KRW"] = frame_rows(fx, through)
    components["fx/observations"] = frame_rows(fx_observations, through)
    components["fx/source-map"] = [r for r in (fx_source_map or []) if r["date"] <= through]
    components["fx/source"] = [{"vendor":"FEDERAL_RESERVE_H10", "seriesId":"DEXKOUS",
                                "units":"KRW_PER_USD",
                                "resolution":"LATEST_PUBLISHED_FIXING_ON_OR_BEFORE_SESSION"}]
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
    components["recovery/kr-systemic"] = [
        {"date":row.get("date") or (row.get("dates") or [""])[0], "kind":kind, **row}
        for kind in ("systemicDates", "accepted", "rejected")
        for row in ((price_recovery or {}).get(kind) or [])]
    components["recovery/source"] = [{
        "version":(price_recovery or {}).get("version"),
        "policy":"ONLY_SYSTEMIC_PRIMARY_GAPS_WITH_VALIDATED_INDEPENDENT_RETURN_BRIDGE"}]
    components["corporate-actions"] = ([{"book":corporate_actions}]
                                        if corporate_actions is not None else [])
    return components


def unpack(components):
    prices, vintages, by_ticker = {}, {}, {}
    for name, rows in components.items():
        if is_price_panel(name):
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
            "fx_observations":rows_frame(components.get("fx/observations", []), series=True),
            "fx_source_map":components.get("fx/source-map", []),
            "fx_source":(components.get("fx/source") or [{}])[0],
            "price_recovery":components.get("recovery/kr-systemic", []),
            "corporate_actions":((components.get("corporate-actions") or [{"book":{"actions":[]}}])[0]
                                  .get("book", {"actions":[]})),
            "benchmark_lineage":components.get(BENCHMARK_SOURCE, []),
            "price_lineage":components.get(PRICE_SOURCE, []),
            "corporate_events":[row for name, rows in sorted(components.items())
                                if name.startswith("corporate-events/")
                                and name != "corporate-events/source"
                                for row in rows],
            "adjustment":(components.get("corporate-events/source") or [{}])[0],
            "universe":universe["universe"],
            "universe_history":pit_data.UniverseHistory(universe["memberships"]),
            "fundamental_store":fundamentals}
