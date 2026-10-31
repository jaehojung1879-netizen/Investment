"""Does each T execution report agree with the frozen listed-share test? Source only; no price, return or label.

The frozen `kr22_source_recovery.execution_evidence` confirmed an execution only when the successor's listed shares
rose by the documented new-share count (EXACT / ADJUSTED). Proposal T (`kr22-terminal-execution-evidence.json`)
replaced that with "the acquirer's own issuance report states the effective date and no cash". This module applies the
FROZEN test to the same six rows, with its own helpers unchanged, so T can be read in the frozen vocabulary.

For a stock-for-stock exchange, successor listed-share increase / ratio is the number of old shares exchanged. It equals
the old security's listed shares when every share is exchanged against NEW successor shares. It is lower when the
acquirer already owned old shares, the old company held treasury shares, or the acquirer delivered its own treasury
shares instead of issuing (listed shares then do not move). Those are structural, per-share terms are unchanged, so a gap
is "documented, not count-reconciled", never "contradicted".
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import inputs as IN
from . import kr22_source_recovery as SR

HERE = Path(__file__).resolve().parent
REPORT = HERE / "kr22-terminal-execution-reconciliation.json"
TOLERANCE = SR.ADJUSTMENT_TOLERANCE
# Stated by the acquirer's report itself (receipt 20200129000273): total delivered 22,114,968 = 13,882,062 treasury + 8,232,906 new.
DOCUMENTED_NEW_SHARES = {"079440.KS": 8232906}


def reconcile(row, snaps):
    old, succ, eff = row["oldSecurity"], row["successorSecurity"], row["effectiveDate"]
    ratio = float(row["reviewedRatio"]["commonShareRatio"])
    _, old_shares, _, _ = SR.share_jump(snaps, old, eff)
    before_date, before, after_date, after = SR.share_jump(snaps, succ, eff)
    jump = None if after is None else after - before
    implied = None if not jump or not ratio else jump / ratio
    documented = DOCUMENTED_NEW_SHARES.get(old)
    if documented is not None and jump is not None and abs(jump - documented) <= TOLERANCE * documented:
        status, basis = SR.EXACT if jump == documented else SR.ADJUSTED, "DOCUMENTED_NEW_SHARES_EQUAL_OBSERVED_LISTED_SHARE_INCREASE"
    elif implied and old_shares and abs(implied - old_shares) <= TOLERANCE * old_shares:
        status, basis = SR.EXACT if round(implied) == round(old_shares) else SR.ADJUSTED, "IMPLIED_OLD_SHARES_EQUAL_OLD_LISTED_SHARES"
    elif jump == 0:
        status, basis = "DOCUMENTED_NOT_COUNT_RECONCILED", "NO_LISTED_SHARE_CHANGE_TREASURY_DELIVERY_STATED"
    else:
        status, basis = "DOCUMENTED_NOT_COUNT_RECONCILED", "GAP_NEEDS_ACQUIRER_STAKE_OR_TREASURY_DATA"
    return {"oldSecurity": old, "successorSecurity": succ, "effectiveDate": eff, "commonShareRatio": ratio,
            "oldListedSharesBefore": old_shares, "successorListedSharesBefore": before, "successorListedSharesAfter": after,
            "snapshotBefore": before_date, "snapshotAfter": after_date, "observedIncrease": jump,
            "impliedOldSharesExchanged": implied,
            "impliedVsOldListed": None if not (implied and old_shares) else implied / old_shares - 1,
            "documentedNewShares": documented, "status": status, "basis": basis}


def build(root=IN.ROOT):
    snaps = IN.load_universe(root)
    rows = [reconcile(r, snaps) for r in json.loads((HERE / "kr22-terminal-execution-evidence.json").read_text())["rows"]]
    exact = [r["oldSecurity"] for r in rows if r["status"] in (SR.EXACT, SR.ADJUSTED)]
    return {"contract": "KR22_TERMINAL_EXECUTION_RECONCILIATION_V1", "evidenceClass": "SOURCE_ONLY_NOT_ADOPTED",
            "historicalOutcomesRead": 0, "pricesRead": 0, "tolerance": TOLERANCE,
            "summary": {"rows": len(rows), "countReconciled": exact,
                        "documentedNotCountReconciled": [r["oldSecurity"] for r in rows if r["oldSecurity"] not in exact]},
            "rows": rows}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--output", default=str(REPORT))
    args = ap.parse_args(argv)
    out = build()
    Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    print(json.dumps(out["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
