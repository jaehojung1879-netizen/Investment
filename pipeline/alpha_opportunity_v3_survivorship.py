"""Input-only survivorship audit for alpha-opportunity-model-v3. Research only.

Reads identities, whether a sealed close/volume EXISTS on a date, membership
snapshots and corporate-event presence. It never computes a return, never
reads a label, and never looks at a price level beyond "positive and finite".

Two different survivorship failures are measured separately, because they
have different consequences and no single fix:

* TRAINING / SAMPLE survivorship: which PIT members have their own history in
  the sealed panel at all. A member missing here contributes no features, no
  training rows and no evaluation rows. Stressing forward endpoints cannot
  restore it: an endpoint bound acts on names that ARE in the sample.
* ENDPOINT survivorship: among names that are in the sample, which scheduled
  forward exits have no close (a delisting inside the horizon).

A region is only survivorship-safe for a historical alpha claim when BOTH are
answered AND the price basis is the same for names that later exit as for
names that survive (here: dividend lineage for terminated names).
"""
from __future__ import annotations

import math
from bisect import bisect_right

import pandas as pd

from . import replay_calendar as RC

NO_PANEL = "NO_PANEL"
NO_SIGNAL_DATE_PRICE = "NO_SIGNAL_DATE_PRICE"
NOT_CONTINUOUSLY_TRADED = "NOT_CONTINUOUSLY_TRADED"
TRADABLE = "TRADABLE"
STATUSES = (NO_PANEL, NO_SIGNAL_DATE_PRICE, NOT_CONTINUOUSLY_TRADED, TRADABLE)

# A panel whose last valid close is this many calendar days before the sealed
# cutoff has stopped trading inside the sample (a terminated security). The
# gap only has to exceed ordinary settling at the cutoff; it is not tuned.
TERMINATION_GAP_DAYS = 45


def ok_number(value):
    return isinstance(value, (int, float)) and math.isfinite(value) and value > 0


def availability_from_rows(rows):
    """{ticker: {date: (closeOk, volumeOk)}} from sealed panel rows."""
    out = {}
    for row in rows:
        out.setdefault(row["ticker"], {})[row["date"]] = (ok_number(row.get("Close")),
                                                          ok_number(row.get("Volume")))
    return out


def weekly_grid(sessions, through):
    """Last regional session of each calendar week (regional_alpha_features semantics)."""
    days = pd.DatetimeIndex(sessions)
    picked = pd.Series(days, index=days).groupby(days.to_period("W")).max()
    return [str(d.date()) for d in picked if str(d.date()) <= through]


def snapshot_on(snapshots, date):
    """Strictly-earlier membership snapshot; same-day observations are never used."""
    dates = [s["date"] for s in snapshots]
    pos = bisect_right(dates, date) - 1
    while pos >= 0 and dates[pos] >= date:
        pos -= 1
    return snapshots[pos] if pos >= 0 else None


def classify(avail_t, date, window_dates):
    """Status of one PIT member-date. No fill, no substitute, no future session."""
    if avail_t is None:
        return NO_PANEL
    today = avail_t.get(date)
    if not today or not today[0]:
        return NO_SIGNAL_DATE_PRICE
    if len(window_dates) < 20 or not all(avail_t.get(d, (False, False)) == (True, True)
                                         for d in window_dates):
        return NOT_CONTINUOUSLY_TRADED
    return TRADABLE


def last_close(avail_t):
    closes = [d for d, (c, _) in avail_t.items() if c]
    return max(closes) if closes else None


def first_close(avail_t):
    closes = [d for d, (c, _) in avail_t.items() if c]
    return min(closes) if closes else None


