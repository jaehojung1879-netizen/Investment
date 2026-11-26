"""US fixed-cohort reconstruction and lagged SPY disclosure bridge under DESIGN-ko.md."""
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

from research.kr_us_exposure_preserving_v1 import nav
from research.kr_us_strategy_batch_v1 import common as cm
from research.kr_us_strategy_batch_v1 import us as batch
from research.us_rank_independent_check_v1.crosscheck import norm
from research.us_selection_value_v1 import evaluate as ev
from research.us_selection_value_v1 import features as features

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PRIOR = ROOT / "research/kr_us_exposure_preserving_v1"
HORIZONS = (126, 252)
MEGA = tuple(sorted(batch.MEGA))
VALID_ID = ("MEMBERSHIP_CIK", "PIT_SINGLE_CIK")
COMPONENTS = (
    "proxyOutsideCommon", "sectorAndMegaWeight", "withinCellWeight",
    "reportNamesOutsideProxy", "reportResidual",
)
NET_FACTOR = (1 - ev.BUY) * (1 - ev.SELL)


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def csv(path, frame):
    frame.to_csv(path, index=False, compression={"method": "gzip", "mtime": 0})


def weighted(returns, weights):
    if not weights or not set(weights).issubset(returns.index):
        return np.nan
    v = returns.loc[list(weights)].to_numpy()
    if not np.isfinite(v).all():
        return np.nan
    return float(v @ np.array(list(weights.values())))


def sum_weights(weights, groups):
    result = defaultdict(float)
    for name, weight in weights.items():
        result[groups[name]] += weight
    return dict(sorted(result.items()))


def normalize(weights, support):
    subset = {t: weights[t] for t in sorted(support)}
    total = sum(subset.values())
    return {t: v / total for t, v in subset.items()} if total else {}


def distance(left, right):
    return float(sum(abs(left.get(t, 0) - right.get(t, 0)) for t in sorted(set(left) | set(right))))


def cell_name(sector, ticker):
    return f"{sector}|{'MEGA' if ticker in MEGA else 'OTHER'}"


def align_weights(base, target, groups):
    """Use target group totals and base relative weights inside each group."""
    if base.keys() != target.keys() or base.keys() != groups.keys():
        raise ValueError("Aligned weights must use the same support")
    b_total, t_total = sum_weights(base, groups), sum_weights(target, groups)
    return {t: w * t_total[groups[t]] / b_total[groups[t]] for t, w in base.items()}


def bridge_books(base, reports, sectors):
    """Use the disclosed, decision-observable names supplied by the caller."""
    common = base.keys() & reports.keys()
    if not common:
        return {}
    bc, lc = normalize(base, common), normalize(reports, common)
    s = normalize(reports, reports)
    groups = {t: sectors[t] for t in bc}
    cells = {t: cell_name(sectors[t], t) for t in bc}
    return {"B": base, "BC": bc, "MSector": align_weights(bc, lc, groups),
            "MC": align_weights(bc, lc, cells), "LC": lc, "LS": s}


def bridge_values(returns, spy, books):
    b, bc, ms, mc, lc, ls = (weighted(returns, books[k]) for k in
                             ("B", "BC", "MSector", "MC", "LC", "LS"))
    return {"proxyNetExcess": b-spy, "proxyOutsideCommon": b-bc,
            "sectorAndMegaWeight": bc-mc, "sectorWeightOnly": bc-ms,
            "megaWithinSectorWeight": ms-mc, "withinCellWeight": mc-lc,
            "reportNamesOutsideProxy": lc-ls, "reportResidual": ls-spy,
            "BNet": b, "BCNet": bc, "MSectorNet": ms, "MCNet": mc, "LCNet": lc,
            "LSNet": ls, "SPYNet": spy}


def endpoint_returns(close, dates, horizon, offset=1):
    """Next close by default, then exactly H exchange sessions forward."""
    positions = close.index.get_indexer(dates)
    if (positions < 0).any():
        raise ValueError("All #351 decision dates must be close sessions")
    entry, exit_ = positions + offset, positions + offset + horizon
    mature = exit_ < len(close)
    e, z = close.iloc[entry[mature]].to_numpy(), close.iloc[exit_[mature]].to_numpy()
    valid = np.isfinite(e) & np.isfinite(z) & (e > 0) & (z > 0)
    prices = np.divide(z, e, out=np.full_like(z, np.nan), where=valid) - 1
    returns = pd.DataFrame(prices, index=dates[mature], columns=close.columns).reindex(dates)
    sessions = pd.DataFrame({"entry": close.index[entry[mature]], "exit": close.index[exit_[mature]]},
                            index=dates[mature]).reindex(dates)
    return returns, sessions


