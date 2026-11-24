# 실험 1 — 역사 예측 비교 계획 (실행 승인 패킷)

- **사양:** [`exp1-protocol.json`](exp1-protocol.json). SHA-256은 `exp1-protocol.sha256`에 있다.
- **구현:** `exp1_design.py`, `exp1_panels.py`, `exp1_inputs.py`, `exp1_execute.py`. 계산 핵심(`stage2_design`, `panels`, Stage 1 원장)은 바꾸지 않고 재사용한다.
- **현재 상태:** 미실행. 실제 신호와 라벨을 결합한 계산은 0회다.
- **#366과의 관계:** #366의 P1 Stage 3(추론) 실행이 아니다. #366의 봉인 결정(`NOT_READY_FOR_INFERENTIAL_STAGE_3`)은 그대로 둔다.

## 1. 예측 대상 (Stage 1 그대로)

- **라벨:** SPY 총수익(SSGA 분배 재투자)이 판단 다음 세션부터 126세션 안에 처음으로 −15%에 진입하는가.
- **사건 처리:** 사건은 이전 고점을 완전히 회복하면 끝난다. 사건 중인 시점은 위험집합에서 제외하고, 남은 세션이 126 미만이면 우측 검열한다.
- **판단 시점:** 월말 XNYS 종가 이후다.
  - 신용은 판단일 전날 유효한 ALFRED 빈티지를 쓴다.
  - VIX·VIX3M은 판단일 종가를 쓴다. 없으면 5일 이내의 직전 종가를 쓰고, 이후 종가는 절대 쓰지 않는다.

## 2. 모형과 표본

| 모형 | 입력 | 표본 A (1998-03~) | 표본 B (VIX3M 정의) |
|---|---|---|---|
| M0 | 기저율 | ○ | ○ |
| M1 | gap200, vol63 | ○ | ○ |
| M2 | M1 + 신용 플래그 | ○ | ○ |
| M3 | M1 + 신용 확대 z | ○ | ○ |
| M4 | M1 + VIX | ○ | ○ |
| M5 | M1 + VIX/VIX3M − 1 | — | ○ |

- **표본 구조(라벨 정의와 신호 존재 여부만으로 확인)**
  - 표본 A: 155행, 평가 시작 2001년, 평가 128행, 양성 23행, **독립 평가 사건 5건**(2008-01, 2018-12, 2020-03, 2022-05, 2025-04). 1998·2000 사건은 학습에만 쓰인다.
  - 표본 B: 첫 행 2012-08, 평가 가능 사건 2건이라 **구조 관문 실패**. 자동으로 `DATA_INSUFFICIENT`로 보고된다.
- **양성 23행은 독립 위기 23건이 아니다.**

## 3. 학습과 평가 (#365에서 그대로)

- **재학습:** 매년 첫 월말에 한 번. 126세션 창이 끝난 라벨만 학습에 쓴다.
- **추정:** 리지 로지스틱 λ 1.0, 학습창으로 표준화. 하이퍼파라미터 탐색은 없다.
- **평가 시작:** 학습 20행 이상과 양성 사건 2건 이상을 처음 만족하는 해.
- **공통 조건:** 같은 표본 안의 모든 모형은 행, 재학습 시점, 학습집합이 같다. 무작위 분할이나 위기 선별은 하지 않는다.

## 4. 출력 (p값 없음)

1. 모형별 Brier, M0 대비 Brier 기술, 로그손실, 보정 구간(0, .05, .10, .20, .40, 1).
2. 경고 품질. 경고는 같은 판단 시점에 모형 확률이 M0 확률의 2배 이상일 때로 사전 고정했다.
   - 사건별: 기회 수, 경고 여부, 첫 경고일, 선행 세션 수.
   - 미탐지 사건.
   - 전체 경고율, 음성 행 경고율, 오경보 행 수와 오경보 구간 수.
3. 기간별 Brier와 M1 대비 ΔBrier(2001~2012 / 2013~2026).
4. 사건 하나 제외 민감도: 평가 쪽에서 해당 사건의 양성 행을 빼고 M1 대비 ΔBrier를 다시 계산한다. 재학습하지 않으므로 표본 외 검증이 아니다.
5. `forecastImprovementObserved` 표시: M1 대비 ΔBrier가 전체, 두 기간 모두, 모든 사건 제외 민감도에서 양수인지. 서술 표시이며 §7 투자 단계를 **제안할 수 있는지**만 정한다.

**해석 규칙(사전 고정)**
- 어떤 결과도 확증이나 통계적 입증으로 쓰지 않는다.
- 부정적 결과가 나와도 변수를 바꾸거나 추가 실험을 자동으로 만들지 않는다.
- 평가 사건이 5건이라 차이가 우연일 수 있다는 점을 결과와 함께 적는다.

