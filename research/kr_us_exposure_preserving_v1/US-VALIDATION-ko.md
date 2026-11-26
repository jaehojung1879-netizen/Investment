# 미국 계산·공개 입력 검증 상태

미국 어댑터와 고정보유 계산은 설계 `e3e572f` 이후 실행했다. `us.py`, `us_prepare.py`, `us_repair_price.py`, `us_validate.py`와 `inputs/US/`, `results/US/`의 미국 산출물은 최종 실행 상태다. 전체 시장 보고·Holm 가족·운용 NAV 검증은 별도 공통 보고에 합친다.

|검증|결과|
|---|---|
|#350 원 7종 Q020 장부·4종 peer의 endpoint 결과 및 결측 마스크|모두 재현. 최대 절대오차 **2.39×10⁻¹⁵**. 기존 결과를 변경하지 않았다.|
|6/12개월 F·B·원 장부 공통 표본|각 7개 구성 모두 **630/604주**.|
|F−SPY=(F−B)+(B−SPY), F−원 장부 항등식|CSV로 재검산. 최대오차 **1.15×10⁻¹⁶** 이하.|
|long-only 및 자본합|비어 있지 않은 기준·F·peer F 7,826개 책 전부 검사. 최소 비중 양수, 합1 최대오차 **2.23×10⁻¹⁶** 이하.|
|원 COCKTAIL/U1의 native·Q020 슬리브 합산|고정보유 비용 후 초과수익과 최대오차 **2.26×10⁻¹⁵** 이하. 운용 CAGR 귀속으로 해석하지 않는다.|
|원 SPY NPORT-P 28개|모두 원 HTTP200 receipt 및 기존 원문 SHA 일치. 공개 normalized 14,120줄의 SHA 재검산.|
|실제 공시 부분노출 감사|16개 구성×353주. 공개일<판단일·보유기준일 age≤180일, ETF 기준 노출 항등식 및 개별 MEGA 합산 검산. 최대 합산오차 **6.11×10⁻¹⁶** 이하.|
|실제 전체 SPY 복제|**0주·검정 불가**. 현재 CUSIP map·미매핑 tail·업종/가격 결측을 숨기지 않았다.|
|FISV 입력 정정 재생성|별도 `/tmp/us-repair-verification`에서 원 함수·원 cached raw·봉인 기업행위로 재실행. 현 repaired 가격 패널 전체와 동일. 원 close/features SHA 불변.|

신호별 own 표본·매칭 실패·블록 수는 `results/US/matching-summary.json`, 원본 매칭 leg는 `matching-audit.csv.gz`, 모든 새 고정보유 관측은 `cohorts-126.csv.gz`와 `cohorts-252.csv.gz`, `selection-*`, `active-contribution-*`에 있다. `funding-book-schedules.json.gz`와 `funding-donors.json.gz`는 실제 계산한 모든 F·peer F·기준 책과 조달을 보존한다. 기존 native 기여는 `native-component-contributions.csv.gz`, 실제 공시 감사는 `actual-spy-partial-exposure-audit.csv.gz`다.

데이터 품질 한계는 검증 통과로 해소되지 않는다. B는 원 feature의 가격 이력 문턱·평균희석주식수·공시 freshness cache·issuer 연결 한계를 상속한 관측 부분집합이다. 특히 COR 과거 CIK 불일치 사례는 `US-INVENTORY-ko.md`에 적었다. B를 실제 SPY 보유 또는 독립 검증된 완전 PIT 지수로 부르지 않는다. 시총 proxy F−SPY가 양수여도 F−B와 실제 복제 미측정을 함께 판단해야 한다.

```bash
python -m research.kr_us_exposure_preserving_v1.us_validate --private /workspace/batch-inputs/us
```

상세 숫자와 공개 입력·어댑터 코드 SHA는 `results/US/us-validation.json`에 있다. 과거를 다시 본 계산이며 기존 전향 기록을 대체하지 않는다.
