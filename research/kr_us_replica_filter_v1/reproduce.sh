#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."
PYTHON=${PYTHON:-python}
KR_INPUTS=${KR_INPUTS:-/workspace/s2-inputs}
US_INPUTS=${US_INPUTS:-/workspace/batch-inputs/us}
US_EXPOSURE_INPUTS=${US_EXPOSURE_INPUTS:-/workspace/exposure-inputs/us}
MOD=research.kr_us_replica_filter_v1
PRIOR=research.kr_us_exposure_preserving_v1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1

report() {
    "$PYTHON" -m "$MOD.report"
    "$PYTHON" -m "$MOD.tables"
    "$PYTHON" -m "$MOD.verify"
}

kr() (
    "$PYTHON" -m "$MOD.kr" --scratch "$KR_INPUTS"
)

us() (
    if [[ ! -f "$US_EXPOSURE_INPUTS/close-repaired.pkl" ]]; then
        "$PYTHON" -m "$PRIOR.us_repair_price" --private "$US_INPUTS" --inputs "$US_EXPOSURE_INPUTS"
    fi
    if [[ ! -f "$US_EXPOSURE_INPUTS/us-adapter-payload.pkl" ]]; then
        prior_output=$(mktemp -d "$US_EXPOSURE_INPUTS/pr351-prepare.XXXXXXXX")
        "$PYTHON" -m "$PRIOR.us" --private "$US_INPUTS" --inputs "$US_EXPOSURE_INPUTS" \
            --out "$prior_output" --prepare-only
    fi
    "$PYTHON" -m "$MOD.support" --private "$US_INPUTS"
    "$PYTHON" -m "$MOD.us" --private "$US_INPUTS" --inputs "$US_EXPOSURE_INPUTS"
)

case "${1:-all}" in
    report) report ;;
    KR) kr ;;
    US) us ;;
    all)
        kr &
        kr_pid=$!
        us &
        us_pid=$!
        kr_status=0
        us_status=0
        wait "$kr_pid" || kr_status=$?
        wait "$us_pid" || us_status=$?
        printf 'Market run status KR=%s US=%s\n' "$kr_status" "$us_status"
        report
        (( kr_status == 0 && us_status == 0 ))
        ;;
    *)
        printf 'Usage: %s [all|KR|US|report]\n' "$0" >&2
        exit 2
        ;;
esac
