import json, sys
sys.path.insert(0, '.'); import doc_blocks as B
S = '/tmp/claude-0/-home-user-Investment/f1fc5aca-e728-512d-8b45-cb00932dc1ea/scratchpad'
docs = json.load(open('../gold/gold-docs.json'))
sel = [d for d in docs if d['split'] == sys.argv[1]][int(sys.argv[2]):int(sys.argv[3])]
for d in sel:
    bl, c = B.candidates(open(f"{S}/{d['dir']}/raw/{d['sha256']}", 'rb').read())
    title = next((v for k, v in bl[:15] if len(v) > 30), '')[:160]
    print(f"\n### {d['ticker']} {d['filingDate']} {d['accession']} nCand={len(c)} | {title}")
    for i, k, v in c[:45]:
        print(f"[{i}{'R' if k == 'row' else ''}] {v[:420]}")
