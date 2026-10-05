"""kr-integrated-alpha-portfolio-v1 — POST-OUTCOME descriptive concentration audit (diagnostic only).

This module diagnoses an ALREADY-EXPOSED, ALREADY-SPENT formal result (Actions run 37374530672). It is not a confirmatory experiment, not a model rescue, not an
architecture selection and not a promotion decision, and nothing here may be read as prospective evidence. It never calls the formal ``execute`` path, never
touches an execution lock, never writes a formal result and never changes a model parameter, band, weight, benchmark or sealed study.

Every number it produces carries one of four evidence labels so the three kinds of statement are never blended:

* ``FORMAL_REPORTED_RESULT`` — read from the exact formal result artifact, never recomputed;
* ``POST_OUTCOME_DIAGNOSTIC_RECONSTRUCTION`` — the frozen code replayed read-only over the frozen raw snapshot, admitted only after it reproduces the formal result;
* ``POST_OUTCOME_COUNTERFACTUAL_SENSITIVITY`` — the one authorised strategy counterfactual (D without Samsung Electronics and SK Hynix);
* ``POST_OUTCOME_DESCRIPTIVE_PROXY`` — an independent reading of frozen inputs (period arithmetic on the frozen benchmark, same-data reference portfolios, market-cap
  shares inside the PIT Top120). A proxy is never described as the KODEX 200 / KOSPI 200 index weight or return.

Pure functions only: no network, no git and no file system access except where a function names a path argument.
"""
from __future__ import annotations

from contextlib import contextmanager
import math

import numpy as np
import pandas as pd

from . import kr_integrated_alpha_portfolio as M

STUDY = "kr-integrated-alpha-portfolio-v1-postoutcome-concentration-audit-v1"
SOURCE_STUDY = M.STUDY
SCIENTIFIC_STATUS = "EXPLORATORY_POST_OUTCOME_DESCRIPTIVE_DIAGNOSTIC"
STATEMENT = ("POST-OUTCOME DESCRIPTIVE DIAGNOSTIC ONLY. It diagnoses an already-exposed result; it is not a new confirmatory experiment, a model rescue, an "
             "architecture selection, a promotion decision or prospective evidence, and it cannot alter the formal result or any frozen rule.")

FORMAL_REPORTED_RESULT = "FORMAL_REPORTED_RESULT"
RECONSTRUCTION = "POST_OUTCOME_DIAGNOSTIC_RECONSTRUCTION"
COUNTERFACTUAL = "POST_OUTCOME_COUNTERFACTUAL_SENSITIVITY"
PROXY = "POST_OUTCOME_DESCRIPTIVE_PROXY"
EVIDENCE_CLASSES = (FORMAL_REPORTED_RESULT, RECONSTRUCTION, COUNTERFACTUAL, PROXY)

SUPPORTED = "SUPPORTED_BY_AUDIT"
PARTIAL = "PARTIALLY_SUPPORTED"
NOT_SUPPORTED = "NOT_SUPPORTED"
UNRESOLVED = "UNRESOLVED_DATA_LIMITATION"
CLASSIFICATIONS = (SUPPORTED, PARTIAL, NOT_SUPPORTED, UNRESOLVED)

NOT_RUN = "NOT_RUN_IN_THIS_ENVIRONMENT"
BENCHMARK_RECONSTRUCTION_MISMATCH = "BENCHMARK_RECONSTRUCTION_MISMATCH"
D_PATH_RECONSTRUCTION_MISMATCH = "D_PATH_RECONSTRUCTION_MISMATCH"
EXTERNAL_UNRESOLVED = "BENCHMARK_EXTERNAL_RECONCILIATION_UNRESOLVED"

# The formal run this audit is about, by identity. Verified (not assumed) against GitHub on every full run.
FORMAL = {
    "workflowRunId": 37374530672, "executionSha": "33237df6d69e31a396959529378a0f881af9a58e",
    "specSha256": "eea6128cd55260904c7f74ba78698f67e522626620fd11d757c27de89c758f77",
    "resultArtifactId": 11371812532, "resultArtifactName": "kr-integrated-alpha-portfolio-v1-results-37374530672",
    "resultArtifactDigest": "sha256:bb29676403068b8330b12808ff30f6a5766fee35d4e66e96594591eaae766722",
    "resultFile": "integrated-alpha-portfolio.json",
    "resultFileSha256": "a204148896de57207e3bf7b6335397ad181afbb0868c21b9e584aefe050707ab",
    "markerFile": "execution-started.json", "markerFileSha256": "2108f3ca01ea0d1d5f90ec9fc74bbfcad1ebdfcf687161879a60b44f8e789b5a",
    "expectedArtifactFiles": ("execution-started.json", "integrated-alpha-portfolio.json", "manifest.json"),
    "executeJob": "success", "sealJob": "failure",
    "rawInputArtifactId": 11157875265, "rawInputArtifactName": "kr-model-raw-inputs-36844599518",
    "rawInputArtifactDigest": "sha256:42eeb18b7a5c88816629036f472a93057b6a9be4768ad47292ba0d2750b4cce7", "rawInputRunId": 36844599518,
    "lockRefs": ("refs/tags/kr-integrated-alpha-portfolio-v1-execution-lock",
                 "refs/tags/kr-integrated-alpha-portfolio-v1-execution-lock-eea6128cd55260904c7f74ba78698f67e522626620fd11d757c27de89c758f77"),
}

BENCHMARK = M.BENCHMARK
WINDOW_START = "2017-01-16"                 # the first scheduled anchor of the formal window
CUTOFF = M.DEVELOPMENT_CUTOFF               # 2026-09-14
DAYS_PER_YEAR = 365.2425
MIN_ANNUALIZATION_YEARS = 0.99      # a calendar year between two year-end sessions spans 364-366 days (0.997-1.002 years); anything shorter is not annualized
# The only period boundaries this audit uses. Fixed in advance because the question is specifically whether the 2025-2026 regime dominates; never tuned.
BOUNDARY_END_2024 = "2024-12-31"
BOUNDARY_END_2025 = "2025-12-31"
PERIOD_LABELS = (("A_2017_to_2024", "2017-01-16 through the last session of 2024"), ("B_2025", "calendar 2025"),
                 ("C_2026_to_cutoff", "2026-01-01 through the formal cutoff"), ("D_full_window", "the full formal window"))
CALENDAR_YEARS = tuple(range(2017, 2027))

NAMED_SECURITIES = {"005930.KS": "Samsung Electronics", "000660.KS": "SK Hynix"}      # fixed in advance; no other name is ever added from observed returns
NAMED = tuple(NAMED_SECURITIES)
SHARE_THRESHOLDS = (0.30, 0.40, 0.50, 0.60)                                           # descriptive round numbers, never model thresholds
TOP_N = 120
FORBIDDEN_LANGUAGE = ("promot", "winner", "recommend", "optimal", "best", "passfail", "pass/fail", "validated", "productionready")


# =======================================================================================================================================
# Period arithmetic
# =======================================================================================================================================
def _years(a, b):
    return (pd.Timestamp(b) - pd.Timestamp(a)).days / DAYS_PER_YEAR


def last_session_on_or_before(index, day):
    eligible = [d for d in index if d <= day]
    if not eligible:
        raise ValueError("NO_SESSION_ON_OR_BEFORE: " + day)
    return eligible[-1]


def period_spans(index, start=WINDOW_START, cutoff=CUTOFF):
    """The four fixed spans as (label, description, from-session, to-session). A span's return is level(to) / level(from) - 1; its sessions are the daily steps after
    `from` up to and including `to`."""
    index = sorted(index)
    end_2024 = last_session_on_or_before(index, BOUNDARY_END_2024)
    end_2025 = last_session_on_or_before(index, BOUNDARY_END_2025)
    ends = {"A_2017_to_2024": (start, end_2024), "B_2025": (end_2024, end_2025), "C_2026_to_cutoff": (end_2025, cutoff), "D_full_window": (start, cutoff)}
    return [(label, text, *ends[label]) for label, text in PERIOD_LABELS]


def period_decomposition(levels, start=WINDOW_START, cutoff=CUTOFF):
    """Cumulative / annualized return, start and end level, number of daily steps and the span's share of terminal wealth, for the four fixed spans.

    `levels` maps session date -> level (a total-return index or a NAV). Two shares are given because they answer different questions: `logShareOfTerminalWealth`
    is ln(end/start) over ln(terminal/initial) (compounding-consistent, additive across the three sub-spans) and `shareOfTerminalGain` is the span's level change over the
    whole window's level change. Annualization needs a full year (a calendar year between two year-end sessions counts); a shorter span reports None rather than an extrapolation."""
    series = pd.Series(levels).sort_index()
    series.index = series.index.astype(str)
    total_start, total_end = float(series[start]), float(series[cutoff])
    total_log, total_gain = math.log(total_end / total_start), total_end - total_start
    rows = []
    for label, text, a, b in period_spans(list(series.index), start, cutoff):
        la, lb = float(series[a]), float(series[b])
        years = _years(a, b)
        rows.append({"period": label, "description": text, "fromSession": a, "toSession": b, "startLevel": la, "endLevel": lb, "cumulativeReturn": lb / la - 1,
                     "years": years, "annualizedReturn": (lb / la) ** (1 / years) - 1 if years >= MIN_ANNUALIZATION_YEARS and la > 0 and lb > 0 else None,
                     "annualizationNote": None if years >= MIN_ANNUALIZATION_YEARS else "SPAN_SHORTER_THAN_ONE_YEAR_NOT_ANNUALIZED",
                     "sessions": int(((series.index > a) & (series.index <= b)).sum()),
                     "logShareOfTerminalWealth": math.log(lb / la) / total_log if total_log else None,
                     "shareOfTerminalGain": (lb - la) / total_gain if total_gain else None})
    return rows


def calendar_year_returns(levels, start=WINDOW_START, cutoff=CUTOFF, years=CALENDAR_YEARS):
    """Calendar-year returns inside the window: the first year starts at the window start, the last ends at the cutoff."""
    series = pd.Series(levels).sort_index()
    series.index = series.index.astype(str)
    out = {}
    for year in years:
        prior = [d for d in series.index if d < f"{year}-01-01" and d >= start]
        base = prior[-1] if prior else start
        end = last_session_on_or_before(list(series.index), min(f"{year}-12-31", cutoff))
        out[str(year)] = {"fromSession": base, "toSession": end, "return": float(series[end] / series[base] - 1)}
    return out


