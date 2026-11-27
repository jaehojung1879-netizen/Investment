import json, hashlib, sys, time, urllib.request
UA = "Investment-research source-admission pilot (non-commercial) research-client@example.org"
d = json.load(open(sys.argv[1])); out = sys.argv[2]; log = []
for r in d["records"]:
    url = f"https://www.sec.gov/Archives/edgar/data/{int(r['cik'])}/{r['accessionNumber'].replace('-','')}/{r['primaryDocument']}"
    try:
        raw = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30).read()
        h = hashlib.sha256(raw).hexdigest(); open(f"{out}/{h}", "wb").write(raw)
        log.append({"accession": r["accessionNumber"], "cik": r["cik"], "url": url, "sha256": h, "bytes": len(raw)})
    except Exception as e:
        log.append({"accession": r["accessionNumber"], "cik": r["cik"], "url": url, "error": type(e).__name__})
    time.sleep(0.25)
json.dump(log, open(out + "/../402-docs.json", "w"), indent=1); print("done", len(log), sum("sha256" in x for x in log))
