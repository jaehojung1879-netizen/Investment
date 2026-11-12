"""Read-only closed-study provenance; never an execution preflight."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.closed_atlas_provenance import canonical, inspect  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-main', required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    temp_root = Path('/tmp').resolve()
    if (args.work.resolve().is_relative_to(ROOT) or args.work.resolve() == temp_root
            or not args.work.resolve().is_relative_to(temp_root) or args.work.is_symlink()):
        parser.error('provenance receipts require a private temporary subdirectory outside the repository')
    failure = None
    try:
        report = inspect(ROOT, expected_main=args.expected_main)
    except Exception as error:
        failure = error
        report = {'status': 'CLOSED_STUDY_PROVENANCE_REFUSED', 'error': str(error),
                  'newExecutionPreflight': 'NOT_RUN', 'formalExecutionAuthorized': False}
    raw = canonical(report) + b'\n'
    args.work.mkdir(parents=True, exist_ok=True)
    target = args.work / 'closed-study-provenance.json'
    if target.is_symlink():
        raise ValueError('PROVENANCE_RECEIPT_SYMLINK_REFUSED')
    try:
        with target.open('xb') as stream:
            stream.write(raw)
    except FileExistsError:
        if target.read_bytes() != raw:
            raise ValueError('PROVENANCE_RECEIPT_ALREADY_EXISTS_WITH_DIFFERENT_BYTES') from None
    print(json.dumps(report, ensure_ascii=False))
    if failure:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
