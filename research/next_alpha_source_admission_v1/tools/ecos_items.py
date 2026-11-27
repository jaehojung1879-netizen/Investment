import json, sys, time, urllib.request
def get(u):
    return json.loads(urllib.request.urlopen(u, timeout=20).read())
out = {}
for code in sys.argv[2:]:
    n = get(f"https://ecos.bok.or.kr/api/StatisticItemList/sample/json/kr/1/1/{code}")["StatisticItemList"]["list_total_count"]
    rows = []
    for s in range(1, n + 1, 10):
        rows += get(f"https://ecos.bok.or.kr/api/StatisticItemList/sample/json/kr/{s}/{s+9}/{code}")["StatisticItemList"]["row"]; time.sleep(0.2)
    out[code] = [r for r in rows if any(k in r["ITEM_NAME"] for k in ("D램", "DRAM", "플래시", "반도체", "메모리", "집적회로"))]
json.dump(out, open(sys.argv[1], "w"), ensure_ascii=False, indent=1)
for c, v in out.items():
    for r in v: print(c, r["STAT_NAME"], r["ITEM_CODE"], r["ITEM_NAME"], r["CYCLE"], r["START_TIME"], r["END_TIME"])
