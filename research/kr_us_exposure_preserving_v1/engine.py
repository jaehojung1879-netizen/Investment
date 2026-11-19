"""Frozen study. Funding uses only decision-day weights and classifications."""
from __future__ import annotations

from collections import defaultdict
import gzip
import json

import numpy as np
import pandas as pd

from research.kr_us_strategy_batch_v1.common import stats


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1, allow_nan=False) + "\n")


def write_books(path, schedules):
    content = {k: {str(d.date()): w for d, w in v.items()} for k, v in schedules.items()}
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(gzip.compress(json.dumps(content, separators=(",", ":")).encode(), compresslevel=4, mtime=0))
    temporary.replace(path)


def exposure(weights, sectors, leaders):
    industry = defaultdict(float)
    for ticker, weight in weights.items():
        industry[sectors.get(ticker) or "UNCLASSIFIED"] += weight
    return dict(industry), sum(weights.get(t, 0) for t in leaders)


def redistribute(base, stock, sectors, leaders):
    """Long-only, proportional donors within each industry/leader cell."""
    if not np.isclose(sum(base.values()), 1, atol=1e-10) or any(v <= 0 for v in base.values()):
        raise ValueError("invalid passive weights")
    budget = sum(stock.values())
    if not 0 <= budget <= 1 + 1e-12:
        raise ValueError("invalid stock budget")
    def cell(ticker):
        return sectors.get(ticker) or "UNCLASSIFIED", ticker in leaders

    available, desired = defaultdict(float), defaultdict(float)
    for ticker, weight in base.items():
        available[cell(ticker)] += weight
    for ticker, weight in stock.items():
        desired[cell(ticker)] += weight
    taken = {key: min(available[key], desired[key]) for key in set(available) | set(desired)}
    gap = budget - sum(taken.values())
    if abs(gap) > 1e-14:
        capacity = 1 - sum(taken.values())
        for key in taken:
            taken[key] += gap * (available[key] - taken[key]) / capacity
    donor = {t: w * (taken[cell(t)] / available[cell(t)]) for t, w in base.items()}
    final = {t: base.get(t, 0) - donor.get(t, 0) + stock.get(t, 0) for t in sorted(set(base) | set(stock))}
    assert min(final.values()) >= -1e-12 and abs(sum(final.values()) - 1) < 1e-10
    assert abs(sum(donor.values()) - budget) < 1e-10
    final = {t: w for t, w in final.items() if w > 1e-14}
    return final, donor, max(0, gap)


def distance(a, b):
    return sum(abs(a.get(k, 0) - b.get(k, 0)) for k in set(a) | set(b))


def weighted(weights, quotes):
    if not weights:
        return np.nan
    values = quotes.reindex(list(weights)).to_numpy()
    if not np.isfinite(values).all():
        return np.nan
    return float(values @ np.array(list(weights.values())))


