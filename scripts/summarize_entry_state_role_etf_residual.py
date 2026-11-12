"""Read-only summary of an entry-state-role-etf-residual-v1 run: summary.csv, vs-ETF paired table and REPORT.md.

    python scripts/summarize_entry_state_role_etf_residual.py RUN_DIR OUT_DIR

Reads only RUN_DIR/result.json and RUN_DIR/decisions.jsonl.gz (or .jsonl). It values nothing and changes no number in
result.json. The strategy-minus-ETF paired intervals are NOT in the frozen spec: they were added after the run was read and
are labelled POST_RESULT_DESCRIPTIVE; they use the same paired statistic and bootstrap settings as the frozen contrast.
"""
from __future__ import annotations

import csv
import gzip
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import entry_state_role_etf_residual as S      # noqa: E402

METRIC_KEYS = ("cagrPct", "etfCagrPct", "annualizedExcessVsEtfPp", "annualizedVolPct", "etfAnnualizedVolPct",
               "trackingErrorPct", "informationRatio", "mddPct", "etfMddPct", "dailyCvar95Pct",
               "annualOneWayTurnoverX", "costDragPctOfNavTotal", "averageStockNames", "averageResidualPct",
               "namesAddedPerRebalance", "namesRetainedPerRebalance", "incumbentRetentionPct", "blocks", "first", "last")


def _decisions(run: Path) -> dict[str, list[dict]]:
    path = run / "decisions.jsonl.gz"
    opener = gzip.open if path.exists() else open
    path = path if path.exists() else run / "decisions.jsonl"
    out: dict[str, list[dict]] = {}
    with opener(path, "rt") as stream:
        for line in stream:
            row = json.loads(line)
            if "navStart" in row:
                out.setdefault(row["strategyId"], []).append(row)
    return out


