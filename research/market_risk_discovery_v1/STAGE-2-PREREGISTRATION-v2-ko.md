# Stage 2 사전등록 v2 — P1 조건부 정보 검정 (독립 감사 대응)

- **기계 판독 사양:** [`protocol-stage2-v2.json`](protocol-stage2-v2.json). SHA-256은 `protocol-stage2-v2.sha256`에 있다.
- **대체 대상:** v1 사양 `protocol-stage2.json`(SHA-256 `e8bb2aee…c8f6`, PR #365 HEAD `87c824c3`). v1 파일은 그대로 보존한다. v1 하네스(`stage3_execute.py`)는 영구 거부로 바꿨다.
- **조회 상태:** 실제 신용 값과 실제 하락 라벨을 함께 계산한 적은 v1과 v2를 통틀어 0회다. Stage 3도 실행하지 않았다.
- **증거 등급:** `EXPLORATORY_ON_OUTCOME_EXPOSED_HISTORY`. 승격 없음, 운영 변경 없음.

## 1. 무엇을 검정하는가

| 구분 | 질문 | v2에서의 지위 |
|---|---|---|
| **A. 조건부 정보가치** | 가격 특징 경로 X가 주어졌을 때, 신용 플래그 경로 C가 라벨 Y에 대해 정보를 갖는가 | **p값이 가리키는 대상** |
| B. 특정 알고리즘의 증분 성과 | 고정한 M1에 C를 더한 M2가 walk-forward에서 Brier를 낮추는가 | ΔBrier로 **보고**한다. p값의 대상은 아니다 |

- **귀무가설 H0:** X 경로가 주어졌을 때 C 경로는 생성모형 G의 법칙을 따르고, 라벨과 독립이다.
- **방향:** ΔBrier 단측(M2가 더 좋음).

### 왜 바꿨나 (감사 A1)

- v1의 원형 회전은 C와 X의 실제 관계를 깨뜨린다.
  - 실제 신호 쪽에서 corr(C, gap200) = −0.39, corr(C, vol63) = +0.50이다.
  - 플래그는 FAST 정상 월의 9.4%, 스트레스 월의 41~51%에서 켜진다.
- 그래서 M1이 표현하지 못하는 X의 비선형 함수를 C가 대리하기만 해도, 회전 귀무분포에서는 C가 "정보 있음"으로 보인다. 감사가 이 반례를 보였다(ΔBrier +0.026, 회전 p 0.003).
- 회전 p는 위 H0의 유의확률이 아니므로 v2에서는 쓰지 않는다.

## 2. 그대로 두는 것

- 사건 정의(SPY 총수익 첫 −15% 진입, 완전 회복 시 종료)와 126세션 지평.
- 표본: FAST=0 월말 위험집합, gap200·vol63, `WIDEN_3M_ABOVE_EXPANDING_P80`, ALFRED 원공표 빈티지와 판단 시점.
- 학습: 만기된 라벨만 쓰는 연간 walk-forward, 평가 시작 2001년.
- 모형: M0/M1/M2, 리지 λ 1.0.
- 평가 표본: 128행, 양성 23행, 평가 사건 5건.
- **양성 23행은 독립 위기 23건이 아니다.** 5개 사건에 속한다.

## 3. 검정: 조건부 무작위화 검정(CRT, model-X)

1. **생성모형 G**
   - 형태: 로지스틱. 입력은 절편, C(t−1), C(t−2), gap200(t), vol63(t)이며 표준화하고 리지 1.0을 쓴다.
   - 적합 범위: 정의된 337개월 전부, FAST 상태 전부. 라벨은 쓰지 않는다.
2. **귀무 사본:** G로 플래그 경로 전체를 999개 시뮬레이션한다(시드 20261125). 첫 두 달은 관측값으로 고정한다.
3. **통계량:** 각 사본으로 M2를 다시 적합하고 ΔBrier를 계산한다. M0·M1은 플래그를 쓰지 않으므로 그대로다.
4. **p값:** p = (1 + #{사본 ΔBrier ≥ 관측 ΔBrier}) / (1 + 999).
5. **타당성 조건**
   - (i) G가 X 경로가 주어졌을 때 C 경로의 참 법칙이다.
   - (ii) H0이 참이다.
   - 두 조건이 성립하면 p는 어떤 통계량에도 타당하다. M1의 함수형이 틀려도 마찬가지다.
   - (i)이 깨지면 타당성이 깨진다.

## 4. 생성모형 적합성 관문 (라벨 없음, 실행 전에 판정)

- **점검 1(표본 내):** 관측 경로의 통계량 12개(경보율, 1차 자기상관, 평균 지속, C와 gap·vol 상관, 공통표본 경보율, 시대별 3개, vol 3분위별 3개)를 계수 불확실성을 포함한 시뮬레이션 분포와 비교한다.
  - 99.5% 구간 밖 0개, 95% 구간 밖 1개 이하여야 한다.
- **점검 2(시기 분할):** 앞 절반으로 적합해 뒤 절반을 시뮬레이션하고, 반대 방향도 한다. 통계량 10개 중 95% 구간 밖이 1개 이하여야 한다.
- **실패 시:** 판정은 `GENERATOR_INADEQUATE_NO_INFERENCE`이고 p값을 보고하지 않는다.
- **선택 이력:** 후보 5개를 라벨 없이 점검했다(`evidence/stage2v2-generator-selection.json`).
  - 처음 쓴 2차항·상호작용 모형은 시기 분할 점검에서 실패했다.
  - 선형 3종은 모두 통과했고, 그중 선형·리지 1.0을 택했다.
- **실제 데이터:** 통과(표본 내 0/12, 시기 분할 0/10).
- 하네스는 실행 마커를 쓰기 전에 이 점검을 다시 계산하고, 통과하지 못하면 거부한다.

## 5. 판정 규칙

| 판정 | 조건 |
|---|---|
| `DATA_INSUFFICIENT` | 구조 관문 실패(평가 사건 < 3, 평가 행 < 100) |
| `GENERATOR_INADEQUATE_NO_INFERENCE` | 생성모형 적합성 관문 실패 |
| `EXPLORATORY_CONDITIONAL_INFORMATION_SUPPORT` | 적합성 통과, **그리고** ΔBrier > 0, **그리고** CRT p ≤ 0.05, **그리고** 사건 하나 제외 민감도에서 모두 ΔBrier > 0 |
| `DIRECTIONAL_NOT_SEPARATED` | ΔBrier > 0이지만 위 조건 중 하나가 실패 |
| `NOT_DETECTED_UNDERPOWERED` | ΔBrier ≤ 0. "신용 정보 없음"으로 보고하지 않는다 |

- **사건 하나 제외 민감도:** 평가 쪽에서만 해당 사건의 양성 행을 빼고 다시 계산한다. 재학습하지 않으므로 표본 외 검증이 아니다.
- **보고 전용:** 로그손실 차이와 그 CRT p, Brier 기술, 블록 부트스트랩 구간, 사건별 적중·선행·오경보(p값 없음), Calibration, 퍼지 교차검증(실시간 아님).
- **판정 상한:** 어떤 판정도 확증이 아니다. 확증은 전향 기록으로만 한다.

## 6. 실행 가능 여부 판정 규칙 (합성 결과를 보기 전에 고정, `stage2v2_protocol.py`)

다음 셋을 모두 만족해야 `READY_FOR_STAGE_3`이고, 아니면 `NOT_READY_FOR_INFERENTIAL_STAGE_3`이다.

1. 실제 생성모형이 적합성 관문을 통과한다.
2. 모든 귀무 환경(S0~S5)에서 v2 지지 판정률의 Clopper–Pearson 95% 하한이 0.05 이하이고, 점추정이 0.075 이하이다.
3. 모든 귀무 환경에서, 적합성을 통과한 세계에 한정한 CRT 기각률도 같은 기준을 만족한다.

## 판정 결과 (사양 SHA-256 `984f7cceef8d003c4d61c3ecbdf60b88b4dd07283358e5cd02b5509421724d56`)

**`NOT_READY_FOR_INFERENTIAL_STAGE_3`**

- 규칙 1(실제 생성모형 적합성)은 통과했다.
- 규칙 2(지지 판정 크기)는 모든 귀무 환경에서 통과했다(4.6% 이하).
- 규칙 3(적합성을 통과한 세계의 CRT 크기)이 S1·S4·S5에서 실패했다.
  - S1: 8.3% [6.3, 10.8]
  - S4: 7.7%, n=26
  - S5: 6.8% [5.1, 8.8]
- 즉 CRT p값이 이 자료 구조에서 타당하지 않다. 상세는 `NULL-VALIDATION-ko.md`에 있다.
- S2는 관문이 모든 세계를 막았다(n=0, 기록 사항).
- 따라서 Stage 3 추론 실행은 하지 않고, 하네스는 실행을 거부한다. P1은 전향 기록 대상으로 남긴다.


## 7. Stage 3 승인 요건 (READY일 때만 의미가 있음 — 현재 해당 없음)

1. `authorization-stage3-v2.json`을 소유자 승인 후에만 만든다. 다음 7개 키만 허용한다.
   - `protocolSha256`, `pins`: v2 사양과 같아야 한다.
   - `scope`: 아래 값과 정확히 같아야 한다.
     ```json
     {"study":"market-risk-discovery-v1","stage":"STAGE_3_P1","hypothesis":"P1",
      "protocolFile":"research/market_risk_discovery_v1/protocol-stage2-v2.json",
      "action":"EXECUTE_ONCE_HISTORICAL_EXPLORATORY","maxExecutions":1,
      "excludes":["MERGE","OTHER_STUDIES","PRODUCTION_CHANGE","PROTOCOL_CHANGE","RERUN","STRATEGY_PROMOTION"],
      "protocolSha256":"<v2 사양 해시>"}
     ```
   - `approvalQuote`: `P1 Stage 3 v2 1회 연구 실행을 승인한다. protocol-stage2-v2 sha256:<해시>` 문장을 포함해야 한다.
   - `approvedBy`
   - `approvedAtUtc`: 과거 시각, 시간대 포함.
   - `authenticity`: `UNAUTHENTICATED_FILE_RECORD_OF_OWNER_APPROVAL`. 이 파일은 사람의 신원을 암호학적으로 증명하지 않는다. 승인 범위와 실행 범위가 같다는 것만 확인한다.
2. **검증:** `python -m research.market_risk_discovery_v1.stage3_execute_v2 --verify-only`
3. **실행:** `python -m research.market_risk_discovery_v1.stage3_execute_v2 --execute`
   - 검증과 라벨 없는 적합성 재계산을 통과해야 한다.
   - 그다음 `O_CREAT|O_EXCL`로 마커를 배타 선점한다. 선점에 실패한 프로세스는 아무것도 계산하지 않는다.
   - 실패해도 마커는 남고 실패 기록이 공개된다. 재실행은 거부된다.
   - 결과는 덮어쓰기를 금지한 채 공개된다.
