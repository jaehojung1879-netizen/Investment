"""Evidence grades, the versioned path mapping and the B3 (AI committee) judgment contract.

GRADES   compute_grade() applies the sequential E0..E5 rule; validate_grades() refuses a matrix
         whose stated grade skips a level, an E5 without an Owner approval reference, or a
         blocked item marked decision-eligible.
PATHS    v3 path names (B0 ETF, B1 academic, B2 production rule, B3 AI committee) mapped onto the
         decision-desk-v1 ledger without rewriting any legacy record: legacy B1 = production copy,
         legacy B2 / BX = AI.
B3       an AI dossier keeps sourced FACT rows (generated from the census, never typed) apart
         from AI text; AI text may not contain a single digit, so every number on the page has a
         source and a date. Status is HOLD_FOR_RESEARCH or ETF_DEFAULT while the nominating path
         is below E2.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
LEVELS = ["E1", "E2", "E3", "E4", "E5"]
BLOCKS = {"SOURCE_BLOCKED", "PIT_UNSAFE", "PIT_CONTAMINATED", "GOVERNANCE_CLOSED"}
B3_STATUSES = {"HOLD_FOR_RESEARCH", "ETF_DEFAULT", "PROSPECTIVE_CANDIDATE"}
FORBIDDEN = {"probability", "targetprice", "expectedreturn", "confidencepct", "winrate", "consensus"}

LEGACY_TO_V3 = {"B0": "v3.B0", "B1": "v3.B2", "B2": "v3.B3", "BX": "v3.B3"}
V3_PATHS = {
    "v3.B0": "지역 ETF (069500.KS / SPY; QQQ 별도 비교)",
    "v3.B1": "선행연구 기반 단순 정량 경로 (B1_PROFITABILITY_V1)",
    "v3.B2": "기존 production 규칙 (weekly-passive-first-v1 영수증 복사)",
    "v3.B3": "AI 투자위원회형 분석 (실험용 challenger)",
}


class ContractError(ValueError):
    pass


# ----------------------------------------------------------------------------- grades
def compute_grade(item: dict) -> str:
    grade = "E0"
    for lvl in LEVELS:
        if item.get("criteria", {}).get(lvl, {}).get("met") is True:
            grade = lvl
        else:
            break
    return grade


def validate_grades(matrix: dict) -> dict:
    out = {}
    for it in matrix["items"]:
        crit = it.get("criteria", {})
        met = [lvl for lvl in LEVELS if crit.get(lvl, {}).get("met") is True]
        g = compute_grade(it)
        if met and met[-1] != g:
            raise ContractError(f"GRADE_SKIPS_A_LEVEL {it['id']}: met {met} but sequential grade {g}")
        if g == "E5" and not crit["E5"].get("ownerApproval"):
            raise ContractError(f"E5_WITHOUT_OWNER_APPROVAL {it['id']}")
        for c in crit.values():
            if c.get("met") is True and not c.get("ref"):
                raise ContractError(f"CRITERION_WITHOUT_EVIDENCE {it['id']}")
        if not set(it.get("blocks", [])) <= BLOCKS:
            raise ContractError(f"UNKNOWN_BLOCK {it['id']}")
        if it.get("benchmark"):
            out[it["id"]] = {"grade": "BENCHMARK", "blocks": [], "decisionEligible": True}
            continue
        out[it["id"]] = {"grade": g, "blocks": it.get("blocks", []),
                         "decisionEligible": g in ("E4", "E5") and not it.get("blocks")}
    return out


# ----------------------------------------------------------------------------- paths
def v3_path(record: dict) -> str:
    """Map a decision-desk ledger record (any schema) to its v3 path name without touching it."""
    return LEGACY_TO_V3[record["path"]]


# ----------------------------------------------------------------------------- B3 contract
def _forbidden(obj, path="") -> list[str]:
    hits = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in FORBIDDEN:
                hits.append(f"{path}/{k}")
            hits += _forbidden(v, f"{path}/{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits += _forbidden(v, f"{path}/{i}")
    return hits


AI_TEXT_FIELDS = ("interpretation", "background", "counterArguments", "invalidationConditions", "unknowns")


def validate_dossier(d: dict, nominating_grade: str, census_rows: dict) -> None:
    for f in ("ticker", "region", "informationCutoff", "origin", "facts", "status") + AI_TEXT_FIELDS:
        if f not in d:
            raise ContractError(f"DOSSIER_MISSING {f} {d.get('ticker')}")
    if d["status"] not in B3_STATUSES:
        raise ContractError("BAD_STATUS")
    if d["status"] == "PROSPECTIVE_CANDIDATE" and nominating_grade not in ("E2", "E3", "E4", "E5"):
        raise ContractError(f"STATUS_ABOVE_EVIDENCE {d['ticker']}: nominating path is {nominating_grade}")
    hits = _forbidden(d)
    if hits:
        raise ContractError(f"FORBIDDEN_FIELD {hits}")
    for f in AI_TEXT_FIELDS:
        for line in d[f]:
            if re.search(r"\d", line):
                raise ContractError(f"NUMBER_IN_AI_TEXT {d['ticker']} {f}: every number must be a sourced FACT")
    if len(d["counterArguments"]) < 2 or not d["invalidationConditions"] or not d["unknowns"]:
        raise ContractError(f"NEEDS_COUNTER_ARGUMENTS_INVALIDATION_AND_UNKNOWNS {d['ticker']}")
    row = census_rows.get(d["ticker"])
    if row is None:
        raise ContractError(f"NOT_NOMINATED_BY_A_QUANT_SCREEN {d['ticker']}")
    for fact in d["facts"]:
        src = fact.get("source") or {}
        if not src.get("availableFrom") or src["availableFrom"] > d["informationCutoff"]:
            raise ContractError(f"FACT_NOT_PUBLIC_AT_CUTOFF {d['ticker']} {fact.get('field')}")
        if fact["field"] in row and abs(float(row[fact["field"]]) - float(fact["value"])) > 1e-9:
            raise ContractError(f"FACT_DIFFERS_FROM_SOURCE {d['ticker']} {fact['field']}")


def facts_from_census(region: str, row: dict, as_of: str, census_ref: str) -> list[dict]:
    """FACT rows are generated, never typed: values copied from the census with their filing dates."""
    fin = {"availableFrom": row["roeFrom"]["availableFrom"], "reportDate": row["roeFrom"]["reportDate"],
           "path": f"signal-history ledger/fundamentals/pit-{region.lower()} (derived)", "census": census_ref}
    px = {"availableFrom": as_of, "reportDate": as_of, "path": "KRX daily close" if region == "KR" else "Yahoo daily close",
          "census": census_ref}
    return [{"field": "roe", "label": "ROE (TTM, PIT)", "value": row["roe"], "source": fin},
            {"field": "operatingMargin", "label": "영업이익률 (TTM, PIT)", "value": row["operatingMargin"], "source": fin},
            {"field": "debtToEquity", "label": "부채/자본", "value": row["debtToEquity"], "source": fin},
            {"field": "bookToPrice", "label": "장부가/주가", "value": row["bookToPrice"], "source": px},
            {"field": "momentum12_2", "label": "12-2개월 수익률", "value": row["momentum12_2"], "source": px}]


def load_json(name: str) -> dict:
    return json.loads((HERE / name).read_text())