def load_frozen(private, inputs):
    receipt = json.loads((PRIOR / "inputs/US/fisv-repair-applied.json").read_text())
    paths = {"originalClose": private / "close.pkl", "repairedClose": inputs / "close-repaired.pkl",
             "features": private / "features.pkl", "adapter": inputs / "us-adapter-payload.pkl"}
    hashes = {k: sha(p) for k, p in paths.items()}
    assert hashes["originalClose"] == receipt["originalClosePklSha256"]
    baseline = json.loads((PRIOR / "results/US/input-status.json").read_text())
    assert hashes["features"] == baseline["unchangedFeatureSha256"]
    with paths["adapter"].open("rb") as f:
        payload = pickle.load(f)
    with paths["repairedClose"].open("rb") as f:
        close = pickle.load(f)["close"]
    if hashes["repairedClose"] != receipt["repairedClosePklSha256"]:
        # #351 pickles the work directory in metadata. A relocated rebuild must
        # still be byte-for-byte equivalent in every numeric price cell.
        with paths["originalClose"].open("rb") as f:
            original = pickle.load(f)["close"]
        date, ticker = pd.Timestamp(receipt["date"]), receipt["ticker"]
        assert pd.isna(original.at[date, ticker])
        original.at[date, ticker] = receipt["proposedForwardTotalReturnClose"]
        pd.testing.assert_frame_equal(close, original, check_exact=True)
    pd.testing.assert_frame_equal(close, payload["close"], check_exact=True)
    assert payload["etf"] == "SPY" and set(MEGA) == payload["leaders"]
    tables = nav.load_books(PRIOR / "results/US/funding-book-schedules.json.gz")
    for d, book in tables["PASSIVE"].items():
        if payload["passive"][d] != book:
            raise ValueError(f"Frozen schedule changed at {d.date()}")
    assert list(tables["PASSIVE"]) == list(payload["dates"])
    return payload, close, hashes


def dated_sectors(close, dates):
    """Repeat #351 source-coverage convention without fundamental admission."""
    membership = features.RAF.MembershipSnapshots(json.loads(
        gzip.decompress((ROOT / features.PILOT.MEMBERSHIP).read_bytes()))["snapshots"])
    sectorbook = features.CA.SectorBook(json.loads(
        gzip.decompress((ROOT / features.PILOT.SECTORS).read_bytes()))["snapshots"])
    identity = json.loads((ROOT / features.PILOT.IDENTITY).read_text())["regions"]["US"]["identity"]
    malformed = {k.upper(): v["resolvedTo"] for k, v in identity["malformed"].items()
                 if v.get("resolvedTo")}
    renames = {t: v["pricedBy"] for t, v in identity["renames"].items() if v.get("pricedBy")}
    for t, u in features.verified_class_links(close).items():
        renames.setdefault(t, u)
    by_norm = {norm(t): t for t in close}
    assert len(by_norm) == len(close.columns)
    result = {}
    for d in dates:
        snap = membership.on(d.date().isoformat())
        result[d] = {}
        for symbol in snap["members"]:
            ticker = malformed.get(symbol.upper(), symbol)
            ticker = renames.get(ticker, ticker)
            ticker = by_norm.get(norm(ticker), ticker)
            label, _ = sectorbook.lookup(snap, symbol)
            if label != features.CA.UNCLASSIFIED:
                result[d][ticker] = label
    return result


