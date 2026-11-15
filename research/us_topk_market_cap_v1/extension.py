"""Inspect actual 2018/2020/2022 SPY SEC holdings, not an index-cap substitute."""
from collections import Counter
from pathlib import Path
import argparse
import gzip
import hashlib
import re
import time
from io import StringIO

from lxml import etree
import pandas as pd
import requests

from research.us_topk_market_cap_v1.inputs import read, write

ROOT = Path(__file__).resolve().parents[2]


def text(node, tag):
    found = node.xpath(f".//*[local-name()='{tag}']")
    return "".join(found[0].itertext()).strip() if found else None


def nport(raw):
    root = etree.fromstring(raw)
    rows = []
    for node in root.xpath("//*[local-name()='invstOrSec']"):
        row = {t: text(node, t) for t in ("name", "lei", "title", "cusip", "balance", "units", "curCd", "valUSD", "pctVal", "assetCat")}
        identifiers = node.xpath(".//*[local-name()='identifiers']")
        row["identifiers"] = etree.tostring(identifiers[0]).decode() if identifiers else None
        rows.append(row)
    return rows


def html_holdings(raw):
    # Reconcile the reported total first, then extract the equity schedule.
    tables = pd.read_html(StringIO(raw.decode("utf-8")), displayed_only=False)
    selected, reported_total = [], None
    for table in tables:
        if table.shape[1] != 9 or not table.iloc[:, 0].astype(str).str.contains("Common Stocks", regex=False).any():
            continue
        # The equity schedules contain name, shares and USD value, separated
        # by layout cells. Exclude totals/industry allocations/financial notes.
        for values in table.itertuples(index=False, name=None):
            name = str(values[0]).replace("\xa0", " ")
            if name.upper().startswith("TOTAL COMMON STOCKS"):
                reported_total = float(str(values[7]).replace(",", ""))
            shares, value = [str(values[i]).replace(",", "").strip() for i in (3, 7)]
            if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", shares) and re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value) and re.search(r"[A-Za-z]{2}", name):
                selected.append({"name": name, "balance": shares, "valUSD": value,
                                 "cusip": None, "lei": None, "assetCat": "EC"})
    if reported_total is None or abs(sum(float(r["valUSD"]) for r in selected) - reported_total) > .5:
        raise ValueError("SEC_COMMON_STOCK_SCHEDULE_TOTAL_NOT_RECONCILED")
    return selected, reported_total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    source = read(ROOT / "docs/us-readiness/us-etf-sec-holdings-cross-check-v1.json")
    # One validated source per fund/asof. Prefer detailed identifiers in XML.
    chosen = {}
    for row in source["results"]:
        if row.get("ticker") != "SPY" or row.get("as_of", "")[:4] not in {"2018", "2020", "2022"}:
            continue
        key = row["as_of"]
        if key not in chosen or row["form"] == "NPORT-P":
            chosen[key] = row
    dest = args.private / "spy-extension"
    dest.mkdir(exist_ok=True)
    results = []
    for asof, row in sorted(chosen.items()):
        path = dest / (row["accession"] + ".gz")
        if path.exists():
            raw, status = gzip.decompress(path.read_bytes()), 200
        else:
            response = requests.get(row["url"], timeout=60, headers={
                "User-Agent": "InvestmentResearchData/1.0 research@investment.example"})
            raw, status = response.content, response.status_code
            if status == 200:
                path.write_bytes(gzip.compress(raw, mtime=0))
            time.sleep(.3)
        receipt = {**row, "retrieved_status": status, "bytes": len(raw)}
        if status == 200:
            sha = hashlib.sha256(raw).hexdigest()
            receipt["retrieved_sha256"] = sha
            receipt["matches_prior_receipt"] = sha == row["source_sha256"]
            if row["form"] == "NPORT-P":
                holdings = nport(raw)
            else:
                holdings, reported_total = html_holdings(raw)
                receipt["reported_common_stock_value_total"] = reported_total
                receipt["common_stock_total_reconciled"] = True
            write(dest / (row["accession"] + "-holdings.json.gz"), holdings)
            receipt["parsed_rows"] = len(holdings)
            if row["form"] != "NPORT-P":
                receipt["parsed_equity_rows"] = len(holdings)
                receipt["equity_with_cusip"] = 0
                receipt["equity_with_lei"] = 0
                receipt["equity_with_usd_value"] = len(holdings)
                receipt["parsed_common_value_sum"] = sum(float(r["valUSD"]) for r in holdings)
            if row["form"] == "NPORT-P":
                equity = [r for r in holdings if r["assetCat"] == "EC"]
                receipt["parsed_equity_rows"] = len(equity)
                receipt["equity_with_cusip"] = sum(bool(r["cusip"]) for r in equity)
                receipt["equity_with_lei"] = sum(bool(r["lei"]) for r in equity)
                receipt["equity_with_usd_value"] = sum(bool(r["valUSD"]) for r in equity)
                receipt["top_issuer_position_sample"] = [{k: r[k] for k in ("name", "cusip", "lei", "pctVal")}
                    for r in sorted(equity, key=lambda r: -float(r["valUSD"]))[:12]]
            receipt["rank_admission"] = "NOT_ADMITTED_ETF_POSITIONS_ARE_NOT_COMPANY_CAP_OR_DAILY_INDEX_MEMBERSHIP"
        results.append(receipt)
        print(asof, status, receipt.get("parsed_rows"), receipt.get("matches_prior_receipt"), flush=True)
    write(args.output / "historical-extension-source-receipts.json", results)
    print(dict(Counter(r["as_of"][:4] for r in results)))


if __name__ == "__main__":
    main()
