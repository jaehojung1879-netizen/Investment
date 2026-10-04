#!/usr/bin/env python3
"""Write the outcome-free readiness record and its human-readable source report from the committed snapshot. Reads observation dates and metadata only."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import kr_market_risk_anatomy_execution as E  # noqa: E402

JSON_PATH = ROOT / E.READINESS_PATH
MD_PATH = ROOT / "docs/kr-market-risk-anatomy-v1-source-readiness.md"


def pct(v):
    return "n/a" if v is None else f"{v * 100:.2f}%"


def render(r):
    out = ["# kr-market-risk-anatomy-v1 — source inventory and readiness (outcome-free)", ""]
    out += [f"**Decision: `{r['decision']}`.** Scientific label: `{r['scientificStatus']}`. Computed from observation DATES and metadata only: no price, rate, return, drawdown, "
            "episode or future label was parsed or computed (counters all zero).", "",
            f"Blockers: {', '.join('`' + b + '`' for b in r['blockers']) or 'none'}. 2008 covered by a selected primary reference: **{r['covers2008']}**. Snapshot acquired on {r['acquiredOn']}.", "",
            "## Primary reference candidates (frozen rule: first KOSPI 200 route that passes every test; the composite only if none does)", "",
            "| candidate | family | first | last | stale days | invalid-row share | 2007-2009 coverage | 2019H2-2020 coverage | longest missing run | eligible | reasons |",
            "|---|---|---|---|---:|---:|---:|---:|---:|---|---|"]
    ev = r["primaryReference"]["evaluated"]
    for sid, d in r["referenceDiagnostics"].items():
        if not d["measured"]:
            out.append(f"| {sid} | - | - | - | - | - | - | - | - | no | {d['reason']} |")
            continue
        e = ev.get(sid, {"eligible": False, "reasons": ["ROBUSTNESS_REFERENCE_ONLY_NEVER_PRIMARY"]})
        out.append(f"| {sid} | {d['family']} | {d['firstDate']} | {d['lastDate']} | {d['staleDaysAtAcquisition']} (limit {d['freshnessLimitDays']}) | {d['droppedRowShare']:.4f} (limit {d['droppedRowShareLimit']}) | "
                   f"{pct(d['sessionCoverage']['GFC_2007_2009'])} | {pct(d['sessionCoverage']['COVID_2019H2_2020'])} | {d['longestMissingRunFrom2006']} | {'yes' if e['eligible'] else 'no'} | {'; '.join(e['reasons']) or '-'} |")
    out += ["", "No candidate was selected, nothing was spliced, nothing was substituted and no frozen limit was changed after the metadata was seen.", "",
            "## Source inventory (acquired snapshot)", "", "| source | status | first | last | valid rows | dropped | identity as recorded | identity by registered function | vintage class |", "|---|---|---|---|---:|---:|---|---|---|"]
    for sid, d in sorted(r["sourceInventory"].items()):
        out.append(f"| {sid} | {d['status']} | {d['firstDate']} | {d['lastDate']} | {d['validRows']} | {d['droppedRows']} | {d['identityOkAsRecorded']} | {d['identityOkByRegisteredFunction']} | {d['vintageClass']} |")
    out += ["", "## Family coverage in the core windows (known, non-stale observations on the cadence grid; dates only)", "", "| family / window | feature | coverage |", "|---|---|---:|"]
    for table, feats in sorted(r["coreCoverageTables"].items()):
        for feat, cov in sorted(feats.items()):
            out.append(f"| {table} | {feat} | {pct(cov)} |")
    if not r["coreCoverageTables"]:
        out.append("| (not computed: the gates stop at the unselected primary reference) | - | - |")
    out += ["", "## Role sources", "", f"VIX -> `{r['roleSources']['VIX']}`; USD/KRW -> `{r['roleSources']['USDKRW']}` (primary routes pass the weekly known-coverage gate in 2007-2009; secondaries are never spliced).", "",
            "## Excluded: revised history or not built", "", "| input | class | reason |", "|---|---|---|"]
    for sid, d in sorted(r["excludedRevisedOrUnbuiltInputs"].items()):
        out.append(f"| {sid} | {d['vintageClass']} | {d['reason']} |")
    t = r["extendedTier"]
    out += ["", "## EXTENDED_KR_INTERNALS (not part of the decision)", "",
            f"PIT Top120 signal dates: {t['pitSignalDates']} ({t['firstPitSignalDate']} to {t['lastPitSignalDate']}); raw-input artifact {t['rawInputArtifact']['artifactName']} (id {t['rawInputArtifact']['artifactId']}). "
            "Status: structurally ready; value coverage is measured at execution; an internals statistic is missing whenever any PIT member lacks its input.", ""]
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    r = E.readiness_audit(ROOT)
    JSON_PATH.write_text(json.dumps(r, sort_keys=True, indent=2, default=str) + "\n")
    MD_PATH.write_text(render(r), encoding="utf-8")
    print(r["decision"])