def published_reports(private, close, passive, dates):
    base = PRIOR / "inputs/US"
    manifest = json.loads((base / "spy-source-manifest.json").read_text())
    source_path = base / "spy-normalized-holdings.csv.gz"
    assert sha(source_path) == manifest["normalizedSha256"]
    holdings = pd.read_csv(source_path, dtype={"cusip": str})
    reports = pd.DataFrame(json.loads((base / "spy-reports.json").read_text()))
    for k in ("holdingAsOf", "publicFrom"):
        reports[k] = pd.to_datetime(reports[k])
    secured = pd.read_csv(base / "spy-source-coverage-by-decision.csv", parse_dates=["date"]).set_index("date")
    groups = {a: g.loc[g.assetCat.eq("EC")].copy() for a, g in holdings.groupby("accession")}
    sectors = dated_sectors(close, dates)
    feat = pd.read_pickle(private / "features.pkl")
    feat["date"] = pd.to_datetime(feat.date)
    features_by_day = {d: g.set_index("ticker")[["identity", "marketCap"]]
                       for d, g in feat.groupby("date")}
    support, rows, lines = {}, [], []
    for d in dates:
        eligible = reports.loc[reports.publicFrom.lt(d) & (d-reports.holdingAsOf).dt.days.le(180)]
        if eligible.empty:
            rows.append({"date": d, "status": "NO_PUBLISHED_REPORT"})
            continue
        r = eligible.sort_values(["holdingAsOf", "publicFrom", "accession"]).iloc[-1]
        eq = groups[r.accession].copy()
        t = eq.candidateTickerFromExistingMap
        mapped = t.notna()
        assert t[mapped].is_unique
        f = features_by_day[d]
        classified = t.map(sectors[d]).notna()
        decision_price = t.map(close.loc[d])
        priced = np.isfinite(decision_price) & decision_price.gt(0)
        identity = t.map(f.identity)
        cap = pd.to_numeric(t.map(f.marketCap), errors="coerce")
        eligible_stock = mapped & priced & classified
        base = passive[d]
        in_proxy = t.isin(base)
        w = eq.netAssetsWeight
        report_weights = dict(zip(t[eligible_stock], w[eligible_stock], strict=True))
        support[d] = {"weights": report_weights, "sectors": sectors[d],
                                     "accession": r.accession}
        reasons = np.select(
            [~mapped, ~priced, ~classified, in_proxy, identity.isna(),
             ~identity.isin(VALID_ID), ~(np.isfinite(cap) & cap.gt(0))],
            ["UNMAPPED", "NO_DECISION_CLOSE", "NO_DATED_SECTOR", "IN_PROXY",
             "NO_FEATURE_ROW", "FEATURE_IDENTITY_NOT_ELIGIBLE", "NO_VALID_PROXY_CAP"],
            default="B_EXCLUSION_NOT_IDENTIFIED")
        common = set(base) & set(report_weights)
        all_mapped = set(t[mapped])
        absent_candidates = set(base) - all_mapped
        matched_sectors = {n: sectors[d][n] for n in report_weights}
        common_base, common_reports = normalize(base, common), normalize(report_weights, common)
        common_cells = {n: cell_name(sectors[d][n], n) for n in common}
        common_a = sum_weights(common_base, common_cells)
        common_b = sum_weights(common_reports, common_cells)
        known_equity = float(w[eligible_stock].sum())
        assert abs(known_equity - secured.loc[d, "pricedAndSectorKnownNetWeight"]) < 1e-9
        assert r.accession == secured.loc[d, "accession"]
        rows.append({"date": d, "status": "LATEST_PUBLIC_LAGGED_REPORT",
                     "accession": r.accession, "holdingAsOf": r.holdingAsOf,
                     "publicFrom": r.publicFrom, "reportAgeDays": (d-r.holdingAsOf).days,
                     "publicationAgeDays": (d-r.publicFrom).days, "reportEquityNetWeight": float(w.sum()),
                     "unmappedNetWeight": float(w[~mapped].sum()),
                     "mappedNoDecisionPriceNetWeight": float(w[mapped & ~priced].sum()),
                     "mappedPricedNoSectorNetWeight": float(w[mapped & priced & ~classified].sum()),
                     "knownEquityNetWeight": known_equity,
                     "knownWithFeatureIdentityNetWeight": float(w[eligible_stock & identity.isin(VALID_ID)].sum()),
                     "reportedNonEquityNetWeight": r.nonEquityReportedNetWeight,
                     "netAssetsLessReportedLinesFraction": r.netAssetsLessReportedLinesFraction,
                     "knownNames": len(report_weights), "commonNames": len(common),
                     "proxyOutsideCommonWeight": sum(base[t0] for t0 in sorted(base.keys() - common)),
                     "proxyNoMappedReportLineWeight": sum(base[t0] for t0 in sorted(absent_candidates)),
                     "reportNamesOutsideProxy": len(set(report_weights)-set(base)),
                     "reportNamesOutsideProxyNetWeight": sum(report_weights[t0] for t0 in sorted(report_weights.keys()-base.keys())),
                     "coverageSectorCellL1": distance(common_a, common_b),
                     "coverageSectorL1": distance(sum_weights(common_base, sectors[d]), sum_weights(common_reports, sectors[d])),
                     "coverageMegaWeightProxyCommon": sum(common_base.get(t0, 0) for t0 in MEGA),
                     "coverageMegaWeightReportCommon": sum(common_reports.get(t0, 0) for t0 in MEGA),
                     "reportKnownMegaNetWeight": sum(report_weights.get(t0, 0) for t0 in MEGA),
                     "proxyMegaWeight": sum(base.get(t0, 0) for t0 in MEGA),
                     "commonProxyCellWeights": json.dumps(common_a),
                     "commonReportCellWeights": json.dumps(common_b),
                     "recognizedReportedSectorNetWeights": json.dumps(sum_weights(report_weights, matched_sectors)),
                     "reportKnownFullReplica": bool(eligible_stock.all()),
                     "identityMappingIsPITProved": False})
        for i, (_, line) in enumerate(eq.iterrows()):
            name = line.candidateTickerFromExistingMap
            lines.append({"date": d, "accession": r.accession, "ticker": name,
                          "cusip": line.cusip, "netAssetsWeight": line.netAssetsWeight,
                          "sectorAtDecision": sectors[d].get(name), "featureIdentity": identity.iloc[i],
                          "isDecisionObservable": bool(eligible_stock.iloc[i]), "proxyInclusion": bool(in_proxy.iloc[i]),
                          "bWeight": base.get(name, 0.), "supportStatus": reasons[i]})
    coverage = pd.DataFrame(rows).set_index("date")
    assert len(support) == len(secured)
    return support, coverage, pd.DataFrame(lines)


def yahoo_price_panels(private, close, passive):
    """Read only prior-captured Yahoo bodies. No fetching or return splicing."""
    names = sorted({t for b in passive.values() for t in b} | {"SPY"})
    root = private / "yahoo-raw"
    manifest = json.loads((private / "yahoo-capture-manifest.json").read_text())
    receipts = {r["ticker"]: r for r in manifest["receipts"]}
    raw, adj, rows = {}, {}, []
    for ticker in names:
        receipt = receipts[ticker]
        if receipt["status"] != 200:
            rows.append({"ticker": ticker, "status": "NOT_SERVED"})
            continue
        path = root / (ticker + ".response.json.gz")
        body = gzip.decompress(path.read_bytes())
        assert hashlib.sha256(body).hexdigest() == receipt["responseSha256"]
        result = json.loads(body)["chart"]["result"][0]
        assert norm(result["meta"]["symbol"]) == norm(ticker) and result["meta"]["currency"] == "USD"
        index = pd.DatetimeIndex(pd.to_datetime(result["timestamp"], unit="s")).normalize()
        p = pd.Series(result["indicators"]["quote"][0]["close"], index=index, dtype=float)
        a = pd.Series(result["indicators"]["adjclose"][0]["adjclose"], index=index, dtype=float)
        assert p.index.is_unique and p.index.is_monotonic_increasing
        overlap = close[ticker].dropna().to_frame("sealed").join(p.rename("raw")).join(a.rename("adjusted")).dropna()
        overlap = overlap[(overlap > 0).all(axis=1)]
        # Retain the original admission's sanity check on this diagnostic input.
        raw_step = np.log(overlap.sealed / overlap.raw).diff().dropna().abs()
        valid = len(overlap) >= 260 and not ((raw_step > .05).mean() > .002 or raw_step.max() > .35)
        rows.append({"ticker": ticker, "status": "VERIFIED_OVERLAP" if valid else "BASIS_CHECK_REFUSED",
                     "overlapSessions": len(overlap), "start": index.min(), "end": index.max(),
                     "responseSha256": receipt["responseSha256"],
                     "maxLogSealedRawStep": raw_step.max(),
                     "maxLogSealedAdjustedStep": np.log(overlap.sealed / overlap.adjusted).diff().abs().max()})
        if valid:
            raw[ticker], adj[ticker] = p, a
    return (pd.DataFrame(raw).reindex(index=close.index, columns=names),
            pd.DataFrame(adj).reindex(index=close.index, columns=names), pd.DataFrame(rows))


