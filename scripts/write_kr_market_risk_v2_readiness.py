#!/usr/bin/env python3
"""Write the outcome-free v2 readiness record and its human-readable source report from the committed v1-retained snapshot. Reads observation dates and metadata only."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import kr_market_risk_anatomy_v2_execution as E  # noqa: E402
from pipeline import kr_market_risk_sources as S  # noqa: E402
from pipeline import kr_market_risk_sources_v2 as R  # noqa: E402

JSON_PATH = ROOT / E.READINESS_PATH
MD_PATH = ROOT / "docs/kr-market-risk-anatomy-v2-source-readiness.md"


def pct(v):
    return "n/a" if v is None else f"{v * 100:.2f}%"


def render(r):
    out = ["# kr-market-risk-anatomy-v2 — source readiness (outcome-free)", ""]
    out += [f"**Decision: `{r['decision']}`.** Scientific label: `{r['scientificStatus']}`. Computed from observation DATES, the XKRX session calendar and metadata only: no price, "
            "rate, return, drawdown, episode or future label was parsed or computed (counters all zero). No new external acquisition occurred: the inputs are the exact "
            "immutable bytes retained by `kr-market-risk-anatomy-v1`, which stays `DATA_BLOCKED_BEFORE_MARKET_RISK_ANATOMY` and unchanged.", "",
            f"Blockers: {', '.join('`' + b + '`' for b in r['blockers']) or 'none'}. Snapshot acquired on {r['acquiredOn']}.", ""]
    ref = r["primaryReference"]
    if ref["primary"]:
        s = r["selectedReference"]
        q, i = s["quality"], s["identity"]
        out += [f"## Selected primary reference: `{ref['primary']}` ({ref['family']}, {ref['basis']})", "",
                f"- Identity: vendor `{i['vendor']}`, symbol `{i['symbol']}`, host `{i['host']}`, fetched {i['fetchedAtUtc']}; identity check by the registered function: {i['identityOkByRegisteredFunction']}.",
                "- Retained bytes (sha256): " + ", ".join(f"`{k}` `{v}`" for k, v in sorted(i["retainedFileSha256"].items())) + ".",
                f"- Vintage class: `{s['vintageClass']}` (unrevised market observation, approximate availability; never PIT_EXACT). Spliced: **{s['spliced']}**.",
                f"- First / last usable date: {s['firstUsableDate']} / {s['lastUsableDate']}. **Frozen analysis end: {s['analysisEnd']}** (the source's own last completed XKRX session; nothing forward-filled or synthesized).",
                f"- Session accounting over {q['windowStart']} to {q['windowEnd']}: expected XKRX sessions {q['expectedSessions']}, valid {q['validSessions']}, missing (no vendor row) {q['missingSessions']}, "
                f"invalid expected-session rows {q['invalidExpectedSessions']}, bad-session share {q['badSessionShare']:.6f} (limit {R.MAX_BAD_SESSION_SHARE}).",
                f"- Reported separately and NOT counted against the source: non-session vendor rows {q['nonSessionRows']}, surplus duplicate raw rows {q['duplicateRawRows']}, duplicate dates in the valid series {q['duplicateValidDates']}.",
                f"- Coverage: 2007-2009 {pct(s['sessionCoverage']['GFC_2007_2009'])}; 2019H2-2020 {pct(s['sessionCoverage']['COVID_2019H2_2020'])}; full range {pct(s['fullRangeCoverage'])}; longest missing run {s['longestMissingRun']}.",
                f"- Live operational freshness (INFORMATIONAL, a separate future deployment question, never a historical gate): stale {s['liveOperationalFreshness']['staleDays']} days against a "
                f"{s['liveOperationalFreshness']['limitDays']}-day live limit -> meets live freshness: {s['liveOperationalFreshness']['meetsLiveFreshness']}; live-ready: **False**.", ""]
    out += ["## Candidates (frozen v2 rule: first KOSPI 200 route that passes every test; the composite only if none does)", "",
            "| candidate | family | first | last | analysis end | expected sessions | missing | invalid | non-session rows | dup raw | bad share | 2007-09 | 2019H2-20 | eligible | v2 reasons | v1 reasons |",
            "|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|"]
    for sid, e in ref["evaluated"].items():
        m = e["metrics"]
        v1 = r["v1Comparison"].get(sid, {})
        if not m:
            out.append(f"| {sid} | - | - | - | - | - | - | - | - | - | - | - | - | no | {'; '.join(e['reasons'])} | {'; '.join(v1.get('v1Reasons', []))} |")
            continue
        q = m["quality"]
        out.append(f"| {sid} | {S.SOURCES[sid]['family']} | {m['firstDate']} | {m['lastDate']} | {m['analysisEnd']} | {q['expectedSessions']} | "
                   f"{q['missingSessions']} | {q['invalidExpectedSessions']} | {q['nonSessionRows']} | {q['duplicateRawRows']} | {q['badSessionShare']:.6f} | {pct(m['sessionCoverage']['GFC_2007_2009'])} | "
                   f"{pct(m['sessionCoverage']['COVID_2019H2_2020'])} | {'yes' if e['eligible'] else 'no'} | {'; '.join(e['reasons']) or '-'} | {'; '.join(v1.get('v1Reasons', [])) or '-'} |")
    out += ["", "No candidate was selected on outcomes, nothing was spliced, nothing was substituted, and no coverage, continuity or identity threshold was changed from v1.", "",
            "## Gates", "", "| gate | pass | detail |", "|---|---|---|"]
    for name, g in sorted(r["gates"].items()):
        out.append(f"| {name} | {g['pass']} | {', '.join(f'{k}={v}' for k, v in g.items() if k != 'pass')} |")
    out += ["", "## Family coverage in the core windows (known, non-stale observations on the cadence grid; dates only)", "", "| family / window | feature | coverage |", "|---|---|---:|"]
    for table, feats in sorted(r["coreCoverageTables"].items()):
        for feat, cov in sorted(feats.items()):
            out.append(f"| {table} | {feat} | {pct(cov)} |")
    out += ["", "## Role sources", "", f"VIX -> `{r['roleSources']['VIX']}`; USD/KRW -> `{r['roleSources']['USDKRW']}` (secondaries are never spliced).", "",
            "## Excluded: revised history or not built", "", "| input | class | reason |", "|---|---|---|"]
    for sid, d in sorted(r["excludedRevisedOrUnbuiltInputs"].items()):
        out.append(f"| {sid} | {d['vintageClass']} | {d['reason']} |")
    t = r["extendedTier"]
    out += ["", "## EXTENDED_KR_INTERNALS (not part of the decision)", "",
            f"PIT Top120 signal dates: {t['pitSignalDates']} ({t['firstPitSignalDate']} to {t['lastPitSignalDate']}); raw-input artifact {t['rawInputArtifact']['artifactName']} (id {t['rawInputArtifact']['artifactId']}).", ""]
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    r = E.readiness_audit(ROOT)
    JSON_PATH.write_text(json.dumps(r, sort_keys=True, indent=2, default=str) + "\n")
    MD_PATH.write_text(render(r), encoding="utf-8")
    print(r["decision"])
