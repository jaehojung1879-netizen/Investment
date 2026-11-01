"""Pure NAV readout. All reported return/risk numbers use explicit percent units."""
import bisect
import calendar
import datetime as dt
import math
import re
import statistics
from collections import Counter


REQUIRED = ("region", "strategyId", "studyId", "currency", "frequency", "returnBasis",
            "costBasis", "evidenceClass", "sourceCommit", "hashes", "nav")
ROUND_OFF_TIE_PP = 1e-10  # arithmetic precision only, never an economic hurdle


def date(value):
    parsed = dt.date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("NON_CANONICAL_DATE")
    return parsed


def validate(path):
    if any(k not in path for k in REQUIRED):
        raise ValueError("REQUIRED_NAV_METADATA_MISSING")
    for k in REQUIRED[:9]:
        if not isinstance(path[k], str) or not path[k]:
            raise ValueError("INVALID_METADATA:" + k)
    if path["frequency"] not in ("WEEKLY", "DAILY"):
        raise ValueError("UNSUPPORTED_FREQUENCY")
    if path["region"] not in ("KR", "US"):
        raise ValueError("UNSUPPORTED_REGION")
    if path["costBasis"] not in ("NET_ALREADY_CHARGED", "GROSS", "UNKNOWN"):
        raise ValueError("INVALID_COST_BASIS")
    if path.get("valueType", "NAV_LEVEL") != "NAV_LEVEL":
        raise ValueError("NAV_LEVELS_REQUIRED_NOT_PERCENT_RETURN_SERIES")
    if not isinstance(path["hashes"], dict) or not path["hashes"]:
        raise ValueError("SOURCE_HASHES_REQUIRED")
    if any(not isinstance(v, str) or not re.fullmatch(r"[0-9a-f]{64}", v) for v in path["hashes"].values()):
        raise ValueError("INVALID_SOURCE_HASH")
    if path["sourceCommit"] != "UNKNOWN" and not re.fullmatch(r"[0-9a-f]{40}", path["sourceCommit"]):
        raise ValueError("EXACT_SOURCE_COMMIT_OR_EXPLICIT_UNKNOWN_REQUIRED")
    points = {}
    previous = None
    for d, nav in path["nav"]:
        current = date(d)
        if previous is not None and current <= previous:
            raise ValueError("DUPLICATE_OR_UNSORTED_DATE")
        previous = current
        if nav is not None and (isinstance(nav, bool) or not isinstance(nav, (int, float))
                                or not math.isfinite(nav) or nav <= 0):
            raise ValueError("INVALID_OR_NONPOSITIVE_NAV_NOT_AN_ASSUMED_ZERO_RETURN")
        points[d] = nav
    if len(points) < 2:
        raise ValueError("INSUFFICIENT_NAV_OBSERVATIONS")
    return points


def quantile(values, fraction):
    if not values:
        return None
    v = sorted(values)
    x = (len(v) - 1) * fraction
    i = int(x)
    return v[i] + (v[min(i + 1, len(v) - 1)] - v[i]) * (x - i)


def summary(dates, nav):
    if len(nav) < 2 or any(x is None for x in nav):
        return None
    years = (date(dates[-1]) - date(dates[0])).days / 365.2425
    if years <= 0:
        return None
    returns = [b / a - 1 for a, b in zip(nav, nav[1:])]
    peak, peak_date = nav[0], dates[0]
    mdd, worst_peak, trough, recovery, worst_level = 0.0, dates[0], dates[0], dates[0], nav[0]
    for d, n in zip(dates, nav):
        drawdown = n / peak - 1
        if drawdown < mdd:
            mdd, worst_peak, trough, worst_level, recovery = drawdown, peak_date, d, peak, None
        if recovery is None and n >= worst_level:
            recovery = d
        if n >= peak:
            peak, peak_date = n, d
    return {
        "from": dates[0], "through": dates[-1], "observations": len(nav),
        "elapsedCalendarDays": (date(dates[-1])-date(dates[0])).days, "annualizationDaysPerYear": 365.2425,
        "normalization": "FIRST_STORED_OBSERVATION_REBASED_TO_ONE_NO_SYNTHETIC_INITIAL_NAV",
        "cumulativeReturnPct": (nav[-1] / nav[0] - 1) * 100,
        "cagrPct": ((nav[-1] / nav[0]) ** (1 / years) - 1) * 100,
        "observedMddPct": mdd * 100,
        "observedPeriodVolatilityPct": statistics.stdev(returns) * 100 if len(returns) > 1 else None,
        "observedPeriodLowerTailMeanReturnPct": statistics.mean(sorted(returns)[:max(1, math.ceil(.05 * len(returns)))]) * 100,
        "periodReturnObservations": len(returns), "lowerTailObservationCount": max(1, math.ceil(.05 * len(returns))),
        "recovery": {"peakDate": worst_peak, "troughDate": trough, "recoveryDate": recovery,
                     "peakToRecoveryCalendarDays": (date(recovery) - date(worst_peak)).days if recovery else None,
                     "unrecoveredCalendarDaysThroughLastObservation": (date(dates[-1]) - date(worst_peak)).days if recovery is None else None},
    }


