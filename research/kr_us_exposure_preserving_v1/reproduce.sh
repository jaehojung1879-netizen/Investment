#!/usr/bin/env bash
set -euo pipefail
PYTHON=${PYTHON:-python}
UNIVERSE_KR=${KR_INPUTS:-/workspace/s2-inputs}
PRIOR_US=${US_INPUTS:-/workspace/batch-inputs/us}
EXPOSURE_US=${US_EXPOSURE_INPUTS:-/workspace/exposure-inputs/us}
MOD=research.kr_us_exposure_preserving_v1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
if [[ "${1:-all}" == report ]]; then
    "$PYTHON" -m "$MOD.report"
    exit
fi
kr() (
    "$PYTHON" -m "$MOD.kr" --scratch "$UNIVERSE_KR"
    "$PYTHON" -m "$MOD.nav" KR --kr-scratch "$UNIVERSE_KR"
    "$PYTHON" -m "$MOD.validate_kr"
)
us() (
    if [[ ! -f "$EXPOSURE_US/close-repaired.pkl" ]]; then
        "$PYTHON" -m "$MOD.us_repair_price" --private "$PRIOR_US" --inputs "$EXPOSURE_US"
    fi
    "$PYTHON" -m "$MOD.us" --private "$PRIOR_US" --inputs "$EXPOSURE_US"
    "$PYTHON" -m "$MOD.nav" US --us-private "$PRIOR_US" --us-repaired "$EXPOSURE_US/close-repaired.pkl"
    "$PYTHON" -m "$MOD.us_validate" --private "$PRIOR_US"
)
kr &
kr_task=$!
us &
us_task=$!
kr_rc=0
us_rc=0
wait "$kr_task" || kr_rc=$?
wait "$us_task" || us_rc=$?
printf 'Market run status KR=%s US=%s\n' "$kr_rc" "$us_rc"
"$PYTHON" -m "$MOD.report"
if [[ "$kr_rc" != 0 || "$us_rc" != 0 ]]; then
    exit 1
fi
