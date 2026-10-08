"""kr-alpha-atlas Phase B — what the matrix actually contains, and which registered comparisons it can support. Outcome-blind: every statistic here is a count of
measured cells, never a relationship to a return.

THE QUESTION ANSWERED. Not "does the feature predict?" but "is there enough point-in-time data, on enough dates, for enough names, in enough years, for the
registered Level 1-3 comparisons to be ATTEMPTED?" A READY here is a statement about data, never about alpha. The registry's `readinessStatus` is the design-time
classification; this report's `measuredStatus` is what the matrix measured, and the registry file is not edited by it.

THRESHOLDS (declared before any measurement, each with its source):
  * a feature is measured on >= 60% of its rows over its own usable range   (config.json kellyPortfolio.probabilityCalibration.integrity.minPitCoverage;
    `kr_alpha_signal_v2.MIN_MEASURED_SHARE`; the registry's own B04 / C06 / C15 wording)
  * a date is evaluable for a Level 1 statistic with >= 30 measured names     (docs/kr-alpha-atlas-methodology.md section 4)
  * a year counts in the stability reading with >= 13 dates                   (same section)
  * a Level 3 2x2 contrast needs >= 3 names in every cell on a date           (a structural minimum: a cell mean over fewer than three names is not a mean;
                                                                               introduced here, stated here)
  * a comparison needs >= 52 evaluable weekly dates (about a year)            (introduced here: one year is the shortest span over which a calendar-year sign
                                                                               can be read twice; stated here)
These are readiness gates, not statistical tests. They are reported with the numbers beside them so a reader can apply a different one.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import kr_alpha_atlas_catalogue as C
from . import replay_calendar as RC

CONTRACT = "KR_ALPHA_ATLAS_READINESS_V1"
ROOT = Path(__file__).resolve().parents[1]
MIN_FEATURE_COVERAGE = 0.60
MIN_MEASURED_NAMES_PER_DATE = 30
MIN_DATES_PER_YEAR = 13
MIN_CELL_NAMES = 3
MIN_EVALUABLE_DATES = 52
RULES = {"minFeatureCoverage": MIN_FEATURE_COVERAGE, "minMeasuredNamesPerDate": MIN_MEASURED_NAMES_PER_DATE, "minDatesPerYear": MIN_DATES_PER_YEAR,
         "minCellNames": MIN_CELL_NAMES, "minEvaluableDates": MIN_EVALUABLE_DATES}
THIN_MARGIN_PCT = 5.0       # a READY that clears the coverage floor by less than this is reported THIN beside the number (a first pass that barely clears is not a comfortable one)
THIN_EVALUABLE_DATES = 2 * 52
MEASURED_STATUSES = ("MEASURED_READY", "MEASURED_BELOW_COVERAGE_FLOOR", "ALREADY_TESTED_COMPUTED_READY", "ALREADY_TESTED_COMPUTED_BELOW_COVERAGE_FLOOR",
                     "REFERENCED_ALREADY_TESTED", "NOT_COMPUTED_DATA_BUILD_REQUIRED", "NOT_COMPUTED_SOURCE_BLOCKED", "NOT_COMPUTED_PIT_UNSAFE",
                     "NOT_COMPUTED_NOT_FEASIBLE", "NOT_A_MATRIX_COLUMN", "NOT_COMPUTED_OTHER")
INTERACTION_STATUSES = ("READY", "INSUFFICIENT_COVERAGE", "SOURCE_BLOCKED", "PIT_UNSAFE")
PRIMARY_REGISTRY_ROLES = ("ALPHA_CANDIDATE",)


def _round(x, n=6):
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else round(float(x), n)


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# --------------------------------------------------------------------------- #
# Calendar facts (no price, no outcome)
# --------------------------------------------------------------------------- #
def last_maturable_signal_date(signal_dates, horizon, cutoff):
    """The latest signal date whose label window (entry the next session, exit `horizon` sessions after entry) closes on or before `cutoff`. A calendar
    fact: it reads no price. Dates after it exist in the matrix and cannot be scored by a development evaluation that stops at the cutoff."""
    days = RC.sessions("2013-01-01", cutoff, "KR")
    last = len(days) - 1
    best = None
    for d in signal_dates:
        pos = days.searchsorted(pd.Timestamp(d), side="right") - 1
        if pos + 1 + horizon <= last:
            best = d
    return best


# --------------------------------------------------------------------------- #
# One feature
# --------------------------------------------------------------------------- #
DENOMINATOR_NOTES = {
    "B08_valueBusinessConfirmation": "member-dates the H2 contract (kr_alpha_signal_v2) does not itself exclude: a preferred share, no price that day, not traded on each of 20 sessions, "
                                     "below the 1 billion KRW median-traded-value floor, no industry label or an industry with fewer than 5 eligible names. Those are definitional "
                                     "exclusions of the sealed design, not data gaps; the all-member-rows figure is published beside it"}


def denominator_mask(rows, feature):
    """Which rows count in a feature's denominator. Every feature uses every PIT member-date, except a feature whose own sealed contract excludes names by definition."""
    if feature == "B08_valueBusinessConfirmation":
        return rows.b08State != "INELIGIBLE"
    return pd.Series(True, index=rows.index)