# =======================================================================================================================================
# Benchmark integrity (internal) and the tracking cross-check
# =======================================================================================================================================
def benchmark_integrity(levels, calendar_sessions, start=WINDOW_START, cutoff=CUTOFF):
    """Structural audit of the frozen benchmark series: session completeness against the registered KR calendar, duplicates, non-positive or non-finite levels and
    the extreme daily moves (reported, never edited). `levels` is a pandas Series indexed by date string; duplicates must be checked on the raw row list by the caller
    (a Series with a unique index cannot carry them), so `duplicate_dates` is passed through."""
    series = pd.Series(levels).sort_index()
    series.index = series.index.astype(str)
    calendar = [d for d in calendar_sessions]
    missing, extra = sorted(set(calendar) - set(series.index)), sorted(set(series.index) - set(calendar))
    daily = series.pct_change().dropna()
    extreme = daily[daily.abs() >= 0.10]
    window = daily[(daily.index > start) & (daily.index <= cutoff)]
    return {"firstSession": series.index[0], "lastSession": series.index[-1], "sessions": int(len(series)), "calendarSessions": int(len(calendar)),
            "sessionsMissingFromSeries": missing, "sessionsNotInCalendar": extra,
            "nonPositiveOrNonFiniteLevels": int(((series <= 0) | ~np.isfinite(series)).sum()),
            "windowFirstSession": start, "windowLastSession": cutoff, "windowSessionsAfterStart": int(len(window)),
            "dailyMovesAtLeast10Percent": [{"date": d, "return": float(r)} for d, r in extreme.items() if start < d <= cutoff],
            "dailyMovesAtLeast10PercentCountAllHistory": int(len(extreme)),
            "largestDailyMoveInWindow": {"date": window.abs().idxmax(), "return": float(window[window.abs().idxmax()])}}


def tracking_cross_check(benchmark, index, references, start=WINDOW_START, cutoff=CUTOFF, years=CALENDAR_YEARS):
    """Calendar-year benchmark total return against independent readings of the same market: a PRICE index (`index`) and same-data constituent total-return reference
    portfolios (`references`: name -> level series). `benchmarkOverIndexRelative` is (1 + TR) / (1 + index) - 1, i.e. what the benchmark earned above the price index in that
    year (distributions plus ETF tracking). It is a plain description of the gap; it states no verdict and fixes no expected yield.

    The reference columns differ from the index by composition (a Top120 cap-weighted book is not KOSPI 200), so only the 2017-2024 span, where concentration was
    modest, is a like-for-like comparison of the accrual; later years are dominated by composition."""
    lv = {"benchmark": pd.Series(benchmark).sort_index(), "index": pd.Series(index).sort_index(), **{k: pd.Series(v).sort_index() for k, v in references.items()}}
    for v in lv.values():
        v.index = v.index.astype(str)
    rows = {}
    for year in years:
        row = {}
        for name, v in lv.items():
            prior = [d for d in v.index if start <= d < f"{year}-01-01"]
            base = prior[-1] if prior else start
            end = last_session_on_or_before(list(v.index), min(f"{year}-12-31", cutoff))
            row[name] = float(v[end] / v[base] - 1)
        row["benchmarkOverIndexRelative"] = (1 + row["benchmark"]) / (1 + row["index"]) - 1
        for name in references:
            row[name + "OverIndexRelative"] = (1 + row[name]) / (1 + row["index"]) - 1
        rows[str(year)] = row

    def span(a, b):
        out = {}
        for name, v in lv.items():
            sa, sb = last_session_on_or_before(list(v.index), a), last_session_on_or_before(list(v.index), b)
            out[name] = float(v[sb] / v[sa] - 1)
        out["benchmarkOverIndexRelative"] = (1 + out["benchmark"]) / (1 + out["index"]) - 1
        out["benchmarkOverIndexRelativePerYear"] = (1 + out["benchmarkOverIndexRelative"]) ** (1 / _years(a, b)) - 1
        for name in references:
            out[name + "OverIndexRelative"] = (1 + out[name]) / (1 + out["index"]) - 1
            out[name + "OverIndexRelativePerYear"] = (1 + out[name + "OverIndexRelative"]) ** (1 / _years(a, b)) - 1
        return out
    end_2024 = last_session_on_or_before(list(lv["benchmark"].index), BOUNDARY_END_2024)
    return {"byCalendarYear": rows, "span2017To2024": span(start, end_2024), "spanFullWindow": span(start, cutoff)}


# =======================================================================================================================================
# Concentration of the two named securities
# =======================================================================================================================================
def concentration_snapshots(universe, tickers=NAMED, top_n=TOP_N):
    """Per universe snapshot date: each named security's share of the total market capitalisation of the PIT Top-`top_n` (rank <= top_n on that date), and the combined share.

    This is a PROXY for benchmark weight: total (not free-float) market capitalisation inside the study's PIT Top120, not the KOSPI 200 index or KODEX 200 weight."""
    frame = universe[universe["rank"] <= top_n]
    rows = []
    for date, group in frame.groupby("date"):
        total = float(group.marketCap.sum())
        row = {"date": date, "members": int(len(group)), "topNMarketCap": total}
        for t in tickers:
            row[t] = float(group[group.ticker == t].marketCap.sum() / total) if total else None
        row["combined"] = float(sum(row[t] for t in tickers))
        rows.append(row)
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


def share_thresholds(snapshots, thresholds=SHARE_THRESHOLDS, start="2017-01-01"):
    """Descriptive: for each round threshold the number of monthly snapshots whose combined share is above it, the first and last such snapshot and the contiguous runs.
    Also the maximum and median combined share inside the formal window and over all history."""
    out = {}
    scoped = snapshots[snapshots.date >= start].reset_index(drop=True)
    for name, frame in (("allHistory", snapshots), ("formalWindow", scoped)):
        series = frame.set_index("date").combined
        block = {"snapshots": int(len(series)), "maximum": float(series.max()), "maximumDate": series.idxmax(), "median": float(series.median()),
                 "minimum": float(series.min()), "minimumDate": series.idxmin(), "latest": float(series.iloc[-1]), "latestDate": series.index[-1], "thresholds": {}}
        for th in thresholds:
            above = series[series > th]
            runs, current = [], None
            for date in series.index:
                if series[date] > th:
                    current = [date, date] if current is None else [current[0], date]
                elif current is not None:
                    runs.append(current)
                    current = None
            if current is not None:
                runs.append(current)
            block["thresholds"][f"{th:.2f}"] = {"snapshotsAbove": int(len(above)), "first": above.index[0] if len(above) else None,
                                                "last": above.index[-1] if len(above) else None, "runs": [{"from": a, "to": b} for a, b in runs]}
        out[name] = block
    return out


def snapshot_table(snapshots, dates):
    """The requested checkpoint rows (nearest snapshot ON OR BEFORE each checkpoint date), never a later one."""
    rows = []
    for checkpoint in dates:
        prior = snapshots[snapshots.date <= checkpoint]
        if prior.empty:
            rows.append({"checkpoint": checkpoint, "snapshot": None})
            continue
        r = prior.iloc[-1]
        rows.append({"checkpoint": checkpoint, "snapshot": r.date, **{NAMED_SECURITIES[t]: float(r[t]) for t in NAMED if t in r}, "combined": float(r.combined),
                     "members": int(r.members)})
    return rows


# =======================================================================================================================================
# Same-data reference portfolios (descriptive lenses, NOT the formal benchmark)
# =======================================================================================================================================
def reference_portfolio(kind, close, universe, sessions, *, exclude=(), track=NAMED, top_n=TOP_N):
    """Daily path of a Top-`top_n` reference portfolio over `sessions` (nav = 1.0 on the first session).

    kind CAP: weights proportional to the snapshot's total market capitalisation; kind EQUAL: 1/n. Names are the snapshot's rank <= top_n members that quote on the
    rebalance session; `exclude` removes ONLY the named tickers and renormalises (no other exclusion). The book is formed at the close of each universe snapshot date
    (and on the first session from the latest snapshot on or before it), earns the following sessions' total-return moves buy-and-hold, and is re-formed at the next
    snapshot. A missing mark carries the previous total-return close (return 0), exactly as the study's engine carries a zero-volume quote. No cost is charged.

    Returns {"nav": Series, "contribution": {ticker: Series of daily NAV-unit contributions}, "rebalances": n, "namesWithoutPriceAtRebalance": n}."""
    if kind not in ("CAP", "EQUAL"):
        raise ValueError("UNREGISTERED_REFERENCE_KIND")
    sessions = list(sessions)
    marks = close.reindex(sessions).ffill()
    returns = marks.pct_change(fill_method=None).fillna(0.0)
    snaps = sorted(universe.date.unique())
    nav, weights, current = 1.0, None, None
    out_nav, contrib = {}, {t: {} for t in track}
    rebalances = skipped = 0
    for day in sessions:
        daily = {t: 0.0 for t in track}
        if weights is not None:
            r = returns.loc[day].reindex(weights.index).fillna(0.0)
            growth = float((weights * (1 + r)).sum())
            for t in track:
                if t in weights.index:
                    daily[t] = nav * float(weights[t]) * float(r[t])
            nav *= growth
            weights = weights * (1 + r) / growth
        applicable = [s for s in snaps if s <= day]
        if applicable:
            snap = applicable[-1]
            if current is None or snap != current:
                members = universe[(universe.date == snap) & (universe["rank"] <= top_n)].set_index("ticker")
                quoted = members.index.isin(marks.columns) & marks.loc[day].reindex(members.index).notna().to_numpy()
                skipped += int((~quoted).sum())
                members = members[quoted]
                members = members.drop([t for t in exclude if t in members.index])
                weights = (members.marketCap / members.marketCap.sum()) if kind == "CAP" else pd.Series(1.0 / len(members), index=members.index)
                current = snap
                rebalances += 1
        out_nav[day] = nav
        for t in track:
            contrib[t][day] = daily[t]
    return {"nav": pd.Series(out_nav), "contribution": {t: pd.Series(v) for t, v in contrib.items()}, "rebalances": rebalances, "namesWithoutPriceAtRebalance": skipped}


