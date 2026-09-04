"""Can the macro panel actually be vintaged, series by series, back to 2013?

WHY THIS EXISTS. `dataIntegrity.integrityGate` fails on `vintageMacro`
because `macroPitStatus` reads REVISED_HISTORY: `historicalReplay.
macroVintageSeries` is empty, so the replay conditions its regime on the
numbers as revised since rather than as printed at the time. The machinery to
fix that is already built — `datafeed.fetch_macro_vintages` pulls ALFRED
release history and `pit_data.MacroVintageView` rebuilds each column from the
prints that existed on the date. Nothing has opted in.

WHY NOT JUST OPT EVERYTHING IN. Because a vintaged column can be WORSE than a
revised one, and the failure is silent. `vintage_column` keeps only the prints
published by the as-of date; if ALFRED's release history for a series starts
in 2019, then on 2013-06-01 it returns an EMPTY series, `MacroVintageView.
as_of` reindexes it to NaN, and that column goes dark for the first six years
of the replay — while `pit_status` upgrades to PIT_EXACT and the integrity
gate turns green. Trading a revised number for no number at all, and getting
a better label for it, is the exact shape of error this repo refuses.

So the question is not "does ALFRED have this series" but "does its release
history reach back far enough to serve the replay's first dates". That is
what this measures, per series, against the real API.

WHAT IT DOES NOT DO. Nothing is written to config and nothing is opted in.
The gate wants PIT_EXACT, which needs EVERY column in the panel, so the
decision is one decision about the whole panel and it belongs to a human
reading this report.

DERIVED COLUMNS. `Yield_Curve` has no FRED series id — it is 10Y minus 2Y —
so ALFRED can never answer for it. `pit_data.DERIVED_MACRO_COLUMNS` records
that and `MacroVintageView` rebuilds it from its vintaged inputs; this probe
reports it as DERIVED and resolves its verdict from theirs, so the panel
verdict counts every column the replay will actually see.

Usage:  python scripts/probe_alfred_macro_vintages.py [--output alfred-probe.json]
        [--start 2013-01-01] [--as-of 2013-06-03,2018-06-01]
        [--series Treasury_10Y,Payrolls]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import pit_data  # noqa: E402
from pipeline.config import Config, load_config  # noqa: E402

# Verdicts, worst last. The panel takes the worst of its columns because
# PIT_EXACT is an all-or-nothing claim about the whole frame.
USABLE = "VINTAGE_USABLE"
TRUNCATED = "VINTAGE_TRUNCATED"
EMPTY = "NO_VINTAGES"
FAILED = "FETCH_FAILED"
VERDICT_ORDER = (USABLE, TRUNCATED, EMPTY, FAILED)


def _stamp(value):
    ts = pd.Timestamp(value)
    return None if pd.isna(ts) else ts.date().isoformat()


def summarize_releases(releases: pd.DataFrame | None, *, start: str,
                       as_of_dates: list[str]) -> dict:
    """What one series' ALFRED history can and cannot serve.

    ``releases`` is ALFRED long form: ``date`` (period described),
    ``realtime_start`` (when that print first appeared), ``value``.

    The decisive field is ``asOf[*].periodsServed``. A series can have tens of
    thousands of rows and still serve nothing on an early replay date, because
    every one of those rows was published later. Row counts and a first
    observation date do not answer that; reconstructing the column does, so
    that is what this runs — the same `vintage_column` the replay uses, not a
    re-implementation of it.
    """
    if releases is None or not len(releases):
        return {"verdict": EMPTY, "rows": 0,
                "reason": "ALFRED returned no release rows"}

    frame = releases.copy()
    frame["date"] = pd.to_datetime(frame.get("date"), errors="coerce")
    frame["realtime_start"] = pd.to_datetime(frame.get("realtime_start"),
                                             errors="coerce")
    frame = frame.dropna(subset=["date", "realtime_start"])
    if frame.empty:
        return {"verdict": EMPTY, "rows": int(len(releases)),
                "reason": "no rows carried both a period and a publication date"}

    start_ts = pd.Timestamp(start)
    first_published = frame["realtime_start"].min()
    # A period observed at or before the replay start, published at or before
    # it. Without at least one of these the first replay dates have nothing.
    visible_at_start = frame[(frame["realtime_start"] <= start_ts)
                             & (frame["date"] <= start_ts)]

    per_as_of = []
    for as_of in as_of_dates:
        column = pit_data.vintage_column(frame, as_of)
        revised = frame.groupby("date", sort=True)["value"].last()
        revised = revised[revised.index <= pd.Timestamp(as_of)]
        per_as_of.append({
            "asOf": as_of,
            "periodsServed": int(len(column)),
            # What the same span looks like using every print regardless of
            # when it appeared — i.e. what REVISED_HISTORY would have shown.
            "periodsInRevisedHistory": int(len(revised)),
            "lastPeriodServed": _stamp(column.index.max()) if len(column) else None,
        })

    # Revisions are why this matters at all: a series ALFRED never revised is
    # already the number that was printed, and vintaging it changes nothing
    # except the label it may honestly carry.
    per_period = frame.groupby("date")["realtime_start"].nunique()
    revised_periods = int((per_period > 1).sum())

    verdict = USABLE if len(visible_at_start) else TRUNCATED
    if verdict == TRUNCATED:
        reason = (f"earliest print {_stamp(first_published)} is after the replay "
                  f"start {start}; opting in would blank this column until then")
    else:
        reason = None
    return {
        "verdict": verdict,
        "rows": int(len(frame)),
        "firstPublished": _stamp(first_published),
        "lastPublished": _stamp(frame["realtime_start"].max()),
        "firstPeriod": _stamp(frame["date"].min()),
        "lastPeriod": _stamp(frame["date"].max()),
        "periodsVisibleAtReplayStart": int(len(visible_at_start)),
        "periodsEverRevised": revised_periods,
        "periodsTotal": int(len(per_period)),
        "asOf": per_as_of,
        "reason": reason,
    }


def resolve_derived(summaries: dict[str, dict]) -> dict[str, dict]:
    """Verdicts for the panel columns that are computed, not fetched.

    A difference of two vintaged series carries their vintage, so the derived
    column inherits the WORSE of its inputs — and an input that was never
    fetched leaves it unresolved rather than passing.
    """
    out: dict[str, dict] = {}
    for name, inputs in pit_data.DERIVED_MACRO_COLUMNS.items():
        parts = {part: (summaries.get(part) or {}).get("verdict") for part in inputs}
        missing = [part for part, verdict in parts.items() if verdict is None]
        if missing:
            verdict, reason = FAILED, f"input series not measured: {missing}"
        else:
            verdict = max(parts.values(), key=VERDICT_ORDER.index)
            reason = (None if verdict == USABLE
                      else f"inherited from its inputs {parts}")
        out[name] = {"verdict": verdict, "derivedFrom": list(inputs),
                     "inputVerdicts": parts, "reason": reason}
    return out


def panel_verdict(summaries: dict[str, dict]) -> dict:
    """Whether the whole panel could reach PIT_EXACT, and what stops it.

    All-or-nothing on purpose: `MacroVintageView.pit_status` returns
    PIT_APPROXIMATE while any column is still a later revision, and the
    integrity gate asks for PIT_EXACT. One good series is not partial credit.
    """
    verdicts = {name: row.get("verdict") for name, row in summaries.items()}
    blocking = sorted(name for name, verdict in verdicts.items() if verdict != USABLE)
    return {
        "columns": len(verdicts),
        "usable": sorted(name for name, verdict in verdicts.items() if verdict == USABLE),
        "blocking": blocking,
        "pitExactReachable": not blocking,
        "wouldBe": (pit_data.PIT_EXACT if not blocking else pit_data.PIT_APPROXIMATE),
        "note": ("every panel column can be served from its own release history "
                 "back to the replay start" if not blocking else
                 "opting in now would leave the panel at PIT_APPROXIMATE, and "
                 "the truncated columns would go dark on early replay dates"),
    }


def fetch_all(cfg: Config, names: list[str]) -> dict[str, pd.DataFrame | None]:
    """One ALFRED call per series. Failures are recorded, never swallowed."""
    from fredapi import Fred

    fred = Fred(api_key=cfg.fred_api_key)
    out: dict[str, pd.DataFrame | None] = {}
    for name in names:
        series_id = cfg.fred_series[name]
        try:
            out[name] = fred.get_series_all_releases(series_id)
            rows = 0 if out[name] is None else len(out[name])
            print(f"  {name:<16} {series_id:<14} {rows:>8,} release rows", flush=True)
        except Exception as exc:  # pragma: no cover - network dependent
            out[name] = None
            print(f"  {name:<16} {series_id:<14} FAILED: {exc}", flush=True)
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="alfred-probe.json")
    parser.add_argument("--start", default=None,
                        help="replay start; defaults to config historicalReplay.start")
    parser.add_argument("--as-of", default=None,
                        help="comma-separated dates to reconstruct each column on")
    parser.add_argument("--series", default=None,
                        help="comma-separated panel names; default is every one")
    args = parser.parse_args(argv)

    cfg, _ = load_config(ROOT / "config.json")
    if not cfg.has_fred:
        print("FRED_API_KEY is not set — ALFRED cannot be reached. Nothing measured.")
        return 2

    start = args.start or (cfg.historical_replay or {}).get("start") or "2013-01-01"
    as_of_dates = [d.strip() for d in (args.as_of or "").split(",") if d.strip()]
    if not as_of_dates:
        # The first replay date is the one that decides the answer; a later one
        # is there to show a truncated series recovering rather than failing.
        as_of_dates = [start, (pd.Timestamp(start) + pd.DateOffset(years=5)).date().isoformat()]

    wanted = [s.strip() for s in (args.series or "").split(",") if s.strip()]
    names = [n for n in cfg.fred_series if not wanted or n in wanted]
    print(f"ALFRED vintages for {len(names)} panel series, replay start {start}")

    releases = fetch_all(cfg, names)
    summaries = {name: summarize_releases(frame, start=start, as_of_dates=as_of_dates)
                 for name, frame in releases.items()}
    for name, frame in releases.items():
        if frame is None:
            summaries[name] = {"verdict": FAILED, "rows": 0,
                               "reason": "the ALFRED call did not return"}
    summaries.update(resolve_derived(summaries))

    report = {
        "probe": "alfred-macro-vintages",
        "replayStart": start,
        "asOfDates": as_of_dates,
        "seriesIds": {n: cfg.fred_series[n] for n in names},
        "derivedColumns": {k: list(v) for k, v in pit_data.DERIVED_MACRO_COLUMNS.items()},
        "series": summaries,
        "panel": panel_verdict(summaries),
    }
    Path(args.output).write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n",
                                 encoding="utf-8")

    print()
    for name in sorted(summaries):
        row = summaries[name]
        served = ", ".join(f"{s['asOf']}:{s['periodsServed']}/{s['periodsInRevisedHistory']}"
                           for s in row.get("asOf") or [])
        print(f"  {row['verdict']:<18} {name:<16} "
              f"first print {row.get('firstPublished') or '—'} "
              f"revised {row.get('periodsEverRevised', 0)}/{row.get('periodsTotal', 0)} "
              f"periods | served {served or '—'}")
        if row.get("reason"):
            print(f"    {row['reason']}")
    panel = report["panel"]
    print()
    print(f"panel: {len(panel['usable'])}/{panel['columns']} columns usable -> "
          f"{panel['wouldBe']}")
    print(f"  {panel['note']}")
    if panel["blocking"]:
        print(f"  blocking: {panel['blocking']}")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