def add_months(day, months):
    offset = day.year * 12 + day.month - 1 + months
    year, month = offset // 12, offset % 12 + 1
    return dt.date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def window_readout(dates, candidate, benchmark, horizon, as_of, *, sessions=False,
                   max_endpoint_lag=7, gap_limits=10, split_boundary=False):
    """Keep every scheduled origin, including missing and right-censored origins."""
    parsed = [date(d) for d in dates]
    invalid = {i for i, d in enumerate(dates) if candidate.get(d) is None or benchmark.get(d) is None}
    prefix = [0]
    for i in range(len(dates)):
        prefix.append(prefix[-1] + int(i in invalid))
    gaps = [i for i in range(1, len(dates)) if (parsed[i] - parsed[i-1]).days > gap_limits]
    records = []
    for i, start in enumerate(parsed):
        target = None if sessions else add_months(start, horizon)
        j = i + horizon if sessions else bisect.bisect_left(parsed, target)
        row = {"start": dates[i], "calendarTargetDate": target.isoformat() if target else None,
               "observedEndDate": dates[j] if j < len(dates) else None,
               "endpointLagCalendarDays": (parsed[j] - target).days if target and j < len(dates) else None}
        if candidate.get(dates[i]) is None or benchmark.get(dates[i]) is None:
            status = "MISSING_START"
        elif split_boundary and (j >= len(dates) or (target is not None and target > parsed[-1])):
            status = "CROSSES_FIXED_TIME_SPLIT"
        elif target and target > as_of:
            status = "IMMATURE_AT_AS_OF"
        elif j >= len(dates):
            status = "BEYOND_STORED_PATH_MATURITY_UNKNOWN" if sessions else "MATURE_TARGET_NO_STORED_ENDPOINT"
        elif parsed[j] > as_of:
            status = "ENDPOINT_AFTER_AS_OF"
        elif target and max_endpoint_lag is not None and (parsed[j] - target).days > max_endpoint_lag:
            status = "ENDPOINT_TOO_LATE_NO_INTERPOLATION"
        elif prefix[j+1] - prefix[i] or any(i < g <= j for g in gaps):
            status = "MISSING_OR_GAPPED_PAIRED_PATH"
        else:
            status = "MEASURED"
            c = candidate[dates[j]] / candidate[dates[i]] - 1
            b = benchmark[dates[j]] / benchmark[dates[i]] - 1
            row.update(candidateReturnPct=c * 100, benchmarkReturnPct=b * 100,
                       excessReturnPp=(c-b) * 100, relativeWealthReturnPct=((1+c)/(1+b)-1)*100)
        records.append({**row, "status": status})
    measured = [r for r in records if r["status"] == "MEASURED"]
    xs = [r["excessReturnPp"] for r in measured]
    disjoint, end = [], None
    for r in measured:
        if end is None or r["start"] >= end:
            disjoint.append(r["start"])
            end = r["observedEndDate"]
    counts = dict(Counter(r["status"] for r in records))
    return {
        "definition": f"H{horizon}_VERIFIED_SESSION_TRANSITIONS" if sessions else f"CALENDAR_{horizon}_MONTHS_" + ("FIRST_VERIFIED_SESSION_ENDPOINT" if max_endpoint_lag is None else f"FIRST_OBSERVED_ENDPOINT_WITHIN_{max_endpoint_lag}_DAYS"),
        "scheduledOrigins": len(records), "statusCounts": counts, "measuredWindows": len(xs),
        "meanExcessReturnPp": statistics.mean(xs) if xs else None,
        "winRatePct": 100 * sum(x > ROUND_OFF_TIE_PP for x in xs) / len(xs) if xs else None,
        "lossWindowCount": sum(x < -ROUND_OFF_TIE_PP for x in xs),
        "tieWindowCount": sum(abs(x) <= ROUND_OFF_TIE_PP for x in xs),
        "arithmeticTieTolerancePp_NOT_MATERIALITY_THRESHOLD": ROUND_OFF_TIE_PP,
        "p05ExcessReturnPp": quantile(xs, .05),
        "worst5PctMeanExcessReturnPp": statistics.mean(sorted(xs)[:max(1, math.ceil(.05*len(xs)))]) if xs else None,
        "disjointTimeWindowCount": len(disjoint), "disjointStartDates": disjoint,
        "independenceWarning": "DISJOINT_IS_NOT_PROOF_OF_STATISTICAL_INDEPENDENCE; NO_INFERENTIAL_CI",
    }, records