def feature_coverage(matrix, feature, horizons, cutoff):
    mask = denominator_mask(matrix.rows, feature)
    rows = matrix.rows[mask]
    measured_all = matrix.values[feature].notna()
    measured = measured_all[mask]
    dates = rows.date
    per_date = measured.groupby(dates).sum().astype(int)
    usable_dates = sorted(per_date[per_date >= MIN_MEASURED_NAMES_PER_DATE].index)
    out = {"eligibleObservations": int(len(rows)), "measuredObservations": int(measured.sum()), "coveragePct": _round(100.0 * measured.mean()),
           "denominator": ("every PIT Top120 member-date in the matrix (%d dates, %d member-dates)" % (rows.date.nunique(), len(rows))) if mask.all()
                          else "%d of %d member-dates: %s" % (len(rows), len(matrix.rows), DENOMINATOR_NOTES[feature])}
    if not mask.all():
        out["coverageAllMemberRowsPct"] = _round(100.0 * measured_all.mean())
    by_year = {}
    years = dates.str[:4]
    for year, idx in rows.groupby(years).groups.items():
        m = measured.loc[idx]
        d_in_year = per_date[[d for d in per_date.index if d[:4] == year]]
        by_year[year] = {"measured": int(m.sum()), "total": int(len(m)), "coveragePct": _round(100.0 * m.mean()), "dates": int(len(d_in_year)),
                         "datesWithEnoughNames": int((d_in_year >= MIN_MEASURED_NAMES_PER_DATE).sum())}
    out["coverageByYear"] = by_year
    out["coverageByIndustry"] = _grouped(measured, rows.industry.fillna("UNCLASSIFIED"))
    out["coverageByLiquidityTier"] = _grouped(measured, rows.liquidityTier)
    if usable_dates:
        first, last = usable_dates[0], usable_dates[-1]
        within = (dates >= first) & (dates <= last)
        out.update(earliestUsableSignalDate=first, latestUsableSignalDate=last, usableSignalDates=len(usable_dates),
                   coverageWithinUsableRangePct=_round(100.0 * measured[within].mean()),
                   **({} if mask.all() else {"coverageAllMemberRowsWithinUsableRangePct": _round(100.0 * measured_all[(matrix.rows.date >= first) & (matrix.rows.date <= last)].mean())}),
                   usableYears=sorted({d[:4] for d in usable_dates if by_year[d[:4]]["datesWithEnoughNames"] >= MIN_DATES_PER_YEAR}))
    else:
        out.update(earliestUsableSignalDate=None, latestUsableSignalDate=None, usableSignalDates=0, coverageWithinUsableRangePct=None, usableYears=[])
    reasons = matrix.reasons[feature][mask][~measured]
    out["missingness"] = {k: int(v) for k, v in sorted(reasons.value_counts().items())}
    within = out.get("coverageWithinUsableRangePct")
    out["marginOverCoverageFloorPct"] = None if within is None else _round(within - 100.0 * MIN_FEATURE_COVERAGE)
    out["thinOverFloor"] = within is not None and 0 <= within - 100.0 * MIN_FEATURE_COVERAGE < THIN_MARGIN_PCT
    out["horizonUsability"] = {}
    for h in horizons:
        if h is None:
            continue
        last_ok = last_maturable_signal_date(sorted(rows.date.unique()), h, cutoff)
        n = sum(1 for d in usable_dates if last_ok is not None and d <= last_ok)
        out["horizonUsability"]["H%d" % h] = {"lastMaturableSignalDate": last_ok, "usableSignalDatesBeforeThat": n, "usable": n >= MIN_EVALUABLE_DATES}
    return out


