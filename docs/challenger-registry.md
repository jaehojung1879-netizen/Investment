# Challenger registry

A running list of every selection-ranking method this repository has scored,
so a name in a report always resolves to one row here. Numbering is a label
for humans; it changes nothing about how `pipeline/portfolio_validation.py`
identifies a selector (`CHAMPION` / `CHALLENGER` constants, or the
`selector`/`scoreSource` fields `selection_null` stamps on every result).
Renumbering never renames the code identifier a study already published
results under.

A row is added the day a genuinely different ranking method is scored against
the champion (a new `score_fn` passed into `selection_null`/`priced_cross_section`),
not for a parameter tweak inside an existing method — a tweak stays a rung on
that method's own ablation ladder (see `docs/*-v1.md`) and is not a new
challenger number.

| # | Internal identifier | One-line description | Status | Introduced in |
|---|---|---|---|---|
| **CHAMPION** | `ALPHA_RANK_PER_DOWNSIDE_RISK` | Sector-neutral 4-factor alpha (momentum/value/quality/lowvol) ranked to a percentile, gated at the 66th percentile, scored as rank-edge ÷ realized downside vol, sized with entry-state + evidence multipliers, top-5 concentrated. Production. | 운용중 (paperTrading; `liveValidated` false) | (기존) |
| **CHALLENGER-1** | `CALIBRATED_EXPECTED_RETURN_PER_DOWNSIDE_RISK` | Calibrated expected-return-per-downside-risk scorer, tested against the champion via the selection-null permutation test. | 검증됨 — 무작위와 통계적으로 구분 안 됨 (best p=0.065); 승격 안 됨 | `selection-value-decomposition-v1` (PR #134) |
| **CHALLENGER-2** | *(미정)* | 완전히 새로운 접근 방식 — 사용자가 별도로 설계 예정. 팩터 조합의 파라미터 조정이 아니라 **다른 종류의 순위 로직**일 때만 이 번호를 씀. | 착수 전 | — |

## What is NOT a new challenger number

These are parameter tweaks on the CHAMPION's own ranking method, each already
run as an ablation rung with its own control, not separate selectors:

- `switch-hurdle-v1` — a regional cost-derived hysteresis on *when to swap*, not
  on how a name is ranked. (PR #135)
- `signal-persistence-v1` — ranks on a k-block trailing mean of the same
  `alphaPercentile` instead of its latest value. Same ranking method, smoothed
  input. (PR #136)

## Adding a row

1. Give the new method a name that describes what it computes (matching the
   existing style: `SOMETHING_PER_SOMETHING`), and assign it the next
   `CHALLENGER-N` number here.
2. Run it through `selection_null` with `score_fn` set to the new method so it
   gets its own permutation-null verdict, per the selection-value invariants.
3. Record the result in this table (status + which study introduced it) in the
   same PR that adds the method.
