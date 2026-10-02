"""KR Top120 regime review v1 — pure descriptive instruments.

EXPLORATORY_POST_OUTCOME_REGIME_DIAGNOSTIC. This study was designed AFTER `kr-factor-anatomy-v1` outcomes were seen, so
nothing here confirms a factor, validates a strategy, rescues `kr-model-overlay-portfolio-v1`, produces a weight, picks a
best factor or tunes a threshold. It only asks whether relationships the anatomy already showed are concentrated in
particular outcome windows, signal-time market states or mega-cap names.

No I/O, no network, no model fit, no portfolio. Functions receive frames and return tables. Anatomy helpers
(`kr_factor_anatomy`) are REUSED, never copied, wherever the arithmetic is identical; the sealed anatomy module is not edited.

Rules that run through every function and are tested on synthetic data:

* CHRONOLOGY IS BY OUTCOME WINDOW. A slice is decided by an observation's entry and exit dates, not by its signal year: a
  late-2024 signal that matures inside 2025 is a 2025 observation.
* RANKS ARE SIGNAL-TIME AND ARE RECOMPUTED AFTER A MECHANICAL EXCLUSION. A slice only removes outcomes; a sensitivity
  universe removes names BEFORE ranking, so deciles are formed inside the reduced same-date cross-section.
* EXTREME WINNERS ARE NOT TRIMMED. There is no winsorisation anywhere; the fixed robust views are the per-date median
  spread and the mean within-date Spearman correlation, reported beside the ordinary mean spread and never substituted for it.
* A MISSING PEER IS NEVER A ZERO. The leave-one-out benchmark needs a frozen minimum number of OTHER valid names.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import kr_factor_anatomy as A
from . import kr_value_quality_catalyst as F

STUDY = "kr-top120-regime-review-v1"
SCIENTIFIC_STATUS = "EXPLORATORY_POST_OUTCOME_REGIME_DIAGNOSTIC"
RETURN_BASIS = A.RETURN_BASIS
HORIZONS = (126, 252)
FACTORS = tuple(F.RAW_FEATURES)
PRIMARY_UNIVERSE = "PIT_TOP120_LARGE_CAP_ANALYSIS_UNIVERSE"

SAMSUNG_ELECTRONICS = "005930.KS"
SK_HYNIX = "000660.KS"
UNIVERSES = ("FULL_TOP120", "EXCLUDE_SAMSUNG_ELECTRONICS", "EXCLUDE_SK_HYNIX", "EXCLUDE_BOTH", "EXCLUDE_DYNAMIC_TOP2_MARKET_CAP")
# The ONLY names any sensitivity may remove by identity. Anything else must come from the signal-date market-cap rule.
FIXED_EXCLUSIONS = {"FULL_TOP120": (), "EXCLUDE_SAMSUNG_ELECTRONICS": (SAMSUNG_ELECTRONICS,),
                    "EXCLUDE_SK_HYNIX": (SK_HYNIX,), "EXCLUDE_BOTH": (SAMSUNG_ELECTRONICS, SK_HYNIX)}
DYNAMIC_TOP_COUNT = 2

SLICES = ("FULL_SAMPLE", "PRE_2025_COMPLETE_WINDOW", "TOUCHES_2025_OR_LATER", "PRE_2026_COMPLETE_WINDOW", "TOUCHES_2026",
          "EXCLUDE_WINDOWS_TOUCHING_2025", "EXCLUDE_WINDOWS_TOUCHING_2026", "EXCLUDE_WINDOWS_TOUCHING_2025_OR_2026")
REGIME_STATES = ("TREND_OK", "TREND_BAD", "VOL_OK", "VOL_HIGH", "TREND_OK_VOL_OK", "TREND_BAD_VOL_OK", "TREND_OK_VOL_HIGH",
                 "TREND_BAD_VOL_HIGH", "RISK_MULTIPLIER_1.0", "RISK_MULTIPLIER_0.7", "RISK_MULTIPLIER_0.4")
OUTCOMES = ("ABSOLUTE_STOCK_RETURN", "KODEX200_RELATIVE_RETURN", "TOP120_LEAVE_ONE_OUT_EQUAL_WEIGHT_RELATIVE_RETURN")
LABELS = ("PERSISTENT_ACROSS_PRE_RECENT_AND_RECENT", "RECENT_REGIME_CONCENTRATED", "PRE_RECENT_ONLY", "OUTLIER_SENSITIVE",
          "MEGA_CAP_SENSITIVE", "REGIME_DEPENDENT", "NO_CLEAR_PATTERN", "DATA_INSUFFICIENT")
FORBIDDEN_OUTPUT_KEY_FRAGMENTS = A.FORBIDDEN_OUTPUT_KEY_FRAGMENTS + ("validated", "proven", "bestfactor", "recommend", "production")
IMPROVEMENT_FLAGS = {"ocfImprovementUp": "ocfImprovementToAssets", "netIncomeImprovementUp": "netIncomeImprovementToAssets"}
SUCCESS_DEFINITIONS = ("ABSOLUTE_UP", "BEATS_KODEX200", "BEATS_TOP120_EQUAL_WEIGHT")


# --------------------------------------------------------------------------- #
# Chronology: slices by OUTCOME WINDOW (entry / exit), never by signal year alone
# --------------------------------------------------------------------------- #
def window_touches_year(entry, exit_, year):
    """True when the closed [entry, exit] interval intersects calendar `year`. ISO date strings compare lexicographically."""
    entry, exit_ = pd.Series(entry, dtype=object), pd.Series(exit_, dtype=object)
    known = entry.notna() & exit_.notna()
    e, x = entry.fillna("").astype(str), exit_.fillna("").astype(str)
    return known & (e <= f"{year}-12-31") & (x >= f"{year}-01-01")


def slice_mask(name, entry, exit_, cutoff):
    """Boolean mask over observations. An observation with an unknown entry/exit belongs to no slice (never to FULL_SAMPLE
    silently): classification needs a window."""
    entry, exit_ = pd.Series(entry, dtype=object), pd.Series(exit_, dtype=object)
    known = entry.notna() & exit_.notna()
    e, x = entry.fillna("").astype(str), exit_.fillna("").astype(str)
    if name == "FULL_SAMPLE":
        return known
    if name == "PRE_2025_COMPLETE_WINDOW":
        return known & (x < "2025-01-01")
    if name == "TOUCHES_2025_OR_LATER":
        return known & (x >= "2025-01-01")
    if name == "PRE_2026_COMPLETE_WINDOW":
        return known & (x < "2026-01-01")
    if name == "TOUCHES_2026":
        return known & (e <= cutoff) & (x >= "2026-01-01")
    if name == "EXCLUDE_WINDOWS_TOUCHING_2025":
        return known & ~window_touches_year(entry, exit_, 2025)
    if name == "EXCLUDE_WINDOWS_TOUCHING_2026":
        return known & ~window_touches_year(entry, exit_, 2026)
    if name == "EXCLUDE_WINDOWS_TOUCHING_2025_OR_2026":
        return known & ~(window_touches_year(entry, exit_, 2025) | window_touches_year(entry, exit_, 2026))
    raise ValueError("UNREGISTERED_SLICE")


# --------------------------------------------------------------------------- #
# Outcomes: three DISTINCT returns
# --------------------------------------------------------------------------- #
def leave_one_out_relative(stock, dates, minimum_peers):
    """stock return of i minus the arithmetic mean of all OTHER valid stock returns on the same date. NaN where the stock
    itself is invalid or fewer than `minimum_peers` OTHER valid names exist; never a zero fill. The sum is an exactly
    rounded `fsum`, so the result does not depend on row order."""
    x = A.clean_numeric(stock)
    out = np.full(len(x), np.nan)
    for index in pd.Series(np.arange(len(x))).groupby(np.asarray(dates)).indices.values():
        values = x[index]
        valid = np.isfinite(values)
        n = int(valid.sum())
        if n - 1 < minimum_peers:
            continue
        total = math.fsum(np.sort(values[valid]))
        out[index[valid]] = values[valid] - (total - values[valid]) / (n - 1)
    return out


def add_outcomes(panel, minimum_peers):
    """Adds, per horizon h: `abs{h}` (treated stock return, NaN unless the observation is MATURED under the v1 terminal
    discipline), `kodex{h}` (that return minus the KODEX200 return — the anatomy's `rel{h}`) and `loo{h}` (leave-one-out
    equal-weight Top120 relative return, peers drawn from the FULL PIT Top120 panel)."""
    out = panel.copy().reset_index(drop=True)
    for h in HORIZONS:
        s = str(h)
        matured = out["status" + s].eq("MATURED")
        stock = A.clean_numeric(out["stock" + s])
        out["abs" + s] = np.where(matured, stock, np.nan)
        out["kodex" + s] = np.where(matured, stock - A.clean_numeric(out["bench" + s]), np.nan)
        out["loo" + s] = leave_one_out_relative(out["abs" + s], out["date"].to_numpy(), minimum_peers)
    return out


# --------------------------------------------------------------------------- #
# Sensitivity universes (names removed BEFORE ranking)
# --------------------------------------------------------------------------- #
def dynamic_top_names(panel, count=DYNAMIC_TOP_COUNT):
    """The `count` largest names by SIGNAL-DATE market cap on each date, ties broken by ticker. Reads only `date`,
    `ticker` and `marketCap`: no outcome column can influence it. Names without a finite market cap are never removed."""
    removed = {}
    for date, group in panel.groupby("date"):
        cap = pd.to_numeric(group.marketCap, errors="coerce")
        ok = group.loc[np.isfinite(cap), ["ticker"]].assign(cap=cap[np.isfinite(cap)])
        top = ok.sort_values(["cap", "ticker"], ascending=[False, True]).head(count)
        removed[date] = list(top.ticker)
    return removed


def apply_universe(panel, name):
    """(reduced panel, removed rows). Only the registered fixed identities or the dynamic market-cap rule can remove a row."""
    if name not in UNIVERSES:
        raise ValueError("UNREGISTERED_SENSITIVITY_UNIVERSE")
    if name == "EXCLUDE_DYNAMIC_TOP2_MARKET_CAP":
        removed = dynamic_top_names(panel[["date", "ticker", "marketCap"]])
        drop = np.fromiter((t in removed.get(d, ()) for d, t in zip(panel.date, panel.ticker)), bool, len(panel))
    else:
        drop = panel.ticker.isin(set(FIXED_EXCLUSIONS[name])).to_numpy()
    return panel.loc[~drop].reset_index(drop=True), panel.loc[drop].reset_index(drop=True)


def ranked_universe(panel, name, factors=FACTORS):
    """Reduced universe with same-date percentiles / counts RECOMPUTED inside it."""
    reduced, removed = apply_universe(panel, name)
    return A.add_signal_time_ranks(reduced, list(factors)), removed


# --------------------------------------------------------------------------- #
# Signal-time market states and concentration context
# --------------------------------------------------------------------------- #
def state_masks(frame):
    """Row masks for the frozen market states from SIGNAL-TIME columns only. Rows whose state could not be read
    (`riskMultiplier` missing) belong to no state."""
    risk = pd.to_numeric(frame.get("riskMultiplier"), errors="coerce")
    ready = risk.notna()
    trend = frame["trendAdverse"].map(lambda v: bool(v) if v is not None and v == v else None)
    vol = frame["volAdverse"].map(lambda v: bool(v) if v is not None and v == v else None)
    t_bad, v_bad = (trend == True).fillna(False), (vol == True).fillna(False)  # noqa: E712
    t_ok, v_ok = (trend == False).fillna(False), (vol == False).fillna(False)  # noqa: E712
    masks = {"TREND_OK": ready & t_ok, "TREND_BAD": ready & t_bad, "VOL_OK": ready & v_ok, "VOL_HIGH": ready & v_bad,
             "TREND_OK_VOL_OK": ready & t_ok & v_ok, "TREND_BAD_VOL_OK": ready & t_bad & v_ok,
             "TREND_OK_VOL_HIGH": ready & t_ok & v_bad, "TREND_BAD_VOL_HIGH": ready & t_bad & v_bad}
    for level in (1.0, 0.7, 0.4):
        masks[f"RISK_MULTIPLIER_{level}"] = ready & np.isclose(risk.fillna(-1).to_numpy(float), level)
    return masks


def concentration_context(panel):
    """Per signal date: Samsung / Hynix / combined / largest-name / top-2 shares of the PIT Top120 market cap, plus the
    signal-time benchmark state. Context only: nothing here is a threshold or a gate."""
    rows = []
    for date, group in sorted(panel.groupby("date"), key=lambda kv: kv[0]):
        cap = pd.to_numeric(group.marketCap, errors="coerce").to_numpy(float)
        finite = np.isfinite(cap)
        total = math.fsum(np.sort(cap[finite])) if finite.any() else float("nan")
        by = dict(zip(group.ticker, cap))

        def share(value):
            return float(value / total) if finite.any() and total > 0 and np.isfinite(value) else None
        ordered = np.sort(cap[finite])[::-1]
        first = group.iloc[0]
        rows.append({"date": date, "names": int(len(group)), "namesWithMarketCap": int(finite.sum()),
                     "samsungElectronicsShare": share(by.get(SAMSUNG_ELECTRONICS, np.nan)),
                     "skHynixShare": share(by.get(SK_HYNIX, np.nan)),
                     "combinedShare": share(by.get(SAMSUNG_ELECTRONICS, np.nan) + by.get(SK_HYNIX, np.nan)),
                     "dynamicLargestShare": share(ordered[0]) if len(ordered) else None,
                     "dynamicTop2Share": share(ordered[:2].sum()) if len(ordered) >= 2 else None,
                     "trendAdverse": _optional_bool(first.get("trendAdverse")), "volAdverse": _optional_bool(first.get("volAdverse")),
                     "riskMultiplier": None if pd.isna(first.get("riskMultiplier")) else float(first.get("riskMultiplier"))})
    return rows


def _optional_bool(value):
    return None if value is None or (isinstance(value, float) and math.isnan(value)) else bool(value)


# --------------------------------------------------------------------------- #
# One factor view: mean spread, MEDIAN spread, within-date Spearman — three separate outputs
# --------------------------------------------------------------------------- #
def assert_no_forbidden_keys(value, path=""):
    """Outputs may not carry promotion / PASS / FAIL / validated / best-factor semantics anywhere in their key space."""
    if isinstance(value, dict):
        for key, item in value.items():
            if any(fragment in str(key).lower().replace("_", "") for fragment in FORBIDDEN_OUTPUT_KEY_FRAGMENTS):
                raise ValueError("FORBIDDEN_OUTPUT_KEY: " + path + "/" + str(key))
            assert_no_forbidden_keys(item, path + "/" + str(key))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            assert_no_forbidden_keys(item, path + "[" + str(i) + "]")
    return True


def _finite(value):
    return isinstance(value, (int, float, np.floating, np.integer)) and bool(np.isfinite(value))


def sign(value):
    if value is None or not np.isfinite(value) or value == 0:
        return 0
    return 1 if value > 0 else -1


def factor_view(ranked, col, outcome_values, spec):
    """Equal-date statistics of one factor against one outcome vector (NaN where the observation is outside the slice).
    `d10MinusD1` is the equal-date mean of (D10 mean - D1 mean); `medianD10MinusD1` is the equal-date mean of
    (D10 median - D1 median); `meanRankCorrelation` is the equal-date mean Spearman. They are never derived from one another."""
    cfg = spec["statistics"]
    frame = ranked[["date", col + "__pct", col + "__n"]].copy()
    frame["y"] = np.asarray(outcome_values, float)
    rows = A.per_date_factor_stats(frame, col, "y", cfg)
    for r in rows:
        m = r["medians"]
        r["medianSpread"] = m[9] - m[0] if np.isfinite(m[0]) and np.isfinite(m[9]) else math.nan
    spreads = [r["spread"] for r in rows]
    rhos = [r["rho"] for r in rows]
    median_spreads = [r["medianSpread"] for r in rows]
    annual, stability = A.year_table(rows, "spread", cfg)
    dates = int(np.isfinite(spreads).sum())
    minimum = spec["labelRules"]["sliceMinimumDates"]
    view = {"datesWithDeciles": dates, "datesWithRankCorrelation": int(np.isfinite(rhos).sum()),
            "outcomeObservations": int(sum(sum(r["counts"]) for r in rows)),
            "d10MinusD1": A._nanmean(spreads), "medianD10MinusD1": A._nanmean(median_spreads),
            "meanRankCorrelation": A._nanmean(rhos),
            "annualD10MinusD1": annual, "spreadYearStability": stability,
            "leaveBestYearOut": A.leave_best_year_out(rows, "spread")}
    ok = dates >= minimum and all(np.isfinite(view[k]) for k in ("d10MinusD1", "medianD10MinusD1", "meanRankCorrelation"))
    view["status"] = "MEASURABLE" if ok else "DATA_INSUFFICIENT"
    return view


def shows_direction(view, direction):
    """A slice view 'shows' a direction when it is measurable and BOTH its mean spread and mean rank correlation carry that sign."""
    return (view is not None and view["status"] == "MEASURABLE" and sign(view["d10MinusD1"]) == direction
            and sign(view["meanRankCorrelation"]) == direction)


def descriptive_label(views, cfg):
    """Deterministic, first-match-wins, sign-based. Constants come from the frozen spec (`labelRules`); the only proportion,
    `weakeningFraction`, is the anatomy's own existing 0.5 floor, not a fitted value."""
    full = views["FULL_SAMPLE"]["FULL_TOP120"]
    if (full["datesWithDeciles"] < cfg["minimumDatesFull"] or full["status"] != "MEASURABLE"
            or not all(_finite(full[k]) for k in ("d10MinusD1", "medianD10MinusD1", "meanRankCorrelation"))):
        return "DATA_INSUFFICIENT"
    direction = sign(full["d10MinusD1"])
    if direction == 0:
        return "NO_CLEAR_PATTERN"
    if sign(full["medianD10MinusD1"]) != direction and sign(full["meanRankCorrelation"]) != direction:
        return "OUTLIER_SENSITIVE"
    for name in ("EXCLUDE_BOTH", "EXCLUDE_DYNAMIC_TOP2_MARKET_CAP"):
        v = views["UNIVERSES"][name]
        if v["status"] == "MEASURABLE" and (sign(v["d10MinusD1"]) != direction
                                            or abs(v["d10MinusD1"]) < cfg["weakeningFraction"] * abs(full["d10MinusD1"])):
            return "MEGA_CAP_SENSITIVE"
    pre = [views["SLICES"][k] for k in ("PRE_2025_COMPLETE_WINDOW", "EXCLUDE_WINDOWS_TOUCHING_2025_OR_2026")
           if views["SLICES"][k]["status"] == "MEASURABLE"]
    recent = views["SLICES"]["TOUCHES_2025_OR_LATER"]
    if pre and recent["status"] == "MEASURABLE":
        pre_all = all(shows_direction(v, direction) for v in pre)
        pre_none = not any(shows_direction(v, direction) for v in pre)
        recent_shows = shows_direction(recent, direction)
        if recent_shows and pre_none:
            return "RECENT_REGIME_CONCENTRATED"
        if pre_all and not recent_shows:
            return "PRE_RECENT_ONLY"
        chronology_persistent = pre_all and recent_shows
    else:
        return "DATA_INSUFFICIENT"                                         # persistence cannot be assessed
    regimes = views["REGIMES"]
    for a, b in (("TREND_OK", "TREND_BAD"), ("VOL_OK", "VOL_HIGH")):
        if (regimes[a]["status"] == "MEASURABLE" and regimes[b]["status"] == "MEASURABLE"
                and sign(regimes[a]["d10MinusD1"]) * sign(regimes[b]["d10MinusD1"]) == -1):
            return "REGIME_DEPENDENT"
    if (chronology_persistent and sign(full["medianD10MinusD1"]) == direction and sign(full["meanRankCorrelation"]) == direction):
        return "PERSISTENT_ACROSS_PRE_RECENT_AND_RECENT"
    return "NO_CLEAR_PATTERN"


