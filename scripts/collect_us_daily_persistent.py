"""Manual owner-gated persistent US staging; defaults to a network-free plan."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pipeline import us_persistent_daily_collection as C  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root')
    parser.add_argument('--mode', choices=['plan','verify','collect'],default='plan')
    parser.add_argument('--session')
    parser.add_argument('--recheck',action='store_true')
    parser.add_argument('--approval')
    parser.add_argument('--approval-sha256')
    args = parser.parse_args(argv)
    now = C.S.now_utc()
    request = C.plan(args.root,now=now,session=args.session,recheck=args.recheck)
    if args.mode == 'plan':
        print(json.dumps(request,sort_keys=True,indent=2))
        return 0
    if args.mode == 'verify':
        print(json.dumps(C.inspect(args.root),sort_keys=True,indent=2))
        return 0
    if not args.approval or not args.approval_sha256:
        raise C.D.Refused('OWNER_APPROVAL_REQUIRED','No real request without exact owner-reviewed approval')
    digest = C.authorize(args.approval,args.approval_sha256,request,now=now)
    # Existing persistent state must verify BEFORE membership/provider network.
    C.inspect(args.root,now=now)
    C.authorize(args.approval,args.approval_sha256,request,now=C.S.now_utc())
    try:
        membership = C.S.current_sp500()
    except C.D.Refused as exc:
        result = C.record_source_failure(args.root,exc,request,digest,now=C.S.now_utc())
        print(json.dumps(result,sort_keys=True,indent=2))
        return 1
    http = []
    try:
        with C.F.provider_http_evidence() as http:
            result = C.run(args.root,membership,C.S.yahoo_daily,now=C.S.now_utc(),session=request['session'],
                           recheck=args.recheck,approval_digest=digest,approval=args.approval)
    finally:
        C.record_transport(args.root,http,request,digest)
    result = {**result,'providerHttpCallsThisProcess':len(http)}
    print(json.dumps(result,sort_keys=True,indent=2))
    return 0 if result['collectionComplete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
