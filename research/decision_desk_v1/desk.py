"""decision-desk-v1 stage runner (protocol v2).

  status              where each cohort stands and what it is waiting for
  packet              stage 2: PIT evidence packet + review request (needs the sealed protocol)
  review-template     stage 3: skeleton review for one reviewer
  commit-review       stage 3: commit-reveal commitment (sha256 of the finished review)
  check-review        stage 3: validate a review against the frozen rules
  decide              stage 4: B0/B1/B2/BX records (needs packet and reviews committed, before the deadline)
  verify-publication  stage 5: PUBLICATION_VERIFIED / _LATE annotations from git history
  annotate            append an annotation (e.g. PIT_CONTAMINATED) without touching a record
  evaluate            stage 6: append SCORED / SOURCE_BLOCKED outcomes for matured horizons

Every stage refuses rather than repairs. No AI provider is called: a review is written by an
agent session and committed (reviewers.json explains why).
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import judgment as J  # noqa: E402
import ledger as L  # noqa: E402
import packet as P  # noqa: E402

LEDGER = L.DRY_RUN_DIR / "ledger.jsonl"
LEGACY = {"2026-11": {"packet": HERE / "inputs" / "2026-11" / "evidence-pack.json",
                      "reviews": {"claude": HERE / "ai-reviews" / "2026-11.json"}}}
BENCH = {"KR": "069500.KS", "US": "SPY"}


class StageError(RuntimeError):
    pass


# ----------------------------------------------------------------------------- git
def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def rel(p: Path) -> str:
    p = Path(p).resolve()
    return str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)


def committed_unchanged(p: Path) -> bool:
    r = rel(p)
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", r], cwd=ROOT, capture_output=True).returncode == 0
    clean = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", r], cwd=ROOT).returncode == 0
    return tracked and clean


def first_commit(p: Path) -> tuple[str, str] | None:
    out = _git("log", "--diff-filter=A", "--format=%H %cI", "--", rel(p))
    return tuple(out.splitlines()[-1].split()) if out else None


def commit_adding(text: str, p: Path) -> tuple[str, str] | None:
    out = _git("log", "--format=%H %cI", "-S", text, "--", rel(p))
    return tuple(out.splitlines()[-1].split()) if out else None


def is_public(sha: str) -> bool:
    return bool(_git("branch", "-r", "--contains", sha))


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


# ----------------------------------------------------------------------------- paths
def cohort_dir(month: str) -> Path:
    return P.COHORTS / month


def packet_path(month: str) -> Path:
    return LEGACY[month]["packet"] if month in LEGACY else cohort_dir(month) / "evidence-packet.json"


def review_path(month: str, reviewer: str) -> Path:
    if month in LEGACY:
        return LEGACY[month]["reviews"][reviewer]
    return cohort_dir(month) / "reviews" / f"{reviewer}.json"


def commitment_path(month: str, reviewer: str) -> Path:
    return cohort_dir(month) / "commitments" / f"{reviewer}.sha256"


def reviewers_at_seal(month: str) -> list[dict]:
    """Registry as committed when the packet was sealed (a later enablement does not join the cohort)."""
    fc = first_commit(packet_path(month))
    text = _git("show", f"{fc[0]}:{rel(P.REVIEWERS)}") if fc else ""
    reg = json.loads(text) if text else json.loads(P.REVIEWERS.read_text())
    return [r for r in reg["reviewers"] if r["status"] == "ENABLED"]


# ----------------------------------------------------------------------------- stage 2
def cmd_packet(month: str, signal_commit: str, fetch: bool) -> dict:
    if not committed_unchanged(P.PROTOCOL_V2) or not committed_unchanged(P.REVIEWERS):
        raise StageError("PROTOCOL_NOT_SEALED: commit protocol-v2.json and reviewers.json unchanged first")
    path, pk = P.write_packet(signal_commit, month, fetch)
    return {"packet": rel(path), "sha256": sha256(path), "status": "AI_REVIEW_REQUIRED",
            "deadlines": {r: v["schedule"]["registrationDeadlineUtc"] for r, v in pk["regions"].items()},
            "next": "commit cohorts/<M>/ (packet, review-request, market) before any review is written"}


# ----------------------------------------------------------------------------- stage 3
TODO = "TODO"


def cmd_review_template(month: str, reviewer: str) -> Path:
    pk_path = packet_path(month)
    pk = json.loads(pk_path.read_text())
    out = review_path(month, reviewer)
    if out.exists():
        raise StageError("REVIEW_EXISTS")
    regions = {}
    for region, v in pk["regions"].items():
        names = [{"ticker": t, "layers": {k: [TODO, TODO] for k in J.LAYERS}, "decision": TODO,
                  "rejectionReason": None, "reasons": [], "thesis6m": None, "thesis12m": None, "catalysts": [], "risks": [],
                  "invalidationConditions": [], "notVerified": [], "whyVersusBenchmark": None} for t in v["gatePassers"]]
        regions[region] = {"marketLabel": TODO, "marketInterpretation": TODO, "macroLabel": TODO, "macroInterpretation": TODO,
                           "names": names, "gatedOutNote": f"{len(v['candidates']) - len(names)} candidates failed a frozen gate",
                           "regionDecision": {"selected": [], "zeroSelectionReason": None}}
    tpl = {"schema": "B2_AI_REVIEW_V2", "cohort": month, "reviewer": reviewer, "generatedAt": TODO,
           "packetSha256": sha256(pk_path), "knowledgeLimit": TODO,
           "readOnlyThePacket": True, "regions": regions}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(tpl, indent=1, ensure_ascii=False) + "\n")
    return out


def _as_v1_review(review: dict) -> dict:
    r = copy.deepcopy(review)
    r["evidencePackSha256"] = r.get("evidencePackSha256") or r.get("packetSha256")
    return r


def cmd_check_review(month: str, reviewer: str) -> list[str]:
    pk_path, rv_path = packet_path(month), review_path(month, reviewer)
    review = json.loads(rv_path.read_text())
    if TODO in json.dumps(review):
        raise StageError("REVIEW_HAS_TODO")
    if month not in LEGACY:
        pk = json.loads(pk_path.read_text())
        if review.get("reviewer") != reviewer or review.get("schema") != "B2_AI_REVIEW_V2":
            raise StageError("REVIEW_IDENTITY")
        if review["generatedAt"] < pk["sealedAtUtc"]:
            raise StageError("REVIEW_BEFORE_PACKET")
        J.check_prose_numbers(review, pk)
    pk = json.loads(pk_path.read_text())
    pk["_sha256"] = sha256(pk_path)
    sel = J.check_review(_as_v1_review(review), pk)
    return [f"{r}: {v or '0 names'}" for r, v in sel.items()]


def cmd_commit_review(month: str, reviewer: str) -> Path:
    cmd_check_review(month, reviewer)
    c = commitment_path(month, reviewer)
    if c.exists():
        raise StageError("COMMITMENT_EXISTS")
    c.parent.mkdir(parents=True, exist_ok=True)
    c.write_text(sha256(review_path(month, reviewer)) + "\n")
    return c


def independence(month: str, reviewers: list[str]) -> dict:
    """INDEPENDENT_BY_COMMIT_ORDER when every commitment precedes the first revealed review in git."""
    commits = {r: first_commit(commitment_path(month, r)) for r in reviewers}
    reveals = {r: first_commit(review_path(month, r)) for r in reviewers}
    out = {}
    first_reveal = min((v[1] for v in reveals.values() if v), default=None)
    for r in reviewers:
        c = commits[r]
        ok = (c is not None and first_reveal is not None and c[1] < first_reveal
              and commitment_path(month, r).read_text().strip() == sha256(review_path(month, r)))
        out[r] = "INDEPENDENT_BY_COMMIT_ORDER" if ok else "INDEPENDENCE_NOT_VERIFIED"
    return out


# ----------------------------------------------------------------------------- stage 4
def build_v2_records(month: str, now: str) -> tuple[list[dict], list[dict]]:
    pk_path = packet_path(month)
    pk = json.loads(pk_path.read_text())
    pk["_sha256"] = sha256(pk_path)
    enabled = reviewers_at_seal(month)
    primary = [r["id"] for r in enabled if r["role"] == "PRIMARY_B2"]
    arms = [r["id"] for r in enabled if r["role"] == "COMPARISON_ARM"]
    available = [r for r in primary + arms if review_path(month, r).exists() and committed_unchanged(review_path(month, r))]
    indep = independence(month, available) if available else {}
    reviews = {r: json.loads(review_path(month, r).read_text()) for r in available}
    for r, rv in reviews.items():  # the same stage checks as check-review, on the decide path itself
        if rv.get("schema") != "B2_AI_REVIEW_V2" or rv.get("reviewer") != r:
            raise StageError(f"REVIEW_IDENTITY {r}")
        if rv["generatedAt"] < pk["sealedAtUtc"]:
            raise StageError(f"REVIEW_BEFORE_PACKET {r}: generated {rv['generatedAt']} before the packet seal {pk['sealedAtUtc']}")
        J.check_prose_numbers(rv, pk)
    selections = {r: J.check_review(_as_v1_review(reviews[r]), pk) for r in available}
    hashes = {"protocolV2": sha256(P.PROTOCOL_V2), "packet": pk["_sha256"], "reviewers": sha256(P.REVIEWERS),
              "reviews": {r: sha256(review_path(month, r)) for r in available},
              "productionReceipts": {"signalHistoryCommit": pk["signalHistoryCommit"], "blob": pk["receiptsBlob"]}}
    records, notes = [], []
    per = J.PROTOCOL["portfolio"]["perNameWeight"]
    for region, ev in sorted(pk["regions"].items()):
        sch = ev["schedule"]
        if now > sch["registrationDeadlineUtc"]:
            raise StageError(f"REGISTRATION_CLOSED {region} deadline {sch['registrationDeadlineUtc']}")
        bench = BENCH[region]
        common = {"schema": L.SCHEMA_V2, "protocolVersion": 2, "region": region, "cohort": month,
                  "signalAsOf": ev["asOfDate"], "informationCutoff": ev["informationCutoffUtc"], "generatedAt": now,
                  "publishedAt": now, "sourceHashes": hashes, "benchmark": bench, "packetSha256": pk["_sha256"],
                  "plannedExecution": sch["plannedExecution"], "plannedExecutionCloseUtc": sch["plannedExecutionCloseUtc"],
                  "registrationDeadlineUtc": sch["registrationDeadlineUtc"], "costs": ev["costs"], "horizon126": None,
                  "horizon252": None, "subsequentReturns": None, "status": "DRY_RUN_NOT_ACTIVATED", "missingDataReason": None}
        records.append({**common, "path": "B0", "reviewer": None, "modelVersion": J.MODEL_VERSION["B0"], "selectedTickers": [],
                        "weights": {bench: 1.0}, "investmentThesis": "Regional ETF baseline.", "invalidationConditions": []})
        b1w = ev["productionWeights"]
        records.append({**common, "path": "B1", "reviewer": None, "modelVersion": J.MODEL_VERSION["B1"],
                        "selectedTickers": sorted(t for t in b1w if t != bench), "weights": b1w,
                        "investmentThesis": f"Production receipt {ev['receiptId']} ({ev['productionStatus']}). Copied, not re-decided.",
                        "invalidationConditions": [], "b1ReceiptDigest": ev["receiptDigest"]})
        for rid in available:
            rv = reviews[rid]["regions"][region]
            sel = selections[rid][region]
            names = {n["ticker"]: n for n in rv["names"]}
            cands = {c["ticker"]: c for c in ev["candidates"]}
            weights = {t: per for t in sel}
            weights[bench] = round(1.0 - per * len(sel), 10)
            picks = [{"ticker": t, "name": cands[t].get("name"), "observed": {k: cands[t].get(k) for k in J.OBSERVED_FIELDS},
                      "layers": {k: {"label": v[0], "interpretation": v[1]} for k, v in names[t]["layers"].items()},
                      **{f: names[t][f] for f in ("reasons", "thesis6m", "thesis12m", "catalysts", "risks", "notVerified", "whyVersusBenchmark")},
                      "researchWeight": per} for t in sel]
            records.append({**common, "path": "B2" if rid in primary else "BX", "reviewer": rid,
                            "generatedAt": reviews[rid]["generatedAt"],
                            "modelVersion": f"decision-desk-v1-ai-synthesis protocol-v2 reviewer={rid}",
                            "selectedTickers": sel, "weights": weights, "independence": indep.get(rid),
                            "investmentThesis": {"market": {"label": rv["marketLabel"], "interpretation": rv["marketInterpretation"], "observed": ev["market"]},
                                                 "macro": {"label": rv["macroLabel"], "interpretation": rv["macroInterpretation"], "observed": ev["macro"]},
                                                 "picks": picks,
                                                 "reviewedRejected": [{"ticker": n["ticker"], "reason": n.get("rejectionReason"),
                                                                       "layers": {k: v[0] for k, v in n["layers"].items()}}
                                                                      for n in rv["names"] if n["decision"] != "SELECT"],
                                                 "gatedOutCount": len(ev["candidates"]) - len(ev["gatePassers"]),
                                                 "zeroSelectionReason": rv["regionDecision"]["zeroSelectionReason"],
                                                 "knowledgeLimit": reviews[rid]["knowledgeLimit"]},
                            "invalidationConditions": {t: names[t]["invalidationConditions"] for t in sel}})
        if not any(r in available for r in primary):
            notes.append(("B2_NO_REVIEW", region, "No primary B2 review was committed before the deadline; B2 is not back-filled."))
        for rid in available:
            if indep.get(rid) != "INDEPENDENT_BY_COMMIT_ORDER" and len(available) > 1:
                notes.append(("INDEPENDENCE_NOT_VERIFIED", region, f"reviewer {rid}: commitment did not precede the first revealed review"))
    return records, notes


def cmd_decide(month: str, now: str | None = None) -> list[dict]:
    if month in LEGACY:
        raise StageError("LEGACY_COHORT: 2026-11 records exist and are never regenerated")
    now = now or now_utc()
    for p in (packet_path(month), cohort_dir(month) / "review-request.json"):
        if not committed_unchanged(p):
            raise StageError(f"NOT_COMMITTED {rel(p)}")
    rows = L.read(LEDGER)
    if any(r.get("cohort") == month and r.get("schema") in L.RECORD_SCHEMAS for r in rows):
        raise StageError("COHORT_ALREADY_DECIDED")
    records, notes = build_v2_records(month, now)
    written = [L.append(LEDGER, r) for r in records]
    for cat, region, detail in notes:
        digests = [r["digest"] for r in written if r["region"] == region]
        L.append(LEDGER, {"schema": L.ANNOTATION_SCHEMA, "cohort": month, "category": cat, "recordDigests": digests,
                          "detail": detail, "createdAt": now})
    return written


# ----------------------------------------------------------------------------- stage 5 / annotations
def cmd_annotate(month: str, category: str, paths: list[str], regions: list[str], detail: str, evidence: str | None) -> dict:
    rows = L.read(LEDGER)
    recs = [r for r in rows if r.get("schema") in L.RECORD_SCHEMAS and r["cohort"] == month
            and r["path"] in paths and r["region"] in regions]
    if not recs:
        raise StageError("NO_MATCHING_RECORDS")
    row = {"schema": L.ANNOTATION_SCHEMA, "cohort": month, "category": category, "recordDigests": [r["digest"] for r in recs],
           "detail": detail, "createdAt": now_utc()}
    if evidence:
        row["evidence"] = {"path": rel(HERE / evidence), "sha256": sha256(HERE / evidence)}
    return L.append(LEDGER, row)


def cmd_verify_publication(month: str) -> list[dict]:
    rows = L.read(LEDGER)
    done = {d for a in rows if a.get("schema") == L.ANNOTATION_SCHEMA
            and a["category"] in ("PUBLICATION_VERIFIED", "PUBLICATION_LATE", "PUBLICATION_NOT_OBSERVED")
            for d in a["recordDigests"]}
    out = []
    for r in rows:
        if r.get("schema") not in L.RECORD_SCHEMAS or r["cohort"] != month or r["digest"] in done:
            continue
        c = commit_adding(r["digest"], LEDGER)
        if c is None or not is_public(c[0]):
            continue  # not yet in a public commit; verify again after pushing
        deadline = r.get("registrationDeadlineUtc") or r["plannedExecutionCloseUtc"]
        when = pd.Timestamp(c[1]).tz_convert("UTC")
        observed = now_utc()
        # Committer time is set by the committer. Only an observation of the public commit made BEFORE the deadline
        # proves the record was public in time (#335 G8); a later check can say no more than "not observed".
        if when >= pd.Timestamp(deadline):
            cat = "PUBLICATION_LATE"
        elif observed <= deadline:
            cat = "PUBLICATION_VERIFIED"
        else:
            cat = "PUBLICATION_NOT_OBSERVED"
        out.append(L.append(LEDGER, {"schema": L.ANNOTATION_SCHEMA, "cohort": month, "category": cat,
                                     "recordDigests": [r["digest"]], "createdAt": observed,
                                     "detail": f"line first committed in {c[0]} at {when.strftime('%Y-%m-%dT%H:%M:%SZ')} (committer time); "
                                               f"public reachability observed {observed}; deadline {deadline}",
                                     "publicationCommit": c[0]}))
    return out


# ----------------------------------------------------------------------------- status
def cohort_status(month: str, rows: list[dict] | None = None, now: str | None = None) -> dict:
    rows = L.read(LEDGER) if rows is None else rows
    now = now or now_utc()
    recs = [r for r in rows if r.get("schema") in L.RECORD_SCHEMAS and r["cohort"] == month]
    notes = [a for a in rows if a.get("schema") == L.ANNOTATION_SCHEMA and a["cohort"] == month]
    outs = [o for o in rows if o.get("schema") == L.OUTCOME_SCHEMA and o["cohort"] == month]
    pk = packet_path(month)
    st = {"cohort": month, "protocol": "v1 (legacy)" if month in LEGACY else "v2",
          "packet": rel(pk) if pk.exists() else None, "records": len(recs),
          "annotations": sorted({a["category"] for a in notes}), "outcomes": len(outs)}
    if month not in LEGACY and not pk.exists():
        st["stage"] = "AWAITING_PACKET"
    elif not recs:
        missing = [r["id"] for r in reviewers_at_seal(month) if r["role"] == "PRIMARY_B2" and not review_path(month, r["id"]).exists()]
        st["stage"] = "AI_REVIEW_REQUIRED" if missing else "READY_TO_DECIDE"
        st["waitingFor"] = missing
        if pk.exists() and month not in LEGACY:
            st["deadlines"] = {r: v["schedule"]["registrationDeadlineUtc"] for r, v in json.loads(pk.read_text())["regions"].items()}
    else:
        verified = {d for a in notes if a["category"] == "PUBLICATION_VERIFIED" for d in a["recordDigests"]}
        scored = {(o["recordDigest"], o["horizon"]) for o in outs if o["status"] != "PENDING"}
        if not all(r["digest"] in verified for r in recs):
            st["stage"] = "AWAITING_PUBLICATION_VERIFICATION"
        elif all((r["digest"], h) in scored for r in recs for h in (126, 252)):
            st["stage"] = "EVALUATED"
        else:
            st["stage"] = "PUBLISHED_AWAITING_HORIZONS"
    return st


def all_cohorts() -> list[str]:
    months = set(LEGACY) | {p.name for p in P.COHORTS.glob("*") if p.is_dir()}
    months |= {r["cohort"] for r in L.read(LEDGER) if r.get("cohort")}
    return sorted(months)


# ----------------------------------------------------------------------------- evaluate
def cmd_evaluate(as_of: str, fetch: bool) -> list[dict]:
    import evaluate as EV
    rows = L.read(LEDGER)
    tickers = sorted({t for r in rows if r.get("schema") in L.RECORD_SCHEMAS for t in r["weights"]})
    start = min((r["plannedExecution"] for r in rows if r.get("schema") in L.RECORD_SCHEMAS), default=as_of)
    store = HERE / "evaluations" / as_of / "prices"
    if fetch:
        EV.fetch_prices(store, tickers, start)
    prices = EV.load_store(store) if (store / "manifest.json").exists() else {}
    observed = f"{as_of}T23:59:59Z" if len(as_of) == 10 else as_of
    outs = []
    for mult in (1.0, 2.0):  # base costs and the 2x stress, both written
        batch = EV.outcomes(rows, prices, observed, cost_mult=mult)
        for o in batch:
            if o["status"] != "PENDING":
                L.append(LEDGER, o)
        outs += batch
    return outs


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status")
    s.add_argument("--month")
    s = sub.add_parser("packet")
    s.add_argument("--month", required=True)
    s.add_argument("--signal-commit", required=True)
    s.add_argument("--fetch", action="store_true")
    for name in ("review-template", "commit-review", "check-review"):
        s = sub.add_parser(name)
        s.add_argument("--month", required=True)
        s.add_argument("--reviewer", required=True)
    s = sub.add_parser("decide")
    s.add_argument("--month", required=True)
    s = sub.add_parser("verify-publication")
    s.add_argument("--month", required=True)
    s = sub.add_parser("annotate")
    s.add_argument("--month", required=True)
    s.add_argument("--category", required=True, choices=sorted(L.ANNOTATION_CATEGORIES))
    s.add_argument("--paths", default="B2")
    s.add_argument("--regions", default="KR,US")
    s.add_argument("--detail", required=True)
    s.add_argument("--evidence")
    s = sub.add_parser("evaluate")
    s.add_argument("--as-of", default=dt.date.today().isoformat())
    s.add_argument("--fetch", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "status":
        res = [cohort_status(m) for m in ([a.month] if a.month else all_cohorts())]
    elif a.cmd == "packet":
        res = cmd_packet(a.month, a.signal_commit, a.fetch)
    elif a.cmd == "review-template":
        res = rel(cmd_review_template(a.month, a.reviewer))
    elif a.cmd == "commit-review":
        res = rel(cmd_commit_review(a.month, a.reviewer))
    elif a.cmd == "check-review":
        res = cmd_check_review(a.month, a.reviewer)
    elif a.cmd == "decide":
        res = [(r["region"], r["path"], r.get("reviewer"), r["weights"], r["digest"][:12]) for r in cmd_decide(a.month)]
    elif a.cmd == "verify-publication":
        res = [(x["category"], x["detail"]) for x in cmd_verify_publication(a.month)]
    elif a.cmd == "annotate":
        res = cmd_annotate(a.month, a.category, a.paths.split(","), a.regions.split(","), a.detail, a.evidence)["digest"]
    else:
        res = [(o["cohort"], o["region"], o["path"], o["horizon"], o["status"], o.get("horizonEndSession"), o.get("excessAfterCostPct"))
               for o in cmd_evaluate(a.as_of, a.fetch)]
    print(json.dumps(res, indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
