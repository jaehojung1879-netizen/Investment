"""US adapter: reuse #350 selections and costs; compare predeclared funding.

python -m research.kr_us_exposure_preserving_v1.us --private /workspace/batch-inputs/us --inputs /workspace/exposure-inputs/us
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import pickle

import numpy as np
import pandas as pd

from research.kr_us_strategy_batch_v1 import common as CM
from research.kr_us_strategy_batch_v1 import us as OLD
from research.us_selection_value_v1 import cocktail as CK
from research.us_selection_value_v1 import evaluate as EV
from research.us_selection_value_v1 import features as F
from research.us_rank_independent_check_v1.crosscheck import norm

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PRIOR = ROOT / "research/kr_us_strategy_batch_v1/results/US"
SIGNALS = ("PRICE", "PRICE_CONFIRMED", "VALUE", "CASH_PROFITABILITY")
CONFIGS = SIGNALS + ("SECTOR_MOMENTUM", "COCKTAIL", "U1")
MEGA = set(OLD.MEGA)


def save(path, value):
    OLD.save(path, value)


def csv(path, frame):
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, compression={"method": "gzip", "mtime": 0})


def weighted_net(net, weights):
    """All endpoint costs identical; weighted single-asset net is exact."""
    if weights is None or not weights:
        return np.nan
    r = net.reindex(list(weights))
    return float(r @ pd.Series(weights)) if r.notna().all() else np.nan


def endpoint_inputs(close, qqq, dates):
    assets, entries, exits, qnet = {}, {}, {}, {}
    for h in (126, 252):
        a = pd.DataFrame(np.nan, index=dates, columns=close.columns)
        entry = pd.Series(pd.NaT, index=dates, dtype="datetime64[ns]")
        exit_ = entry.copy()
        q = pd.Series(np.nan, index=dates)
        for d in dates:
            i = close.index.get_loc(d)
            if i + 1 + h >= len(close):
                continue
            e, z = close.index[i + 1], close.index[i + 1 + h]
            first, last = close.loc[e], close.loc[z]
            valid = first.gt(0) & last.gt(0) & first.notna() & last.notna()
            a.loc[d, valid] = EV.net(last[valid] / first[valid] - 1)
            entry.at[d], exit_.at[d] = e, z
            if pd.notna(qqq.at[e]) and pd.notna(qqq.at[z]) and qqq.at[e] > 0:
                q.at[d] = EV.net(float(qqq.at[z] / qqq.at[e] - 1))
        assets[h], entries[h], exits[h], qnet[h] = a, entry, exit_, q
    return assets, entries, exits, qnet


def original_inputs(close, feats):
    """Reuse saved #350 books; score original features only for controls/sleeves."""
    baseline = json.loads((PRIOR / "summary.json").read_text())
    first, last, count = baseline["signalDates"]
    feats = feats.copy()
    feats["date"] = pd.to_datetime(feats.date)
    dates = pd.DatetimeIndex(sorted(feats.loc[feats.date.between(first, last), "date"].unique()))
    assert len(dates) == count
    raw = pd.read_csv(PRIOR / "books.csv.gz", parse_dates=["date"], low_memory=False)
    books = {s: {} for s in CONFIGS}
    native = {s: {} for s in ("COCKTAIL", "U1")}
    for s in CONFIGS:
        g = raw[raw.config.eq(f"US:{s}:Q020")]
        books[s] = {d: dict(zip(x.ticker, x.weight, strict=True)) for d, x in g.groupby("date")}
    for s in native:
        g = raw[raw.config.eq(f"US:NATIVE_{s}")]
        native[s] = {d: dict(zip(x.ticker, x.weight, strict=True)) for d, x in g.groupby("date")}
    frames, passive, sectors, peers = {}, {}, {}, {s: {} for s in SIGNALS}
    membership = F.RAF.MembershipSnapshots(json.loads(gzip.decompress((ROOT / F.PILOT.MEMBERSHIP).read_bytes()))["snapshots"])
    sectorbook = F.CA.SectorBook(json.loads(gzip.decompress((ROOT / F.PILOT.SECTORS).read_bytes()))["snapshots"])
    identity = json.loads((ROOT / F.PILOT.IDENTITY).read_text())["regions"]["US"]["identity"]
    malformed = {k.upper(): v["resolvedTo"] for k, v in identity["malformed"].items() if v.get("resolvedTo")}
    renames = {t: v["pricedBy"] for t, v in identity["renames"].items() if v.get("pricedBy")}
    for t, u in F.verified_class_links(close).items():
        renames.setdefault(t, u)
    bynorm = {norm(t): t for t in close}
    assert len(bynorm) == len(close.columns)
    audits, coverage, sector_audit = [], [], []
    for d, g in feats[feats.date.isin(dates)].groupby("date", sort=True):
        by = g.set_index("ticker")
        assert by.index.is_unique
        valid = by.identity.isin(("MEMBERSHIP_CIK", "PIT_SINGLE_CIK")) & pd.to_numeric(by.marketCap, errors="coerce").gt(0)
        cap = by.loc[valid, "marketCap"].astype(float)
        passive[d] = (cap / cap.sum()).to_dict()
        # Includes financials/RE; factor completeness is only a signal gate.
        sectors[d] = by.sector.fillna("UNCLASSIFIED").to_dict()
        snap = membership.on(str(d.date()))
        for symbol in snap["members"]:
            t = malformed.get(symbol.upper(), symbol)
            t = renames.get(t, t)
            t = bynorm.get(norm(t), t)
            label, _ = sectorbook.lookup(snap, symbol)
            if label != F.CA.UNCLASSIFIED:
                sectors[d][t] = label
        common = EV.common(g)
        coverage.append({"date": d, "featureNames": len(g), "positiveCapIdentityNames": len(cap),
                         "signalCommonNames": len(common), "financialRealEstateNames": int(by.loc[valid, "sector"].isin(("Financials", "Real Estate")).sum()),
                         "financialRealEstateWeight": float((cap / cap.sum())[by.loc[valid, "sector"].isin(("Financials", "Real Estate"))].sum()),
                         "proxyNotFullIndexOrFloatAdjusted": True, "inheritsFeaturePriceHistoryGate": True})
        if len(common) < 30:
            continue
        x = EV.score(common)
        frames[d] = x
        for s in CONFIGS:
            regenerated = OLD.normalize_stock(OLD.native_book(x, s, d), .2)
            saved = books[s][d]
            assert set(regenerated) == set(saved)
            assert max(abs(regenerated[t] - saved[t]) for t in saved) < 1e-12
        for s in SIGNALS:
            peer, legs = CM.match_book(x, books[s][d], "SPY", sector_col="sector", cap_col="marketCap")
            if peer is not None:
                peers[s][d] = peer
            audits.extend({"date": d, "selector": s, **leg} for leg in legs)
        chosen = {x.at[t, "sector"] for t in books["SECTOR_MOMENTUM"][d] if t != "SPY"}
        assert len(chosen) == 1
        chosen_sector = next(iter(chosen))
        groups = {s: list(y.index) for s, y in x.groupby("sector") if s != chosen_sector}
        control = {"SPY": .8}
        for names in groups.values():
            for t in names:
                control[t] = .2 / len(groups) / len(names)
        peers.setdefault("SECTOR_MOMENTUM", {})[d] = control
        sector_audit.append({"date": d, "selectedSector": chosen_sector, "selectedNames": sum(t != "SPY" for t in books["SECTOR_MOMENTUM"][d]),
                             "controlNames": sum(t != "SPY" for t in control), "controlSectors": len(groups),
                             "stockWeightEachBook": .2, "definition": "Equal weights across all OTHER sectors; equal names within each sector; allocation comparison"})
    return dates, books, native, frames, passive, sectors, peers, pd.DataFrame(audits), pd.DataFrame(coverage), pd.DataFrame(sector_audit)


