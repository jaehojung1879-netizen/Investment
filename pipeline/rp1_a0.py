"""Study A A0 input measurements. No target, training or outcome operation.

TTM arithmetic, visible prefixes, acceleration and sample keys remain the
existing implementations. This module measures the registered H1/H2/H3, not
the different operating-profit LEVEL-cross in the exploratory Pattern B.
"""
from __future__ import annotations

from bisect import bisect_left
from collections import Counter, defaultdict
import datetime as dt
import math

import numpy as np
import pandas as pd

from . import experiment_workbench as W
from . import finnhub_derive as FD
from . import fundamental_acceleration as FA
from . import fundamental_acceleration_seal as FAS
from . import pit_data as PIT
from . import us_cash_profitability as CP
from . import us_multifactor_inputs as MI
from . import winner_inflection as WI
from . import winner_inflection_exploration as WE

HYPOTHESES = ("A-H1", "A-H2", "A-H3")
COMPARATORS = ("delta_operatingMargin", "earningsGrowth", "accelerationComposite")


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def exact_operating_ttm(index, key):
    """Reuse FD TTM, refusing its economically different pretax fallback."""
    year, stage = key
    deps = [key] if stage == "FY" else [key, (year - 1, "FY"), (year - 1, stage)]
    if any(k not in index for k in deps):
        return None
    if any(not index[k].get("periodEnd") or index[k]["periodEnd"] > CP.visible_day(index[k]).isoformat() for k in deps):
        return None
    if any(FD.amount(index[k], "ic", ("OperatingIncomeLoss",)) is None for k in deps):
        return None
    return FD.trailing_twelve_months(index, *key, "operatingIncome")[0]


