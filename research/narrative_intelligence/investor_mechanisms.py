"""Separate source-attributed investor statements from observable aggregate actions."""
from __future__ import annotations

import json
from pathlib import Path

from .ledger import day, indexed, number

PILOT = Path(__file__).with_name("investor_mechanisms_pilot.json")
MODALITIES = {"ASSESSMENT", "INTENTION", "MECHANISM", "CONDITIONAL_RISK", "UNCERTAINTY",
              "SELF_REPORTED_ACTION", "PHILOSOPHY"}


def diagnostics(data):
    if (data["schema"] != "NARRATIVE_INVESTOR_PILOT_V1"
            or data["forecast_registration_authorized"] is not False
            or data["market_outcomes_read"] is not False):
        raise ValueError("SCHEMA_OR_AUTHORIZATION")
    clock = day(data["as_of"])
    sources, claims = indexed(data["sources"]), indexed(data["claims"])
    counts = dict.fromkeys(sorted(MODALITIES), 0)
    for src in sources.values():
        if (day(src["date"]) > clock or not src["url"].startswith("https://")
                or src["raw_sha256"] is not None or src["availability"] != "NOT_PIT_CERTIFIED"):
            raise ValueError("SOURCE_PROVENANCE")
    for c in claims.values():
        if c["actor"] != sources[c["source"]]["actor"] or c["modality"] not in MODALITIES:
            raise ValueError("ATTRIBUTION_OR_MODALITY")
        if c["forecast_target"] is not None or c["forecast_horizon"] is not None:
            raise ValueError("UNADMITTED_FORECAST")
        if not c["paraphrase"] or not c["limit"]:
            raise ValueError("EVIDENCE_LIMIT_REQUIRED")
        counts[c["modality"]] += 1
    for pair in data["contrasts"]:
        a, b = claims[pair["earlier"]], claims[pair["later"]]
        if not pair["limit"]:
            raise ValueError("CONTRAST_LIMIT_REQUIRED")
        if pair["kind"] == "SAME_AUTHOR_ASSESSMENT_REVISION":
            if (a["actor"], a["asset"], a["topic"], a["modality"]) != (
                    b["actor"], b["asset"], b["topic"], b["modality"]):
                raise ValueError("NOT_COMPARABLE")
            if day(sources[a["source"]]["date"]) >= day(sources[b["source"]]["date"]):
                raise ValueError("REVISION_CLOCK")
    behavior = data["behavior"]
    if (behavior["scope"] != "CONSOLIDATED_CASH_FLOW_EQUITY_SECURITIES"
            or behavior["balance_scope"] != "INSURANCE_AND_OTHER_GROSS_BALANCE_SHEET"
            or behavior["unit"] != "USD_millions" or behavior["source"] not in sources):
        raise ValueError("BEHAVIOR_SCOPE")
    flows, balances = [], []
    for rows, fields, output in (
        (behavior["flows"], ("purchases", "sales"), flows),
        (behavior["balances"], ("cash_equivalents", "short_term_treasury_bills", "listed_equity_securities"), balances),
    ):
        years = set()
        for row in rows:
            year = row["year"]
            if type(year) is not int or year in years or year >= int(sources[behavior["source"]]["date"][:4]):
                raise ValueError("YEAR_OR_DUPLICATE")
            years.add(year)
            if any(number(row[k]) < 0 for k in fields):
                raise ValueError("NEGATIVE_AMOUNT")
            output.append(dict(row))
    for row in flows:
        row["net_equity_sales"] = row["sales"] - row["purchases"]
    for row in balances:
        row["gross_cash_plus_tbill"] = row["cash_equivalents"] + row["short_term_treasury_bills"]
    return {"sources": len(sources), "claims": len(claims), "modality_counts": counts,
            "flows": flows, "balances": balances, "forecast_scoreable_claims": 0,
            "independent_investor_sample": None, "motive_identified": False,
            "raw_source_bytes_admitted": 0, "market_outcomes_read": False,
            "production_effect": "NONE"}


if __name__ == "__main__":
    print(json.dumps(diagnostics(json.loads(PILOT.read_text(encoding="utf-8"))), indent=2))
