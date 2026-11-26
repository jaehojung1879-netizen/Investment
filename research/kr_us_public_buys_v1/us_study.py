"""Run the frozen Form 4 purchase design on the original US weekly axis."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import json
from pathlib import Path
import pickle

import exchange_calendars as xc
import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

from research.kr_us_exposure_preserving_v1 import nav
from research.kr_us_replica_filter_v1 import us as frozen
from research.kr_us_strategy_batch_v1 import common, us as batch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
HORIZONS = (126, 252)
MARKET_TIMEZONE = "America/New_York"
OPEN = "CONFIRMED_OPEN_MARKET"
SOURCE_MISSING = "SOURCE_WINDOW_UNAVAILABLE"
STOCK_WEIGHT = .20


def cik(value):
    s = str(value).strip()
    return str(int(s)) if s.isdigit() and int(s) > 0 else None


def aliases(ticker):
    return "".join(c for c in str(ticker).upper() if c.isalnum())


def read_intervals(path):
    data = json.loads(path.read_text())
    intervals = [(pd.Timestamp(x["from"]).date(), pd.Timestamp(x["through"]).date(),
                  None if "issuerCIKs" not in x else frozenset(cik(t) for t in x["issuerCIKs"]))
                 for x in data["coverageIntervals"]]
    if any(first > last for first, last, _ in intervals):
        raise ValueError("Invalid official source coverage interval")
    return data, intervals


def covered_issuers(start, end, intervals):
    """Intersect issuer coverage for every calendar day in a signal window."""
    eligible = None
    for d in pd.date_range(start, end):
        which = [ids for first, last, ids in intervals if first <= d.date() <= last]
        if not which:
            return frozenset()
        if all(ids is not None for ids in which):
            union = frozenset().union(*which)
            eligible = union if eligible is None else eligible & union
    return eligible


def read_events(path):
    required = {"issuerCIK", "ticker", "accession", "transactionDate", "availableAt", "status"}
    extra = {"invalidatedAt", "blocksControl", "securityTitle", "quantity", "price", "eventId"}
    e = pd.read_csv(path, dtype=str, usecols=lambda c: c in required | extra, low_memory=False)
    if not required <= set(e):
        raise ValueError(f"Missing event fields: {sorted(required - set(e))}")
    e["issuerCIK"] = e.issuerCIK.map(cik)
    e["at"] = pd.to_datetime(e.availableAt, utc=True, format="mixed", errors="coerce")
    e["until"] = pd.to_datetime(e.get("invalidatedAt", pd.Series(pd.NaT, index=e.index)),
                                utc=True, format="mixed", errors="coerce")
    e["tradeDate"] = pd.to_datetime(e.transactionDate, format="mixed", errors="coerce").dt.normalize()
    local_day = e["at"].dt.tz_convert(MARKET_TIMEZONE).dt.tz_localize(None).dt.normalize()
    e["symbol"] = e.ticker.map(aliases)
    primary = e.status.eq(OPEN)
    legitimate = (e.issuerCIK.notna() & e.tradeDate.notna() & e["at"].notna()
                  & e.tradeDate.le(local_day))
    e.loc[primary & ~legitimate, "status"] = "INDETERMINATE_EVENT_FIELDS"
    duplicates = economic_collisions(e)
    e.loc[duplicates, "status"] = "INDETERMINATE_LATER_IDENTICAL_ECONOMICS"
    uncertainty = e.status.str.contains("UNKNOWN|UNCONFIRMED|INDETERMINATE|AMBIGU|UNRESOLVED", na=False)
    if "blocksControl" in e:
        uncertainty |= e.blocksControl.astype(str).str.lower().isin(("1", "true"))
    e["blocksControl"] = uncertainty
    return e


def economic_collisions(e):
    """Quarantine a later report indistinguishable by issuer, class, date and cash terms."""
    fields = ["issuerCIK", "tradeDate", "securityTitle", "quantity", "price"]
    if not set(fields + ["eventId"]) <= set(e):
        return []
    paid = e.loc[e.status.eq(OPEN)].dropna(subset=fields).copy()
    paid["securityTitle"] = paid.securityTitle.map(aliases)
    paid[["quantity", "price"]] = paid[["quantity", "price"]].apply(pd.to_numeric)
    repeated = paid.loc[paid.duplicated(fields, keep=False)]
    later = []
    for _, rows in repeated.groupby(fields, sort=False):
        first_by_time = {}
        for _, row in rows.sort_values(["at", "accession", "eventId"]).iterrows():
            if any(ref.accession != row.accession and ref["at"] < row["at"]
                   and (pd.isna(ref["until"]) or ref["until"] > row["at"]) for ref in first_by_time.values()):
                later.append(row.name)
            else:
                first_by_time[row.accession] = row
    return later


def dated_issuer_map(features, close, dates, private):
    """Reconstruct CIKs from membership and the original date-visible CIK sets."""
    f = frozen.features
    p = f.PILOT
    member = f.RAF.MembershipSnapshots(json.loads(gzip.decompress((ROOT / p.MEMBERSHIP).read_bytes()))["snapshots"])
    sector = f.CA.SectorBook(json.loads(gzip.decompress((ROOT / p.SECTORS).read_bytes()))["snapshots"])
    identity = json.loads((ROOT / p.IDENTITY).read_text())["regions"]["US"]["identity"]
    malformed = {k.upper(): v["resolvedTo"] for k, v in identity["malformed"].items() if v.get("resolvedTo")}
    renamed = {k: v["pricedBy"] for k, v in identity["renames"].items() if v.get("pricedBy")}
    for old, new in f.verified_class_links(close).items():
        renamed.setdefault(old, new)
    priced = {aliases(t): t for t in close.columns}
    history = {}
    filings = private / "filings.pkl"
    wanted = set(features.loc[features.identity.eq("PIT_SINGLE_CIK"), "ticker"])
    if filings.is_file() and wanted:
        with filings.open("rb") as stream:
            raw = pickle.load(stream)["raw"]
        for name in wanted:
            history[name] = sorted((visible.isoformat(), owner) for row in raw.get(name, ())
                                   if (visible := f.CP.visible_day(row)) is not None
                                   if (owner := cik(row.get("cik"))) is not None)
    result = {}
    for day in dates:
        text = day.date().isoformat()
        snapshot = member.on(text)
        mapped = defaultdict(set)
        for symbol in snapshot["members"]:
            canonical = malformed.get(symbol.upper(), symbol)
            canonical = renamed.get(canonical, canonical)
            canonical = priced.get(aliases(canonical), canonical)
            owner = cik(sector.cik(snapshot, symbol))
            if owner:
                mapped[canonical].add(owner)
        result[day] = {t: next(iter(ids)) for t, ids in mapped.items() if len(ids) == 1}
    for row in features.loc[features.identity.eq("PIT_SINGLE_CIK"), ["date", "ticker"]].itertuples(index=False):
        text = row.date.date().isoformat()
        owners = {owner for visible, owner in history.get(row.ticker, ()) if visible < text}
        if len(owners) == 1:
            result[row.date][row.ticker] = next(iter(owners))
    return result


def match(frame, chosen, control, adjusted=False):
    """First maximize the number assigned, then minimize total prespecified distance."""
    columns = sorted(control)
    chosen = tuple(sorted(chosen))
    if not chosen:
        return {}, []
    left, right = frame.loc[list(chosen)], frame.loc[columns]
    ratio = right.marketCap.to_numpy()[None, :] / left.marketCap.to_numpy()[:, None]
    same = left.sector.to_numpy()[:, None] == right.sector.to_numpy()[None, :]
    valid = same & np.isfinite(ratio) & (ratio >= .5) & (ratio <= 2)
    distance = np.abs(np.log(ratio))
    caliper = valid.copy()
    if adjusted:
        for col in ("valueRank", "trendRank"):
            gap = np.abs(left[col].to_numpy()[:, None] - right[col].to_numpy()[None, :])
            valid &= np.isfinite(gap) & (gap <= .25)
            distance += gap
        a, b = left.business.to_numpy(dtype=float), right.business.to_numpy(dtype=float)
        valid &= np.isfinite(a[:, None]) & (a[:, None] == b[None, :])
    n, m = valid.shape
    dummy = 2 * (n + 1)
    costs = np.full((n, m + n), float(dummy))
    costs[:, :m] = np.where(valid, distance, 2 * dummy)
    ixs, jxs = linear_sum_assignment(costs)
    paired, audit = {}, []
    for i, j in zip(ixs, jxs, strict=True):
        name = chosen[i]
        row = {"ticker": name, "sector": left.sector.iloc[i], "method": "adjusted" if adjusted else "base",
               "sameSector": int(same[i].sum()), "withinCap": int(caliper[i].sum()),
               "withinAll": int(valid[i].sum())}
        if j < m:
            assert valid[i, j]
            paired[name] = columns[j]
            row.update(peer=columns[j], capRatio=float(ratio[i, j]), reason="MATCHED",
                       valueDifference=left.valueRank.iloc[i]-right.valueRank.iloc[j],
                       trendDifference=left.trendRank.iloc[i]-right.trendRank.iloc[j],
                       businessDifference=left.business.iloc[i]-right.business.iloc[j])
        else:
            reason = ("NO_SAME_SECTOR" if not same[i].any() else
                      "NO_CAP_PEER" if not caliper[i].any() else
                      "NO_SIGNAL_SIMILAR_PEER" if not valid[i].any() else "PEER_CONTENTION")
            row.update(peer=None, capRatio=None, reason=reason)
        audit.append(row)
    return (paired if len(paired) == n else None), audit


def apply_caps(features, path):
    if path is None or not path.is_file():
        return
    overlay = pd.read_csv(path, parse_dates=["date"]).set_index(["date", "ticker"])
    if not overlay.index.is_unique or not overlay.correctedMarketCap.gt(0).all():
        raise ValueError("Invalid verified cap overlay")
    keyed = features.set_index(["date", "ticker"]).index
    known = keyed.isin(overlay.index)
    if int(known.sum()) != len(overlay):
        raise ValueError("A corrected cap maps outside the original features")
    features.loc[known, "marketCap"] = overlay.correctedMarketCap.reindex(keyed[known]).to_numpy()


def build_books(features, close, dates, events, intervals, ids):
    exchange = xc.get_calendar("XNYS", start=str(dates[0].date()), end=str(close.index[-1].date()))
    decisions = pd.Series([exchange.session_close(d) for d in dates], index=dates)
    frames = {d: g for d, g in features.groupby("date", sort=True)}
    audit, weekly, attribution, all_schedules = [], [], [], {}
    for previous, d in zip(dates[:-1], dates[1:], strict=True):
        lower, upper = decisions[previous], decisions[d]
        scope = covered_issuers(previous.date(), d.date(), intervals)
        if scope == frozenset():
            weekly.append({"date": d, "status": SOURCE_MISSING})
            continue
        g = frames[d]
        eligible = (g.identity.isin(frozen.VALID_ID) & g.marketCap.gt(0) & g.sector.notna()
                    & ~g.sector.eq("UNCLASSIFIED") & g.ticker.map(close.loc[d]).gt(0))
        frame = g.loc[eligible].copy().set_index("ticker")
        frame["issuerCIK"] = frame.index.map(ids[d].get)
        mapped = frame.issuerCIK.notna()
        eligible_cik = frame.issuerCIK.isin(scope) if scope is not None else mapped
        eligible_frame = frame.loc[mapped & eligible_cik].copy()
        observed_ids = set(eligible_frame.issuerCIK)
        in_window = events["at"].gt(lower) & events["at"].le(upper)
        active = events.loc[in_window & (events["until"].isna() | events["until"].gt(upper))]
        cand = active.loc[active.status.eq(OPEN) & active.issuerCIK.isin(observed_ids)]
        exact = {(owner, aliases(ticker)): ticker for ticker, owner in eligible_frame.issuerCIK.items()}
        multiple_classes = set(frame.loc[frame.issuerCIK.duplicated(keep=False), "issuerCIK"].dropna())
        # Symbol+dated CIK protects against ticker reuse and decisions on a different share class.
        # A ticker header alone cannot distinguish multiple priced common classes of the issuer.
        latest = {}
        for r in cand.sort_values(["at", "accession"], ascending=[False, True]).itertuples(index=False):
            ticker = exact.get((r.issuerCIK, r.symbol))
            if ticker is not None and r.issuerCIK not in multiple_classes and r.issuerCIK not in latest:
                latest[r.issuerCIK] = (ticker, r.at, r.accession)
        # Lexicographic ticker resolves a same-time tie.
        ranking = sorted(latest.values(), key=lambda r: (-r[1].value, r[0]))
        chosen = tuple(r[0] for r in ranking[:5])
        affected = set(active.loc[active.status.eq(OPEN) | active.blocksControl, "issuerCIK"])
        controls = eligible_frame.index[~eligible_frame.issuerCIK.isin(affected)]
        complete = frozen.ev.common(g)
        scored = frozen.ev.score(complete) if len(complete) else complete
        for col, name in (("WITHIN_SECTOR_VALUE", "valueRank"), ("PRICE", "trendRank")):
            value = scored[col] if col in scored else pd.Series(dtype=float)
            eligible_frame[name] = value.groupby(scored.sector).rank(pct=True) if len(value) else np.nan
        eligible_frame["business"] = scored.confirmed.astype(float) if "confirmed" in scored else np.nan
        base, base_rows = match(eligible_frame, chosen, controls)
        adjusted, adjusted_rows = match(eligible_frame, chosen, controls, adjusted=True)
        audit.extend({"date": d, **r} for r in (*base_rows, *adjusted_rows))
        all_schedules[d] = (chosen, base, adjusted)
        weekly.append({"date": d, "decisionUtc": upper, "status": "MEASURED_SOURCE" if len(eligible_frame) else "NO_COVERED_ELIGIBLE_ISSUERS",
                       "candidates": len(frame), "mapped": int(mapped.sum()), "coveredCandidates": len(eligible_frame),
                       "activeOpenRows": int(active.status.eq(OPEN).sum()), "activeUnknownRows": int(active.blocksControl.sum()),
                       "mappedEligibleOpenRows": len(cand),
                       "openRowsMulticlassUnresolved": int(cand.issuerCIK.isin(multiple_classes).sum()),
                       "openRowsWithoutExactTicker": sum((r.issuerCIK, r.symbol) not in exact
                                                        for r in cand.itertuples(index=False)),
                       "uniqueOpenIssuers": len(ranking),
                       "selected": len(chosen), "baseMatched": base is not None, "adjustedMatched": adjusted is not None})
        attribution.extend({"date": d, "rank": i, "ticker": t, "availableAt": at, "accession": a}
                           for i, (t, at, a) in enumerate(ranking[:5], 1))
        if eligible_frame.empty:
            del all_schedules[d]
    return all_schedules, pd.DataFrame(weekly), pd.DataFrame(audit), pd.DataFrame(attribution)


def portfolio(book):
    return {"SPY": 1-STOCK_WEIGHT, **{name: STOCK_WEIGHT/len(book) for name in book}} if book else {"SPY": 1.}


def payoff(asset, names):
    w = pd.Series(portfolio(names))
    r = asset.reindex(w.index)
    return float(r @ w) if r.notna().all() else np.nan


def return_rows(schedules, dates, close, qqq, h):
    assets, calendar = frozen.endpoint_returns(close, dates, h)
    net = frozen.ev.net(assets)
    qgross, _ = frozen.endpoint_returns(qqq.rename("QQQ").to_frame(), dates, h)
    rows, contributions = [], []
    for day, asset in net.iterrows():
        e, z = calendar.loc[day]
        row = {"date": day, "entry": e, "exit": z}
        if day not in schedules or pd.isna(z):
            row["status"] = SOURCE_MISSING if day not in schedules else "NOT_MATURE"
            rows.append(row)
            continue
        names, base, adjusted = schedules[day]
        signal = payoff(asset, names)
        peer = payoff(asset, base.values()) if base is not None else np.nan
        control = payoff(asset, adjusted.values()) if adjusted is not None else np.nan
        spy = asset.SPY
        q = frozen.ev.net(qgross.at[day, "QQQ"])
        row.update(status="MEASURED" if np.isfinite(signal) else "UNRESOLVED_SELECTED_ENDPOINT",
                   stocks=len(names), etf=spy, qqq=q, selected=signal, peer=peer, adjusted=control,
                   selection=signal-peer, replacement=peer-spy, total=signal-spy,
                   adjustedSelection=signal-control, adjustedReplacement=control-spy, vsQQQ=signal-q,
                   missingSelected="|".join(t for t in names if pd.isna(asset.get(t))),
                   missingPeer="|".join(t for t in base.values() if pd.isna(asset.get(t))) if base is not None else "",
                   missingAdjusted="|".join(t for t in adjusted.values() if pd.isna(asset.get(t))) if adjusted is not None else "")
        if np.isfinite(peer) and np.isfinite(signal):
            assert abs(row["total"]-row["selection"]-row["replacement"]) < 1e-12
        if np.isfinite(control) and np.isfinite(signal):
            assert abs(row["total"]-row["adjustedSelection"]-row["adjustedReplacement"]) < 1e-12
        if names and np.isfinite(signal):
            contributions.extend({"date": day, "entryYear": e.year, "ticker": t, "weight": STOCK_WEIGHT/len(names),
                                  "totalContribution": (asset[t]-spy)*STOCK_WEIGHT/len(names),
                                  "selectionContribution": (asset[t]-asset[base[t]])*STOCK_WEIGHT/len(names)
                                  if base is not None and np.isfinite(peer) else np.nan}
                                 for t in names)
        rows.append(row)
    cohort = pd.DataFrame(rows).set_index("date")
    metric_fields = ("stocks", "etf", "qqq", "selected", "peer", "adjusted", "selection", "replacement",
                     "total", "adjustedSelection", "adjustedReplacement", "vsQQQ")
    for field in set(metric_fields) - set(cohort):
        cohort[field] = np.nan
    return cohort, pd.DataFrame(contributions)


def summarize(cohort, contributions, h):
    def measures(mask):
        return {k: common.stats(cohort[k], h, mask) for k in
                ("etf", "qqq", "selected", "peer", "adjusted", "selection", "replacement",
                 "total", "adjustedSelection", "adjustedReplacement", "vsQQQ")}

    active = cohort.stocks.gt(0)
    matched = active & cohort.selection.notna()
    both = matched & cohort.adjustedSelection.notna()
    stats = {"own": measures(cohort.total.notna()), "active": measures(active),
             "paired": measures(matched), "adjusted": measures(active & cohort.adjustedSelection.notna()),
             "bothMatches": measures(both), "zeroStockMature": int(cohort.stocks.eq(0).sum()),
             "statuses": cohort.status.value_counts().to_dict()}
    stats["adjustedMinusBase"] = common.stats(cohort.adjustedSelection-cohort.selection, h, both)
    if not contributions.empty:
        for key, field in (("ETF", "total"), ("selection", "selection")):
            support = cohort.total.notna() if field == "total" else matched
            col = field + "Contribution"
            leg = contributions.dropna(subset=[col])
            if leg.empty:
                continue
            top_name = leg.groupby("ticker")[col].sum().idxmax()
            top_one = leg.loc[leg.ticker.eq(top_name)].groupby("date")[col].sum()
            top_year = int(leg.groupby("entryYear")[col].sum().idxmax())
            stats[key+"Sensitivity"] = {
                "maxName": top_name, "maxYear": top_year,
                "minusNameContribution": common.stats(cohort[field]-top_one.reindex(cohort.index, fill_value=0), h, support),
                "noNameDates": common.stats(cohort[field], h, support & ~cohort.index.isin(top_one.index)),
                "noYear": common.stats(cohort[field], h, support & cohort.entry.dt.year.ne(top_year)),
            }
    return stats


def covered_runs(dates, schedules):
    groups, current = [], []
    for d in dates:
        if d in schedules:
            current.append(d)
        elif current:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def nav_windows(schedules, dates, close, qqq, out):
    result = {}
    positions = {d: close.index.get_loc(d) for d in dates}
    for weeks in covered_runs(dates, schedules):
        first, last = weeks[0], weeks[-1]
        start = positions[first]
        n = dates.get_loc(last)
        end = positions[dates[n+1]] if n+1 < len(dates) else len(close.index)-1
        relevant = {t for d in weeks for book in schedules[d] if book is not None for t in book}
        # The control dict iterates the selected names. Its values contain the peers.
        relevant.update(p for d in weeks if schedules[d][1] is not None for p in schedules[d][1].values())
        price = close.iloc[start:end+1].loc[:, sorted(relevant | {"SPY"})].assign(QQQ=qqq)
        start_exec = price.index[1]
        benchmark, _ = nav.us_account(price, {start_exec: {"SPY": 1.}})
        auxiliary, _ = nav.us_account(price, {start_exec: {"QQQ": 1.}})
        key = f"{first.date()}_to_{last.date()}"
        result[key] = {"weeks": len(weeks), "windowEnd": price.index[-1], "shortWindow": len(weeks) < 52}
        for interval in (26, 52):
            paths = {"SPY": benchmark.nav, "QQQ": auxiliary.nav}
            by_name = {}
            for name in ("selected", "pairedSelected", "pairedControl"):
                accounts, diagnostics = [], []
                try:
                    for phase in range(interval):
                        orders = {start_exec: {"SPY": 1.}}
                        for day in weeks[phase::interval]:
                            names, peers, _ = schedules[day]
                            if name == "pairedControl":
                                names = tuple(peers.values()) if peers is not None else ()
                            elif name == "pairedSelected" and peers is None:
                                names = ()
                            orders[close.index[positions[day]+1]] = portfolio(names)
                        account, diagnostics_row = nav.us_account(price, orders)
                        accounts.append(account)
                        diagnostics.append(diagnostics_row)
                except (ValueError, KeyError) as exc:
                    by_name[name] = {"status": "NOT_ESTIMABLE", "reason": str(exc)}
                    continue
                avg = sum(accounts)/interval
                paths[name] = avg.nav
                m = common.nav_window(avg.nav, benchmark.nav)
                exited = sum(a[0] for a in diagnostics)
                held = sum(a[1] for a in diagnostics)
                m.update(status="MEASURED", oneWayTurnoverPerYear=float(avg.twoWayTurnover.sum()/2/m["years"]),
                         bookCostPerYear=float(avg.costInitialCapital.sum()/m["years"]),
                         nameExitShare=exited/held if held else None,
                         meanRetainedResetL1=float(np.mean([v for a in diagnostics for v in a[2]])) if held else None,
                         qqqComparison=common.nav_window(avg.nav, auxiliary.nav))
                by_name[name] = m
            reference = common.nav_window(benchmark.nav, benchmark.nav)
            reference["oneWayTurnoverPerYear"] = float(benchmark.twoWayTurnover.sum()/2/reference["years"])
            by_name["SPY"] = reference
            result[key][f"L{interval}"] = by_name
            write_csv(out / f"nav-{key}-L{interval}.csv.gz", pd.DataFrame(paths).reset_index(names="date"))
    return result


def write_csv(path, frame):
    frame.to_csv(path, index=False, compression={"method": "gzip", "mtime": 0})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private", type=Path, default=Path("/workspace/batch-inputs/us"))
    parser.add_argument("--inputs", type=Path, default=Path("/workspace/exposure-inputs/us"))
    parser.add_argument("--out", type=Path, default=HERE / "results/US")
    parser.add_argument("--cap-corrections", type=Path, default=HERE / "results/WAT/corrected-caps.csv")
    a = parser.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    event_path, source_path = a.out / "events.csv.gz", a.out / "events-coverage.json"
    if not (event_path.is_file() and source_path.is_file()):
        batch.save(a.out / "summary.json", {"status": SOURCE_MISSING, "missing": [p.name for p in (event_path, source_path) if not p.is_file()]})
        return
    source, intervals = read_intervals(source_path)
    if source.get("eventsFileSha256") and frozen.sha(event_path) != source["eventsFileSha256"]:
        raise ValueError("SEC normalized event hash differs from its receipt")
    events = read_events(event_path)
    payload, close, hashes = frozen.load_frozen(a.private, a.inputs)
    _, _, qqq, _ = frozen.ev.load(a.private)
    dates = payload["dates"]
    feats = pd.read_pickle(a.private / "features.pkl")
    feats["date"] = pd.to_datetime(feats.date)
    feats = feats.loc[feats.date.isin(dates)].copy()
    apply_caps(feats, a.cap_corrections)
    ids = dated_issuer_map(feats, close, dates, a.private)
    schedules, weekly, audit, positions = build_books(feats, close, dates, events, intervals, ids)
    for name, records in (("weekly", weekly), ("matches", audit), ("positions", positions)):
        write_csv(a.out / f"{name}.csv.gz", records)
    horizons = {}
    for h in HORIZONS:
        cohorts, legs = return_rows(schedules, dates, close, qqq, h)
        write_csv(a.out / f"cohorts-{h}.csv.gz", cohorts.reset_index())
        write_csv(a.out / f"contribution-{h}.csv.gz", legs)
        horizons[str(h)] = summarize(cohorts, legs, h)
    checks = Counter(len(names) for names, _, _ in schedules.values())
    summary = {"status": "MEASURED" if schedules else SOURCE_MISSING, "wholeWeeklyAxis": len(dates),
               "coverageIntervals": source["coverageIntervals"], "sourceStatuses": events.status.value_counts().to_dict(),
               "weights": dict(sorted(checks.items())), "coveredStudyWeeks": len(schedules),
               "matchLegReasons": audit.reason.value_counts().to_dict() if not audit.empty else {},
               "originalInputSHA256": hashes, "horizons": horizons,
               "capOverlaySHA256": frozen.sha(a.cap_corrections) if a.cap_corrections.is_file() else None,
               "ledgers": nav_windows(schedules, dates, close, qqq, a.out)}
    batch.save(a.out / "summary.json", summary)
    print(f"US complete: {len(schedules)} covered weeks, {len(positions)} selected issuer-weeks", flush=True)


if __name__ == "__main__":
    main()
