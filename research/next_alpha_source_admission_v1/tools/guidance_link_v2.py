"""Run a frozen extractor over a release panel and link same issuer/target/metric/basis/unit with #372 revisions()."""
import collections
import csv
import gzip
import importlib
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
S = "/tmp/claude-0/-home-user-Investment/f1fc5aca-e728-512d-8b45-cb00932dc1ea/scratchpad"


def forms():
    rows = csv.DictReader(gzip.open(f"{S}/us-8k-item202.csv.gz", "rt"))
    return {r["accession"]: r["form"] for r in rows}


def run(d, module="guidance_extract_v2"):
    E = importlib.import_module(module)
    I = importlib.import_module("inspect_guidance_372")
    form = forms()
    rows = [r for r in json.load(open(f"{S}/{d}/sample.json")) if r.get("status") == "FETCHED"]
    obs, conflicts, per_doc = [], 0, {}
    for r in rows:
        acc = datetime.fromisoformat(r["acceptanceDateTime"].replace("Z", "+00:00")).isoformat()
        tup = [t for t in E.extract(open(f"{S}/{d}/raw/{r['sha256']}", "rb").read()) if t["kind"] == "CURRENT"]
        by = collections.defaultdict(set)
        for t in tup:
            by[(t["target"], t["metric"], t["basis"], t["unit"])].add((round(t["low"], 6), None if t["high"] is None else round(t["high"], 6)))
        per_doc[r["accession"]] = len(by)
        for (tg, m, b, u), vals in by.items():
            if len(vals) > 1:
                conflicts += 1          # two different values for one key in one release: unresolvable, dropped
                continue
            lo, hi = next(iter(vals))
            if hi is None:
                continue                # open-ended "+" values have no midpoint
            obs.append({"cik": str(r["cik"]), "issuer": r["ticker"], "accession": r["accession"], "accepted_at": acc,
                        "target": tg, "metric": m, "basis": b, "unit": u, "low": str(lo), "high": str(hi), "status": "NUMERIC",
                        "form": form.get(r["accession"], "?")})
    obs = [o for o in obs if o["form"] == "8-K"]   # an 8-K/A restates; it never creates a second observation
    rev = I.revisions(obs)
    return rows, obs, rev, conflicts, per_doc


def classify(rev, obs):
    by_acc = {(o["accession"], o["target"], o["metric"], o["basis"], o["unit"]): o for o in obs}
    out = []
    for x in rev:
        if not x["prior_accession"]:
            continue
        cur = by_acc[(x["accession"], x["target"], x["metric"], x["basis"], x["unit"])]
        pri = by_acc[(x["prior_accession"], x["target"], x["metric"], x["basis"], x["unit"])]
        dm = float(x["midpoint_change"])
        w0, w1 = float(pri["high"]) - float(pri["low"]), float(cur["high"]) - float(cur["low"])
        cls = "RAISE" if dm > 0 else "LOWER" if dm < 0 else ("NARROW" if w1 < w0 else "WIDEN" if w1 > w0 else "MAINTAIN")
        mid0 = (float(pri["high"]) + float(pri["low"])) / 2
        out.append({**x, "class": cls, "priorMid": mid0, "relChange": dm / abs(mid0) if mid0 else None,
                    "accepted_at": cur["accepted_at"], "prior_accepted_at": pri["accepted_at"]})
    return out


if __name__ == "__main__":
    for d in sys.argv[1:]:
        rows, obs, rev, conf, per_doc = run(d)
        links = classify(rev, obs)
        json.dump({"obs": obs, "links": links}, open(f"{S}/{d}/linked_v2.json", "w"))
        print(d, "releases", len(rows), "releasesWithTuples", sum(v > 0 for v in per_doc.values()), "tuples", len(obs),
              "keysConflictDropped", conf, "issuers", len({o["issuer"] for o in obs}),
              "linked", len(links), "issuersLinked", len({x["issuer"] for x in links}),
              dict(collections.Counter(x["class"] for x in links)), dict(collections.Counter(x["metric"] for x in links)))
