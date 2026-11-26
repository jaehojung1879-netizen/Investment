# 전향 연구 운영 체계 (prospective-ops-v1)

작성: 2026-11-25. 연구 방법론·등록 사양·승인 해시·기존 영수증은 변경하지 않았다. 과거 누락 창은 소급 기록하지 않는다.

## 1. 구성

| 요소 | 위치 | 역할 |
|---|---|---|
| 레지스트리 | `research/prospective_ops/registry.json` | 연구별 승인·주기·기록기·만기·감시 기준. **등록해도 기록기는 시작되지 않는다** |
| 상태·가드·검증 | `pipeline/prospective_ops.py` | 영수증 기반 상태 산출, 쓰기 가드(fail-closed), 쓰기 후 원격 검증 |
| CLI | `scripts/prospective_ops.py` | `status` / `guard` / `verify-receipt` (git 객체만 읽음, 원장 쓰기 없음) |
| 워크플로 | `research/prospective_ops/install/prospective-ops.yml` (템플릿, 설치 전에는 실행되지 않음) | 평일 19:40 KST 기록(가드 통과 시) + 항상 감시 |
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

## 3. 단일 writer — 무엇이 보장되고 무엇이 보장되지 않는가

**보장되지 않는 것.** 워크플로의 `concurrency` 그룹은 이 워크플로의 실행끼리만 직렬화한다. 외부 Claude 예약 작업(`trig_01XwJ7…`, `trig_013qoRYz…`)은 GitHub Actions가 볼 수도 멈출 수도 없으므로, 두 writer 사이의 **상호배제는 구조적으로 보장되지 않는다.** 활성 상태의 `trig_013qoRYz…`는 2026-11-25 조회 시점에도 `enabled=true`였다(이 세션의 비활성화 시도는 권한 분류기가 거부했고 적용되지 않았다).

**확인되는 것 (가드, 모두 fail-closed).**
1. 소유자 attestation 파일: 레거시 trigger 전부 `DISABLED` + trigger별 `readbackUtc` 증거 + 7일 이내 시각. 이것은 **소유자의 진술**이며 증명이 아니다(출력에도 `notAProof`로 명시).
2. 같은 세션을 두 writer가 동시에 쓰려 하면 push 단계에서 한쪽이 실패한다: 등록 writer의 실제 `push_with_retry`(고정 커밋 바이트)를 로컬 bare 원격으로 실행해 검증했다 — 두 번째 writer는 `REBASE_ONTO_SIGNAL_HISTORY_FAILED`로 중단되고 원격에는 세션당 정확히 1건만 남는다(`test_two_writers_for_the_same_session_cannot_both_land`). 한 writer가 먼저 끝난 뒤 두 번째가 실행되면 `live_run`이 `ALREADY_RECORDED`로 끝난다(등록 코드의 동작).
3. 사후: 같은 세션 2건 이상은 `DUPLICATE_SESSION`으로 모두 무효가 되고 알림 대상이다.

**남는 위험.** attestation이 거짓이거나 낡았는데 레거시 trigger가 복구되는 경우: 같은 세션의 첫 writer만 성공하고 나머지는 위 2의 경로로 막힌다. 다른 날짜의 영수증은 서로 충돌하지 않는다. 그러므로 위험은 "원장 훼손"이 아니라 "예상 밖 writer가 기록한 유효 영수증이 생길 수 있음"이며, 그 영수증의 `createdAtUtc`·커밋 작성자로 사후 식별한다.

## 3-1. 원장 조회 결과의 4분류와 실시간성·완전성

원장 읽기는 `ROWS` / `EMPTY_VALID`(유효한 빈 파일) / `ABSENT`(참조는 도달 가능하나 파일 없음) / `READ_FAILED`(참조 불가·git 오류·손상 JSON)로 나뉘며 합치지 않는다. 기존 영수증이 있는 승인 연구(`ledgerMustExist`)는 `READ_FAILED`·`ABSENT`·`EMPTY_VALID` 모두에서 가드가 거부하고 상태는 `SOURCE_BLOCKED`이며, 이 경우는 자동화 비활성이어도 알림 대상이다.
상태표는 **실시간성**(`freshness`: 최신 기록이 최근인가)과 **완전성**(`completeness`: 닫힌 창마다 유효 영수증이 있는가)을 별도 필드로 둔다. 등록 주기가 없는 연구는 완전성이 `NOT_ASSESSABLE`이고, 최근 기록이 있어도 `HEALTHY`가 되지 않는다(`PENDING` + `COMPLETENESS_NOT_ASSESSABLE_NO_REGISTERED_CADENCE`). `HEALTHY`는 자동화 활성 + `VERIFIED_COMPLETE` + `FRESH`일 때만이다.

## 3-2. 등록 writer 8aee189의 보존

현재 `8aee189`는 병합되지 않은 브랜치 4개(`research/corporate-event-readiness-v1` 등)에만 있고 태그가 없다(`git tag --contains` 빈 결과, 2026-11-26). 브랜치는 삭제될 수 있으므로 가드는 `PINNED_CODE_NOT_DURABLY_REFERENCED`로 거부한다(태그가 포함하거나 `main`의 조상일 때만 통과). 코드는 바꾸지 않고, 트리 해시 `b1cd5b18…`(레지스트리 `pinnedTreeSha`)와 승인 파일·사양 파일의 **바이트 해시**를 매 실행에서 확인해 같은 코드임을 증명한다. 소유자 조치: 주석 태그 한 개 또는 PR #322 병합(승인 패킷 참조).

## 3-3. 시각·거래일 경계

등록 writer는 실행 시각의 **KST 날짜**가 거래일이고 18:00 KST(09:00 UTC)가 지났을 때만 쓴다(`writer_session`). 따라서 09:00~15:00 UTC 사이에서만 쓸 수 있고, 15:00 UTC(KST 자정) 이후나 주말·휴장일에는 아무것도 쓰지 않으며 해당 세션은 누락으로 남는다. 영수증 *유효 창*(`window_session`)은 다음 개장(00:00 UTC)까지로 더 길지만 writer가 닿는 범위는 아니다. 템플릿 스케줄은 모두 09:00~15:00 UTC 안에 있고(10:40, 11:40, 13:00, 14:20) 같은 세션만 재시도한다. GitHub cron 지연이 15:00 UTC를 넘기면 그 세션은 기록되지 않으며 이는 모니터가 `MISSED`로 보여준다.

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