def audit_region(region, snapshots, avail, dividend_counts, *, start, through,
                 horizons=(21, 126), window=20, sessions=None):
    """Every integrity reading for one region. Pure given its inputs."""
    snapshots = sorted(snapshots, key=lambda s: s["date"])
    sessions = sessions if sessions is not None else RC.sessions("2012-01-01", "2027-12-31", region)
    sdates = [str(d.date()) for d in sessions]
    index = {d: i for i, d in enumerate(sdates)}
    grid = weekly_grid([d for d in sessions if str(d.date()) >= start], through)
    union, first_member, last_member = set(), {}, {}
    rows = []
    for date in grid:
        snap = snapshot_on(snapshots, date)
        if snap is None:
            raise ValueError("PIT_MEMBERSHIP_MISSING: " + region + "/" + date)
        i = index[date]
        window_dates = sdates[max(0, i - window + 1):i + 1]
        for ticker in snap["members"]:
            union.add(ticker)
            first_member.setdefault(ticker, date)
            last_member[ticker] = date
            status = classify(avail.get(ticker), date, window_dates)
            endpoints = {}
            if status == TRADABLE:
                for h in horizons:
                    j = i + 1 + h
                    if j >= len(sdates) or sdates[j] > through:
                        endpoints[h] = "PENDING"
                    else:
                        c = avail[ticker].get(sdates[j])
                        endpoints[h] = "PRESENT" if c and c[0] else "MISSING"
            rows.append({"date": date, "year": date[:4], "ticker": ticker, "status": status,
                         **{f"endpoint{h}": endpoints.get(h) for h in horizons}})
    frame = pd.DataFrame(rows)
    current = set(snapshots[-1]["members"])
    departed = union - current
    no_panel = {t for t in union if t not in avail}
    cutoff = pd.Timestamp(through)
    terminated = {t for t in union - no_panel
                  if (cutoff - pd.Timestamp(last_close(avail[t]))).days > TERMINATION_GAP_DAYS}
    continuing = union - no_panel - terminated
    # A panel whose first close comes after the name's last membership date
    # cannot be that member's own history (symbol reuse or a late series).
    foreign = {t for t in union - no_panel if first_close(avail[t]) > last_member[t]}

    def share(num, den):
        return round(100.0 * num / den, 4) if den else None

    def with_dividends(names):
        return sum(1 for t in names if dividend_counts.get(t, 0) > 0)

    by_year = {}
    for year, g in frame.groupby("year"):
        counts = g.status.value_counts()
        by_year[year] = {"memberDates": int(len(g)),
                         **{s: share(int(counts.get(s, 0)), len(g)) for s in STATUSES},
                         "departedOnlyNoPanelPct": share(int(g.ticker.isin(no_panel & departed).sum()), len(g))}
    tradable = frame.loc[frame.status.eq(TRADABLE)]
    endpoints = {}
    for h in horizons:
        col = tradable[f"endpoint{h}"]
        matured = col.ne("PENDING")
        endpoints[str(h)] = {"matured": int(matured.sum()),
                             "missing": int(col.eq("MISSING").sum()),
                             "missingPct": share(int(col.eq("MISSING").sum()), int(matured.sum())),
                             "missingOnTerminatedNames": int((col.eq("MISSING") & tradable.ticker.isin(terminated)).sum())}
    terminated_no_div = {t for t in terminated if dividend_counts.get(t, 0) == 0}
    gaps = pd.Series(pd.to_datetime([s["date"] for s in snapshots])).diff().dt.days.dropna()
    return {
        "region": region,
        "weeklyDates": len(grid),
        "memberDates": int(len(frame)),
        "universe": {"union": len(union), "currentMembers": len(current & union), "departedMembers": len(departed)},
        "sampleSurvivorship": {
            "noPanelNames": len(no_panel),
            "noPanelDeparted": len(no_panel & departed),
            "noPanelCurrent": len(no_panel & current),
            "pNoPanelGivenDeparted": share(len(no_panel & departed), len(departed)),
            "pNoPanelGivenCurrent": share(len(no_panel & current), len(current & union)),
            "panelNotOwnHistoryNames": len(foreign),
            "departedWithOwnHistory": len(departed - no_panel - foreign),
        },
        "terminations": {
            "terminatedInPanel": len(terminated),
            "continuingPanels": len(continuing),
            "terminationGapDays": TERMINATION_GAP_DAYS,
        },
        "totalReturnLineage": {
            "terminatedWithDividendEvents": with_dividends(terminated),
            "terminatedNames": len(terminated),
            "continuingWithDividendEvents": with_dividends(continuing),
            "continuingNames": len(continuing),
            "tradableMemberDatesOnTerminatedNamesWithoutDividendLineagePct":
                share(int(tradable.ticker.isin(terminated_no_div).sum()), len(tradable)),
            "byYear": {y: share(int(g.ticker.isin(terminated_no_div).sum()), len(g))
                       for y, g in tradable.groupby("year")},
        },
        "endpointSurvivorship": endpoints,
        "memberDatesByYear": by_year,
        "membershipSnapshots": {"count": len(snapshots), "first": snapshots[0]["date"],
                                "last": snapshots[-1]["date"],
                                "maxGapDays": int(gaps.max()) if len(gaps) else None,
                                "gapsOver45Days": int((gaps > 45).sum())},
        "_sets": {"noPanel": sorted(no_panel), "terminated": sorted(terminated),
                  "terminatedWithoutDividends": sorted(terminated_no_div), "notOwnHistory": sorted(foreign)},
    }


def region_verdict(audit):
    """Pre-registered, outcome-free rules. Every clause reads identities only.

    1. Missingness that falls ONLY on departed members is not random: it is
       conditioned on the future (the name left and the vendor dropped it).
    2. A region whose sample never observes a security terminating contains no
       failed or acquired company at all; that is survivorship by construction
       whatever share of member-dates it touches.
    3. Terminated names must carry the same total-return basis as survivors;
       a zero dividend-event count across all terminated names while survivors
       carry them is a source gap, not a dividend policy.
    """
    s, t, lin = audit["sampleSurvivorship"], audit["terminations"], audit["totalReturnLineage"]
    defects = []
    if s["noPanelDeparted"] > 0 and s["noPanelCurrent"] == 0:
        defects.append("MISSINGNESS_CONCENTRATED_IN_DEPARTED_MEMBERS")
    if s["panelNotOwnHistoryNames"] > 0:
        defects.append("PANEL_SYMBOL_NOT_MEMBER_HISTORY")
    if t["terminatedInPanel"] == 0 and audit["universe"]["departedMembers"] > 0:
        defects.append("NO_TERMINATED_SECURITY_IN_SAMPLE")
    if (lin["terminatedNames"] > 0 and lin["terminatedWithDividendEvents"] == 0
            and lin["continuingWithDividendEvents"] > 0):
        defects.append("TERMINATED_NAMES_LACK_TOTAL_RETURN_LINEAGE")
    return {"region": audit["region"], "survivorshipSafe": not defects, "defects": defects}


def restricted_window_exists(audit):
    """Can a later sub-period be survivorship-safe on the SAME rules?

    Decided from data availability only: a year qualifies only if no member-
    date in it falls on a departed no-panel name. A trailing run of qualifying
    years is the only structurally defensible restricted sample; a smoothly
    declining share that never reaches zero offers no cutoff, only a tolerance.
    """
    years = sorted(audit["memberDatesByYear"])
    clean = [y for y in years if audit["memberDatesByYear"][y]["departedOnlyNoPanelPct"] == 0]
    trailing = []
    for y in reversed(years):
        if y not in clean:
            break
        trailing.insert(0, y)
    return {"cleanYears": clean, "trailingCleanYears": trailing,
            "structuralCutoffExists": bool(trailing) and len(trailing) < len(years)}
