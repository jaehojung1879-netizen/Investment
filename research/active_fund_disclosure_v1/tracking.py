"""How far merged / liquidated funds can be followed, and three linked filing examples. Reads no return.

    python -m research.active_fund_disclosure_v1.tracking --private <dir> --out research/active_fund_disclosure_v1/results
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

EXAMPLES = ("Growth Fund of America", "T. Rowe Price Blue Chip Growth Fund, Inc.", "VIP Contrafund Portfolio")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    P, OUT = Path(a.private), Path(a.out)
    F = pd.read_parquet(P / "nport" / "filings.parquet")
    S = F[F["inSample"]]
    allf = pd.read_parquet(P / "nport" / "x" / "funds.parquet", columns=["series_id", "report_date"])
    end = allf["report_date"].max()
    cut = end - pd.Timedelta(days=200)
    last_all = allf.groupby("series_id")["report_date"].max().reindex(S["series_id"].unique())
    last_in = S.groupby("series_id")["report_date"].max()
    stopped = last_all < cut
    left = ~stopped & (last_in.reindex(last_all.index) < cut)
    lag = (S["filing_date"] - S["report_date"]).dt.days
    ex = []
    for nm in EXAMPLES:
        g = S[S["series_name"] == nm].sort_values("report_date")
        if len(g):
            r = g.iloc[-1]
            ex.append({"series": nm, "seriesId": r["series_id"], "registrantCik": r["cik"], "accession": r["accession"],
                       "reportDate": str(r["report_date"].date()), "publicDate": str(r["filing_date"].date()),
                       "lagDays": int((r["filing_date"] - r["report_date"]).days), "netAssetsBn": round(r["netAssets"] / 1e9, 1),
                       "equityHoldings": int(r["nEquity"]), "activeShareVsSp500": round(r["activeShare"], 3),
                       "linkedValueShare": round(r["linkedValueShare"], 3), "sp500ValueShare": round(r["sp500Share"], 3)})
    out = {"lastReportDate": str(end.date()), "inSampleSeries": int(len(last_all)),
           "stoppedFilingMergedLiquidatedOrReregistered": int(stopped.sum()),
           "stoppedByYearOfLastFiling": {int(k): int(v) for k, v in last_all[stopped].dt.year.value_counts().sort_index().items()},
           "stillFilingButLeftScreens": int(left.sum()), "presentToEnd": int(len(last_all) - stopped.sum() - left.sum()),
           "note": "a series that stops filing stays in every signal date while it filed; nothing after its last filing is used or imputed",
           "lagOver75DaysShare": float((lag > 75).mean()), "lagOver120DaysFilings": int((lag > 120).sum()), "examples": ex}
    (OUT / "us-tracking.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