class FilingHistory:
    """Lazy public-event prefixes, never deriving a future filing for a date."""
    def __init__(self, ticker, records, *, adapter=None):
        self.ticker = ticker
        self.adapter = adapter
        visible = adapter.visible_day if adapter else CP.visible_day
        self.records = sorted((r for r in records if visible(r)),
            key=lambda r: (visible(r), str(r.get("availableFrom")), str(r.get("id"))))
        self.days = sorted({visible(r).isoformat() for r in self.records})
        self.cache = {}

    def prefix_state(self, n):
        if n == 0:
            return {"growth": None, "eventDate": None, "uncertainEventDate": None, "periodEnd": None, "currentKey": None,
                    "fields": {}, "deltas": {}, "sourceIds": [], "publicDay": None, "reason": "NO_VISIBLE_FILING"}
        if n in self.cache:
            return self.cache[n]
        previous = self.prefix_state(n - 1)
        public = self.days[n - 1]
        available = (dt.date.fromisoformat(public) + dt.timedelta(days=1)).isoformat()
        adapter = self.adapter
        visible = adapter.visible_day if adapter else CP.visible_day
        prefix = W.filing_prefix(self.records, adapter.market if adapter else "US", available)
        assert all(visible(r).isoformat() <= public for r in prefix)
        # FD's legacy earliest-availableFrom rule predates acceptedDate. Keep
        # the first actually public row per period before calling that builder;
        # a later amendment with a backdated vendor date cannot replace it.
        first_public = {}
        for record in sorted(prefix, key=lambda r: (visible(r), str(r.get("availableFrom")), str(r.get("id")))):
            keys = adapter.index([record]) if adapter else FD.index_filings([record])
            if keys:
                first_public.setdefault(next(iter(keys)), record)
        # KR keeps its existing receipt-dated visible index: a correction can
        # affect its own public date, never an earlier signal. US keeps the
        # original first-actually-public-per-period rule exactly.
        index = adapter.index(list(prefix)) if adapter else FD.index_filings(list(first_public.values()))
        key = adapter.current_key(index) if adapter else CP.current_key(index)
        if sorted(str(r.get("id")) for r in index.values()) == previous["sourceIds"]:
            self.cache[n] = previous
            return previous  # an ignored restatement cannot restart a 26-week clock
        state = {**previous, "growth": None, "periodEnd": None, "currentKey": key,
                 "fields": {}, "deltas": {}, "publicDay": max((visible(r).isoformat() for r in index.values()), default=public),
                 "sourceIds": sorted(str(r.get("id")) for r in index.values()),
                 "reason": "INCOMPLETE_TTM_CHAIN"}
        if key is not None:
            end = adapter.period_end(key) if adapter else index[key].get("periodEnd")
            if not end or end > visible(index[key]).isoformat():
                state["reason"] = "REPORT_PERIOD_AFTER_PUBLICATION"
                state["uncertainEventDate"] = available
                self.cache[n] = state
                return state
            if adapter:
                op, prior, cash, reason = adapter.values(index, key)
                state["reason"] = reason
            else:
                op = exact_operating_ttm(index, key)
                prior = exact_operating_ttm(index, (key[0] - 1, key[1]))
                cash = FD.trailing_twelve_months(index, *key, "operatingCashFlow")[0]
            # The same positive growth-base rule used by #250; a loss base is
            # missing, never a fabricated percentage or an absolute denominator.
            growth = op / prior - 1 if finite(op) and finite(prior) and prior > 0 else None
            state.update(growth=growth, periodEnd=end)
            known_false = ((growth is not None and growth <= 0) or
                           (previous["growth"] is not None and previous["growth"] > 0) or
                           (finite(cash) and cash <= 0))
            if not known_false and (growth is None or previous["growth"] is None or not finite(cash)):
                state["uncertainEventDate"] = available
            if finite(op) and finite(prior) and prior <= 0:
                state["reason"] = "NON_POSITIVE_YOY_BASE"
            if growth is not None and finite(cash):
                state["reason"] = "AVAILABLE"
                if previous["growth"] is not None and previous["growth"] <= 0 < growth and cash > 0:
                    state["eventDate"] = available
            # Continuous controls use the existing first-public FD derivation
            # and FA delta arithmetic. A nonconsecutive public predecessor is
            # not silently turned into a quarter-on-quarter delta.
            fields = adapter.fields(index, key) if adapter else FD.derive_fields(index, *key)[0]
            state["fields"] = fields
            if previous["currentKey"] == WI.previous_period(key, adapter.market if adapter else "US"):
                cur = PIT.FundamentalRecord(self.ticker, f"{key[0]}-{key[1]}", public, fields)
                old_key = previous["currentKey"]
                old = PIT.FundamentalRecord(self.ticker, f"{old_key[0]}-{old_key[1]}", previous["publicDay"], previous["fields"])
                state["deltas"] = FA.compute_deltas(cur, old)
            elif previous["currentKey"] == key:
                state["deltas"] = previous["deltas"]
        self.cache[n] = state
        return state

    def at(self, day):
        state = self.prefix_state(bisect_left(self.days, day))
        result = {**state, "flag": None}
        end = state["periodEnd"]
        if end and (dt.date.fromisoformat(day) - dt.date.fromisoformat(end)).days > 180:
            return {**result, "fields": {}, "deltas": {}, "reason": "REPORT_STALE_OVER_180_DAYS"}
        event = state["eventDate"]
        active = bool(event and 0 <= (dt.date.fromisoformat(day) - dt.date.fromisoformat(event)).days <= 26 * 7)
        # Once observed, the registered event lasts 26 weeks. A later fresh
        # filing with an incomplete TTM chain cannot erase that known event;
        # it still withholds its own missing continuous controls. Invalid
        # publication periods and stale reports remain blocked above/below.
        retained = self.adapter.retention_reasons if self.adapter else ("AVAILABLE", "INCOMPLETE_TTM_CHAIN", "NON_POSITIVE_YOY_BASE")
        if active and end and state["reason"] in retained:
            return {**result, "flag": True, "reason": ("AVAILABLE" if state["reason"] == "AVAILABLE"
                                                       else "KNOWN_EVENT_IN_26_WEEK_RETENTION")}
        if state["reason"] != "AVAILABLE":
            return result
        result["flag"] = active
        unknown = state["uncertainEventDate"]
        if not result["flag"] and unknown and 0 <= (dt.date.fromisoformat(day) - dt.date.fromisoformat(unknown)).days <= 26 * 7:
            result.update(flag=None, reason="EVENT_HISTORY_UNRESOLVED")
        return result


