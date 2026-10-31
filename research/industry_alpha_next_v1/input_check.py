"""Label-free verification of the real inputs for industry-alpha-kr-next-v1.

Publishes COUNTS ONLY: who is in the PIT cohorts and who is not (by count and by snapshot-cap share), how many
industry-dates and dates each hypothesis could use, how much of each feature block is measured, and what the CALENDAR
alone says about the registered support rule. It never computes a forward return, never publishes a feature value or a
feature/target relationship, and asserts that no outcome function was entered.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline import kr_factor_anatomy_execution as AE
from pipeline import kr_industry_anatomy as I
from pipeline import kr_industry_anatomy_execution as IE
from pipeline import kr_value_quality_catalyst as VQC
from pipeline import replay_calendar as RC

from . import evaluate as E
from . import panel as P
from . import study as S

CALENDAR = ("2013-01-01", "2028-12-31")


def calendar_support(dates, sessions, through):
    """Per horizon: maturable signals, walk-forward test years/dates and the registered support verdict. Dates only."""
    days = pd.DatetimeIndex(sessions)
    out = {}
    for h in S.HORIZONS:
        mature = [d for d in sorted(dates) if E.label_exit_position(days, d, h) < len(days)
                  and days[E.label_exit_position(days, d, h)] <= pd.Timestamp(through)]
        folds = E.folds(mature, days, h)
        test = [d for _, _, t in folds for d in t]
        blocks = E.support_blocks(test)
        out[f"H{h}"] = {"maturableSignals": len(mature), "firstMaturable": mature[0] if mature else None,
                        "lastMaturable": mature[-1] if mature else None,
                        "testYears": [y for y, _, _ in folds], "testSignals": len(test), "supportBlocks": blocks,
                        "requiredBlocks": S.MIN_NONOVERLAPPING_H252_BLOCKS,
                        "supportReading": "SUPPORT_REACHABLE" if blocks >= S.MIN_NONOVERLAPPING_H252_BLOCKS
                        else "STRUCTURALLY_INSUFFICIENT_SUPPORT_UNDER_REGISTERED_RULE"}
    return out


def _by_year(frame, column, how="sum"):
    g = frame.assign(year=frame["date"].str[:4]).groupby("year")[column]
    return {k: (int(v) if how == "sum" else round(float(v), 4)) for k, v in getattr(g, how)().items()}


def build_label_free(loaded):
    """The full label-free panel the study would use. `loaded` = dict(membership, caps, prices, accounting)."""
    m, caps_view, prices, accounting = loaded["membership"], loaded["caps"], loaded["prices"], loaded["accounting"]
    schedule = P.monthly_signals(m["weekly"])
    caps = {(d, t): caps_view.cap(t, d) or np.nan for d, names in schedule.items() for t in names}
    capframe = pd.DataFrame([{"date": d, "ticker": t, "marketCap": v} for (d, t), v in caps.items()])
    membership = I.membership_table(schedule, m["intervals"], m["crosswalk"], m["ends"])
    cohorts = I.build_cohorts(membership, capframe)
    days = RC.sessions(*CALENDAR, "KR")
    market = loaded["marketAdapter"]
    bench = prices.get(S.BENCHMARK)
    panel_values, past, market_by_date = {}, {}, {}
    for date, names in schedule.items():
        past[date] = IE.past_features(prices, names, days, date)
        vals = {}
        for t in names:
            row = VQC.feature_at(t, date, accounting.get(t, []), market, prices.get(t), bench)
            row["netIncomeImprovementToAssets"] = AE.improvement_to_assets(accounting.get(t, []), date, "당기순이익")
            vals[t] = row
        panel_values[date] = vals
        pos = days.searchsorted(pd.Timestamp(date), side="right") - 1
        close = bench["Close"].reindex(days[max(0, pos - 252):pos + 1]).to_numpy(float) if bench is not None else []
        market_by_date[date] = P.market_context(close)
    rows, splits = P.industry_rows(cohorts, past, panel_values, market_by_date, caps)
    return {"schedule": schedule, "membership": membership, "cohorts": cohorts, "rows": rows, "splits": splits,
            "caps": caps, "sessions": days}


def summarize(built, terminal, through):
    schedule, rows, cohorts = built["schedule"], built["rows"], built["cohorts"]
    exposure = P.exposure_audit(built["membership"], built["caps"], terminal)
    eligible = [k for k, c in cohorts.items() if c["status"] == "ELIGIBLE"]
    per_date = pd.Series([d for d, _ in eligible]).value_counts()
    dates_ok = sorted(d for d in schedule if per_date.get(d, 0) >= S.MIN_INDUSTRIES_PER_DATE)
    columns = [c for cols in S.BLOCKS.values() for c in cols] + list(S.NUISANCE) + list(S.MARKET_CONTEXT) \
        + list(S.DIFFUSION_BASE) + list(S.DIFFUSION_SIGNAL)
    coverage = {c: int(pd.to_numeric(rows[c], errors="coerce").notna().sum()) if c in rows else 0 for c in dict.fromkeys(columns)}
    by_year = rows.assign(year=rows["date"].str[:4]) if len(rows) else rows
    block_cov = {}
    for block, cols in S.BLOCKS.items():
        ok = rows[list(cols)].apply(pd.to_numeric, errors="coerce").notna().all(axis=1) if len(rows) else pd.Series(dtype=bool)
        block_cov[block] = {k: round(float(v), 4) for k, v in ok.groupby(by_year["year"]).mean().items()} if len(rows) else {}
    return {
        "studyId": S.STUDY_ID, "status": S.STATUS, "evidenceClass": "LABEL_FREE_INPUT_VERIFICATION",
        "specSha256": S.spec_sha256(), "outcomeCalls": 0,
        "signals": {"count": len(schedule), "first": min(schedule), "last": max(schedule), "rule": S.SIGNAL_RULE,
                    "membersPerSignal": sorted({len(v) for v in schedule.values()})},
        "cohortExclusion": {
            "memberDates": int(exposure["members"].sum()),
            "unclassifiedMemberDates": int(exposure["unclassified"].sum()),
            "unclassifiedCapShareMean": round(float(exposure["unclassifiedCapShare"].mean()), 4),
            "unclassifiedCapShareMax": round(float(exposure["unclassifiedCapShare"].max()), 4),
            "terminalLaterMemberDates": int(exposure["terminalLater"].sum()),
            "terminalLaterClassifiedMemberDates": int(exposure["terminalLaterClassified"].sum()),
            "terminalLaterCapShareMean": round(float(exposure["terminalLaterCapShare"].mean()), 4),
            "inEligibleCohortCapShareMean": round(float(exposure["inEligibleCohortCapShare"].mean()), 4),
            "inEligibleCohortCapShareMin": round(float(exposure["inEligibleCohortCapShare"].min()), 4),
            "datesWithAnyUnclassifiedMember": int((exposure["unclassified"] > 0).sum()),
            "byYearUnclassifiedCapShare": _by_year(exposure, "unclassifiedCapShare", "mean"),
            "byYearTerminalLaterMemberDates": _by_year(exposure, "terminalLater"),
        },
        "industryDates": {"total": len(cohorts), "eligible": len(eligible),
                          "ineligibleBelowMinimumMembers": len(cohorts) - len(eligible),
                          "eligiblePerDateMin": int(per_date.min()) if len(per_date) else 0,
                          "eligiblePerDateMedian": float(per_date.median()) if len(per_date) else 0,
                          "eligiblePerDateMax": int(per_date.max()) if len(per_date) else 0,
                          "datesWithAtLeastMinIndustries": len(dates_ok),
                          "diffusionEligibleIndustryDates": len(built["splits"])},
        "featureCoverage": {"finiteIndustryDates": coverage, "blockCompleteShareByYear": block_cov},
        "calendarSupport": calendar_support(dates_ok, built["sessions"], through),
    }


def run(loaded, through):
    """Entry used by `run_study verify-inputs`. Refuses if any outcome function was entered (checked by the caller's spy)."""
    built = build_label_free(loaded)
    return summarize(built, loaded["membership"]["terminal"], through)


def structural_findings(report):
    """Plain statements derived from the report (counts only), for the approval packet."""
    out = []
    ex = report["cohortExclusion"]
    out.append(f"classified cohorts omit {ex['unclassifiedMemberDates']} of {ex['memberDates']} PIT member-dates "
               f"(mean snapshot-cap share {ex['unclassifiedCapShareMean']:.1%}); every date with an unclassified member: "
               f"{ex['datesWithAnyUnclassifiedMember']} of {report['signals']['count']}")
    out.append(f"later-terminated securities: {ex['terminalLaterMemberDates']} member-dates, "
               f"{ex['terminalLaterClassifiedMemberDates']} of them classified (i.e. in a cohort)")
    for h, v in report["calendarSupport"].items():
        out.append(f"{h}: {v['testSignals']} test signals in {len(v['testYears'])} test years -> {v['supportBlocks']} "
                   f"support blocks vs {v['requiredBlocks']} required: {v['supportReading']}")
    return out
