"""Revision diagnostics and narrative evidence validation, no outcome evaluation."""
from __future__ import annotations

import json
from pathlib import Path

from .ledger import day, indexed, number

PILOT = Path(__file__).with_name("mechanism_pilot.json")
MEASURES = ("stocks", "gdp", "cpi", "unemployment", "t_bill", "t10")
SCOPES = {"A_FEW", "MOST", "MANY", "STAFF"}
MODALITIES = {"CONDITIONAL_EXPECTATION", "RISK_SCENARIO", "EXPECTATION", "ATTRIBUTED_OBSERVATION"}


def diagnostics(data):
    if data["schema"] != "NARRATIVE_MECHANISM_PILOT_V1" or data["investment_evaluation_authorized"] is not False:
        raise ValueError("SCHEMA_OR_AUTHORIZATION")
    clock = day(data["as_of"])
    docs, releases, claims = (indexed(data[key]) for key in ("docs", "releases", "claims"))
    for source in [*docs.values(), *releases.values()]:
        if source["raw_sha256"] is not None or not source["url"].startswith("https://"):
            raise ValueError("SOURCE_PROVENANCE")
    for source in docs.values():
        if not day(source["event"]) < day(source["public"]) <= clock:
            raise ValueError("PUBLICATION_CLOCK")
        if not source["release_url"].startswith("https://"):
            raise ValueError("RELEASE_SOURCE_REQUIRED")
    ordered = sorted(releases.values(), key=lambda x: day(x["publication"]))
    for row in ordered:
        if day(row["publication"]) > clock:
            raise ValueError("FUTURE_RELEASE")
        if row["submission_end"] is not None and day(row["submission_end"]) > day(row["publication"]):
            raise ValueError("SUBMISSION_CLOCK")
        n = row["stock_n"]
        if row["stocks"] and (type(n) is not int or not 0 < n <= row["population"]):
            raise ValueError("STOCK_SAMPLE_COUNT")
        for key in MEASURES:
            for target, val in row[key].items():
                number(val)
                if key == "stocks":
                    if day(target) <= day(row["publication"]) or val <= 0:
                        raise ValueError("INVALID_STOCK_TARGET")
    revisions = []
    for a, b in zip(ordered, ordered[1:]):
        for metric in MEASURES:
            for target in sorted(a[metric].keys() & b[metric].keys()):
                old, new = a[metric][target], b[metric][target]
                revisions.append({
                    "old_source": a["id"], "new_source": b["id"],
                    "metric": metric, "target": target, "old": old, "new": new,
                    "delta": round(new - old, 10),
                    "relative_revision_pct": round(100 * (new / old - 1), 6) if metric == "stocks" else None,
                    "same_panel_verified": False,
                })
    for claim in claims.values():
        src = docs[claim["source"]]
        if claim["scope"] not in SCOPES or claim["type"] not in MODALITIES:
            raise ValueError("MODALITY_OR_SCOPE")
        if (claim["scope"] == "STAFF") != (claim["actor"] == "Federal Reserve staff"):
            raise ValueError("ACTOR_SCOPE")
        if not all(claim.get(k) for k in ("subject", "mechanism", "locator", "test")):
            raise ValueError("MISSING_MECHANISM_EVIDENCE")
        if "probability" in claim or "population_share" in claim:
            raise ValueError("UNOBSERVED_PROBABILITY")
        if day(src["public"]) > clock:
            raise ValueError("FUTURE_CLAIM")
    for contrast in data["contrasts"]:
        a, b = (claims[contrast[k]] for k in ("left", "right"))
        if a["subject"] != b["subject"]:
            raise ValueError("UNMATCHED_SUBJECT")
        if contrast["kind"] == "SAME_SOURCE_COMPETING_HYPOTHESES" and a["source"] != b["source"]:
            raise ValueError("UNMATCHED_SOURCE")
        if not contrast["note"]:
            raise ValueError("MISSING_CONTRAST_LIMITATION")
    for candidate in data["prospective_candidates"]:
        if candidate["kind"] != "DESIGN_ONLY" or candidate["source_claim"] not in claims or not candidate["blocker"]:
            raise ValueError("UNAUTHORIZED_FORECAST")
    return {"classification": "EXPLORATORY_AUTHOR_VALIDATION_ONLY", "releases": len(releases),
            "stock_table_releases": sum(bool(r["stocks"]) for r in releases.values()),
            "mechanism_claims": len(claims), "document_count": len(docs),
            "revisions": revisions, "candidate_count": len(data["prospective_candidates"]),
            "raw_source_bytes_admitted": 0, "prospective_forecasts_registered": 0,
            "market_outcomes_read": False, "investment_evaluation_authorized": False,
            "production_effect": "NONE"}


if __name__ == "__main__":
    print(json.dumps(diagnostics(json.loads(PILOT.read_text(encoding="utf-8"))), indent=2, allow_nan=False))
