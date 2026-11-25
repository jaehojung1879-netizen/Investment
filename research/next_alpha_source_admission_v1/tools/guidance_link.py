"""Extract conservative full-year numeric guidance tuples and link same issuer/target/metric/basis/unit
with #372 inspect_guidance.revisions (unmodified). Source-only; no prices."""
import collections
import importlib
import json
import re
import sys
from datetime import datetime
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent)); import guidance_detect as G  # noqa: E402,E702
MET = [("eps", r"\b(eps|earnings per (diluted )?share|per diluted share|diluted earnings per share)\b"),
       ("revenue", r"\b(revenue|revenues|net sales|total sales)\b"),
       ("capex", r"\b(capital expenditures?|capex|capital spending)\b"),
       ("free_cash_flow", r"\bfree cash flow\b"),
       ("operating_income", r"\b(operating income|operating profit|adjusted ebitda|ebitda)\b")]
RNG = re.compile(r"\$\s?(\d[\d,]*\.?\d*)\s*(billion|million)?\s*(?:to|-|–|—)\s*\$?\s?(\d[\d,]*\.?\d*)\s*(billion|million)?", re.I)
TGT = re.compile(r"(?:full[- ]year|fiscal(?: year)?|calendar(?: year)?|FY)\s*'?(20\d\d)|(20\d\d)\s+(?:full[- ]year|fiscal[- ]year|outlook|guidance)", re.I)
def tuples(raw):
    out = []
    for s in G.detect(raw)["examples_all"]:
        mt = TGT.search(s); mets = [m for m, p in MET if re.search(p, s, re.I)]
        rngs = RNG.findall(s)
        if not mt or len(mets) != 1 or len(rngs) != 1: continue
        if re.search(r"\bquarter\b", s, re.I) and not re.search(r"full[- ]year", s, re.I): continue
        if mets[0] == "revenue" and re.search(r"\bexpenses?\b|\bcosts?\b", s, re.I): continue
        lo, u1, hi, u2 = rngs[0]; unit = (u2 or u1 or "").lower()
        if mets[0] == "eps": unit = "USD_per_share"
        elif unit: unit = "USD_" + unit
        else: continue
        lo, hi = float(lo.replace(",", "")), float(hi.replace(",", ""))
        if lo > hi: continue
        basis = "non_GAAP" if re.search(r"non[- ]gaap|adjusted", s, re.I) else ("GAAP" if re.search(r"\bgaap\b|reported", s, re.I) else "unstated")
        out.append({"target": "FY" + (mt.group(1) or mt.group(2)), "metric": mets[0], "basis": basis, "unit": unit, "low": str(lo), "high": str(hi)})
    return out
def run(d):
    rows = json.load(open(f"{d}/sample.json")); obs = []
    for r in rows:
        if r.get("status") != "FETCHED": continue
        acc = datetime.fromisoformat(r["acceptanceDateTime"].replace("Z", "+00:00")).isoformat()
        seen = set()
        for t in tuples(open(f"{d}/raw/{r['sha256']}", "rb").read()):
            k = (t["target"], t["metric"], t["basis"], t["unit"])
            if k in seen: continue   # first statement per filing per key only
            seen.add(k)
            obs.append({"cik": str(r["cik"]), "issuer": r["ticker"], "accession": r["accession"], "accepted_at": acc, "status": "NUMERIC", **t})
    I = importlib.import_module("inspect_guidance_372")  # #372 inspect_guidance.py, fetched with git show (see README)
    rev = I.revisions(obs)
    linked = [x for x in rev if x["prior_accession"]]
    cls = collections.Counter("RAISE" if float(x["midpoint_change"]) > 0 else "LOWER" if float(x["midpoint_change"]) < 0 else "MAINTAIN" for x in linked)
    return {"filings": sum(r.get("status") == "FETCHED" for r in rows), "tuples": len(obs), "issuersWithTuples": len({o["cik"] for o in obs}),
            "keys": len({(o["cik"], o["target"], o["metric"], o["basis"], o["unit"]) for o in obs}), "linkedRevisions": len(linked), "classes": dict(cls),
            "byMetric": dict(collections.Counter(x["metric"] for x in linked)), "issuersWithLinked": len({x["issuer"] for x in linked}),
            "issuerFilingPairs": len({(x["issuer"], x["accession"]) for x in linked}), "obs": obs, "revisions": rev}
if __name__ == "__main__":
    res = run(sys.argv[1]); json.dump(res, open(sys.argv[1] + "/linked.json", "w"), indent=1)
    print({k: v for k, v in res.items() if k not in ("obs", "revisions")})