class PastPrices:
    """Use the existing PIT view to enforce end <= signal at every lookup."""
    def __init__(self, frames, calendar, events=None, *, benchmark="SPY"):
        self.frames, self.calendar = frames, calendar
        self.benchmark = benchmark
        self.events = events
        self.forward_reads = 0

    def window(self, ticker, day, length):
        stamps = self.calendar[self.calendar <= pd.Timestamp(day)][-length:]
        if len(stamps) != length or ticker not in self.frames:
            return None
        frame = self.frames[ticker].loc[:day].reindex(stamps)
        PIT.assert_no_future(frame, day, "A0 past-only input")
        if "Close" not in frame or not np.isfinite(frame.Close).all() or not (frame.Close > 0).all():
            return None
        return frame

    def features(self, ticker, day):
        stock, spy = self.window(ticker, day, 127), self.window(self.benchmark, day, 127)
        if stock is not None and ("Volume" not in stock or not np.isfinite(stock.Volume).all() or not (stock.Volume > 0).all()):
            stock = None
        relative = (float(stock.Close.iloc[-1] / stock.Close.iloc[0] - spy.Close.iloc[-1] / spy.Close.iloc[0])
                    if stock is not None and spy is not None else None)
        size = None
        # Same proxy as the existing phase-3 readiness audit: median AS-TRADED
        # dollars over 63 sessions, withheld across a split. Multiplying the
        # replay total-return index by volume would rank a different quantity.
        stamps = self.calendar[self.calendar <= pd.Timestamp(day)][-63:]
        if self.events is not None and ticker in self.frames and len(stamps) == 63:
            own = self.frames[ticker].loc[:day].dropna(subset=["Close"])
            events = [e for e in self.events.get(ticker, ()) if e[0] <= day]
            split_inside = any(stamps[0] < pd.Timestamp(e[0]) <= stamps[-1] and e[2] and e[2] != 1 for e in events)
            if not split_inside and "Volume" in own and np.isfinite(own.Close).all() and (own.Close > 0).all():
                native = pd.Series(MI.as_traded_from_total_return(own.index, own.Close.to_numpy(), events), index=own.index)
                values = native.reindex(stamps) * own.Volume.reindex(stamps)
                values = values[np.isfinite(values) & (values > 0)]
                if len(values) >= 63 // 2:  # inherited ADV_SESSIONS // 2
                    size = float(values.median())
        return {"relative126": relative, "size63": size,
                "basis": "INHERITED_REPLAY_RECONSTRUCTED_BASIS_NOT_WP0_VERIFIED"}


def h2(h1, relative):
    # A missing financial observation is not evidence that the event is absent.
    return bool(h1 and relative > 0) if h1 is not None and finite(relative) else None


def h3(rows, *, size_field="size63"):
    """Sector leaders = top 3 by prior 63-session traded value; no new factor.

    Missing peer/leader inputs and a tied top-3 boundary abstain. Removing the
    missing names before ranking would silently choose a different leader set.
    """
    groups = defaultdict(list)
    for row in rows:
        if row.get("sector"):
            groups[row["sector"]].append(row)
    leaders, reasons = {}, {}
    for sector, group in groups.items():
        if len(group) < 3 or any(not finite(r.get(size_field)) or not finite(r.get("relative126")) for r in group):
            reasons[sector] = "INDUSTRY_PEER_INPUT_UNRESOLVED"
            continue
        ordered = sorted(group, key=lambda r: (-r[size_field], r["ticker"]))
        if len(ordered) > 3 and ordered[2][size_field] == ordered[3][size_field]:
            reasons[sector] = "LEADER_BOUNDARY_TIE_UNRESOLVED"
            continue
        leaders[sector] = float(np.mean([r["relative126"] for r in ordered[:3]]))
    # The registered comparison is across sectors. Unknown sectors cannot be
    # dropped to manufacture a top tercile among the survivors.
    cutoff = float(pd.Series(leaders).quantile(2 / 3)) if len(leaders) >= 3 and not reasons else None
    output = {}
    for row in rows:
        sector = row.get("sector")
        cause = reasons.get(sector) or ("INDUSTRY_CROSS_SECTION_UNRESOLVED" if cutoff is None else None)
        if not sector:
            cause = "INDUSTRY_UNRESOLVED"
        median = float(np.median([r["relative126"] for r in groups[sector]])) if not cause else None
        output[row["ticker"]] = (None, cause) if cause else (
            bool(leaders[sector] >= cutoff and row["relative126"] <= median), "AVAILABLE")
    return output


