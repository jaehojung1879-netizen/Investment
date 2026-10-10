"""Turn a validated production site-data.json into the weekly decision artifact.

    python -m pipeline.weekly_publish <site-data.json> <receipts-in.jsonl> \
        <weekly-decision.json out> <receipts-out.jsonl>

Why a separate step: ``pipeline/build.py``, ``pipeline/validate.py`` and
``.github/workflows/pages.yml`` are byte-pinned by sealed studies
(alpha-opportunity-model-v1 and kr-alpha-atlas Phase C v4), and so is the
workflow census, so no new workflow file can be added. The weekly layer runs
inside the paper-ledger workflow (``ledger.yml``) on the artifact it has just
built and validated, and writes to signal-history beside the paper ledger. Every input it
needs is in site-data: the research sleeve (``longTerm.regions.*.picks``), the
production calibration (``historicalValidation.alphaCalibration``), each name's
last session (``details.*.asOf``) and the safety flags.

``now`` is the site's own ``generatedAt``, not the wall clock, so the same
site-data always produces the same receipts.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

from . import weekly_decision as W
from . import weekly_history as H

SCHEMA = "WEEKLY_DECISION_ARTIFACT_V1"
ACTIVE = {"STOCKS_SELECTED", "PASSIVE_NO_DEFENSIBLE_EDGE", "NO_CANDIDATES"}


def observed_sessions(site: dict) -> dict:
    """Each region's latest observed session, from its own names only."""
    out: dict[str, str] = {}
    for detail in (site.get("details") or {}).values():
        region, as_of = detail.get("region"), detail.get("asOf")
        if region in W.BENCHMARKS and as_of and as_of > out.get(region, ""):
            out[region] = as_of
    return out


def unsafe_reason(site: dict) -> str | None:
    if site.get("recommendationsBlocked"):
        return "RECOMMENDATIONS_BLOCKED"
    mode = (site.get("provenance") or {}).get("dataMode") or site.get("dataMode")
    if site.get("seed") or site.get("synthetic") or mode in {"seed", "synthetic"}:
        return "SEED_OR_SYNTHETIC_ARTIFACT"
    if site.get("stale"):
        return "STALE_ARTIFACT"
    return None


def receipt_history(receipts: list[dict], limit: int = 12) -> dict:
    """The last FINAL receipts per region, compact, newest first."""
    out = {}
    for region in W.BENCHMARKS:
        rows = sorted((r for r in receipts if r.get("region") == region
                       and r.get("weekStatus") == "FINAL_WEEKLY"),
                      key=lambda r: r["asOfDate"], reverse=True)[:limit]
        out[region] = [{"asOfDate": r["asOfDate"], "status": r.get("status"),
                        "stockCount": r.get("stockCount"),
                        "benchmarkWeightPct": r.get("benchmarkWeightPct"),
                        "holdings": [{"ticker": h["ticker"], "name": h.get("name")}
                                     for h in r.get("holdings") or []],
                        "digest": r.get("digest")} for r in rows]
    return out


def build_from_site(site: dict, site_sha256: str, receipts: list[dict]) -> dict:
    now = datetime.fromisoformat(str(site["generatedAt"]).replace("Z", "+00:00"))
    reason = unsafe_reason(site)
    calibration = (site.get("historicalValidation") or {}).get("alphaCalibration")
    provenance = site.get("provenance") or {}
    identity = {
        "siteDataSha256": site_sha256,
        "siteGeneratedAt": site.get("generatedAt"),
        "buildCommitSha": provenance.get("buildCommitSha"),
        "modelVersion": provenance.get("modelVersion") or site.get("modelVersion"),
        "historicalLedgerCommitSha": (site.get("historicalValidation") or {}).get("ledgerCommitSha"),
        "calibrationSha256": W.calibration_digest(calibration),
    }
    block = W.build(site.get("longTerm"), calibration, observed_sessions(site), now=now,
                    blocked=reason is not None, prior_receipts=receipts,
                    names=site.get("names") or {}, input_identity=identity,
                    history=H.build_history())
    # A week already recorded is shown exactly as recorded. A later build for
    # the same (policy, region, asOfDate) may differ (vendor snapshots move);
    # the page must not show a decision the ledger refused to record.
    recorded = {r.get("receiptId"): r for r in receipts}
    for region, blob in block["regions"].items():
        prior = recorded.get(blob.get("receiptId"))
        if prior is not None and prior.get("digest") != blob.get("digest"):
            block["regions"][region] = {**prior, "freshness": blob.get("freshness"),
                                        "publishedFrom": "RECORDED_RECEIPT",
                                        "laterRecomputationDigest": blob.get("digest")}
    block["receiptHistory"] = receipt_history(receipts)
    block["schema"] = SCHEMA
    block["unsafeReason"] = reason
    block["sourceArtifact"] = identity
    return block


