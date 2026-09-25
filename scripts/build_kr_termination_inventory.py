"""Build the input-only inventory for the 22 KR terminated securities.

    python scripts/build_kr_termination_inventory.py \
        --input-root <checkout of signal-history 4ea107e with ledger/universe/kr> \
        --survivorship-audit docs/results/alpha-opportunity-model-v3-survivorship-audit.json \
        --output docs/results/kr-termination-inventory.json

Reads the 22-security list FROM the sealed v3 survivorship audit's own
`krTerminations` — never hardcoded, per this repository's own identity
discipline (`alpha-opportunity-model-v3-identity.py`'s "no guess becomes
normalized truth"). Computes each security's first/last KR-universe
membership date from the same sealed KRX snapshot shards the v3 audit reads.

No DART identity, terminal-action, or dividend-lineage evidence is supplied:
this sandbox has no `DART_API_KEY` and cannot reach `opendart.fss.or.kr`'s
`corpCode.xml` (see the accompanying doc). Every row this script writes is
therefore `dartIdentityStatus: DART_DIRECTORY_NOT_AVAILABLE` and
`terminationType: TERMINATION_TYPE_UNRESOLVED` — an honest, input-only
snapshot the live collection workflow extends, never replaces with a second
code path (`pipeline.kr_termination_inventory.build_inventory` is the same
function either way).

Computes no return, no label, no Alpha, no IC. Output is byte-stable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import historical_store as HS  # noqa: E402
from pipeline import kr_termination_inventory as INV  # noqa: E402

KR_TOP = 120  # same constant `audit_alpha_opportunity_v3_survivorship.py` uses


def kr_snapshot_rows(ledger: Path) -> list[dict]:
    rows = []
    for path in sorted((ledger / "universe/kr").glob("krx-universe-*.jsonl.gz")):
        rows.extend(HS.read_jsonl(path))
    return rows


def membership_windows(rows: list[dict], codes: set[str]) -> dict[str, dict]:
    """First/last KRX-universe snapshot date each of `codes` was ranked
    inside the top `KR_TOP` by market cap — the same top-N membership rule
    `alpha_opportunity_v3_survivorship`'s KR audit already applies, computed
    directly from the raw snapshot rows rather than re-deriving a second
    ranking rule.

    ``rows`` must be the FULL day's cross-section (every ticker, not just
    ``codes``): the rank cutoff is meaningless applied to a pre-filtered
    subset, since a code's rank depends on every OTHER name that day too.
    """
    by_date: dict[str, list[dict]] = {}
    for row in rows:
        date = str(row.get("date") or "")
        if date:
            by_date.setdefault(date, []).append(row)
    dates_by_code: dict[str, list[str]] = {code: [] for code in codes}
    for date, day_rows in by_date.items():
        # Filtered by rank VALUE, not sliced by position: a positional slice
        # only equals "rank <= KR_TOP" when the day's rows already cover
        # ranks 1..N with no gaps, which real KRX snapshots do but a partial
        # fixture need not.
        ranked = [r for r in day_rows
                 if r.get("rank") is not None and int(r["rank"]) <= KR_TOP]
        for row in ranked:
            code = str(row.get("ticker") or "").removesuffix(".KS")
            if code in dates_by_code:
                dates_by_code[code].append(date)
    return {code: {"first": min(dates), "last": max(dates)} if dates else {"first": None, "last": None}
           for code, dates in dates_by_code.items()}


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(input_root: Path, survivorship_audit: Path) -> dict:
    ledger = input_root / "ledger"
    audit = json.loads(survivorship_audit.read_text(encoding="utf-8"))
    kr_terminations = audit.get("krTerminations") or []
    if not kr_terminations:
        raise ValueError("survivorship audit has no krTerminations — nothing to build")
    codes = {row["code"].removesuffix(".KS") for row in kr_terminations}

    rows = kr_snapshot_rows(ledger)
    windows_by_bare_code = membership_windows(rows, codes)
    windows = {f"{code}.KS": window for code, window in windows_by_bare_code.items()}

    inventory = INV.build_inventory(kr_terminations=kr_terminations,
                                    kr_membership_windows=windows)
    return {
        "studyId": "kr-terminated-security-total-return-foundation-v1",
        "phase": "INPUT_ONLY_TERMINATION_INVENTORY",
        "historicalOutcomesComputed": False, "returnsComputed": False,
        "labelsConstructed": False, "modelsTrained": False,
        "inputs": {
            "signalHistoryCommit": audit["inputs"]["signalHistoryCommit"],
            "survivorshipAuditPath": str(survivorship_audit),
            "survivorshipAuditSha256": sha256_of(survivorship_audit),
            "krTerminationsCount": len(kr_terminations),
        },
        "securities": inventory,
        "summary": INV.summary(inventory),
        "foundationStatus": INV.foundation_status(inventory),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", required=True, type=Path)
    parser.add_argument(
        "--survivorship-audit", type=Path,
        default=ROOT / "docs/results/alpha-opportunity-model-v3-survivorship-audit.json")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    report = run(args.input_root, args.survivorship_audit)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    sidecar = args.output.with_suffix(args.output.suffix + ".sha256")
    sidecar.write_text(sha256_of(args.output) + "\n")
    print(json.dumps({"foundationStatus": report["foundationStatus"],
                      "securities": len(report["securities"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
