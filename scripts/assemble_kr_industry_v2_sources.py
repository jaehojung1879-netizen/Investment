"""Verify and retain, byte-for-byte, the already-collected v2 Actions artifacts. Collects nothing."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'data/kr-industry-membership-foundation-v2'
PLAN = ROOT / 'research_specs/kr-industry-membership-foundation-v2/classification-chapters.json'
BATCHES = 26


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def copy(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        if dst.read_bytes() != src.read_bytes():
            raise ValueError('RETAINED_OBJECT_DIFFERS:' + str(dst))
        return
    shutil.copyfile(src, dst)


def assemble(downloads, chapters):
    downloads = Path(downloads)
    for n in range(BATCHES):
        inv, src = downloads / f'kr-industry-v2-original-inventory-{n}', downloads / f'kr-industry-v2-original-sources-{n}'
        plan_sha = sha(inv / 'remaining.json')
        if plan_sha != (inv / 'remaining.json.sha256').read_text().strip() or json.loads((inv / 'remaining.json').read_text())['batch'] != n:
            raise ValueError(f'FROZEN_BATCH_INVENTORY_MISMATCH:{n}')
        manifest = json.loads((src / 'manifest-originals.json').read_text())
        if manifest['planSha256'] != plan_sha or manifest['archiveSha256'] != sha(src / manifest['archive']):
            raise ValueError(f'ORIGINAL_SOURCE_ARCHIVE_MISMATCH:{n}')
        for name in ('remaining.json', 'remaining.json.sha256', 'inventory.json'):
            copy(inv / name, DEST / f'inventory/batch-{n:02d}/{name}')
        for name in ('manifest-originals.json', manifest['archive']):
            copy(src / name, DEST / f'acquired-dart/annual/batch-{n:02d}/{name}')
    if chapters:
        chapters = Path(chapters)
        manifest = json.loads((chapters / 'manifest-chapters.json').read_text())
        if manifest['planSha256'] != sha(PLAN) or manifest['archiveSha256'] != sha(chapters / manifest['archive']):
            raise ValueError('CHAPTER_ARCHIVE_MISMATCH')
        for name in ('manifest-chapters.json', manifest['archive']):
            copy(chapters / name, DEST / f'acquired-dart/chapters/{name}')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--downloads', type=Path, required=True)
    p.add_argument('--chapters', type=Path)
    a = p.parse_args()
    assemble(a.downloads, a.chapters)