def _as_path(blocks):
    return {"status": "COMPLETE", "blocks": blocks}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    run, out = Path(argv[0]), Path(argv[1])
    result = json.loads((run / "result.json").read_text())
    decisions = _decisions(run)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for region, reg in result["regions"].items():
        etf_id = f"{region}:ETF_ONLY"
        etf_blocks = decisions[etf_id]
        for n, scenario in reg["scenarios"].items():
            if n == "N0":
                continue
            for residual in S.RESIDUALS:
                paired = scenario[residual]["pairedAtWeightMinusInRank"]
                for rung in S.RUNGS:
                    sid = f"{region}:{rung}:{n}:{residual}"
                    cell = scenario[residual][rung]
                    vs_etf = S.paired_difference(_as_path(decisions[sid]), _as_path(etf_blocks))
                    row = {"region": region, "strategyId": sid, "nameCountScenario": int(n[1:]), "residual": residual,
                           "rung": rung, "primary": int(n[1:]) == S.PRIMARY_NAME_COUNT and residual == "ETF",
                           **{k: cell["metrics"].get(k) for k in METRIC_KEYS}}
                    for h in S.HORIZONS:
                        hw = cell["horizons"][h]
                        row[f"{h}MeanExcessPct"] = hw.get("meanExcessPct")
                        row[f"{h}HitRatePct"] = hw.get("hitRatePct")
                        row[f"{h}MaturedAnchors"] = hw.get("maturedAnchors")
                        row[f"{h}PendingAnchors"] = hw.get("pendingAnchorsNotMatured")
                        row[f"{h}NonOverlappingWorstPct"] = hw.get("nonOverlappingWorstExcessPct")
                    row["vsEtfPairedPp_POST_RESULT_DESCRIPTIVE"] = vs_etf["pointEstimatePp"]
                    row["vsEtfCi95LowPp"], row["vsEtfCi95HighPp"] = vs_etf["ci95Pp"]
                    row["atWeightMinusInRankPp"] = paired["pointEstimatePp"]
                    row["atWeightMinusInRankCi95Pp"] = json.dumps(paired["ci95Pp"])
                    rows.append(row)
    with (out / "summary.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    def cell(region, n, residual, rung):
        return next(r for r in rows if r["strategyId"] == f"{region}:{rung}:N{n}:{residual}")

    lines = [f"# {S.STUDY_ID} — result", "",
             f"Evidence class **{S.EVIDENCE_CLASS}**. Outcome-exposed replay-v16 history, not out of sample; nothing here "
             "promotes a selector or changes production.", "",
             f"- spec `{result['source']['specSha256']}` (frozen in commit before valuation), code commit "
             f"`{result['source']['codeCommit']}`, input `{result['source']['inputSha256']}`, "
             f"signal-history `{result['source']['sourceCommit']}`",
             f"- {result['calendar']['maturedBlocks']} matured 21-session blocks {result['calendar']['first']} .. "
             f"{result['calendar']['lastEnd']}; {result['calendar']['unmaturedBlocksPending']} block pending (not zero)",
             "- every path started 100% in its regional ETF, residual = ETF, same budget for both rungs, dated stock/ETF "
             "leg costs charged once; KR in KRW vs 069500.KS, US in USD vs SPY; QQQ separate", ""]
    for region, reg in result["regions"].items():
        e = reg["etfOnly"]
        lines += [f"## {region} — ETF {reg['etf']} ({reg['currency']}): CAGR {e['cagrPct']:.3f}%, vol "
                  f"{e['annualizedVolPct']:.2f}%, MDD {e['mddPct']:.2f}%", ""]
        if reg.get("separateComparison"):
            q = reg["separateComparison"]["metrics"]
            lines += [f"Separate comparison {reg['separateComparison']['ticker']}: CAGR {q['cagrPct']:.3f}%, "
                      f"{q['annualizedExcessVsEtfPp']:+.3f}pp/yr vs SPY, MDD {q['mddPct']:.2f}%", ""]
        lines += ["| N | residual | rung | CAGR | vs ETF pp/yr [95% CI, descriptive] | vol | MDD | TE | turnover x/yr | "
                  "names | residual % | H126 mean / hit | H252 mean |", "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for n in [k for k in S.SCENARIO_NAME_COUNTS if k]:
            for residual in S.RESIDUALS:
                for rung in S.RUNGS:
                    r = cell(region, n, residual, rung)
                    lines.append(
                        f"| {n}{' (primary)' if r['primary'] else ''} | {residual} | {rung} | {r['cagrPct']:.2f}% | "
                        f"{r['vsEtfPairedPp_POST_RESULT_DESCRIPTIVE']:+.2f} [{r['vsEtfCi95LowPp']:+.2f}, "
                        f"{r['vsEtfCi95HighPp']:+.2f}] | {r['annualizedVolPct']:.2f}% | {r['mddPct']:.2f}% | "
                        f"{r['trackingErrorPct']:.2f} | {r['annualOneWayTurnoverX']:.2f} | {r['averageStockNames']:.2f} | "
                        f"{r['averageResidualPct']:.1f} | {r['H126MeanExcessPct']:+.2f}% / {r['H126HitRatePct']:.0f}% | "
                        f"{r['H252MeanExcessPct']:+.2f}% |")
        lines += ["", "Frozen contrast ENTRY_AT_WEIGHT minus ENTRY_IN_RANK (annualized log-growth difference incl. cost, "
                  "circular block bootstrap, 6 blocks, 2000 draws):", ""]
        for n in [k for k in S.SCENARIO_NAME_COUNTS if k]:
            for residual in S.RESIDUALS:
                p = reg["scenarios"][f"N{n}"][residual]["pairedAtWeightMinusInRank"]
                lines.append(f"- N{n} {residual}: {p['pointEstimatePp']:+.3f}pp [{p['ci95Pp'][0]:+.3f}, "
                             f"{p['ci95Pp'][1]:+.3f}] {p['direction']}")
        lines.append("")
    lines += ["## Reading", ""]
    for region, reg in result["regions"].items():
        p = reg["scenarios"][f"N{S.PRIMARY_NAME_COUNT}"]["ETF"]["pairedAtWeightMinusInRank"]
        lines.append(f"- {region} primary contrast (N={S.PRIMARY_NAME_COUNT}, ETF residual, legacy target not an "
                     f"optimum): ENTRY_AT_WEIGHT minus ENTRY_IN_RANK {p['pointEstimatePp']:+.3f}pp/yr, 95% CI "
                     f"[{p['ci95Pp'][0]:+.3f}, {p['ci95Pp'][1]:+.3f}], {p['direction']}.")
    lines += [
              "- A point estimate of opposite sign in the two regions, both intervals containing zero, is not evidence "
              "that either role is better; it is reported, not resolved.",
              "- No N, window or region is chosen from these numbers. The N grid is a fixed scenario set.",
              "- The ETF-minus-cash residual rows show how much of a cash-residual comparison is the residual itself; "
              "the sealed +1.385pp (cash residual, matched benchmark) is not an estimate for an ETF-residual strategy.",
              "- Vs-ETF intervals are POST_RESULT_DESCRIPTIVE (not in the frozen spec) and uncorrected for multiplicity.",
              ""]
    (out / "REPORT.md").write_text("\n".join(lines) + "\n")
    print(f"wrote {out / 'summary.csv'} ({len(rows)} rows) and REPORT.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
