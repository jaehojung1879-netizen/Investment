"""Fetch SEC companyfacts for a CIK list and keep 3-month revenue facts (source-only; no prices)."""
import hashlib, json, sys, time, urllib.request
UA = "Investment-research source-admission pilot (non-commercial) research-client@example.org"
CON = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet", "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueGoodsNet"]
out, man = {}, []
for cik in sys.argv[2:]:
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json"
    try:
        raw = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60).read()
    except Exception as e:
        man.append({"cik": cik, "error": type(e).__name__}); continue
    man.append({"cik": cik, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
    facts = json.loads(raw).get("facts", {}).get("us-gaap", {})
    q = {}
    for c in CON:
        for u in facts.get(c, {}).get("units", {}).get("USD", []):
            if "start" not in u: continue
            from datetime import date
            dd = (date.fromisoformat(u["end"]) - date.fromisoformat(u["start"])).days
            if 80 <= dd <= 100:
                q.setdefault(u["end"], (u["val"] / 1e6, c, u["filed"]))
    out[cik] = q
    time.sleep(0.2)
json.dump({"facts": out, "manifest": man}, open(sys.argv[1], "w"))
print(len(out), sum(len(v) for v in out.values()))