def validate(block: dict) -> list[str]:
    """Invariants the published file must satisfy; any error refuses publication."""
    errors: list[str] = []
    if block.get("liveValidated") is not False:
        errors.append("claims_validation")
    if (block.get("evidence") or {}).get("verifiedLive") != "NOT_VERIFIED":
        errors.append("verified_without_ledger")
    blocked = bool(block.get("blocked"))
    for region, blob in (block.get("regions") or {}).items():
        holdings, weights = blob.get("holdings") or [], blob.get("weights") or {}
        status = blob.get("status")
        if blocked:
            if status != "BLOCKED" or holdings or weights or blob.get("candidates"):
                errors.append(f"blocked_with_actionable_output:{region}")
            continue
        if blob.get("liveValidated") not in (None, False):
            errors.append(f"claims_validation:{region}")
        if status not in ACTIVE:
            if holdings or weights:
                errors.append(f"inactive_with_weights:{region}")
            continue
        bench = W.BENCHMARKS[region]
        if blob.get("benchmark") != bench:
            errors.append(f"wrong_benchmark:{region}")
        if len(holdings) > W.MAX_NAMES or blob.get("stockCount") != len(holdings):
            errors.append(f"name_count_invalid:{region}")
        if abs(sum(float(v) for v in weights.values()) - 1.0) > 1e-6:
            errors.append(f"weights_not_100pct:{region}")
        stocks = {t for t in weights if t != bench}
        if stocks != {h.get("ticker") for h in holdings}:
            errors.append(f"weights_holdings_mismatch:{region}")
        for row in holdings:
            net = row.get("expectedNetAdvantagePct")
            if net is None or float(net) <= 0:
                errors.append(f"unsupported_holding:{region}:{row.get('ticker')}")
        if not holdings and weights != {bench: 1.0}:
            errors.append(f"zero_names_not_full_benchmark:{region}")
        if blob.get("digest") and W.receipt_digest(blob) != blob["digest"]:
            errors.append(f"receipt_digest_mismatch:{region}")
    return errors


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 4:
        print(__doc__)
        return 2
    site_path, receipts_in, out_path, receipts_out = map(Path, argv)
    raw = site_path.read_bytes()
    site = json.loads(raw)
    receipts = _read_jsonl(receipts_in)
    block = build_from_site(site, hashlib.sha256(raw).hexdigest(), receipts)
    errors = validate(block)
    if errors:
        print("refusing to publish the weekly decision:", ", ".join(errors))
        return 1
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(block, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n",
                        encoding="utf-8")
    new = [] if block.get("blocked") else [
        blob for blob in block["regions"].values() if blob.get("receiptId")]
    merged, report = W.append_receipts(receipts, new)
    receipts_out.parent.mkdir(parents=True, exist_ok=True)
    receipts_out.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n"
                                    for r in merged), encoding="utf-8")
    summary = {r: (b.get("status"), b.get("asOfDate"), b.get("weekStatus"), b.get("stockCount"))
               for r, b in block["regions"].items()}
    print(json.dumps({"regions": summary, "receipts": report}, ensure_ascii=False))
    for conflict in report["conflicts"]:
        print(f"notice: kept the first receipt for {conflict['receiptId']}; a later, different "
              "payload for the same week was refused")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
