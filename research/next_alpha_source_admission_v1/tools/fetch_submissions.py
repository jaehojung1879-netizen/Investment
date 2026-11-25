"""Fetch SEC submissions JSON (root + declared historical pages) for a CIK cohort into a ZIP whose
basenames equal SEC's bulk submissions.zip, so #375 bulk_402.extract runs unmodified."""
import csv, gzip, hashlib, json, sys, time, zipfile, urllib.request
UA = "Investment-research source-admission pilot (non-commercial) research-client@example.org"
def get(url, tries=4):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception as e:
            err = e; time.sleep(2 ** k)
    raise err
catalog, out = sys.argv[1], sys.argv[2]
with gzip.open(catalog, "rt") as f:
    ciks = sorted({f"{int(r['cik']):010d}" for r in csv.DictReader(f)})
log = []
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for i, cik in enumerate(ciks):
        name = f"CIK{cik}.json"
        raw = get(f"https://data.sec.gov/submissions/{name}"); time.sleep(0.13)
        z.writestr(name, raw)
        log.append({"name": name, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
        for d in json.loads(raw)["filings"]["files"]:
            p = d["name"]
            raw2 = get(f"https://data.sec.gov/submissions/{p}"); time.sleep(0.13)
            z.writestr(p, raw2)
            log.append({"name": p, "sha256": hashlib.sha256(raw2).hexdigest(), "bytes": len(raw2)})
        if i % 100 == 0: print(i, len(log), flush=True)
json.dump({"retrievedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "userAgent": UA, "pages": log},
          open(out + ".manifest.json", "w"), indent=1)
print("done", len(ciks), len(log))
