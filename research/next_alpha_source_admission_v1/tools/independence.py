"""Overlap between the current-quarter surprise (actual vs the issuer's own prior guide) and the change in
forward guidance announced at the same time. Actuals are SEC XBRL 3-month revenue; no prices are read."""
import json, math, statistics as st, sys
from datetime import date, datetime
S = "/tmp/claude-0/-home-user-Investment/f1fc5aca-e728-512d-8b45-cb00932dc1ea/scratchpad"
facts = json.load(open(f"{S}/xbrl/revenue-q.json"))["facts"]


def rank(x):
    o = sorted(range(len(x)), key=lambda i: x[i]); r = [0.0] * len(x)
    for k, i in enumerate(o): r[i] = k
    return r


def spearman(a, b):
    ra, rb = rank(a), rank(b)
    ma, mb = st.mean(ra), st.mean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    return num / math.sqrt(sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb))


def events(d):
    obs = json.load(open(f"{S}/{d}/linked_v2.json"))["obs"]
    rel = {}
    for o in obs:
        if o["metric"] == "revenue" and o["unit"] == "USD_million" and o["target"].startswith("Q"):
            rel.setdefault((o["cik"], o["accepted_at"]), []).append(o)
    fy = {}
    for o in obs:
        if o["metric"] == "revenue" and o["target"].startswith("FY"):
            fy.setdefault(o["cik"], []).append(o)
    out = []
    for cik in {k[0] for k in rel}:
        seq = sorted((k[1], v) for k, v in rel.items() if k[0] == cik)
        q = facts.get(cik, {})
        for (t0, g0), (t1, g1) in zip(seq, seq[1:]):
            if len(g0) != 1 or len(g1) != 1:
                continue
            d0, d1 = datetime.fromisoformat(t0).date(), datetime.fromisoformat(t1).date()
            if not 60 <= (d1 - d0).days <= 120:
                continue
            ends = [e for e in q if d0 < date.fromisoformat(e) < d1]
            if len(ends) != 1:
                continue
            actual = q[ends[0]][0]
            m0 = (float(g0[0]["low"]) + float(g0[0]["high"])) / 2
            m1 = (float(g1[0]["low"]) + float(g1[0]["high"])) / 2
            if min(actual, m0, m1) <= 0 or not 0.5 < actual / m0 < 2:
                continue
            fyrev = None
            for a, b in ((x, y) for x in fy.get(cik, []) for y in fy.get(cik, [])):
                if a["accepted_at"] == t0 and b["accepted_at"] == t1 and a["target"] == b["target"] and a["basis"] == b["basis"]:
                    fyrev = ((float(b["low"]) + float(b["high"])) - (float(a["low"]) + float(a["high"]))) / (float(a["low"]) + float(a["high"]))
            out.append({"cik": cik, "issuer": g1[0]["issuer"], "accepted_at": t1, "surprise": actual / m0 - 1,
                        "fwdGuideChange": m1 / actual - 1, "fyRevision": fyrev})
    return out


if __name__ == "__main__":
    allev = []
    for d in sys.argv[1:]:
        ev = events(d); allev += ev
    s = [e["surprise"] for e in allev]; f = [e["fwdGuideChange"] for e in allev]
    n = len(allev)
    agree = sum((a > 0) == (b > 0) for a, b in zip(s, f))
    # residual share: 1 - R^2 of OLS f ~ s
    ms, mf = st.mean(s), st.mean(f)
    beta = sum((a - ms) * (b - mf) for a, b in zip(s, f)) / sum((a - ms) ** 2 for a in s)
    resid = [b - mf - beta * (a - ms) for a, b in zip(s, f)]
    r2 = 1 - sum(x * x for x in resid) / sum((b - mf) ** 2 for b in f)
    fyp = [(e["surprise"], e["fyRevision"]) for e in allev if e["fyRevision"] is not None]
    res = {"events": n, "issuers": len({e["cik"] for e in allev}), "quarters": len({e["accepted_at"][:7] for e in allev}),
           "spearman_surprise_vs_nextQGuideChange": round(spearman(s, f), 3), "signAgreement": round(agree / n, 3),
           "r2_nextQGuideChange_on_surprise": round(r2, 3), "slope": round(beta, 3),
           "medianAbsSurprisePct": round(100 * st.median(abs(x) for x in s), 2), "medianAbsNextQChangePct": round(100 * st.median(abs(x) for x in f), 2),
           "fyRevisionPairs": len(fyp)}
    if len(fyp) >= 5:
        res["spearman_surprise_vs_fyRevision"] = round(spearman([a for a, _ in fyp], [b for _, b in fyp]), 3)
        res["fySignAgreement"] = round(sum((a > 0) == (b > 0) for a, b in fyp if b != 0) / max(1, sum(b != 0 for _, b in fyp)), 3)
    print(json.dumps(res))
    json.dump(allev, open(f"{S}/independence-events.json", "w"))