def basis_frame(close, passive, sectors, dates, h, raw_close, adj_close):
    gross, sessions = endpoint_returns(close, dates, h)
    shift, shift_dates = endpoint_returns(close, dates, h, offset=0)
    raw, _ = endpoint_returns(raw_close, dates, h)
    adj, _ = endpoint_returns(adj_close, dates, h)
    rows, contribution = [], []
    benchmark = PRIOR / "results/US" / f"cohorts-{h}.csv.gz"
    reference = pd.read_csv(benchmark, parse_dates=["date"], usecols=["config", "date", "passive", "active", "funded"])
    reference = reference.loc[reference.config.eq("PRICE_CONFIRMED")].set_index("date").reindex(dates)
    for d in dates:
        b = passive[d]
        r = gross.loc[d]
        held = list(b)
        maturity = pd.notna(sessions.loc[d, "exit"])
        missing = r.loc[held].isna()
        valid = maturity and not missing.any() and np.isfinite(r.SPY)
        gross_b = weighted(r, b) if valid else np.nan
        net_b, net_spy = ev.net(gross_b), ev.net(r.SPY)
        shift_r, raw_r, adj_r = shift.loc[d], raw.loc[d], adj.loc[d]
        raw_b, adj_b = weighted(raw_r, b), weighted(adj_r, b)
        rows.append({"date": d, "entry": sessions.loc[d, "entry"], "exit": sessions.loc[d, "exit"],
                     "decisionCloseEntry": shift_dates.loc[d, "entry"], "decisionCloseExit": shift_dates.loc[d, "exit"],
                     "entryYear": sessions.loc[d, "entry"].year, "baseStockNames": len(b),
                     "status": "MEASURED" if valid else ("MISSING_PRICE" if maturity else "UNMATURED"),
                     "grossB": gross_b, "grossSPY": r.SPY, "netB": net_b, "netSPY": net_spy,
                     "netExcess": net_b-net_spy, "grossExcess": gross_b-r.SPY,
                     "costNetMinusGross": net_b-net_spy-(gross_b-r.SPY),
                     "decisionCloseGrossExcess": weighted(shift_r, b)-shift_r.SPY,
                     "decisionCloseNetExcess": NET_FACTOR*(weighted(shift_r, b)-shift_r.SPY),
                     "originalPassive": reference.loc[d, "passive"],
                     "originalPriceConfirmedActive": reference.loc[d, "active"],
                     "originalPriceConfirmedFunded": reference.loc[d, "funded"],
                     "originalPriceConfirmedBridgeError": (reference.loc[d, "funded"]
                         -reference.loc[d, "active"]-reference.loc[d, "passive"]),
                     "yahooRawB": raw_b, "yahooRawSPY": raw_r.SPY,
                     "yahooAdjustedB": adj_b, "yahooAdjustedSPY": adj_r.SPY,
                     "yahooMissingNames": "|".join(t for t in held if maturity and
                                                  (not np.isfinite(raw_r[t]) or not np.isfinite(adj_r[t]))),
                     "yahooMissingWeight": sum(b[t] for t in held if maturity and
                                              (not np.isfinite(raw_r[t]) or not np.isfinite(adj_r[t]))),
                     "heldPriceMissing": "|".join(missing[missing].index) if maturity else "",
                     "heldPriceMissingWeight": sum(b[t] for t in missing[missing].index) if maturity else np.nan})
        if not valid:
            continue
        assert abs(net_b-net_spy-NET_FACTOR*(gross_b-r.SPY)) < 1e-12
        for ticker, w in sorted(b.items()):
            sector = sectors[d].get(ticker, "UNCLASSIFIED")
            ticker_net = ev.net(r[ticker])
            contribution.append({"date": d, "entryYear": sessions.loc[d, "entry"].year,
                                 "ticker": ticker, "sector": sector, "cell": cell_name(sector, ticker),
                                 "weight": w, "netReturn": ticker_net, "netExcessContribution": w*(ticker_net-net_spy)})
    frame = pd.DataFrame(rows).set_index("date")
    assert frame.netExcess.notna().equals(frame.originalPassive.notna())
    errors = (frame.netExcess-frame.originalPassive).abs()
    assert errors.max() < 1e-12
    assert frame.originalPriceConfirmedBridgeError.abs().max() < 1e-12
    frame["grossMinusYahooAdjusted"] = frame.grossExcess-(frame.yahooAdjustedB-frame.yahooAdjustedSPY)
    frame["grossMinusYahooRaw"] = frame.grossExcess-(frame.yahooRawB-frame.yahooRawSPY)
    frame["yahooAdjustedExcess"] = frame.yahooAdjustedB-frame.yahooAdjustedSPY
    frame["yahooPriceOnlyExcess"] = frame.yahooRawB-frame.yahooRawSPY
    frame["yahooDistributionGap"] = frame.yahooAdjustedExcess-frame.yahooPriceOnlyExcess
    frame["yahooDistributionB"] = frame.yahooAdjustedB-frame.yahooRawB
    frame["yahooDistributionSPY"] = frame.yahooAdjustedSPY-frame.yahooRawSPY
    frame["sealedMinusYahooAdjustedB"] = frame.grossB-frame.yahooAdjustedB
    frame["sealedMinusYahooAdjustedSPY"] = frame.grossSPY-frame.yahooAdjustedSPY
    frame["decisionCloseMinusNextCloseNet"] = frame.decisionCloseNetExcess-frame.netExcess
    contribution = pd.DataFrame(contribution)
    recon = contribution.groupby("date").netExcessContribution.sum()-frame.netExcess
    assert recon.abs().max() < 1e-12
    return frame, contribution, ev.net(gross)