def acceleration_controls(rows, *, market="US"):
    """Existing composite definition; no discovery/result module imported."""
    frame = pd.DataFrame([{**r, "region": market, "dataSufficient": sum(finite(r.get(k)) for k in (
        "deltaRoe", "deltaOperatingMargin", "deltaProfitMargin", "deltaEarningsGrowth")) >= FA.MIN_PRIMARY_FIELDS} for r in rows])
    if frame.empty:
        return {}
    for key in ("deltaRoe", "deltaOperatingMargin", "deltaProfitMargin", "deltaEarningsGrowth"):
        if key not in frame:
            frame[key] = np.nan
    scored = FAS.score_candidate_rows(frame)
    return {r.ticker: float(r.compositeZ) if finite(r.compositeZ) else None for r in scored.itertuples()}


def rank_biserial(flags, values):
    pairs = [(f, v) for f, v in zip(flags, values) if f is not None and finite(v)]
    if not pairs or len({f for f, _ in pairs}) != 2:
        return None
    f = pd.Series([x[0] for x in pairs], dtype=bool)
    ranks = pd.Series([x[1] for x in pairs]).rank(method="average")
    n1, n0 = int(f.sum()), int((~f).sum())
    u = float(ranks[f].sum() - n1 * (n1 + 1) / 2)
    return 2 * u / (n1 * n0) - 1


def terciles(values):
    known = pd.Series({k: v for k, v in values.items() if finite(v)}, dtype=float)
    if known.empty:
        return {}
    a, b = known.quantile([1 / 3, 2 / 3])
    return {k: 0 if v <= a else 1 if v <= b else 2 for k, v in known.items()}


def population_audit(observations, departed_symbols):
    """Retrospective WP2 departure attribution only; never an event input.

    Departure means absence from the last PRESERVED index snapshot, not
    delisting. Identity holds remain in each group's full denominator.
    """
    groups = defaultdict(lambda: {"population": 0, "eligible": 0,
        "hypotheses": {h: Counter() for h in HYPOTHESES}})
    for row in observations:
        cells = {c.name: c.value for c in row.cells}
        labels = ("identity:" + row.identity_status,
                  "index:EXITED" if row.ticker in departed_symbols else "index:LAST_PRESERVED_SNAPSHOT_MEMBER")
        for label in labels:
            group = groups[label]
            group["population"] += 1
            if row.investable is not True:
                continue
            group["eligible"] += 1
            for h in HYPOTHESES:
                flag = cells.get("financial." + h.replace("-", "_"))
                group["hypotheses"][h].update(measured=int(flag is not None),
                    missing=int(flag is None), events=int(flag == 1))
    return {"definition": "WP2: not in last preserved snapshot; not proof of delisting; retrospective audit only",
            "groups": {key: value for key, value in sorted(groups.items())}}


