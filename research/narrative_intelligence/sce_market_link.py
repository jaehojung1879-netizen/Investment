"""Descriptive link between SCE belief changes and monthly SPX price moves.

External CSV only: month,price_return_pct (one decimal place for the pilot).
No licensed price series committed; no forward returns, trading or inference.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from statistics import correlation

from .sce_diagnostics import PANEL, analyze


def describe(x, y):
    if len(x) != len(y) or len(x) < 4:
        raise ValueError("INVALID_PAIR_COUNT")
    leave_one = [correlation(x[:i] + x[i+1:], y[:i] + y[i+1:])
                 for i in range(len(x))]
    return {
        "n": len(x), "pearson_r": correlation(x, y),
        "same_nonzero_direction": sum(a*b > 0 for a, b in zip(x, y)),
        "leave_one_out_min": min(leave_one), "leave_one_out_max": max(leave_one),
    }


def diagnostics(panel, returns):
    analyze(panel)
    rows = panel["rows"]
    months = [r["month"] for r in rows]
    if set(returns) != set(months):
        raise ValueError("EXACT_MONTH_CENSUS_REQUIRED")
    values = [returns[m] for m in months]
    if any(type(v) not in (int, float) or not math.isfinite(v) or v <= -100 for v in values):
        raise ValueError("INVALID_PRICE_RETURN")
    stocks = [round(b["stock"] - a["stock"], 1) for a, b in zip(rows, rows[1:])]
    jobs = [round(b["unemployment"] - a["unemployment"], 1) for a, b in zip(rows, rows[1:])]
    return {
        "status": "EXPLORATORY_DESCRIPTIVE_ONLY",
        "survey_months": len(months), "adjacent_changes": len(stocks),
        "prior_month_stock_belief": describe(stocks, values[:-1]),
        "same_month_stock_belief": describe(stocks, values[1:]),
        "prior_month_unemployment_belief_r": correlation(jobs, values[:-1]),
        "same_month_unemployment_belief_r": correlation(jobs, values[1:]),
        "periods": {
            "2025": {"prior": describe(stocks[:11], values[:11]),
                     "same": describe(stocks[:11], values[1:12])},
            "2026_Jan_Oct": {"prior": describe(stocks[11:], values[11:-1]),
                             "same": describe(stocks[11:], values[12:])},
        },
        "same_month_available_before_each_response": False,
        "forward_return_join": False, "forecast_registration_authorized": False,
        "production_effect": "NONE",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--returns", type=Path, required=True)
    args = parser.parse_args()
    with args.returns.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != ["month", "price_return_pct"]:
            raise ValueError("RETURN_SCHEMA")
        returns = {}
        for row in reader:
            if row["month"] in returns:
                raise ValueError("DUPLICATE_RETURN_MONTH")
            returns[row["month"]] = float(row["price_return_pct"])
    print(json.dumps(diagnostics(json.loads(PANEL.read_text(encoding="utf-8")), returns),
                     indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
