"""Stratified random sample of #354 Item 2.02 accessions; fetch EX-99 press release; detect guidance.
Outcome-blind: reads only SEC filing text. Stores raw bytes outside git, keyed by sha256."""
import csv, gzip, hashlib, json, random, re, sys, time, urllib.request
UA = "Investment-research source-admission pilot (non-commercial) research-client@example.org"
OUT = sys.argv[2]
def get(url):
    for k in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30) as r:
                time.sleep(0.3); return r.read()
        except Exception as e:
            err = e; time.sleep(2 ** k)
    raise err
rows = list(csv.DictReader(gzip.open(sys.argv[1], "rt")))
byacc = {}
for r in rows:
    if r["form"] == "8-K": byacc.setdefault((int(r["cik"]), r["accession"]), r)
years = {}
for k, r in byacc.items(): years.setdefault(r["filingDate"][:4], []).append(k)
rng = random.Random(20261125); sample = []
for y in sorted(years):
    if "2014" <= y <= "2026": sample += rng.sample(sorted(years[y]), min(25, len(years[y])))
print("sample", len(sample), flush=True)
res = []
for cik, acc in sample:
    r = byacc[(cik, acc)]; nd = acc.replace("-", "")
    rec = {"cik": cik, "ticker": r["ticker"], "accession": acc, "filingDate": r["filingDate"], "acceptanceDateTime": r["acceptanceDateTime"]}
    try:
        idx = json.loads(get(f"https://www.sec.gov/Archives/edgar/data/{cik}/{nd}/index.json"))
        names = [i["name"] for i in idx["directory"]["item"]]
        ex = [n for n in names if re.search(r"ex-?99|ex99|exhibit99|dex99", n, re.I) and n.lower().endswith((".htm", ".html", ".txt"))]
        rec["exhibitCandidates"] = len(ex)
        if not ex:
            rec["status"] = "NO_EX99_FOUND"; res.append(rec); continue
        raw = get(f"https://www.sec.gov/Archives/edgar/data/{cik}/{nd}/{sorted(ex)[0]}")
        h = hashlib.sha256(raw).hexdigest(); open(f"{OUT}/raw/{h}", "wb").write(raw)
        rec.update(status="FETCHED", exhibit=sorted(ex)[0], sha256=h, bytes=len(raw))
    except Exception as e:
        rec["status"] = "FETCH_ERROR:" + type(e).__name__
    res.append(rec)
    if len(res) % 50 == 0: print(len(res), flush=True)
json.dump(res, open(f"{OUT}/sample.json", "w"), indent=1)
print("done", len(res))