def _grouped(measured, key):
    out = {}
    for name, idx in measured.groupby(key).groups.items():
        m = measured.loc[idx]
        out[str(name)] = {"measured": int(m.sum()), "total": int(len(m)), "coveragePct": _round(100.0 * m.mean())}
    return dict(sorted(out.items()))


def measured_status(registry_feature, implemented, cov):
    fid = registry_feature["featureId"]
    if fid in C.NOT_A_MATRIX_COLUMN:
        return "NOT_A_MATRIX_COLUMN"
    if implemented:
        ready = (cov["usableSignalDates"] >= MIN_EVALUABLE_DATES and (cov["coverageWithinUsableRangePct"] or 0) >= 100.0 * MIN_FEATURE_COVERAGE)
        if registry_feature["readinessStatus"] == "ALREADY_TESTED":
            return "ALREADY_TESTED_COMPUTED_READY" if ready else "ALREADY_TESTED_COMPUTED_BELOW_COVERAGE_FLOOR"
        return "MEASURED_READY" if ready else "MEASURED_BELOW_COVERAGE_FLOOR"
    status = registry_feature["readinessStatus"]
    return {"ALREADY_TESTED": "REFERENCED_ALREADY_TESTED", "DATA_BUILD_REQUIRED": "NOT_COMPUTED_DATA_BUILD_REQUIRED", "SOURCE_BLOCKED": "NOT_COMPUTED_SOURCE_BLOCKED",
            "PIT_UNSAFE": "NOT_COMPUTED_PIT_UNSAFE", "NOT_FEASIBLE": "NOT_COMPUTED_NOT_FEASIBLE"}.get(status, "NOT_COMPUTED_OTHER")


def pit_checks(matrix):
    """Leakage checks that need no model: every filing-based figure became visible STRICTLY before its signal date, and every membership snapshot is older."""
    rows, avail = matrix.rows, matrix.available
    violations = 0
    checked = 0
    for col in avail.columns:
        stamp = avail[col].dropna()
        if len(stamp):
            checked += len(stamp)
            violations += int((stamp.astype(str) >= rows.loc[stamp.index, "date"].astype(str)).sum())
    snapshot_violations = int((rows.pitSnapshotDate.astype(str) >= rows.date.astype(str)).sum())
    return {"filingBasedCellsChecked": int(checked), "availableFromNotBeforeSignalDate": int(violations),
            "membershipSnapshotNotOlderThanSignalDate": snapshot_violations, "pass": violations == 0 and snapshot_violations == 0}


def reason_checks(matrix):
    """Every missing cell must say why, and only in the closed vocabulary. A NaN without a reason is a hole in the audit trail, not a missing value."""
    from . import kr_alpha_atlas_matrix as M
    missing = matrix.values.isna()
    unexplained = int((missing & matrix.reasons.isin(["", "REASON_NOT_RECORDED"])).sum().sum())
    unknown = sorted(set(matrix.reasons.stack().unique()) - {""} - set(M.REASONS))
    stray = int((~missing & matrix.reasons.ne("")).sum().sum())
    return {"missingCells": int(missing.sum().sum()), "missingWithoutReason": unexplained, "reasonsOutsideVocabulary": unknown, "measuredCellsCarryingAReason": stray,
            "pass": unexplained == 0 and not unknown and stray == 0}


# --------------------------------------------------------------------------- #
# Joint coverage and interactions
# --------------------------------------------------------------------------- #
def overlap_matrix(matrix, features):
    m = matrix.values[features].notna().to_numpy(float)
    joint = (m.T @ m) / max(1, len(m))
    return {"features": list(features), "jointCoverage": [[_round(x, 4) for x in row] for row in joint]}


def _terciles(x):
    r = x.rank(pct=True, method="average")
    return pd.Series(np.where(r <= 1 / 3, "LOW", np.where(r >= 2 / 3, "HIGH", "MID")), index=x.index)