def contribution_by_period(reference, start=WINDOW_START, cutoff=CUTOFF):
    """Weighted contribution of each tracked security over the three fixed sub-spans and the full window, chained daily (sum of nav_{t-1} * w_{t-1} * r_t). Reported in
    NAV units, in percentage points of the span's opening NAV, and as a share of the span's gain."""
    nav = reference["nav"]
    out = {}
    for label, text, a, b in period_spans(list(nav.index), start, cutoff):
        gain = float(nav[b] - nav[a])
        entry = {"description": text, "fromSession": a, "toSession": b, "navStart": float(nav[a]), "navEnd": float(nav[b]), "gain": gain, "securities": {}}
        named_total = 0.0
        for t, series in reference["contribution"].items():
            c = float(series[(series.index > a) & (series.index <= b)].sum())
            named_total += c
            entry["securities"][t] = {"name": NAMED_SECURITIES.get(t, t), "contributionNavUnits": c, "contributionPointsOfOpeningNav": c / float(nav[a]),
                                      "shareOfSpanGain": c / gain if gain else None}
        entry["combined"] = {"contributionNavUnits": named_total, "contributionPointsOfOpeningNav": named_total / float(nav[a]), "shareOfSpanGain": named_total / gain if gain else None}
        entry["residual"] = {"contributionNavUnits": gain - named_total, "contributionPointsOfOpeningNav": (gain - named_total) / float(nav[a]),
                             "shareOfSpanGain": (gain - named_total) / gain if gain else None}
        out[label] = entry
    return out


def annualize(growth, years):
    return float(growth ** (1.0 / years) - 1.0) if years >= MIN_ANNUALIZATION_YEARS and growth > 0 else None


# =======================================================================================================================================
# External reconciliation (metadata contract; nothing here fetches anything)
# =======================================================================================================================================
SOURCE_BASES = ("MARKET_PRICE_RETURN", "NAV_RETURN", "INDEX_RETURN", "TOTAL_RETURN", "DISTRIBUTION_REINVESTED_RETURN")
SOURCE_FIELDS = ("sourceId", "url", "issuer", "publicationDate", "measurementDate", "metricName", "basis", "retrievalDate", "basisLimitations", "value")


def external_source_record(**fields):
    """Validate one external evidence record. Every field is required (a missing publication date or an unlabelled basis would let unlike bases be compared as if alike);
    `value` may be None only with retrievalStatus UNREACHABLE."""
    missing = [f for f in SOURCE_FIELDS if f not in fields]
    if missing:
        raise ValueError("EXTERNAL_SOURCE_FIELD_MISSING: " + ",".join(missing))
    if fields["basis"] not in SOURCE_BASES:
        raise ValueError("EXTERNAL_SOURCE_BASIS_UNLABELLED")
    if fields["value"] is None and fields.get("retrievalStatus") != "UNREACHABLE":
        raise ValueError("EXTERNAL_SOURCE_VALUE_MISSING_WITHOUT_UNREACHABLE_STATUS")
    return dict(fields)


def reconcile_checkpoint(frozen_return, external_return, frozen_basis, external_basis, tolerance_pp=0.25):
    """Compare one frozen return with one external return. Different bases are never compared silently: the result is BASIS_DIFFERS with both labels. The tolerance is a
    reporting convenience for identifying a gap worth explaining, not a pass/fail threshold."""
    if external_return is None:
        return {"status": EXTERNAL_UNRESOLVED, "reason": "NO_EXTERNAL_VALUE", "frozenReturn": frozen_return}
    gap = (frozen_return - external_return) * 100
    if frozen_basis != external_basis:
        return {"status": "BASIS_DIFFERS", "frozenBasis": frozen_basis, "externalBasis": external_basis, "gapPercentagePoints": gap, "frozenReturn": frozen_return,
                "externalReturn": external_return}
    return {"status": "MATCHES_WITHIN_REPORTING_TOLERANCE" if abs(gap) <= tolerance_pp else EXTERNAL_UNRESOLVED, "gapPercentagePoints": gap, "frozenReturn": frozen_return,
            "externalReturn": external_return, "tolerancePp": tolerance_pp}


# =======================================================================================================================================
# Formal-result extraction and reproduction
# =======================================================================================================================================
SUMMARY_KEYS = ("cumulativeNetReturn", "netAnnualizedReturn", "excessAnnualizedVsPassive", "cumulativeGrossReturn", "maxDrawdown", "annualizedOneWayTurnover",
                "totalOneWayTurnover", "totalCostFractionOfNav", "annualizedCostDrag", "replacements", "averageHoldings", "averageCashShare", "annualizedVolatility",
                "calendarYears", "halves", "firstDate", "lastDate", "sessions")


def extract_formal(result, architectures=("A", "B", "C", "D", "E", "F")):
    """The formal reported values, copied verbatim and labelled FORMAL_REPORTED_RESULT. Nothing is recomputed."""
    summaries = {a: {k: result["summaries"][a].get(k) for k in SUMMARY_KEYS} for a in architectures if result["summaries"].get(a, {}).get("complete")}
    return {"evidenceClass": FORMAL_REPORTED_RESULT, "specSha256": result.get("specSha256"), "window": result.get("window"), "passive": result.get("passive"),
            "summaries": summaries, "monthEndNav": {a: result["monthEndNav"][a] for a in architectures if a in result.get("monthEndNav", {})},
            "attribution": result.get("attribution"), "interaction": result.get("interaction"), "layerDecisions": result.get("layerDecisions"),
            "finalArchitecture": (result.get("layerDecisions") or {}).get("finalArchitecture"), "signalAvailability": result.get("signalAvailability"),
            "comparisons": result.get("comparisons")}


def _close(a, b, tolerance):
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    return math.isclose(float(a), float(b), rel_tol=tolerance, abs_tol=tolerance)


def _diff(path, a, b, tolerance, out):
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b)):
            if key not in a or key not in b:
                out.append({"path": f"{path}/{key}", "formal": a.get(key, "<absent>"), "reconstructed": b.get(key, "<absent>")})
            else:
                _diff(f"{path}/{key}", a[key], b[key], tolerance, out)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append({"path": path + "/len", "formal": len(a), "reconstructed": len(b)})
        for i, (x, y) in enumerate(zip(a, b)):
            _diff(f"{path}[{i}]", x, y, tolerance, out)
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)) or a is None or b is None:
        if not _close(a, b, tolerance):
            out.append({"path": path, "formal": a, "reconstructed": b})
    elif a != b:
        out.append({"path": path, "formal": a, "reconstructed": b})


def reproduction_check(formal_summary, formal_month_end_nav, reconstructed_summary, reconstructed_month_end_nav, tolerance=1e-9):
    """Compare a reconstructed path with the formal one on every available metric and every month-end NAV. Any difference is reported with its path; the first one is the
    first divergence. The tolerance is for exact deterministic float replay, never a fit parameter."""
    divergences = []
    _diff("monthEndNav", formal_month_end_nav, reconstructed_month_end_nav, tolerance, divergences)
    keys = [k for k in SUMMARY_KEYS if k in formal_summary]
    _diff("summary", {k: formal_summary[k] for k in keys}, {k: reconstructed_summary.get(k) for k in keys}, tolerance, divergences)
    return {"reproduced": not divergences, "metricsCompared": keys, "monthEndNavDates": len(formal_month_end_nav), "tolerance": tolerance,
            "firstDivergence": divergences[0] if divergences else None, "divergences": divergences[:25], "divergenceCount": len(divergences)}


# =======================================================================================================================================
# Portfolio-level attribution on a replayed path (architecture-agnostic; reads records only)
# =======================================================================================================================================
def _in_span(day, a, b, first=None):
    """A span covers the daily steps after `a` up to `b`; a span that opens on the path's first record also includes that record (its opening trade and cost)."""
    return a < day <= b or (first is not None and a == first and day == a)


def _opening_nav(nav_by_date, a, first):
    return 1.0 if a == first else nav_by_date[a]


def record_spans(path, cutoff=CUTOFF):
    """The fixed spans over a replayed path's own dates. The path starts on the window start, so its first record is the opening level."""
    dates = [r["date"] for r in path]
    return period_spans(dates, dates[0], min(cutoff, dates[-1]))


def holdings_concentration(path, industry_of, spans=None):
    """Per fixed span: holdings and weight concentration of the stock book, from the records only.

    `industry_of(record_date, ticker)` returns the industry the strategy itself used for that holding (never a retrospective taxonomy). HHI is computed on the
    invested weights renormalised to 1 (as the engine's `meanHerfindahl`); the largest-name weight is the share of NAV. A session with no holding contributes to the
    holdings-count histogram only."""
    spans = spans or record_spans(path)
    first = path[0]["date"]
    out = {}
    for label, text, a, b in spans:
        rows = [r for r in path if _in_span(r["date"], a, b, first)]
        held = [r for r in rows if r["weights"]]
        counts = {str(k): int(sum(1 for r in rows if len(r["weights"]) == k)) for k in range(0, 6)}
        largest, hhi, top_industry, three_same = [], [], [], 0
        for r in held:
            w = r["weights"]
            gross = sum(w.values())
            largest.append(max(w.values()))
            hhi.append(sum((v / gross) ** 2 for v in w.values()))
            by_industry = {}
            by_count = {}
            for t, v in w.items():
                ind = industry_of(r["date"], t)
                by_industry[ind] = by_industry.get(ind, 0.0) + v / gross
                by_count[ind] = by_count.get(ind, 0) + 1
            top_industry.append(max(by_industry.values()))
            three_same += int(max(by_count.values()) >= 3)
        out[label] = {"description": text, "sessions": len(rows), "sessionsWithHoldings": len(held), "holdingsHistogram": counts,
                      "averageHoldings": float(np.mean([len(r["weights"]) for r in rows])) if rows else None,
                      "averageLargestNameWeightOfNav": float(np.mean(largest)) if largest else None, "maximumLargestNameWeightOfNav": float(max(largest)) if largest else None,
                      "meanHhi": float(np.mean(hhi)) if hhi else None, "maximumHhi": float(max(hhi)) if hhi else None,
                      "meanTopIndustryShareOfInvested": float(np.mean(top_industry)) if top_industry else None,
                      "maximumTopIndustryShareOfInvested": float(max(top_industry)) if top_industry else None,
                      "shareOfHeldSessionsWithThreeOrMoreNamesInOneIndustry": three_same / len(held) if held else None,
                      "averageCashWeight": float(np.mean([r["cashWeight"] for r in rows])) if rows else None}
    return out