def fixed_inputs(dates, assets, books, peers):
    legacy, selection, bridge = {}, {}, {}
    for h in (126, 252):
        fixed = pd.DataFrame(np.nan, index=dates, columns=list(books))
        peer = pd.DataFrame(np.nan, index=dates, columns=list(peers))
        for d in dates:
            for s, schedule in books.items():
                fixed.at[d, s] = weighted_net(assets[h].loc[d], schedule.get(d))
            for s, schedule in peers.items():
                peer.at[d, s] = weighted_net(assets[h].loc[d], schedule.get(d))
        legacy[h] = fixed.subtract(assets[h].SPY, axis=0)
        selection[h] = fixed[list(peers)] - peer
        prior_fixed = pd.read_csv(PRIOR / f"cohorts-net-{h}.csv.gz", index_col=0, parse_dates=True)
        prior_peer = pd.read_csv(PRIOR / f"peer-cohorts-net-{h}.csv.gz", index_col=0, parse_dates=True)
        checks = {}
        for s in CONFIGS:
            old = prior_fixed[f"US:{s}:Q020"].reindex(dates)
            same = fixed[s].notna() & old.notna()
            error = float((fixed.loc[same, s] - old[same]).abs().max())
            assert error < 1e-12
            assert fixed[s].notna().equals(old.notna())
            checks[s] = {"n": int(same.sum()), "maxAbsoluteError": error}
        for s in SIGNALS:
            old = prior_peer[s].reindex(dates)
            same = peer[s].notna() & old.notna()
            error = float((peer.loc[same, s] - old[same]).abs().max())
            assert error < 1e-12
            assert peer[s].notna().equals(old.notna())
            checks[s]["peerN"] = int(same.sum())
            checks[s]["peerMaxAbsoluteError"] = error
        bridge[str(h)] = checks
    return legacy, selection, bridge


