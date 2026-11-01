"""One M3 hypothesis: metadata support geometry only; no numerical observations."""

import calendar
import datetime as dt
import math
import re
from pathlib import Path
from zoneinfo import ZoneInfo

from scipy.stats import nct, t

from .parser import GROUPS

ROOT = Path(__file__).resolve().parent


def shift_month(month, n):
    year, m = map(int, month.split("-"))
    total = year * 12 + m - 1 + n
    return f"{total // 12:04}-{total % 12 + 1:02}"


def month_end(month):
    year, m = map(int, month.split("-"))
    return dt.date(year, m, calendar.monthrange(year, m)[1])


def metadata_valid(row, kinds):
    if row.get("status") != "METADATA_PRESENT":
        return False
    pub = row.get("printedPublicationDate")
    ref = row.get("referenceMonth")
    if not pub or not ref or dt.date.fromisoformat(pub) <= month_end(ref):
        return False
    # Original Apr-2003 notice: semiconductor shipments return with Jul-2003.
    # Keep all six groups; do not backfill revised semiconductor history or drop it.
    if ref < "2003-07":
        return False
    return all(row.get("tables", {}).get(kind, {}).get(g, {}).get("status") ==
               "SHAPE_PRESENT_NOT_VALUE_ADMITTED" for g in GROUPS for kind in kinds)


def known_before_month_end(row, cutoff):
    publication = dt.date.fromisoformat(row["printedPublicationDate"])
    if publication != cutoff:
        return publication < cutoff
    # Day-only metadata must not be silently assigned midnight on the cutoff day.
    for clock in row.get("printedReleaseClock", []):
        m = re.fullmatch(r"(\d{1,2}):(\d{2})\s*([AP])\.?M\.?\s*(EST|EDT|ET)", clock, re.I)
        if m and 1 <= int(m[1]) <= 12 and 0 <= int(m[2]) <= 59:
            ny = ZoneInfo("America/New_York")
            tz = {"EST": dt.timezone(dt.timedelta(hours=-5)),
                  "EDT": dt.timezone(dt.timedelta(hours=-4)), "ET": ny}[m[4].upper()]
            hour = int(m[1]) % 12 + (12 if m[3].upper() == "P" else 0)
            instant = dt.datetime.combine(publication, dt.time(hour, int(m[2]), tzinfo=tz))
            return instant < dt.datetime.combine(cutoff, dt.time(23, 59, 59, tzinfo=ny))
    return False


def origin_support(month, rows):
    cutoff = month_end(month)
    available = [r for r in rows.values()
                 if r.get("printedPublicationDate") and r.get("referenceMonth")
                 and dt.date.fromisoformat(r["printedPublicationDate"]) > month_end(r["referenceMonth"])
                 and dt.date.fromisoformat(r["printedPublicationDate"]) <= cutoff]
    if not available:
        return {"cutoffMonth": month, "metadataSupport": False, "reason": "NO_KNOWN_FULL_RELEASE"}
    latest = max(available, key=lambda r: (r["printedPublicationDate"], r["referenceMonth"]))
    if not known_before_month_end(latest, cutoff):
        return {"cutoffMonth": month, "metadataSupport": False,
                "reason": "LATEST_RELEASE_SAME_DAY_CLOCK_UNKNOWN_NO_FALLBACK"}
    if not metadata_valid(latest, ("shipments", "unfilledOrders")):
        return {"cutoffMonth": month, "metadataSupport": False,
                "reason": "LATEST_RELEASE_INPUT_MISSING_NO_FALLBACK"}
    ref = latest["referenceMonth"]
    prior = [shift_month(ref, -i) for i in range(3)]
    # A later release cannot supply a missing earlier first-full baseline.
    missing_past = [m for m in prior
                    if m not in rows or not metadata_valid(rows[m], ("shipments",))
                    or dt.date.fromisoformat(rows[m]["printedPublicationDate"]) > cutoff]
    future = [shift_month(month, i) for i in (1, 2, 3)]
    missing_future = [m for m in future
                      if m not in rows or not metadata_valid(rows[m], ("shipments",))]
    last_pub = (max(rows[m]["printedPublicationDate"] for m in future)
                if not missing_future else None)
    return {"cutoffMonth": month, "latestReferenceMonthKnownAtCutoff": ref,
            "latestPrintedPublicationDate": latest["printedPublicationDate"],
            "baselineFirstFullReferences": prior, "futureTargetReferences_METADATA_ONLY": future,
            "missingPastReferences": missing_past, "missingFutureReferences": missing_future,
            "targetFinalPublicationDate_METADATA_ONLY": last_pub,
            "metadataSupport": not missing_past and not missing_future,
            "numericalPredictorOrOutcome": None}


def power_feasibility(n, effect=0.40, variance_inflation=1.5):
    """Planning calculation, not a historical power estimate or valid real-data test."""
    if n < 2:
        return None
    noncentrality = effect * math.sqrt(n / variance_inflation)
    return float(nct.sf(t.ppf(0.95, n - 1), n - 1, noncentrality))


def summarize(rows):
    by_month = {r["referenceMonth"]: r for r in rows if r.get("referenceMonth")}
    origins = {}
    month = "2003-01"
    while month <= "2025-12":
        origins[month] = origin_support(month, by_month)
        month = shift_month(month, 1)
    evaluation = []
    for month, origin in origins.items():
        if month < "2009-01" or int(month[5:]) not in (1, 4, 7, 10):
            continue
        cutoff = month_end(month).isoformat()
        completed = [m for m, prior in origins.items() if m < month
                     and prior["metadataSupport"]
                     and prior.get("targetFinalPublicationDate_METADATA_ONLY")
                     and prior["targetFinalPublicationDate_METADATA_ONLY"] <= cutoff
                     and all(known_before_month_end(by_month[ref], month_end(month))
                             for ref in prior["futureTargetReferences_METADATA_ONLY"])]
        evaluation.append({**origin, "priorCompletedMonthlyTrainingOrigins": len(completed),
                           "passesTrainingMetadataFloor": len(completed) >= 60,
                           "metadataCompleteSixGroupTimeBlock": origin["metadataSupport"]
                           and len(completed) >= 60})
    n = sum(x["metadataCompleteSixGroupTimeBlock"] for x in evaluation)
    return {
        "evaluationRows": evaluation,
        "fixedEvaluationTimeBlocks": len(evaluation),
        "metadataCompleteSixGroupTimeBlocks": n,
        "completeMetadataFraction": n / len(evaluation),
        "metadataSupportPasses60BlockFloor": n >= 60,
        "planningPowerAtFixedAssumptions": power_feasibility(n),
        "underpoweredCounterexampleAtHalfPlanningEffect": power_feasibility(n, effect=0.20),
        "actualPowerFromHistoricalLosses": None,
        "numericalOutcomeValuesMaterialized": 0,
        "fitsOrForecastEvaluationRuns": 0,
    }