# --------------------------------------------------------------------------- #
# Fundamentals improved: three DISTINCT success definitions
# --------------------------------------------------------------------------- #
def improvement_outcomes(frame, flag_col, h, slice_mask_values, cfg):
    """Rates among rows with `flag_col` > 0 (and, for context, <= 0), over rows inside the slice. ABSOLUTE_UP,
    BEATS_KODEX200 and BEATS_TOP120_EQUAL_WEIGHT are separate columns, each over its OWN valid population: a row without
    a leave-one-out value is absent from that rate's denominator, never counted as a failure. Date-equal weighting, dates
    with fewer than `interactionCellMinimumNames` flagged names excluded from the rate."""
    s = str(h)
    flag = A.clean_numeric(frame[flag_col])
    inside = np.asarray(slice_mask_values, bool)
    minimum = cfg["statistics"]["interactionCellMinimumNames"]
    result = {}
    for group, mask in (("IMPROVED", np.isfinite(flag) & (flag > 0) & inside), ("NOT_IMPROVED", np.isfinite(flag) & (flag <= 0) & inside)):
        sub = frame.loc[mask, ["date", "abs" + s, "kodex" + s, "loo" + s]]
        rates = {k: [] for k in SUCCESS_DEFINITIONS}
        counts = {k: 0 for k in SUCCESS_DEFINITIONS}
        for _, g in sub.groupby("date"):
            for key, col, test in (("ABSOLUTE_UP", "abs" + s, lambda v: v > 0), ("BEATS_KODEX200", "kodex" + s, lambda v: v > 0),
                                   ("BEATS_TOP120_EQUAL_WEIGHT", "loo" + s, lambda v: v > 0)):
                v = A.clean_numeric(g[col])
                v = v[np.isfinite(v)]
                counts[key] += int(len(v))
                if len(v) >= minimum:
                    rates[key].append(float(test(v).mean()))
        result[group] = {key: {"rate": A._nanmean(rates[key]) if rates[key] else None, "dates": len(rates[key]),
                               "observations": counts[key]} for key in SUCCESS_DEFINITIONS}
    return result


