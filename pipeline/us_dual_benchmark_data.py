"""SPY and QQQ on one total-return basis, read from the sealed replay-v16 inputs.

WHY NO NEW DOWNLOAD
-------------------
QQQ was never a benchmark here, but it has always been a member of
``config.json universe.US``, so every replay acquisition priced it alongside
the S&P 500 names. The sealed ``replay-v16`` input store therefore already
holds QQQ in its ``price/<YYYY-MM>`` panels, SPY in its ``benchmark/<YYYY-MM>``
panels, both with their distributions in ``corporate-events/<YYYY-MM>``, all
from ONE vendor route (``YAHOO_UNADJUSTED_WITH_ACTIONS``) and ONE adjustment
(``price_adjustment.to_total_return``, ``as-traded-forward-total-return-v1``,
anchored at each ticker's first observed session). Taking both legs from the
same sealed manifest is the strongest same-basis guarantee available: a fresh
QQQ fetch would be a second vintage on a possibly different basis, which is
exactly what ``Benchmark acquisition invariants (v2.8)`` forbid splicing.

The store is read at a pinned ``signal-history`` commit, and every component's
gzip content is checked against the SHA-256 it is addressed by, the same way
``kr_alpha_atlas_benchmark_audit`` reads 069500.KS.

THE DOUBLE-COUNT GUARD
----------------------
The KODEX 200 defect (``docs/weekly-decision/kodex200-benchmark-audit.md``):
a vendor close that was ALREADY distribution-adjusted had Yahoo's
distributions applied a second time, so each ex-date grew by the SQUARE of the
official factor. Two protections live here:

* ``apply_distributions`` refuses any close whose declared basis is not
  ``SPLIT_ADJUSTED_DIVIDEND_UNADJUSTED``. A total-return close (Yahoo
  ``auto_adjust=True``, or this store's own ``Close``) cannot be passed to it.
* ``reconstruct_raw_close`` inverts the forward recipe and
  ``distribution_application_multiples`` measures, per ex-date, how many times
  the factor sits in the stored series. A single application reads 1.0; the
  KODEX defect read 2.0. This proves the RECIPE was applied once to the vendor
  close. Whether the vendor close itself was dividend-unadjusted is a separate
  fact that only an external raw close can settle, and is reported as such.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import price_adjustment as PA

US_MARKET_BENCHMARK = "SPY"
US_GROWTH_BENCHMARK = "QQQ"
# The official US research and weekly-decision benchmark. QQQ is an ADDITIONAL
# alternative and never a retrospective revision of SPY-based evidence.
OFFICIAL_US_BENCHMARK = US_MARKET_BENCHMARK

SOURCE_COMMIT = "704d7db6d5b00def771aba5d2665d0846d6bc776"   # signal-history, observed 2026-10-11
REPLAY_MANIFEST = "ledger/historical/replay-v16/inputs.json"
REPLAY_MANIFEST_SHA256 = "f0781292f508a123c234ded6d28aa8e84a0dc3cc29500e14989dc0b68f53b4d2"
OBJECTS = "ledger/replay-inputs/objects/"

BASIS_RAW = "SPLIT_ADJUSTED_DIVIDEND_UNADJUSTED"
BASIS_TOTAL_RETURN = "TOTAL_RETURN_ADJUSTED"

# Where each benchmark lives inside the sealed store.
PANEL_PREFIX = {US_MARKET_BENCHMARK: "benchmark/", US_GROWTH_BENCHMARK: "price/"}

# A daily move this large in a broad ETF is listed for review, never removed.
JUMP_REVIEW_PCT = 7.0
# A one-day move in the QQQ/SPY ratio this large is a basis break candidate.
RATIO_JUMP_REVIEW_PCT = 4.0
# Max calendar-day age of an FX fixing used for a session.
MAX_FX_AGE_DAYS = 7


class DoubleCountRefused(ValueError):
    """Distributions were requested on a close that already includes them."""


@dataclass(frozen=True)
class SealedReader:
    """Read content-addressed components from a pinned git commit."""
    repo: Path
    commit: str = SOURCE_COMMIT

    def blob(self, path: str) -> bytes:
        return subprocess.check_output(
            ["git", "cat-file", "blob", f"{self.commit}:{path}"], cwd=self.repo)

    def manifest(self) -> dict:
        raw = self.blob(REPLAY_MANIFEST)
        manifest = json.loads(raw)
        if manifest.get("sha256") != REPLAY_MANIFEST_SHA256:
            raise ValueError("FROZEN_REPLAY_MANIFEST_CHANGED")
        return manifest

    def component(self, ref: str) -> list:
        content = gzip.decompress(self.blob(OBJECTS + ref + ".json.gz"))
        if hashlib.sha256(content).hexdigest() != ref:
            raise ValueError(f"FROZEN_COMPONENT_CHANGED: {ref}")
        return json.loads(content)


def _monthly(name: str, prefix: str) -> bool:
    return name.startswith(prefix) and name[len(prefix):len(prefix) + 2] in ("19", "20")


def extract_sealed(reader: SealedReader, tickers=(US_MARKET_BENCHMARK, US_GROWTH_BENCHMARK)) -> dict:
    """Bars, events, FX and USD rate for ``tickers`` from the pinned manifest."""
    manifest = reader.manifest()
    components = manifest["components"]
    wanted = set(tickers)
    bars: dict[str, dict[str, dict]] = {t: {} for t in tickers}
    events: dict[str, list[dict]] = {t: [] for t in tickers}
    used: list[dict] = []
    for name in sorted(components):
        is_bar = any(_monthly(name, PANEL_PREFIX[t]) for t in tickers)
        is_event = _monthly(name, "corporate-events/")
        if not (is_bar or is_event):
            continue
        for ref in components[name]:
            rows = [r for r in reader.component(ref) if r.get("ticker") in wanted]
            if not rows:
                continue
            used.append({"component": name, "sha256": ref, "rows": len(rows)})
            for row in rows:
                ticker = row["ticker"]
                if is_event:
                    events[ticker].append({k: row[k] for k in ("date", "dividend", "split")})
                elif name.startswith(PANEL_PREFIX[ticker]):
                    if row["date"] in bars[ticker]:
                        raise ValueError(f"DUPLICATE_SESSION {ticker} {row['date']}")
                    bars[ticker][row["date"]] = {k: row.get(k) for k in
                                                 ("Open", "High", "Low", "Close", "Volume")}
    lineage = {
        "benchmark": reader.component(components["benchmark/source"][0]),
        "price": reader.component(components["price/source"][0]),
        "adjustment": reader.component(components["corporate-events/source"][0]),
        "fx": reader.component(components["fx/source"][0]),
    }
    fx = {}
    for ref in components["fx/observations"]:
        for row in reader.component(ref):
            fx[row["date"]] = row["value"]
    fed_funds = {}
    for ref in components["macro"]:
        for row in reader.component(ref):
            if row.get("FedFunds") is not None:
                fed_funds[row["date"]] = row["FedFunds"]
    krw_rate = {}
    for ref in components["risk-free/KRW"]:
        for row in reader.component(ref):
            krw_rate[row["date"]] = row["annualRatePct"]
    lineage["riskFreeKrw"] = reader.component(components["risk-free/source"][0])
    return {"bars": bars, "events": events, "lineage": lineage, "fx": fx,
            "fedFunds": fed_funds, "krwPolicyRate": krw_rate, "componentsUsed": used,
            "manifest": {"sha256": manifest["sha256"], "through": manifest["through"],
                         "replayVersion": manifest["replayVersion"],
                         "dataVersion": manifest["dataVersion"]}}


# --------------------------------------------------------------------------- #
# Basis arithmetic
# --------------------------------------------------------------------------- #
def event_frame(index: pd.DatetimeIndex, events: list[dict]) -> pd.DataFrame:
    """Dividends and split ratios placed on ``index`` (1.0 = no split)."""
    frame = pd.DataFrame({"dividend": 0.0, "split": 1.0}, index=index)
    for row in events or []:
        stamp = pd.Timestamp(row["date"])
        position = index.searchsorted(stamp, side="left")
        if position >= len(index):
            continue
        if float(row.get("dividend") or 0) > 0:
            frame.iloc[position, 0] += float(row["dividend"])
        ratio = float(row.get("split") or 0)
        if ratio > 0 and ratio != 1.0:
            frame.iloc[position, 1] *= ratio
    return frame


def apply_distributions(close: pd.Series, events: pd.DataFrame, *, basis: str) -> pd.Series:
    """Forward total-return index from a dividend-UNADJUSTED close.

    This is ``price_adjustment.to_total_return`` behind a basis contract: a
    close that already carries distributions is refused instead of having them
    applied twice.
    """
    if basis != BASIS_RAW:
        raise DoubleCountRefused(
            f"distributions may only be applied to a {BASIS_RAW} close, got {basis}")
    frame = pd.DataFrame({"Close": close.astype(float),
                          PA.DIVIDEND: events["dividend"].reindex(close.index).fillna(0.0),
                          PA.SPLIT: events["split"].reindex(close.index).fillna(1.0)
                          .where(lambda s: s != 1.0, 0.0)})
    rebased, _ = PA.to_total_return(frame)
    return rebased["Close"].rename("tr")


def reconstruct_raw_close(tr: pd.Series, events: pd.DataFrame) -> pd.Series:
    """Invert the forward recipe: the vendor close the stored index was built from.

    The anchor is the first stored session (``FIRST_OBSERVED_SESSION``), so the
    raw close equals the index there. Splits are none for both ETFs over the
    sealed span; one present is refused rather than guessed at.
    """
    if (events["split"] != 1.0).any():
        raise ValueError("SPLIT_PRESENT_RECONSTRUCTION_NOT_DEFINED")
    values = tr.to_numpy(dtype=float)
    dividends = events["dividend"].reindex(tr.index).fillna(0.0).to_numpy(dtype=float)
    raw = np.empty_like(values)
    cumulative = 1.0
    raw[0] = values[0]
    for i in range(1, len(values)):
        if dividends[i] > 0:
            cumulative *= 1.0 / (1.0 - dividends[i] / raw[i - 1])
        raw[i] = values[i] / cumulative
    return pd.Series(raw, index=tr.index, name="raw")


def distribution_application_multiples(tr: pd.Series, raw: pd.Series,
                                       events: pd.DataFrame) -> list[dict]:
    """Per ex-date: log(TR growth / raw growth) / log(single factor). 1 = once."""
    out = []
    dividends = events["dividend"].reindex(tr.index).fillna(0.0)
    for i in np.flatnonzero(dividends.to_numpy() > 0):
        if i == 0:
            continue
        factor = 1.0 / (1.0 - dividends.iloc[i] / raw.iloc[i - 1])
        observed = (tr.iloc[i] / tr.iloc[i - 1]) / (raw.iloc[i] / raw.iloc[i - 1])
        out.append({"date": tr.index[i].strftime("%Y-%m-%d"),
                    "dividend": round(float(dividends.iloc[i]), 6),
                    "yieldPct": round((factor - 1) * 100, 5),
                    "multiple": round(float(np.log(observed) / np.log(factor)), 6)})
    return out


# --------------------------------------------------------------------------- #
# Integrity checks
# --------------------------------------------------------------------------- #
def series_checks(ticker: str, bars: dict[str, dict], events: list[dict]) -> dict:
    dates = sorted(bars)
    index = pd.DatetimeIndex(pd.to_datetime(dates))
    close = pd.Series([bars[d]["Close"] for d in dates], index=index, dtype=float)
    ev = event_frame(index, events)
    raw = reconstruct_raw_close(close, ev)
    roundtrip = apply_distributions(raw, ev, basis=BASIS_RAW)
    multiples = distribution_application_multiples(close, raw, ev)
    returns = close.pct_change().dropna()
    jumps = returns[returns.abs() * 100 >= JUMP_REVIEW_PCT]
    years = (index[-1] - index[0]).days / 365.25
    tr_cagr = (close.iloc[-1] / close.iloc[0]) ** (1 / years) - 1
    px_cagr = (raw.iloc[-1] / raw.iloc[0]) ** (1 / years) - 1
    return {
        "ticker": ticker,
        "sessions": len(dates),
        "firstSession": dates[0], "lastSession": dates[-1],
        "duplicateSessions": len(dates) - len(set(dates)),
        "nonPositiveOrMissingClose": int((~np.isfinite(close) | (close <= 0)).sum()),
        "splitsInSpan": int((ev["split"] != 1.0).sum()),
        "distributions": len(multiples),
        "distributionsDropped": len([e for e in events if float(e.get("dividend") or 0) > 0]) - len(multiples),
        "distributionMultiple": {"min": min(m["multiple"] for m in multiples),
                                 "max": max(m["multiple"] for m in multiples)} if multiples else None,
        "recipeRoundTripMaxRelError": float(((roundtrip / roundtrip.iloc[0]) /
                                             (close / close.iloc[0]) - 1).abs().max()),
        "totalReturnCagrPct": round(tr_cagr * 100, 4),
        "priceOnlyCagrPct": round(px_cagr * 100, 4),
        "impliedDistributionDragPctPerYear": round((tr_cagr - px_cagr) * 100, 4),
        "trailingDistributionYieldPct": _trailing_yields(raw, ev),
        "jumpsForReview": [{"date": d.strftime("%Y-%m-%d"), "returnPct": round(v * 100, 3)}
                           for d, v in jumps.items()],
        "_close": close, "_raw": raw, "_events": ev, "_multiples": multiples,
    }


def _trailing_yields(raw: pd.Series, ev: pd.DataFrame) -> dict:
    """Calendar-year distributions over the year's first close, in percent."""
    out = {}
    for year, group in raw.groupby(raw.index.year):
        paid = ev.loc[group.index, "dividend"].sum()
        out[str(year)] = round(float(paid / group.iloc[0] * 100), 3)
    return out