def named_exposure(path, tickers=NAMED, spans=None):
    """Per fixed span: sessions each named security was held, either held, both held, and the conditional and combined average weights."""
    spans = spans or record_spans(path)
    first = path[0]["date"]
    out = {}
    for label, text, a, b in spans:
        rows = [r for r in path if _in_span(r["date"], a, b, first)]
        entry = {"description": text, "sessions": len(rows), "securities": {}}
        for t in tickers:
            weights = [r["weights"].get(t, 0.0) for r in rows]
            held = [w for w in weights if w > 0]
            entry["securities"][t] = {"name": NAMED_SECURITIES.get(t, t), "sessionsHeld": len(held), "averageWeightWhenHeld": float(np.mean(held)) if held else None,
                                      "averageWeightOverAllSessions": float(np.mean(weights)) if weights else None}
        combined = [sum(r["weights"].get(t, 0.0) for t in tickers) for r in rows]
        entry["sessionsEitherHeld"] = int(sum(1 for r in rows if any(r["weights"].get(t, 0.0) > 0 for t in tickers)))
        entry["sessionsBothHeld"] = int(sum(1 for r in rows if all(r["weights"].get(t, 0.0) > 0 for t in tickers)))
        entry["averageCombinedWeight"] = float(np.mean(combined)) if combined else None
        entry["maximumCombinedWeight"] = float(max(combined)) if combined else None
        out[label] = entry
    return out


def security_contributions(path, mark, spans=None):
    """Gross return attribution by security for a replayed path: contribution_t(i) = nav_{t-1} * w_{t-1}(i) * r_t(i) in NAV units, where w is the end-of-day weight after
    drift and trade and r the same total-return mark move the engine used (`mark(ticker, day, previous)`). Transaction cost is NOT allocated to securities: it is the
    residual `(nav_{t-1} + sum contributions) - nav_t`, reported on its own, as is cash (zero-rate, so exactly zero).

    Two checks make the attribution non-tautological: each day's residual cost must equal the engine's own `costFraction` times the pre-trade NAV, and the whole identity
    nav_T - nav_0 = sum(contributions) - sum(cost) must hold to 1e-9. A path that fails either is not the engine's path and raises."""
    spans = spans or record_spans(path)
    previous_nav, previous_w, previous_marks = 1.0, {}, {}
    daily = []
    for r in path:
        contributions = {}
        for t, w in previous_w.items():
            m = mark(t, r["date"], previous_marks.get(t))
            contributions[t] = previous_nav * w * (m / previous_marks[t] - 1)
            previous_marks[t] = m
        gross = sum(contributions.values())
        pre_trade_nav = previous_nav + gross
        cost = pre_trade_nav - r["nav"]                    # the NAV the day's trade cost, read off the record
        # An INDEPENDENT reading of the same cost: the engine's costFraction is a share of the pre-trade NAV. If the records and the marks disagree the attribution
        # is not attributing the engine's path, and refusing is the only honest answer.
        if abs(cost - pre_trade_nav * r["cost"]) > 1e-9 * max(1.0, pre_trade_nav):
            raise ValueError("ATTRIBUTION_DOES_NOT_CLOSE_TO_THE_PATH_NAV: " + r["date"])
        daily.append({"date": r["date"], "contributions": contributions, "cost": cost})
        previous_nav = r["nav"]
        previous_w = dict(r["weights"])
        for t in previous_w:
            if t not in previous_marks or t not in contributions:
                previous_marks[t] = mark(t, r["date"], previous_marks.get(t))
    total_gross = sum(sum(d["contributions"].values()) for d in daily)
    total_cost = sum(d["cost"] for d in daily)
    if abs((path[-1]["nav"] - 1.0) - (total_gross - total_cost)) > 1e-9:
        raise ValueError("ATTRIBUTION_DOES_NOT_CLOSE_TO_THE_PATH_NAV")
    out = {}
    first = path[0]["date"]
    for label, text, a, b in spans:
        rows = [d for d in daily if _in_span(d["date"], a, b, first)]
        by_security = {}
        for d in rows:
            for t, c in d["contributions"].items():
                by_security[t] = by_security.get(t, 0.0) + c
        cost = sum(d["cost"] for d in rows)
        gross = sum(by_security.values())
        ordered = sorted(by_security.items(), key=lambda kv: (-kv[1], kv[0]))
        out[label] = {"description": text, "grossContributionNavUnits": gross, "transactionCostNavUnits": cost, "cashContributionNavUnits": 0.0,
                      "netChangeNavUnits": gross - cost, "bySecurity": {t: c for t, c in ordered},
                      "top10Contributors": [{"ticker": t, "contribution": c} for t, c in ordered[:10]],
                      "top10Detractors": [{"ticker": t, "contribution": c} for t, c in sorted(by_security.items(), key=lambda kv: (kv[1], kv[0]))[:10]]}
    return out, daily


def industry_contributions(daily, industry_of, spans):
    """Gross contribution by the industry the strategy used for each holding, over the fixed spans."""
    out = {}
    first = daily[0]["date"]
    for label, text, a, b in spans:
        by_industry = {}
        for d in daily:
            if not _in_span(d["date"], a, b, first):
                continue
            for t, c in d["contributions"].items():
                ind = industry_of(d["date"], t)
                by_industry[ind] = by_industry.get(ind, 0.0) + c
        ordered = sorted(by_industry.items(), key=lambda kv: (-kv[1], str(kv[0])))
        out[label] = {"byIndustry": {str(k): v for k, v in ordered}, "top": [{"industry": str(k), "contribution": v} for k, v in ordered[:5]],
                      "bottom": [{"industry": str(k), "contribution": v} for k, v in sorted(by_industry.items(), key=lambda kv: (kv[1], str(kv[0])))[:5]]}
    return out


def d_minus_a(decisions_a, decisions_d, anchors, path_a, path_d, contributions_a, contributions_d, spans):
    """Why D differs from A, by fixed span: the names the two books chose at each anchor, the same-name share, the return difference, the cost difference and the gross
    contribution difference by name (mechanically identifiable because both books price the same names with the same marks).

    `decisions_*` map signal date -> underlying decision. Anchors where either book had no valid new decision are counted separately and excluded from the name-overlap
    averages (a held book is not a new selection)."""
    out = {}
    nav_a = {r["date"]: r["nav"] for r in path_a}
    nav_d = {r["date"]: r["nav"] for r in path_d}
    first = path_a[0]["date"]
    for label, text, a, b in spans:
        both, same, differing, only_a, only_d = 0, [], [], [], []
        for day, signal in anchors:
            if not _in_span(day, a, b, first):
                continue
            da, dd = decisions_a[signal], decisions_d[signal]
            if not (da.get("available", True) and dd.get("available", True)):
                continue
            both += 1
            sa, sd = set(da["selected"]), set(dd["selected"])
            n = max(len(sa), len(sd), 1)
            same.append(len(sa & sd) / n)
            differing.append(len(sa ^ sd) / 2)
            only_a.append(len(sa - sd))
            only_d.append(len(sd - sa))
        ra, rd = nav_a[b] / _opening_nav(nav_a, a, first) - 1, nav_d[b] / _opening_nav(nav_d, a, first) - 1
        gross_a, gross_d = contributions_a[label]["bySecurity"], contributions_d[label]["bySecurity"]
        names = sorted(set(gross_a) | set(gross_d))
        diff = {t: gross_d.get(t, 0.0) - gross_a.get(t, 0.0) for t in names}
        ordered = sorted(diff.items(), key=lambda kv: (-kv[1], kv[0]))
        out[label] = {"description": text, "anchorsBothBooksHadAValidDecision": both,
                      "meanSameNameShare": float(np.mean(same)) if same else None, "meanDifferingNames": float(np.mean(differing)) if differing else None,
                      "meanNamesOnlyInA": float(np.mean(only_a)) if only_a else None, "meanNamesOnlyInD": float(np.mean(only_d)) if only_d else None,
                      "returnA": ra, "returnD": rd, "returnDMinusA": rd - ra,
                      "costNavUnitsA": contributions_a[label]["transactionCostNavUnits"], "costNavUnitsD": contributions_d[label]["transactionCostNavUnits"],
                      "grossContributionDifferenceNavUnits": contributions_d[label]["grossContributionNavUnits"] - contributions_a[label]["grossContributionNavUnits"],
                      "topNamesAddingToDMinusA": [{"ticker": t, "difference": v} for t, v in ordered[:10]],
                      "topNamesSubtractingFromDMinusA": [{"ticker": t, "difference": v} for t, v in sorted(diff.items(), key=lambda kv: (kv[1], kv[0]))[:10]]}
    return out


def industry_map_provider(membership_by_signal, anchors, path):
    """`industry_of(day, ticker)` for a replayed path: the industry of a holding is the industry at the SIGNAL date of the anchor that last selected it (the strategy's own
    identity at the decision state), carried while the name stays in the book. `membership_by_signal` maps signal date -> {ticker: industry}. Unknown -> 'UNCLASSIFIED'."""
    signal_of = dict(anchors)
    state, held_since = {}, {}
    by_day = {}
    for r in path:
        day = r["date"]
        if day in signal_of and r["kind"] == "ANCHOR":
            table = membership_by_signal.get(signal_of[day], {})
            for t in r["weights"]:
                if t not in held_since or t not in state:
                    state[t] = table.get(t, "UNCLASSIFIED")
                    held_since[t] = day
        for t in list(state):
            if t not in r["weights"]:
                state.pop(t, None)
                held_since.pop(t, None)
        by_day[day] = dict(state)

    def industry_of(day, ticker):
        return by_day.get(day, {}).get(ticker, "UNCLASSIFIED")
    return industry_of


# =======================================================================================================================================
# The one authorised strategy counterfactual
# =======================================================================================================================================
@contextmanager
def exclude_named_from_selection(tickers=NAMED):
    """D_EXCLUDE_SAMSUNG_HYNIX, mechanically: for the duration of the context the frozen `decision_rows` drops the named tickers AFTER stock and industry scoring and BEFORE
    selection, so every score stays what the frozen model computed and the next eligible ranked names fill the book under the unchanged rules. Nothing else is touched."""
    original = M.decision_rows
    drop = set(tickers)

    def filtered(scored, industry_map):
        return [row for row in original(scored, industry_map) if row["ticker"] not in drop]
    M.decision_rows = filtered
    try:
        yield
    finally:
        M.decision_rows = original


