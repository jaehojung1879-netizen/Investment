# US 현금 수익성 H63 — 단일 소유자 승인 P4 탐색 실행 설계 (다음 PR)

이 문서는 **설계**다. 이 PR은 P4를 실행하지 않았고, 신호일 이후 가격·새 IC·실현 성과를 읽지 않았으며, 일회 연구 예산을 쓰지 않았다.
승인 기록, 실행 워크플로, 잠금 ref는 만들지 않았다. 기존 표본(마지막 성숙 신호일 2026-06-05, 성숙·정의 코호트 692개)은 그대로 보존하며
임의의 2026-09 절단은 두지 않는다.

**실행하는 연구는 독립적 알파 확증이 아니다.** 결과가 노출된 역사(2013–2026)에 대한 `EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_US_HISTORY`
무익성 선별이며, 표본은 생존 편향을 가진다.

## 1. 현재 상태 (`us-cash-profitability-exploratory-readiness-v2.json`)

| 구분 | 상태 | 분류 |
|---|---|---|
| 보정 준비도 (부모 P3 + 보충 150–244) | **PASS** — 정의 날짜 700개의 이름 수 범위가 모두 보정됨 | 기술 (완료) |
| 이탈 종목 가격 부재 (324개 중 212개) | CONDITIONAL — 고치지 않음, 계속 공개 | 소유자 수용 |
| 멤버십·식별 한계 (스냅샷 21개 공백 > 45일, 최대 769일; 모호 식별 7,260 구성원-날짜 제외; 검증된 개명 14개) | CONDITIONAL — 고치지 않음 | 소유자 수용 |
| 결과 노출 역사 | CONDITIONAL — 해결 불가 | 소유자 수용 |
| 소유자 승인 기록 | **BLOCKED** (의도) | 소유자 결정 |
| 영속 일회 잠금 | **BLOCKED** (의도) | 기술 (다음 PR) |
| 고정 입력 식별자 14개 | 현재 main에서 모두 재현됨 | 기술 (확인 완료) |

과학적 준비도는 CONDITIONAL, 실행 준비도는 BLOCKED(소유자 승인 + 잠금 두 가지)다. 최근 재무상태표 누락(2026-10-07~10 수집분 618건)은 P4를 막지 않는다
(마지막 성숙 신호일 이전에 보이는 항목은 6건·5종목뿐, 고정 입력의 일부). 전향 등록만 막으며, 이 연구의 범위 밖이다.

## 2. 다음 PR의 최소 범위 (이것이 마지막 준비 PR)

데이터 소스 조사가 아니다. 아래 다섯 가지만 한다.

1. **하네스 식별자 확장.** `scripts/run_us_cash_profitability_exploratory.py`의 `identities()`에 보충 보정 프로토콜·결과 해시와 readiness v2 해시를 추가한다.
   (이 파일의 해시는 승인 기록이 고정하므로, 승인은 이 PR이 병합된 **뒤** 작성한다.)
2. **소유자 위험 수용 검사.** `authorize()`가 승인 기록의 `ownerAcknowledgements`(§3)에 필수 항목이 모두 `true`인지, `ownerLogin`이 저장소 소유자인지 확인한다.
3. **일회 잠금 워크플로.** `.github/workflows/us-cash-profitability-exploratory-v1.yml` — `workflow_dispatch` 전용, KR 일회 연구의 잠금 방식 재사용(§4).
4. **봉인 스크립트.** `scripts/seal_us_cash_profitability_exploratory_v1.py` — 실제 `main()` 가드를 가지며, 테스트가 실제 서브프로세스로 실행한다(통합 연구 봉인이 가드 없이 조용히 no-op이 된 전례).
5. **합성 테스트.** 가짜 GitHub API와 임시 저장소로 승인·잠금·2차 시도 거부를 검증한다. 실제 결과는 읽지 않는다.

하지 않는 것: 소스 복구(SEC/Finnhub/Yahoo), 총자산 대체 추정, 절단, 보정 재실행, 가설·피처·통제·지평·임계값 변경, 승격, `liveValidated`.

## 3. 소유자 명시 위험 수용

소유자가 직접 커밋하는 `docs/us-readiness/us-cash-profitability-exploratory-authorization-v1.json`(현재 없음). 형식:

```json
{
  "contract": "US_CASH_PROFITABILITY_EXPLORATORY_V1",
  "authorizes": "ONE_EXPLORATORY_EXECUTION",
  "ownerLogin": "<저장소 소유자 GitHub 로그인>",
  "acknowledgedAt": "<UTC 시각>",
  "ownerAcknowledgements": {
    "SURVIVOR_CONDITIONED_SAMPLE": true,
    "ABANDON_MAY_REFLECT_MISSING_DEPARTED_NAMES": true,
    "CONTINUE_IS_NOT_CONFIRMATION": true,
    "OUTCOME_EXPOSED_HISTORY_EXPLORATORY_ONLY": true,
    "MEMBERSHIP_GAPS_AND_IDENTITY_EXCLUSIONS": true,
    "CALIBRATION_IS_SYNTHETIC_AND_DOES_NOT_COVER_INFORMATIVE_MISSINGNESS": true,
    "ONE_SHOT_NO_RERUN_NO_RESEED_NO_THRESHOLD_CHANGE": true,
    "NO_PROMOTION_NO_LIVEVALIDATED_NO_PRODUCTION_USE": true,
    "LAST_MATURED_SIGNAL_DATE_2026_06_05_PRESERVED_NO_CUTOFF": true
  },
  "pinnedIdentities": { "<사전점검 식별자 14개 + 추가 식별자 그대로>": "..." }
}
```