def number_range(x):
    return {"min": float(x.min()), "median": float(x.median()), "max": float(x.max())} if len(x.dropna()) else None


def stats(frame, cols, h, mask=None):
    return {c: cm.stats(frame[c], h, mask) for c in cols}


def disclosure_bridge(frame, assets, passive, report_support, h):
    results = {}
    for mode in ("strict", "endpointObserved"):
        rows = []
        for d in frame.index:
            row = {"date": d}
            if d not in report_support:
                rows.append({**row, "status": "NO_PUBLISHED_REPORT"})
                continue
            if frame.loc[d, "status"] != "MEASURED":
                rows.append({**row, "status": frame.loc[d, "status"]})
                continue
            report = report_support[d]
            net_r = assets.loc[d]
            names = list(report["weights"])
            valid = net_r.reindex(names).dropna().index
            missing = sorted(set(names)-set(valid))
            balances = report["weights"]
            observed = {t: balances[t] for t in valid}
            row.update(accession=report["accession"], strictNames=len(names),
                       endpointObservedNames=len(observed), endpointMissingNames="|".join(missing),
                       endpointMissingReportNetWeight=sum(balances[t] for t in missing),
                       availableReportNetWeight=sum(observed.values()))
            if missing and mode == "strict":
                rows.append({**row, "status": "MISSING_DISCLOSED_ENDPOINT"})
                continue
            books = bridge_books(passive[d], balances if mode == "strict" else observed, report["sectors"])
            if not books:
                rows.append({**row, "status": "NO_COMMON_SUPPORT"})
                continue
            split = bridge_values(net_r, net_r.SPY, books)
            assert np.isfinite(list(split.values())).all()
            error = split["proxyNetExcess"] - sum(split[x] for x in COMPONENTS)
            sub = split["sectorAndMegaWeight"] - split["sectorWeightOnly"] - split["megaWithinSectorWeight"]
            assert abs(error) < 1e-12 and abs(sub) < 1e-12
            assert abs(split["proxyNetExcess"] - frame.loc[d, "netExcess"]) < 1e-12
            b, c, lc, ls = (books[x] for x in ("B", "BC", "LC", "LS"))
            groups = {t: report["sectors"][t] for t in ls}
            cells = {t: cell_name(groups[t], t) for t in ls}
            rows.append({**row, "status": "MEASURED", **split, "sumError": error, "sectorSumError": sub,
                         "commonNames": len(c), "observedReportNamesOutsideB": len(ls.keys()-b.keys()),
                         "proxyCommonWeight": sum(b[t] for t in c),
                         "commonSectorL1": distance(sum_weights(c, groups), sum_weights(lc, groups)),
                         "commonSectorMegaCellL1": distance(sum_weights(c, cells), sum_weights(lc, cells)),
                         "commonTickerL1": distance(c, lc),
                         "commonMegaProxyWeight": sum(c.get(t, 0) for t in MEGA),
                         "commonMegaReportedWeight": sum(lc.get(t, 0) for t in MEGA)})
        results[mode] = df = pd.DataFrame(rows).set_index("date")
        assert df.index.equals(frame.index)
    report_available = frame.index.isin(report_support)
    summary = {"allBaseline": cm.stats(frame.netExcess, h),
               "withPublishedReport": cm.stats(frame.netExcess, h, report_available),
               "withoutPublishedReport": cm.stats(frame.netExcess, h, ~report_available)}
    summary["withMinusAllMean"] = summary["withPublishedReport"]["mean"] - summary["allBaseline"]["mean"]
    cols = ("proxyNetExcess", *COMPONENTS, "sectorWeightOnly", "megaWithinSectorWeight")
    full_n = int(frame.netExcess.notna().sum())
    for mode, df in results.items():
        measured = df.loc[df.status.eq("MEASURED")]
        measured_mask = df.status.eq("MEASURED")
        components = {c: float(measured[c].sum()/full_n) for c in COMPONENTS}
        outside = float(frame.loc[~measured_mask, "netExcess"].sum()/full_n)
        assert abs(sum(components.values()) + outside - frame.netExcess.mean()) < 1e-12
        missing = df.loc[df.endpointMissingNames.fillna("").ne(""), "endpointMissingNames"].str.split("|").explode()
        summary[mode] = {"components": stats(df, cols, h), "statusCounts": df.status.value_counts().to_dict(),
                         "first": measured.index.min(), "last": measured.index.max(),
                         "fullOriginalSampleAttribution": {"n": full_n, "bridgeN": len(measured),
                             "components": components, "outsideBridgeContributionToFullMean": outside,
                             "outsideBridge": cm.stats(frame.netExcess, h, ~measured_mask)},
                         "endpointMissingReportNetWeight": number_range(df.endpointMissingReportNetWeight),
                         "missingEndpointTickersByWeek": missing.value_counts().to_dict(),
                         "endpointMissingReportNetWeightOnAffectedWeeks": number_range(
                             df.loc[df.endpointMissingNames.fillna("").ne(""), "endpointMissingReportNetWeight"]),
                         "availableReportNetWeight": number_range(measured.availableReportNetWeight),
                         "commonNames": number_range(measured.commonNames),
                         "observedReportNamesOutsideB": number_range(measured.observedReportNamesOutsideB),
                         "commonSectorL1": number_range(measured.commonSectorL1),
                         "commonSectorMegaCellL1": number_range(measured.commonSectorMegaCellL1),
                         "commonTickerL1": number_range(measured.commonTickerL1),
                         "commonMegaProxyWeight": number_range(measured.commonMegaProxyWeight),
                         "commonMegaReportedWeight": number_range(measured.commonMegaReportedWeight),
                         "maxSumError": float(measured.sumError.abs().max()),
                         "maxSectorSumError": float(measured.sectorSumError.abs().max())}
    return results, summary


