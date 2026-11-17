"""Frozen S2 prefix ladder; see PREREGISTRATION.md. Research only, no live writes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.alpha_search_round6_v1 import common as CM
from research.alpha_search_round6_v1 import kr as K6

KD, RC, A, M, C = K6.KD, K6.RC, K6.A, K6.M, K6.C
HERE = Path(__file__).resolve().parent
SEED, DRAWS, PATHS = 20261117, 4000, 5
LABEL = "FOLLOW_UP_ON_OUTCOME_EXPOSED_HISTORY_NOT_PROSPECTIVE"


def dump(path, obj):
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=str, allow_nan=False) + "\n")


def book(names):
    out = {t: 0.2 for t in names}
    if len(names) < 5:
        out[M.ETF] = 0.2 * (5 - len(names))
    return out


def build(ctx, base):
    books = {f"N{k}": {} for k in range(6)}
    random = {f"R{p}_{k}": {} for p in range(PATHS) for k in range(6)}
    matched, audit, ranks = {}, [], []
    for d in base["dates"]:
        g = ctx.by[d].sort_values("ticker").copy()
        original, picks, _ = C.sleeve_book("S2_VALUE_CONFIRMED", g)
        assert original == base["s2"][d], f"S2_CACHE_DISAGREES:{d}"
        score = C.sleeve_score("S2_VALUE_CONFIRMED", g)
        eligible = g.loc[g["_q"] & score.notna() & ~g["ticker"].isin(C.WITHHELD)].assign(_score=score)
        eligible = eligible.sort_values(["_score", "ticker"], ascending=[False, True])
        assert list(eligible.head(5)["ticker"]) == picks
        pool = sorted(eligible["ticker"])
        assert pool == base["eligible"][d], f"ELIGIBLE_CACHE_DISAGREES:{d}"
        for i, (_, row) in enumerate(eligible.iterrows(), 1):
            ranks.append({"date": d, "rank": i, "ticker": row.ticker, "score": row[RC.SCORE],
                          "industry": row.industry, "marketCap": row["_mcap"], "inOriginalTop5": i <= 5})
        gi = g.set_index("ticker")
        candidates = g.loc[~g["ticker"].isin(C.WITHHELD)]
        controls = M.matched_controls(candidates, picks, ["_mcap"])
        matched[d] = controls
        permutations = {p: np.random.default_rng([SEED, p, d.toordinal()]).permutation(pool).tolist() for p in range(PATHS)}
        for k in range(6):
            selected = picks[:k]
            books[f"N{k}"][d] = book(selected)
            for p in range(PATHS):
                random[f"R{p}_{k}"][d] = book(permutations[p][:len(selected)])
            audit.append({"date": d, "requested": k, "actual": len(selected), "eligible": len(pool),
                          "shortfall": len(selected) < k, "etfWeight": 1 - 0.2 * len(selected),
                          "tickersInRankOrder": "|".join(selected),
                          "matchedTickers": "|".join(str(controls[t]) for t in selected),
                          "matchingComplete": all(controls[t] is not None for t in selected),
                          "selectedMarketCaps": "|".join(str(gi.at[t, "_mcap"]) for t in selected)})
    return books, random, matched, pd.DataFrame(audit), pd.DataFrame(ranks)


def stats(v, mask=None, block=25):
    """Resample the ORIGINAL weekly axis, then apply subset/missing masks (never concatenate separated regimes)."""
    v = np.asarray(v, float)
    ok = np.isfinite(v)
    if mask is not None:
        ok &= np.asarray(mask, bool)
    n, span = int(ok.sum()), len(v)
    out = {"n": n, "mean": float(v[ok].mean()) if n else None, "blockWeeks": block,
           "independentBlocksApprox": round(n / block, 2), "ci": None, "pOneSidedApprox": None}
    if n < 2 * block:
        return out
    rng = np.random.default_rng(SEED)
    starts = rng.integers(0, span - block + 1, size=(DRAWS, int(np.ceil(span / block))))
    idx = (starts[:, :, None] + np.arange(block)).reshape(DRAWS, -1)[:, :span]
    vv = np.where(ok, v, np.nan)[idx]
    counts = np.isfinite(vv).sum(axis=1)
    means = np.nansum(vv, axis=1) / np.maximum(counts, 1)
    means = means[counts > 0]
    out.update(ci=np.quantile(means, [0.025, 0.975]).tolist(),
               pOneSidedApprox=float((1 + (means <= 0).sum()) / (len(means) + 1)))
    return out


def asset_return(cl, t, e, x):
    pe, px = cl.at[e, t], cl.at[x, t]
    if not np.isfinite(pe) or not np.isfinite(px) or pe <= 0:
        return None
    r = float(px / pe - 1)
    cost = C.cost_rate(t, "buy", e) + (1 + r) * C.cost_rate(t, "sell", x)
    return r, r - cost, cost


def fixed(I, ctx, base, books, matched, out):
    lead = KD.leadership(I, ctx, base)
    dump(out / "leadership.json", {str(d.date()): v for d, v in lead.items()})
    allframes, summaries, exclusions = {}, {}, []
    sess, cl = I["sessions"], I["closes"]
    for h in (126, 252):
        rows = []
        for d in base["dates"]:
            e = M.next_session(sess, d)
            ix = sess.get_loc(e) + h
            if ix >= len(sess) or sess[ix] > cl[M.ETF].last_valid_index():
                exclusions.append({"date": d, "horizon": h, "reason": "NOT_MATURED"})
                continue
            x = sess[ix]
            picks = list(t for t in books["N5"][d] if t != M.ETF)
            pool = base["eligible"][d]
            need = set(pool) | {M.ETF} | {v for v in matched[d].values() if v}
            returns = {t: asset_return(cl, t, e, x) for t in need}
            bad = [t for t in [M.ETF] + picks if returns[t] is None]
            if bad:
                exclusions.append({"date": d, "horizon": h, "reason": "UNRESOLVED_MAIN_COMMON_MASK", "tickers": "|".join(bad)})
            months = pd.period_range(e, x, freq="M")
            labels = [KD.month_of(lead, pd.Timestamp(p.end_time.date())) for p in months]
            row = {"date": d, "entry": e, "exit": x, "horizon": h, "mainValid": not bad,
                   "touchesSemiLed": "SEMI_LED" in labels, "leadershipUnknown": any(l is None for l in labels)}
            etf = returns[M.ETF]
            for k in range(6):
                sel, n = picks[:k], len(picks[:k])
                row[f"N{k}_actual"] = n
                for j, suffix in enumerate(("gross", "net", "cost")):
                    row[f"N{k}_{suffix}"] = sum(0.2 * returns[t][j] for t in sel) + (1 - .2 * n) * etf[j] if not bad else np.nan
                # Exact expectation of a uniform WITHOUT-replacement n-name portfolio; linear fixed-cohort payoff.
                row[f"R{k}_net"] = (.2 * n * np.mean([returns[t][1] for t in pool]) if n else 0.) + (1 - .2 * n) * etf[1] if etf and all(returns[t] for t in pool) else np.nan
                peers = [matched[d][t] for t in sel]
                complete = all(t is not None and returns[t] is not None for t in peers)
                row[f"M{k}_net"] = sum(.2 * returns[t][1] for t in peers) + (1 - .2 * n) * etf[1] if etf and complete else np.nan
                if k:
                    row[f"rank{k}Ticker"] = picks[k-1] if len(picks) >= k else None
                    row[f"delta{k}"] = row[f"N{k}_net"] - row[f"N{k-1}_net"]
                    row[f"rank{k}Present"] = len(picks) >= k
                    row[f"selection{k}"] = row[f"N{k}_net"] - row[f"R{k}_net"]
                    row[f"exposure{k}"] = row[f"R{k}_net"] - row["N0_net"]
                    if not bad:
                        assert abs(row[f"N{k}_net"] - row["N0_net"] - sum(row[f"delta{z}"] for z in range(1, k + 1))) < 1e-12
            rows.append(row)
        df = pd.DataFrame(rows)
        df.to_csv(out / f"cohorts-{h}.csv", index=False, float_format="%.12g")
        allframes[h] = df
        masks = {"FULL": df.mainValid, "TO_2021": df.mainValid & (df.date < "2022-01-01"),
                 "FROM_2022": df.mainValid & (df.date >= "2022-01-01"),
                 "TOUCHES_SEMI_LED": df.mainValid & df.touchesSemiLed,
                 "EX_SEMI_LED": df.mainValid & ~df.touchesSemiLed & ~df.leadershipUnknown}
        result = {}
        block = round(h / 5)
        for name, mask in masks.items():
            cell = {}
            for k in range(6):
                net = df[f"N{k}_net"]
                val = {"vsETF": stats(net - df.N0_net, mask, block),
                       "costMean": float(df.loc[mask, f"N{k}_cost"].mean()) if mask.any() else None,
                       "randomSelection": stats(net - df[f"R{k}_net"], mask, block),
                       "eligibleExposure": stats(df[f"R{k}_net"] - df.N0_net, mask, block),
                       "matchedSelection": stats(net - df[f"M{k}_net"], mask, block)}
                if k:
                    val["increment"] = stats(df[f"delta{k}"], mask, block)
                    val["presentOnlyIncrement"] = stats(df[f"delta{k}"], mask & df[f"rank{k}Present"], block)
                    val["incrementNetOfRandom"] = stats(df[f"delta{k}"] - (df[f"R{k}_net"] - df[f"R{k-1}_net"]), mask, block)
                    val["incrementNetOfMatched"] = stats(df[f"delta{k}"] - (df[f"M{k}_net"] - df[f"M{k-1}_net"]), mask, block)
                cell[str(k)] = val
            result[name] = cell
        adjusted = CM.holm({str(k): result["FULL"][str(k)]["increment"]["pOneSidedApprox"] for k in range(1, 6)})
        for k, p in adjusted.items():
            result["FULL"][k]["increment"]["holmPApproxFiveRanks"] = p
        summaries[str(h)] = result
    pd.DataFrame(exclusions).to_csv(out / "excluded-cohorts.csv", index=False)
    dump(out / "fixed.json", summaries)
    return allframes, summaries


def past_only(base, frames, books, out):
    train = frames[126]
    policy, log = {}, []
    for d in base["dates"]:
        old = train[train.mainValid & (train.exit < d)]
        means = [float((old[f"N{k}_net"] - old.N0_net).mean()) for k in range(6)] if len(old) else [0.] * 6
        k = int(np.argmax(means)) if len(old) >= 52 else 0
        policy[d] = books[f"N{k}"][d]
        log.append({"date": d, "k": k, "maturedTrain": len(old), "lastTrainExit": old.exit.max() if len(old) else None,
                    **{f"trainMean{k0}": means[k0] for k0 in range(6)}})
        assert old.empty or old.exit.max() < d
    trace = pd.DataFrame(log)
    trace.to_csv(out / "past-only-decisions.csv", index=False)
    res = {}
    for h, df in frames.items():
        ks = trace.set_index("date").k.reindex(df.date).to_numpy()
        chosen = np.array([df.iloc[i][f"N{k}_net"] for i, k in enumerate(ks)])
        # common post-warmup sample, all policies on the SAME dates
        eligible = df.mainValid.to_numpy() & (trace.set_index("date").maturedTrain.reindex(df.date).to_numpy() >= 52)
        res[str(h)] = {"vsETF": stats(chosen - df.N0_net, eligible, round(h / 5)),
                       "vsN5": stats(chosen - df.N5_net, eligible, round(h / 5)),
                       "fixedOnSameDates": {str(k): stats(df[f"N{k}_net"] - df.N0_net, eligible, round(h / 5)) for k in range(6)}}
        df = df.assign(pastOnlyK=ks, pastOnlyNet=chosen, pastOnlyAfterWarmup=eligible)
        df.to_csv(out / f"cohorts-{h}.csv", index=False, float_format="%.12g")
    dump(out / "past-only.json", res)
    return policy


def turnover_diagnostic(px, schedules, start, end):
    """Membership replacement and drift resets, separately from frozen engine total turnover.

    Reset is descriptive L1 distance on retained assets from the pre-trade marked weights to the
    recorded post-trade weights (the engine rounds its audit weights to 6 decimals).
    This is not a second turnover/cost implementation or an additive cost attribution.
    """
    departed = held = 0
    resets = []
    for schedule in schedules:
        r = C.simulate(px, schedule, start, end, record=True)
        prev_date, prev = start, {M.ETF: 1.}
        for row in r["holdings"]:
            d = pd.Timestamp(row["date"])
            post = row["weights"]
            oldnames = {t for t, w in prev.items() if t not in (M.ETF, M.CASH) and w > 1e-5}
            newnames = {t for t, w in post.items() if t not in (M.ETF, M.CASH) and w > 1e-5}
            held += len(oldnames)
            departed += len(oldnames - newnames)
            values = {t: w * px.price(t, px.pos[d]) / px.price(t, px.pos[prev_date]) for t, w in prev.items() if t != M.CASH}
            total = sum(values.values())
            common = set(values) & set(post)
            resets.append(sum(abs(post[t] - values[t] / total) for t in common) if total else 0.)
            prev, prev_date = post, d
    return {"departedStockNames": departed, "priorStockNameOccurrences": held,
            "nameReplacementShare": departed / held if held else None,
            "meanRetainedAssetL1ResetApprox": float(np.mean(resets)) if resets else None,
            "note": "6-decimal recorded weights; resets are descriptive, not additive turnover attribution"}


def ledgers(I, ctx, base, books, random, policy, out):
    sess, dates = I["sessions"], base["dates"]
    start = M.next_session(sess, dates[0])
    end = I["closes"][M.ETF].last_valid_index()
    etf = pd.Series(ctx.px.etf, index=sess)
    metrics, pairs = {}, {}
    fullbooks = dict(books, PAST_ONLY=policy, **random)
    for every in (26, 52):
        navs = {}
        for name, b in fullbooks.items():
            # R*_0 are literally N0; avoid rerunning identical books.
            if name.startswith("R") and name.endswith("_0"):
                continue
            scheds = [A.books_to_schedule({d: b[d] for d in dates[i::every]}, sess) for i in range(every)]
            r = A.multi_account(ctx.px, scheds, start, end, I["rf"], etf, 1.)
            navs[name] = r["nav"]
            m = RC.window(r["nav"], etf, start=start)
            m.update(oneWayTurnoverPerYear=r["oneWayTurnoverPerYear"], costPerYear=r["costPerYear"])
            if name.startswith("N") or name == "PAST_ONLY":
                m["turnoverDiagnostic"] = turnover_diagnostic(ctx.px, scheds, start, end)
            metrics[f"L{every}|{name}"] = m
            print("ledger", every, name, round(m["excess"] * 100, 4), flush=True)
        nav = pd.DataFrame(navs)
        nav.to_csv(out / f"daily-nav-L{every}.csv", float_format="%.12g", index_label="date")
        daily = nav.pct_change().iloc[1:]
        for k in range(1, 6):
            diff = daily[f"N{k}"] - daily[f"N{k-1}"]
            geo = metrics[f"L{every}|N{k}"]["cagr"] - metrics[f"L{every}|N{k-1}"]["cagr"]
            arith = float(diff.mean() * 252)
            peers = [metrics[f"L{every}|R{p}_{k}"]["excess"] for p in range(PATHS)]
            pairs[f"L{every}|rank{k}"] = {"cagrGap": geo, "annualArithmeticDailyGap": arith,
                                          "compoundingRemainder": geo - arith,
                                          "randomExcessMean": float(np.mean(peers)), "randomExcessRange": [min(peers), max(peers)],
                                          "selectionVsRandomCagrMean": metrics[f"L{every}|N{k}"]["excess"] - float(np.mean(peers))}
        pd.DataFrame({f"rank{k}": daily[f"N{k}"] - daily[f"N{k-1}"] for k in range(1, 6)}).to_csv(
            out / f"daily-adjacent-L{every}.csv", float_format="%.12g", index_label="date")
        dump(out / "ledgers.json", {"metrics": metrics, "adjacent": pairs})
    return metrics


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", required=True)
    ap.add_argument("--out", type=Path, default=HERE / "results")
    ap.add_argument("--stage", choices=("all", "fixed", "ledgers"), default="all")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    I, ctx, base = RC.setup(args.scratch)
    books, random, matched, audit, ranks = build(ctx, base)
    audit.to_csv(args.out / "decisions.csv", index=False)
    ranks.to_csv(args.out / "eligible-ranks.csv", index=False)
    dump(args.out / "inputs.json", {"label": LABEL, "baseCommit": "3a3e9d8e60c90bf6707072efca9d1dabf3cb79ac",
                                    "sourceCommit": "4ea107ed0cde289f0a049a65ff13d2441a786710", "identity": I["ident"],
                                    "decisionCount": len(base["dates"]), "first": str(base["dates"][0].date()), "last": str(base["dates"][-1].date()),
                                    "randomSeed": SEED, "randomLedgerPaths": PATHS,
                                    "preregistrationCommit": "7a6ec28",
                                    "codeSha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(HERE.glob("*.py"))},
                                    "scratchFiles": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(args.scratch).glob("*.pkl")},
                                    "pythonNumpyPandas": [__import__("sys").version, np.__version__, pd.__version__]})
    if args.stage in ("all", "fixed"):
        frames, _ = fixed(I, ctx, base, books, matched, args.out)
    else:
        frames = {h: pd.read_csv(args.out / f"cohorts-{h}.csv", parse_dates=["date", "entry", "exit"]) for h in (126, 252)}
    policy = past_only(base, frames, books, args.out)
    if args.stage in ("all", "ledgers"):
        ledgers(I, ctx, base, books, random, policy, args.out)


if __name__ == "__main__":
    main()
