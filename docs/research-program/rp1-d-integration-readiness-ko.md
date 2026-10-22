# Track D — Evidence-qualified integration readiness

검토 기준: 2026-10-22 UTC, `main@7b0dbad53c46382291699887e1d5ee9364a33d49`.
출발점은 병합된 [#265](https://github.com/jaehojung1879-netizen/Investment/pull/265)의
[`rp1_d_composition_contract.py`](../../pipeline/rp1_d_composition_contract.py)다.
기준 main의 [Tests 39753244037](https://github.com/jaehojung1879-netizen/Investment/actions/runs/39753244037)는 SUCCESS였다.

**판정: D는 입력 자격의 shadow 점검에 준비됐고, 통합 투자 판단·배분에는 준비되지 않았다.**
현재 선택은 활성 종목 0개와 기존 지역 passive ETF 정책 유지다. 새로운 현금 목표는 없다.
이 문서의 제안은 소유자 승인·등록·실행 권한이 아니며, 기존 계약/봉인/설정을 변경하지 않는다.
코드상 `EXPECTED_EXCESS_DEFINITION = UNRESOLVED`, `UPSTREAM_PRODUCER = None`,
`OWNER_APPROVED_C_ARTIFACTS = frozenset()`는 유지한다.

## 1. A/B/C의 실제 상태

| 입력 | main의 구현·산출물 | 증거의 뜻 / D에 부족한 것 |
|---|---|---|
| A-US | `rp1_a0.py`, 병합 #260, [US A0](results/rp1-a0-measurability-v1.json) | H1/H2/H3 측정률 58.127% / 58.092% / 1.030%. 모두 `PROSPECTIVE_ONLY`, A1 `NO_GO`, 경제 단위 `MDE_UNRESOLVED`. 검증된 선택 신호나 기대수익 예측이 아니다. |
| A-KR | `rp1_kr_a0.py`, 병합 #262, [KR A0](results/rp1-kr-a0-measurability-v1.json), [결측 감사](results/rp1-kr-a0-missingness-audit-v1.json) | 714주, 적격 50,462 관측에서 H1/H2/H3 측정률 37.941% / 37.593% / 35.978%, 모두 `PROSPECTIVE_ONLY`. KR A1 `GOVERNANCE_CLOSED`, A2 `NOT_AUTHORIZED`. 최근 52주 측정률 상승은 새 통과 기준이 아니다. |
| A 공통 추론 | 병합 #257, [WP1 합성 보정](results/rp1-inference-calibration-v1-result.json) | KR H252·US H126/H252 추론 구간의 보정이다. `calibrated=True`로 보낼 종목별 기대수익·예측오차 보정이 아니다. 사건 확률 보정도 기대 초과수익 보정을 대신하지 않는다. |
| B-KR | 병합 #264, `rp1_b_state_receipt.py` | `FAST == 2 OR trailing 24m return < 0` 상태 preview. `PROSPECTIVE_PAPER_PREVIEW`, `ledgerWritten=False`; 조건부 선택 효과·C 대비 증분 효과는 검증하지 않는다. live writer·승인·블록 원점 사양도 별도다. |
| C-KR | 병합 #266와 #275 수정, `rp1_c_risk_state_receipt.py` | 동결 함수에 공급된 SLOW/TRANSITION/FAST를 넣어 C0~C3 배수를 계산하는 preview다. 결측 배수는 `None`. 실제 관측의 진위, 현금화 판단이나 노출 정책의 승인을 인증하지 않는다. 기존 KR C 연구는 종료됐다. |
| C-US C1 | 병합 #249~#255, `rp1_c1_us_execution.py`, `rp1_c1_us_validator.py`, [C1 계약](rp1-c1-us-exposure-ladder-replication.md) | 동등성·freeze·재취득·단회 실행기·독립 검증기가 있다. 현재 정식 실행 승인 파일, 결과, 시작 마커는 main에 없다. read-only 원격 조회에서 execution-lock prefix도 0개였다. 과거 재취득 성공은 현재 원천 readiness가 아니다. |
| D | 병합 #265, `qualify_a`, `compose`, 114개 기존 합성 테스트 | 모든 A를 미해결 정의로 차단한다. B는 context, C는 등록 digest가 없으면 미승인이다. 승인됐더라도 `used=False`; 실제 overlay는 구현하지 않는다. production/scripts는 D 모듈을 import하지 않는다. |

확인한 파일은 구현과 이미 공개된 입력 측정 산출물이다. 새로운 역사 수익률·라벨·A1·C1 실행은 하지 않았다.
C1 부재는 결과가 유효하지 않다는 판정이 아니라 **아직 결과 자체가 없다는 사실**이다.

진행 중인 [#277](https://github.com/jaehojung1879-netizen/Investment/pull/277)
(`f266baa9a0eeb10103697bbf16d68dab1fb6ed70`)과
[#278](https://github.com/jaehojung1879-netizen/Investment/pull/278)
(`7c1395a7d41be59fe29cff327727386318b738e3`)는 별도로 읽기만 했다.
전자는 가격 기반 KR challenger, 후자는 PIT DART 확인 가치 challenger이며 둘 다 아직 미병합이다.
`productionEffect: NONE`인 전향 paper 설계이며 아직 성과 증거가 없다.
등록된 향후 `SUPPORTED`도 원 RP1 A의 판정이나 기대수익 보정으로 자동 변환되지 않는다.
각 연구의 선택기·표본·수익 기준·비용·판정 범위를 명시하는 별도 admission이 필요하다.
이 검토는 두 브랜치나 원장을 수정하지 않는다.

## 2. D의 미해결 관문을 분리한다

| 관문 | 지금 코드가 확인하는 것 | 실제 통합 전에 필요한 것 / 담당 |
|---|---|---|
| 선택 증거 | A의 literal `validated=True` | A 소유자의 등록 판정, 정확한 결과·검증기·선택기·증거 창·다중성·원천/경제성 자격의 연결. 불리한 결과와 결측도 보존. A0/event flag/PR 병합만으로 통과 금지. |
| 예측 보정 | `calibrated=True`, 수치와 양의 `uncertaintyPct` | A 담당의 **종목별** 기대 초과수익·예측 불확실성 생산자. 지평·단위·표본·평가/학습 경계·보정 방법·보정 결과가 필요하다. 현재 지역당 하나의 scalar를 후보 전체에 적용하는 v1은 편입 계약이 아니다. |
| 경제적 정의 | basis, 정확한 KR/US benchmark, `UNRESOLVED` 차단 | 아래 단일 비용 정의와 소유자의 비용/여유 관문 결정. `UPSTREAM_PRODUCER`를 이름만 채우는 것은 연결 구현이 아니다. |
| 신호·출처 | 티커 형식, 숫자, 중복 제거 | Workbench Key, 신원·산업, 실제 signal/available/observed 시각, 사양·코드·입력 hash, freshness와 종결/배당/분할 기준. v1은 이 계보를 인증하지 않는다. |
| 0~5종목 | 합계 5 초과 시 전체 shadow 후보 차단, 정렬은 지역/티커 | 소유자가 정한 동점·cutoff·지역 슬롯 규칙과 섹터/위험 제약. 정렬을 투자 순위로 쓰지 않는다. |
| B | 관측 bool만, `used=False` | B를 배분에 쓰려면 전향 조건부 효과와 동일 책에서 C 대비 증분 증거. 부족하면 계속 context로 남는다. |
| C | 등록 digest만 승인 증거로 인식, 현재 registry 비어 있음 | C 결과 봉인·독립 검증 + 별도의 지역/규칙/위험 예산 해석 승인. 연구 execute 승인은 노출 적용 승인이 아니다. |
| 투자 판단 | `activeNames=[]`, `productionAffected=False` | 별도 shadow 경제성 비교와 검토를 통과한 뒤, 소유자의 명시적 통합 판단. 이 작업은 주문·실제 비중을 만들지 않는다. |

따라서 기대수익 정의 **한 상수만** 풀어도 v1이 승인된 입력을 인증하는 것은 아니다.
`CANDIDATES_ELIGIBLE_FOR_SEPARATE_ECONOMIC_VALIDATION`은 별도 검증 후보 목록이라는 뜻이다.
구조적 자격·증거 admission·경제성·포트폴리오 제약·사용자 위험 선호를 하나의 PASS로 합치지 않는다.
B/C 부재는 독립적으로 자격을 갖춘 A의 경제성 검증을 막을 이유가 없다.

## 3. 기대 초과수익과 비용: 제안하는 단일 정의

**제안:** 같은 지역, 같은 투자 원금 기준, 같은 다음 세션 종가 진입과 H세션 지평의
산술 총수익 차이를 `G = E[R_stock,total − R_ETF,total]` (%p/H)로 정의한다.
주식으로 전환했다가 지역 ETF로 복귀하는 데 드는 **추가** 비용을 `C`라 하고,
정규화한 순초과수익은 `N = G − C`, 경제적 관문은 `N > 0`으로 한다.
H252 기대수익을 H126 비용/SE와 조합하거나 연율과 지평 수익을 비교하지 않는다.
기본 벤치마크는 KR `069500.KS`, US `SPY`; C1 PRIMARY의 `^GSPC`와 혼용하지 않는다.

| 생산자가 선언한 basis | 받은 값 | D에서 정규화한 값 | 관문 |
|---|---:|---:|---|
| `GROSS_OF_ROUND_TRIP_COST` | G | G − C | > 0 |
| `NET_OF_ROUND_TRIP_COST` | N | N 그대로 | > 0 |

v1의 `expectedNetExcessPct`라는 필드명은 GROSS도 허용하는 legacy 명칭이다.
향후 생산자 연결에서는 원래 값+basis와 G/C/N을 함께 보존하고 재계산을 대조한다.
NET 선언이 비용 명세·보정 사양 없이 온 경우 신뢰하지 않는다.
`G=N+C`의 대수적 복원만으로 비용이 실제로 포함됐다고 증명할 수 없다.

예를 들어 합성 G=0.8, C=0.5이면 N=0.3이다. NET에서 다시 C를 빼면 −0.2로 잘못 차단한다.
반대로 G=0.3, C=0.5에서 gross만 0과 비교하면 손해 기대를 통과시킨다.
문서의 기존 literal `net > cost`는 N을 이미 C 차감 후로 읽으면 `G > 2C`가 된다.
추가 안전마진이 필요하면 `N > h`라는 **별도 owner 위험 관문**으로 명명하고,
비용 2회 차감을 보수성이라는 이름으로 숨기지 않는다. 이 문서는 h 또는 SE 배수를 고르지 않는다.

### 비용 범위도 고정해야 한다

기준은 이미 보유한 ETF를 계속 보유하는 대안이다. 제안하는 C의 네 leg는 다음과 같다.

1. 진입 때 ETF 매도
2. 같은 전환의 주식 매수
3. 지평 말 주식 매도
4. ETF 재매수

각 leg는 commission + half spread, 매도에는 해당 종목/ETF의 날짜 있는 세금·수수료를 적용한다.
KR 국내 주식형 ETF의 거래세는 0이다. 비용은 교체하는 sleeve 원금의 %p이며 전체 포트폴리오 비중을
두 번 곱하지 않는다. 예측 시에는 신호 시점에 알려진 schedule/추정 가정을 고정하고,
실현 비교에서는 각 거래일의 schedule을 쓴다. 추가 FX/슬리피지 비용이 있으면 별도 명시하고
누락을 0으로 채우지 않는다.

이는 [`weekly_decision.cost_breakdown`](../../pipeline/weekly_decision.py)의
`stockRoundTripPct + benchmarkRoundTripPct = switchCostPct`와 맞춘 보수적 가산 비용 정의다.
실제 현금흐름 재현의 체결 원금 변화와 이 가산 근사는 구분해 기록한다.
원 D 설명의 “종목 왕복 + ETF 매도”에는 ETF 재매수가 명시되지 않았다.
이를 **다음 연결 계약에서 네 leg로 명시하는 안**이며, hash-pinned 원 계약·주간 정책은 수정하지 않는다.
1×/2×/3× 스트레스도 gross G와 λC에서 각각 `N_λ = G − λC`로 계산한다.
기존 NET을 λ번 빼거나 이미 차감한 기준 비용을 재차 차감하지 않는다.

#277의 `kr_selection_challenger.book_result`는 다른 비교다.
paper book과 ETF control이 각각 매수/매도 비용을 부담하고, `netExcessReturn`에는 ETF control 비용의
credit이 들어간다. 기존 ETF 보유에서 출발하는 D 전환 비용과 기준이 다르다.
또한 이는 만기 **실현 결과**이며 현재의 기대수익 예측이 아니다.
이 필드를 D의 NET 예측에 그대로 연결하지 않는다. 미래 admission은 원 gross·leg 명세·control을
명시적으로 대조해야 하며, C1의 이미 비용 차감된 노출 결과도 A의 순선택 알파로 재사용하지 않는다.

## 4. 배분 의사결정 계약: 고정할 것과 owner가 결정할 것

원 [04 §7](04-common-research-contract-ko.md#7-비용과-포트폴리오-제약)의 0~5종목,
섹터당 2종목, 종목당 15% 상한, 잔여 지역 ETF, 레버리지·공매도 없음은 유지한다.
**현재 주간 정책의 지역별 최대 5종목은 D의 KR+US 합계 5종목과 다르다.**
현재 `compose`는 shadow 후보만 나열하므로 이 차이가 실제 비중을 발생시키지 않는다.

| 항목 | 제안 계약 | owner 결정 / 결측 시 동작 |
|---|---|---|
| 지역 자본 | 기존 전략적 KR/US 자본 예산을 외생 입력으로 받는다. 각 지역은 자기 통화·완료 세션을 사용한다. | 목표 지역 비율/허용 범위, 기준 통화, FX 시각·원천·헤지. 미정이면 지역별 기존 ETF 상태만 설명하고 통합 숫자를 산출하지 않는다. 50:50이나 역사 최적 비율을 새 기본값으로 만들지 않는다. |
| 5개 슬롯 | 적격성 판정 후 합계 ≤5. 지역 슬롯과 동점 규칙을 결과 열람 전에 고정한다. | 지역 고정 슬롯 또는 비교 가능한 보수적 net-edge 순위 중 정책 선택. 정렬/입력 순서로 선택 금지. 미등록 상태의 6개 이상은 현재처럼 차단한다. 5개를 반드시 채우지 않는다. |
| 종목 규모 | 15%는 상한이다. 기대수익이나 양의 SE만으로 Kelly/최적 비중을 계산하지 않는다. | 15%의 전체 책/지역 sleeve 분모와 실제 편입 단위. 기존 weekly의 15%는 지역 책 기준이므로 그대로 global 비중으로 복사하지 않는다. |
| 섹터 | 원 섹터당 2종목을 유지하고 투자용 taxonomy와 날짜 있는 분류를 핀한다. | `longterm.maxSectorWeight=0.30`과 `kellyPortfolio.maxSectorWeight=0.45` 중 어떤 문맥/분모를 쓸지 명시. 제안은 D의 15%/2종목과 일관된 30% 상한이나, 적용 분모와 KR/US 공통 섹터 매핑은 owner 확정 전 미해결이다. ETF look-through 위험도 별도로 표시한다. |
| 위험 예산 | 기대 알파와 별도인 손실·집중·유동성/통화 위험 제약을 검사한다. 검증된 위험 측정의 출처·창·단위를 동반한다. | 허용 총 equity 노출, 주식/지역/섹터 한도, 손실 스트레스 한도, 결측/위반 때 보류 규칙. 역사 MDD 최소점·Sharpe 최대점으로 수치를 정하지 않는다. |
| ETF·현금 | 먼저 고정 A+잔여 ETF 책을 만든다. 승인된 C의 배수 m을 그 지역 위험 책 전체에 한 번 적용하고 감축분만 현금으로 분리한다. | C 적용 지역/규칙/유효 기간, 현금 상품·수익/비용, 재진입·결측 상태의 이전 target 처리. owner 위험 예산이 없으면 m=1인 기존 ETF 정책을 유지한다. |
| B | 현재 context만 제공한다. | 독립 조건부 효과와 C 대비 증분 검증 전에는 배수·노출·슬롯에 영향 0. B와 C의 곱으로 중복 감축 금지. |

수학적 검사 예: owner가 고정한 지역 예산을 a_r라 하면 C 적용 전 지역 주식+ETF 합은 a_r,
C 적용 후 위험자산 합은 m_r a_r, 새 현금은 (1−m_r)a_r다.
감축분을 다시 ETF로 채워 m을 취소하거나 C를 주식과 책 전체에 중복 적용하지 않는다.
이는 보존식 설명이며 실제 비중을 산출하는 구현·권고가 아니다.
기존 보유/매도·재진입 비용과 중복 거래 상계 규칙도 최초 경제성 비교 전에 고정한다.

## 5. 미래 A/B/C가 전달할 증거 묶음

공통 envelope는 새 승인 설정이 아니라 **제안 형식**이다. `schemaVersion`, `contractId`, `studyId`,
`region`, `signalSession`, `createdAtUtc`, Workbench `Key`/`sampleId`/legacy mapping,
security identity와 분류 버전, 입력별 `availableAt`/`observedAt`/missing reason,
`evidenceClass`/증거 창/성숙 cutoff, spec/code/input/result/validator의 exact byte SHA-256,
생산 commit와 run URL, validator 상태, 허용 사용 범위를 포함한다.
증거 class별 표본/판정은 분리한다. digest는 내용 식별자이지 서명이나 owner 인증이 아니다.

* **A:** 원 가설/선택기 ID와 등록된 A1 또는 A2 판정, 경제성·신원·산업·종결/배당 기준,
  새 signal의 개별 G/C/N·지평·통화·수익/비용 basis, 불확실성의 정의/단위,
  forecaster/보정 spec와 학습 cutoff·만기 누설 검사·OOS/전향 보정 증거.
  A0나 원 연구와 다른 challenger 결과에는 독립 admission 필요.
* **B:** 현재 관측 상태의 출처/가용성은 context 입력으로 충분하다. 배분 기능은 별도의
  등록 전향 conditional-effect 결과·양쪽 상태의 유효 블록 수·다중성·동일 책 C 대비 증분 검증이 필요하다.
* **C:** 아래 C1 실행 증거와 **별도 owner 해석 artifact**, 최신 지역 state provenance와
  사용자 위험 예산. 지수층 복제는 선택 책에 대한 유효성 증거로 바뀌지 않는다.

## 6. C1 도착 시 받아야 할 형식과 승인 범위

새 C 실행기를 만들 필요는 없다. 기존 실행기는 다음 산출물을 만든다.

| 기존 파일 | D의 미래 검토에 연결할 내용 |
|---|---|
| `result.json` | study/spec/authorization hash, locked main/ref, source freeze, `validationStatus`, `decision`, `interpretation`, `economicReadingStatus`, `cashEconomic` 상태와 scientific spec |
| `validation.json` | `CONSISTENT`, 독립 계산의 checks/tolerance/max difference, primary/economic scope 구별 |
| `manifest.json` | exact file hashes, spec/authorization/source freeze, 실행 카운터·원천 교차검증. manifest 자체 hash도 외부 봉인 참조에 둔다. |
| `execution-started.json` | 두 durable lock의 연결과 값 열람 전 카운터 0, locked main/승인 연결 |
| `report.md` | 수익·위험·상승 미참여·재진입·비용의 해석과 한계; 수치의 기계적 진실은 위 파일과 검증기에 둔다. |

`rp1_c1_us_exposure_spec.RESULT_PATH`/`MARKER_PATH`로 정확 바이트가 검토·봉인된 뒤에만
참조한다. `synthetic-*`/dry-run/템플릿, 재계산한 임의 요약 JSON은 정식 결과가 아니다.
`PRIMARY`는 `^GSPC` 가격지수·현금 0%, `CASH_ECONOMIC`은 별도 scientific hash의
SPY 현금배당 재투자+DTB3다. PRIMARY PASS만으로 ETF 투자 경제성을 인증하지 않는다.
SPY 외부 총수익 대조 미완료와 `UNRESOLVED` scope는 계속 드러낸다.

**두 승인은 분리한다.** 기존
`authorizations/rp1-c1-us-exposure-execution-authorization.json`의 `ONE_FORMAL_EXECUTION`은
연구 결과 열람 승인이다. D에 노출 규칙을 쓰는 승인으로 등록하지 않는다.
그 다음 owner가 검토할 별도 해석 artifact의 초안 형식은 다음과 같다. 이 예시는 승인하지 않는다.

```json
{
  "schemaVersion": 1,
  "contractId": "RP1_D_C_INTERPRETATION_PROPOSED_V1",
  "status": "PROPOSED_NOT_REGISTERED",
  "authorizes": "NOTHING",
  "ownerLogin": "OWNER_APPROVAL_NOT_ISSUED",
  "approvedAtUtc": null,
  "scope": {
    "region": "US",
    "ruleId": null,
    "modelSpecSha256": null,
    "fixedBookContractSha256": null,
    "riskBudgetArtifactSha256": null,
    "effectiveFrom": null,
    "expiresAt": null
  },
  "evidence": {
    "studyId": "rp1-c1-us-exposure-ladder-replication-v1",
    "sealedCommit": null,
    "resultSha256": null,
    "validationSha256": null,
    "manifestSha256": null,
    "executionMarkerSha256": null,
    "executionAuthorizationSha256": null,
    "primaryScientificSha256": null,
    "cashEconomicScientificSha256": null,
    "sourceFreezeSha256": null,
    "economicScopeDisposition": null
  },
  "interpretation": null,
  "acknowledgments": {
    "replicationIsNotValidatedAlpha": false,
    "economicLimitationsReviewed": false,
    "riskBudgetAndOpportunityCostReviewed": false,
    "applyOnceToFixedBookNoBMultiplier": false,
    "noProductionPromotionOrOrders": false
  }
}
```

owner가 검토한 commit/PR과 exact bytes의 hash를 연결하고, 미래 registry는
digest뿐 아니라 위 region/rule/model/book/evidence/budget/유효 기간과 실제 입력을 대조해야 한다.
지금 비어 있는 registry에 항목을 추가하지 않는다. 현재 v1의 digest lookup만으로는 scope를 대조할 수 없다.
승인 후에도 shadow 검증 범위로 제한하고 production의 별도 승인을 암묵적으로 포함하지 않는다.
owner 확인은 문자열 자기 선언이 아니라 owner가 검토한 커밋의 계보를 뜻한다.

동결 해석표를 먼저 따른다. KR은 `NO_CANDIDATE_NOMINATED_CONTROL_RETAINED`이고,
US control 유지/nominee/trade-off/no-protection은
`rp1_c1_us_exposure_spec.interpretation_definition`에 각각 고정돼 있다.
결과를 보고 가장 좋아 보이는 C 규칙을 새로 선택하거나 임계값을 바꾸지 않는다.
C1의 지수 책 결과를 A 선택 책으로 일반화하려면 그 책의 beta/상관과 동일 책 비교가 별도로 필요하다.
결과가 부정적이거나 경제 scope가 미해결이어도 artifact는 이를 보존하며 자동 승격하지 않는다.

## 7. 합성 검증과 발견한 실제 결함

[`test_rp1_d_composition_contract.py`](../../tests/test_rp1_d_composition_contract.py)의 기존 검증은
무입력/미검증/미보정/비용 경계/잘못된 benchmark/NaN/식별자/6개 cap/위조 C 승인/배분 키를 다룬다.
추가한 실제 B/C interface 결합 검증은 **발명한 하락 지수**로 B preview와 C preview를 만들고,
A 없음·사건 플래그만 있음·caller가 검증/보정을 주장하는 입력을 각각 공급한다.
세 경우 모두 passive default, 빈 active/shadow 목록, B/C `used=False`, C 미승인,
`productionAffected=False`를 확인한다. 실제 원장·승인·가격·성과를 생성하거나 읽지 않는다.
기존 합성 registry 테스트의 승인 C도 `used=False`이며 승인만으로 노출을 적용하지 않는다.

**결함 재현:** 기준 main에서 `expectedNetExcessPct=10**400`, GROSS, 정상 비용 0.5를 넣으면
`_num`이 정수를 허용한 뒤 float 비용과의 뺄셈에서 `OverflowError`가 발생했다.
정의가 `UNRESOLVED`여도 발생하므로 정상적인 차단 응답을 반환하지 못한다.
수정은 float 연산 도메인 밖 정수를 `A_NUMERIC_FIELD_UNAVAILABLE`로 거부하는 것뿐이다.
수익률의 경험적 plausibility 상한이나 투자 파라미터를 도입하지 않는다.
양/음 거대 정수 × 세 숫자 필드 × GROSS/NET × 미해결/합성 해결 정의의 24개 회귀가 ETF 기본값을 확인한다.
정상 입력의 qualification/비용/상한/승인 동작은 유지한다.

검증 기록은 PR 설명과 실행 로그에 연결한다. D+B+C 집중 suite는 **525 passed**다.
기존 C byte-equivalence 테스트는 partial clone에 원 head blob이 없어 한 번 실패했고,
해당 commit/blob을 읽기 전용 fetch한 뒤 같은 suite 전체가 통과했다. 테스트/원천은 고치지 않았다.

## 8. 첫 통합 투자 판단까지의 최소 작업

1. **지금:** 이 작은 숫자 결함만 수정하고 본 문서로 증거 인계 형식을 정리한다.
   상수·승인 registry·봉인 파일·원장·스케줄·A/B/C 진행 브랜치를 바꾸지 않는다.
2. **증거 생산은 각 트랙의 일:** A는 권리/현재 PIT/등록·승인 후 전향 기록과 원 판정,
   별도 기대수익·불확실성 보정을 공급한다. KR 역사 재개는 없다. US A1의 NO_GO를 D가 우회하지 않는다.
   원 KR A2 첫 판정은 첫 신호 뒤 36개월이므로 코드 연결로 증거 대기 기간을 단축할 수 없다.
   B는 계속 context일 수 있다. C1은 기존 owner 절차로만 실행·봉인한다.
3. **첫 자격 있는 A/승인된 C가 오기 전:** owner는 §3~4의 경제 단위·비용·cap/지역/섹터 분모·위험 예산을
   결정하고 outcome 경제성 열람 전에 기계 계약으로 고정한다. 아직 선택할 증거가 없는 동안 optimizer를 만들지 않는다.
4. **생산자 형식이 고정되면:** 비봉인 D 경계에 작은 증거 resolver/validator를 연결한다.
   A의 per-name forecast와 등록 판정을 묶고, C의 실제 artifact와 owner 해석의 scope를 대조하며,
   stale/preview/미등록/변조/다른 benchmark·지평/불완전 경제성은 별도 이유로 거부한다.
   caller bool이나 같은 digest의 엉뚱한 region/rule 재사용을 허용하지 않는다.
   실제 artifact 형식이 없는 지금 범용 registry 서비스·수집기·실행기를 만들 필요는 없다.
5. **그 다음 최소 shadow 통합:** 고정된 자본·슬롯·섹터·위험 제약을 적용하고 같은 날짜/모집단/책에서
   ETF → A → 검증된 B(없으면 생략) → 승인된 C를 한 요소씩 비교한다.
   N/비용스트레스·선택/복리·회전율·하방위험/상승 미참여/재진입·현금/ETF를 분리한다.
   이미 노출된 역사를 새 OOS로 사용하거나 역사 수익으로 정책값을 고르지 않는다.
6. **owner 검토:** 이 결과로 최초 통합 투자 판단을 검토한다. 판단의 가능한 결론에는 계속
   0종목+지역 ETF가 포함된다. 자동 주문·실거래·실제 비중 변경·`liveValidated` 승격은 포함되지 않는다.

명확한 코드 결함은 이번 PR 하나로 제한한다. 남은 핵심 병목은 검증된 A 기대수익 생산자와
owner 위험/배분 계약이다. C1 결과만 도착해도 A 알파나 그 생산자는 생기지 않는다.
