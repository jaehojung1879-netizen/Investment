"""Extract long common-equity positions from the GCAP N-PORT release into private files (outside git).

    python -m research.active_fund_disclosure_v1.nport_extract --zip <nport.zip> --out <private dir>

Source: Cavani, Maggiori, Schreger (2025), "GCAP Public Security-Level Data on U.S. Fund Holdings", built from the SEC Form N-PORT
public flat files (academic/educational use; the raw data stay outside the repository). One row per (accession, holding) with
asset_cat EC (equity-common) and payoff Long. Fund-level fields are kept per accession. Nothing here reads a return.
"""
from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

HOLD_COLS = ["accession_number", "series_id", "issuer_name", "issuer_cusip", "identifier_isin", "identifier_ticker",
             "currency_value", "currency_code", "investment_country", "asset_cat", "payoff_profile"]
FUND_COLS = ["accession_number", "series_id", "series_name", "cik", "registrant_name", "filing_date", "report_date",
             "net_assets", "total_assets"]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    z = zipfile.ZipFile(a.zip)
    funds = []
    for name in sorted(n for n in z.namelist() if n.endswith(".parquet")):
        f = pq.ParquetFile(z.open(name))
        parts = []
        for g in range(f.num_row_groups):
            t = f.read_row_group(g, columns=sorted(set(HOLD_COLS + FUND_COLS))).to_pandas()
            fu = t[FUND_COLS].drop_duplicates("accession_number")
            fu["file"] = name
            funds.append(fu)
            h = t[(t["asset_cat"] == "EC") & (t["payoff_profile"] == "Long")][HOLD_COLS].drop(columns=["asset_cat", "payoff_profile"])
            h["currency_value"] = pd.to_numeric(h["currency_value"], errors="coerce")
            parts.append(h[h["currency_value"] > 0])
        hold = pd.concat(parts, ignore_index=True)
        hold.to_parquet(out / f"ec-{name}", index=False)
        print(name, len(hold), flush=True)
    fu = pd.concat(funds, ignore_index=True).drop_duplicates("accession_number")
    for c in ("net_assets", "total_assets"):
        fu[c] = pd.to_numeric(fu[c], errors="coerce")
    fu.to_parquet(out / "funds.parquet", index=False)
    print("funds", len(fu))


if __name__ == "__main__":
    main()
