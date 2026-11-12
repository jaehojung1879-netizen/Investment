"""Pinned Git inspection and merge-tree simulation; no branch, index or worktree merge.

commit-tree creates unreachable audit-only objects to test cumulative merge parents.
It never changes a ref. No strategy, label, model or backtest is executed.
"""
from pathlib import Path
import json
import os
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / 'evidence'
MAIN = '37f8cbf6b1c066f6b3c65235953648d17ebf2f69'
HEADS = {
    '321': 'cd2892eb6d6623c2527eeda690959d18839acc4d',
    '328': '3b3edb13164ad38f8393c87432bb166f75068291',
    '329': '0a1f494171576af6928fe531145a8c8f050253fd',
    '330': '8657acd5dd840617fc25a6a0cce467294edf72bf',
    '331': 'd2cd9781627773381b63cd9f2db13b369a1dd31e',
    '332': '0f39c2fef93a9cf924f45ae87662de41090f2528',
}
BASES = {**{k: MAIN for k in ('321', '329', '331')},
         '328': '1e0289d09ba30bf2e26ec9cfb7e118f33a6a8a87',
         '330': '17404f86535f0b8a8992da451dc7667f00539dd6',
         '332': HEADS['330']}

def git(*args, check=True, input=None):
    env = dict(os.environ)
    if args and args[0] == 'commit-tree':
        env.update({'GIT_AUTHOR_NAME': 'Integration Audit', 'GIT_AUTHOR_EMAIL': 'audit@example.invalid',
                    'GIT_COMMITTER_NAME': 'Integration Audit', 'GIT_COMMITTER_EMAIL': 'audit@example.invalid',
                    'GIT_AUTHOR_DATE': '2026-11-11T00:00:00Z', 'GIT_COMMITTER_DATE': '2026-11-11T00:00:00Z'})
    return subprocess.run(['git', *args], cwd=ROOT, text=True, env=env,
                          input=input, capture_output=True, check=check)

def changed(a, b):
    return git('diff', '--name-only', a, b).stdout.splitlines()

def ancestor(a, b):
    return git('merge-base', '--is-ancestor', a, b, check=False).returncode == 0

patches = {k: changed(BASES[k], v) for k, v in HEADS.items()}
matrix = {a: {b: ancestor(HEADS[a], HEADS[b]) for b in HEADS} for a in HEADS}
overlap = [{ 'a': a, 'b': b, 'paths': sorted(set(patches[a]) & set(patches[b]))}
           for a in HEADS for b in HEADS if a < b]
old = BASES['330']
subtree = 'research/ml_strategy_tournament_v1'
old_tree = git('rev-parse', old + ':' + subtree).stdout.strip()
new_tree = git('rev-parse', HEADS['329'] + ':' + subtree).stdout.strip()
simulations = []
left = MAIN
for key in ('321', '329', '330', '332', '331', '328'):
    right = HEADS[key]
    result = git('merge-tree', '--write-tree', '--name-only', '--messages', left, right, check=False)
    lines = result.stdout.splitlines()
    row = {'nextPr': key, 'left': left, 'right': right, 'exitCode': result.returncode,
           'clean': result.returncode == 0, 'tree': lines[0] if lines else None,
           'messages': lines[1:], 'stderr': result.stderr}
    simulations.append(row)
    if result.returncode:
        break
    left = git('commit-tree', row['tree'], '-p', left, '-p', right,
               input='UNREFERENCED AUDIT SIMULATION ONLY\n').stdout.strip()
output = {
    'main': MAIN, 'heads': HEADS, 'bases': BASES,
    'prChanges': patches, 'prChangeCounts': {k: len(v) for k, v in patches.items()},
    'mainChangeCounts': {k: len(changed(MAIN, h)) for k, h in HEADS.items()},
    'ancestry': matrix, 'patchPathOverlaps': overlap,
    'old329Head': old, 'oldV1Tree': old_tree, 'newV1Tree': new_tree,
    'v1SubtreeUnchanged': old_tree == new_tree,
    'additionsSinceOld329': changed(old, HEADS['329']),
    'maintenanceParent': '23522002dcd2d9e0e16dfb9d325a235aef664f0c',
    'maintenanceParentIsAncestorOf321': ancestor('23522002dcd2d9e0e16dfb9d325a235aef664f0c', HEADS['321']),
    'mergeTreeSimulations': simulations,
    'scope': 'TEXT_TREE_COMPATIBILITY_ONLY_NOT_COMBINED_CI_OR_MERGE_AUTHORIZATION',
    'anyExistingRefUpdated': False,
}
OUT.mkdir(parents=True, exist_ok=True)
(OUT / 'lineage.json').write_text(json.dumps(output, indent=2) + '\n')
print(json.dumps({k: output[k] for k in ('prChangeCounts', 'mainChangeCounts', 'v1SubtreeUnchanged')}, indent=2))
print('Simulated clean:', [(r['nextPr'], r['clean']) for r in simulations])
