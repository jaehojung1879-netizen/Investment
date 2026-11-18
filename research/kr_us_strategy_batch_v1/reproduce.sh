#!/usr/bin/env bash
set -euo pipefail
# Run from repository root. Independent markets finish even if the other fails.
PYTHON=${PYTHON:-python}
KR_INPUTS=${KR_INPUTS:-/workspace/s2-inputs}
US_INPUTS=${US_INPUTS:-/workspace/batch-inputs/us}
STAGE=${1:-all}
OUT=research/kr_us_strategy_batch_v1
export PYTHON KR_INPUTS US_INPUTS
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
mkdir -p "$OUT/validation"
case "$STAGE" in
  all|inputs|compute|report|verify) ;;
  *) printf 'Unknown stage: %s\n' "$STAGE" >&2; exit 2 ;;
esac
if [[ "$STAGE" == all || "$STAGE" == inputs ]]; then
  bash "$OUT/prepare_kr.sh" > "$OUT/validation/kr-inputs.log" 2>&1 &
  kr_prep_pid=$!
  "$PYTHON" -m research.kr_us_strategy_batch_v1.us_prepare --private "$US_INPUTS" \
    --out "$OUT/results/us-input-preparation.json" > "$OUT/validation/us-inputs.log" 2>&1 &
  us_prep_pid=$!
  if wait "$kr_prep_pid"; then kr_prep_status=0; else kr_prep_status=$?; fi
  if wait "$us_prep_pid"; then us_prep_status=0; else us_prep_status=$?; fi
  printf 'Input preparation exit codes KR=%s US=%s\n' "$kr_prep_status" "$us_prep_status"
fi
if [[ "$STAGE" == all || "$STAGE" == compute ]]; then
  "$PYTHON" -m research.kr_us_strategy_batch_v1.kr --scratch "$KR_INPUTS" --stage all \
    > "$OUT/validation/kr-run.log" 2>&1 &
  kr_run_pid=$!
  "$PYTHON" -m research.kr_us_strategy_batch_v1.us --private "$US_INPUTS" --stage all --workers "${US_WORKERS:-2}" \
    > "$OUT/validation/us-run.log" 2>&1 &
  us_run_pid=$!
  if wait "$kr_run_pid"; then kr_run_status=0; else kr_run_status=$?; fi
  if wait "$us_run_pid"; then us_run_status=0; else us_run_status=$?; fi
  if [[ "$us_run_status" == 0 ]]; then
    "$PYTHON" -m research.kr_us_strategy_batch_v1.us_bridge --private "$US_INPUTS" \
      > "$OUT/validation/us-source-bridge.log" 2>&1
    "$PYTHON" -m research.kr_us_strategy_batch_v1.us_qqq --private "$US_INPUTS" \
      > "$OUT/validation/us-qqq.log" 2>&1
    "$PYTHON" -m research.kr_us_strategy_batch_v1.us_attribution_export --private "$US_INPUTS" \
      > "$OUT/validation/us-pername-export.log" 2>&1
  fi
  "$PYTHON" -c 'import json,sys; from pathlib import Path; Path(sys.argv[1]).write_text(json.dumps({"KR":int(sys.argv[2]),"US":int(sys.argv[3])},indent=1)+"\n")' \
    "$OUT/results/run-exit-codes.json" "$kr_run_status" "$us_run_status"
  printf 'Market calculation exit codes KR=%s US=%s\n' "$kr_run_status" "$us_run_status"
fi
if [[ "$STAGE" == all || "$STAGE" == compute || "$STAGE" == report ]]; then
  "$PYTHON" -m research.kr_us_strategy_batch_v1.report
fi
if [[ "$STAGE" == all || "$STAGE" == compute || "$STAGE" == report || "$STAGE" == verify ]]; then
  "$PYTHON" -m research.kr_us_strategy_batch_v1.verify
fi
