"""Reproduce the authorized ETF-only audit or predeclared stock source checks.

Writes a fresh audit receipt only; cannot amend a registration, lock or execute.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pipeline.kr_alpha_atlas_phase_c import contract  # noqa: E402
from pipeline.kr_alpha_atlas_price_integrity import reconcile_benchmark, audit_stocks, final_session_sources  # noqa: E402
from pipeline.kr_model_raw_snapshot import immutable_bytes  # noqa: E402


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scope',choices=['benchmark','stock-source','final-session-source'])
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():
        parser.error('fresh audit output required; frozen evidence is never overwritten')
    function={'benchmark':reconcile_benchmark,'stock-source':audit_stocks,'final-session-source':final_session_sources}[args.scope]
    report=function(contract.ROOT)
    immutable_bytes(args.output,contract.canonical(report)+b'\n')
    print(json.dumps({'scope':args.scope,'outputSha256':contract.file_hash(args.output),'realHistoricalAlphaOutcomeReads':0}))


if __name__=='__main__':
    main()
