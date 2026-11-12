"""RESEARCH_OPPORTUNITY_REGISTER: load, validate, prioritise, render (schema: ../REGISTER_SCHEMA.md).

    python research/master_research_program_v1/evidence_map/register.py [--write]

``--write`` regenerates REGISTER.md and register.json beside this file from every lane's
``register-entries.json``. Validation fails closed: one bad entry stops the whole register.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

PROGRAM = Path(__file__).resolve().parents[1]
REQUIRED = ("researchId", "region", "track", "title", "economicMechanism", "overlapWithExisting",
            "pitSourceAndRights", "h126h252Feasibility", "effectiveSampleAndMde", "transactionCostMeasurable",
            "expectedEconomicImportance", "prerequisitesAndBlockers", "evidenceClass", "progressStatus",
            "highestGatePassed", "failedGate", "nextExecutionUnit", "ownerApprovalRequired", "priority",
            "evidenceRefs")
VOCAB = {
    "region": {"KR", "US", "COMMON"},
    "track": {"MARKET", "INDUSTRY", "STOCK", "PORTFOLIO", "DATA"},
    "evidenceClass": {"VERIFIED_EVIDENCE", "EXPLORATORY_EVIDENCE", "EMPIRICAL_FAIL", "SOURCE_BLOCKED",
                      "PREPARED_NOT_EXECUTED", "PROSPECTIVE_PENDING", "NOT_STARTED"},
    "progressStatus": {"ACTIVE", "SOURCE_BACKLOG", "CLOSED", "PARKED"},
    "highestGatePassed": {"NONE", "G0", "G1", "G2", "G3", "G4", "G5", "G6"},
}
GATES = ("G0", "G1", "G2", "G3", "G4", "G5", "G6")
PREFIXES = ("X-", "M-", "I-", "S1-", "S2-", "S3-", "S4-", "S5-", "P-", "D-")
SCORES = ("netReturnRelevance", "mechanism", "independence", "sourceObtainable", "timeToDecision", "krUsExtensible")
TIERS = ("P1", "P2", "P3")


def validate(entry: dict, where: str = "") -> None:
    rid = entry.get("researchId", "?")
    for f in REQUIRED:
        if f not in entry:
            raise ValueError(f"MISSING_FIELD:{f}:{rid}{where}")
    if not str(rid).startswith(PREFIXES):
        raise ValueError(f"BAD_ID_PREFIX:{rid}")
    for f, allowed in VOCAB.items():
        if entry[f] not in allowed:
            raise ValueError(f"BAD_VOCAB:{f}={entry[f]}:{rid}")
    if entry["failedGate"] is not None and entry["failedGate"] not in GATES:
        raise ValueError(f"BAD_VOCAB:failedGate:{rid}")
    if not isinstance(entry["ownerApprovalRequired"], bool):
        raise ValueError(f"BAD_TYPE:ownerApprovalRequired:{rid}")
    if not isinstance(entry["prerequisitesAndBlockers"], list) or not isinstance(entry["evidenceRefs"], list):
        raise ValueError(f"BAD_TYPE:list:{rid}")
    p = entry["priority"]
    if not isinstance(p, dict) or p.get("tier") not in TIERS:
        raise ValueError(f"BAD_PRIORITY_TIER:{rid}")
    for s in SCORES:
        v = p.get(s)
        if not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= 3:
            raise ValueError(f"BAD_PRIORITY_SCORE:{s}:{rid}")
    if entry["evidenceClass"] == "VERIFIED_EVIDENCE" and entry["highestGatePassed"] not in ("G5", "G6"):
        raise ValueError(f"VERIFIED_WITHOUT_G5:{rid}")


def load_all(root: Path = PROGRAM) -> list[dict]:
    entries, seen = [], {}
    for path in sorted(Path(root).rglob("register-entries.json")):
        for e in json.loads(path.read_text())["entries"]:
            validate(e, f"@{path}")
            if e["researchId"] in seen:
                raise ValueError(f"DUPLICATE_RESEARCH_ID:{e['researchId']}:{seen[e['researchId']]}|{path}")
            seen[e["researchId"]] = str(path)
            entries.append({**e, "_source": str(path.relative_to(root))})
    return entries


def prioritize(entries: list[dict]) -> list[dict]:
    return sorted(entries, key=lambda e: (TIERS.index(e["priority"]["tier"]),
                                          -sum(e["priority"][s] for s in SCORES), e["researchId"]))


def render_markdown(entries: list[dict]) -> str:
    out = ["# RESEARCH_OPPORTUNITY_REGISTER (generated; edit lane register-entries.json)", "",
           "| # | ID | 지역 | 영역 | 증거 등급 | 상태 | 통과/실패 관문 | 우선 | 점수 | Owner 승인 | 다음 실행 단위 |",
           "|---:|---|---|---|---|---|---|---|---:|---|---|"]
    for i, e in enumerate(prioritize(entries), 1):
        score = sum(e["priority"][s] for s in SCORES)
        gate = f"{e['highestGatePassed']}/{e['failedGate'] or '-'}"
        nxt = e["nextExecutionUnit"].replace("|", "/")
        out.append(f"| {i} | {e['researchId']} | {e['region']} | {e['track']} | {e['evidenceClass']} | "
                   f"{e['progressStatus']} | {gate} | {e['priority']['tier']} | {score} | "
                   f"{'예' if e['ownerApprovalRequired'] else '아니오'} | {nxt} |")
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    entries = load_all()
    here = Path(__file__).resolve().parent
    summary = {"entries": len(entries),
               "byClass": {c: sum(1 for e in entries if e["evidenceClass"] == c) for c in sorted(VOCAB["evidenceClass"])},
               "byStatus": {c: sum(1 for e in entries if e["progressStatus"] == c) for c in sorted(VOCAB["progressStatus"])}}
    if args.write:
        (here / "REGISTER.md").write_text(render_markdown(entries))
        (here / "register.json").write_text(json.dumps({"summary": summary, "entries": prioritize(entries)},
                                                       ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
