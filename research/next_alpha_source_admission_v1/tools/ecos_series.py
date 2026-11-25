import json, sys, time, hashlib, urllib.request
def get(u):
    return urllib.request.urlopen(u, timeout=20).read()
out = {}; pages = []
for key, path in [("price_usd", "402Y014/M/201301/202610/30911AA/D"), ("value", "403Y001/M/201301/202610/30911AA"), ("volume", "403Y002/M/201301/202610/30911AA")]:
    base = "https://ecos.bok.or.kr/api/StatisticSearch/sample/json/kr"
    n = json.loads(get(f"{base}/1/1/{path}"))["StatisticSearch"]["list_total_count"]; rows = []
    for s in range(1, n + 1, 10):
        raw = get(f"{base}/{s}/{s+9}/{path}"); pages.append(hashlib.sha256(raw).hexdigest())
        rows += json.loads(raw)["StatisticSearch"]["row"]; time.sleep(0.15)
    out[key] = {r["TIME"]: float(r["DATA_VALUE"]) for r in rows}
    print(key, n, len(out[key]))
json.dump({"retrieved": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "series": out, "pageSha256": pages}, open(sys.argv[1], "w"))
