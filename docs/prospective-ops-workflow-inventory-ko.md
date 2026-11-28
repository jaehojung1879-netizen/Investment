# 전향 기록 운영 워크플로 인벤토리

## ACTIVE

| Workflow | Trigger | Write boundary |
|---|---|---|
| `prospective-ops.yml` | 평일 UTC 10:40, 11:40, 13:00, 14:20 및 main 수동 실행 | 원격 읽기·Actions 상태 아티팩트가 기본. 소유자 인수 승인과 기존 writer 종료 확인 후에만 고정 writer와 상태 스냅샷 게시 가능. |

기존 네 개의 업무 인벤토리는 당시 업무를 고정한 바이트로 보존한다. 이 운영 인벤토리는 새 업무 추가분이다.