def attribution_summary(frame, contribution, h):
    eligible = frame.netExcess.notna()
    n = int(eligible.sum())
    groupings = {"ticker": ["ticker"], "sector": ["sector"], "cell": ["cell"],
                 "yearCell": ["entryYear", "cell"], "yearTicker": ["entryYear", "ticker"]}
    agg = {}
    for name, groups in groupings.items():
        t = contribution.groupby(groups, sort=True).agg(
            measuredHoldingWeeks=("date", "nunique"),
            summedContribution=("netExcessContribution", "sum"),
            summedEntryWeight=("weight", "sum")).reset_index()
        t["contributionToFullMean"] = t.summedContribution/n
        t["weightOnFullWeeklySample"] = t.summedEntryWeight/n
        assert abs(t.contributionToFullMean.sum()-frame.netExcess.mean()) < 1e-12
        agg[name] = t.sort_values(["contributionToFullMean", *groups], ascending=[False]+[True]*len(groups))
    years = sorted(frame.entryYear.loc[eligible].astype(int).unique())
    year_rows = []
    for y in years:
        same = frame.entryYear.eq(y)
        m = cm.stats(frame.netExcess, h, same)
        contribution_to_full = m["mean"]*m["n"]/n
        year_rows.append({"entryYear": y, "contributionToFullMean": contribution_to_full, **m})
    agg["year"] = pd.DataFrame(year_rows)
    assert abs(agg["year"].contributionToFullMean.sum()-frame.netExcess.mean()) < 1e-12
    name = agg["ticker"].iloc[0].ticker
    omit_year = max(year_rows, key=lambda t: t["contributionToFullMean"])["entryYear"]
    include_year = frame.entryYear.eq(omit_year)
    strongest = contribution.loc[contribution.ticker.eq(name)].set_index("date").netExcessContribution
    # A date with no position in this ticker has zero contribution by definition.
    remaining = frame.netExcess - strongest.reindex(frame.index, fill_value=0.)
    all_mega = contribution.loc[contribution.ticker.isin(MEGA)].groupby("date").netExcessContribution.sum()
    scenarios = {
        "noMaxTickerContribution": cm.stats(remaining, h),
        "maxTickerActiveContribution": cm.stats(frame.netExcess-remaining, h),
        "noMaxEntryYear": cm.stats(frame.netExcess, h, ~include_year),
        "maxEntryYearOnly": cm.stats(frame.netExcess, h, include_year),
        "no2021Entry": cm.stats(frame.netExcess, h, ~frame.entryYear.eq(2021)),
        "entry2021Only": cm.stats(frame.netExcess, h, frame.entryYear.eq(2021)),
        "noMegaContribution": cm.stats(frame.netExcess-all_mega.reindex(frame.index, fill_value=0.), h),
        "megaContribution": cm.stats(all_mega.reindex(frame.index, fill_value=0.).where(eligible), h),
    }
    return agg, {"maxTicker": name, "maxTickerHoldingWeeks": len(strongest), "maxEntryYear": omit_year,
                 "maxEntryYearContributionToFullMean": max(y["contributionToFullMean"] for y in year_rows),
                 "scenarios": scenarios}


