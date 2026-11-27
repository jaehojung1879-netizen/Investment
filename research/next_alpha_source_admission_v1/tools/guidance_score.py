"""Score an extractor against the frozen gold set. Only blocks inside the frozen annotation universe count.

Usage: guidance_score.py dev|test [v1|v2] [--errors]"""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
S = "/tmp/claude-0/-home-user-Investment/f1fc5aca-e728-512d-8b45-cb00932dc1ea/scratchpad"
G = Path(__file__).parent.parent / "gold"
TOL = 0.005


def close(a, b):
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= TOL * max(abs(b), 1e-9) + 1e-9


def match(p, g, relaxed=False):
    return (p["target"] == g["target"] and p["metric"] == g["metric"] and p["unit"] == g["unit"]
            and (relaxed or p["basis"] == g["basis"]) and close(p["low"], g["low"]) and close(p["high"], g["high"]))


def load_gold(split):
    rows = list(csv.DictReader(open(G / f"gold-{split}.csv")))
    for r in rows:
        r["low"] = float(r["low"])
        r["high"] = float(r["high"]) if r["high"] else None
    return rows


def v1_predict(raw):
    """#383 v1 linker tuples (full-year only) mapped into the v2 schema for a like-for-like baseline."""
    import guidance_link as L
    out = []
    for t in L.tuples(raw):
        unit = "USD_per_share" if t["unit"] == "USD_per_share" else "USD_million"
        sc = 1000.0 if t["unit"] == "USD_billion" else 1.0
        lo, hi = float(t["low"]) * sc, float(t["high"]) * sc
        out.append({"block": None, "target": t["target"], "metric": t["metric"], "basis": t["basis"],
                    "unit": unit, "low": lo, "high": hi, "kind": "CURRENT"})
    return out


def score(split, version="v2", show=False):
    import importlib
    E = importlib.import_module("guidance_extract_v2" if version == "v2frozen" else "guidance_extract")
    docs = [d for d in json.load(open(G / "gold-docs.json")) if d["split"] == split]
    uni = json.load(open(G / "annotation-universe.json"))["universe"]
    gold = load_gold(split)
    res = {}
    errs = []
    for relaxed in (False, True):
        tp = fp = fn = leak = 0
        ptp = pfp = pfn = 0
        for d in docs:
            raw = open(f"{S}/{d['dir']}/raw/{d['sha256']}", "rb").read()
            preds = v1_predict(raw) if version == "v1" else E.extract(raw)
            allowed = set(uni[d["accession"]])
            preds = [p for p in preds if p["block"] is None or p["block"] in allowed]
            gd = [g for g in gold if g["accession"] == d["accession"]]
            for kind in ("CURRENT", "PRIOR"):
                gk = [g for g in gd if g["kind"] == kind]
                pk = [p for p in preds if p["kind"] == kind]
                used = set()
                hit = 0
                for p in pk:
                    j = next((j for j, g in enumerate(gk) if j not in used and match(p, g, relaxed)), None)
                    if j is None:
                        if kind == "CURRENT":
                            fp += 1
                            if any(match(p, g, relaxed) for g in gd if g["kind"] == "PRIOR"):
                                leak += 1
                            if show and not relaxed:
                                errs.append(("FP", d["ticker"], d["filingDate"], p))
                        else:
                            pfp += 1
                    else:
                        used.add(j)
                        hit += 1
                miss = [g for j, g in enumerate(gk) if j not in used]
                if kind == "CURRENT":
                    tp += hit
                    fn += len(miss)
                    if show and not relaxed:
                        errs += [("FN", d["ticker"], d["filingDate"], g) for g in miss]
                else:
                    ptp += hit
                    pfn += len(miss)
        P = tp / (tp + fp) if tp + fp else 0.0
        R = tp / (tp + fn) if tp + fn else 0.0
        F = 2 * P * R / (P + R) if P + R else 0.0
        res["relaxed_basis" if relaxed else "strict"] = {
            "tp": tp, "fp": fp, "fn": fn, "precision": round(P, 3), "recall": round(R, 3), "f1": round(F, 3),
            "priorLeakedAsCurrent": leak, "prior": {"tp": ptp, "fp": pfp, "fn": pfn}}
    return res, errs


if __name__ == "__main__":
    split = sys.argv[1]
    ver = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else "v2"
    r, e = score(split, ver, "--errors" in sys.argv)
    print(json.dumps(r))
    for x in e:
        p = x[3]
        print(x[0], x[1], x[2], p["target"], p["metric"], p["basis"], p["unit"], p["low"], p["high"], p.get("block", ""))