# --------------------------------------------------------------------------- #
# Assembly over the frozen grid
# --------------------------------------------------------------------------- #
def _flat(view):
    """One CSV-able row from a factor view (counts, three separate spreads, status)."""
    return {"status": view["status"], "dates": view["datesWithDeciles"], "rankDates": view["datesWithRankCorrelation"],
            "observations": view["outcomeObservations"], "meanD10MinusD1": view["d10MinusD1"],
            "medianD10MinusD1": view["medianD10MinusD1"], "meanRankCorrelation": view["meanRankCorrelation"],
            "leaveBestYearOutMean": (view["leaveBestYearOut"] or {}).get("meanWithoutYear"),
            "leaveBestYearOutSignRetained": (view["leaveBestYearOut"] or {}).get("signRetained")}


def analyze_all(panel, spec):
    """Everything the future execution publishes. `panel` is the anatomy-shaped panel (signal-time features, endpoints,
    treated status) already carrying `abs/kodex/loo` outcome columns from `add_outcomes`."""
    if tuple(f["name"] for f in spec["factors"]) != FACTORS:
        raise ValueError("FACTOR_LIST_DIFFERS_FROM_ANATOMY")
    cutoff = spec["developmentCutoff"]
    ranked_full = A.add_signal_time_ranks(panel, list(FACTORS))
    universes = {"FULL_TOP120": ranked_full}
    removed_names = {}
    for name in UNIVERSES[1:]:
        universes[name], removed = ranked_universe(panel, name)
        removed_names[name] = sorted(set(removed.ticker)) if name != "EXCLUDE_DYNAMIC_TOP2_MARKET_CAP" else None
    masks = state_masks(ranked_full)
    family = {n: fam for fam, names in F.FAMILIES.items() for n in names}
    factors, executive, mega, regime_rows = [], [], [], []
    for col in FACTORS:
        entry = {"factor": col, "family": family[col], "horizons": {}}
        for h in HORIZONS:
            s = str(h)
            slice_views = {}
            for name in SLICES:
                inside = slice_mask(name, ranked_full["entry" + s], ranked_full["exit" + s], cutoff).to_numpy()
                slice_views[name] = factor_view(ranked_full, col, np.where(inside, ranked_full["abs" + s], np.nan), spec)
            universe_views = {"FULL_TOP120": slice_views["FULL_SAMPLE"]}
            for name in UNIVERSES[1:]:
                frame = universes[name]
                universe_views[name] = factor_view(frame, col, frame["abs" + s].to_numpy(float), spec)
            absolute = ranked_full["abs" + s].to_numpy(float)
            regime_views = {state: factor_view(ranked_full, col, np.where(masks[state].to_numpy(), absolute, np.nan), spec)
                            for state in REGIME_STATES}
            label = descriptive_label({"FULL_SAMPLE": {"FULL_TOP120": slice_views["FULL_SAMPLE"]}, "SLICES": slice_views,
                                       "UNIVERSES": universe_views, "REGIMES": regime_views}, spec["labelRules"])
            entry["horizons"][s] = {"descriptiveLabel": label, "slices": slice_views, "universes": universe_views,
                                    "regimes": regime_views, "signalYearChronology": slice_views["FULL_SAMPLE"]["annualD10MinusD1"]}
            executive += [{"factor": col, "horizon": h, "slice": n, "descriptiveLabel": label, **_flat(slice_views[n])} for n in SLICES]
            mega += [{"factor": col, "horizon": h, "universe": n, **_flat(universe_views[n])} for n in UNIVERSES]
            regime_rows += [{"factor": col, "horizon": h, "state": n, **_flat(regime_views[n])} for n in REGIME_STATES]
        factors.append(entry)
    improved = []
    for flag, source in IMPROVEMENT_FLAGS.items():
        for h in HORIZONS:
            s = str(h)
            for name in ("FULL_SAMPLE", "PRE_2025_COMPLETE_WINDOW", "TOUCHES_2025_OR_LATER", "EXCLUDE_WINDOWS_TOUCHING_2025_OR_2026"):
                inside = slice_mask(name, ranked_full["entry" + s], ranked_full["exit" + s], cutoff).to_numpy()
                for group, rates in improvement_outcomes(ranked_full, source, h, inside, spec).items():
                    for definition, r in rates.items():
                        improved.append({"flag": flag, "horizon": h, "slice": name, "group": group, "successDefinition": definition, **r})
    context = concentration_context(panel)
    result = {"studyId": STUDY, "scientificStatus": SCIENTIFIC_STATUS, "returnBasis": RETURN_BASIS,
              "universe": PRIMARY_UNIVERSE, "limitation": spec["limitation"],
              "factors": factors, "megaCapSensitivity": mega, "marketRegimes": regime_rows,
              "fundamentalsImproved": improved, "concentrationContext": context,
              "sensitivityExclusions": {"fixedIdentities": {k: list(v) for k, v in FIXED_EXCLUSIONS.items()},
                                        "dynamic": f"top {DYNAMIC_TOP_COUNT} by signal-date marketCap, per date"},
              "regimeStateCoverage": {k: int(v.sum()) for k, v in masks.items()},
              "outcomes": list(OUTCOMES), "slices": list(SLICES), "regimeStates": list(REGIME_STATES)}
    assert_no_forbidden_keys(result)
    return {"result": result, "tables": {"executive-map": executive, "mega-cap-sensitivity": mega, "market-regimes": regime_rows,
                                          "fundamentals-improved": improved, "concentration-context": context}}


