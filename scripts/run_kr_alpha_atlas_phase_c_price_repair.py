"""Validate the source repair by default. Never authorizes or locks a study."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import kr_alpha_atlas_mirae_repair as repair  # noqa: E402
from pipeline.kr_alpha_atlas_phase_c import contract, preflight, synthetic  # noqa: E402
from pipeline.kr_alpha_atlas_mirae_source_audit import source_diagnostic  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['validate','preflight','synthetic','source-audit','execute'], default='validate', nargs='?')
    parser.add_argument('--expected-main')
    parser.add_argument('--work', type=Path, default=Path('/tmp/atlas-phase-c-price-repair'))
    args = parser.parse_args()
    if args.mode == 'execute':
        out = repair.formal(work=args.work)
    else:
        spec = repair.load()
        if args.mode == 'validate':
            out = {'registration':'VALID_VERSIONED_SOURCE_REPAIR',
                   'repairAddendumFileSha256':contract.file_hash(contract.ROOT/repair.ADDENDUM),
                   'effectiveContractSha256':contract.digest(spec),
                   'calendar':contract.calendar_facts(spec),
                   'gitInputs':preflight.verify_git_inputs(contract.ROOT,spec),'realOutcomeReads':0}
        elif args.mode == 'source-audit':
            out = source_diagnostic()
        elif args.mode == 'synthetic':
            out = synthetic.complete_study(spec,args.work)
        else:
            if not args.expected_main:
                parser.error('--expected-main is required for outcome-free reconstruction')
            report = repair.audit(contract.ROOT,args.work,args.expected_main)
            out = {k:report[k] for k in ['status','actualMatrixDigest','elapsedSeconds','counters']}
    print(json.dumps(out,ensure_ascii=False))
    if args.mode=='preflight' and out['status'].startswith('BLOCKED'):
        raise SystemExit(2)


if __name__=='__main__':
    main()