def _cells(frame, a, b):
    """Per date: names measured on both, and the four corner cells of the 2x2 contrast. Corners need >= MIN_CELL_NAMES names each."""
    out = {}
    for date, g in frame.groupby("date", sort=True):
        g = g.dropna(subset=[a, b])
        n = len(g)
        if n < MIN_MEASURED_NAMES_PER_DATE:
            out[date] = (n, 0, False)
            continue
        ta = _terciles(g[a]) if g[a].nunique() > 2 else g[a].map({0.0: "LOW", 1.0: "HIGH"})
        tb = _terciles(g[b]) if g[b].nunique() > 2 else g[b].map({0.0: "LOW", 1.0: "HIGH"})
        counts = [int(((ta == x) & (tb == y)).sum()) for x in ("LOW", "HIGH") for y in ("LOW", "HIGH")]
        out[date] = (n, min(counts), min(counts) >= MIN_CELL_NAMES)
    return out


def interaction_readiness(matrix, registry, features_report):
    """Classify the six registered Level 3 interactions. Never evaluates a return."""
    reg = {f["featureId"]: f for f in registry["features"]}
    rows = matrix.rows
    v = matrix.values
    results = {}
    for ix in registry["levelThreeInteractions"]:
        ids = ix["features"]
        entry = {"interactionId": ix["interactionId"], "features": ids, "horizon": ix["horizon"], "negativeControl": ix["negativeControl"]}
        blocked = [f for f in ids if reg[f]["readinessStatus"] == "SOURCE_BLOCKED"]
        unsafe = [f for f in ids if reg[f]["readinessStatus"] == "PIT_UNSAFE"]
        if blocked:
            entry.update(status="SOURCE_BLOCKED", reason="component(s) %s SOURCE_BLOCKED; the OHLCV accumulation proxy D11 is never a substitute" % ",".join(blocked))
        elif unsafe:
            entry.update(status="PIT_UNSAFE", reason="component(s) %s PIT_UNSAFE" % ",".join(unsafe))
        else:
            frame = pd.DataFrame({"date": rows.date})
            if ix["interactionId"].startswith("X1"):
                frame["a"] = v["B05_industryRelativeValue"]
                frame["b"] = rows.b08Confirmed
            elif ix["interactionId"].startswith("X6"):
                frame["a"] = v["I01_kospiTrendVolState"].map(lambda x: np.nan if not np.isfinite(x) else (1.0 if x < 1.0 else 0.0))
                frame["b"] = v["A05_relative126"]
            else:
                frame["a"], frame["b"] = v[ids[0]], v[ids[1]]
            joint = frame[["a", "b"]].notna().all(axis=1)
            denominator = (rows.b08State != "INELIGIBLE") if ix["interactionId"].startswith("X1") else pd.Series(True, index=rows.index)
            joint = joint & denominator
            entry["denominatorRows"] = int(denominator.sum())
            entry["jointMeasuredObservations"] = int(joint.sum())
            entry["jointCoveragePct"] = _round(100.0 * joint.sum() / denominator.sum())
            if ix["interactionId"].startswith("X6"):
                evaluable, per_state = _regime_dates(frame, rows)
                entry["evaluableDatesByRegimeState"] = per_state
                dates_ok = min(per_state.values()) if per_state else 0
            else:
                cells = _cells(frame.assign(date=rows.date), "a", "b")
                evaluable = sorted(d for d, (n, m, ok) in cells.items() if ok)
                dates_ok = len(evaluable)
                entry["jointMeasuredNamesPerDate"] = _dist([n for n, _, _ in cells.values()])
                entry["smallestCornerCellPerDate"] = _dist([m for _, m, _ in cells.values()])
            entry["evaluableDates"] = int(dates_ok)
            if evaluable:
                first, last = evaluable[0], evaluable[-1]
                entry["evaluableRange"] = [first, last]
                within = (rows.date >= first) & (rows.date <= last)
                entry["jointCoverageWithinEvaluableRangePct"] = _round(100.0 * joint[within].sum() / max(1, int((denominator & within).sum())))
                entry["evaluableYears"] = sorted({d[:4] for d in evaluable})
                ok = dates_ok >= MIN_EVALUABLE_DATES and (entry["jointCoverageWithinEvaluableRangePct"] or 0) >= 100.0 * MIN_FEATURE_COVERAGE
            else:
                ok = False
            entry["status"] = "READY" if ok else "INSUFFICIENT_COVERAGE"
            margin = (entry.get("jointCoverageWithinEvaluableRangePct") or 0.0) - 100.0 * MIN_FEATURE_COVERAGE
            entry["marginOverCoverageFloorPct"] = _round(margin)
            entry["thin"] = bool(ok and (margin < THIN_MARGIN_PCT or dates_ok < THIN_EVALUABLE_DATES))
            entry["reason"] = ("%d evaluable weekly dates (need %d); joint coverage within the evaluable range %s%% (need %.0f%%)"
                               % (dates_ok, MIN_EVALUABLE_DATES, entry.get("jointCoverageWithinEvaluableRangePct"), 100 * MIN_FEATURE_COVERAGE))
        results[ix["interactionId"]] = entry
    return results


