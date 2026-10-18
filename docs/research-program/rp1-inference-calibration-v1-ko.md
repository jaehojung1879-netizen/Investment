# rp1-inference-calibration-v1 (Track A / WP1) — 6·12개월 주장의 추론 보정

**성격:** 합성 데이터 전용 사전등록. 실제 종목 수익률, 라벨, 승자 표시, 전략 성과는 읽지 않는다. 저장소 데이터 중 읽는 것은 거래소 달력(날짜)뿐이다.
**프로토콜:** `docs/research-program/specs/rp1-inference-calibration-v1.json` (+ `.sha256`). `pipeline/rp1_inference_calibration.py`의 `build_spec`가 정의하는 내용과 바이트 단위로 같아야 한다.

## 1. 질문

우리 표본 길이와 겹침 구조에서 H126(6개월)과 H252(12개월) 초과수익 주장을 calendar-time SN 구간이 명목 수준대로 검정할 수 있는가? 이 연구는 그 답만 낸다.

## 2. 재사용(변경 없음)

- **엔진:** v4 엔진 그대로 호출한다. 엔진 파일 sha256은 v5 `FORMAL_PINS`와 대조한다.
  - `simulate_replicate`
  - `statistic_designs`
  - `calendar_time_series`
  - `calendar_time_sn_interval` (U1 = 66.57, 양측 97.5%)
  - `replicate_intervals`
  - `decide_statistic`
- **v5에서 키 단위로 그대로 상속:**
  - DGP 6종 (v4 4종과 지속 예측변수 2종)
  - 기하: 60종목, 5세션 간격
  - 선택 비율
  - 확정 통계 5종. rankIC는 기술통계로만 쓴다.
  - 수용 임계값
  - Monte Carlo 판정 수준
- **반복 수:** v5 정밀도 규칙을 재계산해 R = 8,000으로 고정한다 (`v5.chosen_replicates()`).
- **판정:** Clopper–Pearson 3상태 (PASS / FAIL / INCONCLUSIVE).
  - PASS 쪽은 단측 0.025를 쓴다.
  - FAIL 쪽은 0.05를 등록된 모든 판정 수로 Bonferroni 조정한다.

## 3. 새로 정한 것 (네 가지뿐)

1. **셀:**
   - H252: 78주, 312주, 실제 깊이 660주(KR), 662주(US)
   - H126: 78주, 312주, 실제 깊이 688주(US)
   - 6 DGP를 곱해 총 42셀이다.
   - 실제 깊이는 XKRX/XNYS 달력에서 셌다. 2013-01-01 이후 주간 마지막 세션 중 2026-09-14까지 H세션 창이 성숙한 신호일 수다.
2. **FAIL 쪽 판정 수:** 42 × 5 × 3 = 630.
3. **시드:** 20261018. 결과 이전에 고정했고 기존 모든 시드와 다르다.
4. **기술적 검정력 판독:** 판정에는 쓰지 않는다. 귀무 복제에서 정확히 계산한다(4절).

엔진에는 지역 파라미터가 없다. 그래서 지역은 실제 깊이로만 들어가고, KR과 US의 H252는 78·312주 셀을 공유한다.

## 4. 판정 규칙 (결과 전 고정)

- **주장의 판정:**
  - 주장(시장, 지평)은 **실제 깊이**의 6개 DGP 셀이 모두 PASS일 때만 `CALIBRATED_FOR_PRIMARY_INFERENCE`이다.
  - 그중 하나라도 FAIL이면 `NOT_CALIBRATED_FAIL`이다.
  - 나머지 경우는 `NOT_CERTIFIED_INCONCLUSIVE`이다.
  - 78·312주 셀은 깊이 시나리오로 보고만 한다. FAIL 쪽 다중성 수에는 들어가지만 주장 판정에는 쓰지 않는다.
- **Study A 분기** (`03-studies-abc-ko.md` §A):
  - KR: H252가 보정되면 H252, 아니면 H126 (v5에서 보정됨).
  - US: H252, 그다음 H126 순서로 본다. 둘 다 아니면 주 확정 주장은 없다. US Study A는 기술적 분석 또는 전향적 검증으로만 진행한다.
- **보정 실패 후의 금지 사항:** 재시드, 반복 수 증가, 임계값 완화, 다른 구간으로 대체, 재실행.

## 5. A0 MDE에 주는 제약

- **검정력 판독의 원리:**
  - 균일 누적 위치이동(효과 θ가 매 달력주 기여 D(w)에 θ·x(w)를 더함)에서 SN 정규화항은 변하지 않고 추정치는 정확히 θ만큼 이동한다.
  - 따라서 하한이 0을 넘을 조건은 θ > halfWidth − estimate 이다.
  - 귀무 복제에서 이 값의 80% 분위수가 MDE80이다.
  - 단위가 없는 형태로 `mde80InEstimatorSd`(추정치 표준편차의 배수)를 보고한다.
  - 분산이 알려진 경우의 기준값은 z₀.₉₈₇₅ + z₀.₈ ≈ 3.08이다.
- **A0에 넘기는 계약:**
  - A0는 보정된 지평에서만 주 검정을 한다.
  - A0 MDE는 `mde80InEstimatorSd × SE_실제`로 산출한다.
  - 이 구간은 양측 97.5%다. 따라서 A0 문서의 "단측 2.5%"보다 보수적이다.
  - 보정되지 않은 95% 구간이나 정규근사 SE를 대신 쓸 수 없다.
- **비중첩 창 수의 한계:** H252는 약 13개, H126은 약 27개다. SN 구간의 꼬리가 무거우므로 MDE 배수는 3.08보다 클 것으로 예상한다. 정확한 값은 정식 결과에서 나온다.