def basis_summary(frame, qqq_net, h):
    own = ("grossB", "grossSPY", "netB", "netSPY", "netExcess", "grossExcess", "costNetMinusGross",
           "originalPriceConfirmedActive", "originalPriceConfirmedFunded")
    date_timing = ("netExcess", "decisionCloseNetExcess", "decisionCloseMinusNextCloseNet")
    yahoo_fields = ("grossExcess", "yahooAdjustedExcess", "yahooPriceOnlyExcess", "yahooDistributionGap",
                    "yahooDistributionB", "yahooDistributionSPY", "sealedMinusYahooAdjustedB",
                    "sealedMinusYahooAdjustedSPY", "grossMinusYahooAdjusted", "grossMinusYahooRaw")
    measured = frame.netExcess.notna()
    the_rest = frame.loc[measured & frame.yahooMissingNames.ne(""), "yahooMissingNames"].str.split("|").explode()
    matched_yahoo = measured & frame[list(yahoo_fields)].notna().all(axis=1)
    no_spy_path = frame.grossSPY-frame.yahooAdjustedSPY
    price_check = frame.grossExcess-(frame.yahooPriceOnlyExcess + frame.yahooDistributionGap + frame.grossMinusYahooAdjusted)
    assert price_check.abs().max() < 1e-12
    return {"netGross": stats(frame, own, h, measured),
            "dateTiming": stats(frame, date_timing, h, measured & frame.decisionCloseNetExcess.notna()),
            "yahooPaths": stats(frame, yahoo_fields, h, matched_yahoo),
            "spyOnlySealedMinusYahooAdjusted": cm.stats(no_spy_path, h, measured),
            "netExcessVsQQQ": cm.stats(frame.netB-qqq_net, h),
            "statusCounts": frame.status.value_counts().to_dict(),
            "cohortFirst": frame.loc[measured, "entry"].min(), "cohortLast": frame.loc[measured, "exit"].max(),
            "yahooMissingFullBookDates": int((measured & ~matched_yahoo).sum()),
            "yahooMissingNamesByWeek": the_rest.value_counts().to_dict(),
            "yahooMissingBookWeights": number_range(frame.loc[measured & ~matched_yahoo, "yahooMissingWeight"]),
            "maxYahooBasisIdentityError": float(price_check.abs().max()),
            "maxPriorParityError": float((frame.netExcess-frame.originalPassive).abs().max()),
            "maxPriorActiveBridgeError": float(frame.originalPriceConfirmedBridgeError.abs().max())}


def ledger_reuse(first_wat_fill):
    """Reconcile stored #351 same-day NAV results with the original evaluator."""
    root = PRIOR / "results/US"
    reported = json.loads((root / "funded-ledgers.json").read_text())
    out = {}
    for cadence in ("L26", "L52"):
        p = root / f"funded-nav-{cadence}.csv.gz"
        dates = pd.read_csv(p, index_col=0, parse_dates=True, usecols=["Unnamed: 0", "ETF", "PASSIVE", "QQQ"])
        found = cm.nav_window(dates.PASSIVE, dates.ETF)
        old = reported[cadence]["PASSIVE"]
        error = max(abs(found[k]-old[k]) for k in found if isinstance(found[k], float))
        assert error < 1e-12
        benchmark = cm.nav_window(dates.ETF, dates.ETF)
        out[cadence] = {"originalPassive": old, "spy": benchmark, "priorNAVSha256": sha(p),
                        "prefixBeforeAbnormalWATFill": cm.nav_window(
                            dates.loc[dates.index < first_wat_fill, "PASSIVE"],
                            dates.loc[dates.index < first_wat_fill, "ETF"]),
                        "recheckMaxError": error, "initialFeeSPY": ev.BUY,
                        "spyAnnualOneWayTurnoverIncludingInitialBuy": 1/(2*benchmark["years"]),
                        "spyAnnualOneWayTurnoverAfterInitialBuy": 0.}
    return out


