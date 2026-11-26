# 전향 연구 운영 체계 (prospective-ops-v1)

작성: 2026-11-25. 연구 방법론·등록 사양·승인 해시·기존 영수증은 변경하지 않았다. 과거 누락 창은 소급 기록하지 않는다.

## 1. 구성

| 요소 | 위치 | 역할 |
|---|---|---|
| 레지스트리 | `research/prospective_ops/registry.json` | 연구별 승인·주기·기록기·만기·감시 기준. **등록해도 기록기는 시작되지 않는다** |
| 상태·가드·검증 | `pipeline/prospective_ops.py` | 영수증 기반 상태 산출, 쓰기 가드(fail-closed), 쓰기 후 원격 검증 |
| CLI | `scripts/prospective_ops.py` | `status` / `guard` / `verify-receipt` (git 객체만 읽음, 원장 쓰기 없음) |
| 워크플로 | `.github/workflows/prospective-ops.yml` | 평일 19:40 KST 기록(가드 통과 시) + 항상 감시 |
| 연속성 감사 | `scripts/audit_corporate_receipt_continuity.py` | #374 코드를 그대로 재사용(cherry-pick). 상태 산출은 동일 규칙 |
| 공시 기록기 | 등록 커밋 `8aee189`의 `live_run` | **수정 없이** 별도 worktree에서 실행 |

## 2. 상태 정의 (영수증으로만 판정)

| 상태 | 의미 |
|---|---|
| HEALTHY | 자동화 활성 + 닫힌 창마다 유효 영수증 + 무결성 오류 없음 |
| PENDING | 열린 창이 있고 아직 기록 시각 전 |
| MISSED | 닫힌 창에 유효 영수증 없음 (`MISSED_NOT_OBSERVED`, 이벤트 0건과 다름) |
| SOURCE_BLOCKED | 원장 파일 부재 또는 원천 차단 |
| EXECUTION_FAILED | 영수증 무결성 오류(중복·해시·창 위반) 또는 기록기 실행 실패 |
| DISABLED | 승인됐으나 기록기가 의도적으로 비활성 |
| UNAUTHORIZED | 승인 없음 — 자동화 대상 아님 |

워크플로 성공 ≠ 영수증 성공. 쓰기 후 `verify-receipt`가 원격 `signal-history`에 해당 세션 영수증이 정확히 1건, 유효한지 확인한다.
알림(`alerts`)은 **자동화가 활성화된 연구**의 MISSED / EXECUTION_FAILED / SOURCE_BLOCKED만 발생시킨다. 비활성 상태는 알려진 상태이지 사고가 아니다.

## 3. 단일 writer 보장 (fail-closed)

가드는 다음이 모두 참일 때만 `ALLOW_WRITE`: 연구 승인(소유자 해시), `automation.enabled`(소유자 커밋), 레거시 Claude trigger 전부 `DISABLED`로 서명된 attestation 파일, 고정 코드 커밋 존재, AUTHORIZATION의 사양 해시 일치, 원격 원장에 무결성 오류 없음.
보조 장치: (1) `live_run`은 같은 날 영수증이 있으면 `ALREADY_RECORDED`(멱등), (2) push 충돌 시 영수증 행이 서로 다르게 덧붙여져 rebase가 충돌하면 중단, (3) 워크플로 `concurrency` 직렬화, (4) 모니터가 `DUPLICATE_SESSION`을 무효로 판정해 이중 기록을 보이게 한다.
기존 Claude writer가 다시 실행돼도 원장은 같은 규칙(append-only, 날짜 1행, 쓰기 시각 창)으로 보호된다.

## 4. 새 연구 등록 (Stage E)

레지스트리에 한 항목을 추가하면 상태 산출·감시·독립 관측 계산이 그대로 적용된다. 승인 전(`approval.status` 미승인)은 UNAUTHORIZED이며
`automation.enabled=true`는 승인·고정 커밋·단일 writer attestation 없이는 `validate_registry`가 거부한다. 새 스케줄러·새 워크플로가 필요 없다.
연구별 기록기는 `guard`가 요구하는 단일 인터페이스(승인 해시, 고정 커밋, 원장 경로)만 맞추면 된다. 현재 기록기가 구현된 연구는 공시 연구 1건이며,
나머지 승인 연구(`kr-selection-challenger-*`, `rp1-b-h1-state-v1`, `current-champion-decisions-v1`, `weekly-decisions`)의 기록기는 기존 `ledger.yml`이 계속 담당하고 본 체계는 감시만 한다.

## 5. 한계 (확인된 사실)

- 사이트(Pages) 표시는 구현하지 않았다. `pages.yml`은 봉인 연구가 바이트 고정하고, Pages 상태 저장은 다른 담당 환경의 진행 중인 작업(#380/#381)이다. 상태 스냅샷은 `signal-history/ledger/research-ops/prospective-status.json`에 게시되므로 해당 작업이 이를 읽기 전용으로 소비하면 된다.
- 감시 대상 중 `OBSERVED_ONLY` 연구는 등록된 주기가 없어 완전성을 주장하지 않는다(최근 기록 경과일 기준 점검만).
- 만기 달력은 `pipeline/replay_calendar.py`(버전 고정) 기준이며 미공시 휴장은 반영되지 않는다.
- 고정 코드 커밋 `8aee189`는 병합되지 않은 브랜치 `research/corporate-event-readiness-v1`에 있다. 브랜치 삭제 시 체크아웃이 실패한다(가드가 `PINNED_CODE_COMMIT_UNAVAILABLE`로 거부). 병합 또는 태그로 보존할 것.

## 6. 불변 조건 (AGENTS.md에는 추가하지 않음)

`AGENTS.md`는 Phase C 봉인 사양이 해시로 고정한 파일이므로 수정하지 않는다. 운영 불변 조건은 이 문서에 둔다.

- 워크플로 성공 ≠ 영수증 존재. 상태는 영수증으로만 산출하고, 기록기 실행 결과는 `EXECUTION_FAILED`를 더할 수만 있다.
- 누락 창은 `MISSED_NOT_OBSERVED`. 소급 기록·날짜 변경·"이벤트 0건" 해석·독립 표본 산입을 하지 않는다. `continuityBaselineSession`은 알림 구분용이며 `missedRecords`를 줄이지 않는다.
- 등록은 아무것도 시작하지 않는다. 활성화는 소유자 승인 해시, 고정 코드 커밋, 단일 writer attestation이 모두 있어야 한다.
- 등록 코드는 수정 없이 고정 커밋에서 실행한다.
