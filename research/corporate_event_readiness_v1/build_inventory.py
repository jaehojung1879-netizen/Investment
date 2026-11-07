"""Offline regeneration from selectively extracted, pinned Git source bytes.

python -m research.corporate_event_readiness_v1.build_inventory \
  --source-root /tmp/investment-lane-c --output /tmp/inventory.json

Source extraction (no DART API): git archive 75aab7bc... \
research/alpha_mechanism_sprint_v1/data/dart-list | tar -x -C SOURCE_ROOT
and git archive 4ea107ed... ledger/universe/kr/krx-universe-2013.jsonl.gz | tar -x -C SOURCE_ROOT.
No input source bytes are copied into this package.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

from .inventory import sample_inventory
from .universe import membership_inventory

ROOT = Path(__file__).resolve().parents[2]
LIST_REF = "75aab7bc7096b551543bc1582c1e7fd288e94e59"
UNIVERSE_REF = "4ea107ed0cde289f0a049a65ff13d2441a786710"
BASELINE_MAIN = "37f8cbf6b1c066f6b3c65235953648d17ebf2f69"
TOP120_SHA256 = "d7c464973ad029bf08886c4bdf2517d1b3ece04cce87bcc63706f1230ed53cd0"
TERMINATIONS_SHA256 = "b58ecb2c4500302c40784613318c8451beee663ece5ee76ada26873a4292f93f"
LIST_PATH = "research/alpha_mechanism_sprint_v1/data/dart-list"
CATEGORIES = {
    "BUYBACK_DECISION": "자기주식취득결정",
    "BUYBACK_TRUST_DECISION": "자기주식취득신탁계약체결결정",
    "SHARE_CANCELLATION_DECISION": "주식소각결정",
    "TREASURY_DISPOSAL_DECISION": "자기주식처분결정",
    "RIGHTS_OFFERING_DECISION": "유상증자결정",
    "CONVERTIBLE_BOND_DECISION": "전환사채권발행결정",
    "EXCHANGEABLE_BOND_DECISION": "교환사채권발행결정",
    "SUPPLY_CONTRACT": "단일판매ㆍ공급계약체결",
    "SUPPLY_CONTRACT_TERMINATION": "단일판매ㆍ공급계약해지",
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git_tree(ref: str, path: str) -> dict[str, str]:
    # Disable lazy network access: this CLI can never fetch or call an API.
    import os
    env = {**os.environ, "GIT_NO_LAZY_FETCH": "1"}
    raw = subprocess.check_output(["git", "ls-tree", "-r", ref, "--", path], cwd=ROOT, env=env)
    result = {}
    for line in raw.decode().splitlines():
        meta, name = line.split("\t", 1)
        result[name] = meta.split()[2]
    return result


def _verify(data: bytes, blob: str) -> None:
    header = f"blob {len(data)}\0".encode()
    if hashlib.sha1(header + data).hexdigest() != blob:
        raise ValueError("PINNED_GIT_BLOB_MISMATCH")


def build(source_root: Path) -> dict:
    tree = _git_tree(LIST_REF, LIST_PATH)
    paths = sorted(p for p in tree if p.endswith("-I.jsonl.gz"))
    if len(paths) != 254:
        raise ValueError("PINNED_254_ISSUER_LIST_SCOPE_REQUIRED")
    rows, receipts, list_hashes = [], [], []
    for rel in paths:
        data = (source_root / rel).read_bytes()
        _verify(data, tree[rel])
        list_hashes.append({"path": rel, "git_blob": tree[rel], "sha256": _sha(data)})
        for line in gzip.decompress(data).decode().splitlines():
            r = json.loads(line)
            if not "20130101" <= r["rcept_dt"] <= "20261031":
                continue
            name = r["report_nm"]
            hits = [k for k, term in CATEGORIES.items() if term in name]
            if not hits:
                continue
            day = r["rcept_dt"]
            row = {"issuer_id": r["corp_code"], "receipt_id": r["rcept_no"],
                   "received_date": f"{day[:4]}-{day[4:6]}-{day[6:]}",
                   "family": hits[0], "parse_status": "NOT_PARSED",
                   "relation_type": "CORRECTION" if "정정" in name else
                   "TERMINATION" if "해지" in name else "ORIGINAL"}
            rows.append(row)
            receipts.append((row, (r.get("stock_code") or "") + ".KS"))
    out = sample_inventory(rows)
    out["scope"] = {"from": "2013-01-01", "through": "2026-10-31",
                    "issuer_lists": 254, "list_type": "I_EXCHANGE_DISCLOSURES_ONLY",
                    "classification": "TITLE_SUBSTRING_READING_LIST_NOT_BODY_VERIFIED_EVENTS",
                    "B_major_matters_raw": "NOT_RETAINED_IN_PINNED_PACKET"}
    out["source_lists"] = {"commit": LIST_REF, "files": list_hashes}
    out["by_family_issuer"] = {family: dict(sorted(Counter(r["issuer_id"] for r in rows
                                              if r["family"] == family).items()))
                               for family in sorted({r["family"] for r in rows})}
    out["by_family_year"] = {family: dict(sorted(Counter(r["received_date"][:4] for r in rows
                                            if r["family"] == family).items()))
                             for family in sorted({r["family"] for r in rows})}
    top_path = ROOT / "data/kr-industry-membership-foundation-v1/top120-inputs.json"
    top_bytes = top_path.read_bytes()
    if _sha(top_bytes) != TOP120_SHA256:
        raise ValueError("PINNED_TOP120_SOURCE_MISMATCH")
    top = json.loads(top_bytes)
    snapshots = {r["date"]: r["members"] for r in top["snapshots"]}
    out["top120"] = {**membership_inventory(snapshots),
                     "source_path": str(top_path.relative_to(ROOT)), "sha256": _sha(top_bytes),
                     "source_commit": top["sourceCommit"], "rule": top["universeRule"],
                     "packet_source_commit": BASELINE_MAIN}
    match_counts, unmatched_counts = Counter(), Counter()
    for row, ticker in receipts:
        prior = [d for d in snapshots if d < row["received_date"]]
        if not prior:
            unmatched_counts["NO_STRICTLY_PRIOR_SNAPSHOT"] += 1
        elif ticker in snapshots[max(prior)]:
            match_counts[row["family"]] += 1
        else:
            unmatched_counts["TITLE_TICKER_NOT_IN_PRIOR_TOP120"] += 1
    out["title_code_top120_comparison"] = {
        "matched_by_family": dict(sorted(match_counts.items())),
        "unmatched": dict(sorted(unmatched_counts.items())),
        "limitation": "TITLE_STOCK_CODE_NOT_DATED_SECURITY_CROSSWALK; NOT_RESEARCH_ADMISSION"}
    universe_tree = _git_tree(UNIVERSE_REF, "ledger/universe/kr")
    all_snaps = defaultdict(list)
    source_hashes = []
    universe_expected = sorted(p for p in universe_tree if p.endswith(".jsonl.gz"))
    universe_missing = []
    for rel in universe_expected:
        local_path = source_root / rel
        if not local_path.exists():
            # The 2013 shard was inspected individually; no implicit fetch or
            # claim that absent later years were measured.
            local_path = source_root / Path(rel).name
        if not local_path.exists():
            universe_missing.append(rel)
            continue
        data = local_path.read_bytes()
        _verify(data, universe_tree[rel])
        source_hashes.append({"path": rel, "git_blob": universe_tree[rel], "sha256": _sha(data)})
        for line in gzip.decompress(data).decode().splitlines():
            r = json.loads(line)
            all_snaps[r["date"]].append(r["ticker"])
    out["retained_rank_capped_universe"] = {
        **membership_inventory(dict(all_snaps)), "commit": UNIVERSE_REF,
        "source_files": source_hashes, "scope": "INSPECTED_2013_ONLY_RANK_CAPPED_TOP300_NOT_FULL_KOSPI",
        "uninspected_shards": universe_missing}
    termination_path = ROOT / "docs/results/kr-termination-inventory.json"
    term_bytes = termination_path.read_bytes()
    if _sha(term_bytes) != TERMINATIONS_SHA256:
        raise ValueError("PINNED_TERMINATION_SOURCE_MISMATCH")
    term = json.loads(term_bytes)
    out["existing_termination_metadata"] = {
        "source_path": str(termination_path.relative_to(ROOT)), "sha256": _sha(term_bytes),
        "packet_source_commit": BASELINE_MAIN, "identified_securities": len(term["securities"]),
        "codes": sorted(r["code"] for r in term["securities"]),
        "new_return_eligible": 0, "note": "SOURCE_INVENTORY_ONLY_NOT_TERMINAL_ECONOMICS_ADMISSION"}
    out["expanded_full_kospi"] = {"monthly_counts": None, "event_count_delta_vs_top120": None,
                                   "reason": "FULL_UNCAPPED_KOSPI_SOURCE_NOT_RETAINED"}
    out["expanded_liquidity"] = {"monthly_counts": None, "event_count_delta_vs_top120": None,
                                 "reason": "OFFICIAL_TRAILING_ACC_TRDVAL_AND_APPROVED_CONTRACT_REQUIRED"}
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(build(args.source_root), ensure_ascii=False,
                                      sort_keys=True, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
