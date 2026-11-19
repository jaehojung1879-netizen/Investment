"""L26/L52 simulation using original trading engines and explicit quote refusal."""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
import pickle

import numpy as np
import pandas as pd

from pipeline.us_decision_pilot import REALISTIC_COSTS, rebalance, simulate
from research.kr_us_strategy_batch_v1 import common as C
from research.kr_us_strategy_batch_v1 import kr as K
from research.kr_us_strategy_batch_v1 import us as U
from research.kr_us_exposure_preserving_v1.engine import write_json

HERE = Path(__file__).resolve().parent


def us_account(close, orders):
    """Vectorize the buy-and-hold intervals, calling the original cost solver."""
    index = close.index
    policy = REALISTIC_COSTS["US"]
    buy = (policy["commissionBps"] + policy["spreadBps"] / 2) / 10000
    sell = buy + policy["sellTaxBps"] / 10000
    fills = {index.get_loc(d) for d in orders}
    nav = np.ones(len(index))
    costs, traded = np.zeros(len(index)), np.zeros(len(index))
    weights = {}
    start, capital = 0, 1.
    names_exited, names_prior, retained_reset = 0, 0, []
    for stop in sorted(fills | {len(index)-1}):
        if weights:
            names = list(weights)
            block = close.iloc[start:stop+1].loc[:, names].to_numpy()
            invalid = ~np.isfinite(block) | (block <= 0)
            if invalid.any():
                j, column = np.argwhere(invalid)[0]
                raise ValueError(f"UNRESOLVED_HELD_OBSERVATION:{index[start+j].date()}:{names[column]}")
            weighted = block / block[0] * np.array(list(weights.values()))
            growth = 1 - sum(weights.values()) + weighted.sum(axis=1)
            nav[start:stop+1] = capital * growth
            drift = dict(zip(names, weighted[-1] / growth[-1], strict=True))
        else:
            nav[start:stop+1] = capital
            drift = {}
        if stop not in fills:
            break
        target = orders[index[stop]]
        execution = close.iloc[stop].reindex(target)
        invalid = ~np.isfinite(execution) | execution.le(0)
        if invalid.any():
            raise ValueError(f"UNRESOLVED_ENTRY_OBSERVATION:{index[stop].date()}:{'|'.join(execution.index[invalid])}")
        fraction, traded[stop] = rebalance(drift, target, buy, sell)
        costs[stop] = nav[stop] * fraction
        nav[stop] -= costs[stop]
        prior = set(drift) - {"SPY", "QQQ"}
        names_prior += len(prior)
        names_exited += len(prior - set(target))
        retained_reset.append(sum(abs(target[t] - drift[t]) for t in set(drift) & set(target)))
        weights, start, capital = dict(target), stop, nav[stop]
    return (pd.DataFrame({"nav":nav,"costInitialCapital":costs,"twoWayTurnover":traded}, index=index),
            (names_exited, names_prior, retained_reset))


def kr_support(px, schedules, start, end):
    """Track which positions can be held under the original engine's trade locks."""
    events = []
    locked_targets = 0
    terminal = px.terminal
    etf, cash = K.M.ETF, K.M.CASH
    for account, schedule in enumerate(schedules):
        intervals = {px.pos[d]: w for d,w in schedule.items() if start <= d <= end}
        held = {etf}
        for i in range(px.pos[start], px.pos[end] + 1):
            for ticker in held & terminal.keys():
                if i > terminal[ticker]:
                    events.append({"account":account,"date":str(px.sessions[i].date()),"ticker":ticker})
            if events and events[-1]["account"] == account:
                break
            if i in intervals:
                target = intervals[i]
                unavailable = {t for t in set(held)|set(target)
                               if t not in (etf,cash) and not px.tradable[i,px.col[t]]}
                locked_targets += len(set(target)&unavailable)
                free = {t for t,w in target.items() if t not in unavailable and w > 0}
                held = (held & unavailable) | ((free or {etf}) - {cash})
    return events, locked_targets


def load_books(path):
    with gzip.open(path, "rt") as f:
        value = json.load(f)
    return {k:{pd.Timestamp(d):w for d,w in b.items()} for k,b in value.items()}


