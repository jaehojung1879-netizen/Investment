"""Publication contract for desk.json (the #333 four-type rule, plus production receipts).

Refuses: an unknown type; a SOURCE_BLOCKED item carrying a performance number; a
RESEARCH_ALLOCATION_AS_OF without its timestamps or generated after its execution; a
historical item marked as a current recommendation; any probability/target claim.
"""
from __future__ import annotations

import ledger as L

TYPES = {"HISTORICAL_EXPLORATORY", "CORRECTED_CASH_SCOPE", "SOURCE_BLOCKED", "RESEARCH_ALLOCATION_AS_OF", "PRODUCTION_RECEIPT"}
METRICS = ("cagrPct", "excessVsEtfPp", "sharpe", "mddPct")


class DeskError(ValueError):
    pass


def _alloc_ok(item: dict) -> None:
    for k in ("signalAsOf", "informationCutoff", "generatedAt", "executionAt"):
        if not item.get(k):
            raise DeskError(f"ALLOCATION_MISSING_{k} {item.get('id')}")
    if str(item["generatedAt"])[:10] > str(item["executionAt"]):
        raise DeskError(f"ALLOCATION_GENERATED_AFTER_EXECUTION {item.get('id')}")
    if str(item["informationCutoff"]) > str(item["generatedAt"])[:10]:
        raise DeskError(f"CUTOFF_AFTER_GENERATION {item.get('id')}")


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
