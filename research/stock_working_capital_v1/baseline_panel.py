"""Outcome-free controls for the proposed WC comparison, not new alpha.

Reuse the original annual-pair reader. Sales growth and focal levels separate
an unchanged balance divided by growing sales from a shrinking balance. The
algebra below is an attribution convention, not evidence of cash collection.
No age policy, source admission, hypothesis or registered study is changed.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import json
import math
from pathlib import Path

from . import features as F
from . import pit_admission as A
from . import pit_filing_evidence as E
from . import pit_join as J


def pair_controls(current, previous, as_of):
    pair = F.annual_pair(current, previous, as_of)
    out = {"asOf": as_of, "ticker": pair["ticker"], "filingDigests": pair["filingDigests"],
           "status": "RAW_PAIR_CONTROL_DIAGNOSTIC_NOT_SOURCE_ADMITTED", "controls": {}}
    for signal, field in zip(F.SIGNALS, ("receivables", "inventory")):
        reasons = list(pair["signals"][signal]["reasons"])
        values = None
        if not reasons:
            now_sales, _ = F.amount(current, "sales")
            old_sales, _ = F.amount(previous, "sales")
            now, _ = F.amount(current, field)
            old, _ = F.amount(previous, field)
            # Exact Decimal identity before conversion. This path changes the
            # numerator first at PRIOR sales, then changes its denominator.
            numerator = (old - now) / old_sales
            denominator = now / old_sales - now / now_sales
            values = {"salesGrowth": float(now_sales / old_sales - 1),
                      "currentFocalIntensity": float(now / now_sales),
                      "priorFocalIntensity": float(old / old_sales),
                      "numeratorTermAtPriorSales": float(numerator),
                      "denominatorTermAtCurrentBalance": float(denominator),
                      "rawIntensityChange": pair["signals"][signal]["value"]}
            if not all(math.isfinite(v) for v in values.values()):
                values = None
                reasons.append("NONFINITE_CONTROL")
        out["controls"][signal] = {"values": values, "reasons": reasons}
    return out


def build_controls(cohorts, rows, filings):
    """One diagnostic per intended member; do not complete-case the panel.

    Admission is always false here. Raw pair readability does not prove original
    facts, a fiscal-age choice, legal rights, or an executable shareholder path.
    """
    expected, by_date = set(), {}
    for cohort in cohorts:
        stamp = cohort["signal"]
        if stamp in by_date or cohort["intendedSha256"] != F.digest({
                k: v for k, v in cohort.items() if k != "intendedSha256"}):
            raise ValueError("INVALID_OR_DUPLICATE_COHORT")
        by_date[stamp] = cohort
        for member in cohort["members"]:
            key = stamp, member["ticker"]
            if key in expected:
                raise ValueError("DUPLICATE_INTENDED_MEMBER")
            expected.add(key)
    seen, by_ticker, result = set(), defaultdict(list), []
    for filing in filings:
        by_ticker[filing["ticker"]].append(filing)
    for row in rows:
        key = row["signal"], row["ticker"]
        if key in seen or key not in expected:
            raise ValueError("DUPLICATE_OR_EXTRA_MEASUREMENT_ROW")
        seen.add(key)
        if row["intendedSha256"] != by_date[key[0]]["intendedSha256"]:
            raise ValueError("MEASUREMENT_COHORT_BINDING_MISMATCH")
        current, prior, reasons = A.choose_pair(by_ticker[key[1]], key[0])
        selected = [r.get("receiptNos") if r else None for r in (prior, current)]
        if selected != row["filingReceipts"]:
            raise ValueError("CONTROL_PAIR_DIFFERS_FROM_MEASUREMENT")
        controls = (pair_controls(current, prior, key[0])["controls"] if not reasons else
                    {s: {"values": None, "reasons": reasons} for s in F.SIGNALS})
        result.append({"signal": key[0], "ticker": key[1], "intendedSha256": row["intendedSha256"],
                       "filingReceipts": selected, "controls": controls, "sourceAdmitted": False})
    if seen != expected or not expected:
        raise ValueError("MISSING_OR_EMPTY_INTENDED_POPULATION")
    counts = {}
    for signal in F.SIGNALS:
        readable_rows = [r for r in result if r["controls"][signal]["values"] is not None]
        readable = [r["controls"][signal]["values"] for r in readable_rows]
        positive_rows = [r for r in readable_rows if r["controls"][signal]["values"]["rawIntensityChange"] > 0
                         and r["controls"][signal]["values"]["numeratorTermAtPriorSales"] <= 0]
        def pair_key(row):
            return row["ticker"], F.digest(row["filingReceipts"])
        counts[signal] = {"denominator": len(result), "rawControlPairsReadable": len(readable),
                         "sourceAdmittedPairs": 0,
                         "distinctRawAnnualPairs": len({pair_key(r) for r in readable_rows}),
                         "positiveIntensityChangesWithNoNumeratorImprovement": len(positive_rows),
                         "distinctPositiveWithNoNumeratorImprovementPairs": len({pair_key(r) for r in positive_rows}),
                         "missingReasonsNonexclusive": dict(Counter(
                             reason for r in result for reason in r["controls"][signal]["reasons"]))}
    return {"schema": "STOCK_WC_SAME_PAIR_CONTROLS_V1", "status": "INPUT_DIAGNOSTICS_ONLY",
            "signals": counts, "memberDates": len(result), "panelSha256": F.digest(result),
            "attributionConvention": "NUMERATOR_FIRST_AT_PRIOR_SALES_THEN_DENOMINATOR_AT_CURRENT_BALANCE",
            "samplingNote": "Weekly member-date repeats are not independent annual evidence. Source-only diagnostics, no return or forecast evaluation.",
            "sourceAdmitted": False, "historicalOutcomesRead": 0, "modelFits": 0}, result


def inspect_controls(measurement, output):
    measurement, output = Path(measurement), Path(output)
    if output.exists():
        raise ValueError("OUTPUT_MUST_BE_NEW")
    J.verify_measurement(measurement)
    cohorts, rows = ([json.loads(line) for line in gzip.decompress((measurement / name).read_bytes()).splitlines()]
                     for name in ("cohorts.jsonl.gz", "rows.jsonl.gz"))
    source = J.PinnedInputs(J.ROOT)
    filings = [r for year in range(2015, 2025)
               for r in source.rows(f"ledger/fundamentals/kr-raw/raw-{year}.jsonl.gz")
               if r.get("reportCode") == "11011"]
    report, panel = build_controls(cohorts, rows, filings)
    report["sourceReceipts"] = source.receipts
    report["measurementSha256"] = {
        name: E.sha((measurement / name).read_bytes())
        for name in ("coverage.json", "cohorts.jsonl.gz", "rows.jsonl.gz")}
    output.mkdir(parents=True, exist_ok=False)
    raw = gzip.compress(J.canonical_lines(panel), mtime=0)
    (output / "controls.jsonl.gz").write_bytes(raw)
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--measurement", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    print(json.dumps(inspect_controls(args.measurement, args.output), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