def measure(observations, *, missing_details=None, market="US", comparators=COMPARATORS, size_field="risk.size63"):
    """Common Observation/Cell inputs only; target tables cannot be passed in."""
    population_sha = WE.validate_panel(observations)
    dates = defaultdict(list)
    for row in observations:
        if market not in ("KR", "US") or row.key.market != market or row.identity_status not in ("PROVISIONAL", "UNRESOLVED"):
            raise ValueError("WP2_PROVISIONAL_POPULATION_REQUIRED")
        dates[row.key.signal_date].append(row)
    aggregate = {h: Counter() for h in HYPOTHESES}
    missing = {h: Counter() for h in HYPOTHESES}
    eligibility_reasons = Counter(o.eligibility_reason for o in observations if o.investable is not True)
    identity_statuses = Counter(o.identity_status for o in observations)
    daily, correlations, correlation_counts = [], [], []
    strata = {h: Counter() for h in HYPOTHESES}
    for day, members in sorted(dates.items()):
        eligible = [o for o in members if o.investable is True]
        cells = {o.key.sample_id: {c.name: c for c in o.cells} for o in eligible}
        def value(o, name):
            cell = cells[o.key.sample_id].get(name)
            return cell.value if cell else None
        sizes = terciles({o.key.sample_id: value(o, size_field) for o in eligible})
        momentum = terciles({o.key.sample_id: value(o, "price.relative126") for o in eligible})
        record = {"date": day, "population": len(members), "eligible": len(eligible), "hypotheses": {}}
        for h in HYPOTHESES:
            name = "financial." + h.replace("-", "_")
            if any(value(o, name) is not None and value(o, name) not in (0, 1) for o in eligible):
                raise ValueError("BINARY_EVENT_REQUIRED")
            measured = [o for o in eligible if value(o, name) is not None]
            events = [o for o in measured if value(o, name) == 1]
            aggregate[h].update(population=len(members), eligible=len(eligible), measured=len(measured), events=len(events))
            for o in eligible:
                if value(o, name) is None:
                    cell = cells[o.key.sample_id].get(name)
                    detail = (missing_details or {}).get(o.key.sample_id, {}).get(h)
                    missing[h][detail or (cell.missing_reason if cell else "NO_SOURCE")] += 1
            record["hypotheses"][h] = {"measured": len(measured), "events": len(events) if measured else None,
                "prevalence": len(events) / len(measured) if measured else None}
            date_strata = Counter()
            for o in measured:
                sid = o.key.sample_id
                components = (o.industry_id, sizes.get(sid)) + (() if h == "A-H2" else (momentum.get(sid),))
                label = "|".join(str(x) for x in components) if all(x is not None for x in components) else "STRATUM_UNRESOLVED"
                cell_key = label + (":S1" if value(o, name) == 1 else ":S0")
                strata[h][cell_key] += 1
                date_strata[cell_key] += 1
            record["hypotheses"][h]["strata"] = dict(sorted(date_strata.items()))
        flags = [value(o, "financial.A_H1") for o in eligible]
        correlations.append({"date": day, **{name: rank_biserial(flags, [value(o, "financial." + name) for o in eligible])
                                           for name in comparators}})
        denominators = {"date": day}
        for name in comparators:
            pairs = [(f, value(o, "financial." + name)) for f, o in zip(flags, eligible)
                     if f is not None and finite(value(o, "financial." + name))]
            denominators[name] = {"pairs": len(pairs), "S1": sum(f == 1 for f, _ in pairs), "S0": sum(f == 0 for f, _ in pairs)}
        correlation_counts.append(denominators)
        daily.append(record)
    hypotheses = {}
    for h, counts in aggregate.items():
        measured, events, eligible = counts["measured"], counts["events"], counts["eligible"]
        prevalence = events / measured if measured else None
        coverage = measured / eligible if eligible else None
        event_counts = [d["hypotheses"][h]["events"] for d in daily]
        gates = {"prevalence": None if prevalence is None else .03 <= prevalence <= .50,
                 "measurability": None if coverage is None else coverage >= .60,
                 "namesPerDate": None if not event_counts or any(n is None for n in event_counts) else min(event_counts) >= (5 if market == "KR" else 10),
                 "mde": None}
        # Per-date correlations are exposed without inventing an unregistered
        # averaging/maximum rule. That aggregation needs an explicit contract.
        if h == "A-H1":
            gates["distinctness"] = None
        status = "PROSPECTIVE_ONLY" if False in gates.values() else "BLOCKED/UNRESOLVED"
        hypotheses[h] = {**dict(counts), "prevalence": prevalence, "measurability": coverage, "gates": gates,
            "verdict": status, "missing": dict(sorted(missing[h].items())), "strata": dict(sorted(strata[h].items())),
            "mde": {"status": "MDE_UNRESOLVED", "annualPercentagePoints": None,
                    "reason": "No outcome-free identified economic-scale variance of the registered contrast; synthetic units do not supply it."}}
    return {"status": "A0_INPUT_MEASUREMENT", "populationSha256": population_sha, "hypotheses": hypotheses,
        "eligibilityReasons": dict(sorted(eligibility_reasons.items())), "identityStatusCensus": dict(sorted(identity_statuses.items())),
        "byDate": daily, "h1RankBiserialByDate": correlations, "h1CorrelationDenominatorsByDate": correlation_counts,
        "primaryHorizon": 252,
        "contractClarifications": ["The document specifies datewise |rho| <= 0.70 but no cross-date correlation aggregation rule; no invented PASS or DROP.",
            "Non-positive operating-income growth bases are withheld, following the existing growth adapter; no unapproved loss-base percentage convention.",
            "Synthetic standardized power is not a monetary MDE; actual event geometry alone cannot identify outcome variance."],
        "accessCounters": {"outcomeReads": 0, "forwardPriceReads": 0, "labelReads": 0, "modelFits": 0, "locksCreated": 0},
        "historicalExecutionAuthorized": False, "a1Admission": "NO_GO"}
