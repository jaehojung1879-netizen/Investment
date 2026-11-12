"""Publication contract for desk.json (the #333 four-type rule, plus production receipts).

Refuses: an unknown type; a SOURCE_BLOCKED item carrying a performance number; a
RESEARCH_ALLOCATION_AS_OF without its timestamps or generated after its execution; a
historical item marked as a current recommendation; any probability/target claim.
Evidence-first v2: a graded item that is decision-eligible below E4 or while blocked, an AI dossier
whose status exceeds HOLD_FOR_RESEARCH / ETF_DEFAULT below E2, or AI text carrying a digit.
"""
from __future__ import annotations

import re

import ledger as L

TYPES = {"HISTORICAL_EXPLORATORY", "CORRECTED_CASH_SCOPE", "SOURCE_BLOCKED", "RESEARCH_ALLOCATION_AS_OF", "PRODUCTION_RECEIPT"}
METRICS = ("cagrPct", "excessVsEtfPp", "sharpe", "mddPct")


class DeskError(ValueError):
    pass


def _alloc_ok(item: dict) -> None:
    for k in ("signalAsOf", "informationCutoff", "generatedAt", "executionAt"):
        if not item.get(k):
            raise DeskError(f"ALLOCATION_MISSING_{k} {item.get('id')}")
    if str(item["generatedAt"])[:10] > str(item["executionAt"])[:10]:
        raise DeskError(f"ALLOCATION_GENERATED_AFTER_EXECUTION {item.get('id')}")
    if _when(item["informationCutoff"]) > _when(item["generatedAt"], date_end=False):
        raise DeskError(f"CUTOFF_AFTER_GENERATION {item.get('id')}")


def _when(v, date_end: bool = True):
    """A full timestamp compares as itself; a date-only cutoff is the end of that day (#335 G3)."""
    import pandas as pd
    t = pd.Timestamp(str(v))
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    if len(str(v)) == 10 and date_end:
        t = t + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    return t


def validate(desk: dict) -> None:
    hits = L._forbidden(desk)
    if hits:
        raise DeskError(f"FORBIDDEN_NUMERIC_CLAIM {hits}")
    for row in desk["history"]:
        if row["type"] not in TYPES - {"RESEARCH_ALLOCATION_AS_OF", "PRODUCTION_RECEIPT"}:
            raise DeskError(f"BAD_HISTORY_TYPE {row['type']}")
        if row["type"] == "SOURCE_BLOCKED" and any(row.get(m) is not None for m in METRICS):
            raise DeskError(f"SOURCE_BLOCKED_WITH_NUMBER {row['strategy']}")
        if not row.get("period") or not row.get("source", {}).get("blob"):
            raise DeskError(f"HISTORY_ROW_WITHOUT_PERIOD_OR_SOURCE {row['strategy']}")
    for region, reg in desk["regions"].items():
        if reg["production"]["type"] != "PRODUCTION_RECEIPT" or not reg["production"].get("digest"):
            raise DeskError(f"PRODUCTION_RECEIPT_MISSING {region}")
        for item in reg["research"] + reg["deskRecords"] + reg.get("historicalAllocations", []):
            if item["type"] not in TYPES:
                raise DeskError(f"BAD_TYPE {item['type']}")
            if item["type"] == "RESEARCH_ALLOCATION_AS_OF":
                _alloc_ok(item)
            if item["type"] == "SOURCE_BLOCKED" and item.get("weights"):
                raise DeskError(f"SOURCE_BLOCKED_WITH_WEIGHTS {item.get('id')}")
            if item["type"] == "HISTORICAL_EXPLORATORY" and item.get("currentRecommendation") is not False:
                raise DeskError(f"HISTORICAL_ITEM_MUST_DECLARE_NOT_CURRENT {item.get('id')}")

    ef = desk.get("evidenceFirst")
    if ef is None:
        raise DeskError("EVIDENCE_FIRST_MISSING")
    for g in ef["grades"]:
        if g["decisionEligible"] and g["grade"] != "BENCHMARK" and (g["grade"] not in ("E4", "E5") or g["blocks"]):
            raise DeskError(f"ELIGIBLE_WITHOUT_EVIDENCE {g['id']}")
    for g in ef["grades"]:
        if g.get("track") == "A_VERIFIED_STRATEGY" and g["grade"] != "E5":
            raise DeskError(f"VERIFIED_TRACK_WITHOUT_E5 {g['id']}")
    pr = ef["prospective"]
    if pr["activation"] == "ALLOWED" and any(x["status"] != "RESOLVED" and "ALL" in x["blocks"] for x in pr["gates"]):
        raise DeskError("ACTIVATION_SHOWN_WHILE_A_GATE_IS_OPEN")
    for region, v in pr["dryRun"].items():
        for arm in v["arms"].values():
            if arm.get("track") == "B_PROSPECTIVE_VIRTUAL" and arm.get("recordLabel") != "UNVERIFIED_PROSPECTIVE_VIRTUAL":
                raise DeskError(f"VIRTUAL_ARM_WITHOUT_UNVERIFIED_LABEL {region}")
    for d in ef["dossiers"]["dossiers"]:
        low = d["nominatingEvidence"]["grade"] not in ("E2", "E3", "E4", "E5")
        if d["status"] not in ("HOLD_FOR_RESEARCH", "ETF_DEFAULT") and low:
            raise DeskError(f"DOSSIER_STATUS_ABOVE_EVIDENCE {d['ticker']}")
        for f in ("interpretation", "background", "counterArguments", "invalidationConditions", "unknowns"):
            if any(re.search(r"\d", x) for x in d[f]):
                raise DeskError(f"NUMBER_IN_AI_TEXT {d['ticker']}")