# =======================================================================================================================================
# Interpretation matrix and language discipline
# =======================================================================================================================================
def assert_clean_language(value, path=""):
    """No promotion / pass-fail / winner vocabulary may appear as a KEY anywhere in the audit output (the same discipline as the sibling studies' forbidden-key scan)."""
    if isinstance(value, dict):
        for key, inner in value.items():
            low = str(key).lower().replace("_", "").replace("/", "")
            if any(f.replace("/", "") in low for f in FORBIDDEN_LANGUAGE):
                raise ValueError("FORBIDDEN_LANGUAGE_IN_KEY: " + path + "/" + str(key))
            assert_clean_language(inner, path + "/" + str(key))
    elif isinstance(value, list):
        for inner in value:
            assert_clean_language(inner, path)


def question_entry(question, classification, evidence, basis):
    if classification not in CLASSIFICATIONS:
        raise ValueError("UNREGISTERED_CLASSIFICATION")
    return {"question": question, "classification": classification, "evidence": evidence, "basis": basis}


# =======================================================================================================================================
# The locally computable part: frozen inputs only, no formal artifact and no raw snapshot
# =======================================================================================================================================
EXTERNAL_TARGETS = (
    ("SAMSUNG_KODEX200_FACTSHEET", "Samsung Asset Management (Samsung Fund) KODEX 200 official product page and monthly factsheet", "https://www.samsungfund.com / https://www.kodex.com"),
    ("KRX_KODEX200_DATA", "Korea Exchange (KRX) official ETF and KOSPI 200 data", "https://data.krx.co.kr"),
    ("KODEX200_DISTRIBUTION_DISCLOSURE", "Official KODEX 200 distribution disclosures", "https://www.samsungfund.com / https://kind.krx.co.kr"))
EXTERNAL_CHECKPOINTS = ("2024-12-30", "2025-12-30", "2026-01-30", "2026-04-30", "2026-09-14")


def _round_floats(value, digits=12):
    if isinstance(value, dict):
        return {str(k): _round_floats(v, digits) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_round_floats(v, digits) for v in value]
    if isinstance(value, (np.floating, float)):
        return None if not math.isfinite(float(value)) else round(float(value), digits)
    if isinstance(value, np.integer):
        return int(value)
    return value


def frozen_checkpoints(levels, checkpoints=EXTERNAL_CHECKPOINTS):
    """The frozen benchmark at each external checkpoint: nearest session ON OR BEFORE the date, its level, and the year-to-date total return from the prior year's last session."""
    series = pd.Series(levels).sort_index()
    series.index = series.index.astype(str)
    rows = []
    for checkpoint in checkpoints:
        session = last_session_on_or_before(list(series.index), checkpoint)
        year_base = last_session_on_or_before(list(series.index), f"{int(session[:4]) - 1}-12-31")
        rows.append({"checkpoint": checkpoint, "session": session, "level": float(series[session]), "yearBaseSession": year_base,
                     "yearToDateReturn": float(series[session] / series[year_base] - 1)})
    return rows


def build_local_result(*, benchmark, index_levels, close, universe, sessions, calendar_sessions, identities, sealed_evidence, observed_github_state):
    """Everything this audit can establish from frozen, repository-resident inputs alone.

    benchmark / index_levels: date -> level Series (the frozen 069500.KS total-return close; the committed FDR KS200 price index). close: date x ticker DataFrame of the
    frozen total-return closes of the study's securities. universe: the pinned monthly universe snapshots. sessions: the formal window's sessions. identities: what the
    caller verified about its inputs (hashes, manifest digest). The formal result artifact and the raw KRX snapshot are NOT inputs: every section that needs them is
    emitted as NOT_RUN_IN_THIS_ENVIRONMENT with the reason."""
    bench = pd.Series(benchmark).sort_index()
    bench.index = bench.index.astype(str)
    index = pd.Series(index_levels).sort_index()
    index.index = index.index.astype(str)
    window = [d for d in sessions if WINDOW_START <= d <= CUTOFF]
    in_window = bench[(bench.index >= WINDOW_START) & (bench.index <= CUTOFF)]
    years = _years(window[0], window[-1])
    passive_cagr = annualize(float(in_window.iloc[-1] / in_window.iloc[0]), years)

    refs = {name: reference_portfolio(kind, close, universe, window, exclude=excl) for name, kind, excl in
            (("REF_TOP120_CAP_WEIGHTED", "CAP", ()), ("REF_TOP120_CAP_WEIGHTED_EX_SAMSUNG_HYNIX", "CAP", NAMED), ("REF_TOP120_EQUAL_WEIGHT", "EQUAL", ()))}
    ref_levels = {name: r["nav"] for name, r in refs.items()}

    ref_periods = {name: {row["period"]: {k: row[k] for k in ("fromSession", "toSession", "cumulativeReturn", "annualizedReturn", "logShareOfTerminalWealth")}
                          for row in period_decomposition(r["nav"])} for name, r in refs.items()}
    cap_contribution = contribution_by_period(refs["REF_TOP120_CAP_WEIGHTED"])
    snapshots = concentration_snapshots(universe)
    year_end = [f"{y}-12-31" for y in range(2016, 2026)] + [CUTOFF]
    in_formal_window = snapshots[snapshots.date >= "2017-01-01"]

    result = {
        "studyId": STUDY, "sourceStudy": SOURCE_STUDY, "scientificStatus": SCIENTIFIC_STATUS, "statement": STATEMENT, "formalIdentity": {k: v for k, v in FORMAL.items()},
        "formalStateObservedOnGitHub": observed_github_state, "evidenceClasses": list(EVIDENCE_CLASSES),
        "inputsVerified": identities,
        "returnBasisNote": ("The frozen benchmark is 069500.KS on the repository's AS_TRADED_CLOSE_WITH_FORWARD_ACCUMULATED_TOTAL_RETURN basis (KRX/FDR sessions joined to Yahoo "
                            "distributions via the krx-total-return route). It is an adjusted-index return with partial distributions: neither a price return nor a complete "
                            "shareholder total return. The primary formal benchmark remains 069500.KS; nothing below replaces it."),
        "benchmarkIntegrity": {"evidenceClass": RECONSTRUCTION, "status": "FROZEN_SERIES_READ_AND_HASH_VERIFIED",
                               **benchmark_integrity(bench, calendar_sessions)},
        "benchmarkPassiveReproduction": {
            "evidenceClass": RECONSTRUCTION, "windowFirstSession": window[0], "windowLastSession": window[-1], "years": years,
            "windowSessionsIncludingStart": len(window), "reproducedPassiveCumulativeReturn": float(in_window.iloc[-1] / in_window.iloc[0] - 1),
            "reproducedPassiveAnnualizedReturn": passive_cagr,
            "formalPassiveAnnualizedReturnQuotedInTheTask": 0.2024, "reproducesTheQuotedFormalFigureToFourDecimals": bool(passive_cagr is not None and round(passive_cagr, 4) == 0.2024),
            "formalArtifactComparison": NOT_RUN, "formalArtifactComparisonReason": "the formal result artifact is stored on Azure blob storage, unreachable from the authoring sandbox (CONNECT 403)",
            "formula": "(level[cutoff] / level[first anchor]) ** (365.2425 / calendar days) - 1, the formula pipeline.kr_integrated_alpha_portfolio_replay.summarize_path applies to the passive path"},
        "benchmarkPeriods": {"evidenceClass": RECONSTRUCTION, "levels": period_decomposition(bench), "calendarYears": calendar_year_returns(bench),
                             "checkpoints": frozen_checkpoints(bench)},
        "priceIndexPeriods": {"evidenceClass": PROXY, "description": "the committed FinanceDataReader KS200 PRICE index (no distributions), an independent route to the same market",
                              "levels": period_decomposition(index), "calendarYears": calendar_year_returns(index), "checkpoints": frozen_checkpoints(index)},
        "trackingCrossCheck": {"evidenceClass": PROXY, **tracking_cross_check(bench, index, {"refCapWeightedTop120": ref_levels["REF_TOP120_CAP_WEIGHTED"]})},
        "externalReconciliation": {
            "status": EXTERNAL_UNRESOLVED, "reason": "samsungfund.com, kodex.com and data.krx.co.kr are not reachable from the authoring sandbox (outbound HTTPS is allow-listed); no official "
            "value was retrieved, so no number below is an official number",
            "sourcesAttempted": [{"sourceId": s, "issuer": issuer, "urlFamily": url, "retrievalStatus": "UNREACHABLE", "value": None} for s, issuer, url in EXTERNAL_TARGETS],
            "frozenValuesToReconcile": frozen_checkpoints(bench),
            "basisToCompare": "the frozen series is an as-traded-close total return with forward-accumulated Yahoo distributions: compare with Samsung AM's DISTRIBUTION-REINVESTED "
                              "market-price or NAV return, never with a price-only return or a different date window",
            "possibleExplanationsToDecompose": ["market price vs NAV", "distribution reinvestment", "ex-date treatment", "split treatment", "benchmark publication date mismatch",
                                                "closing-price timing", "missing event", "incorrect event application", "raw vendor discrepancy", "simple date-window mismatch"],
            "benchmarkDistributionEvidence": ("the frozen store keeps only the total-return close for 069500.KS; its distribution events were applied upstream (Yahoo, as-traded) and are "
                                              "NOT stored as a separate component, so the applied events cannot be listed from the snapshot. They can only be inferred as the "
                                              "jump of the series over the price index on ex-dates (see trackingCrossCheck)")},
        "concentrationProxy": {
            "evidenceClass": PROXY, "label": "MARKET_CAP_SHARE_INSIDE_THE_PIT_TOP120_NOT_KODEX200_OR_KOSPI200_WEIGHT",
            "limitations": ["total (not free-float) market capitalisation", "the study's PIT Top120, not the KOSPI 200 constituent list", "monthly snapshots on the first trading day of each month",
                            "no index cap or methodology adjustment", "Samsung Electronics preferred shares (005935.KS) are not included in the named security"],
            "checkpoints": snapshot_table(snapshots, year_end), "thresholds": share_thresholds(snapshots),
            "formalWindowSnapshots": [{"date": r.date, "samsung": float(r["005930.KS"]), "skHynix": float(r["000660.KS"]), "combined": float(r.combined)}
                                      for _, r in in_formal_window.iterrows()]},
        "referencePortfolios": {
            "evidenceClass": PROXY, "rule": "Top120 members of each monthly universe snapshot; formed at the snapshot close; buy-and-hold between snapshots; no cost; same frozen "
            "total-return closes the study used; a missing mark carries the previous close",
            "notTheFormalBenchmark": True, "periods": ref_periods,
            "annualizedFullWindow": {name: annualize(float(r["nav"].iloc[-1]), years) for name, r in refs.items()},
            "rebalances": {name: r["rebalances"] for name, r in refs.items()},
            "namesWithoutPriceAtRebalance": {name: r["namesWithoutPriceAtRebalance"] for name, r in refs.items()}},
        "approximateBenchmarkContribution": {
            "evidenceClass": PROXY, "label": "APPROXIMATE_WEIGHTED_CONTRIBUTION_USING_MONTHLY_WEIGHT_SNAPSHOTS",
            "explanation": ("Contribution of Samsung Electronics and SK Hynix to the return of the CAP-WEIGHTED TOP120 reference (monthly market-cap weights, buy-and-hold between "
                            "snapshots, chained daily as nav_{t-1} * w_{t-1} * r_t). It is NOT the contribution to the KODEX 200 benchmark: the weights are proxy weights and the "
                            "reference is a different portfolio. Official PIT KODEX 200 / KOSPI 200 constituent weights were unreachable."),
            "periods": cap_contribution},
        "sealedAnatomyEvidence": sealed_evidence,
    }
    return _round_floats(result)