def verify_calendar(path, dates):
    policy = path.get("calendarPolicy")
    if path["frequency"] != "DAILY" or policy not in ("XKRX", "XNYS", "XKRX_DISCOVERY_V1"):
        return {"verified": False, "reason": "NO_VERIFIED_SESSION_CALENDAR", "expectedDates": None}
    if (path["region"] == "KR") != policy.startswith("XKRX"):
        raise ValueError("REGION_CALENDAR_MISMATCH")
    import exchange_calendars as xc
    cal = xc.get_calendar("XKRX" if policy.startswith("XKRX") else "XNYS",
                          start=dates[0], end=dates[-1])
    expected = [d.strftime("%Y-%m-%d") for d in cal.sessions]
    if policy == "XKRX_DISCOVERY_V1":
        expected = [d for d in expected if d not in {"2026-05-25", "2026-06-03", "2026-07-17"}]
    return {"verified": expected == dates, "policy": policy, "packageVersion": xc.__version__,
            "missingDates": sorted(set(expected) - set(dates)), "unexpectedDates": sorted(set(dates) - set(expected)),
            "expectedDates": expected, "scope": "SESSION_SCHEDULE_ONLY_NOT_SOURCE_OR_TOTAL_RETURN_ADMISSION"}


def compare(candidate_path, benchmark_path, as_of):
    candidate, benchmark = validate(candidate_path), validate(benchmark_path)
    for k in ("region", "currency", "frequency"):
        if candidate_path[k] != benchmark_path[k]:
            raise ValueError("INCOMPARABLE_" + k.upper())
    as_of = date(as_of)
    dates = sorted(set(candidate) | set(benchmark))
    if date(dates[-1]) > as_of:
        raise ValueError("NAV_AFTER_READOUT_AS_OF")
    cal = verify_calendar(candidate_path, dates)
    if candidate_path.get("calendarPolicy") != benchmark_path.get("calendarPolicy"):
        cal = {"verified": False, "reason": "PAIRED_CALENDAR_POLICIES_DIFFER", "expectedDates": None}
    schedule = sorted(set(dates) | set(cal.get("expectedDates") or []))
    missing = {"candidate": [d for d in schedule if candidate.get(d) is None],
               "benchmark": [d for d in schedule if benchmark.get(d) is None]}
    gap_limit = 10 if candidate_path["frequency"] == "WEEKLY" else (370 if cal["verified"] else 7)
    gaps = [schedule[i] for i in range(1, len(schedule)) if (date(schedule[i])-date(schedule[i-1])).days > gap_limit]
    midpoint = date(schedule[0]) + (date(schedule[-1])-date(schedule[0])) / 2
    split = bisect.bisect_left([date(d) for d in schedule], midpoint)
    partitions = {"FULL": schedule, "FIRST_EQUAL_TIME_HALF": schedule[:split], "SECOND_EQUAL_TIME_HALF": schedule[split:]}
    scopes, detail = {}, {}
    for label, ds in partitions.items():
        if len(ds) < 2:
            scopes[label] = {"status": "INSUFFICIENT_OBSERVATIONS"}
            continue
        c = summary(ds, [candidate.get(d) for d in ds])
        b = summary(ds, [benchmark.get(d) for d in ds])
        if any(d in missing["candidate"] or d in missing["benchmark"] or d in gaps for d in ds):
            c = b = None  # never chain over an absent funded observation
        windows = {}
        for months in (6, 12):
            w, rows = window_readout(ds, candidate, benchmark, months, as_of, gap_limits=gap_limit,
                                    max_endpoint_lag=None if cal["verified"] else 7,
                                    split_boundary=label == "FIRST_EQUAL_TIME_HALF")
            windows[f"CALENDAR_{months}M"] = w
            detail[label + f"/CALENDAR_{months}M"] = rows
        for sessions in (126, 252):
            if cal["verified"]:
                w, rows = window_readout(ds, candidate, benchmark, sessions, as_of, sessions=True, gap_limits=370,
                                        split_boundary=label == "FIRST_EQUAL_TIME_HALF")
                windows[f"H{sessions}"] = w
                detail[label+f"/H{sessions}"] = rows
            else:
                windows[f"H{sessions}"] = {"status": "UNAVAILABLE", "reason": "REQUIRES_VERIFIED_COMPLETE_DAILY_SESSION_PATH"}
        numeric_verdict = "INSUFFICIENT_PATH_DATA"
        if c and b:
            deltas = [c["cagrPct"]-b["cagrPct"], c["observedMddPct"]-b["observedMddPct"],
                      c["observedPeriodLowerTailMeanReturnPct"]-b["observedPeriodLowerTailMeanReturnPct"],
                      b["observedPeriodVolatilityPct"]-c["observedPeriodVolatilityPct"]
                      if c["observedPeriodVolatilityPct"] is not None and b["observedPeriodVolatilityPct"] is not None else 0]
            deltas = [0 if abs(x) <= ROUND_OFF_TIE_PP else x for x in deltas]
            numeric_verdict = ("OBSERVED_INFERIOR" if all(x <= 0 for x in deltas) and any(x < 0 for x in deltas)
                               else "OBSERVED_DOMINATES" if all(x >= 0 for x in deltas) and any(x > 0 for x in deltas)
                               else "OBSERVED_EQUAL" if all(abs(x) < 1e-12 for x in deltas) else "RISK_RETURN_TRADE_OFF")
        scopes[label] = {"candidate": c, "benchmark": b,
                        "cagrGapPp": c["cagrPct"]-b["cagrPct"] if c and b else None,
                        "cumulativeReturnGapPp": c["cumulativeReturnPct"]-b["cumulativeReturnPct"] if c and b else None,
                        "observedPathVerdict": numeric_verdict, "windows": windows}
    meta = lambda p: {k: v for k, v in p.items() if k != "nav"}
    return {
        "candidateInput": meta(candidate_path), "benchmarkInput": meta(benchmark_path),
        "asOfDate": as_of.isoformat(), "units": "PERCENT_FOR_RETURNS_AND_PP_FOR_DIFFERENCES_NOT_FRACTIONS",
        "pairedCalendar": {k:v for k,v in cal.items() if k != "expectedDates"},
        "schedule": {"origins": len(schedule), "candidateObservations": len(candidate), "benchmarkObservations": len(benchmark),
                     "missingCandidateDates": missing["candidate"], "missingBenchmarkDates": missing["benchmark"], "gapDates": gaps},
        "equalElapsedTimeSplitDate": midpoint.isoformat(), "scopes": scopes,
        "dailyMdd": "AVAILABLE_OBSERVED_DAILY" if cal["verified"] and not any(missing.values()) and not gaps else "UNAVAILABLE",
        "turnover": None, "exactAdditionalCostStress": None, "selectionAlpha": None,
        "unavailableReason": "NO_POSITIONS_OR_TRADE_LEDGER_IN_THIS_ADAPTER; NO_COST_DEDUCTION_OR_MODEL_SELECTION",
        "investmentConclusion": "INSUFFICIENT_SOURCE_EVIDENCE_NO_PROMOTION",
        "comparativeInterpretation": "DESCRIPTIVE_ONLY_RETURN_OR_COST_BASIS_MISMATCH"
        if candidate_path["returnBasis"] != benchmark_path["returnBasis"] or candidate_path["costBasis"] != benchmark_path["costBasis"]
        else "DESCRIPTIVE_ONLY_SOURCE_ADMISSION_NOT_CERTIFIED",
        "excessLabel": "STORED_NET_NAV_DIFFERENCE_NOT_CERTIFIED_INVESTABLE_ALPHA" if candidate_path["costBasis"] == benchmark_path["costBasis"] == "NET_ALREADY_CHARGED" else "STORED_NAV_DIFFERENCE_NET_STATUS_UNPROVEN",
        "economicBasisMatches": candidate_path["returnBasis"] == benchmark_path["returnBasis"] != "UNKNOWN",
        "costBasisMatches": candidate_path["costBasis"] == benchmark_path["costBasis"],
    }, detail
