"""Next-open execution backtester with explicit cash accounting."""
from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_COSTS = {
    "US": {"buyCommissionBps": 0.0, "sellCommissionBps": 0.0, "sellTaxBps": 0.0, "slippageBps": 10.0, "asOf": "2026-07-12 configurable assumption"},
    "KR": {"buyCommissionBps": 1.5, "sellCommissionBps": 1.5, "sellTaxBps": 15.0, "slippageBps": 10.0, "asOf": "2026-07-12 configurable assumption"},
}


def _bps(x): return float(x or 0) / 10000.0


def long_flat_next_open(df: pd.DataFrame, signal_col: str = "pred_cal", region: str = "US",
                        costs: dict | None = None, initial_capital: float = 100_000.0,
                        force_liquidate: bool = True) -> dict:
    df = df.dropna(subset=["Open", "Close", signal_col]).copy()
    if len(df) < 2: return {}
    c = (costs or DEFAULT_COSTS).get(region, DEFAULT_COSTS["US"])
    buy_fee = _bps(c.get("buyCommissionBps")); sell_fee = _bps(c.get("sellCommissionBps")) + _bps(c.get("sellTaxBps")); slip = _bps(c.get("slippageBps"))
    cash = float(initial_capital); shares = 0.0; values=[]; trades=[]
    idx=list(df.index)
    for i in range(len(df)-1):
        sig = int(df.iloc[i][signal_col]); trade_date = idx[i+1]
        open_px = float(df.iloc[i+1]["Open"]); close_px = float(df.iloc[i+1]["Close"])
        if shares == 0 and sig == 1:
            px = open_px * (1 + slip); shares = cash / (px * (1 + buy_fee)); cost = shares * px; fee = cost * buy_fee; cash -= cost + fee
            trades.append({"date": trade_date, "side": "BUY", "price": px, "shares": shares, "fee": fee})
        elif shares > 0 and sig == 0:
            px = open_px * (1 - slip); proceeds = shares * px; fee = proceeds * sell_fee; cash += proceeds - fee
            trades.append({"date": trade_date, "side": "SELL", "price": px, "shares": shares, "fee": fee}); shares = 0.0
        values.append({"date": trade_date, "cash": cash, "shares": shares, "stockValue": shares * close_px, "value": cash + shares * close_px, "position": int(shares > 0)})
    if force_liquidate and shares > 0:
        px = float(df.iloc[-1]["Close"]) * (1 - slip); proceeds = shares * px; fee = proceeds * sell_fee; cash += proceeds - fee
        trades.append({"date": idx[-1], "side": "LIQUIDATE", "price": px, "shares": shares, "fee": fee}); shares = 0.0
        if values:
            values[-1].update({"cash": cash, "shares": 0.0, "stockValue": 0.0, "value": cash, "position": 0})
    pv = pd.DataFrame(values).set_index("date")
    ret = (cash - initial_capital) / initial_capital
    years = max((pv.index[-1] - pv.index[0]).days / 365.25, 1e-9)
    ann = (1 + ret) ** (1 / years) - 1 if ret > -1 else -1
    r = pv["value"].pct_change().dropna(); vol = float(r.std()*np.sqrt(252)) if len(r) else 0.0
    sharpe = float(r.mean()/r.std()*np.sqrt(252)) if len(r) and r.std() > 0 else 0.0
    downside = r[r < 0].std(); sortino = float(r.mean()/downside*np.sqrt(252)) if len(r) and downside and downside > 0 else 0.0
    dd = float((pv["value"]/pv["value"].cummax()-1).min()) if len(pv) else 0.0
    bh = float(df.iloc[-1]["Close"] / df.iloc[1]["Open"] - 1)
    return {"annualReturn": round(ann*100,2), "totalReturn": round(ret*100,2), "volatility": round(vol*100,2), "sharpe": round(sharpe,2), "sortino": round(sortino,2), "maxDrawdown": round(dd*100,2), "numTrades": len(trades), "turnover": len(trades), "buyHoldReturn": round(bh*100,2), "vsBuyHold": round((ret-bh)*100,2), "costAssumptions": c, "accountingOk": bool(np.allclose(pv["cash"]+pv["stockValue"], pv["value"])), "trades": trades[:10], "strategyLabel": "0.5 long/flat reference; next-open execution"}
