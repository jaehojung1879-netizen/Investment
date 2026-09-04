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
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import pit_data  # noqa: E402
from pipeline.config import load_config  # noqa: E402

# WHY NOT fredapi's get_series_all_releases. Measured on the first real run: it
# asks ALFRED for the whole real-time period at once and six of the panel's
# series came back
#
#   Bad Request. There are 5103 vintage dates in the specified real-time
#   period: 1776-07-04 to 9999-12-31. This exceeds the maximum number of
#   vintage dates allowed for this file type (2000).
#
# — DGS10, DGS2, DFF, DFII10, T10YIE, RRPONTSYD, and with them Yield_Curve,
# which is derived from the first two. Those are daily series ALFRED stamps a
# new vintage for on every business day, so the cap is structural and no retry
# clears it. Two others (NFCI, ANFCI) returned exactly 100,000 rows, which is
# the row cap rather than their length, so those answers were silently clipped.
#
# The decisive question does not need the whole matrix. "Does this series'
# release history reach the replay start" is answered by its FIRST vintage
# date, and `series/vintagedates` lists vintage dates directly. "What would the
# column serve on date T" is answered by pinning the request to that one
# vintage — `realtime_start = realtime_end = T` returns the series exactly as
# it stood that day. Both are one small call and neither can hit either cap.
FRED_BASE = "https://api.stlouisfed.org/fred"
VINTAGE_PAGE = 10000

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


def api(path: str, params: dict, api_key: str, *, timeout: int = 60) -> dict:
    """One FRED call. A refusal is raised with what FRED actually said.

    The first run recorded six failures as "the ALFRED call did not return",
    which is the shape of absence this repo refuses everywhere else: the reason
    was a specific, actionable message about a vintage-date cap, and throwing it
    away cost a whole run to rediscover.
    """
    query = dict(params)
    query.update({"api_key": api_key, "file_type": "json"})
    url = f"{FRED_BASE}/{path}?{urllib.parse.urlencode(query)}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            message = json.loads(body).get("error_message") or body
        except ValueError:
            message = body
        raise RuntimeError(f"HTTP {exc.code}: {message.strip()[:300]}") from None


def vintage_dates(series_id: str, api_key: str) -> list[str]:
    """Every date ALFRED holds a vintage of this series for, oldest first."""
    out: list[str] = []
    offset = 0
    while True:
        payload = api("series/vintagedates", {"series_id": series_id,
                                              "limit": VINTAGE_PAGE,
                                              "offset": offset}, api_key)
        page = payload.get("vintage_dates") or []
        out.extend(page)
        if len(page) < VINTAGE_PAGE:
            break
        offset += VINTAGE_PAGE
    return sorted(set(out))


def vintage_observations(series_id: str, api_key: str, as_of: str | None) -> list[str]:
    """Observation dates the series carried on ``as_of`` (None = latest).

    Pinning `realtime_start = realtime_end = as_of` is ALFRED's own way of
    asking "what did this series look like that day", so this is the same
    quantity `pit_data.vintage_column` reconstructs, obtained from the vendor
    rather than rebuilt — and it costs one small request instead of the whole
    release matrix the cap refuses to serve.
    """
    params = {"series_id": series_id}
    if as_of is not None:
        params["realtime_start"] = as_of
        params["realtime_end"] = as_of
    payload = api("series/observations", params, api_key)
    return [row["date"] for row in (payload.get("observations") or [])
            if row.get("value") not in (None, "", ".")]


def summarize_series(vintages: list[str], served: dict[str, list[str]],
                     revised: list[str], *, start: str,
                     as_of_dates: list[str]) -> dict:
    """What one series' release history can and cannot serve. Pure.

    ``vintages`` are its vintage dates, ``served[T]`` the observation dates it
    carried on T, ``revised`` the observation dates it carries today.

    The verdict turns on the FIRST vintage date against the replay start, and
    nothing else — not row counts, not how many periods exist. A series with
    decades of observations whose first vintage is 2023 serves NOTHING on a
    2013 replay date while `pit_status` upgrades the panel to PIT_EXACT, and
    that is the trade this exists to make visible.
    """
    if not vintages:
        return {"verdict": EMPTY, "vintages": 0,
                "reason": "ALFRED holds no vintage dates for this series"}
    first, last = vintages[0], vintages[-1]
    per_as_of = []
    for as_of in as_of_dates:
        cutoff = pd.Timestamp(as_of)
        held = [d for d in served.get(as_of, []) if pd.Timestamp(d) <= cutoff]
        today = [d for d in revised if pd.Timestamp(d) <= cutoff]
        per_as_of.append({
            "asOf": as_of,
            "periodsServed": len(held),
            # What the same span looks like using the numbers as revised since,
            # i.e. what REVISED_HISTORY shows today. The gap between the two is
            # the cost of opting this series in.
            "periodsInRevisedHistory": len(today),
            "lastPeriodServed": max(held) if held else None,
        })
    usable = first <= start
    return {
        "verdict": USABLE if usable else TRUNCATED,
        "vintages": len(vintages),
        "firstVintage": first,
        "lastVintage": last,
        "asOf": per_as_of,
        "reason": (None if usable else
                   f"earliest vintage {first} is after the replay start {start}; "
                   "opting in would blank this column until then"),
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


def probe_all(series_ids: dict[str, str], api_key: str, *, start: str,
              as_of_dates: list[str], sleep: float = 0.15) -> dict[str, dict]:
    """One summary per panel series. A failure keeps its reason."""
    out: dict[str, dict] = {}
    for name, series_id in series_ids.items():
        try:
            vintages = vintage_dates(series_id, api_key)
            time.sleep(sleep)
            revised = vintage_observations(series_id, api_key, None)
            served = {}
            for as_of in as_of_dates:
                time.sleep(sleep)
                served[as_of] = vintage_observations(series_id, api_key, as_of)
            out[name] = summarize_series(vintages, served, revised, start=start,
                                         as_of_dates=as_of_dates)
            row = out[name]
            print(f"  {name:<16} {series_id:<16} {row.get('vintages', 0):>6,} vintages "
                  f"from {row.get('firstVintage') or '—'}", flush=True)
        except Exception as exc:  # pragma: no cover - network dependent
            out[name] = {"verdict": FAILED, "vintages": 0, "reason": str(exc)}
            print(f"  {name:<16} {series_id:<16} FAILED: {exc}", flush=True)
        time.sleep(sleep)
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
        as_of_dates = [start,
                       (pd.Timestamp(start) + pd.DateOffset(years=5)).date().isoformat()]

    wanted = [s.strip() for s in (args.series or "").split(",") if s.strip()]
    series_ids = {n: sid for n, sid in cfg.fred_series.items()
                  if not wanted or n in wanted}
    print(f"ALFRED vintages for {len(series_ids)} panel series, replay start {start}")

    summaries = probe_all(series_ids, cfg.fred_api_key, start=start,
                          as_of_dates=as_of_dates)
    summaries.update(resolve_derived(summaries))

    report = {
        "probe": "alfred-macro-vintages",
        "method": "VINTAGE_DATES_PLUS_PINNED_SNAPSHOTS",
        "replayStart": start,
        "asOfDates": as_of_dates,
        "seriesIds": series_ids,
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
              f"first vintage {row.get('firstVintage') or '—'} "
              f"({row.get('vintages', 0):,} vintages) | served {served or '—'}")
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
