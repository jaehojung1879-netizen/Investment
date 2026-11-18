기존 S2와 미국 전략이 비용 차감 후 ETF를 개선하는지, 종목 선택력·주식 비중·분산·주도주 의존을 구분해 비교합니다. 기준은 한국 #349 `d9ac3ed5`이며 이 정확한 커밋에서 출발한 후속 연구입니다.

- [한국어 보고서](https://github.com/jaehojung1879-netizen/Investment/blob/research/kr-us-strategy-batch-v1/research/kr_us_strategy_batch_v1/REPORT-ko.md), [전체 표](https://github.com/jaehojung1879-netizen/Investment/blob/research/kr-us-strategy-batch-v1/research/kr_us_strategy_batch_v1/TABLES-ko.md), [재실행](https://github.com/jaehojung1879-netizen/Investment/blob/research/kr-us-strategy-batch-v1/research/kr_us_strategy_batch_v1/reproduce.sh), [검증](https://github.com/jaehojung1879-netizen/Investment/blob/research/kr-us-strategy-batch-v1/research/kr_us_strategy_batch_v1/VALIDATION.md)
- 성과 전 `e6786ee`로 KR70·US36개 구성 슬롯, core41·broad115 검정 가족, 시총½~2배 매칭, 만기 자료만 쓰는 연간 LCB/MDD 규칙을 고정했습니다. 가용 US는30개이며 N-PORT6개 슬롯은 입력 미확보로 p=1을 유지합니다.
- 한국 S2 총주식20%·5종목은 공통421/393주에서6·12개월 ETF 순초과 −0.34/+0.16%p(두95% 구간0 포함). L26/L52 CAGR차 +0.12/+0.31%p, MDD −40.02/−40.28%(ETF −40.81%)였지만 양의 CAGR 차이는 음의 산술차와 양의 복리 잔여로 나뉩니다. 판단일에0~5개를 고를 근거가 충분하지 않습니다.
- 미국 가격+사업확인은 신호별 매칭537/511주에서 peer 대비 +0.37/+0.52%p(구간0 포함). U1 주식20%·SPY80%는 ETF 대비 +0.05/+0.18%p였지만 고정 대형 기술주 직접 비중을 ETF로 바꾸면 −0.26/−0.48%p입니다.
- 전체 신호 공통 매칭은 KR33/24주·US0주입니다. 핵심 선택력19개는 표본 부족/구조적 매칭 불가로 검정 미측정이며, 이를 선택력 부재의 증거로 바꾸지 않았습니다. core41·broad115의6개월 Holm 통과는0개입니다. 매칭 가능한 보조 집합(KR complete4신호·US 단일7신호)의 공통 날짜와 선택/ETF→peer/전체3항 분해는 사후 가용성 진단으로 별도 보존했습니다. 원 핵심 가족을 대체하지 않습니다.
- 한국 두 시간순 규칙은 평가 기간 내내ETF, 미국 두 규칙은2020년에만 가격+사업확인50%를 골랐습니다. 미국 post-fit6·12개월 초과는 −0.61/−1.06%p였습니다. 이미 살펴본 과거의 causal replay이며 untouched OOS나 전향 증거가 아닙니다.
- 미국 입력 감사에서 고정 Yahoo 조회 종료일 뒤 CTVA6.665배 분할 누락을 발견했습니다. 새 성과 해석 전 `4710738`로 원 응답에 근거한 입력 정정을 고정했고 admission·신호·구성은 바꾸지 않았습니다. 정정 전 입력은 원 native 평균을1e-17 수준까지 재현했고 정정의 영향·전후SHA·원종가 기준을 별도 공개했습니다.
- 원 한국 S2/K2/혼합을 검산하고, 전 후보 고정보유·실패·매칭·기여·정책 fit/trace·L26/L52 NAV·비용·회전율을 보존했습니다. SPY가 주 기준이며 QQQ는 보조입니다. 기존 전향6파일은 바이트 동일, preview7개를 실제 전향 관측으로 소급하지 않았습니다.

검증: 전체6,819 passed/4 skipped/4 xfailed, 최종 추가 연구18 passed, ruff/compileall/seed·artifact 검증 및 산출물 독립 검산. 원 로그와 정확한 검증 범위는 VALIDATION에 있습니다. 완전 PIT 확인·운영 승격·main 병합·점수 가중치 튜닝·추가 데이터 구매는 수행하지 않았습니다.