def build(dates, books, passive, sectors, etf, leaders, peers):
    schedules = {"PASSIVE": passive}
    donor_maps, audits = {}, []
    for config, bydate in books.items():
        aligned, peer_aligned, donor_maps[config] = {}, {}, {}
        for date in dates:
            if date not in bydate or date not in passive:
                continue
            book, base, groups = bydate[date], passive[date], sectors[date]
            stock = {t: w for t, w in book.items() if t != etf and w > 0}
            q = sum(stock.values())
            if q <= 0:
                continue
            aligned[date], donor, gap = redistribute(base, stock, groups, leaders)
            donor_maps[config][date] = donor
            original_lookthrough = {t: (1-q)*base.get(t, 0)+stock.get(t, 0) for t in set(base) | set(stock)}
            b_sector, b_mega = exposure(base, groups, leaders)
            o_sector, o_mega = exposure(original_lookthrough, groups, leaders)
            f_sector, f_mega = exposure(aligned[date], groups, leaders)
            peer = peers.get(config, {}).get(date)
            shared = None
            if peer:
                peer_stock = {t: w for t, w in peer.items() if t != etf and w > 0}
                assert abs(sum(peer_stock.values()) - q) < 1e-10
                peer_aligned[date], peer_donor, _ = redistribute(base, peer_stock, groups, leaders)
                shared = distance(donor, peer_donor) < 1e-10
            audits.append({"date": date, "config": config, "activeNames": len(stock),
                           "baseNames": len(base), "fundedNames": len(aligned[date]),
                           "nominalBudget": q, "netActiveBuys": distance(base, aligned[date])/2,
                           "unmatchedFunding": gap, "exactCells": gap < 1e-10,
                           "baseLeader": b_mega, "originalLeader": o_mega, "fundedLeader": f_mega,
                           "originalDirectLeader": sum(stock.get(t, 0) for t in leaders),
                           "originalIndirectLeader": (1-q)*b_mega, "fundedIndirectLeader": 0.,
                           "originalSectorL1": distance(b_sector, o_sector),
                           "fundedSectorL1": distance(b_sector, f_sector),
                           "originalIndividualLeaderL1": sum(abs(original_lookthrough.get(t, 0) - base.get(t, 0)) for t in leaders),
                           "fundedIndividualLeaderL1": sum(abs(aligned[date].get(t, 0) - base.get(t, 0)) for t in leaders),
                           "baseIndustries": json.dumps(b_sector, sort_keys=True),
                           "originalIndustries": json.dumps(o_sector, sort_keys=True),
                           "fundedIndustries": json.dumps(f_sector, sort_keys=True),
                           "leaderWeights": json.dumps({t: [base.get(t, 0), original_lookthrough.get(t, 0), aligned[date].get(t, 0)]
                                                        for t in sorted(leaders)}),
                           "sameDonorForPeer": shared})
        schedules[config] = aligned
        schedules[config + ":PEER"] = peer_aligned
    return schedules, donor_maps, pd.DataFrame(audits)


