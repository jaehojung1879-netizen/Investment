"""Narrative pilot: deterministic claim validation and revision diagnostics.

No LLM score, no price joins or investment outcomes, no automated trading.
The manually transcribed archive is not historical PIT-certified.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import date
from pathlib import Path
from statistics import mean

PILOT = Path(__file__).with_name("pilot.json")
KEY = ("actor", "metric", "target", "unit")


def day(value):
    if not isinstance(value, str):
        raise ValueError("DATE_REQUIRED")
    d = date.fromisoformat(value)
    if d.isoformat() != value:
        raise ValueError("DATE_REQUIRED")
    return d


def indexed(items):
    result = {}
    for item in items:
        key = item["id"]
        if not key or key in result:
            raise ValueError("DUPLICATE_OR_EMPTY_ID")
        result[key] = item
    return result


def number(value):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError("FINITE_NUMBER_REQUIRED")
    return value


def target_end(target):
    if len(target) == 4 and target.isdigit():
        return date(int(target), 12, 31)
    if len(target) == 6 and target[:4].isdigit() and target[4] == "Q" and target[5] in "1234":
        month = int(target[5]) * 3
        return date(int(target[:4]), month, 30 if month in (6, 9) else 31)
    raise ValueError("INVALID_TARGET")


def prepare(ledger):
    if ledger["schema"] != "NARRATIVE_BELIEF_PILOT_V1":
        raise ValueError("SCHEMA")
    clock = day(ledger["as_of_date"])
    sources = indexed(ledger["sources"])
    claims = indexed(ledger["claims"])
    for item in sources.values():
        if not item["url"].startswith("https://") or not item["locator"] or not item["paraphrase"]:
            raise ValueError("SOURCE_EVIDENCE_REQUIRED")
        if item["publication_date"] is not None and day(item["publication_date"]) > clock:
            raise ValueError("FUTURE_SOURCE")
        if item["access"] != "INDEXED_OFFICIAL_TEXT_NOT_RAW_BYTES" or item["raw_sha256"] is not None:
            raise ValueError("UNSUPPORTED_PROVENANCE")
    prepared = {}
    for item in claims.values():
        src = sources[item["source"]]
        published = day(src["publication_date"])
        if src["actor"] != item["actor"]:
            raise ValueError("ACTOR_MISMATCH")
        if not all(isinstance(item[k], str) and item[k] for k in KEY):
            raise ValueError("MISSING_TARGET_KEY")
        value = number(item["value"])
        if item["unit"] == "probability_percent" and not 0 <= value <= 100:
            raise ValueError("INVALID_PROBABILITY")
        if item["kind"] not in ("PUBLISHED_FORECAST", "REPORTED_PRIOR_FORECAST", "PUBLISHED_PROBABILITY"):
            raise ValueError("UNSUPPORTED_CLAIM_KIND")
        vintage = day(item.get("forecast_date", src["publication_date"]))
        available = day(item.get("available_date", src["publication_date"]))
        if not vintage <= published <= available <= clock:
            raise ValueError("INVALID_VINTAGE_ORDER")
        if item["kind"] == "REPORTED_PRIOR_FORECAST":
            if not vintage < published:
                raise ValueError("PRIOR_MUST_PREDATE_REPORT")
        elif vintage != published:
            raise ValueError("UNSUPPORTED_HISTORICAL_VINTAGE")
        if vintage >= target_end(item["target"]):
            raise ValueError("NOT_A_FUTURE_TARGET")
        if not isinstance(item["mechanisms"], list) or not all(isinstance(m, str) and m for m in item["mechanisms"]):
            raise ValueError("MECHANISM_SCHEMA")
        if "mechanism_source" in item:
            mech = sources[item["mechanism_source"]]
            if mech["actor"] != item["actor"] or day(mech["publication_date"]) > available:
                raise ValueError("MECHANISM_SOURCE_MISMATCH")
        prepared[item["id"]] = (item, vintage, available)
    return sources, prepared


def diagnostics(ledger):
    sources, claims = prepare(ledger)
    revisions = []
    seen = set()
    for before, after in ledger["comparisons"]:
        if (before, after) in seen:
            raise ValueError("DUPLICATE_COMPARISON")
        seen.add((before, after))
        a, va, aa = claims[before]
        b, vb, ab = claims[after]
        if tuple(a[k] for k in KEY) != tuple(b[k] for k in KEY):
            raise ValueError("MISMATCHED_TARGET")
        if not va < vb or aa > ab:
            raise ValueError("REVISION_CLOCK")
        revisions.append({
            "before": before, "after": after, "actor": a["actor"],
            "metric": a["metric"], "target": a["target"], "unit": a["unit"],
            "old": a["value"], "new": b["value"], "delta": round(b["value"] - a["value"], 10),
            "prior_independently_attested": a["kind"] != "REPORTED_PRIOR_FORECAST",
            "mechanisms_before": a["mechanisms"], "mechanisms_after": b["mechanisms"],
        })
    actuals = {}
    for item in ledger["resolutions"]:
        key = tuple(item[k] for k in KEY[1:])
        if key in actuals:
            raise ValueError("DUPLICATE_RESOLUTION")
        src = sources[item["source"]]
        resolved = day(src["publication_date"])
        if src["actor"] != "BEA" or resolved <= target_end(item["target"]):
            raise ValueError("BAD_RESOLUTION")
        actuals[key] = (number(item["value"]), resolved)
    errors = []
    for row in revisions:
        if row["actor"] != "IMF":
            continue
        key = tuple(row[k] for k in KEY[1:])
        if key not in actuals:
            continue
        actual, resolved = actuals[key]
        if claims[row["after"]][2] >= resolved:
            raise ValueError("FORECAST_AFTER_RESOLUTION")
        errors.append({
            "target": row["target"], "jan": row["old"], "jul": row["new"], "first_actual": actual,
            "jan_error_actual_minus_forecast": round(actual - row["old"], 10),
            "jul_error_actual_minus_forecast": round(actual - row["new"], 10),
        })
    for hyp in ledger["hypotheses"]:
        if hyp["status"] != "DESIGN_ONLY_NOT_FORECAST" or not hyp["support"] or not hyp["falsifier"]:
            raise ValueError("UNAUTHORIZED_FORECAST")
        if any(k not in claims for k in hyp["support"]):
            raise ValueError("MISSING_HYPOTHESIS_SUPPORT")
    return {
        "classification": "EXPLORATORY_AUTHOR_VALIDATION_ONLY", "sources": len(sources),
        "claims": len(claims), "revisions": revisions, "economic_errors": errors,
        "independent_year_blocks": len({r["target"] for r in errors}),
        "jan_mae": mean(abs(r["jan_error_actual_minus_forecast"]) for r in errors) if errors else None,
        "jul_mae": mean(abs(r["jul_error_actual_minus_forecast"]) for r in errors) if errors else None,
        "market_context_joined": False, "raw_source_bytes_admitted": 0,
        "prospective_forecasts_registered": 0, "investment_evaluation_authorized": False,
        "production_effect": "NONE",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=PILOT)
    args = parser.parse_args()
    print(json.dumps(diagnostics(json.loads(args.ledger.read_text(encoding="utf-8"))), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
