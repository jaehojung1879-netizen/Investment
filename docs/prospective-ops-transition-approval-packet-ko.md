# 운영 전환 승인 패킷 — kr-corporate-information-events-v1 (Claude trigger → GitHub Actions)

연구 사양(`specSha256 1692b5b3…d61d4`), AUTHORIZATION(`c7191d75…15d1e`), 기록기 코드(`8aee189f…d5e1e5975bd7d211c`)는 **변경 없음**. 바뀌는 것은 실행 환경뿐이다.
이 패킷은 승인 요청이며, 소유자 조치 전에는 어떤 영수증도 새로 기록되지 않는다.

## 확인된 현황 (2026-11-25 조회)

| 항목 | 값 |
|---|---|
| `trig_01XwJ7yivCe5uokkmUTk8MWE` | 조회 가능. `enabled=false`(2026-11-09 비활성). 삭제 아님 |
| `trig_013qoRYz6H9UwUosNzCWv69B` (standing session) | **`enabled=true`, 평일 19:40 KST 실행 중, 매일 실패.** 세션 작업 디렉터리가 비어 있어(`not a git repository`) 단계 1~7을 실행할 수 없음. 이것이 모바일 실패 알림의 출처 |
| `trig_01623WK1XcoLsTEkAQUkAmJ7` (capital-event) | 비활성, 미승인 연구 |
| 이 세션에서 `trig_013qoRYz…` 비활성화 시도 | 권한 분류기가 거부 — **적용되지 않음**. 소유자가 직접 비활성화 필요 |
| 유효 영수증 | 3건(11-09, 11-11, 11-12). 11-10, 11-13, 11-16~11-24 창 누락 (11-25 포함 시 9건, `MISSED_NOT_OBSERVED`) |

## 소유자 조치 (순서 고정)

1. **PR 병합** (이 PR). 워크플로는 기본 비활성 상태로 병합되므로 병합만으로 기록이 시작되지 않는다.
2. **Claude trigger 비활성화**: claude.ai 예약 작업 목록 또는 Claude Code에서 `trig_013qoRYz6H9UwUosNzCWv69B`를 비활성화(삭제 불필요). 이후 `trig_01XwJ7…`, `trig_013q…` 모두 `enabled=false`를 `get_trigger`로 재확인.
3. **attestation 커밋**: `research/prospective_ops/attestations/kr-corporate-information-events-v1-single-writer.json`
   ```json
   {"studyId":"kr-corporate-information-events-v1","attestedAtUtc":"<UTC>","attestedBy":"jaehojung1879-netizen","legacyWriterStates":{"trig_01XwJ7yivCe5uokkmUTk8MWE":"DISABLED","trig_013qoRYz6H9UwUosNzCWv69B":"DISABLED"}}
   ```
4. **레지스트리 활성화 커밋**: `automation.enabled=true`, `monitoring.continuityBaselineSession`을 첫 자동 기록 직전 세션으로 설정(과거 누락은 `MISSED_NOT_OBSERVED`로 남고 N에 산입되지 않는다).
5. **Actions 시크릿 확인**: 저장소 시크릿 `DART`(기존 `fundamentals.yml`이 사용)가 유효한지. 값은 노출 불필요.
6. **검증 1회**: Actions → `Prospective ops` → Run workflow(`mode: write`)를 KR 세션 마감(18:00 KST) 이후 1회 실행. 요약에서 `RECORDED_AND_VERIFIED` 확인. 이후 2개 연속 세션 정상 기록 시 #378 종결 기준 충족.

## 변경하지 않는 것

기존 영수증, 등록 사양·승인 해시, 연구 코드, 투자 성과, production 추천·배분, 보호 워크플로, branch protection, 승인되지 않은 연구(`kr-capital-event-prospective-v1`은 UNAUTHORIZED로 표시만).

## 롤백

레지스트리 `automation.enabled=false`로 되돌리면 다음 실행부터 가드가 거부한다. 이미 쓰인 영수증은 append-only로 유지된다.