def not_run_sections():
    """The parts of the requested audit that need the formal result artifact or the raw KRX snapshot. They are emitted explicitly, never silently omitted."""
    reason = ("needs the exact formal result artifact and/or the 336 MB raw-input snapshot, both stored on Azure blob storage that the authoring sandbox cannot reach "
              "(CONNECT 403); the KRX daily market-value files in that snapshot are not stored in git")
    how = ("dispatch .github/workflows/kr-integrated-alpha-portfolio-v1-postoutcome-audit.yml (workflow_dispatch, read-only, never touches a lock) which downloads the two "
           "exact artifacts, verifies their identities, reproduces the formal A and D paths and only then attributes them")
    return {name: {"status": NOT_RUN, "reason": reason, "howToRun": how} for name in (
        "formalResultExtraction", "strategyPeriodDecomposition", "dPathReconstruction", "dHoldingsAndIndustryAttribution", "namedSecurityExposureInD", "dMinusAChronology",
        "dExcludeSamsungHynixSensitivity")}


def question_matrix(local):
    """The ten registered questions, classified only with the four registered labels. Rule-based from the computed numbers where the local evidence decides it."""
    levels = {r["period"]: r for r in local["benchmarkPeriods"]["levels"]}
    late_share = levels["B_2025"]["logShareOfTerminalWealth"] + levels["C_2026_to_cutoff"]["logShareOfTerminalWealth"]
    early_cagr = levels["A_2017_to_2024"]["annualizedReturn"]
    full_cagr = levels["D_full_window"]["annualizedReturn"]
    track = local["trackingCrossCheck"]["span2017To2024"]
    thr = local["concentrationProxy"]["thresholds"]["formalWindow"]
    contrib = local["approximateBenchmarkContribution"]["periods"]
    late = [contrib["B_2025"], contrib["C_2026_to_cutoff"]]
    late_combined_share = sum(p["combined"]["contributionNavUnits"] for p in late) / sum(p["gain"] for p in late)
    q = []
    q.append(question_entry("Q1. Is the formal passive CAGR a normal long-run Korean equity return, or heavily elevated by the 2025-2026 endpoint regime?", SUPPORTED,
                            f"On the frozen benchmark the last two spans (2025 and 2026 to the cutoff) carry {late_share:.1%} of the window's log wealth; 2017-2024 alone annualizes "
                            f"{early_cagr:.2%} against {full_cagr:.2%} for the full window.", "frozen benchmark series, fixed spans (reproduction of the benchmark path)"))
    q.append(question_entry("Q2. Is the frozen KODEX 200 benchmark internally correct?", PARTIAL,
                            "Hash-verified, complete against the registered calendar, no duplicate or non-positive level, and it reproduces the quoted passive CAGR. But its excess over "
                            f"the committed price index is {track['benchmarkOverIndexRelativePerYear']:.2%} a year over 2017-2024, against "
                            f"{track['refCapWeightedTop120OverIndexRelativePerYear']:.2%} for a same-data constituent total-return reference over the same span; the distribution events "
                            "behind it are not stored, so the gap cannot be decomposed from the snapshot.", "internal consistency only; no official value retrieved"))
    q.append(question_entry("Q3. Does it reconcile with authoritative external KODEX 200 evidence?", UNRESOLVED,
                            "No official source was reachable. The frozen values to reconcile are recorded for five fixed checkpoints.", EXTERNAL_UNRESOLVED))
    q.append(question_entry("Q4. How much benchmark concentration is explained by Samsung Electronics and SK Hynix?", PARTIAL,
                            f"Inside the PIT Top120 their combined market-cap share has a median of {thr['median']:.1%}, a maximum of {thr['maximum']:.1%} ({thr['maximumDate']}) and a latest "
                            f"value of {thr['latest']:.1%} ({thr['latestDate']}). This is a proxy for, not a measurement of, the KODEX 200 weight.", "PROXY_NOT_OFFICIAL_WEIGHT"))
    q.append(question_entry("Q5. How much of the benchmark's 2025-2026 return is attributable to them?", PARTIAL,
                            f"In the cap-weighted Top120 reference they contributed {late_combined_share:.1%} of its combined 2025 and 2026-to-cutoff gain "
                            "(APPROXIMATE_WEIGHTED_CONTRIBUTION_USING_MONTHLY_WEIGHT_SNAPSHOTS). Not exact for KODEX 200.", "APPROXIMATE_WEIGHTED_CONTRIBUTION_USING_MONTHLY_WEIGHT_SNAPSHOTS"))
    for name, text in (("Q6", "How much of D's 2025-2026 performance comes from Samsung Electronics and SK Hynix directly?"),
                       ("Q7", "How much comes from the broader industry exposure selected by the Industry layer?"),
                       ("Q8", "Did Industry help persistently over 2017-2024, or mostly in the recent industry-led regime?"),
                       ("Q9", "Does D_EXCLUDE_SAMSUNG_HYNIX materially change the descriptive result?")):
        q.append(question_entry(f"{name}. {text}", UNRESOLVED, "Needs the formal result artifact and the raw snapshot; not run in this environment.", NOT_RUN))
    q.append(question_entry("Q10. Does any benchmark or data-integrity issue require distrusting the formal economic comparison?", UNRESOLVED,
                            "The internal cross-check flags an unexplained excess of the frozen benchmark over both the price index and a same-data reference. If it were an error it "
                            "would overstate the passive path and therefore understate every architecture's excess; its size and direction cannot be settled without the official "
                            "distribution history.", EXTERNAL_UNRESOLVED))
    return q


# =======================================================================================================================================
# Facts carried forward from the two SEALED anatomy reports (read, never rerun)
# =======================================================================================================================================
INDUSTRY_FEATURES = ("REL_MOM_126", "BREADTH_ABOVE_MA_126")
STOCK_FEATURES = ("bookToMarketProxy", "earningsYieldProxy", "negativeDownsideVol126", "relative126")


def _table_after(text, heading):
    section = text.split(heading, 1)
    if len(section) != 2:
        raise ValueError("SEALED_REPORT_SECTION_NOT_FOUND: " + heading)
    rows = []
    for line in section[1].splitlines()[1:]:
        if line.startswith("## ") and rows:
            break
        if line.startswith("|"):
            rows.append([c.strip() for c in line.strip().strip("|").split("|")])
        elif rows and not line.strip():
            break
    return rows


def sealed_anatomy_evidence(industry_report, stock_report, hashes):
    """Quote, with provenance, what the two sealed reports already say about removing Samsung Electronics and SK Hynix. Parsed from the committed report text so the quoted
    numbers cannot drift from it. The interpretation keeps two questions apart: (A) does the SIGNAL ASSOCIATION survive removal of the two names (a statement about a
    cross-sectional rank statistic), and (B) does an implemented CONCENTRATED PORTFOLIO depend on holding them (a statement about a five-name book). A survives or not
    independently of B."""
    pattern = r"([+-][\d.]+) / ([+-][\d.]+) \((\d+), (\d+)\)"
    import re
    industry = {}
    rows = {r[0]: r for r in _table_after(industry_report, "## 5. Mega-cap and concentration sensitivities")}
    for feature in INDUSTRY_FEATURES:
        cells = rows[feature][1:4]
        parsed = [re.fullmatch(pattern, c) for c in cells]
        if not all(parsed):
            raise ValueError("SEALED_INDUSTRY_CELL_UNPARSED: " + feature)
        industry[feature] = {name: {"icMean": float(m.group(1)), "tercileSpreadPp": float(m.group(2)), "icDates": int(m.group(3)), "tercileDates": int(m.group(4))}
                             for name, m in zip(("FULL", "LEAVE_LARGEST_CONSTITUENT_OUT", "EXCLUDE_SAMSUNG_ELECTRONICS_AND_SK_HYNIX"), parsed)}
    grid = _table_after(stock_report, "## 5. Weight lens, horizon and sensitivity grid")
    header = grid[0]
    full_i, excl_i = header.index("FULL CAP H126"), header.index("EXCL CAP H126")
    stock = {}
    for row in grid[2:]:
        if row[0] in STOCK_FEATURES:
            stock[row[0]] = {"FULL_CAP_H126": float(row[full_i]), "EXCLUDE_SAMSUNG_ELECTRONICS_AND_SK_HYNIX_CAP_H126": float(row[excl_i])}
    if sorted(stock) != sorted(STOCK_FEATURES):
        raise ValueError("SEALED_STOCK_ROWS_INCOMPLETE")
    return {
        "provenance": {"industryAnatomyReport": "docs/results/kr-industry-opportunity-anatomy-v1-report.md", "stockAnatomyReport": "docs/results/kr-stock-within-industry-anatomy-v1-report.md",
                       "fileSha256": hashes, "studiesRerun": False},
        "industryAnatomy_FULL_vs_EXCLUDE_vs_LEAVE_LARGEST_OUT": {"view": "CAP_WEIGHTED H126; IC mean and top-minus-bottom tercile spread in percentage points", "features": industry},
        "stockWithinIndustryAnatomy_FULL_vs_EXCLUDE": {"view": "within-industry rank, CAP_WEIGHTED H126, mean per-date rank correlation", "features": stock},
        "interpretation": {
            "A_signalAssociationSurvivesRemovingTheTwoNames": ("In the sealed readings the REL_MOM_126 and BREADTH_ABOVE_MA_126 industry associations keep their sign when only the two names are "
                                                              "removed; leaving the single largest constituent out of each industry shrinks the REL_MOM_126 tercile spread to near zero. "
                                                              "The four stock features keep their sign and most of their size when the two names are removed."),
            "B_implementedConcentratedPortfolioDependsOnThem": ("NOT ANSWERED by these reports. They measure rank associations over the whole cross-section; they say nothing about whether a "
                                                               "five-name book held the two names, how large their weights were, or what they earned. That is what the D reconstruction "
                                                               "and the D_EXCLUDE_SAMSUNG_HYNIX sensitivity are for."),
            "caveat": "both sealed studies are exploratory, overlap-heavy, outcome-exposed and carry the partial-distribution return basis"}}