def us_run(out, input_dir, close_path):
    close, _, qqq, _ = U.EV.load(input_dir)
    with close_path.open("rb") as f:
        repaired = pickle.load(f)
    close = repaired["close"] if isinstance(repaired,dict) else repaired
    close = close.copy()
    close["QQQ"] = qqq
    funded = load_books(out / "funding-book-schedules.json.gz")
    dates = sorted(funded["PASSIVE"])
    price = close.loc[dates[0]:]
    experiment = {k:b for k,b in funded.items() if not k.endswith(":PEER")}
    spy, _ = us_account(price, {price.index[1]:{"SPY":1.}})
    qqq, _ = us_account(price, {price.index[1]:{"QQQ":1.}})
    result = {"L26":{},"L52":{}}
    # Original-engine parity on a short real path with rebalancing, drift and costs.
    sample = price[["SPY","AAPL","MSFT"]].iloc[:200]
    orders = {sample.index[1]:{"SPY":1.},sample.index[6]:{"SPY":.8,"AAPL":.2},
              sample.index[91]:{"SPY":.8,"MSFT":.2}}
    fast, _ = us_account(sample,orders)
    slow = simulate(sample,orders)
    error = float((fast-slow[fast.columns]).abs().max().max())
    assert error < 1e-10, error
    for interval in (26,52):
        all_nav = {"ETF":spy.nav,"QQQ":qqq.nav}
        for name, bydate in experiment.items():
            accounts, diagnostics = [], []
            try:
                for phase in range(interval):
                    orders = {price.index[1]:{"SPY":1.}}
                    for date in dates[phase::interval]:
                        fill = close.index[close.index.get_loc(date)+1]
                        orders[fill] = bydate[date]
                    account, diagnostic = us_account(price, orders)
                    accounts.append(account)
                    diagnostics.append(diagnostic)
            except (ValueError,KeyError) as exc:
                result[f"L{interval}"][name] = {"status":"NOT_ESTIMABLE","reason":str(exc)}
                continue
            avg = sum(accounts)/interval
            nav = avg.nav
            all_nav[name] = nav
            m = C.nav_window(nav, spy.nav)
            m["status"] = "MEASURED"
            m["oneWayTurnoverPerYear"] = float(avg.twoWayTurnover.sum()/2/m["years"])
            m["costPerYear"] = float(avg.costInitialCapital.sum()/m["years"])
            m["namesExited"] = sum(d[0] for d in diagnostics)
            prior = sum(d[1] for d in diagnostics)
            m["nameExitShare"] = m["namesExited"]/prior if prior else None
            m["meanRetainedResetL1"] = float(np.mean([x for d in diagnostics for x in d[2]]))
            m["qqqComparison"] = C.nav_window(nav, qqq.nav)
            result[f"L{interval}"][name] = m
        pd.DataFrame(all_nav).to_csv(out/f"funded-nav-L{interval}.csv.gz")
    result["originalEngineParityMaxError"] = error
    write_json(out/"funded-ledgers.json",result)


def kr_run(out, scratch):
    funded = load_books(out / "funding-book-schedules.json.gz")
    actual = load_books(K.HERE / "results/KR/books.json.gz")
    etf = K.M.ETF
    experiment = {k:b for k,b in funded.items() if not k.endswith(":PEER")}
    for name in experiment.copy():
        if name == "PASSIVE":
            continue
        selector, k = ("S2",name[-1]) if name.startswith("S2_K") else (name,5)
        experiment[name+":ORIGINAL"] = actual[f"KR:{selector}:FIXED20:K{k}"]
    prepared = scratch / "kr-us-batch-v1-prepared.pkl"
    if prepared.exists():
        I, ctx, base, *_ = pickle.loads(prepared.read_bytes())
    else:
        I, ctx, base = K.RC.setup(str(scratch))
    expected = json.loads((K.HERE/"results/KR/summary.json").read_text())["inputs"]["identity"]
    assert I["ident"] == expected
    sessions, end = I["sessions"], I["closes"][etf].last_valid_index()
    reference = pd.Series(ctx.px.etf,index=sessions)
    result = {}
    for span, dates in (("FULL",base["dates"]), ("SUFFIX",[d for d in base["dates"] if d >= pd.Timestamp("2026-01-02")])):
        start = K.M.next_session(sessions, dates[0])
        for interval in (26,52):
            states = {}
            all_nav = {"ETF":reference.loc[start:end]/reference.at[start]}
            for name, bydate in experiment.items():
                if span == "FULL" and name.endswith(":ORIGINAL"):
                    continue  # exact existing L26/L52 artifacts are reused in the report
                if any(d not in bydate for d in dates):
                    states[name] = {"status":"NOT_ESTIMABLE","reason":"MISSING_TARGET"}
                    continue
                schedules = [K.A.books_to_schedule({d:bydate[d] for d in dates[i::interval]},sessions)
                             for i in range(interval)]
                failures, locks = kr_support(ctx.px,schedules,start,end)
                if failures:
                    states[name] = {"status":"NOT_ESTIMABLE","reason":"UNRESOLVED_TERMINAL_WHILE_HELD",
                                    "firstFailurePerAccount":failures,"unavailableTargetsBeforeRefusal":locks}
                    continue
                book = K.A.multi_account(ctx.px,schedules,start,end,I["rf"],reference)
                metrics = C.nav_window(book["nav"],reference)
                diagnostics = K.nav_diagnostic(ctx.px,schedules,start,end)
                assert not diagnostics["terminalEvents"]
                metrics.update(status="MEASURED",oneWayTurnoverPerYear=book["oneWayTurnoverPerYear"],
                               costPerYear=book["costPerYear"], targetNontradable=locks,
                               turnoverDiagnostic=diagnostics)
                all_nav[name] = book["nav"]
                states[name] = metrics
            result[f"{span}:L{interval}"] = states
            pd.DataFrame(all_nav).to_csv(out/f"funded-nav-{span}-L{interval}.csv.gz")
    write_json(out/"funded-ledgers.json",result)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("market",choices=("KR","US"))
    parser.add_argument("--kr-scratch",type=Path,default=Path("/workspace/s2-inputs"))
    parser.add_argument("--us-private",type=Path,default=Path("/workspace/batch-inputs/us"))
    parser.add_argument("--us-repaired",type=Path,default=Path("/workspace/exposure-inputs/us/close-repaired.pkl"))
    args = parser.parse_args()
    out = HERE/"results"/args.market
    if args.market == "KR":
        kr_run(out,args.kr_scratch)
    else:
        us_run(out,args.us_private,args.us_repaired)


if __name__ == "__main__":
    main()
