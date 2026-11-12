"""PIT security identity from the monthly KOSPI Top300 snapshots (no prices read).

Only ``date``, ``code`` and ``name`` are read from the snapshot rows; market
cap and listed shares are present in the file but are not used here.
A filing on day D is matched against the latest snapshot dated strictly
BEFORE D, so the identity used was knowable before the filing.
"""
from __future__ import annotations

import bisect
import gzip
import hashlib
import json
from pathlib import Path


def load_snapshots(directory: Path) -> dict[str, dict[str, str]]:
    snapshots: dict[str, dict[str, str]] = {}
    for path in sorted(Path(directory).glob('krx-universe-*.jsonl.gz')):
        with gzip.open(path, 'rt', encoding='utf-8') as fh:
            for line in fh:
                row = json.loads(line)
                snapshots.setdefault(row['date'], {})[row['code']] = row['name']
    if not snapshots:
        raise ValueError('NO_PIT_UNIVERSE_SNAPSHOTS')
    return snapshots


def snapshot_digest(directory: Path) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(directory).glob('krx-universe-*.jsonl.gz'))}


class PitTop300:
    def __init__(self, snapshots: dict[str, dict[str, str]]):
        self.snapshots = snapshots
        self.dates = sorted(snapshots)

    def prior_snapshot(self, receipt_day: str) -> str | None:
        """Latest snapshot dated strictly before ``receipt_day`` (ISO date)."""
        i = bisect.bisect_left(self.dates, receipt_day)
        return self.dates[i - 1] if i else None

    def membership(self, stock_code: str | None, receipt_day: str) -> dict:
        snap = self.prior_snapshot(receipt_day)
        if snap is None:
            return {'status': 'NO_PRIOR_SNAPSHOT', 'snapshot': None}
        if not stock_code:
            return {'status': 'STOCK_CODE_ABSENT_IN_INDEX', 'snapshot': snap}
        if stock_code in self.snapshots[snap]:
            return {'status': 'PIT_TOP300_MEMBER', 'snapshot': snap,
                    'nameAtSnapshot': self.snapshots[snap][stock_code]}
        return {'status': 'NOT_IN_PIT_TOP300', 'snapshot': snap}
