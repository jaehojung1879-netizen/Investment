"""Recompute the descriptive public SCE release panel, not a return backtest."""
from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path
from statistics import correlation, mean

PANEL = Path(__file__).with_name("sce_release_panel.json")


def analyze(data):
    if (data["schema"] != "NARRATIVE_SCE_RELEASE_PANEL_V1"
            or data["forecast_registration_authorized"] is not False
            or data["production_effect"] != "NONE"):
        raise ValueError("SCOPE")
    rows = data["rows"]
    expected = [f"2025-{m:02d}" for m in range(1, 13)] + [f"2026-{m:02d}" for m in range(1, 11)]
    if [r["month"] for r in rows] != expected:
        raise ValueError("INCOMPLETE_OR_DUPLICATE_MONTH")
    stock, unemp = [], []
    for row in rows:
        published = date.fromisoformat(row["published"])
        if not date.fromisoformat(row["month"] + "-01") < published <= date.fromisoformat(data["as_of"]):
            raise ValueError("PUBLICATION_CLOCK")
        if published.strftime("%Y-%m") == row["month"]:
            raise ValueError("SAME_MONTH_PUBLICATION")
        expected_url = ("https://www.newyorkfed.org/newsevents/news/research/"
                        + published.strftime("%Y/%Y%m%d"))
        if row["source"] != expected_url or row["raw_sha256"] is not None:
            raise ValueError("SOURCE_PROVENANCE")
        for key, out in (("stock", stock), ("unemployment", unemp)):
            value = row[key]
            if type(value) not in (float, int) or not math.isfinite(value) or not 0 <= value <= 100:
                raise ValueError("PROBABILITY")
            out.append(value)
    a = [round(y - x, 1) for x, y in zip(stock, stock[1:])]
    b = [round(y - x, 1) for x, y in zip(unemp, unemp[1:])]
    counts = dict.fromkeys(("both_up", "both_down", "stock_up_unemployment_down",
                           "stock_down_unemployment_up", "ties"), 0)
    for x, y in zip(a, b):
        if x == 0 or y == 0:
            key = "ties"
        elif x > 0 and y > 0:
            key = "both_up"
        elif x < 0 and y < 0:
            key = "both_down"
        elif x > 0:
            key = "stock_up_unemployment_down"
        else:
            key = "stock_down_unemployment_up"
        counts[key] += 1
    result = {"months": len(rows), "changes": len(a),
              "level_correlation": correlation(stock, unemp),
              "change_correlation": correlation(a, b),
              "change_counts": counts,
              "periods": [{"period": str(yr), "n": len(s),
                           "stock_mean": mean(s), "unemp_mean": mean(u),
                           "level_correlation": correlation(s, u)}
                          for yr, s, u in [(2025, stock[:12], unemp[:12]),
                                            (2026, stock[12:], unemp[12:])]],
              "market_outcomes_read": False, "forecast_registration_authorized": False}
    saved = data["results"]
    for key in ("months", "changes", "change_counts"):
        if result[key] != saved[key]:
            raise ValueError("RESULT_MISMATCH")
    for key in ("level_correlation", "change_correlation"):
        if not math.isclose(result[key], saved[key], abs_tol=1e-12):
            raise ValueError("RESULT_MISMATCH")
    for actual, stored in zip(result["periods"], saved["periods"], strict=True):
        if actual["period"] != stored["period"] or actual["n"] != stored["n"]:
            raise ValueError("RESULT_MISMATCH")
        for key in ("stock_mean", "unemp_mean", "level_correlation"):
            if not math.isclose(actual[key], stored[key], abs_tol=1e-12):
                raise ValueError("RESULT_MISMATCH")
    return result


if __name__ == "__main__":
    print(json.dumps(analyze(json.loads(PANEL.read_text(encoding="utf-8"))), indent=2))
