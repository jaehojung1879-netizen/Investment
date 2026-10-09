"""Default validates v2 input amendment; no automatic outcome access."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pipeline.kr_alpha_atlas_phase_c import contract, synthetic, preflight  # noqa: E402
from pipeline import kr_alpha_atlas_phase_c_amendment as amendment  # noqa: E402


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['validate','preflight','synthetic','execute'],nargs='?',default='validate')
    p.add_argument('--work',type=Path,default=Path('/tmp/atlas-phase-c-amended'))
    p.add_argument('--expected-main')
    a=p.parse_args()
    # Formal main/owner checks must precede exact registration validation.
    spec=amendment.load() if a.mode!='execute' else None
    if a.mode=='validate':
        out={'registration':'VALID_VERSIONED_AMENDMENT','amendmentFileSha256':contract.file_hash(contract.ROOT/amendment.AMENDMENT),
             'effectiveContractSha256':contract.digest(spec),'globalOneShotLock':amendment.GLOBAL_LOCK,
             'calendar':contract.calendar_facts(spec),'gitInputs':preflight.verify_git_inputs(contract.ROOT,spec),
             'realOutcomeReads':0}
    elif a.mode=='preflight':
        if not a.expected_main:
            p.error('--expected-main is required for the outcome-free full preparation audit')
        out=amendment.audit(contract.ROOT,a.work,a.expected_main)
        out={k:out[k] for k in ['status','actualMatrixDigest','elapsedSeconds','counters']}
    elif a.mode=='synthetic':
        out=synthetic.complete_study(spec,a.work)
    else:
        out=amendment.formal(work=a.work)
    print(json.dumps(out,ensure_ascii=False))
    if a.mode=='preflight' and out['status'].startswith('BLOCKED'):
        raise SystemExit(2)  # receipt is durable; a blocked gate is not success


if __name__=='__main__':
    main()
