"""Where a replay benchmark series comes from, and why it can be trusted.

On 2026-08-19 and 2026-08-20 the *identical* commit produced KR benchmark
coverage of 452/452 and then 0/452. Nothing in this repository changed between
those two runs; the vendor simply returned one row for ``^KS200`` instead of a
decade. The same thing happened again on 08-23 and 08-24, and on 08-25 the
preflight added by the previous fix finally reported it out loud::

    ^KS200: 1 sessions 2026-08-25 .. 2026-08-25
    benchmark preflight KR 126D: 0.0% (0/327628; 1 benchmark sessions)

That is not a timezone or a calendar-mixing bug — those would move dates, not
delete fifteen years of them. It is an intermittent vendor failure, and it was
destructive because ``compute_outcomes`` re-derives every outcome from a freshly
downloaded panel on every run. One bad response therefore erased the Korean half
of the evidence base for that night, and the published headline moved from
+1.96%/yr to -2.18%/yr on the same ledger.

Two mechanisms close that hole. They are different jobs and both are needed:

1. **Plausibility.** A benchmark panel far shorter than the span it was asked
   for is a failed download, not a market with no sessions. Rejecting it at the
   source turns a silent truncation into a named, visible failure.

2. **A committed snapshot.** The last panel that passed (1) is stored in the
   ledger. When every source fails plausibility the replay continues on the
   snapshot instead of on nothing. That is not a substitute value: it is the
   same vendor's own observations, captured earlier, versioned in git, and
   labelled ``SNAPSHOT_FALLBACK`` in the diagnostics so no reader can mistake it
   for a fresh fetch. A vendor outage then costs the newest grid dates — which
   have not matured at 126 days anyway — instead of costing a decade.

Redundancy is across **vendors, never across indices**. Two sources for
``^KS200`` must both be KOSPI 200. Substituting KOSPI, or a tracking ETF, when
the index is unavailable would change what "excess return" means halfway through
the history — a quieter and worse error than the outage itself.

An accepted candidate is used *alone*, never merged with the snapshot. Adjusted
closes are rescaled retroactively on every dividend, so a series stitched from
two fetch vintages carries two adjustment factors and its returns across the
join are wrong. One vintage per published series, always.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from . import historical_store as HS
from .market_dates import normalize_daily_series

SNAPSHOT_DIR = "benchmarks"
SNAPSHOT_INDEX = "index.json"
COVERAGE_HISTORY = "benchmark-coverage-history.jsonl"

STATUS_VENDOR = "VENDOR"
STATUS_SNAPSHOT = "SNAPSHOT_FALLBACK"
STATUS_UNAVAILABLE = "UNAVAILABLE"

# A candidate must reproduce this share of the sessions the snapshot already
# knows about, up to the candidate's own last session. The tolerance is not
# zero because a vendor may legitimately drop a single halted session; it is
# nowhere near loose enough to admit a truncated panel.
MIN_SNAPSHOT_COVERAGE_PCT = 98.0

# Bootstrap plausibility, used only when there is no snapshot to compare with.
# Real exchanges run ~245-252 sessions a year; anything under this is a failed
# download wearing the shape of a success.
MIN_SESSIONS_PER_YEAR = 180

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def _slug(ticker: str) -> str:
    """Filename for a ticker, keeping distinct tickers distinct.

    Unsafe characters become ``_`` and nothing is stripped, so ``^KS200`` and
    ``KS200`` do not collide on a case-insensitive filesystem.
    """
    return _UNSAFE.sub("_", str(ticker or "unknown"))


# --------------------------------------------------------------------------- #
# Sources
# --------------------------------------------------------------------------- #
def source_specs(ticker: str, configured: dict | None) -> list[dict]:
    """Ordered vendor list for one benchmark; Yahoo alone when unconfigured."""
    specs = ((configured or {}).get(ticker)) or []
    out: list[dict] = []
    for spec in specs:
        kind = str((spec or {}).get("kind") or "").strip().lower()
        symbol = str((spec or {}).get("symbol") or "").strip()
        if kind and symbol:
            out.append({"kind": kind, "symbol": symbol})
    return out or [{"kind": "yahoo", "symbol": ticker}]


def _yahoo_close(symbol: str, start: str) -> pd.Series | None:
    """Yahoo via the same retrying path the universe uses, so one policy."""
    from .datafeed import fetch_prices

    frame = fetch_prices([symbol], start, batch=1).get(symbol)
    if frame is None or "Close" not in frame:
        return None
    return _clean(frame["Close"])


def _fdr_close(symbol: str, start: str) -> pd.Series | None:
    """FinanceDataReader — an independent route for the Korean indices."""
    try:
        import FinanceDataReader as fdr

        frame = fdr.DataReader(symbol, start)
    except Exception as exc:  # pragma: no cover - network dependent
        print(f"    warning: FinanceDataReader {symbol} failed: {exc}")
        return None
    if frame is None or getattr(frame, "empty", True) or "Close" not in frame:
        return None
    return _clean(frame["Close"])


FETCHERS = {"yahoo": _yahoo_close, "fdr": _fdr_close}


def _clean(series: pd.Series | None) -> pd.Series | None:
    if series is None:
        return None
    values = pd.to_numeric(series, errors="coerce").dropna()
    values = values[values > 0]
    if not len(values):
        return None
    return normalize_daily_series(values).rename("Close")


# --------------------------------------------------------------------------- #
# Snapshot storage
# --------------------------------------------------------------------------- #
def snapshot_root(ledger_dir: str | Path) -> Path:
    return Path(ledger_dir) / SNAPSHOT_DIR


def snapshot_path(ledger_dir: str | Path, ticker: str) -> Path:
    return snapshot_root(ledger_dir) / f"{_slug(ticker)}.jsonl.gz"


def read_snapshot(ledger_dir: str | Path, ticker: str) -> pd.Series | None:
    rows = HS.read_jsonl(snapshot_path(ledger_dir, ticker))
    if not rows:
        return None
    index, values = [], []
    for row in rows:
        date, close = row.get("date"), row.get("close")
        if date is None or close is None:
            continue
        index.append(date)
        values.append(close)
    if not index:
        return None
    return _clean(pd.Series(values, index=pd.to_datetime(index, errors="coerce")))


def write_snapshot(ledger_dir: str | Path, ticker: str, series: pd.Series) -> bool:
    """Store a benchmark series. Returns True when the bytes actually changed.

    Serialization is the ledger's deterministic gzip, so a snapshot that did not
    move re-serializes identically and git records no change — the same property
    that keeps the nightly shard commits small.
    """
    # Stored at full float64 precision, deliberately. ``json`` emits the
    # shortest string that round-trips, so a snapshot reload is bit-identical to
    # the fetch it came from. Rounding to six places here is enough to move a
    # 126-day return in the last digit, and the whole point of the snapshot is
    # that an outage night reproduces the previous night exactly.
    rows = [{"date": stamp.strftime("%Y-%m-%d"), "close": float(value)}
            for stamp, value in series.sort_index().items()]
    payload = HS.encode(rows)
    path = snapshot_path(ledger_dir, ticker)
    if path.exists() and path.read_bytes() == payload:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return True


def write_snapshot_index(ledger_dir: str | Path, entries: dict) -> None:
    """Which vendor produced each stored snapshot, and how far it reaches.

    Deliberately carries no wall-clock timestamp: an unchanged snapshot must
    produce an unchanged index, or every run commits a diff for nothing.
    """
    root = snapshot_root(ledger_dir)
    root.mkdir(parents=True, exist_ok=True)
    (root / SNAPSHOT_INDEX).write_text(
        json.dumps(entries, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")


def read_snapshot_index(ledger_dir: str | Path) -> dict:
    path = snapshot_root(ledger_dir) / SNAPSHOT_INDEX
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


# --------------------------------------------------------------------------- #
# Acceptance
# --------------------------------------------------------------------------- #
def _expected_minimum_sessions(start: str, last: pd.Timestamp) -> int:
    """Floor on a plausible panel length for the requested span.

    Half the conservative session rate, so a genuinely short listing history or
    a market with an unusual holiday year is never rejected — the bar exists to
    catch a panel that is short by orders of magnitude, not by a few percent.
    """
    years = max((pd.Timestamp(last) - pd.Timestamp(start)).days, 0) / 365.25
    return int(max(MIN_SESSIONS_PER_YEAR * years * 0.5, 20))


def snapshot_coverage_pct(candidate: pd.Series, snapshot: pd.Series) -> float:
    """Share of known sessions, up to the candidate's own last session.

    Bounding the window at the candidate's last session forgives a vendor that
    has not published today yet. It does not forgive a truncated panel: a
    one-row response dated today still has the whole snapshot in its window.
    """
    if snapshot is None or not len(snapshot):
        return 100.0
    if candidate is None or not len(candidate):
        return 0.0
    window = snapshot.index[snapshot.index <= candidate.index[-1]]
    if not len(window):
        return 0.0
    matched = int(window.isin(candidate.index).sum())
    return round(matched / len(window) * 100.0, 4)


def evaluate_candidate(candidate: pd.Series | None, snapshot: pd.Series | None, *,
                       start: str,
                       min_coverage_pct: float = MIN_SNAPSHOT_COVERAGE_PCT) -> dict:
    """Accept or reject one vendor response, with the reason it was rejected."""
    if candidate is None or not len(candidate):
        return {"accepted": False, "reason": "no_data", "sessions": 0,
                "snapshotCoveragePct": None, "minimumSessions": None}
    sessions = int(len(candidate))
    if snapshot is not None and len(snapshot):
        coverage = snapshot_coverage_pct(candidate, snapshot)
        accepted = coverage >= float(min_coverage_pct)
        return {
            "accepted": accepted,
            "reason": None if accepted else "below_known_session_calendar",
            "sessions": sessions,
            "snapshotCoveragePct": coverage,
            "minimumSessions": None,
        }
    minimum = _expected_minimum_sessions(start, candidate.index[-1])
    accepted = sessions >= minimum
    return {
        "accepted": accepted,
        "reason": None if accepted else "implausibly_short_for_requested_span",
        "sessions": sessions,
        "snapshotCoveragePct": None,
        "minimumSessions": minimum,
    }


def resolve_one(ticker: str, specs: list[dict], *, start: str,
                snapshot: pd.Series | None,
                min_coverage_pct: float = MIN_SNAPSHOT_COVERAGE_PCT,
                fetchers: dict | None = None) -> dict:
    """Pick a trustworthy series for one benchmark, or fall back to the snapshot."""
    fetchers = fetchers or FETCHERS
    candidates: list[dict] = []
    accepted: list[tuple[dict, pd.Series]] = []

    for spec in specs:
        fetcher = fetchers.get(spec["kind"])
        row = {"source": spec["kind"], "symbol": spec["symbol"]}
        if fetcher is None:
            row.update({"accepted": False, "reason": "unknown_source_kind",
                        "sessions": 0})
            candidates.append(row)
            continue
        try:
            series = _clean(fetcher(spec["symbol"], start))
        except Exception as exc:  # pragma: no cover - network dependent
            print(f"    warning: {spec['kind']} {spec['symbol']} raised: {exc}")
            series = None
        verdict = evaluate_candidate(series, snapshot, start=start,
                                     min_coverage_pct=min_coverage_pct)
        row.update(verdict)
        if series is not None and len(series):
            row["firstSession"] = series.index[0].strftime("%Y-%m-%d")
            row["lastSession"] = series.index[-1].strftime("%Y-%m-%d")
        candidates.append(row)
        if verdict["accepted"]:
            accepted.append((row, series))

    if accepted:
        # Same rule the market-tape fetcher uses: freshest first, then longest.
        row, series = max(accepted, key=lambda item: (item[1].index[-1], len(item[1])))
        return {
            "ticker": ticker, "status": STATUS_VENDOR, "series": series,
            "source": row["source"], "symbol": row["symbol"],
            "sessions": int(len(series)),
            "firstSession": series.index[0].strftime("%Y-%m-%d"),
            "lastSession": series.index[-1].strftime("%Y-%m-%d"),
            "candidates": candidates,
        }

    if snapshot is not None and len(snapshot):
        return {
            "ticker": ticker, "status": STATUS_SNAPSHOT, "series": snapshot,
            "source": STATUS_SNAPSHOT, "symbol": None,
            "sessions": int(len(snapshot)),
            "firstSession": snapshot.index[0].strftime("%Y-%m-%d"),
            "lastSession": snapshot.index[-1].strftime("%Y-%m-%d"),
            "candidates": candidates,
        }

    return {
        "ticker": ticker, "status": STATUS_UNAVAILABLE, "series": None,
        "source": None, "symbol": None, "sessions": 0,
        "firstSession": None, "lastSession": None,
        "candidates": candidates,
    }


def resolve(benchmarks: dict[str, str], sources: dict | None, *, start: str,
            ledger_dir: str | Path,
            min_coverage_pct: float = MIN_SNAPSHOT_COVERAGE_PCT,
            fetchers: dict | None = None) -> tuple[dict[str, pd.Series], dict]:
    """Resolve every regional benchmark. Returns (series by ticker, diagnostics).

    Only a vendor-sourced series updates the stored snapshot. A snapshot
    fallback deliberately leaves the file untouched, so a run that could not
    reach the vendor cannot quietly shorten the record for the next one.
    """
    series_by_ticker: dict[str, pd.Series] = {}
    by_region: dict[str, dict] = {}
    index = read_snapshot_index(ledger_dir)
    degraded, unavailable, changed = [], [], []

    for region, ticker in (benchmarks or {}).items():
        snapshot = read_snapshot(ledger_dir, ticker)
        result = resolve_one(
            ticker, source_specs(ticker, sources), start=start, snapshot=snapshot,
            min_coverage_pct=min_coverage_pct, fetchers=fetchers)
        series = result.pop("series")
        result["snapshotSessions"] = int(len(snapshot)) if snapshot is not None else 0

        if series is not None and len(series):
            series_by_ticker[ticker] = series
            if result["status"] == STATUS_VENDOR and write_snapshot(ledger_dir, ticker, series):
                changed.append(ticker)
            if result["status"] == STATUS_VENDOR:
                index[ticker] = {
                    "source": result["source"], "symbol": result["symbol"],
                    "sessions": result["sessions"],
                    "firstSession": result["firstSession"],
                    "lastSession": result["lastSession"],
                }
        if result["status"] == STATUS_SNAPSHOT:
            degraded.append(region)
        elif result["status"] == STATUS_UNAVAILABLE:
            unavailable.append(region)
        by_region[region] = result

    write_snapshot_index(ledger_dir, index)
    return series_by_ticker, {
        "policy": "VENDOR_REDUNDANCY_THEN_COMMITTED_SNAPSHOT",
        "minSnapshotCoveragePct": float(min_coverage_pct),
        "minSessionsPerYearForBootstrap": MIN_SESSIONS_PER_YEAR,
        "byRegion": by_region,
        "degradedRegions": sorted(degraded),
        "unavailableRegions": sorted(unavailable),
        "snapshotsUpdated": sorted(changed),
        "indexMixingForbidden": True,
    }


def describe(diagnostics: dict) -> list[str]:
    """Human-readable lines for the CI log."""
    lines = []
    for region, row in sorted((diagnostics.get("byRegion") or {}).items()):
        detail = f"{row['sessions']} sessions"
        if row.get("firstSession"):
            detail += f" {row['firstSession']} .. {row['lastSession']}"
        lines.append(f"  benchmark {region} {row['ticker']}: {row['status']}"
                     f" via {row.get('source') or '-'} ({detail})")
        for candidate in row.get("candidates") or []:
            verdict = "accepted" if candidate.get("accepted") else \
                f"rejected:{candidate.get('reason')}"
            extra = ""
            if candidate.get("snapshotCoveragePct") is not None:
                extra = f", known-calendar {candidate['snapshotCoveragePct']}%"
            elif candidate.get("minimumSessions") is not None:
                extra = f", minimum {candidate['minimumSessions']}"
            lines.append(f"      {candidate['source']}:{candidate['symbol']} "
                         f"{candidate.get('sessions', 0)} sessions -> {verdict}{extra}")
    return lines


# --------------------------------------------------------------------------- #
# Coverage history
# --------------------------------------------------------------------------- #
def coverage_history_path(ledger_dir: str | Path) -> Path:
    return Path(ledger_dir) / COVERAGE_HISTORY


def read_coverage_history(ledger_dir: str | Path) -> list[dict]:
    return HS.read_jsonl(coverage_history_path(ledger_dir))


def record_coverage(ledger_dir: str | Path, *, run_date: str, horizon: int,
                    coverage: dict, benchmark_diagnostics: dict) -> list[dict]:
    """Append one row per region so a coverage regression is visible as a trend.

    The 08-19 -> 08-20 collapse left no trace anywhere: the only way to find it
    afterwards was to rewind the branch and recount the shards by hand. A
    committed history makes the same event a one-line diff.
    """
    by_region = coverage.get("benchmarkCoverageByRegion") or {}
    signals_by_region = coverage.get("signalsByRegion") or {}
    rows = [row for row in read_coverage_history(ledger_dir)
            if row.get("date") != run_date]
    for region in sorted(set(by_region) | set(signals_by_region)):
        cell = (by_region.get(region) or {}).get(str(horizon)) or {}
        source = ((benchmark_diagnostics.get("byRegion") or {}).get(region) or {})
        rows.append({
            "date": run_date,
            "region": region,
            "horizon": int(horizon),
            "coveragePct": cell.get("coveragePct"),
            "matchedBenchmarkReturns": cell.get("matchedBenchmarkReturns"),
            "maturedAbsoluteReturns": cell.get("maturedAbsoluteReturns"),
            "benchmarkStatus": source.get("status"),
            "benchmarkSource": source.get("source"),
            "benchmarkSessions": source.get("sessions"),
        })
    rows.sort(key=lambda row: (str(row.get("date")), str(row.get("region"))))
    path = coverage_history_path(ledger_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8")
    return rows


def coverage_regression(history: list[dict], *, region: str,
                        drop_pct_points: float = 5.0) -> dict | None:
    """The previous reading for a region, when today fell materially below it."""
    rows = [row for row in history if row.get("region") == region
            and row.get("coveragePct") is not None]
    if len(rows) < 2:
        return None
    latest, previous = rows[-1], rows[-2]
    drop = float(previous["coveragePct"]) - float(latest["coveragePct"])
    if drop < float(drop_pct_points):
        return None
    return {"region": region, "previousDate": previous.get("date"),
            "previousCoveragePct": previous.get("coveragePct"),
            "coveragePct": latest.get("coveragePct"),
            "dropPctPoints": round(drop, 4)}
