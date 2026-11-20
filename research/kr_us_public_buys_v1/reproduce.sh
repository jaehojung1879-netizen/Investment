#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."
PYTHON=${PYTHON:-python}
KR_INPUTS=${KR_INPUTS:-/workspace/s2-inputs}
US_INPUTS=${US_INPUTS:-/workspace/batch-inputs/us}
US_EXPOSURE_INPUTS=${US_EXPOSURE_INPUTS:-/workspace/exposure-inputs/us}
US_PUBLIC_BUYS_INPUTS=${US_PUBLIC_BUYS_INPUTS:-/workspace/public-buys-inputs/US}
MOD=research.kr_us_public_buys_v1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1

kr() {
    "$PYTHON" -m "$MOD.kr" --scratch "$KR_INPUTS"
}

wat() {
    "$PYTHON" -m "$MOD.wat" --private "$US_INPUTS" --inputs "$US_EXPOSURE_INPUTS" &&
        "$PYTHON" -m "$MOD.wat_verify"
}

us() {
    "$PYTHON" -m "$MOD.us_study" --private "$US_INPUTS" --inputs "$US_EXPOSURE_INPUTS"
}

report() {
    "$PYTHON" -m "$MOD.report"
}

case "${1:-all}" in
    KR) kr ;;
    US) us ;;
    WAT) wat ;;
    source-US)
        "$PYTHON" -m "$MOD.us_events" --private "$US_PUBLIC_BUYS_INPUTS"             --stage "${2:-all}"
        ;;
    report) report ;;
    all)
        kr &
        kr_pid=$!
        (
            wat_status=0
            buy_status=0
            wat || wat_status=$?
            us || buy_status=$?
            printf 'US branch statuses WAT=%s PURCHASES=%s\n' "$wat_status" "$buy_status"
            (( wat_status == 0 && buy_status == 0 ))
        ) &
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
        printf 'Usage: %s [all|WAT|KR|US|source-US [stage]|report]\n' "$0" >&2
        exit 2
        ;;
esac
