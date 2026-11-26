#!/usr/bin/env bash
set -euo pipefail
# Run from the repository root. Old v1 outputs are read only.
: "${S:?Set S to an absolute input scratch path outside the checkout}"
PYTHON=${PYTHON:-python}
GENERATOR=0a1f494171576af6928fe531145a8c8f050253fd
SOURCE=4ea107ed0cde289f0a049a65ff13d2441a786710
ACCOUNTING=fb6e83743fd8cdba647d1522a4645b662a9d5647
mkdir -p "$S"
if [[ ! -f "$S/matrix.pkl" || ! -f "$S/dataset.pkl" || ! -f "$S/macro_panel.pkl" || ! -f "$S/vix_fx.pkl" ]]; then
  git fetch --no-tags --depth=1 --filter=blob:none origin "$GENERATOR" "$SOURCE" "$ACCOUNTING"
  if [[ ! -d "$S/wt329" ]]; then git worktree add --detach "$S/wt329" "$GENERATOR"; fi
  [[ $(git -C "$S/wt329" rev-parse HEAD) == "$GENERATOR" ]]
  if [[ ! -f "$S/matrix.pkl" ]]; then
    (cd "$S/wt329" && "$PYTHON" research/ml_strategy_tournament_v1/build_features.py --scratch "$S/raw" --out "$S/matrix.pkl")
  fi
  if [[ ! -f "$S/dataset.pkl" ]]; then
    (cd "$S/wt329" && "$PYTHON" research/ml_strategy_tournament_v1/prepare_dataset.py --scratch "$S")
  fi
  if [[ ! -f "$S/macro_panel.pkl" || ! -f "$S/vix_fx.pkl" ]]; then
    (cd "$S/wt329" && "$PYTHON" research/adaptive_cocktail_v1/load_sources.py --scratch "$S")
  fi
fi
"$PYTHON" -m research.kr_s2_single_slot_matched_v1.analyze --scratch "$S"
"$PYTHON" -m research.kr_s2_single_slot_matched_v1.report
"$PYTHON" -m research.kr_s2_single_slot_matched_v1.verify
