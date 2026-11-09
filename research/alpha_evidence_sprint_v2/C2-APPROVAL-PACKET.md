# c2-fixed-exposure-attribution-v1 — Owner 실행 승인 패킷 (2026-11-09)

상태: **READY_FOR_OWNER_APPROVAL**. 역사 outcome·수익률·NAV·베타 값은 이 패킷 작성까지 **0회** 계산·조회했다.
검증 수준: `AUTHOR_VALIDATION_ONLY` (비작성자 독립 감사 미완료 — Codex 지적사항 미접수).

## 1. 정확 해시

| 대상 | SHA256 |
|---|---|
| 연구 계약 `c2-fixed-exposure-attribution-v1.json` | `f83035d804de56a2799dcd188c02a0839a63da93c48cd756edb98d306310922a` |
| `c2_attribution.py` | `933f05b285b1a35d0120dcce435a21b4cfc16d4677056819c1a7f9ba3d8fc40d` |
| `c2_attribution_run.py` | `50df18fe8b5160fbdf65258afe894f109c4c82ab0020f793bfbb4aaf60352e48` |
| replay-v16 입력 매니페스트 (내용 digest, 계약에 고정) | `f0781292f508a123c234ded6d28aa8e84a0dc3cc29500e14989dc0b68f53b4d2` |
| 매니페스트 파일 blob (`signal-history` `4b6f8b71` = 현재 `0b3025d9`, 동일) | `76556e948fd89786d846a6275a0bc55f4bb56658` |
| `docs/results/regional-standalone-paths.json.gz` (155블록 목표 비중) | `7a09751f99f5d892821cac6bbb4f28359049d58364cb40db1814fac4f93210cb` |
| `docs/weekly-decision/weekly-passive-first-v1-replay-corrected-benchmark.json` (재현 대상 C2/P0) | `901b3aee7d3bc06eed3fd2bd14b07a0d4ca4da23745b861a877203c48772b8d2` |
| `docs/audits/kr-alpha-atlas-phase-c-integrity/benchmark-reconciliation-corrected.json` (069500 교정 TR) | `58580c4370ec2c5afa124f849afbc4fa7b5c879012e75ebbd48ee7c7a0e659a9` |
| `data/bok-policy-rates.json` | `a7edf0e532c7b54da9d962ebf12ff2552c90c783439fef99d7c761c5b9ea69ff` |
| `docs/results/kr-termination-inventory.json` | `b58ecb2c4500302c40784613318c8451beee663ece5ee76ada26873a4292f93f` |

## 2. 실행 가능성 (outcome-free preflight, `evidence/c2-preflight.json`)

- 155/155 블록 적격. 결측 0. 보유 종목 72개 모두 253세션 베타 창 확보, 최소 공동 수익률 쌍 **250** (하한 200).
- 069500 교정 TR: 첫 창 ETF 수익률 250개, 155블록 시작·종료일 모두 호가 존재.
- 현금: 계약대로 `ZERO` / `BOK_POLICY_PROXY` / `BOK_POLICY_PLUS_100BP` 3시나리오 band. 투자 가능한 KRW 현금수익률(CD91·153130)은 측정하지 않는다 — 결론은 "세 시나리오 일치 시 조건부" 이다.
- 출력 전에는 미확정: 매수-보유 항등식 실패 블록 수(기업행동 적용 0블록이라 0 예상), 베타 clipping 수(실행 결과에 날짜와 함께 기록).

## 3. 사전(outcome 전) 개정 — 계약 `preOutcomeRevisions`

- **R1 재현 게이트:** 재구성한 C2·ETF(P0) 순수익 경로가 공개된 C2/P0 `cagrPct`·`cumulativeNetReturnPct`(14.258% / 12.507% 등)를 ±0.0005pp로 재현하지 못하면 `SOURCE_OR_SAMPLE_INSUFFICIENT`. 강화만.
- **R2 비용 후 조건:** SURVIVES는 비용 1x 순수익 C2−대조군 구간 하한 > 0도 요구. SURVIVES를 지울 수만 있다.
- **R3 결함 수정 (실행 전 발견):** ① `execute`가 존재하지 않는 `replay_valuation.normalize_daily_series`를 호출 → 승인 후 즉시 중단되었을 것 ② >10% 귀속불가 규칙 미구현 ③ 베타 결측 1블록이 C2·ETF 경로까지 지움 ④ ETF 단독 경로 초기 매수비용 누락 ⑤ 회전율 미보고 ⑥ 승인 파일 존재만 확인 → Owner 커밋·무수정 확인 ⑦ 1회 실행 강제 없음 ⑧ 연수 365.25 vs replay 365.2425.

## 4. 실행 명령 및 출력

```bash
git worktree add --detach /tmp/sh-c2 4b6f8b7137521a148d9cd2c9e3c2fdfdcb5ae71a
python research/alpha_evidence_sprint_v2/c2_attribution_run.py execute /tmp/sh-c2/ledger
```

출력: `research/alpha_evidence_sprint_v2/c2-fixed-exposure-attribution-v1-result.json` 하나뿐. 이 파일이 디스크나 git 이력에 있으면 재실행을 거부한다.

## 5. 잠금·봉인 충돌 없음

- 수정 파일은 `research/alpha_evidence_sprint_v2/` 내 C2 파일과 이 패킷뿐. `research_specs/`, `docs/results/`, `pipeline/`, `.github/`, `data/` 무변경.
- 이 연구의 잠금 ref 없음(`git ls-remote origin 'refs/tags/*'`에 c2-fixed-exposure 없음). Phase C 봉인·잠금, A1/B1, #320/#322/#324 미접촉.
- 계약 `promotionEligible: false`. 어떤 결과도 C2 승격·ETF 기본값 변경을 하지 않는다.

## 6. Owner가 승인할 정확한 문구와 파일

브랜치 `claude/optimistic-cray-wnegq7`에 Owner 계정으로 아래 파일을 커밋한다(GitHub 웹 "Add file"이면 된다). 다른 사람이 이 파일을 수정한 커밋이 하나라도 있으면 실행이 거부된다.

`research/alpha_evidence_sprint_v2/AUTHORIZATION-c2.json`:

```json
{
 "phrase": "APPROVE KR_PHASE_D_EXCEPTION c2-fixed-exposure-attribution-v1 f83035d804de56a2799dcd188c02a0839a63da93c48cd756edb98d306310922a",
 "codeSha256": {
  "c2_attribution.py": "933f05b285b1a35d0120dcce435a21b4cfc16d4677056819c1a7f9ba3d8fc40d",
  "c2_attribution_run.py": "50df18fe8b5160fbdf65258afe894f109c4c82ab0020f793bfbb4aaf60352e48"
 },
 "scope": "one-shot historical attribution of the fixed saved KR C2 path; KR Phase D exception for this study only; no promotion, no production change",
 "independentAuditRequiredBeforeExecution": true
}
```

승인 전 필요: 비작성자 독립 감사(Codex 등)가 위 해시의 코드를 검토. 감사로 코드가 바뀌면 해시가 바뀌고 이 패킷은 다시 발행된다.