def matching_summary(dates, books, peers, audit, selection):
    result = {}
    for signal in SIGNALS:
        a = audit[audit.selector.eq(signal)]
        failures = a[a.reason.notna()]
        failed_weeks = failures[["date", "reason"]].drop_duplicates().groupby("reason").size().to_dict()
        total = len(books[signal])
        matched = len(peers[signal])
        result[signal] = {"nonemptyDecisionWeeks": total, "completeMatchedDecisionWeeks": matched,
                          "completeMatchRate": matched / total, "failedWeeksByReasonOverlapping": failed_weeks,
                          "failedLegsByReason": failures.reason.value_counts().to_dict(),
                          "peerUniverse": "Original EV.common, same sector, cap ratio [0.5,2], one-to-one, no held or reused names",
                          "horizons": {str(h): CM.stats(selection[h][signal], h) for h in (126, 252)}}
    result["SECTOR_MOMENTUM"] = {"interpretation": "Sector allocation, not within-sector stock selection",
          "nonemptyDecisionWeeks": len(books["SECTOR_MOMENTUM"]), "controlDecisionWeeks": len(peers["SECTOR_MOMENTUM"]),
          "horizons": {str(h): CM.stats(selection[h]["SECTOR_MOMENTUM"], h) for h in (126, 252)}}
    result["weeklyAxisCount"] = len(dates)
    return result


def component_contributions(frames, assets, native, books, out):
    rows, checks = [], []
    for d, x in frames.items():
        cocktail = {}
        for sleeve in CK.SLEEVES["COCKTAIL"]:
            names = CK.sleeve_names(x, sleeve)
            cocktail[sleeve] = {t: .25 / len(names) for t in names} if names else {"SPY": .25}
        top = x.marketCap.astype(float).sort_values(ascending=False).head(5)
        top_share = float(top.sum() / x.marketCap.astype(float).sum())
        u1 = {s: {t: (1 - top_share) * w for t, w in wts.items()} for s, wts in cocktail.items()}
        u1["CAP_TOP5"] = (top / x.marketCap.astype(float).sum()).to_dict()
        for strategy, comps in (("COCKTAIL", cocktail), ("U1", u1)):
            combined = defaultdict(float)
            for wts in comps.values():
                for t, w in wts.items():
                    combined[t] += w
            assert set(combined) == set(native[strategy][d])
            assert max(abs(combined[t] - native[strategy][d][t]) for t in combined) < 1e-12
            stock_total = sum(w for t, w in combined.items() if t != "SPY")
            for h in (126, 252):
                net = assets[h].loc[d]
                if pd.isna(net.SPY):
                    continue
                for portfolio in ("NATIVE", "Q020"):
                    total = 0.
                    for component, weights in comps.items():
                        wts = weights if portfolio == "NATIVE" else {t: .2 * w / stock_total for t, w in weights.items() if t != "SPY"}
                        r = net.reindex(list(wts))
                        contribution = float((r - net.SPY) @ pd.Series(wts)) if r.notna().all() else np.nan
                        total += contribution
                        rows.append({"date": d, "H": h, "strategy": strategy, "portfolio": portfolio, "component": component,
                                     "componentWeight": sum(wts.values()), "netExcessContribution": contribution,
                                     "top5CommonCapShare": top_share, "interpretation": "Fixed-holding attribution; combined target costs once; not operating CAGR attribution"})
                    target = native[strategy][d] if portfolio == "NATIVE" else books[strategy][d]
                    expected = weighted_net(net, target) - net.SPY
                    assert abs(total - expected) < 1e-12
                    checks.append({"date": d, "H": h, "strategy": strategy, "portfolio": portfolio, "sumComponents": total,
                                   "totalNetExcess": expected, "error": total - expected})
    result = pd.DataFrame(rows)
    csv(out / "native-component-contributions.csv.gz", result)
    csv(out / "native-component-reconciliation.csv.gz", pd.DataFrame(checks))
    summary = {}
    for (strategy, portfolio, component, h), g in result.groupby(["strategy", "portfolio", "component", "H"]):
        series = pd.Series(np.nan, index=assets[h].index)
        series.loc[g.date] = g.netExcessContribution.to_numpy()
        summary.setdefault(strategy, {}).setdefault(portfolio, {}).setdefault(str(h), {})[component] = CM.stats(series, h)
    save(out / "native-components.json", {"summary": summary, "maximumReconciliationError": max(abs(r["error"]) for r in checks),
                                          "netCostMethod": "Constant original buy/sell costs are linear across fixed funded weights; overlap trades once. NAV attribution is not claimed."})