def _dist(values):
    a = np.asarray(values, float)
    return {"min": _round(a.min()), "p10": _round(np.percentile(a, 10)), "median": _round(np.median(a)), "p90": _round(np.percentile(a, 90)), "max": _round(a.max())}


def _regime_dates(frame, rows):
    out = {}
    for state, label in ((1.0, "ADVERSE_MULTIPLIER_BELOW_1"), (0.0, "NORMAL_MULTIPLIER_1")):
        g = frame[frame.a == state].assign(date=rows.date)
        n = g.dropna(subset=["b"]).groupby("date").size()
        out[label] = sorted(n[n >= MIN_MEASURED_NAMES_PER_DATE].index)
    evaluable = sorted(set(out["ADVERSE_MULTIPLIER_BELOW_1"]) | set(out["NORMAL_MULTIPLIER_1"]))
    return evaluable, {k: len(v) for k, v in out.items()}


def baseline_readiness(registry, features_report, matrix=None):
    """A baseline is READY when every member is individually usable. The Level 2 reference model carries missingness indicators, so complete-case coverage is not a gate;
    it is reported (over the members' common usable range) so a reader sees how much of the sample a naive complete-case fit would keep."""
    out = {}
    for name, members in registry["levelTwoBaselines"].items():
        statuses = {m: features_report[m]["measuredStatus"] for m in members}
        usable = [m for m, s in statuses.items() if s in ("ALREADY_TESTED_COMPUTED_READY", "MEASURED_READY")]
        entry = {"members": members, "memberStatuses": statuses, "status": "READY" if len(usable) == len(members) else "INSUFFICIENT_COVERAGE",
                 "membersBelowFloor": sorted(set(members) - set(usable))}
        if matrix is not None and len(usable) == len(members):
            firsts = [features_report[m]["earliestUsableSignalDate"] for m in members]
            lasts = [features_report[m]["latestUsableSignalDate"] for m in members]
            lo, hi = max(firsts), min(lasts)
            window = (matrix.rows.date >= lo) & (matrix.rows.date <= hi)
            complete = matrix.values.loc[window, members].notna().all(axis=1)
            entry.update(commonUsableRange=[lo, hi], completeCaseCoverageWithinCommonRangePct=_round(100.0 * complete.mean()) if window.any() else None)
        out[name] = entry
    return out