## 5. 계산 범위와 비용

- 155행, 모형 5개(표본 A), 재학습 26회. 실행 시간은 수 초다(합성 테스트 기준 1초 미만).
- 대규모 시뮬레이션이나 재표본은 없다.

## 6. 재현 명령

```bash
python -m research.market_risk_discovery_v1.exp1_inputs
```

```bash
python -m research.market_risk_discovery_v1.exp1_readiness
```

```bash
python -m research.market_risk_discovery_v1.exp1_protocol
```

```bash
python -m research.market_risk_discovery_v1.exp1_execute --verify-only
```

```bash
python -m pytest -q tests/test_market_risk_exp1.py
```

- `exp1_inputs`는 FRED에서 다시 수집하므로 원천 해시가 바뀔 수 있다. 실행에는 커밋된 원본을 쓴다.

## 7. 투자 규칙 (사전 고정, 이번에는 실행하지 않음)

- **조건:** §4에서 `forecastImprovementObserved`가 참인 후보가 있을 때만, 별도 승인으로 아래 규칙을 실행한다. 결과를 본 뒤 규칙을 바꾸지 않는다.
- **노출 규칙**
  - 기준 전략 S1: 월말 FAST ≥ 1이면 다음 달 노출 0.5, 아니면 1.0.
  - 후보 전략 SC: FAST ≥ 1 **또는** 후보 모형 경고이면 0.5, 아니면 1.0.
  - M1 경고를 쓴 SM1을 같은 방식으로 대조한다.
- **체결:** 판단 다음 XNYS 세션 종가. 월말 종가로 체결하지 않는다.
- **비용:** 노출 변화 1단위당 5bp.
- **현금:** BIL 총수익(#358 재구성, 2007-05~). 평가 구간은 2008-01~2026-10이다.
- **비교 대상**
  - SPY 보유
  - 같은 평균 노출의 고정 배분(LEVEL 대조). #316 분해로 TIMING을 분리한다.
  - 같은 실현 변동성의 고정 배분
- **지표:** CAGR, 최대낙폭, 변동성, 상승장 포착, 위기 후 재진입 지연(저점에서 노출 1.0 복귀까지 세션 수), 비용.
- **승격 금지:** Brier가 개선돼도 투자 성과가 개선되지 않으면 전략 성공으로 승격하지 않는다.

## 8. 실행 승인 범위 (소유자가 승인할 정확한 대상)

- **승인 대상:** 사양 `exp1-protocol.json`(SHA-256 `exp1-protocol.sha256` 값)의 **역사 예측 비교 1회 실행**.
  - 모형 M0~M5, 표본 A·B, 위 §4 출력 전부.
- **제외:** 투자 시뮬레이션, P1 Stage 3 추론, 병합, 운영 변경, 전략 승격, 재실행, 사양 변경, 다른 연구.
- **승인 후 절차**
  1. 아래 형식의 `research/market_risk_discovery_v1/authorization-exp1.json`을 만든다.
     ```json
     {"protocolSha256":"<사양 해시>","pins":<사양의 pins 그대로>,
      "scope":{"study":"market-risk-discovery-v1","experiment":"EXP1_HISTORICAL_FORECAST_COMPARISON",
               "protocolFile":"research/market_risk_discovery_v1/exp1-protocol.json",
               "action":"EXECUTE_ONCE_HISTORICAL_EXPLORATORY_NO_INFERENCE","maxExecutions":1,
               "models":["M0","M1","M2","M3","M4","M5"],
               "excludes":["INVESTMENT_SIMULATION","MERGE","OTHER_STUDIES","P1_STAGE3_INFERENCE","PRODUCTION_CHANGE","PROTOCOL_CHANGE","RERUN","STRATEGY_PROMOTION"],
               "protocolSha256":"<사양 해시>"},
      "approvedBy":"<승인자>","approvalQuote":"... 실험 1 역사 예측 비교를 1회 실행하는 것을 승인한다. exp1-protocol sha256:<사양 해시> ...",
      "approvedAtUtc":"<ISO-8601, 시간대 포함>","authenticity":"UNAUTHENTICATED_FILE_RECORD_OF_OWNER_APPROVAL"}
     ```
  2. 검증한다.
     ```bash
     python -m research.market_risk_discovery_v1.exp1_execute --verify-only
     ```
  3. 실행한다.
     ```bash
     python -m research.market_risk_discovery_v1.exp1_execute --execute
     ```
     - 배타 마커를 선점한 뒤 1회 계산한다.
     - 결과는 `results/exp1-historical-forecast-comparison.json`에 덮어쓰기 없이 공개된다.
     - 실패해도 마커가 남아 재실행이 거부된다.
  4. 결과를 빠짐없이 보고하고 커밋한다. 부정적인 결과도 그대로 보존한다.
