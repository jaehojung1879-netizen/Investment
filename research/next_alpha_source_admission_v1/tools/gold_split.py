"""Deterministic dev/test split for the guidance gold set; split is BY ISSUER so no issuer is in both."""
import hashlib, json, random
S = '/tmp/claude-0/-home-user-Investment/f1fc5aca-e728-512d-8b45-cb00932dc1ea/scratchpad'
def split_of(ticker):
    return "dev" if int(hashlib.sha256(ticker.encode()).hexdigest(), 16) % 2 == 0 else "test"
panel = [r for r in json.load(open(f'{S}/panel/sample.json')) if r.get('status') == 'FETCHED']
strat = [r for r in json.load(open(f'{S}/guid/sample.json')) if r.get('status') == 'FETCHED']
rng = random.Random(20261126); out = []
pticks = sorted({r['ticker'] for r in panel})
for sp in ("dev", "test"):
    ts = [t for t in pticks if split_of(t) == sp]
    for t in rng.sample(ts, 3):
        docs = sorted([r for r in panel if r['ticker'] == t and r['filingDate'][:4] == '2023'], key=lambda r: r['acceptanceDateTime'])[:4]
        out += [{"split": sp, "source": "panel", "dir": "panel", **{k: r[k] for k in ('ticker', 'cik', 'accession', 'filingDate', 'acceptanceDateTime', 'sha256')}} for r in docs]
    pool = [r for r in strat if split_of(r['ticker']) == sp and r['ticker'] not in pticks]
    seen = set(); pick = []
    for r in rng.sample(pool, len(pool)):
        if r['ticker'] in seen: continue
        seen.add(r['ticker']); pick.append(r)
        if len(pick) == 12: break
    out += [{"split": sp, "source": "stratified", "dir": "guid", **{k: r[k] for k in ('ticker', 'cik', 'accession', 'filingDate', 'acceptanceDateTime', 'sha256')}} for r in pick]
json.dump(out, open('../gold/gold-docs.json', 'w'), indent=1)
print(len(out), {sp: sum(o['split'] == sp for o in out) for sp in ('dev', 'test')})
for o in out: print(o['split'], o['source'], o['ticker'], o['filingDate'])