def wat_exposure_diagnostic(private, close, dates, passive):
    """Audit the WAT input anomaly observed in the late disclosure exposure table."""
    first_anomaly = pd.Timestamp("2026-05-15")
    weights = pd.Series({d: w.get("WAT", 0.) for d, w in passive.items()}, name="priorProxyWeight")
    assert weights.index[weights.gt(.01)].equals(dates[dates >= first_anomaly])
    f = pd.read_pickle(private / "features.pkl")
    selected = f.loc[f.ticker.eq("WAT") & f.date.ge("2026-05-15"),
                     ["date", "asTradedClose", "sharesForProxy", "sharesVisibleDay", "marketCap"]].copy()
    selected["date"] = pd.to_datetime(selected.date)
    selected = selected.set_index("date").join(weights, how="inner").reset_index()
    first_fill = close.index[close.index.get_loc(first_anomaly)+1]
    filing_receipts, filings_hash = [], None
    source, receipt = (private / name for name in ("filings.pkl", "core-input-receipt.json"))
    missing = [p.name for p in (source, receipt) if not p.is_file()]
    status = "CACHED_REPORT_ROWS_CROSS_CHECKED"
    if missing:
        status = "FILINGS_OR_INPUT_RECEIPT_UNAVAILABLE"
    else:
        filings_hash = sha(source)
        if filings_hash != json.loads(receipt.read_text())["filingsSha256"]:
            status = "FILINGS_HASH_MISMATCH"
    if status == "CACHED_REPORT_ROWS_CROSS_CHECKED":
        with source.open("rb") as f:
            wat = pickle.load(f)["raw"]["WAT"]
        for row in wat:
            if row["accession"] not in ("0001193125-26-219487", "0001193125-26-344691"):
                continue
            numbers = {c["concept"]: c["value"] for c in row["statements"]["ic"]}
            ni = numbers["us-gaap_NetIncomeLoss"]
            eps = numbers["us-gaap_EarningsPerShareDiluted"]
            shares = numbers["us-gaap_WeightedAverageNumberOfDilutedSharesOutstanding"]
            implied = ni / eps
            filing_receipts.append({"accession": row["accession"], "visibleFrom": row["availableFrom"],
                                    "periodEnd": row["periodEnd"], "reportedDilutedSharesField": shares,
                                    "netIncome": ni, "dilutedEps": eps, "netIncomeDividedByEps": implied,
                                    "reportedSharesToImpliedRatio": shares / implied})
        assert len(filing_receipts) == 2 and all(
            980 < row["reportedSharesToImpliedRatio"] < 1020 for row in filing_receipts)
    info = {"label": "POST_HOC_SOURCE_DIAGNOSTIC_ORIGINAL_WEIGHTS_UNCHANGED",
            "firstDecision": first_anomaly, "firstExecution": first_fill,
            "weeks": len(selected), "weightRange": number_range(selected.priorProxyWeight),
            "filingReceipts": filing_receipts, "filingsSha256": filings_hash,
            "sourceStatus": status, "missingSourceFiles": missing}
    return selected, info


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", type=Path, required=True)
    ap.add_argument("--inputs", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=HERE / "results/US")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    payload, close, input_hash = load_frozen(a.private, a.inputs)
    dates, passive = payload["dates"], payload["passive"]
    assert len(dates) == 654
    wat, wat_info = wat_exposure_diagnostic(a.private, close, dates, passive)
    csv(a.out / "wat-tail-exposure.csv.gz", wat)
    report_support, coverage, support_lines = published_reports(a.private, close, passive, dates)
    csv(a.out / "report-coverage.csv.gz", coverage.reset_index())
    csv(a.out / "report-support-lines.csv.gz", support_lines)
    raw, adjusted, prices = yahoo_price_panels(a.private, close, passive)
    csv(a.out / "alternate-price-sources.csv.gz", prices)
    spy_bundle = pd.read_csv(ROOT / "data/research/us-dual-benchmark-v1/spy-qqq-total-return.csv.gz")
    spy_bundle = spy_bundle.loc[spy_bundle.ticker.eq("SPY")].set_index(pd.to_datetime(
        spy_bundle.loc[spy_bundle.ticker.eq("SPY"), "date"]))
    report_stats = {c: number_range(coverage[c]) for c in coverage.select_dtypes(include="number")}
    summary = {"market": "US", "weeklyAxis": len(dates),
               "firstDecisionDate": dates.min(), "lastDecisionDate": dates.max(),
               "historyReused": True, "inputSha256": input_hash, "buy": ev.BUY, "sell": ev.SELL,
               "netAffineFactor": NET_FACTOR, "horizons": {},
               "ledgers": ledger_reuse(wat_info["firstExecution"]), "watTailDiagnostic": wat_info,
               "reportCoverage": {"sourceReports": 28, "usableDistinctReports": coverage.accession.nunique(),
                                  "decisionWeeks": len(report_support), "firstAvailable": min(report_support),
                                  "lastAvailable": max(report_support),
                                  "completeReplicaWeeks": int(coverage.reportKnownFullReplica.eq(True).sum()),
                                  "mappingIsPITProved": False, "ranges": report_stats},
               "spyPriceSource": {"sealedComparisonMaxRelError":
                     float((spy_bundle.totalReturnClose/close.SPY-1).abs().max()),
                     "bundleDistributionsRecorded": int(spy_bundle.dividend.ne(0).sum()),
                     "bundleRawEqualsTR": bool(spy_bundle.rawClose.eq(spy_bundle.totalReturnClose).all()),
                     "separateYahooAdjAndSplitOnlyPriceUsedAsDiagnostic": True}}
    for h, expected in zip(HORIZONS, (630, 604), strict=True):
        frame, contribution, returns = basis_frame(close, passive, payload["sectors"], dates, h, raw, adjusted)
        assert frame.netExcess.notna().sum() == expected
        assert frame.loc[wat_info["firstDecision"]:, "status"].eq("UNMATURED").all()
        assert frame.entry.equals(payload["entries"][h])
        prior_net = payload["net_asset"][h]
        pd.testing.assert_frame_equal(returns, prior_net)
        bridge_frames, bridge = disclosure_bridge(frame, returns, passive, report_support, h)
        attrib_frames, sensitivity = attribution_summary(frame, contribution, h)
        baseline = basis_summary(frame, payload["qqq"][h], h)
        csv(a.out / f"cohorts-{h}.csv.gz", frame.reset_index())
        csv(a.out / f"full-contribution-{h}.csv.gz", contribution)
        for name, t in bridge_frames.items():
            csv(a.out / f"bridge-{name}-{h}.csv.gz", t.reset_index())
        for name, t in attrib_frames.items():
            csv(a.out / f"{name}-contribution-{h}.csv.gz", t)
        summary["horizons"][str(h)] = {"baseline": baseline, "bridge": bridge, "sensitivity": sensitivity}
        print(f"US h={h}: original={expected}, strict={bridge['strict']['components']['proxyNetExcess']['n']}, "
              f"endpointObserved={bridge['endpointObserved']['components']['proxyNetExcess']['n']}", flush=True)
    batch.save(a.out / "summary.json", summary)


if __name__ == "__main__":
    main()
