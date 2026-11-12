"""Prepare the next prospective cohort under prospective-protocol-v1.json (four comparable arms).

python research/evidence_first_v2/prospective.py dry-run        ->  results/prospective-dry-run.json
python research/evidence_first_v2/prospective.py check-activation

This module builds DRAFT cohort records only. It has no function that writes to a ledger: recording is
a separate step that calls assert_activation_allowed() first, and that call refuses until the Owner
approval file and every activation gate are in place. Arms share one information cutoff, one execution
rule, one cost basis and one return definition; only the selection differs.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PROTOCOL = HERE / "prospective-protocol-v1.json"
APPROVAL = HERE / "owner-approvals" / "prospective-v1.json"
INTEGRITY = HERE / "results" / "data-integrity.json"
OUT = HERE / "results" / "prospective-dry-run.json"
ETF = {"KR": "069500.KS", "US": "SPY"}
UNCLASSIFIED = "UNCLASSIFIED"


class ProtocolError(ValueError):
    pass


def protocol() -> tuple[dict, str]:
    raw = PROTOCOL.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


# ----------------------------------------------------------------------------- industry
def _kr_intervals() -> dict:
    p = ROOT / "data" / "kr-industry-membership-foundation-v4" / "state" / "intervals.json.gz"
    return json.loads(gzip.decompress(p.read_bytes()))


def industry_of(region: str, ticker: str, as_of: str, kr_intervals: dict | None = None) -> str:
    """Point-in-time industry; anything unknown is the shared UNCLASSIFIED bucket (same cap), never its own."""
    if region == "KR":
        for iv in (kr_intervals if kr_intervals is not None else _kr_intervals()).get(ticker, []):
            if iv.get("status") == "UNKNOWN" or not iv.get("research_industry_name"):
                continue
            if (iv["start"] is None or iv["start"] <= as_of) and (iv["end"] is None or as_of < iv["end"]):
                return iv["research_industry_name"]
        return UNCLASSIFIED
    sys.path.insert(0, str(ROOT))
    from pipeline.sectors import sector_of
    return sector_of(ticker) or UNCLASSIFIED


# ----------------------------------------------------------------------------- selection
def select_b1(ranked: list[str], industry: dict[str, str], max_names: int, per_industry: int) -> dict:
    """Walk the ROE ranking; skip a name whose industry already holds per_industry picks; stop at max_names."""
    picked, skipped, count = [], [], {}
    for t in ranked:
        if len(picked) == max_names:
            break
        ind = industry[t]
        if count.get(ind, 0) >= per_industry:
            skipped.append({"ticker": t, "reason": f"INDUSTRY_CAP {ind}"})
            continue
        picked.append(t)
        count[ind] = count.get(ind, 0) + 1
    return {"selected": picked, "skipped": skipped, "industries": {t: industry[t] for t in picked}}


def weights(selected: list[str], region: str, per_name: float) -> dict[str, float]:
    if len(selected) * per_name > 1 + 1e-12:
        raise ProtocolError("WEIGHTS_EXCEED_ONE")
    w = {t: per_name for t in selected}
    w[ETF[region]] = round(1 - per_name * len(selected), 10)
    return w


def ai_filter(b1_selected: list[str], review: dict | None) -> dict:
    """The AI may only remove B1 names. review = {ticker: {"decision": "KEEP"|"EXCLUDE", "reasons": [...]}}."""
    if review is None:
        return {"status": "NO_RECORD", "reason": "NO_REVIEW_COMMITTED_BEFORE_DEADLINE", "selected": None}
    extra = set(review) - set(b1_selected)
    if extra:
        raise ProtocolError(f"AI_MAY_NOT_ADD_NAMES {sorted(extra)}")
    missing = set(b1_selected) - set(review)
    if missing:
        raise ProtocolError(f"AI_REVIEW_INCOMPLETE {sorted(missing)}")
    for t, v in review.items():
        if v.get("decision") not in ("KEEP", "EXCLUDE"):
            raise ProtocolError(f"AI_DECISION_INVALID {t}")
        if v["decision"] == "EXCLUDE" and len(v.get("reasons", [])) < 2:
            raise ProtocolError(f"AI_EXCLUDE_NEEDS_TWO_REASONS {t}")
        if any(ch.isdigit() for r in v.get("reasons", []) for ch in r):
            raise ProtocolError(f"NUMBER_IN_AI_REASON {t}")
    keep = [t for t in b1_selected if review[t]["decision"] == "KEEP"]
    return {"status": "DRAFT", "selected": keep, "excluded": {t: review[t]["reasons"] for t in b1_selected if t not in keep}}


def build_cohort(region: str, cohort: str, decision_date: str, ranked: list[dict], production: dict,
                 review: dict | None, industry: dict[str, str], proto: dict, proto_sha: str, label: str) -> dict:
    p = proto["portfolio"]
    b1 = select_b1([r["ticker"] for r in ranked], industry, p["maxNames"], p["maxNamesPerIndustry"])
    ai = ai_filter(b1["selected"], review)
    common = {"region": region, "cohort": cohort, "decisionDate": decision_date,
              "informationCutoff": f"{decision_date} regional close", "execution": proto["cohort"]["execution"],
              "costs": production.get("costs"), "costStress": 2.0, "returnDefinition": proto["returns"]["definition"],
              "benchmark": ETF[region], "protocolSha256": proto_sha, "label": label}
    arms = {
        "ETF100": {"v3Path": "v3.B0", "track": "BENCHMARK", "status": "DRAFT", "weights": {ETF[region]: 1.0}},
        "B1_ROE": {"v3Path": "v3.B1", "track": "B_PROSPECTIVE_VIRTUAL", "status": "DRAFT", "recordLabel": "UNVERIFIED_PROSPECTIVE_VIRTUAL",
                   "weights": weights(b1["selected"], region, p["perNameWeight"]), "selection": b1,
                   "inputs": {r["ticker"]: {k: r[k] for k in ("roe", "reportDate", "availableFrom")} for r in ranked if r["ticker"] in b1["selected"]}},
        "PRODUCTION": {"v3Path": "v3.B2", "track": "PRODUCTION_COPY", "status": "DRAFT", "weights": production["weights"],
                       "receiptId": production.get("receiptId"), "receiptDigest": production.get("digest")},
        "B1_PLUS_AI": {"v3Path": "v3.B3", "track": "B_PROSPECTIVE_VIRTUAL", "recordLabel": "UNVERIFIED_PROSPECTIVE_VIRTUAL",
                       "status": ai["status"], "reason": ai.get("reason"),
                       "weights": None if ai["selected"] is None else weights(ai["selected"], region, p["perNameWeight"]),
                       "excluded": ai.get("excluded")},
    }
    for a in arms.values():
        if a["weights"] is not None and abs(sum(a["weights"].values()) - 1) > 1e-9:
            raise ProtocolError("WEIGHTS_DO_NOT_SUM_TO_ONE")
    return {"common": common, "arms": arms}


# ----------------------------------------------------------------------------- activation
def assert_activation_allowed(approval: Path = APPROVAL) -> None:
    sys.path.insert(0, str(ROOT / "research" / "decision_desk_v1"))
    import ledger as L
    _, sha = protocol()
    missing = []
    if not approval.exists():
        missing.append("OWNER_APPROVAL_FILE_MISSING")
    elif json.loads(approval.read_text()).get("protocolSha256") != sha:
        missing.append("OWNER_APPROVAL_NAMES_ANOTHER_PROTOCOL")
    missing += [f"GATE_OPEN {g['id']}" for g in L.open_gates("PROSPECTIVE_V1")]
    if missing:
        raise ProtocolError("ACTIVATION_BLOCKED " + ", ".join(missing))


# ----------------------------------------------------------------------------- dry run
def dry_run() -> dict:
    proto, sha = protocol()
    integ = json.loads(INTEGRITY.read_text())
    desk = json.loads((ROOT / "research" / "decision_desk_v1" / "desk.json").read_text())
    kr_iv = _kr_intervals()
    out = {"schema": "PROSPECTIVE_DRY_RUN_V1", "protocolSha256": sha,
           "label": "DRY_RUN_NOT_A_COHORT: run on the 2026-11 census to exercise the rules; nothing is recorded or evaluated",
           "integritySha256": hashlib.sha256(INTEGRITY.read_bytes()).hexdigest(), "regions": {}}
    for region in ("KR", "US"):
        r = integ["regions"][region]
        ranked = r["b1v2DryRun"]["ranked"]
        industry = {x["ticker"]: industry_of(region, x["ticker"], r["asOf"], kr_iv) for x in ranked}
        prod = desk["regions"][region]["production"]
        out["regions"][region] = build_cohort(region, "DRY-RUN", r["asOf"], ranked, prod, None, industry, proto, sha,
                                              "DRY_RUN_NOT_A_COHORT")
    try:
        assert_activation_allowed()
        out["activation"] = "ALLOWED"
    except ProtocolError as e:
        out["activation"] = str(e)
    return out


def production_receipt(signal_commit: str, region: str, as_of: str) -> dict:
    """The FINAL_WEEKLY production receipt of the decision date, read from the pinned signal-history commit."""
    import subprocess
    raw = subprocess.check_output(["git", "show", f"{signal_commit}:ledger/weekly-decisions/receipts.jsonl"], cwd=ROOT)
    rows = [json.loads(x) for x in raw.decode().splitlines() if x.strip()]
    hit = [r for r in rows if r["region"] == region and r["asOfDate"] == as_of and r["weekStatus"] == "FINAL_WEEKLY"]
    if len(hit) != 1:
        raise ProtocolError(f"NO_UNIQUE_FINAL_WEEKLY_RECEIPT {region} {as_of}: {len(hit)}")
    r = hit[0]
    return {"weights": r["weights"], "costs": r["costs"], "receiptId": r["receiptId"], "digest": r["digest"]}


def prepare(cohort: str, signal_commit: str, integrity_path: Path, reviews: dict | None = None) -> dict:
    """Draft the four arms of a real cohort. Writes nothing to any ledger; recording is a separate,
    activation-gated step."""
    proto, sha = protocol()
    integ = json.loads(integrity_path.read_text())
    kr_iv = _kr_intervals()
    out = {"schema": "PROSPECTIVE_COHORT_DRAFT_V1", "cohort": cohort, "protocolSha256": sha, "signalHistoryCommit": signal_commit,
           "integritySha256": hashlib.sha256(integrity_path.read_bytes()).hexdigest(), "status": "DRAFT_NOT_RECORDED", "regions": {}}
    for region in ("KR", "US"):
        r = integ["regions"][region]
        ranked = r["b1v2DryRun"]["ranked"]
        industry = {x["ticker"]: industry_of(region, x["ticker"], r["asOf"], kr_iv) for x in ranked}
        prod = production_receipt(signal_commit, region, r["asOf"])
        out["regions"][region] = build_cohort(region, cohort, r["asOf"], ranked, prod, (reviews or {}).get(region),
                                              industry, proto, sha, "DRAFT_NOT_RECORDED")
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "dry-run"
    if cmd == "check-activation":
        assert_activation_allowed()
        print("ACTIVATION_ALLOWED")
    elif cmd == "prepare":
        import argparse
        ap = argparse.ArgumentParser()
        ap.add_argument("cmd")
        ap.add_argument("--cohort", required=True)
        ap.add_argument("--signal-commit", required=True)
        ap.add_argument("--integrity", type=Path, required=True)
        ap.add_argument("--reviews", type=Path, help="JSON {region: {ticker: {decision, reasons}}}")
        a = ap.parse_args()
        res = prepare(a.cohort, a.signal_commit, a.integrity, json.loads(a.reviews.read_text()) if a.reviews else None)
        dest = HERE / "cohorts" / a.cohort / "draft.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(res, indent=1, ensure_ascii=False, sort_keys=True) + "\n")
        print(dest)
    else:
        res = dry_run()
        OUT.write_text(json.dumps(res, indent=1, ensure_ascii=False, sort_keys=True) + "\n")
        for g, v in res["regions"].items():
            print(g, {k: a["weights"] for k, a in v["arms"].items()}, v["arms"]["B1_ROE"]["selection"]["skipped"])
        print(res["activation"])