def run(market, etf, dates, books, passive, sectors, leaders, net_asset, entries,
        legacy, peers, selection, out, periods=None, qqq=None):
    out.mkdir(parents=True, exist_ok=True)
    schedules, donors, exposure_audit = build(dates, books, passive, sectors, etf, leaders, peers)
    exposure_audit.to_csv(out / "exposure.csv.gz", index=False)
    write_books(out / "funding-book-schedules.json.gz", schedules)
    write_books(out / "funding-donors.json.gz", donors)
    shared_donors = exposure_audit.set_index(["config", "date"]).sameDonorForPeer.to_dict()
    report = {"market": market, "horizons": {}}
    for h in (126, 252):
        assets = net_asset[h].reindex(dates)
        entry = pd.to_datetime(entries[h].reindex(dates))
        data = {}
        attribution = []
        for config in books:
            aligned = schedules[config]
            peer_aligned = schedules[config + ":PEER"]
            legacy_excess = legacy[h][config].reindex(dates)
            select = selection[h].get(config, pd.Series(np.nan, index=dates)).reindex(dates)
            rows = []
            for date, quotes in assets.iterrows():
                base = passive.get(date)
                book = aligned.get(date)
                etf_net = quotes.get(etf, np.nan)
                control = weighted(base, quotes)
                net = weighted(book, quotes)
                peer_net = weighted(peer_aligned.get(date), quotes)
                direction = net - control
                shared = shared_donors.get((config, date), False)
                row = {"date": date, "legacy": legacy_excess.at[date], "funded": net-etf_net,
                       "passive": control-etf_net, "active": direction, "fundedMinusLegacy": net-etf_net-legacy_excess.at[date],
                       "legacySelection": select.at[date], "fundedSelection": net-peer_net,
                       "fundedSharedDonorSelection": net-peer_net if shared else np.nan,
                       "entryYear": entry.at[date].year if pd.notna(entry.at[date]) else None,
                       "missingPassiveNames": "|".join(t for t in (base or {}) if not np.isfinite(quotes.get(t, np.nan))),
                       "missingFundedNames": "|".join(t for t in (book or {}) if not np.isfinite(quotes.get(t, np.nan)))}
                if qqq is not None:
                    row["fundedVsQQQ"] = net - qqq[h].at[date]
                    row["legacyVsQQQ"] = legacy_excess.at[date] + etf_net - qqq[h].at[date]
                if np.isfinite(direction):
                    active = {t: book.get(t, 0)-base.get(t, 0) for t in set(book) | set(base)}
                    parts = {t: w*(quotes.at[t]-etf_net) for t, w in active.items() if abs(w) > 1e-14}
                    assert abs(sum(parts.values()) - direction) < 1e-9
                    assert abs(row["funded"] - row["passive"] - direction) < 1e-9
                    row["leaderContribution"] = sum(parts.get(t, 0) for t in leaders)
                    original = books[config][date]
                    stock_weight = 1 - original.get(etf, 0)
                    old_parts = {
                        t: (original.get(t, 0) - stock_weight * base.get(t, 0)) * (quotes.get(t, np.nan) - etf_net)
                        for t in set(base) | (set(original) - {etf})
                    }
                    row["legacyLeaderContribution"] = sum(old_parts.get(t, 0) for t in leaders)
                    for ticker, value in sorted(parts.items()):
                        attribution.append({"date": date, "config": config, "ticker": ticker,
                                            "activeWeight": active[ticker], "contribution": value})
                rows.append(row)
            f = pd.DataFrame(rows).set_index("date")
            data[config] = f
        attr = pd.DataFrame(attribution, columns=["date","config","ticker","activeWeight","contribution"])
        attr.to_csv(out / f"active-contribution-{h}.csv.gz", index=False)
        table = pd.concat(data, names=["config","date"])
        table.to_csv(out / f"cohorts-{h}.csv.gz")
        section = {"portfolios": {}, "selection": {}, "pairwise": {}}
        for config, f in data.items():
            common = f[["funded", "passive", "legacy"]].notna().all(axis=1)
            fields = ["legacy", "funded", "passive", "active", "fundedMinusLegacy"]
            comparisons = {k: stats(f[k], h, common) for k in fields}
            comparisons["legacyOwn"] = stats(f.legacy, h)
            comparisons["fundedSelection"] = stats(f.fundedSelection, h)
            comparisons["fundedSharedDonorSelection"] = stats(f.fundedSharedDonorSelection, h)
            same_dates = f[["fundedSelection","legacySelection"]].notna().all(axis=1)
            comparisons["legacySelectionOnFundedPeerDates"] = stats(f.legacySelection, h, same_dates)
            comparisons["fundedSelectionMinusOriginal"] = stats(f.fundedSelection-f.legacySelection, h, same_dates)
            if qqq is not None:
                for k in ("fundedVsQQQ", "legacyVsQQQ"):
                    comparisons[k] = stats(f[k], h, common)
            a = attr[attr.config == config]
            by_name = a.groupby("ticker").contribution.sum()
            if not by_name.empty and common.any():
                by_name = a[a.date.isin(f.index[common])].groupby("ticker").contribution.sum()
                name = by_name.idxmax()
                contribution = a[a.ticker == name].set_index("date").contribution.reindex(dates, fill_value=0.)
                comparisons["maximumName"] = name
                comparisons["excludeMaximumName"] = stats(f.funded-contribution, h, common)
                comparisons["excludeLeaderContribution"] = stats(f.funded-f.leaderContribution, h, common)
                comparisons["legacyExcludeLeaderContribution"] = stats(f.legacy-f.legacyLeaderContribution, h, common)
                year = int(f.funded.where(common).groupby(f.entryYear).sum(min_count=1).idxmax())
                comparisons["maximumEntryYear"] = year
                comparisons["excludeMaximumEntryYear"] = stats(f.funded, h, common & f.entryYear.ne(year))
            comparisons["periods"] = {label: {k: stats(f[k],h,common & mask.reindex(dates,fill_value=False)) for k in fields}
                                      for label, mask in (periods or {}).get(h, {}).items()}
            comparisons["annual"] = {str(int(y)): {k: stats(f[k],h,common & f.entryYear.eq(y)) for k in fields}
                                     for y in sorted(f.entryYear.dropna().unique())}
            section["portfolios"][config] = comparisons
        for config in selection[h]:
            section["selection"][config] = stats(selection[h][config], h)
        pairs = (("S2", "VALUE_COMPLETE"), ("CONFIRM_NEUTRAL", "S2")) if market == "KR" else (
            ("PRICE_CONFIRMED", "PRICE"), ("PRICE_CONFIRMED", "VALUE"))
        for a, b in pairs:
            if a in selection[h] and b in selection[h]:
                section["pairwise"][a+"-"+b] = stats(selection[h][a]-selection[h][b], h)
        selection[h].to_csv(out / f"selection-{h}.csv.gz")
        report["horizons"][str(h)] = section
    write_json(out / "summary.json", report)
    return report
