"""Validate v4 by default; explicit owner approval is separate from merging."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.kr_alpha_atlas_numeric_runtime import bootstrap  # noqa: E402

bootstrap()  # Before every numerical import, including hash-seed re-exec.
from pipeline import kr_alpha_atlas_reproducibility as V4  # noqa: E402
from pipeline.kr_alpha_atlas_phase_c import contract, preflight, synthetic  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['validate', 'preflight', 'synthetic', 'execute'], default='validate', nargs='?')
    parser.add_argument('--expected-main')
    parser.add_argument('--work', type=Path, default=Path('/tmp/atlas-phase-c-reproducible'))
    args = parser.parse_args()
    if args.action == 'execute':
        out = V4.formal(work=args.work)
    else:
        spec = V4.load()
        if args.action == 'validate':
            out = {'registration': 'VALID_PRE_OUTCOME_REPRODUCIBILITY_ADDENDUM',
                   'addendumFileSha256': contract.file_hash(contract.ROOT/V4.ADDENDUM),
                   'effectiveContractSha256': contract.digest(spec),
                   'runtime': V4.NR.verify(spec), 'calendar': contract.calendar_facts(spec),
                   'gitInputs': preflight.verify_git_inputs(contract.ROOT, spec), 'realOutcomeReads': 0}
        elif args.action == 'synthetic':
            out = synthetic.complete_study(spec, args.work)
        else:
            if not args.expected_main:
                parser.error('--expected-main is required')
            report = V4.audit(contract.ROOT, args.work, args.expected_main)
            out = {k: report[k] for k in ('status', 'actualMatrixDigest', 'elapsedSeconds', 'counters')}
    print(json.dumps(out, ensure_ascii=False))
    if args.action == 'preflight' and out['status'].startswith('BLOCKED'):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