def render_report(result, spec):
    """Plain, non-promotional Markdown. Factors are always listed in frozen order, never sorted by result."""
    lines = ["# KR Top120 regime review v1 — EXPLORATORY POST-OUTCOME REGIME DIAGNOSTIC", "",
             "**" + spec["limitation"] + "**", "",
             f"Return basis: `{RETURN_BASIS}` (an adjusted index with vendor-served distributions; not total shareholder return). "
             "Same-date D10-D1 is a cross-sectional stock-return spread (the benchmark cancels); benchmark-relative levels, "
             "beat-benchmark fractions and the fundamentals success rates remain benchmark dependent.", "",
             f"Universe: `{PRIMARY_UNIVERSE}` — PIT top-120 KRX market-cap large caps only.", "", "## A. Regime executive map", "",
             "| factor | horizon | label | slice | dates | mean D10-D1 | median D10-D1 | mean Spearman |", "|---|---|---|---|---|---|---|---|"]

    def fmt(v):
        return "n/a" if v is None else f"{v:+.4f}"
    for f in result["factors"]:
        for h, block in f["horizons"].items():
            for name, v in block["slices"].items():
                lines.append(f"| {f['factor']} | H{h} | {block['descriptiveLabel']} | {name} | {v['datesWithDeciles']} | "
                             f"{fmt(v['d10MinusD1'])} | {fmt(v['medianD10MinusD1'])} | {fmt(v['meanRankCorrelation'])} |")
    lines += ["", "## B. Mega-cap sensitivity", "", "| factor | horizon | universe | mean D10-D1 | median D10-D1 | mean Spearman |", "|---|---|---|---|---|---|"]
    for r in result["megaCapSensitivity"]:
        lines.append(f"| {r['factor']} | H{r['horizon']} | {r['universe']} | {fmt(r['meanD10MinusD1'])} | {fmt(r['medianD10MinusD1'])} | {fmt(r['meanRankCorrelation'])} |")
    lines += ["", "## C. Signal-time market regimes", "", "| factor | horizon | state | dates | mean D10-D1 | median D10-D1 | mean Spearman |", "|---|---|---|---|---|---|---|"]
    for r in result["marketRegimes"]:
        lines.append(f"| {r['factor']} | H{r['horizon']} | {r['state']} | {r['dates']} | {fmt(r['meanD10MinusD1'])} | {fmt(r['medianD10MinusD1'])} | {fmt(r['meanRankCorrelation'])} |")
    lines += ["", "## D. Fundamentals improved: three distinct success definitions", "",
              "| flag | horizon | slice | group | definition | rate | dates | observations |", "|---|---|---|---|---|---|---|---|"]
    for r in result["fundamentalsImproved"]:
        rate = "n/a" if r["rate"] is None else f"{r['rate']:.4f}"
        lines.append(f"| {r['flag']} | H{r['horizon']} | {r['slice']} | {r['group']} | {r['successDefinition']} | {rate} | {r['dates']} | {r['observations']} |")
    lines += ["", "## E. Concentration context", "", "Per-date shares are in `tables/concentration-context.csv.gz`; context only, no causal claim.", "",
              "This study confirms nothing, ranks no factor, and promotes nothing."]
    return "\n".join(lines) + "\n"