## 6. 실행 규칙

- **정식 실행은 한 번이다.** 사양 커밋 이후, 다른 어떤 정식 복제보다 먼저 `scripts/run_rp1_inference_calibration.py formal`을 실행한다.
  - 출력 바이트는 그대로 `docs/research-program/results/rp1-inference-calibration-v1-result.json`에 커밋한다.
  - 결과의 `specSha256`가 이 사양의 digest와 같아야 결과로 인정된다.
- **워크플로 파일은 추가하지도 수정하지도 않는다.** 이유는 두 가지다.
  - 워크플로 인벤토리와 센서스는 봉인 사양에 바이트 고정되어 있다.
  - `tests/test_rp1_c1_us_wp4d.py`는 C1 호스트 외 어떤 워크플로 경로 변경도 거부한다. C1 코드는 수정 금지다.
  - 따라서 GitHub 측 검증은 기존 `Tests` 워크플로가 맡는다. `pytest -q`가 정식 시드로 고정 셀(IID_SHARED, PERSISTENT_SHARED_HEAVY_TAILED_PERSISTENT_PREDICTORS의 H252/78주, 8,000회)을 다시 계산한다.
  - 정수 개수, 상태, 판정은 정확히 같아야 한다. 부동소수는 상대 1e-9 이내여야 한다. 인터프리터 빌드 간 libm 마지막 비트 차이는 보고하되, 판정에 흡수하지 않는다.
- **추가 재현:** `reproduce` 모드로 모든 DGP의 H252/78주와 H126/78주 셀을 같은 시드로 재계산할 수 있다.
- **개발용 smoke:** 다른 시드와 최대 50회 반복만 허용한다. 판정에 쓰지 않으며 커밋하지 않는다.
- **재실행 금지:** 결과가 나온 뒤에는 재시드, 재실행, 반복 수 변경, 임계값 변경, 셀 변경을 하지 않는다. 이런 변경에는 새 프로토콜 식별자가 필요하다.

## 7. 정식 결과 (사양 `c4270baa…`, 시드 20261018, R = 8,000)

- **결과 파일:** `docs/research-program/results/rp1-inference-calibration-v1-result.json`, sha256 `19a78059e7db002f30e9b7cd3935672a0f3d88a10d7be8a88f1f6d30aa4e8664`.
- **실행 환경:** 로컬 실행 1회. Python 3.13.16, numpy 2.3.1, scipy 1.16.0, BLAS 스레드 1개, 4 worker, 1,922초.
- **셀 결과:** 42셀 중 PASS 30, INCONCLUSIVE 9, FAIL 3.
  - PASS가 아닌 셀은 모두 **78주** 깊이 시나리오다.
  - FAIL 3셀은 공통 충격이 강한 PERSISTENT_SHARED_HEAVY의 H126·H252, 그리고 heavy-tailed 지속 예측변수 DGP의 H252다. 셋 모두 dateMean·selectedMean의 `MATERIAL_UNDERCOVERAGE`였다.
  - 전체 `primaryStatus`는 깊이 시나리오를 포함한 연언이므로 FAIL이다. 이는 주장 판정이 아니다.

| 주장 | 실제 깊이 | 비중첩 창 | 실제 깊이 판정 | 312주 | 78주 |
|---|---|---|---|---|---|
| KR H252 | 660주 | 13.1 | **CALIBRATED_FOR_PRIMARY_INFERENCE** (6/6 PASS) | PASS | FAIL |
| US H126 | 688주 | 27.3 | **CALIBRATED_FOR_PRIMARY_INFERENCE** (6/6 PASS) | PASS | FAIL |
| US H252 | 662주 | 13.1 | **CALIBRATED_FOR_PRIMARY_INFERENCE** (6/6 PASS) | PASS | FAIL |

- **실제 깊이에서의 수치** (6 DGP × 5 통계):
  - 최소 coverage: 0.9650 (KR H252), 0.9696 (US H126), 0.9670 (US H252). 명목 0.975보다 약간 낮지만 0.95 바닥은 Clopper–Pearson PASS 하한으로 넘는다. 최소 PASS 하한은 0.9607이다.
  - 최대 positive false positive: 0.018.
- **Study A 분기:** KR = H252, US = H252. 두 시장 모두 H252를 주 검정 지평으로 쓸 수 있다. US는 H126도 보정되었다.
- **78주의 의미:** 짧은 표본(약 1.5년)에서는 이 구간으로 6·12개월 주장을 판정할 수 없다. 전향적 검증은 312주에 근접해야 주 추론이 가능하다.

### A0 MDE 함의 (기술적, 판정에 쓰지 않음)

- **MDE 배수:** 실제 깊이에서 MDE80은 추정치 표준편차의 **4.10–4.33배**다 (보정된 97.5% SN 구간, 80% 검정력). 분산을 아는 경우의 기준값 3.08배보다 약 35–40% 크다. 하한 기준 반폭은 약 2.5–2.8 SD다.
- **A0 계약:**
  - MDE₈₀ ≈ 4.3 × SD(추정치)로 계산한다. 보수적으로 통계·DGP 최대값을 쓴다.
  - A0 목표 "MDE ≤ 4pp/년"을 만족하려면 연환산 추정치 SD가 약 **0.92pp/년 이하** (4 ÷ 4.33)여야 한다.
  - 03 문서의 예시 SE 2.3pp라면 MDE는 약 9.9pp/년이다. 정규근사 6.5pp보다 크다.
  - SD(추정치)는 실제 데이터에서 보정된 SN 구간의 반폭으로 역산한다 (SD ≈ 반폭 / 2.7). 보정되지 않은 HAC/정규 SE로 대신하면 MDE를 과소평가한다.