def markdown_report(result):
    """Human-readable report rendered from the result dict (and nothing else), so the prose cannot disagree with the JSON."""
    L = []
    add = L.append
    levels = {r["period"]: r for r in result["benchmarkPeriods"]["levels"]}
    index_levels = {r["period"]: r for r in result["priceIndexPeriods"]["levels"]}
    track = result["trackingCrossCheck"]
    thr = result["concentrationProxy"]["thresholds"]["formalWindow"]
    refs = result["referencePortfolios"]
    contrib = result["approximateBenchmarkContribution"]["periods"]
    matrix = result["questionMatrix"]
    pct = lambda x: "n/a" if x is None else f"{x:+.2%}"       # noqa: E731
    share = lambda x: "n/a" if x is None else f"{x:.1%}"      # noqa: E731
    f = result["formalIdentity"]

    add("# KR integrated alpha portfolio v1 — post-outcome concentration audit")
    add("")
    add(f"**{STATEMENT}**")
    add("")
    add(f"Scientific status: `{SCIENTIFIC_STATUS}`. Formal execution run `{f['workflowRunId']}` at `{f['executionSha'][:12]}` (spec `{f['specSha256'][:12]}…`). The formal result is not "
        "rerun, rewritten or reinterpreted here; the locks were not touched; the primary formal benchmark remains `069500.KS`.")
    add("")
    add("**What this report could and could not do.** The formal result artifact and the 336 MB raw-input snapshot sit on GitHub's Azure blob storage, which the authoring "
        "environment cannot reach, and no official KODEX 200 source (Samsung Asset Management, KRX) was reachable either. So every number below comes from frozen, repository-resident "
        "inputs and is labelled as a reconstruction or a proxy; every section that needs the artifacts is marked `NOT_RUN_IN_THIS_ENVIRONMENT` and is runnable through the read-only "
        "audit workflow added with this report.")
    add("")
    add("## 1. Executive conclusion")
    add("")
    late = levels["B_2025"]["logShareOfTerminalWealth"] + levels["C_2026_to_cutoff"]["logShareOfTerminalWealth"]
    add(f"* **The ~20.24% passive figure is dominated by the last 20 months.** The frozen benchmark reproduces {pct(levels['D_full_window']['annualizedReturn'])} a year over the full window "
        f"({pct(levels['D_full_window']['cumulativeReturn'])} cumulative). Only the first span (2017-2024) is a multi-year regime: it annualizes {pct(levels['A_2017_to_2024']['annualizedReturn'])}. "
        f"2025 alone returned {pct(levels['B_2025']['cumulativeReturn'])} and 2026 to the cutoff {pct(levels['C_2026_to_cutoff']['cumulativeReturn'])}; together they carry {share(late)} "
        f"of the window's log wealth and {share(levels['B_2025']['shareOfTerminalGain'] + levels['C_2026_to_cutoff']['shareOfTerminalGain'])} of its terminal gain.")
    add(f"* **Samsung Electronics and SK Hynix became a very large part of the market.** Inside the PIT Top120 their combined market-cap share has a median of {share(thr['median'])} in the "
        f"formal window, peaked at {share(thr['maximum'])} ({thr['maximumDate']}) and was {share(thr['latest'])} on {thr['latestDate']}. This is a market-cap proxy, not the KODEX 200 weight.")
    cap2526 = [contrib["B_2025"], contrib["C_2026_to_cutoff"]]
    add(f"* **They account for a large share of the recent gain in a broad cap-weighted reference.** In the cap-weighted Top120 reference they contributed "
        f"{share(sum(p['combined']['contributionNavUnits'] for p in cap2526) / sum(p['gain'] for p in cap2526))} of the 2025 plus 2026-to-cutoff gain (approximate; monthly proxy weights).")
    full_years = [track["byCalendarYear"][str(y)]["benchmarkOverIndexRelative"] for y in range(2018, 2026)]
    add(f"* **The benchmark's internal cross-check raises a question that needs official data.** Over 2017-2024 the frozen benchmark earned {pct(track['span2017To2024']['benchmarkOverIndexRelativePerYear'])} "
        f"a year above the committed KS200 price index, against {pct(track['span2017To2024']['refCapWeightedTop120OverIndexRelativePerYear'])} for the same-data constituent reference. "
        f"In every full calendar year 2018-2025 the benchmark's excess over the index sat between {pct(min(full_years))} and {pct(max(full_years))}, including 2025 when the index itself "
        f"rose {pct(result['priceIndexPeriods']['calendarYears']['2025']['return'])}. Whether that gap is real distribution income or an overstatement of the applied events cannot be "
        f"settled here; it is classified `{EXTERNAL_UNRESOLVED}`.")
    add("* **The statement \"Industry was strongly supported\" cannot be re-examined here.** It rests on the formal A and D paths and their calendar-year chronology, which this environment "
        "could not read or reconstruct. Nothing in the locally computable evidence supports or contradicts narrowing it; the chronology of D versus A, the direct Samsung/SK Hynix exposure of D "
        "and the D_EXCLUDE_SAMSUNG_HYNIX sensitivity are the evidence that decides it, and they are `NOT_RUN_IN_THIS_ENVIRONMENT`.")
    add("")
    add("## 2. Is the 20.24% benchmark CAGR misleading without period decomposition?")
    add("")
    add("Frozen benchmark (`069500.KS`, total-return basis). Fixed spans; no breakpoint was optimised. Evidence class: " + RECONSTRUCTION + ".")
    add("")
    add("| Span | From → to | Start level | End level | Cumulative | Annualized | Daily steps | Share of log wealth | Share of terminal gain |")
    add("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for r in result["benchmarkPeriods"]["levels"]:
        add(f"| {r['period']} | {r['fromSession']} → {r['toSession']} | {r['startLevel']:,.1f} | {r['endLevel']:,.1f} | {pct(r['cumulativeReturn'])} | "
            f"{pct(r['annualizedReturn'])} | {r['sessions']} | {share(r['logShareOfTerminalWealth'])} | {share(r['shareOfTerminalGain'])} |")
    add("")
    add("Annualized is shown only for spans of a full year or more (calendar 2025 between its two year-end sessions counts; 2026 to the cutoff is 0.7 years and is not annualized). Calendar years (frozen benchmark vs the committed KS200 price index):")
    add("")
    add("| Year | Benchmark | KS200 price index |")
    add("|---|---:|---:|")
    for y in CALENDAR_YEARS:
        note = " (from 2017-01-16)" if y == 2017 else (f" (to {CUTOFF})" if y == 2026 else "")
        add(f"| {y}{note} | {pct(result['benchmarkPeriods']['calendarYears'][str(y)]['return'])} | {pct(result['priceIndexPeriods']['calendarYears'][str(y)]['return'])} |")
    add("")
    add("A and D strategy decomposition: `NOT_RUN_IN_THIS_ENVIRONMENT` (needs the formal month-end NAV and calendar-year returns).")
    add("")
    add("## 3. Benchmark integrity and official reconciliation")
    add("")
    bi = result["benchmarkIntegrity"]
    add(f"* Series: {bi['sessions']} sessions, {bi['firstSession']} to {bi['lastSession']}; registered KR calendar {bi['calendarSessions']}; missing {len(bi['sessionsMissingFromSeries'])}, "
        f"not in calendar {len(bi['sessionsNotInCalendar'])}; non-positive or non-finite levels {bi['nonPositiveOrNonFiniteLevels']}.")
    rep = result["benchmarkPassiveReproduction"]
    add(f"* Passive path reproduced from the frozen series: {pct(rep['reproducedPassiveAnnualizedReturn'])} a year, {pct(rep['reproducedPassiveCumulativeReturn'])} cumulative over "
        f"{rep['windowFirstSession']} → {rep['windowLastSession']}; matches the ~20.24% quoted for the formal result to four decimals: {rep['reproducesTheQuotedFormalFigureToFourDecimals']}. "
        "The artifact's own value could not be read, so the exact comparison is not run.")
    add(f"* Daily moves of at least 10% inside the window: {len(bi['dailyMovesAtLeast10Percent'])} (largest {pct(bi['largestDailyMoveInWindow']['return'])} on {bi['largestDailyMoveInWindow']['date']}). "
        "They are reported, not edited; each should be confirmed against an official source.")
    add("* The snapshot stores the benchmark only as a total-return close. Its distribution and split events were applied upstream and are not a separate component, so a "
        "from-events reconstruction is impossible from the snapshot; this is a data limitation, not a mismatch (`BENCHMARK_RECONSTRUCTION_MISMATCH` was not triggered).")
    add("")
    add("Tracking cross-check (evidence class " + PROXY + "): the benchmark's excess over the committed price index.")
    add("")
    add("| Year | Benchmark | KS200 price index | Benchmark over index | Cap-weighted Top120 reference | Reference over index |")
    add("|---|---:|---:|---:|---:|---:|")
    for y in CALENDAR_YEARS:
        r = track["byCalendarYear"][str(y)]
        add(f"| {y} | {pct(r['benchmark'])} | {pct(r['index'])} | {pct(r['benchmarkOverIndexRelative'])} | {pct(r['refCapWeightedTop120'])} | {pct(r['refCapWeightedTop120OverIndexRelative'])} |")
    s = track["span2017To2024"]
    add("")
    add(f"2017-2024 as one span: benchmark {pct(s['benchmark'])}, price index {pct(s['index'])}, cap-weighted reference {pct(s['refCapWeightedTop120'])}; the benchmark's annual excess over "
        f"the index is {pct(s['benchmarkOverIndexRelativePerYear'])} and the reference's is {pct(s['refCapWeightedTop120OverIndexRelativePerYear'])}. After 2024 the reference differs from the index by "
        "composition (the two names), so only the 2017-2024 span is like-for-like.")
    add("")
    ext = result["externalReconciliation"]
    add(f"**External reconciliation: `{ext['status']}`.** {ext['reason']}. The frozen values to reconcile against Samsung Asset Management / KRX at fixed checkpoints:")
    add("")
    add("| Checkpoint | Session | Level | Year-to-date total return (frozen) |")
    add("|---|---|---:|---:|")
    for r in ext["frozenValuesToReconcile"]:
        add(f"| {r['checkpoint']} | {r['session']} | {r['level']:,.1f} | {pct(r['yearToDateReturn'])} |")
    add("")
    add("No official number is quoted anywhere in this report. " + ext["basisToCompare"])
    add("")
    add("## 4. Samsung Electronics + SK Hynix concentration (proxy)")
    add("")
    add("Share of the total market capitalisation of the PIT Top120 (monthly snapshots; not free-float; not the KOSPI 200 weight).")
    add("")
    add("| Snapshot on or before | Samsung Electronics | SK Hynix | Combined |")
    add("|---|---:|---:|---:|")
    for r in result["concentrationProxy"]["checkpoints"]:
        if r.get("snapshot"):
            add(f"| {r['checkpoint']} ({r['snapshot']}) | {share(r['Samsung Electronics'])} | {share(r['SK Hynix'])} | {share(r['combined'])} |")
    add("")
    add(f"Formal window: maximum {share(thr['maximum'])} ({thr['maximumDate']}), median {share(thr['median'])}, minimum {share(thr['minimum'])} ({thr['minimumDate']}). Snapshots above each descriptive round number:")
    add("")
    add("| Threshold | Snapshots above | First | Last | Runs |")
    add("|---:|---:|---|---|---|")
    for k, v in thr["thresholds"].items():
        runs = "; ".join(f"{r['from']}→{r['to']}" for r in v["runs"][-3:]) or "none"
        add(f"| {float(k):.0%} | {v['snapshotsAbove']} of {thr['snapshots']} | {v['first'] or '—'} | {v['last'] or '—'} | {runs} |")
    add("")
    add("## 5. Benchmark return contribution (approximate, proxy weights)")
    add("")
    add("Label: `APPROXIMATE_WEIGHTED_CONTRIBUTION_USING_MONTHLY_WEIGHT_SNAPSHOTS`. " + result["approximateBenchmarkContribution"]["explanation"])
    add("")
    add("| Span | Reference gain | Samsung Electronics | SK Hynix | Combined | Residual | Combined share of gain |")
    add("|---|---:|---:|---:|---:|---:|---:|")
    for label, p in contrib.items():
        sec = p["securities"]
        add(f"| {label} | {p['gain']:+.3f} | {sec['005930.KS']['contributionNavUnits']:+.3f} | {sec['000660.KS']['contributionNavUnits']:+.3f} | {p['combined']['contributionNavUnits']:+.3f} | "
            f"{p['residual']['contributionNavUnits']:+.3f} | {share(p['combined']['shareOfSpanGain'])} |")
    add("")
    add("Contributions are in units of the reference's NAV (1.0 at the window start). Same-data reference portfolios (descriptive lenses, not the benchmark):")
    add("")
    add("| Reference | Full window | Annualized | 2017-2024 | 2025 | 2026 to cutoff |")
    add("|---|---:|---:|---:|---:|---:|")
    for name, per in refs["periods"].items():
        add(f"| {name} | {pct(per['D_full_window']['cumulativeReturn'])} | {pct(refs['annualizedFullWindow'][name])} | {pct(per['A_2017_to_2024']['cumulativeReturn'])} | "
            f"{pct(per['B_2025']['cumulativeReturn'])} | {pct(per['C_2026_to_cutoff']['cumulativeReturn'])} |")
    add(f"| Frozen benchmark (069500.KS TR) | {pct(levels['D_full_window']['cumulativeReturn'])} | {pct(levels['D_full_window']['annualizedReturn'])} | {pct(levels['A_2017_to_2024']['cumulativeReturn'])} | "
        f"{pct(levels['B_2025']['cumulativeReturn'])} | {pct(levels['C_2026_to_cutoff']['cumulativeReturn'])} |")
    add(f"| KS200 price index | {pct(index_levels['D_full_window']['cumulativeReturn'])} | {pct(index_levels['D_full_window']['annualizedReturn'])} | {pct(index_levels['A_2017_to_2024']['cumulativeReturn'])} | "
        f"{pct(index_levels['B_2025']['cumulativeReturn'])} | {pct(index_levels['C_2026_to_cutoff']['cumulativeReturn'])} |")
    add("")
    cap, ex = refs["periods"]["REF_TOP120_CAP_WEIGHTED"], refs["periods"]["REF_TOP120_CAP_WEIGHTED_EX_SAMSUNG_HYNIX"]
    lower = all(ex[k]["cumulativeReturn"] < cap[k]["cumulativeReturn"] for k in ("B_2025", "C_2026_to_cutoff"))
    add(("Removing the two names leaves a broad Korean large-cap cross-section that returned much less in 2025 and in 2026 to the cutoff than the cap-weighted reference "
         f"({pct(ex['B_2025']['cumulativeReturn'])} vs {pct(cap['B_2025']['cumulativeReturn'])} and {pct(ex['C_2026_to_cutoff']['cumulativeReturn'])} vs {pct(cap['C_2026_to_cutoff']['cumulativeReturn'])}); "
         "the recent regime is, in this lens, a concentration phenomenon in these two securities as much as a market-wide one. ") if lower else
        "Removing the two names did not lower the reference's 2025 and 2026 returns in both spans. ")
    add("This is a description of the reference portfolios, not a statement about what the investor's passive alternative should be: the formal benchmark "
        "stays `069500.KS`, concentration included.")
    add("")
    names = sorted(result["notRunSections"])
    first = result["notRunSections"][names[0]]
    groups = (("## 6. A vs D chronology", ("strategyPeriodDecomposition", "dMinusAChronology")),
              ("## 7. D holdings and industry attribution", ("dPathReconstruction", "dHoldingsAndIndustryAttribution")),
              ("## 8. Samsung Electronics + SK Hynix direct exposure in D", ("namedSecurityExposureInD",)),
              ("## 9. D_EXCLUDE_SAMSUNG_HYNIX sensitivity", ("dExcludeSamsungHynixSensitivity",)))
    for heading, members in groups:
        add(heading)
        add("")
        add("`" + first["status"] + "`: " + ", ".join(f"`{m}`" for m in members) + ". Not computed, not estimated, not inferred from the proxies above.")
        add("")
    add("Why: " + first["reason"] + ".")
    add("")
    add("How to run them: " + first["howToRun"] + ". The audit-only reconstruction must reproduce the formal A and D metrics and month-end NAVs "
        f"(tolerance 1e-9) before any attribution is trusted; otherwise it stops with `{D_PATH_RECONSTRUCTION_MISMATCH}` and reports the first divergence. The only strategy "
        "counterfactual is `D_EXCLUDE_SAMSUNG_HYNIX` (the two tickers removed after scoring and before selection, every other frozen rule unchanged); no other exclusion set is run. "
        "Also run in that workflow: `formalResultExtraction` (the formal values copied verbatim as FORMAL_REPORTED_RESULT).")
    add("")
    add("## 10. Existing sealed mega-cap anatomy evidence (read, not rerun)")
    add("")
    ev = result["sealedAnatomyEvidence"]
    add("Industry anatomy, CAP_WEIGHTED H126 (IC mean / tercile spread pp):")
    add("")
    add("| Feature | FULL | Leave largest constituent out | Exclude Samsung + SK Hynix |")
    add("|---|---:|---:|---:|")
    for feat, v in ev["industryAnatomy_FULL_vs_EXCLUDE_vs_LEAVE_LARGEST_OUT"]["features"].items():
        cells = [f"{v[k]['icMean']:+.3f} / {v[k]['tercileSpreadPp']:+.1f}" for k in ("FULL", "LEAVE_LARGEST_CONSTITUENT_OUT", "EXCLUDE_SAMSUNG_ELECTRONICS_AND_SK_HYNIX")]
        add(f"| {feat} | " + " | ".join(cells) + " |")
    add("")
    add("Stock within-industry anatomy, CAP_WEIGHTED H126 (mean rank correlation):")
    add("")
    add("| Feature | FULL | Exclude Samsung + SK Hynix |")
    add("|---|---:|---:|")
    for feat, v in ev["stockWithinIndustryAnatomy_FULL_vs_EXCLUDE"]["features"].items():
        add(f"| {feat} | {v['FULL_CAP_H126']:+.3f} | {v['EXCLUDE_SAMSUNG_ELECTRONICS_AND_SK_HYNIX_CAP_H126']:+.3f} |")
    add("")
    add("* **A — signal association.** " + ev["interpretation"]["A_signalAssociationSurvivesRemovingTheTwoNames"])
    add("* **B — implemented portfolio.** " + ev["interpretation"]["B_implementedConcentratedPortfolioDependsOnThem"])
    add("")
    add("## 11. What is actually established")
    add("")
    for q in matrix:
        if q["classification"] in (SUPPORTED, PARTIAL):
            add(f"* **{q['question']}** `{q['classification']}` — {q['evidence']}")
    add("")
    add("## 12. What remains uncertain")
    add("")
    for q in matrix:
        if q["classification"] in (UNRESOLVED, NOT_SUPPORTED):
            add(f"* **{q['question']}** `{q['classification']}` — {q['evidence']}")
    add("")
    add("## 13. Consequence for the next research step")
    add("")
    add("1. Dispatch the read-only audit workflow once, so the A/D reconstruction, attribution and the single registered sensitivity are computed against the exact artifacts; do not "
        "rerun `kr-integrated-alpha-portfolio-v1` (its lock is spent).")
    add("2. Obtain Samsung Asset Management's KODEX 200 distribution-reinvested return and KRX's KOSPI 200 total-return index at the five checkpoints and decompose any gap with the "
        "listed explanations. Until then the passive path carries an unresolved question.")
    add("3. Any narrowing of the Industry conclusion is decided by the D-versus-A chronology and the exposure tables above once they exist, not before. The prospective receipts remain the only route to evidence.")
    add("")
    add("*This is a post-outcome descriptive diagnostic. It does not change the formal result, any frozen rule or any decision, and it is not prospective evidence.*")
    return "\n".join(L) + "\n"
