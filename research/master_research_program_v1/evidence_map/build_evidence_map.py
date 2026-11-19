"""Master Research Evidence Map (KR/US x MARKET/INDUSTRY/STOCK/PORTFOLIO), deterministic.

Inputs (read-only): the outcome-blind catalogue `research/alpha_evidence_sprint_v2/evidence/research-tracks.json`
(each item's quoted verdict and path@commit), plus the curated rows below for studies that catalogue did not
cover and for this program's own prepared studies. The six evidence classes are the owner's taxonomy:

    VERIFIED_EVIDENCE      independent preregistered OOS or prospective, cost-net economic validation done
    EXPLORATORY_EVIDENCE   results exist on exposed history, not an independent confirmation
    EMPIRICAL_FAIL         did not pass its registered empirical criterion
    SOURCE_BLOCKED         data / rights / identity / shareholder-return basis / power not secured
    PREPARED_NOT_EXECUTED  preregistered or coded, real test not run
    PROSPECTIVE_PENDING    recording forward, no maturity yet

    python research/master_research_program_v1/evidence_map/build_evidence_map.py --check
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CATALOGUE = ROOT / "research/alpha_evidence_sprint_v2/evidence/research-tracks.json"
CLASSES = ("VERIFIED_EVIDENCE", "EXPLORATORY_EVIDENCE", "EMPIRICAL_FAIL", "SOURCE_BLOCKED",
           "PREPARED_NOT_EXECUTED", "PROSPECTIVE_PENDING")
REGIONS = ("KR", "US")
TRACKS = ("MARKET", "INDUSTRY", "STOCK", "PORTFOLIO")

# catalogue id prefix -> (regions, track, owner-taxonomy class). Re-classification of the catalogue's coarser
# PARTIAL class is explicit here so a reviewer can disagree with one row, not with a rule.
CATALOGUE_MAP = {
    "kr-market-risk-model-v1 (C1-KR": (("KR",), "MARKET", "EMPIRICAL_FAIL"),
    "kr-market-risk-model-v1 C2_PREEMPTIVE": (("KR",), "MARKET", "EMPIRICAL_FAIL"),
    "rp1-c1-us-exposure-ladder-replication-v1": (("US",), "MARKET", "EMPIRICAL_FAIL"),
    "C1c asymmetric exit": (("KR",), "MARKET", "PREPARED_NOT_EXECUTED"),
    "rp1-b-h1-state-v1": (("KR",), "MARKET", "PROSPECTIVE_PENDING"),
    "EXP-C-RECOVERY-01/02": (("KR",), "MARKET", "SOURCE_BLOCKED"),
    "industry-alpha-kr/us-next-v1": (("KR", "US"), "INDUSTRY", "PREPARED_NOT_EXECUTED"),
    "kr-industry-membership-foundation": (("KR",), "INDUSTRY", "SOURCE_BLOCKED"),
    "kr-industry-opportunity-anatomy-v1": (("KR",), "INDUSTRY", "EXPLORATORY_EVIDENCE"),
    "industry-ocfyield-conditional-v1": (("KR",), "INDUSTRY", "SOURCE_BLOCKED"),
    "M3 backlog": (("US",), "INDUSTRY", "EMPIRICAL_FAIL"),
    "industry-information-transfer-v1": (("KR",), "INDUSTRY", "EXPLORATORY_EVIDENCE"),
    "kr-alpha-atlas-phase-c-v1": (("KR",), "STOCK", "EMPIRICAL_FAIL"),
    "historical-alpha-discovery-v1": (("KR",), "STOCK", "EMPIRICAL_FAIL"),
    "c2_aggregate_evidence_v1": (("KR",), "PORTFOLIO", "EXPLORATORY_EVIDENCE"),
    "entry-state-role-etf-residual-v1 (PR": (("KR",), "STOCK", "EMPIRICAL_FAIL"),
    "alpha-mechanism-sprint-v1": (("KR",), "STOCK", "PREPARED_NOT_EXECUTED"),
    "kr-alpha-discovery-tournament-v1": (("KR",), "STOCK", "SOURCE_BLOCKED"),
    "kr-model-overlay-portfolio-v1": (("KR",), "STOCK", "EMPIRICAL_FAIL"),
    "alpha-opportunity-model-v5": (("KR",), "STOCK", "EMPIRICAL_FAIL"),
    "rp1-kr-a0-measurability-v1": (("KR",), "STOCK", "PREPARED_NOT_EXECUTED"),
    "WID historical execution recovery": (("US",), "STOCK", "SOURCE_BLOCKED"),
    "rp1-a0-measurability-v1": (("US",), "STOCK", "SOURCE_BLOCKED"),
    "regional-alpha-model-v1": (("KR", "US"), "STOCK", "EMPIRICAL_FAIL"),
    "entry-state-role-etf-residual-v1 US": (("US",), "STOCK", "EMPIRICAL_FAIL"),
    "rp1_d_composition_contract": (("KR", "US"), "PORTFOLIO", "PREPARED_NOT_EXECUTED"),
    "kr-integrated-alpha-portfolio-v1": (("KR",), "PORTFOLIO", "EMPIRICAL_FAIL"),
    "economic-path-readout-v1": (("KR",), "PORTFOLIO", "EXPLORATORY_EVIDENCE"),
    "portfolio-edge-forensics-v1": (("KR", "US"), "PORTFOLIO", "EXPLORATORY_EVIDENCE"),
    "market-industry-alpha-decomposition-v1": (("KR",), "PORTFOLIO", "SOURCE_BLOCKED"),
    "independent_audit_c2_marketc_v1": (("KR",), "PORTFOLIO", "EXPLORATORY_EVIDENCE"),
}

# rows not in the catalogue. Prospective counts were read 2026-11-04 from signal-history 0b10f54d (file listing and
# receipt dates only; no value read).
CURATED = [
    {"id": "kr-selection-challenger-v1 / v2-accounting (#277/#278)", "regions": ["KR"], "track": "STOCK",
     "class": "PROSPECTIVE_PENDING",
     "evidence": "signal-history@0b10f54d ledger/research-strategies/kr-selection-challenger-v1/receipts.jsonl and "
                 "-v2-accounting/receipts.jsonl: 1 receipt each, signalDate 2026-10-30; no matured outcome"},
    {"id": "current-champion-decisions-v1 (weekly CHAMPION record)", "regions": ["KR", "US"], "track": "PORTFOLIO",
     "class": "PROSPECTIVE_PENDING",
     "evidence": "signal-history@0b10f54d ledger/research-strategies/current-champion-decisions-v1/receipts.jsonl: "
                 "13 receipts, 10 as-of dates 2026-10-09..2026-10-30, regions KR/US"},
    {"id": "us-capital-allocation-alpha-v1", "regions": ["US"], "track": "STOCK", "class": "PREPARED_NOT_EXECUTED",
     "evidence": "docs/us-capital-allocation-alpha-v1.md@37f8cbf6: REGISTERED_PENDING_OWNER_APPROVAL; phase 2 "
                 "NEEDS_SOURCE_REPAIR"},
    {"id": "us-cash-profitability H63 (P3/P4)", "regions": ["US"], "track": "STOCK", "class": "PREPARED_NOT_EXECUTED",
     "evidence": "docs/us-cash-profitability-p4-execution-design-ko.md@37f8cbf6: scientific CONDITIONAL, execution "
                 "BLOCKED (owner approval + lock)"},
    {"id": "four-factor-signal-attribution-audit", "regions": ["KR", "US"], "track": "STOCK",
     "class": "EMPIRICAL_FAIL",
     "evidence": "AGENTS.md v2.21: none of four primary hypotheses clears raw significance; all D_UNSTABLE"},
    {"id": "fundamental-acceleration-discovery-v1", "regions": ["KR", "US"], "track": "STOCK",
     "class": "EMPIRICAL_FAIL", "evidence": "AGENTS.md v2.22: CASE D NO_DISCOVERY_EVIDENCE"},
    {"id": "entry-state shadow ledger (#306, open Draft)", "regions": ["KR", "US"], "track": "STOCK",
     "class": "PREPARED_NOT_EXECUTED", "evidence": "PR #306 head 49e35ace: hook not merged, no receipt on signal-history"},
    {"id": "c2-fixed-exposure-attribution-v1 (#316)", "regions": ["KR"], "track": "PORTFOLIO",
     "class": "PREPARED_NOT_EXECUTED",
     "evidence": "research/alpha_evidence_sprint_v2/c2-fixed-exposure-attribution-v1.json@86c5983f: owner approval "
                 "required; investable KRW cash SOURCE_BLOCKED"},
    {"id": "kr-insider-open-market-purchase-v1 (#316)", "regions": ["KR"], "track": "STOCK",
     "class": "PREPARED_NOT_EXECUTED",
     "evidence": "research/alpha_evidence_sprint_v2/kr-insider-open-market-purchase-v1.json@86c5983f; density gate "
                 "see research/master_research_program_v1/stock/"},
    {"id": "us-insider-form4 (#316 probe)", "regions": ["US"], "track": "STOCK", "class": "SOURCE_BLOCKED",
     "evidence": "research/alpha_evidence_sprint_v2/evidence/us-insider-probe.json@86c5983f: SEC 403 without a "
                 "declared contact; US panel survivorship (212 departed identities unpriced)"},
    {"id": "portfolio-d-p0-p5-comparison-v1 (this program)", "regions": ["KR", "US"], "track": "PORTFOLIO",
     "class": "PREPARED_NOT_EXECUTED",
     "evidence": "research/master_research_program_v1/portfolio/portfolio-d-p0-p5-comparison-v1.json"},
]


def build(catalogue: dict) -> dict:
    rows = []
    for lane in catalogue["lanes"]:
        for item in lane["items"]:
            match = [v for k, v in CATALOGUE_MAP.items() if item["id"].startswith(k)]
            if len(match) != 1:
                raise ValueError(f"UNMAPPED_OR_AMBIGUOUS_CATALOGUE_ITEM:{item['id']}")
            regions, track, cls = match[0]
            rows.append({"id": item["id"], "regions": list(regions), "track": track, "class": cls,
                         "catalogueClass": item["class"], "evidence": item["evidence"]})
    rows.extend(dict(r) for r in CURATED)
    for r in rows:
        if r["class"] not in CLASSES or r["track"] not in TRACKS or not set(r["regions"]) <= set(REGIONS):
            raise ValueError(f"BAD_ROW:{r['id']}")
    matrix = {reg: {tr: {c: [] for c in CLASSES} for tr in TRACKS} for reg in REGIONS}
    for r in rows:
        for reg in r["regions"]:
            matrix[reg][r["track"]][r["class"]].append(r["id"])
    counts = {c: sum(1 for r in rows if r["class"] == c) for c in CLASSES}
    return {"mapId": "master-research-evidence-map-v1", "asOf": "2026-11-04",
            "mainCommit": catalogue["mainCommit"], "classes": list(CLASSES), "rowCounts": counts,
            "verifiedEvidence": {"KR": 0, "US": 0}, "rows": rows, "matrix": matrix}


def render(m: dict) -> str:
    lines = ["# Master Research Evidence Map v1 (2026-11-04)", "",
             "Generated by `build_evidence_map.py`; edit the mapping there, not this file.", "",
             "| 지역 | 영역 | " + " | ".join(m["classes"]) + " |", "|---|---|" + "---:|" * len(m["classes"])]
    for reg in REGIONS:
        for tr in TRACKS:
            cells = [str(len(m["matrix"][reg][tr][c])) for c in m["classes"]]
            lines.append(f"| {reg} | {tr} | " + " | ".join(cells) + " |")
    lines += ["", f"**VERIFIED_EVIDENCE: KR {m['verifiedEvidence']['KR']}, US {m['verifiedEvidence']['US']}.**", "",
              "| 연구 | 지역 | 영역 | 분류 | 근거 |", "|---|---|---|---|---|"]
    for r in m["rows"]:
        ev = r["evidence"].replace("|", "/")
        lines.append(f"| {r['id']} | {'/'.join(r['regions'])} | {r['track']} | {r['class']} | {ev} |")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="fail if the committed outputs differ")
    args = ap.parse_args(argv)
    m = build(json.loads(CATALOGUE.read_text()))
    js = json.dumps(m, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    md = render(m)
    if args.check:
        same = (HERE / "evidence_map.json").read_text() == js and (HERE / "EVIDENCE_MAP.md").read_text() == md
        print("UP_TO_DATE" if same else "STALE")
        return 0 if same else 1
    (HERE / "evidence_map.json").write_text(js)
    (HERE / "EVIDENCE_MAP.md").write_text(md)
    print(json.dumps(m["rowCounts"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
