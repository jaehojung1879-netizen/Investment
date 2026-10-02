"""Manual-only ECOS metadata and smoke validation. No values, URLs or secrets saved.

Only fixed API services are used. Missing/ambiguous semantic selectors remain
unresolved. Exact selection can be provided in an audited JSON input; it is
checked against fresh table/item metadata before any smoke request.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import ecos_macro as EM  # noqa: E402

# Approved semantic descriptions, NOT guesses at item codes. Corporate yield
# requires an explicit rating choice rather than merging AA-/BBB- under a label.
SEMANTICS = {
    "BaseRate": ("한국은행 기준금리",), "KTB_3Y": ("국고채(3년)",),
    "CorpBond_3Y": ("회사채(3년, AA-)", "회사채(3년, BBB-)"),
    "CPI": ("소비자물가지수", "총지수"),
    "CoreCPI": ("농산물 및 석유류 제외지수", "식료품 및 에너지 제외지수"),
    "IndustrialProduction": ("전산업생산지수", "광공업생산지수"),
    "LeadingIndex": ("선행지수", "선행지수 순환변동치"),
    "Exports": ("수출", "수출금액"), "M2": ("M2", "M2(광의통화)"),
}
# Broad catalog discovery terms expose alternatives to incorrect placeholders.
# They NEVER select an item; automatic selection still requires exact semantics.
TABLE_SEARCH = {
    "BaseRate": ("기준금리",), "KTB_3Y": ("시장금리",), "CorpBond_3Y": ("시장금리",),
    "CPI": ("소비자물가",), "CoreCPI": ("소비자물가", "근원"),
    "IndustrialProduction": ("생산", "광공업"), "LeadingIndex": ("경기종합", "선행"),
    "Exports": ("수출", "수출입", "무역", "국제수지"), "M2": ("M2", "광의통화"),
}
TABLE_FIELDS = ("STAT_CODE", "STAT_NAME", "CYCLE", "SRCH_YN", "ORG_NAME")
ITEM_FIELDS = ("STAT_CODE", "STAT_NAME", "GRP_CODE", "GRP_NAME", "ITEM_CODE", "ITEM_NAME",
               "CYCLE", "START_TIME", "END_TIME", "DATA_CNT", "UNIT_NAME")


def clean(row, fields):
    return {k: row.get(k) for k in fields}


def metadata(key, service, code=None):
    collected = []
    for first in range(1, 20001, 1000):
        parts = [first, first+999] + ([code] if code else [])
        payload, error = EM.request(key, service, *parts)
        rows, error = ([], error) if error else EM.parse_service(payload, service)
        if error:
            return [], error
        collected.extend(rows)
        total = payload[service].get("list_total_count")
        if len(rows) < 1000 or (total is not None and first+999 >= int(total)):
            return collected, None
    return [], "PAGINATION_LIMIT"


def validate_selection(name, selection, table, items):
    """Exact identities and native cycle checked. No first-row/default selection."""
    if not selection or not table or table.get("SRCH_YN") != "Y":
        return None, "DATA_LINEAGE_UNRESOLVED"
    cycle = selection.get("cycle")
    if cycle not in {"D", "M", "Q", "A"}:
        return None, "DATA_LINEAGE_UNRESOLVED"
    groups = {}
    for item in items:
        if item.get("CYCLE") == cycle:
            groups.setdefault(item.get("GRP_CODE"), []).append(item)
    selected = []
    for group_index, (_, rows) in enumerate(sorted(groups.items()), 1):
        code = selection.get("itemCode" if group_index == 1 else f"itemCode{group_index}")
        matches = [r for r in rows if r.get("ITEM_CODE") == code]
        if len(matches) != 1:
            return None, "AMBIGUOUS_SOURCE"
        selected.append(matches[0])
    if not selected or len(groups) > 4 or not selected[0].get("UNIT_NAME"):
        return None, "DATA_LINEAGE_UNRESOLVED"
    # Semantic meaning must be explicitly reviewed, including table name,
    # unit, seasonal adjustment and corporate rating, not inferred by code.
    expected_names = selection.get("expectedItemNames")
    if (expected_names != [r.get("ITEM_NAME") for r in selected]
            or selection.get("expectedTableName") != table.get("STAT_NAME")
            or selection.get("expectedUnit") != selected[0].get("UNIT_NAME")
            or selection.get("semanticName") != name):
        return None, "DATA_LINEAGE_UNRESOLVED"
    primary = selected[0]
    if not any(token in str(primary.get("ITEM_NAME")) or token in str(table.get("STAT_NAME"))
               for token in SEMANTICS[name]):
        return None, "DATA_LINEAGE_UNRESOLVED"
    return selected, None


def automatic_selection(name, table, items):
    """Only unique exact semantic item names; no substring or first-row guessing."""
    if not table:
        return None, "NOT_AVAILABLE"
    normalize = lambda value: "".join(str(value).split())
    meanings = {normalize(token) for token in SEMANTICS[name]}
    primary = [r for r in items if r.get("GRP_CODE") == "Group1"
               and normalize(r.get("ITEM_NAME")) in meanings]
    if len(primary) != 1:
        return None, "AMBIGUOUS_SOURCE" if len(primary) > 1 else "DATA_LINEAGE_UNRESOLVED"
    cycle = primary[0].get("CYCLE")
    groups = {}
    for item in items:
        if item.get("CYCLE") == cycle:
            groups.setdefault(item.get("GRP_CODE"), []).append(item)
    selected = []
    for group, rows in sorted(groups.items()):
        match = primary if group == "Group1" else rows
        if len(match) != 1:
            return None, "AMBIGUOUS_SOURCE"
        selected.append(match[0])
    selection = {"seriesId": table["STAT_CODE"], "cycle": cycle, "semanticName": name,
                 "expectedTableName": table.get("STAT_NAME"),
                 "expectedItemNames": [r.get("ITEM_NAME") for r in selected],
                 "expectedUnit": primary[0].get("UNIT_NAME")}
    for index, row in enumerate(selected, 1):
        selection["itemCode" if index == 1 else f"itemCode{index}"] = row["ITEM_CODE"]
    return selection, None


def probe(key, config, selections=None):
    selections = selections or {}
    tables, catalog_error = metadata(key, "StatisticTableList")
    table_map = {r["STAT_CODE"]: r for r in tables if r.get("STAT_CODE")}
    cache, output, validated = {}, [], {}
    for name, original in config.items():
        chosen = selections.get(name)
        code = (chosen or original).get("seriesId")
        table = table_map.get(code)
        # Relevant metadata includes alternatives to wrong placeholder tables;
        # it does not automatically redefine a series from fuzzy matches.
        candidates = [r for r in tables if r.get("STAT_CODE") == code or any(
            token in str(r.get("STAT_NAME")) for token in TABLE_SEARCH[name])]
        item_candidates = []
        for candidate in candidates:
            stat = candidate["STAT_CODE"]
            if stat not in cache:
                cache[stat] = metadata(key, "StatisticItemList", stat)
            rows, _ = cache[stat]
            item_candidates.extend(clean(r, ITEM_FIELDS) for r in rows)
        if code not in cache and table:
            cache[code] = metadata(key, "StatisticItemList", code)
        items, item_error = cache.get(code, ([], "TABLE_NOT_FOUND"))
        selection_error = None
        if chosen is None:
            chosen, selection_error = automatic_selection(name, table, items)
        selected, error = validate_selection(name, chosen, table, items)
        error = selection_error or error
        if catalog_error or item_error:
            error = "NOT_AVAILABLE" if item_error in {"INFO-200", "TABLE_NOT_FOUND"} else "DATA_LINEAGE_UNRESOLVED"
        row = {"name": name, "configuredCandidate": original, "tableExists": bool(table),
               "table": clean(table, TABLE_FIELDS) if table else None,
               "candidateTables": [clean(r, TABLE_FIELDS) for r in candidates],
               "candidateItems": item_candidates, "sourceStatus": error,
               "vintageStatus": "REVISED_HISTORY", "publishedAt": None,
               "availableFrom": None, "historicalConfirmatoryEligible": False,
               "selectedItems": None, "smoke": None}
        if not error:
            row["selectedItems"] = [clean(r, ITEM_FIELDS) for r in selected]
            # One metadata-advertised latest period, all selectors; discard values.
            cycle = chosen["cycle"]
            end = min(r["END_TIME"] for r in selected)
            parts = [1, 10, code, cycle, end, end]
            parts.extend(r["ITEM_CODE"] for r in selected)
            payload, smoke_error = EM.request(key, "StatisticSearch", *parts)
            smoke_rows, smoke_error = ([], smoke_error) if smoke_error else EM.parse_response(payload)
            correct = [r for r in smoke_rows if r.get("STAT_CODE") == code and r.get("TIME") == end
                       and all(r.get(f"ITEM_CODE{i}") == s["ITEM_CODE"] for i,s in enumerate(selected,1))
                       and EM.row_to_observation(r)[1] is not None]
            good = not smoke_error and bool(correct)
            row["sourceStatus"] = "LIVE_VALIDATED_SOURCE" if good else "DATA_LINEAGE_UNRESOLVED"
            row["smoke"] = {"validObservationFound": good, "period": end, "errorCode": smoke_error}
            if good:
                allowed = {k:v for k,v in chosen.items() if k in {"seriesId", "itemCode", "itemCode2", "itemCode3", "itemCode4", "cycle"}}
                allowed.update(sourceStatus="LIVE_VALIDATED_SOURCE", vintageStatus="REVISED_HISTORY",
                    unit=selected[0]["UNIT_NAME"], itemName=selected[0]["ITEM_NAME"],
                    validationEvidenceSha256=hashlib.sha256(json.dumps(row["selectedItems"], sort_keys=True, ensure_ascii=False).encode()).hexdigest())
                validated[name] = allowed
        output.append(row)
    return {"contract": "ECOS_MARKET_CONTEXT_SOURCE_PROBE_V1", "checkedAt": datetime.now(timezone.utc).isoformat(),
            "credentialMode": "MANUAL_ACTIONS_SECRET_ECOS", "sourceHead": os.environ.get("GITHUB_SHA"), "series": output,
            "validatedConfig": validated, "catalogError": catalog_error,
            "vintageEvidence": {"status": "NO_RELEASE_VINTAGE_EVIDENCE",
                "servicesInspected": ["StatisticTableList", "StatisticItemList", "StatisticSearch"],
                "observationCoverageIsNotPublicationCoverage": True,
                "inventedVintageEndpoint": False},
            "historicalOutcomeComputed": False, "modelFitPerformed": False}


def safe_json(value, key):
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
    if key and any(token in serialized for token in {key, quote(key, safe=""), json.dumps(key)[1:-1]}):
        raise ValueError("REDACTION_GUARD_REJECTED_OUTPUT")
    return serialized + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # Refuse live access even with a supplied key outside the authorized job.
    if os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch" or os.environ.get("ECOS_MANUAL_PROBE") != "1":
        raise ValueError("MANUAL_WORKFLOW_REQUIRED")
    key = os.environ.get("ECOS_API_KEY", "")
    if not key:
        result = {"sourceStatus": "NOT_AVAILABLE", "reason": "ECOS_SECRET_MISSING"}
    else:
        config = json.loads((ROOT / "config.json").read_text())["ecos"]["KR"]
        selections = json.loads(os.environ.get("ECOS_SELECTIONS", "{}") or "{}")
        result = probe(key, config, selections)
    body = safe_json(result, key)
    result_digest = hashlib.sha256(body.encode()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        stream.write(body)
    print("ECOS metadata probe completed; sanitized output sha256=" + result_digest)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Tracebacks can carry a credential-bearing URL from a network layer.
        print("ECOS_PROBE_FAILED_CLOSED; no raw diagnostic retained", file=sys.stderr)
        sys.exit(1)
