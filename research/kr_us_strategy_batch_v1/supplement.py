"""Descriptive availability diagnostics, never a replacement for the frozen core.

Basket selectors exhaust same-sector common peers. Keep the original zero-size
joint sample and additionally show the named complete-pool/single-stock subset.
"""
from __future__ import annotations

import pandas as pd

from research.kr_us_strategy_batch_v1 import common as C
from research.kr_us_strategy_batch_v1 import report as R

SETS = {"KR": ["S2", "VALUE_COMPLETE", "QUALITY_NEUTRAL", "CONFIRM_NEUTRAL"],
        "US": ["PRICE", "PRICE_CONFIRMED", "QUALITY_NEUTRAL", "CONFIRM_NEUTRAL",
               "VALUE", "VALUE_CONFIRMED", "CASH_PROFITABILITY"]}


def run():
    result = {"label": "POST_HOC_AVAILABILITY_DIAGNOSTIC_NOMINAL_CI_NOT_CORE",
              "reason": "US sector-wide baskets exhaust unused same-industry peers; retain original all-signal core unchanged",
              "coreFamilyUnchanged": 41, "broadFamilyUnchanged": 115, "sets": SETS, "markets": {}}
    rows = []
    for market in ("KR", "US"):
        if not (R.OUT / market / "summary.json").exists():
            continue
        result["markets"][market] = {}
        for h in (126, 252):
            if market == "KR":
                frame = pd.read_csv(R.OUT / market / f"cohorts-{h}.csv.gz", index_col="date", parse_dates=True)
                peer = pd.read_csv(R.OUT / market / f"matched-{h}.csv", index_col="date", parse_dates=True)
                selection = pd.DataFrame({s: peer[s + "_selection"] for s in R.REG["krSelectors"]})
                replacement = pd.DataFrame({s: peer[s + "_replacement"] for s in R.REG["krSelectors"]})
                total = pd.DataFrame({s: frame[f"KR:{s}:FIXED20:K5_excess"] for s in R.REG["krSelectors"]})
            else:
                net = pd.read_csv(R.OUT / market / f"cohorts-net-{h}.csv.gz", index_col=0, parse_dates=True)
                peer = pd.read_csv(R.OUT / market / f"peer-cohorts-net-{h}.csv.gz", index_col=0, parse_dates=True)
                selection = pd.DataFrame({s: net[f"US:{s}:Q020"] - peer[s] for s in peer})
                replacement = peer.subtract(net["US:SPY"], axis=0)
                total = pd.DataFrame({s: net[f"US:{s}:Q020"] - net["US:SPY"] for s in peer})
            common = selection[SETS[market]].notna().all(axis=1)
            cells = {}
            max_error = 0.0
            for s in selection:
                own = selection[s].notna()
                error = (total[s] - selection[s] - replacement[s]).where(own).abs().max()
                if pd.notna(error):
                    max_error = max(max_error, float(error))
                cells[s] = {}
                for name, mask in (("own", own), ("subsetCommon", common & own)):
                    cells[s][name] = {"total": C.stats(total[s], h, mask),
                                      "selection": C.stats(selection[s], h, mask),
                                      "replacement": C.stats(replacement[s], h, mask)}
                    if name == "subsetCommon" and s not in SETS[market]:
                        cells[s][name] = None
                for d in selection.index:
                    rows.append({"market": market, "H": h, "date": d, "selector": s,
                                 "inSupplementSubset": s in SETS[market], "subsetCommonDate": bool(common.at[d]),
                                 "totalIncrement": total.at[d, s], "selectionEffect": selection.at[d, s],
                                 "etfToPeerEffect": replacement.at[d, s]})
            assert max_error < 1e-9
            result["markets"][market][str(h)] = {"subsetCommonDates": [str(d.date()) for d in common.index[common]],
                                                      "commonWeeks": int(common.sum()),
                                                      "maxThreeTermIdentityError": max_error, "selectors": cells}
    pd.DataFrame(rows).to_csv(R.OUT / "matched-decomposition-diagnostics.csv.gz", index=False,
                             compression={"method": "gzip", "mtime": 0})
    R.dump(R.OUT / "matched-common-diagnostics.json", result)
    return result
