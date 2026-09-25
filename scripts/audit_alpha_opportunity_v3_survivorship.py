"""Reproduce alpha-opportunity-model-v3's input-only survivorship audit.

    python scripts/audit_alpha_opportunity_v3_survivorship.py \
        --input-root <checkout of signal-history 4ea107e with ledger/replay-inputs,
                      ledger/historical/replay-v16/inputs.json, ledger/universe/kr> \
        --output docs/results/alpha-opportunity-model-v3-survivorship-audit.json

Reads sealed identities, price EXISTENCE, membership and corporate-event
presence. Computes no return and constructs no label. Output is byte-stable.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import alpha_opportunity_v3_survivorship as A  # noqa: E402
from pipeline import historical_store as HS  # noqa: E402
from pipeline import replay_inputs as RI  # noqa: E402

REPLAY = "replay-v16"
US_MEMBERSHIP = ROOT / "research_specs/alpha-opportunity-model-v1-us-membership.json.gz"
US_IDENTITY = ROOT / "research_specs/alpha-opportunity-model-v3-us-identity-evidence.json.gz"
V2_AUDIT = ROOT / "docs/results/alpha-opportunity-model-v2-input-audit.json"
V3_FIRST_SEAL_COUNTS = {"union": 828, "noPanelNames": 195}  # PR #156 first commit f3077f0
START, THROUGH = "2013-01-01", "2026-09-14"
KR_TOP = 120


def blob_sha1(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def kr_snapshots(ledger):
    grouped = {}
    for path in sorted((Path(ledger) / "universe/kr").glob("krx-universe-*.jsonl.gz")):
        for row in HS.read_jsonl(path):
            grouped.setdefault(row["date"], []).append(row)
    return [{"date": d, "members": sorted(r["ticker"] for r in sorted(
                (r for r in rows if r.get("rank") is not None), key=lambda r: (r["rank"], r["ticker"]))[:KR_TOP])}
            for d, rows in sorted(grouped.items())]


def kr_names(ledger):
    names = {}
    for path in sorted((Path(ledger) / "universe/kr").glob("krx-universe-*.jsonl.gz")):
        for row in HS.read_jsonl(path):
            names.setdefault(row["ticker"], {})[row["date"]] = row.get("name")
    return {t: v[max(v)] for t, v in names.items()}


def kr_terminations(kr_audit, avail, dividends, names):
    """The terminated KR securities, typed only as far as sealed evidence allows.

    No sealed or repository source states WHY a KR security stopped trading
    (merger, share swap into a holding company, tender/cash-out, bankruptcy
    delisting). Every row is therefore TERMINATION_TYPE_UNRESOLVED and names
    the DART disclosure families that would resolve it.
    """
    out = []
    for t in kr_audit["_sets"]["terminated"]:
        closes = [d for d, (ok, _) in avail[t].items() if ok]
        out.append({"code": t, "krxName": names.get(t), "lastSession": max(closes),
                    "dividendEvents": dividends.get(t, 0),
                    "terminationType": "TERMINATION_TYPE_UNRESOLVED",
                    "resolveWith": "DART 주요사항보고서 (합병/주식교환·이전/분할합병/영업양수도 결정), 공개매수 신고, "
                                   "상장폐지 관련 공시, and 현금·현물배당결정 for distributions"})
    return out


def us_identity_index(us_snapshots):
    """Per-snapshot {symbol: (rawSymbol, name, cik)} aligned by sourceCommit."""
    evidence = json.loads(gzip.decompress(US_IDENTITY.read_bytes()))
    if evidence["pinnedMembershipSha256"] != hashlib.sha256(US_MEMBERSHIP.read_bytes()).hexdigest():
        raise ValueError("IDENTITY_EVIDENCE_FOR_A_DIFFERENT_MEMBERSHIP")
    by_commit = {s["sourceCommit"]: s for s in evidence["snapshots"]}
    rows = evidence["rows"]
    index = []
    for snap in us_snapshots:
        ev = by_commit[snap["sourceCommit"]]
        table = {rows[i][0].replace(".", "-"): tuple(rows[i]) for i in ev["rows"]}
        if sorted(table) != snap["members"]:
            raise ValueError("IDENTITY_EVIDENCE_DOES_NOT_MATCH_SNAPSHOT: " + snap["date"])
        index.append(table)
    return index, evidence


def reconciliation(us_audit, us_snapshots, avail):
    """Why v2 (829 / 194), v3's first seal (828 / 195) and this audit differ.

    Every step is a set difference computed here, not a narrative number.
    """
    v2 = json.loads(V2_AUDIT.read_text())
    malformed = us_audit["identity"]["malformed"]
    ident = us_audit["identity"]
    reachable = set()
    for date in A.weekly_grid([d for d in A.RC.sessions("2012-01-01", "2027-12-31", "US")
                               if str(d.date()) >= START], THROUGH):
        reachable.update(A.snapshot_on(us_snapshots, date)["members"])
    first_seal = {t for t in reachable if t not in avail}
    now = set(us_audit["_sets"]["noPanel"])
    resolved_malformed = {k for k, v in malformed.items() if v["resolvedTo"]} & first_seal
    priced_by_rename = {t for t, r in ident["renames"].items() if r["pricedBy"]} & first_seal
    reuse_now_unpriced = now - first_seal
    steps = {"firstSealNoPanel": len(first_seal),
             "minusResolvedMalformedKeys": sorted(resolved_malformed),
             "minusRenamesPricedThroughSuccessor": sorted(priced_by_rename),
             "plusSymbolsWhosePanelBelongsToALaterSecurity": sorted(reuse_now_unpriced),
             "equals": len(first_seal) - len(resolved_malformed) - len(priced_by_rename) + len(reuse_now_unpriced),
             "auditNoPanel": len(now)}
    if steps["equals"] != steps["auditNoPanel"] or not (first_seal - resolved_malformed - priced_by_rename) <= now:
        raise ValueError("RECONCILIATION_DOES_NOT_CLOSE")
    return {"steps": steps,
        "v2InputAudit": {"membershipUnion": v2["usMembershipUnion"], "noPanelNames": v2["usNoPanelNames"],
                         "method": "union over ALL snapshots; no-panel list from data/us-unpriced-members.json, "
                                   "which set the malformed keys aside"},
        "v3FirstSeal": {**V3_FIRST_SEAL_COUNTS,
                        "method": "union over grid-REACHABLE snapshots (strictly-earlier lookup); every "
                                  "non-panel key counted as a departed security, malformed or not"},
        "thisAudit": {"rawAllSnapshotUnion": us_audit["universe"]["rawAllSnapshotUnion"],
                      "rawGridReachableUnion": us_audit["universe"]["rawGridReachableUnion"],
                      "identityResolvedUnion": us_audit["universe"]["union"],
                      "noPanelIdentities": us_audit["sampleSurvivorship"]["noPanelNames"]},
        "malformedKeys": malformed,
        "explanation": [
            "829 -> 828: 'RVTY (Previously PKI)' appears only in the 2023-12-31 snapshot, which no weekly "
            "signal date ever uses under the strictly-earlier rule, so it is in the all-snapshot union and "
            "not in the reachable one",
            "194 -> 195: v3's first seal counted the malformed key 'American Airlines Group' (reachable from "
            "the 2021-03-11 snapshot) as a departed security without a panel; v2's list excluded it",
            "both keys are upstream data errors in the Symbol column (commits 9217bee and a9ae84a) and are "
            "resolved here to AAL and RVTY by the bracketing-snapshot rule; renames verified by CIK, an "
            "explicit '(Previously X)' annotation or an identical name at the exact switch are then priced "
            "through their successor, which is why no-panel identities fall below 194",
        ],
    }


def run(input_root):
    ledger = Path(input_root) / "ledger"
    manifest_raw = json.loads((ledger / f"historical/{REPLAY}/inputs.json").read_text())
    store = RI.InputStore(ledger, REPLAY, manifest_raw["dataVersion"])
    manifest = store.manifest()
    rows = []
    for name in sorted(c for c in manifest["components"] if RI.is_price_panel(c)):
        rows.extend(store.load_component(name, manifest))
    avail = A.availability_from_rows(rows)
    del rows
    dividends = {}
    for name in sorted(c for c in manifest["components"] if c.startswith("corporate-events/20")):
        for row in store.load_component(name, manifest):
            if row.get("dividend"):
                dividends[row["ticker"]] = dividends.get(row["ticker"], 0) + 1
    price_source = store.load_component("price/source", manifest)
    us = json.loads(gzip.decompress(US_MEMBERSHIP.read_bytes()))["snapshots"]
    kr = kr_snapshots(ledger)
    us_index, evidence = us_identity_index(us)
    actions = store.load_component("corporate-actions", manifest)[0]["book"]["actions"]
    audits, verdicts, windows = {}, {}, {}
    for region, snaps, idx in (("US", us, us_index), ("KR", kr, None)):
        audit = A.audit_region(region, snaps, avail, dividends, start=START, through=THROUGH,
                               identity_index=idx,
                               corporate_actions=[a for a in actions if a.get("region") == region])
        audits[region] = audit
        verdicts[region] = A.region_verdict(audit)
        windows[region] = A.restricted_window_exists(audit)
    kr_shards = {str(p.relative_to(input_root)): blob_sha1(p.read_bytes())
                 for p in sorted((ledger / "universe/kr").glob("krx-universe-*.jsonl.gz"))}
    return {
        "studyId": "alpha-opportunity-model-v3", "phase": "INPUT_ONLY_SURVIVORSHIP_AUDIT",
        "historicalOutcomesComputed": False, "returnsComputed": False, "labelsConstructed": False,
        "modelsTrained": False, "priceUse": "existence of a positive finite close/volume only",
        "inputs": {"signalHistoryCommit": "4ea107ed0cde289f0a049a65ff13d2441a786710",
                   "replayVersion": REPLAY, "replayManifestSha256": manifest["sha256"],
                   "through": manifest["through"],
                   "usMembership": {"path": str(US_MEMBERSHIP.relative_to(ROOT)),
                                    "sha256": hashlib.sha256(US_MEMBERSHIP.read_bytes()).hexdigest()},
                   "usIdentityEvidence": {"path": str(US_IDENTITY.relative_to(ROOT)),
                                          "sha256": hashlib.sha256(US_IDENTITY.read_bytes()).hexdigest(),
                                          "upstream": evidence["source"], "ref": evidence["ref"],
                                          "reproducesPinnedMembers": evidence["reproducesPinnedMembers"],
                                          "firstSnapshotWithCik": next(s["date"] for s in evidence["snapshots"] if s["hasCik"])},
                   "corporateActions": [a["ticker"] for a in actions],
                   "krUniverseShardBlobSha1": kr_shards,
                   "priceSource": [{k: s.get(k) for k in ("region", "vendor", "distributions", "source")}
                                   for s in price_source]},
        "window": {"start": START, "through": THROUGH, "krTopN": KR_TOP,
                   "membership": "strictly-earlier snapshot per last regional session of each week"},
        "regions": audits, "verdicts": verdicts, "restrictedWindow": windows,
        "usCountReconciliation": reconciliation(audits["US"], us, avail),
        "krTerminations": kr_terminations(audits["KR"], avail, dividends, kr_names(ledger)),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    report = run(args.input_root)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(json.dumps({"verdicts": report["verdicts"], "restrictedWindow": report["restrictedWindow"]},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
