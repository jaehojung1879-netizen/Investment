# 전향 기록 운영 · prospective-ops-v1

[인수 승인 패킷](prospective-ops-transition-approval-packet-ko.md)에 설치와 별도 활성화 절차를 둔다. #382는 기존 Claude 코드를 이어받아, GitHub Actions에서 현재 전향 기록을 감시하고 승인된 기업 공시 writer로만 전환할 수 있도록 한다.

| 요소 | 위치 | 역할 |
|---|---|---|
| 레지스트리 | `research/prospective_ops/registry.json` | 연구별 원장, 승인, 기록 위치, 주기·운영 상태 |
| 운영 CLI | `scripts/prospective_ops.py` | 상태, 쓰기 가드, 원격 영수증 검증, 기존 바이트 무결성 |
| Actions | `.github/workflows/prospective-ops.yml` | main에서 평일 19:40 KST와 20:40/22:00/23:20 동일 세션 재시도, 수동 읽기 점검 |
| 연속성 감사 | `scripts/audit_corporate_receipt_continuity.py` | 기존 #374의 누락 창 감사 |
| 등록 writer | `8aee189ff453d9bd624a67df5e1e5975bd7d211c` | 고정 커밋의 `live_run`을 별도 worktree에서 호출 |

## 기록과 만기

| 연구 | 기록 및 만기 상태 |
|---|---|
| 기업 이벤트 A1/B1 | 기존 3개 LIVE 영수증, 기록 누락은 `MISSED_NOT_OBSERVED`. 독립 (발행사, 가설) 관측과 H126/H252 달력 만기를 산출한다. 달력 성숙은 가격·비용 적격성이나 경제성 평가를 확정하지 않는다. |
| KR selection challenger v1/v2 accounting | 기존 `ledger.yml`이 기록 및 만기 hooks를 운영한다. 관제는 기존 `publication-status.outcomes.json`의 상태와 카운터를 읽는다. |
| RP1 B-H1 | 기존 `ledger.yml`의 격리 기록기를 관찰한다. 평가 계약이 미등록이면 `BLOCKED_OUTCOME_CONTRACT_NOT_REGISTERED`를 표시한다. |
| Current champion 및 주간 판단 | 기존 두 지역 영수증을 날짜와 시장으로 센다. 원천 조회만으로 적격 성과 판정을 하지 않는다. |
| KR capital events 및 설계·preview | 등록/승인 상태가 잠겨 있다. 기존 [Evidence Registry](../research/next_alpha_program_v1/EVIDENCE-MAP-ko.md)의 승인 및 재실험 제한을 적용한다. |

승인된 원장을 읽을 수 없거나 기존 영수증이 바뀌면 오류다. 유효한 0-event 영수증과 누락은 구별한다. 원래 닫힌 창 수와 누락 수는 계속 표시한다. 인수 시각 이전의 누락을 보존하면서 인수 이후 운영 연속성은 별도로 보여준다. 등록된 주기가 없는 원장은 `OBSERVED_ONLY`이며 조회 성공으로 완전성을 승인하지 않는다.

## 쓰기 경계

- 현재 main의 정확한 워크플로에서만 소유자의 현재 승인을 읽는다. 검증된 소유자 댓글은 실행 때마다 다시 조회한다. GitHub가 Claude 자체의 현재 상태를 조회할 수 없으므로 영구 퇴역은 정확한 종료 readback으로 소유자가 인수 시 확인한다.
- `status-only`는 읽기 권한 모니터와 아티팩트만 실행한다. 서면 인수·등록 해시·정확한 현재 원장을 통과할 때만 기록을 시도한다. 승인되지 않은 프로젝트나 놓친 과거 창에는 새 기록을 만들지 않는다.
- 후속 retry는 동일 세션 원격 영수증을 먼저 확인한다. 등록 writer의 push는 non-force이며 경쟁으로 먼저 올라간 별도 경로는 rebase 이후 보존한다. 같은 세션 충돌에서는 한 쪽이 중단한다. 커밋·리베이스에 실행 환경의 committer identity를 명시한다.
- 세 기존 영수증의 정규 digest·순서와 원장의 바이트 앞부분을 모두 검증한다. GitHub Actions에서의 첫 실운영 성공은 두 적격 세션의 원격 영수증 확인을 요구한다.

## 역사 워크플로 계약

`pipeline/prospective_workflow_maintenance.py`는 새 워크플로와 [운영 인벤토리](prospective-ops-workflow-inventory-ko.md)의 단일 라이브 조합을 정확 바이트로 확인한다. 과거 WP2 워크플로 트리 검사는 검증된 한 추가 파일을 등록 당시 트리 투영에서 제외하고, 나머지 전 경로를 기존 기대 해시와 대조한다. 기존 인벤토리 문서와 바이트 고정 테스트 파일을 보존한다. 테스트의 인벤토리 입력에 새 운영 레이어를 추가해 두 기존 센서스가 **전체 현재 파일 목록**에 대해 ACTIVE/RETIRED 및 커버리지 판정을 수행한다. 기존 기대 해시, 테스트 어설션, formal 실행 관문은 그대로다.
