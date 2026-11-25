import json, re, sys, time, hashlib, urllib.request, html
UA = "Investment-research source-admission pilot (non-commercial) research-client@example.org"
def get(u):
    r = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=30).read(); time.sleep(0.3); return r
d = sys.argv[1]; rows = json.load(open(f"{d}/sample.json")); n = 0
for r in rows:
    if r.get("status") != "NO_EX99_FOUND": continue
    nd = r["accession"].replace("-", ""); base = f"https://www.sec.gov/Archives/edgar/data/{r['cik']}/{nd}/"
    try:
        idx = get(base + r["accession"] + "-index.htm").decode("utf-8", "replace")
        cand = []
        for tr in re.findall(r"(?is)<tr.*?</tr>", idx):
            cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"(?is)<td.*?</td>", tr)]
            link = re.search(r'href="([^"]+\.(htm|html|txt))"', tr, re.I)
            if link and len(cells) >= 4 and cells[3].upper().startswith("EX-99"):
                cand.append((cells[3], link.group(1).split("/")[-1]))
        if not cand: r["status"] = "NO_EX99_IN_INDEX"; continue
        raw = get(base + sorted(cand)[0][1]); h = hashlib.sha256(raw).hexdigest(); open(f"{d}/raw/{h}", "wb").write(raw)
        r.update(status="FETCHED", exhibit=sorted(cand)[0][1], exhibitType=sorted(cand)[0][0], sha256=h, bytes=len(raw), exhibitResolution="INDEX_HTM"); n += 1
    except Exception as e:
        r["status"] = "REFETCH_ERROR:" + type(e).__name__
json.dump(rows, open(f"{d}/sample.json", "w"), indent=1); print("refetched", n)
