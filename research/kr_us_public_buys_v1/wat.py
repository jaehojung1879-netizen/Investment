"""Rebuild PR #351/352 US schedules with point-in-time verified share counts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.kr_us_exposure_preserving_v1 import engine, nav
from research.kr_us_public_buys_v1 import wat_sources
from research.kr_us_replica_filter_v1 import us as baseline
from research.kr_us_strategy_batch_v1 import common as cm
from research.kr_us_strategy_batch_v1 import us as batch
from research.us_selection_value_v1 import evaluate as ev

HERE = Path(__file__).resolve().parent
HORIZONS = (126, 252)
REGIMES = ("WAT_UNIT_ONLY", "WAT_WHOLE", "ALL_VERIFIED")


def verified_wat_caps(feats, dates, source):
    rows = []
    f = feats.loc[feats.ticker.eq("WAT") & feats.date.isin(dates)].sort_values("date")
    sources = source["shares"]
    # The first observed post-closing share total is the cover of the February 23 10-K.
    # The 8-K disclosed an issuance, so the total is unconfirmed until that cover.
    for item in f.itertuples(index=False):
        cutoff = wat_sources.decision_close(item.date)
        visible = [s for s in sources if pd.Timestamp(s["acceptedET"]) < cutoff
                   and pd.Timestamp(s["shareAsOf"]) <= item.date]
        if not visible:
            continue
        fact = max(visible, key=lambda s: s["acceptedET"])
        assert np.isfinite(item.marketCap) and np.isfinite(item.asTradedClose)
        regime = "WAT_UNIT_OF_WEIGHTED_AVERAGE_FIELDS" if item.date >= pd.Timestamp("2026-05-15") else "WAT_POST_MERGER_SHARE_CUTOFF"
        rows.append({"date": item.date, "ticker": item.ticker, "correctedMarketCap": item.asTradedClose*fact["shares"],
                     "sourceId": fact["sourceId"], "case": regime, "previousMarketCap": item.marketCap,
                     "previousShares": item.sharesForProxy, "confirmedActualShares": fact["shares"],
                     "rawAsTradedPrice": item.asTradedClose, "shareAsOf": fact["shareAsOf"],
                     "acceptedET": fact["acceptedET"], "sourceURL": fact["document"]["url"]})
    return pd.DataFrame(rows)


def load_inputs(private, inputs):
    p, close, hashes = baseline.load_frozen(private, inputs)
    f = pd.read_pickle(private / "features.pkl")
    f["date"] = pd.to_datetime(f.date)
    f = f.loc[f.date.isin(p["dates"])].copy()
    return p, close, hashes, f


def next_close(close, day):
    return close.index[close.index.get_loc(day)+1]


def book_dist(a, b):
    return sum(abs(a.get(t, 0.)-b.get(t, 0.)) for t in sorted(set(a) | set(b)))


def data_rows(by_date, d):
    return by_date[d].copy()


def rebuild(p, f, corrections, original):
    """Regenerate affected dates with only the proved share inputs substituted."""
    replacement = {k: value.copy() for k, value in original.items()}
    for d, g in corrections.groupby("date"):
        day = data_rows(f, d)
        changed = g.set_index("ticker").correctedMarketCap
        for t, v in changed.items():
            selection = day.ticker.eq(t)
            assert selection.sum() == 1 and np.isfinite(v) and v > 0
            day.loc[selection, "marketCap"] = v
        cap = day.set_index("ticker").loc[list(original["B"][d]), "marketCap"].astype(float)
        assert cap.gt(0).all()
        fixed_b = (cap/cap.sum()).to_dict()
        x = ev.score(ev.common(day))
        fixed_native = batch.native_book(x, "U1", d)
        oq = original["U1_20"][d]
        transformed = batch.normalize_stock(fixed_native, .2)
        if book_dist(oq, transformed) < 1e-12:
            transformed = oq
        funded, _, _ = engine.redistribute(
            fixed_b, {t: w for t, w in transformed.items() if t != "SPY" and w > 0},
            p["sectors"][d], p["leaders"])
        replacement["B"][d] = fixed_b
        replacement["U1_NATIVE"][d] = fixed_native
        replacement["U1_20"][d] = transformed
        replacement["U1_FUNDED"][d] = funded
    return replacement


def choose_rows(corrections, case):
    if case == "ALL_VERIFIED":
        return corrections
    condition = corrections.ticker.eq("WAT")
    if case == "WAT_UNIT_ONLY":
        condition &= corrections.case.eq("WAT_UNIT_OF_WEIGHTED_AVERAGE_FIELDS")
    return corrections.loc[condition]


def validate_original(p, f, corrections, original):
    for d in sorted(corrections.date.unique()):
        group = data_rows(f, d)
        valid = group.identity.isin(baseline.VALID_ID) & group.marketCap.gt(0)
        caps = group.loc[valid].set_index("ticker").marketCap
        original_b = original["B"][d]
        assert set(caps.index) == set(original_b)
        assert book_dist((caps/caps.sum()).to_dict(), original_b) < 1e-12
        model = batch.native_book(ev.score(ev.common(group)), "U1", d)
        assert book_dist(model, original["U1_NATIVE"][d]) < 1e-12
        assert book_dist(batch.normalize_stock(model, .2), original["U1_20"][d]) < 1e-12
        replication, _, _ = engine.redistribute(original_b, {
            t: w for t, w in original["U1_20"][d].items() if t != "SPY" and w > 0
        }, p["sectors"][d], p["leaders"])
        assert book_dist(replication, original["U1_FUNDED"][d]) < 1e-12


def weights_table(original, replacement, corrections):
    rows = []
    corrected = {(r.date, r.ticker) for r in corrections.itertuples(index=False)}
    for book, bydate in replacement.items():
        for date, w in bydate.items():
            older = original[book][date]
            if book_dist(older, w) < 1e-12:
                continue
            for t in sorted(set(w) | set(older)):
                a, b = older.get(t, 0.), w.get(t, 0.)
                if abs(a-b) > 1e-12:
                    rows.append({"book": book, "date": date, "ticker": t, "oldWeight": a, "newWeight": b,
                                 "weightChange": b-a, "inputCorrected": (date, t) in corrected})
    return rows


def cohorts(p, original, replacement, case):
    rows = []
    horizon_stats = {}
    for h in HORIZONS:
        values = p["net_asset"][h]
        tf = p["entries"][h]
        spy = values.SPY
        q = p["qqq"][h]
        summaries = {}
        for book in replacement:
            old, new = (pd.Series({d: baseline.weighted(values.loc[d], w) for d, w in sched.items()})
                        for sched in (original[book], replacement[book]))
            common = old.notna() & new.notna() & spy.notna()
            changed = pd.Series({
                d: book_dist(w, replacement[book][d]) >= 1e-12 for d, w in original[book].items()})
            delta = new-old
            summaries[book] = {"originalVsSPY": cm.stats(old-spy, h, common),
                              "correctedVsSPY": cm.stats(new-spy, h, common),
                              "correctedMinusOriginal": cm.stats(delta, h, common),
                              "correctedMinusOriginalChangedDates": cm.stats(delta, h, common & changed),
                              "targetChangedWeeks": int(changed.sum()), "matureTargetChangedWeeks": int((changed & tf.notna()).sum()),
                              "lostPriceWeeks": int((old.notna() & new.isna()).sum()),
                              "gainedPriceWeeks": int((old.isna() & new.notna()).sum()),
                              "samePriceSample": old.notna().equals(new.notna()),
                              "maximumAbsolutePayoffDelta": float(delta.abs().max()),
                              "correctedVsQQQ": cm.stats(new-q, h, common & q.notna())}
            for d in p["dates"]:
                rows.append({"case": case, "horizon": h, "book": book, "date": d, "entry": tf.at[d],
                             "targetChanged": changed.at[d], "oldNetExcessSPY": old.at[d]-spy.at[d],
                             "newNetExcessSPY": new.at[d]-spy.at[d], "netChange": delta.at[d],
                             "oldStatus": "MEASURED" if pd.notna(old.at[d]) else "UNMATURED" if pd.isna(tf.at[d]) else "UNRESOLVED",
                             "newStatus": "MEASURED" if pd.notna(new.at[d]) else "UNMATURED" if pd.isna(tf.at[d]) else "UNRESOLVED"})
        horizon_stats[str(h)] = summaries
    return rows, horizon_stats


def compute_account(price, schedule, phase_dates):
    fill = {price.index[1]: {"SPY": 1.}}
    for d in phase_dates:
        fill[next_close(price, d)] = schedule[d]
    needed = sorted(set().union(*(w.keys() for w in fill.values())))
    account, _ = nav.us_account(price.loc[:, needed], fill)
    return account


def summarize_nav(account, spy, qqq):
    metrics = cm.nav_window(account.nav, spy.nav)
    metrics["oneWayTurnoverPerYear"] = float(account.twoWayTurnover.sum()/2/metrics["years"])
    metrics["costPerYear"] = float(account.costInitialCapital.sum()/metrics["years"])
    metrics["vsQQQ"] = cm.nav_window(account.nav, qqq.nav)
    return metrics


def run_ledgers(p, close, original, scenarios, out, wat_cache=None):
    dates = p["dates"]
    prices = close.loc[dates[0]:].copy()
    # #351 uses the 2020-09-21 corrected QQQ close file, not the cohort return.
    qdata = pd.read_csv(baseline.ROOT / "data/research/us-dual-benchmark-v1/spy-qqq-total-return.csv.gz")
    prior_raw = qdata.loc[qdata.ticker.eq("QQQ") & qdata.date.lt(ev.QQQ_FIX[0]), "rawClose"].iloc[-1]
    prices.loc[ev.QQQ_FIX[0]:, "QQQ"] *= 1 + ev.QQQ_FIX[1]/prior_raw
    spy, _ = nav.us_account(prices[["SPY"]], {prices.index[1]: {"SPY": 1.}})
    qqq, _ = nav.us_account(prices[["QQQ"]], {prices.index[1]: {"QQQ": 1.}})
    outputs = {}
    cached = json.loads((wat_cache/"summary.json").read_text())["ledgers"] if wat_cache else None
    for interval in (26, 52):
        navs = {"SPY": spy.nav, "QQQ": qqq.nav}
        summary = {}
        old_path = pd.read_csv(
            baseline.PRIOR / f"results/US/funded-nav-L{interval}.csv.gz", index_col=0, parse_dates=True)
        np.testing.assert_allclose(qqq.nav, old_path.QQQ, atol=1e-12, rtol=0)
        stored = pd.read_csv(wat_cache/f"ledgers-L{interval}.csv.gz", index_col="date", parse_dates=True) if wat_cache else None
        for book, source in original.items():
            if book == "U1_20":
                continue
            phases = [dates[i::interval] for i in range(interval)]
            accounts = {}
            if stored is None:
                accounts = {i: compute_account(prices, source, phase) for i, phase in enumerate(phases)}
                old = sum(accounts.values())/interval
                old_nav = old.nav
                old_metrics = summarize_nav(old, spy, qqq)
            else:
                old_nav = stored[book+"_ORIGINAL"]
                old_metrics = cached[f"L{interval}"][book]["old"]
                verified = cm.nav_window(old_nav, spy.nav)
                assert abs(verified["cagr"]-old_metrics["cagr"]) < 1e-12
                assert abs(verified["mdd"]-old_metrics["mdd"]) < 1e-12
            navs[book+"_ORIGINAL"] = old_nav
            if book in ("B", "U1_FUNDED"):
                np.testing.assert_allclose(old_nav, old_path["PASSIVE" if book == "B" else "U1"],
                                           atol=3e-12, rtol=0)
            summary[book] = {"old": old_metrics}
            for case, replacement in scenarios.items():
                if stored is not None and case != "ALL_VERIFIED":
                    navs[f"{book}_{case}"] = stored[f"{book}_{case}"]
                    summary[book][case] = cached[f"L{interval}"][book][case]
                    continue
                target = replacement[book]
                changed = {d for d in dates if book_dist(source[d], target[d]) >= 1e-12}
                revised = []
                for i, phase in enumerate(phases):
                    if any(d in changed for d in phase):
                        revised.append(compute_account(prices, target, phase))
                    else:
                        if i not in accounts:
                            accounts[i] = compute_account(prices, source, phase)
                        revised.append(accounts[i])
                new = sum(revised)/interval
                navs[f"{book}_{case}"] = new.nav
                new_metrics = summarize_nav(new, spy, qqq)
                first_d = min(changed) if changed else None
                first_exec = next_close(prices, first_d) if first_d else None
                delta = new.nav-old_nav
                if first_exec is not None:
                    assert delta.loc[delta.index < first_exec].abs().max() < 1e-12
                summary[book][case] = {"new": new_metrics, "firstChangedDecision": first_d,
                                       "firstChangedExecution": first_exec, "weeks": len(changed),
                                       "firstChangedNAV": delta.loc[delta.abs().gt(1e-12)].index.min() if
                                                   delta.abs().gt(1e-12).any() else None,
                                       "endNAVDeltaPct": float(new.nav.iloc[-1]/old_nav.iloc[-1]-1),
                                       "cagrChange": new_metrics["cagr"]-old_metrics["cagr"],
                                       "mddChange": new_metrics["mdd"]-old_metrics["mdd"]}
            print(f"US {book} L{interval} complete", flush=True)
        navs = pd.DataFrame(navs)
        baseline.csv(out / f"ledgers-L{interval}.csv.gz", navs.rename_axis("date").reset_index())
        outputs[f"L{interval}"] = summary
    return outputs


def main(argv=None):
    a0 = argparse.ArgumentParser(description=__doc__)
    a0.add_argument("--private", type=Path, default=Path("/workspace/batch-inputs/us"))
    a0.add_argument("--inputs", type=Path, default=Path("/workspace/exposure-inputs/us"))
    a0.add_argument("--out", type=Path, default=HERE / "results/WAT")
    a0.add_argument("--caps-only", action="store_true")
    a0.add_argument("--reuse-wat-check", type=Path, help="Reuse an independently generated WAT-only ledger cache.")
    a = a0.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    p, close, hashes, f = load_inputs(a.private, a.inputs)
    source = json.loads((a.out/"wat-sec-receipts.json").read_text())
    wat = verified_wat_caps(f, p["dates"], source)
    other = a.out/"verified-non-wat-caps.csv"
    corrected = pd.concat([wat, pd.read_csv(other, parse_dates=["date"])], ignore_index=True) if other.is_file() else wat
    assert not corrected[["date", "ticker"]].duplicated().any()
    corrected.sort_values(["date", "ticker"]).to_csv(a.out/"corrected-caps.csv", index=False)
    if a.caps_only:
        return
    if a.reuse_wat_check:
        state = json.loads((a.reuse_wat_check/"summary.json").read_text())
        assert state["inputSha256"] == hashes and state["correctedCapRows"] == len(wat)
        expected = pd.read_csv(a.reuse_wat_check/"corrected-caps.csv", parse_dates=["date"])
        pd.testing.assert_frame_equal(wat.reset_index(drop=True), expected)
    by_date = dict(tuple(f.groupby("date", sort=False)))
    original = {"B": p["passive"], "U1_NATIVE": p["native"]["U1"], "U1_20": p["books"]["U1"],
                "U1_FUNDED": nav.load_books(baseline.PRIOR / "results/US/funding-book-schedules.json.gz")["U1"]}
    validate_original(p, by_date, corrected, original)
    comp = {}
    horizons, weight_rows, cohorts_rows = {}, [], []
    for case in REGIMES:
        using = choose_rows(corrected, case)
        comp[case] = rebuild(p, by_date, using, original)
        weight_rows.extend({"case": case, **r} for r in weights_table(original, comp[case], using))
        c, result = cohorts(p, original, comp[case], case)
        cohorts_rows.extend(c)
        horizons[case] = result
        print(f"US corrected {case} {len(using)} cap rows; cohort calculations complete", flush=True)
    baseline.csv(a.out/"target-weight-deltas.csv.gz", pd.DataFrame(weight_rows))
    baseline.csv(a.out/"cohorts.csv.gz", pd.DataFrame(cohorts_rows))
    ledgers = run_ledgers(p, close, original, comp, a.out, a.reuse_wat_check)
    batch.save(a.out/"summary.json", {"horizons": horizons, "ledgers": ledgers,
               "inputSha256": hashes, "correctedCapRows": len(corrected),
               "correctionsByCase": corrected.case.value_counts().to_dict()})


if __name__ == "__main__":
    main()
