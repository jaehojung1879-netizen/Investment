#!/usr/bin/env bash
set -euo pipefail
# Only recreate absent input caches; never invoke an old report's output stage.
: "${KR_INPUTS:?Set KR_INPUTS to the external Korean scratch directory}"
PYTHON=${PYTHON:-python}
GENERATOR=0a1f494171576af6928fe531145a8c8f050253fd
SOURCE=4ea107ed0cde289f0a049a65ff13d2441a786710
ACCOUNTING=fb6e83743fd8cdba647d1522a4645b662a9d5647
mkdir -p "$KR_INPUTS"
if [[ ! -f "$KR_INPUTS/matrix.pkl" || ! -f "$KR_INPUTS/dataset.pkl" || ! -f "$KR_INPUTS/macro_panel.pkl" || ! -f "$KR_INPUTS/vix_fx.pkl" ]]; then
  git fetch --no-tags --depth=1 --filter=blob:none origin "$GENERATOR" "$SOURCE" "$ACCOUNTING"
  if [[ ! -d "$KR_INPUTS/wt329" ]]; then git worktree add --detach "$KR_INPUTS/wt329" "$GENERATOR"; fi
  [[ $(git -C "$KR_INPUTS/wt329" rev-parse HEAD) == "$GENERATOR" ]]
  if [[ ! -f "$KR_INPUTS/matrix.pkl" ]]; then
    (cd "$KR_INPUTS/wt329" && "$PYTHON" research/ml_strategy_tournament_v1/build_features.py --scratch "$KR_INPUTS/raw" --out "$KR_INPUTS/matrix.pkl")
  fi
  if [[ ! -f "$KR_INPUTS/dataset.pkl" ]]; then
    (cd "$KR_INPUTS/wt329" && "$PYTHON" research/ml_strategy_tournament_v1/prepare_dataset.py --scratch "$KR_INPUTS")
  fi
  if [[ ! -f "$KR_INPUTS/macro_panel.pkl" || ! -f "$KR_INPUTS/vix_fx.pkl" ]]; then
    (cd "$KR_INPUTS/wt329" && "$PYTHON" research/adaptive_cocktail_v1/load_sources.py --scratch "$KR_INPUTS")
  fi
fi