def actual_exposure_audit(books, passive, sectors, out):
    """Conditional partial audit only; do not turn unknown tail into ETF/zero."""
    inputs = HERE / "inputs/US"
    holdings = pd.read_csv(inputs / "spy-normalized-holdings.csv.gz", dtype={"cusip": str})
    reports = pd.DataFrame(json.loads((inputs / "spy-reports.json").read_text()))
    reports["publicFrom"] = pd.to_datetime(reports.publicFrom)
    reports["holdingAsOf"] = pd.to_datetime(reports.holdingAsOf)
    grouped = {a: g for a, g in holdings.groupby("accession")}
    rows = []
    for d in sorted(passive):
        available = reports[(reports.publicFrom < d) & ((d - reports.holdingAsOf).dt.days <= 180)]
        if available.empty:
            continue
        r = available.sort_values(["holdingAsOf", "publicFrom", "accession"]).iloc[-1]
        g = grouped[r.accession]
        eq = g[g.assetCat.eq("EC")].copy()
        eq["sector"] = eq.candidateTickerFromExistingMap.map(sectors[d])
        sector_weights = eq.dropna(subset=["sector"]).groupby("sector").netAssetsWeight.sum().to_dict()
        known_mega = eq.loc[eq.candidateTickerFromExistingMap.isin(MEGA), "netAssetsWeight"].sum()
        unknown_sector = float(eq.loc[eq.sector.isna(), "netAssetsWeight"].sum())
        unknown_ticker = float(eq.loc[eq.candidateTickerFromExistingMap.isna(), "netAssetsWeight"].sum())
        for config, schedule in books.items():
            if d not in schedule:
                continue
            w = schedule[d]
            etf = w.get("SPY", 0.)
            direct_sector = defaultdict(float)
            for t, a in w.items():
                if t != "SPY":
                    direct_sector[sectors[d].get(t, "UNCLASSIFIED")] += a
            conditional_sector = {s: direct_sector[s] + etf * a for s, a in sector_weights.items()}
            for s, a in direct_sector.items():
                conditional_sector.setdefault(s, a)
            base_mega = sum(a for t, a in passive[d].items() if t in MEGA)
            direct_mega = sum(w.get(t, 0) for t in MEGA)
            proxy_lookthrough = direct_mega + etf * base_mega
            actual_conditional = direct_mega + etf * float(known_mega)
            row = {"date": d, "config": config, "accession": r.accession, "holdingAsOf": r.holdingAsOf,
                   "publicFrom": r.publicFrom, "reportAgeDays": (d - r.holdingAsOf).days,
                   "mappingIsPITProved": False, "actualFullReplicaReturnEstimable": False,
                   "reportedEquityNetWeight": float(eq.netAssetsWeight.sum()), "reportedUnmappedNetWeight": unknown_ticker,
                   "reportedUnknownSectorNetWeight": unknown_sector, "directMegaWeight": direct_mega,
                   "etfIndirectMegaConditionalWeight": etf * float(known_mega), "totalMegaConditionalWeight": actual_conditional,
                   "reportedMegaConditionalBaseWeight": float(known_mega), "totalMegaProxyWeight": proxy_lookthrough,
                   "proxyMegaBaseWeight": base_mega, "conditionalActualMegaDifference": actual_conditional - float(known_mega),
                   "conditionalActualSectorL1Difference": sum(abs(conditional_sector.get(s, 0) - sector_weights.get(s, 0)) for s in set(conditional_sector) | set(sector_weights)),
                   "unknownSectorWeightViaEtf": etf * unknown_sector,
                   "reportedSectorWeightsConditional": json.dumps(sector_weights, sort_keys=True),
                   "bookSectorWeightsConditional": json.dumps(conditional_sector, sort_keys=True)}
            for name in sorted(MEGA):
                reported = float(eq.loc[eq.candidateTickerFromExistingMap.eq(name), "netAssetsWeight"].sum())
                row[f"reported_{name}"] = reported
                row[f"total_{name}_conditional"] = w.get(name, 0) + etf * reported
            rows.append(row)
    csv(out / "actual-spy-partial-exposure-audit.csv.gz", pd.DataFrame(rows))
    save(out / "actual-spy-status.json", {"status": "PARTIAL_LAGGED_REPORTED_EXPOSURE_ONLY_FULL_ACTUAL_REPLICA_BLOCKED",
         "weeks": len({r["date"] for r in rows}), "fullReplicaWeeks": 0,
         "limitation": "Current CUSIP map is conditional, not dated identity proof; unknown tail retained; lagged public report is not current holdings; no tail return or full exposure invented.",
         "sourceCoverage": json.loads((inputs / "spy-coverage-summary.json").read_text())})


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", type=Path, required=True)
    ap.add_argument("--inputs", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=HERE / "results/US")
    ap.add_argument("--prepare-only", action="store_true")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    original_close, feats, qqq, metadata = EV.load(a.private)
    receipt = json.loads((a.inputs / "fisv-repair-applied.json").read_text())
    with (a.inputs / "close-repaired.pkl").open("rb") as f:
        close = pickle.load(f)["close"]
    changed = ~(close.eq(original_close) | (close.isna() & original_close.isna()))
    assert int(changed.sum().sum()) == 1 and changed.at[pd.Timestamp("2025-11-12"), "FISV"]
    assert hashlib.sha256((a.inputs / "close-repaired.pkl").read_bytes()).hexdigest() == receipt["repairedClosePklSha256"]
    assert hashlib.sha256((a.private / "close.pkl").read_bytes()).hexdigest() == receipt["originalClosePklSha256"]
    dates, books, native, frames, passive, sectors, peers, audit, coverage, sector_audit = original_inputs(close, feats)
    csv(a.out / "matching-audit.csv.gz", audit)
    csv(a.out / "proxy-coverage.csv.gz", coverage)
    csv(a.out / "sector-control-audit.csv.gz", sector_audit)
    assets, entries, exits, qnet = endpoint_inputs(close, qqq, dates)
    legacy, selection, bridge = fixed_inputs(dates, assets, books, peers)
    save(a.out / "prior-350-bridge.json", bridge)
    save(a.out / "matching-summary.json", matching_summary(dates, books, peers, audit, selection))
    component_contributions(frames, assets, native, books, a.out)
    c2 = a.private.parent / "nport/round8/C2.pkl"
    save(a.out / "input-status.json", {"designCommit": "e3e572f", "priceRepair": receipt,
          "unchangedFeatureSha256": hashlib.sha256((a.private / "features.pkl").read_bytes()).hexdigest(),
          "fundDisclosure": {"status": "MISSING_OPTIONAL_C2" if not c2.exists() else "PRESENT_REQUIRES_ORIGINAL_C2_ADAPTER", "requiredFile": str(c2)},
          "qqq": metadata, "priorBooksReused": str(PRIOR / "books.csv.gz"), "signalDates": [dates[0], dates[-1], len(dates)]})
    audit_books = {"ETF": {d: {"SPY": 1.} for d in dates}, "B": passive, **books}
    actual_exposure_audit(audit_books, passive, sectors, a.out)
    # Data for the owner's original NAV adapter; no alternative NAV is implemented here.
    payload = {"market": "US", "etf": "SPY", "dates": dates, "books": books, "passive": passive,
               "sectors": sectors, "leaders": MEGA, "net_asset": assets, "entries": entries,
               "legacy": legacy, "peers": peers, "selection": selection, "out": a.out,
               "periods": {h: {"EX_2021": entries[h].dt.year.ne(2021) & entries[h].notna(),
                               "FROM_2023": entries[h].ge(pd.Timestamp("2023-01-03")),
                               "EXIT_BY_2022": exits[h].le(pd.Timestamp("2022-12-30"))} for h in (126, 252)}, "qqq": qnet}
    with (a.inputs / "us-adapter-payload.pkl").open("wb") as f:
        pickle.dump({**payload, "close": close, "native": native}, f)
    if not a.prepare_only:
        from research.kr_us_exposure_preserving_v1 import engine
        engine.run(**payload)
        with gzip.open(a.out / "funding-book-schedules.json.gz", "rt") as f:
            funded = json.load(f)
        for config, schedule in funded.items():
            if not config.endswith(":PEER") and config != "PASSIVE":
                audit_books["FUNDED:" + config] = {pd.Timestamp(d): w for d, w in schedule.items()}
        actual_exposure_audit(audit_books, passive, sectors, a.out)


if __name__ == "__main__":
    main()