- `pinnedIdentities`는 `identities()` 출력과 **키 집합까지 정확히** 같아야 한다(기존 `authorize` 규칙). 하나라도 다르면 결과를 읽기 전에 거부한다.
- 이 기록은 AI나 자동화가 작성하지 않는다. 소유자 커밋이어야 하고, 워크플로가 커밋 작성자를 확인한다.

## 4. 결과를 읽기 전 원자적 영속 잠금

순서(앞 단계의 실패는 예산을 쓰지 않는다):

1. 병합된 `main`의 `workflow_dispatch`에서만 시작(다른 ref 거부).
2. 승인 기록·식별자 14+개·하네스 파일 해시·보정 결과(부모와 보충)·결과 파일 부재를 확인. 결과를 읽지 않는 검사만.
3. 합성 자체 점검(투입된 발명 세계에서 하네스가 완결, 카운터 `outcomeReads = 0`).
4. **잠금:** `refs/tags/us-cash-profitability-signal-v1-exploratory-lock`과 `…-lock-<specSha256>`를 `POST /git/refs`로 원자적으로 생성한다.
   이미 있으면 422 → 거부. `POST`와 `GET`만 사용하며 ref를 이동·삭제하지 않는다.
5. 마커를 쓴다(`outcomeReadsBeforeThisMarker == 0`).
6. 그 뒤에야 `read_outcomes`가 처음 호출된다.

**잠금 이후의 실패는 예산을 영구히 소진한 것으로 본다.** 재시도·재시드·임계값 조정은 없다. 정확한 바이트로 이미 쓰인 산출물의 복구만 허용한다.

## 5. 두 번째 시도의 거부 (겹겹이)

- 잠금 접두사 아래 **어떤** ref라도 있으면 거부(스펙 해시가 달라도 마찬가지 — 스펙을 고쳐 다시 여는 길을 막는다).
- 커밋된 결과 파일이 있으면 거부(기존 로컬 가드 유지, 단 이것만으로는 일회성이 아니다).
- 결과 아티팩트가 있고 만료 전이면 거부.
- 승인 기록은 한 번의 실행에만 쓰이며, 승인 해시가 마커와 결과에 기록된다.

## 6. 결과의 봉인과 감사

- 실행 산출물: 결과 JSON(식별자, 카운터, 판정, 승인 해시), 마커, 잠금 ref 두 개.
- `seal` 작업: 실행 ID·아티팩트 다이제스트·파일 목록·마커·스펙·잠금 ref 두 개를 검증하고 정확한 바이트를 새 브랜치에 복사한 뒤 **Draft PR 하나**만 연다. 병합·Ready 전환 없음.
  Draft PR API 거부는 `RECOVERABLE_SEAL_HANDOFF_FAILURE`로 처리하고 재실행하지 않는다.
- `postoutcome-audit` 워크플로(읽기 전용, 잠금·마커·허가 참조 금지 — AST 테스트): 결과 재구성이 봉인된 결과를 재현하는지 확인한다. 불일치는 해석을 멈춘다.
- 결과 파일은 `docs/results/`에서 봉인 PR 외에는 편집하지 않는다.

## 7. 판정 해석 (프로토콜 규칙 하나뿐)

| 판정 | 조건 | 의미 |
|---|---|---|
| `ABANDON_BEFORE_PROSPECTIVE_COLLECTION` | 보정된 단측 95% 상한 ≤ 0 | 전향 수집 전 중단. **이탈 종목 부재가 일부 원인일 수 있다.** 독립적 반증도 아니다 |
| `CONTINUE_TO_PROSPECTIVE_REGISTRATION_REVIEW` | 그 밖의 모든 경우 | 전향 등록을 **검토할** 허가일 뿐이다. 하한 > 0이어도 "개발 표본에서 지지됨"으로만 기록하며 확증·승격·생산 반영·투자 결정 근거가 아니다 |
| `NOT_EVALUABLE` | 정의·성숙 코호트 260개 미만, 구간 정의 불가, 미해결 코호트 10% 초과 | 결과 없음 |

어떤 판정도 생존 편향이 없는 표본이라는 뜻이 아니다. 독립 확증은 전향 데이터만 줄 수 있다.

## 8. 남은 차단 요인 분류

| 차단 | 분류 | 해소 방법 |
|---|---|---|
| 승인 기록 없음 | 소유자 결정 | §3 기록을 소유자가 커밋 |
| 영속 잠금 없음 | 기술 | §2 다음 PR |
| 하네스 식별자에 보충 보정 미포함 | 기술 | §2-1 |
| 생존 편향·정보성 결측 | 소유자 수용 | 고치지 않음; 편향 상한 민감도가 필요하면 실행 **전에** 새 프로토콜 버전으로 등록 |
| 멤버십·식별 한계 | 소유자 수용 | 고치지 않음 |
| 결과 노출 역사 | 소유자 수용 | 해결 대상 아님 |
| 재무상태표 누락(전향 한정) | 별도 작업 | P4와 무관 |