def ratio_checks(spy: pd.Series, qqq: pd.Series) -> dict:
    common = spy.index.intersection(qqq.index)
    ratio = (qqq.loc[common] / spy.loc[common])
    moves = ratio.pct_change().dropna()
    flagged = moves[moves.abs() * 100 >= RATIO_JUMP_REVIEW_PCT]
    return {"commonSessions": len(common),
            "onlySpy": [d.strftime("%Y-%m-%d") for d in spy.index.difference(qqq.index)],
            "onlyQqq": [d.strftime("%Y-%m-%d") for d in qqq.index.difference(spy.index)],
            "ratioJumpsForReview": [{"date": d.strftime("%Y-%m-%d"), "movePct": round(v * 100, 3)}
                                    for d, v in flagged.items()],
            "maxAbsDailyRatioMovePct": round(float(moves.abs().max() * 100), 3)}


def calendar_checks(index: pd.DatetimeIndex, sessions: list[str]) -> dict:
    """Missing / extra sessions against an exchange session list."""
    expected = pd.DatetimeIndex(pd.to_datetime(sessions))
    expected = expected[(expected >= index[0]) & (expected <= index[-1])]
    return {"expectedSessions": len(expected),
            "missing": [d.strftime("%Y-%m-%d") for d in expected.difference(index)],
            "extra": [d.strftime("%Y-%m-%d") for d in index.difference(expected)]}


