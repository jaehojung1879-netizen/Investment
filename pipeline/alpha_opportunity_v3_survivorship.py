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
IDENTITY_UNRESOLVED = "IDENTITY_UNRESOLVED"
STATUSES = (IDENTITY_UNRESOLVED, NO_PANEL, NO_SIGNAL_DATE_PRICE, NOT_CONTINUOUSLY_TRADED, TRADABLE)

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
                 horizons=(21, 126), window=20, sessions=None, identity_index=None,
                 corporate_actions=()):
    """Every integrity reading for one region. Pure given its inputs.

    Identity is resolved FIRST (``alpha_opportunity_v3_identity``): evidence-
    resolved malformed keys are replaced by their security, unresolved ones are
    counted as IDENTITY_UNRESOLVED member-dates, and each symbol is priced only
    from its own history or its verified rename successor's.
    """
    from . import alpha_opportunity_v3_identity as ID
    snapshots = sorted(snapshots, key=lambda s: s["date"])
    raw_records, malformed_map = ID.classify(snapshots, avail, index=identity_index,
                                             corporate_actions=corporate_actions, through=through)
    snaps = ID.normalized_snapshots(snapshots, malformed_map)
    index_norm = None
    if identity_index is not None:
        index_norm = [{malformed_map.get(t, t): row for t, row in idx.items()} for idx in identity_index]
    records, _ = ID.classify(snaps, avail, index=index_norm, corporate_actions=corporate_actions,
                             through=through)
    pricing = {t: ID.pricing_symbol(t, records) for t in records}
    sessions = sessions if sessions is not None else RC.sessions("2012-01-01", "2027-12-31", region)
    sdates = [str(d.date()) for d in sessions]
    index = {d: i for i, d in enumerate(sdates)}
    grid = weekly_grid([d for d in sessions if str(d.date()) >= start], through)
    raw_reachable, union = set(), set()
    rows = []
    for date in grid:
        raw_snap = snapshot_on(snapshots, date)
        snap = snapshot_on(snaps, date)
        if snap is None:
            raise ValueError("PIT_MEMBERSHIP_MISSING: " + region + "/" + date)
        raw_reachable.update(raw_snap["members"])
        i = index[date]
        window_dates = sdates[max(0, i - window + 1):i + 1]
        for ticker in snap["members"]:
            union.add(ticker)
            if records[ticker]["category"] == ID.IDENTIFIER_MALFORMED_UNRESOLVED:
                status, priced = IDENTITY_UNRESOLVED, None
            else:
                priced = pricing[ticker]
                status = classify(avail.get(priced) if priced else None, date, window_dates)
            endpoints = {}
            if status == TRADABLE:
                for h in horizons:
                    j = i + 1 + h
                    if j >= len(sdates) or sdates[j] > through:
                        endpoints[h] = "PENDING"
                    else:
                        c = avail[priced].get(sdates[j])
                        endpoints[h] = "PRESENT" if c and c[0] else "MISSING"
            rows.append({"date": date, "year": date[:4], "ticker": ticker, "status": status,
                         **{f"endpoint{h}": endpoints.get(h) for h in horizons}})
    frame = pd.DataFrame(rows)
    current = set(snaps[-1]["members"])
    departed = union - current
    unresolved = {t for t in union if records[t]["category"] == ID.IDENTIFIER_MALFORMED_UNRESOLVED}
    no_panel = {t for t in union - unresolved if pricing[t] is None}
    cutoff = pd.Timestamp(through)
    priced_union = union - no_panel - unresolved
    terminated = {t for t in priced_union
                  if (cutoff - pd.Timestamp(last_close(avail[pricing[t]]))).days > TERMINATION_GAP_DAYS}
    continuing = priced_union - terminated
    foreign = {t for t in union if "PANEL_POSTDATES_MEMBERSHIP" in records[t]["flags"]}
    renamed = {t for t in union if records[t]["category"] == ID.SAME_SECURITY_RENAME}

    def share(num, den):
        return round(100.0 * num / den, 4) if den else None

    def with_dividends(names):
        return sum(1 for t in names if dividend_counts.get(pricing[t], 0) > 0)

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
    terminated_no_div = {t for t in terminated if dividend_counts.get(pricing[t], 0) == 0}
    categories = {}
    for t in sorted(union):
        categories.setdefault(records[t]["category"], []).append(t)
    identity = {
        "categoryCounts": {c: len(v) for c, v in sorted(categories.items())},
        "categories": {c: v for c, v in sorted(categories.items())},
        "renames": {t: {"successor": records[t]["successor"], "basis": records[t]["basis"],
                        "pricedBy": pricing[t]} for t in sorted(renamed)},
        "malformed": {t: {"category": r["category"], "resolvedTo": r.get("resolvedTo"),
                          "snapshots": [s["date"] for s in snapshots if t in s["members"]],
                          "reachableFromGrid": t in raw_reachable}
                      for t, r in sorted(raw_records.items())
                      if r["category"] in (ID.IDENTIFIER_MALFORMED_RESOLVED, ID.IDENTIFIER_MALFORMED_UNRESOLVED)},
        "panelPostdatesMembership": sorted(foreign),
        "ambiguousRenames": sorted(t for t in union if "RENAME_AMBIGUOUS" in records[t]["flags"]),
    }
    gaps = pd.Series(pd.to_datetime([s["date"] for s in snapshots])).diff().dt.days.dropna()
    return {
        "region": region,
        "weeklyDates": len(grid),
        "memberDates": int(len(frame)),
        "universe": {"union": len(union), "currentMembers": len(current & union), "departedMembers": len(departed),
                     "rawAllSnapshotUnion": len(set().union(*[set(x["members"]) for x in snapshots])),
                     "rawGridReachableUnion": len(raw_reachable),
                     "identityUnresolvedNames": len(unresolved)},
        "identity": identity,
        "sampleSurvivorship": {
            "noPanelNames": len(no_panel),
            "noPanelDeparted": len(no_panel & departed),
            "noPanelCurrent": len(no_panel & current),
            "pNoPanelGivenDeparted": share(len(no_panel & departed), len(departed)),
            "pNoPanelGivenCurrent": share(len(no_panel & current), len(current & union)),
            "panelNotOwnHistoryNames": len(foreign),
            "departedPricedByOwnHistory": len({t for t in departed - no_panel - unresolved if pricing[t] == t}),
            "departedPricedViaVerifiedRename": len({t for t in departed & renamed if pricing[t] is not None}),
            "departedExitIdentityUnresolved": len(set(categories.get(ID.DEPARTED_NO_PANEL_REASON_UNRESOLVED, ()))),
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
    4. A departed symbol with no usable panel whose exit cannot be established
       from sealed evidence (a verified rename, a sealed corporate action) is
       an unresolved IDENTITY, not merely a missing price.
    """
    s, t, lin = audit["sampleSurvivorship"], audit["terminations"], audit["totalReturnLineage"]
    defects = []
    if s["noPanelDeparted"] > 0 and s["noPanelCurrent"] == 0:
        defects.append("MISSINGNESS_CONCENTRATED_IN_DEPARTED_MEMBERS")
    if s["panelNotOwnHistoryNames"] > 0:
        defects.append("PANEL_SYMBOL_NOT_MEMBER_HISTORY")
    if s["departedExitIdentityUnresolved"] > 0:
        defects.append("EXIT_IDENTITY_UNRESOLVED")
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
