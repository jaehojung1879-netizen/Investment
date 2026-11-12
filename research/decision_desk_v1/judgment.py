"""Turn a cohort's evidence pack + AI review into B0/B1/B2 dry-run records.

The AI review supplies only labels and interpretation. Every observed number is
copied here from the evidence pack, so the record cannot quote a figure the
evidence did not contain. The frozen gates and selection rule are enforced in code:
a review that selects a gated name, or a name without enough supporting layers, is
refused rather than corrected.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

import pandas as pd

import ledger as L

HERE = Path(__file__).resolve().parent
PROTOCOL = json.loads((HERE / "protocol.json").read_text())
LAYERS = ["market", "industry", "company", "price", "macro", "research", "risk"]
LABELS = {"SUPPORTS", "NEUTRAL", "CONTRADICTS"}
CALENDARS = {"KR": "XKRX", "US": "XNYS"}
BENCH = {"KR": "069500.KS", "US": "SPY"}
MODEL_VERSION = {"B0": "etf-baseline-v1", "B1": "weekly-passive-first-v1 (production receipt copy)",
                 "B2": "decision-desk-v1-ai-synthesis (Claude, structured gates)"}


class ReviewError(ValueError):
    pass


def sha256_file(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def execution_after(region: str, published_at: str) -> tuple[str, str]:
    """First regional session whose close is after publishedAt; returns (date, close UTC)."""
    import exchange_calendars as xc
    cal = xc.get_calendar(CALENDARS[region])
    t = pd.Timestamp(published_at)
    for s in cal.sessions_in_range(t.normalize().tz_localize(None) - pd.Timedelta(days=1), t.normalize().tz_localize(None) + pd.Timedelta(days=10)):
        close = cal.session_close(s)
        if close > t:
            return str(pd.Timestamp(s).date()), close.strftime("%Y-%m-%dT%H:%M:%SZ")
    raise ReviewError("NO_SESSION_FOUND")


_NUM = __import__("re").compile(r"\d+(?:[.,]\d+)*")
_STRUCTURAL = {"generatedAt", "evidencePackSha256", "packetSha256", "cohort", "reviewer", "schema", "commitment", "ticker"}


def _numbers_in(obj, out: set) -> set:
    if isinstance(obj, dict):
        for v in obj.values():
            _numbers_in(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _numbers_in(v, out)
    elif isinstance(obj, bool) or obj is None:
        pass
    elif isinstance(obj, (int, float)):
        for d in (0, 1, 2, 3, 4):
            out.add(f"{round(float(obj), d):.{d}f}".rstrip("0").rstrip(".") if d else str(int(round(float(obj)))))
        out.add(str(obj))
    else:
        for tok in _NUM.findall(str(obj)):
            out.add(tok.replace(",", ""))
    return out


def check_prose_numbers(review: dict, pack: dict) -> None:
    """Every number written in a v2 review's free text must appear in the evidence packet (#335 G4).

    A forecast such as "expected return 999%" quotes a number no evidence contains and is refused.
    Rounding of a packet value (e.g. 28 for 28.18) is accepted; anything else is not."""
    known = _numbers_in(pack, set()) | {"6", "12", "126", "252"}  # the protocol's own horizons

    def walk(obj, key=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k not in _STRUCTURAL:
                    walk(v, k)
        elif isinstance(obj, list):
            for v in obj:
                walk(v, key)
        elif isinstance(obj, str):
            for tok in _NUM.findall(obj):
                t = tok.replace(",", "")
                if t not in known and not (len(t) == 4 and t.startswith("20")):  # a year is a date, not a claim
                    raise ReviewError(f"UNSOURCED_NUMBER_IN_PROSE {key}: {tok!r}")
    walk(review.get("regions", {}))


def check_review(review: dict, pack: dict) -> dict:
    """Enforce the frozen B2 rules; returns {region: [selected tickers]}."""
    if review["evidencePackSha256"] != pack["_sha256"]:
        raise ReviewError("REVIEW_CITES_A_DIFFERENT_EVIDENCE_PACK")
    hits = L._forbidden(review)
    if hits:
        raise ReviewError(f"FORBIDDEN_NUMERIC_CLAIM {hits}")
    port = PROTOCOL["portfolio"]
    out = {}
    for region, rv in review["regions"].items():
        cands = {c["ticker"]: c for c in pack["regions"][region]["candidates"]}
        cap = 2 if rv["marketLabel"] == "CONTRADICTS" else port["maxNames"]
        selected = []
        for n in rv["names"]:
            c = cands.get(n["ticker"])
            if c is None:
                raise ReviewError(f"NAME_NOT_IN_EVIDENCE {n['ticker']}")
            if set(n["layers"]) != set(LAYERS) or any(v[0] not in LABELS for v in n["layers"].values()):
                raise ReviewError(f"LAYER_SET_INCOMPLETE {n['ticker']}")
            if n["decision"] != "SELECT":
                continue
            if c["gatesFailed"]:
                raise ReviewError(f"SELECTED_A_GATED_NAME {n['ticker']} {c['gatesFailed']}")
            supports = sum(v[0] == "SUPPORTS" for v in n["layers"].values())
            vetoes = [k for k in ("company", "price", "risk") if n["layers"][k][0] == "CONTRADICTS"]
            if supports < 3 or vetoes:
                raise ReviewError(f"SELECTION_RULE_NOT_MET {n['ticker']} supports={supports} vetoes={vetoes}")
            for f in ("reasons", "thesis6m", "thesis12m", "catalysts", "risks", "invalidationConditions", "notVerified", "whyVersusBenchmark"):
                if not n.get(f):
                    raise ReviewError(f"MISSING_OUTPUT_FIELD {n['ticker']} {f}")
            if len(n["reasons"]) > 3:
                raise ReviewError("MORE_THAN_THREE_REASONS")
            selected.append(n["ticker"])
        sectors = pd.Series([cands[t].get("sector") for t in selected]).value_counts()
        if len(selected) > cap or (len(sectors) and sectors.max() > port["maxNamesPerSector"]):
            raise ReviewError(f"CONCENTRATION_OR_CAP {region}")
        if sorted(selected) != sorted(rv["regionDecision"]["selected"]):
            raise ReviewError(f"REGION_DECISION_DISAGREES {region}")
        out[region] = selected
    return out


OBSERVED_FIELDS = ["alphaPercentile", "entryState", "sector", "factorPercentiles", "priceMomentum", "liquidityRisk",
                   "valuationProfitability", "coverage", "gatesFailed"]


def build_records(pack: dict, review: dict, published_at: str, source_hashes: dict) -> list[dict]:
    selected = check_review(review, pack)
    per = PROTOCOL["portfolio"]["perNameWeight"]
    records = []
    for region in sorted(pack["regions"]):
        ev = pack["regions"][region]
        bench = BENCH[region]
        exec_date, exec_close = execution_after(region, published_at)
        common = {"schema": L.SCHEMA, "region": region, "cohort": pack["cohort"], "signalAsOf": ev["asOfDate"],
                  "informationCutoff": ev["asOfDate"], "generatedAt": review["generatedAt"], "publishedAt": published_at,
                  "sourceHashes": source_hashes, "benchmark": bench, "plannedExecution": exec_date,
                  "plannedExecutionCloseUtc": exec_close, "costs": ev["costs"], "horizon126": None, "horizon252": None,
                  "subsequentReturns": None, "status": "DRY_RUN_NOT_ACTIVATED", "missingDataReason": None}
        records.append({**common, "path": "B0", "modelVersion": MODEL_VERSION["B0"], "selectedTickers": [],
                        "weights": {bench: 1.0}, "investmentThesis": "Regional ETF baseline: the passive default every path is judged against.",
                        "invalidationConditions": []})
        b1w = ev["productionWeights"]
        records.append({**common, "path": "B1", "modelVersion": MODEL_VERSION["B1"],
                        "selectedTickers": sorted(t for t in b1w if t != bench), "weights": b1w,
                        "investmentThesis": f"Production receipt {ev['receiptId']} ({ev['productionStatus']}; {ev['noTradeReason']}). Copied, not re-decided.",
                        "invalidationConditions": [], "b1ReceiptDigest": ev["receiptDigest"]})
        rv = review["regions"][region]
        names = {n["ticker"]: n for n in rv["names"]}
        cands = {c["ticker"]: c for c in ev["candidates"]}
        sel = selected[region]
        weights = {t: per for t in sel}
        weights[bench] = round(1.0 - per * len(sel), 10)
        picks = []
        for t in sel:
            n = names[t]
            picks.append({"ticker": t, "name": cands[t].get("name"), "observed": {k: cands[t].get(k) for k in OBSERVED_FIELDS},
                          "layers": {k: {"label": v[0], "interpretation": v[1]} for k, v in n["layers"].items()},
                          **{f: n[f] for f in ("reasons", "thesis6m", "thesis12m", "catalysts", "risks", "notVerified", "whyVersusBenchmark")},
                          "researchWeight": per})
        rejected = [{"ticker": n["ticker"], "decision": n["decision"], "reason": n.get("rejectionReason"),
                     "layers": {k: v[0] for k, v in n["layers"].items()}} for n in rv["names"] if n["decision"] != "SELECT"]
        gated = [{"ticker": c["ticker"], "name": c.get("name"), "gatesFailed": c["gatesFailed"]} for c in ev["candidates"] if c["gatesFailed"]]
        records.append({**common, "path": "B2", "modelVersion": MODEL_VERSION["B2"], "selectedTickers": sel, "weights": weights,
                        "investmentThesis": {"market": {"label": rv["marketLabel"], "interpretation": rv["marketInterpretation"], "observed": ev["market"]},
                                             "macro": {"label": rv["macroLabel"], "interpretation": rv["macroInterpretation"], "observed": ev["macro"]},
                                             "picks": picks, "reviewedRejected": rejected, "gatedOut": gated,
                                             "zeroSelectionReason": rv["regionDecision"]["zeroSelectionReason"],
                                             "knowledgeLimit": review["knowledgeLimit"]},
                        "invalidationConditions": {t: names[t]["invalidationConditions"] for t in sel}})
    return records


def main(cohort: str, published_at: str | None = None, write: bool = True) -> list[dict]:
    pack_path = HERE / "inputs" / cohort / "evidence-pack.json"
    review_path = HERE / "ai-reviews" / f"{cohort}.json"
    pack = json.loads(pack_path.read_text())
    pack["_sha256"] = sha256_file(pack_path)
    review = json.loads(review_path.read_text())
    published_at = published_at or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    hashes = {"protocol": sha256_file(HERE / "protocol.json"), "evidencePack": pack["_sha256"],
              "aiReview": sha256_file(review_path), "marketManifest": pack["marketManifestSha256"],
              "productionReceipts": {"signalHistoryCommit": pack["signalHistoryCommit"], "blob": pack["receiptsBlob"],
                                     "sha256": pack["receiptsSha256"]}}
    records = build_records(pack, review, published_at, hashes)
    if write:
        path = L.DRY_RUN_DIR / "ledger.jsonl"
        records = [L.append(path, r) for r in records]
    return records


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--cohort", required=True)
    ap.add_argument("--published-at")
    a = ap.parse_args()
    for r in main(a.cohort, a.published_at):
        print(r["region"], r["path"], r["weights"], r["plannedExecution"], r["digest"][:12])