def fx_on_sessions(fx_observations: dict[str, float], sessions: pd.DatetimeIndex,
                   max_age_days: int = MAX_FX_AGE_DAYS) -> pd.Series:
    """Latest published fixing on or before each session; stale or absent -> NaN.

    Never forward-filled past ``max_age_days``: a missing fixing is missing.
    """
    obs = pd.Series(fx_observations, dtype=float)
    obs.index = pd.to_datetime(obs.index)
    obs = obs.sort_index().dropna()
    obs = obs[obs > 0]
    positions = obs.index.searchsorted(sessions, side="right") - 1
    values = np.full(len(sessions), np.nan)
    for i, (session, pos) in enumerate(zip(sessions, positions)):
        if pos < 0:
            continue
        if (session - obs.index[pos]).days <= max_age_days:
            values[i] = obs.iloc[pos]
    return pd.Series(values, index=sessions, name="usdkrw")


def snapshot_rows(checks: dict, fx: pd.Series) -> list[dict]:
    """One deterministic row per (ticker, session) for the research snapshot."""
    rows = []
    for ticker, info in sorted(checks.items()):
        close, raw, ev = info["_close"], info["_raw"], info["_events"]
        for stamp in close.index:
            fx_value = fx.get(stamp, np.nan)
            rows.append({
                "ticker": ticker, "date": stamp.strftime("%Y-%m-%d"),
                "totalReturnClose": float(close.loc[stamp]),
                "rawClose": float(raw.loc[stamp]),
                "dividend": float(ev.loc[stamp, "dividend"]),
                "split": float(ev.loc[stamp, "split"]),
                "usdKrw": None if not np.isfinite(fx_value) else float(fx_value),
            })
    return rows


def write_snapshot(rows: list[dict], path: Path) -> str:
    """Deterministic gzip CSV (fixed mtime, fixed float format). Returns SHA-256."""
    header = ["ticker", "date", "totalReturnClose", "rawClose", "dividend", "split", "usdKrw"]
    lines = [",".join(header)]
    for row in rows:
        lines.append(",".join([
            row["ticker"], row["date"], f"{row['totalReturnClose']:.10f}",
            f"{row['rawClose']:.10f}", f"{row['dividend']:.6f}", f"{row['split']:.6f}",
            "" if row["usdKrw"] is None else f"{row['usdKrw']:.4f}"]))
    payload = ("\n".join(lines) + "\n").encode()
    data = gzip.compress(payload, compresslevel=9, mtime=0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def read_snapshot(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, compression="gzip", dtype={"ticker": str, "date": str})
    frame["date"] = pd.to_datetime(frame["date"])
    return frame


def public_checks(info: dict) -> dict:
    return {k: v for k, v in info.items() if not k.startswith("_")}