# --------------------------------------------------------------------------- #
# Whole report
# --------------------------------------------------------------------------- #
def build_features_report(matrix, registry, cutoff):
    reg = {f["featureId"]: f for f in registry["features"]}
    families = registry["families"]
    out = {}
    for fid, f in reg.items():
        fam = families[f["family"]]
        horizons = [fam["primaryHorizon"], fam.get("secondaryHorizon")]
        implemented = fid in C.CATALOGUE
        cat = C.CATALOGUE.get(fid)
        entry = {"featureId": fid, "family": f["family"], "role": f["role"], "registryReadinessStatus": f["readinessStatus"],
                 "registryPriorEvidence": f["existingResearchStatus"], "registryPitStatus": f["pitStatus"], "registeredHorizons": horizons,
                 "source": f["source"], "sourceClass": f.get("sourceClass"), "registryLimitations": f["limitations"], "blockingReason": f.get("blockingReason"),
                 "implementation": ("COMPUTED_ALREADY_TESTED" if implemented and f["readinessStatus"] == "ALREADY_TESTED"
                                    else "IMPLEMENTED" if implemented else "NOT_A_MATRIX_COLUMN" if fid in C.NOT_A_MATRIX_COLUMN
                                    else "REFERENCED_NOT_RECOMPUTED" if f["readinessStatus"] == "ALREADY_TESTED" else "NOT_COMPUTED")}
        if implemented:
            entry.update(catalogue=cat, **feature_coverage(matrix, fid, horizons, cutoff))
            entry["pitSafetyVerdict"] = "PIT_SAFE" if f["pitStatus"] in registry["pitStatuses"]["safe"] else "PIT_UNSAFE_PER_REGISTRY"
        else:
            cov = {"usableSignalDates": 0, "coverageWithinUsableRangePct": None}
            entry["pitSafetyVerdict"] = ("NOT_APPLICABLE" if fid in C.NOT_A_MATRIX_COLUMN else "PIT_SAFE_PER_REGISTRY_NOT_COMPUTED_HERE"
                                         if f["pitStatus"] in registry["pitStatuses"]["safe"] else "PIT_UNSAFE_PER_REGISTRY")
            entry["notComputedReason"] = C.NOT_A_MATRIX_COLUMN.get(fid) or f.get("blockingReason") or (
                "ALREADY_TESTED: sealed reading referenced, not re-measured" if f["readinessStatus"] == "ALREADY_TESTED" else f.get("nextAction"))
        entry["measuredStatus"] = measured_status(f, implemented, entry if implemented else cov)
        entry["nextAction"] = _next_action(entry, f)
        out[fid] = entry
    return out


def _next_action(entry, f):
    s = entry["measuredStatus"]
    if s in ("MEASURED_READY", "ALREADY_TESTED_COMPUTED_READY"):
        return "eligible for the Phase C registration at its measured usable range"
    if s in ("MEASURED_BELOW_COVERAGE_FLOOR", "ALREADY_TESTED_COMPUTED_BELOW_COVERAGE_FLOOR"):
        return "excluded from Phase C unless the missingness reasons below are repaired by a data-foundation change (not part of the evaluation)"
    if s == "REFERENCED_ALREADY_TESTED":
        return "sealed prior reading stands; not re-run"
    if s == "NOT_COMPUTED_SOURCE_BLOCKED":
        return "stays SOURCE_BLOCKED; at most one re-probe through the Probes workflow, never a substitute"
    return f.get("nextAction") or "none"


def family_summary(features_report, registry):
    out = {}
    for fam in sorted(registry["families"]):
        feats = [r for r in features_report.values() if r["family"] == fam]
        eligible = [r["featureId"] for r in feats if r["measuredStatus"] == "MEASURED_READY" and r["role"] in PRIMARY_REGISTRY_ROLES
                    and r["registryReadinessStatus"] != "ALREADY_TESTED"]
        out[fam] = {"name": registry["families"][fam]["name"], "registered": len(feats),
                    "byMeasuredStatus": {k: sum(1 for r in feats if r["measuredStatus"] == k) for k in MEASURED_STATUSES if any(r["measuredStatus"] == k for r in feats)},
                    "eligibleAlphaCandidates": eligible, "hasUsableReadyFeature": bool(eligible)}
    return out


def recommendation(families):
    usable = [f for f, s in families.items() if s["hasUsableReadyFeature"]]
    if len(usable) < 2:
        return {"verdict": "REGISTERED_BLOCKED_PATH", "familiesWithUsableReadyFeature": usable,
                "reason": "fewer than two information families have a usable READY alpha candidate; Phase C is formally BLOCKED and Phase D is written from this report alone"}
    return {"verdict": "PROCEED_TO_PHASE_C_PREREGISTRATION", "familiesWithUsableReadyFeature": usable,
            "reason": "%d information families have at least one alpha candidate measured on >= %.0f%% of rows over >= %d evaluable weekly dates"
                      % (len(usable), 100 * MIN_FEATURE_COVERAGE, MIN_EVALUABLE_DATES)}


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def digest(obj):
    return hashlib.sha256(canonical(obj).encode()).hexdigest()
