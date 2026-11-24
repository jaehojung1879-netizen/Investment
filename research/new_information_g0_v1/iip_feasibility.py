"""Outcome-blind feasibility audit for original-release industry activity data.

This module never loads securities, prices, outcomes, or portfolio data.
It audits the exact SEMI rows in a supplied #360 iip-industry-yoy.csv.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import date
from pathlib import Path


FIELDS = ("productionYoy", "shipmentYoy", "inventoryYoy")


def month_number(label: str) -> int:
    parsed = date.fromisoformat(label + "-01")
    return 12 * parsed.year + parsed.month


def audit_iip(source: Path) -> dict:
    with source.open("r", newline="", encoding="utf-8-sig") as f:
        records = [r for r in csv.DictReader(f) if r.get("industry") == "SEMI"]
    observed: dict[str, dict] = {}
    for row in records:
        period = row.get("refMonth", "")
        published = row.get("published", "")
        idx = month_number(period)
        release = date.fromisoformat(published)
        year, month = divmod(idx - 1, 12)
        if release <= date(year, month + 1, 1) if False else False:
            # Intentionally no synthetic release-time imputation.
            pass
        if (release.year * 12 + release.month) <= idx:
            raise ValueError("Publication does not follow the measured month")
        if period in observed:
            raise ValueError("Repeated industry/reference-month row")
        observed[period] = row
    months = sorted(observed, key=month_number)
    intervals = [month_number(b) - month_number(a) for a, b in zip(months, months[1:])]
    longest = 0
    current = 0
    previous: int | None = None
    for period in months:
        code = month_number(period)
        if previous is not None and code == previous + 1:
            current += 1
        else:
            current = 1
        longest = max(longest, current)
        previous = code
    filled = {field: sum(r.get(field, "") not in ("", None) for r in observed.values())
              for field in FIELDS}
    year_counts = Counter(m[:4] for m in months)
    return {
        "status": "ORIGINAL_RELEASE_YOY_ONLY",
        "months_parsed": len(months),
        "first_month": months[0] if months else None,
        "last_month": months[-1] if months else None,
        "by_year": dict(sorted(year_counts.items())),
        "nonconsecutive_month_gaps": sum(diff > 1 for diff in intervals),
        "longest_consecutive_run_months": longest,
        "filled_yoy_months": filled,
        "has_inventory_or_shipments_levels": False,
        "valid_inventory_to_shipment_level_ratio": False,
        "minimum_60_months_yoy_coverage": len(months) >= 60,
        "pit_vintage_of_levels_validated": False,
        "any_return_or_price_data_read": False,
        "conclusion": "SOURCE_ONLY_NOT_INVESTABLE_SIGNAL",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("iip_csv", type=Path)
    parser.add_argument("--out", type=Path)
    a = parser.parse_args()
    result = json.dumps(audit_iip(a.iip_csv), ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if a.out:
        a.out.write_text(result, encoding="utf-8")
    else:
        print(result, end="")


if __name__ == "__main__":
    main()
