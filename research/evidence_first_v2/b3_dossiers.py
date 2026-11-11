"""Assemble the B3 (AI committee) dossiers for the B1 deep-review names and validate them.

python research/evidence_first_v2/b3_dossiers.py

FACT rows are generated from results/census.json by contract.facts_from_census; the AI text comes
from ai-dossiers-2026-11.json and may not contain a digit. Every dossier is checked by
contract.validate_dossier before results/b3-dossiers.json is written. The B3 path is a challenger:
its status can never exceed what the nominating path's evidence grade allows (E1 -> HOLD_FOR_RESEARCH).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from contract import compute_grade, facts_from_census, validate_dossier

HERE = Path(__file__).resolve().parent
CENSUS = HERE / "results" / "census.json"
TEXT = HERE / "ai-dossiers-2026-11.json"
GRADES = HERE / "evidence-grades.json"
OUT = HERE / "results" / "b3-dossiers.json"
NOMINATING_ITEM = {"KR": "ACADEMIC_PROFITABILITY_KR", "US": "ACADEMIC_PROFITABILITY_US"}


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def build() -> dict:
    census = json.loads(CENSUS.read_text())
    text = json.loads(TEXT.read_text())
    grades = {it["id"]: it for it in json.loads(GRADES.read_text())["items"]}
    census_ref = f"results/census.json sha256 {_sha(CENSUS)[:16]}"
    out, seen = [], set()
    for region in ("KR", "US"):
        reg = census["regions"][region]
        rows = {r["ticker"]: r for r in reg["b1"]["topQuintile"]}
        item = grades[NOMINATING_ITEM[region]]
        grade = compute_grade(item)
        for ticker in reg["b1"]["deepReview"]:
            row = rows[ticker]
            body = text["dossiers"][ticker]
            d = {"ticker": ticker, "name": row["name"], "region": region,
                 "informationCutoff": reg["asOf"],
                 "origin": {"path": "v3.B1", "rule": "B1_PROFITABILITY_V1", "rank": reg["b1"]["deepReview"].index(ticker) + 1,
                            "inProductionWatchlist": ticker in reg["productionComparison"]["both"]},
                 "nominatingEvidence": {"item": item["id"], "grade": grade, "blocks": item.get("blocks", [])},
                 "facts": facts_from_census(region, row, reg["asOf"], census_ref),
                 **{k: body[k] for k in ("interpretation", "background", "counterArguments", "invalidationConditions", "unknowns")},
                 "status": "HOLD_FOR_RESEARCH",
                 "statusReason": "The nominating screen is graded " + grade + "; nothing below E2 can propose capital. "
                                 "The decision for the region stays the ETF."}
            validate_dossier(d, grade, rows)
            out.append(d)
            seen.add(ticker)
    extra = set(text["dossiers"]) - seen
    if extra:
        raise ValueError(f"AI_TEXT_FOR_A_NAME_NO_SCREEN_NOMINATED {sorted(extra)}")
    return {"schema": "B3_DOSSIERS_V1", "path": "v3.B3", "role": "EXPERIMENTAL_CHALLENGER",
            "author": text["author"], "knowledgeLimit": text["knowledgeLimit"],
            "censusSha256": _sha(CENSUS), "textSha256": _sha(TEXT),
            "concentrationNote": {"KR": "HD현대일렉트릭 and HD현대마린솔루션 share a group; two of five names.",
                                  "US": "NVDA, KLAC, WDC and LRCX are semiconductors, semicap or storage hardware; four of five names."},
            "regionDecision": {"KR": "ETF_DEFAULT (069500.KS)", "US": "ETF_DEFAULT (SPY)"},
            "dossiers": out}


if __name__ == "__main__":
    res = build()
    OUT.write_text(json.dumps(res, indent=1, ensure_ascii=False, sort_keys=True) + "\n")
    print("dossiers", len(res["dossiers"]), "->", OUT.relative_to(HERE))
