# 미국 입력·구현 감사

기준 #350 `36ac329261f8f9000935e524d8a28c2005524c10`, 새 성과 전 설계 `e3e572f`, 가격 한 셀 복구 승인 `ec9a221`. 기존 판단일은 2014-02-14~2026-08-21의 654주, 다음 거래일 종가 체결, 126/252세션 보유다. 원 buy 8.0bp·sell 8.3bp를 ETF·종목 모두에 적용한다. QQQ는 원 2020-09-21 누락 분배 $0.38824 정정을 한 총수익 보조 기준이다.

## 재사용 입력과 장부

|입력|경로·근거|처리|
|---|---|---|
|가격·공시·원 신호|저장소 밖 `/workspace/batch-inputs/us/close.pkl`, `filings.pkl`, `features.pkl`|원본 불변. 기존 features/점수/순위를 다시 고치지 않는다.|
|원 판단일별 장부|`research/kr_us_strategy_batch_v1/results/US/books.csv.gz`|Q020 7개와 원 native COCKTAIL/U1 재사용. 원 신호 함수로 비중을 재검산한다.|
|선택 대조군|원 `common.match_book`, 원 EV.common 후보|동일 sector·시총비 [0.5,2], 절대 log 거리 최소, ticker 동률, 보유 및 이미 쓴 peer 제외. 실패한 전체 장부는 미측정.|
|업종·membership|`research_specs/alpha-opportunity-model-v1-us-membership.json.gz`, `data/research/us-capital-allocation-alpha-v1/sp500-snapshot-sectors.json.gz`|원 strict-earlier MembershipSnapshots·SectorBook 사용. 실제 공시의 업종 감사에도 재무 common 필터를 적용하지 않는다.|
|신원|`docs/results/alpha-opportunity-model-v3-survivorship-audit.json` 및 `research/us_historical_market_recovery_v1/results/security-lineage.json`|기존 official class link·rename 규칙을 상속한다. 새 issuer 추측 없음.|
|공시 선택 신호|정확한 최소 필요 파일 `/workspace/batch-inputs/nport/round8/C2.pkl`|로컬 부재. 원 생성은 `research.followup_round8_v1.us_audit`와 기존 funds/샘플 보유 parquet가 필요하다. 추가 구매·7.4GB 전체 ZIP 다운로드 없음. OW/OW_RESID 가설 슬롯은 미측정으로 유지.|

#350 own paired 선택력 표본은 PRICE 525/499주, PRICE_CONFIRMED 537/511주, VALUE 310/288주, CASH_PROFITABILITY 489/475주다(6/12개월). 이번에는 각 신호의 유효 날짜를 주 표본으로 사용하고, 직접 비교하는 두 신호만 교집합을 쓴다. 전체 654주 축을 유지하는 25/50주 블록, 4,000회, seed 20261118을 재사용한다. 표본·매칭 실패는 새 `results/US/matching-audit.csv.gz`, 원 대조 재현은 `prior-350-bridge.json`에 남긴다.

## SPY 원 공시: 확보했지만 완전 실제 복제는 불가

기존 `docs/us-readiness/us-etf-sec-holdings-cross-check-v1.json`에 있던 **SPY NPORT-P 28개**(보유기준일 2019-09-30~2026-06-30)를 원 URL에서 복구했다. 28개 모두 HTTP 200 및 기존 SHA256과 byte 일치한다. 원 XML gzip은 저장소 밖 `/workspace/exposure-inputs/us/sec-spy/`에 보존한다. 공개할 정규화 자료는 `inputs/US/spy-normalized-holdings.csv.gz`(전체 14,120개 원 보유 줄), URL·공개일·원 SHA·HTTP receipt는 `spy-source-manifest.json`, 자산/잔여 검산은 `spy-reports.json`이다. 원 파서 `snapshot.parse_nport`를 호출하는 재실행 코드는 `us_prepare.py`다.

판단일보다 **공개일이 이른** 보고 중 가장 최근 보유기준일을 쓰고 age≤180일로 제한한다. 최초 가용 판단일은 2019-11-22, 353/654주, 보유기준일 age 최소/중앙/최대는 51/103/151일이다. 2026-06-30 보고는 2026-08-28 공개되어 마지막 판단일 2026-08-21 이후이므로 쓰지 않는다. 이 공시는 공개 지연된 과거 보유이며 판단일의 실제 현재 보유라고 부르지 않는다.

|원 공시 관측 비중|최소|중앙|최대|
|---|---:|---:|---:|
|원 equity / 순자산|99.9419%|99.9845%|100.0207%|
|기존 CUSIP map으로 ticker 후보 매핑|90.5934%|94.1227%|96.5866%|
|판단일 가격·업종 모두 관측|87.7187%|93.8105%|96.5452%|
|미매핑 equity|3.4070%|5.8491%|9.4096%|
|업종 미관측 equity|3.4142%|5.8962%|11.9123%|
|기존 매핑 기준 MEGA 9종 합|16.6491%|27.1996%|37.6527%|

매핑은 `research/us_rank_independent_check_v1/inputs/openfigi-cusip-map.json`의 **현재 composite ticker**다. BRK/B→BRK-B와 같이 유일한 구두점 정규화만 추가했으며 현재 CUSIP map을 과거 신원 증거로 올려 부르지 않는다. 금융·부동산을 포함하고 factor CIK/common 여부는 별도 coverage로 기록한다. 그 필터를 제거해도 모든 줄의 ticker·가격·업종을 완전히 관측한 주는 **0주**다. 미매핑 tail을 수익 0이나 ETF로 대체하지 않는다. netAssets−equity 잔여는 현금·비주식·부채 등이 섞일 수 있어 전부 현금으로 부르지 않는다.

따라서 실제 공시층은 **조건부 부분 업종·MEGA 노출 감사**이고, 실제 전체 SPY 복제 성과층은 검정 불가다. 새 시총 proxy 성과와 구분한다. QQQ 보유 복구는 주 가설에 필요하지 않아 확장하지 않고 기존 총수익만 재사용했다.

## 시총 proxy B와 투자 가능성

B는 기존 #350 feature rows 중 `MEMBERSHIP_CIK`/`PIT_SINGLE_CIK`이며 양의 marketCap을 가진 전원을 cap 비례로 담는다. 재무 common·손익·현금흐름 완전성·금융/부동산 제외를 적용하지 않는다. feature rows 자체의 252세션 가격 이력·업종 관측 문턱은 상속한다. 새 cap-only universe 확장은 쓰지 않았다. cap은 평균희석주식수(일부 동일 공시 NI/EPS 추정)×원 as-traded 가격의 대용치이고 free-float index weights가 아니다. 결측 cap은 0이 아니라 미관측이다.

654주에서 B 이름 수 최소/중앙/최대 272/360/477, 원 common은 41/233/319다. 금융·부동산 B 이름 수는 49/65/103, 그 비중은 9.23/15.25/18.21%다. 원 입력 프레임 `/workspace/exposure-inputs/us/all-membership-cap-sector-frame.csv.gz`는 모든 dated membership, 업종 source/date, cap 결측, factor admission을 분리해 놓았다. 재생성되는 새 `results/US/proxy-coverage.csv.gz`도 기준 후보와 신호 후보의 차이를 보존한다.

원 AccountingCache는 날짜별 accounting age를 검사하지만 cached `reportAgeDays`가 후속 TTM·shares/cap gating으로 전달되는 구현 한계도 상속한다. 예를 들어 원 COR 2014-02-14 row는 reportEnd 2012-12-31인데 cached reportAgeDays 60을 지닌다. 이 날짜 raw COR의 visible CIK는 1490892이지만 ABC→COR 공식 class link의 CIK는 1140859다. 따라서 `PIT_SINGLE_CIK`라는 원 규칙 통과 표시는 모든 과거 issuer·가격 연결을 독립 확인했다는 뜻이 아니다. 원 features를 바꾸거나 stale 자료를 최신 공시라고 부르지 않는다. 이번 결과는 이 원 feature vintage 및 신원·시총 한계에 조건부다.

80% SPY+20% 선택주식 S의 lookthrough는 0.8B+0.2S다. 동일한 5이름·ETF80%를 유지한 채 모든 지수 업종 비중을 맞출 수는 없다. 설계 F는 **B를 직접 복제한 다수 종목 장부**에서 20% 선택 슬리브를 사고 업종×MEGA 셀 안에서 B 비례로 자금을 뺀다. 셀 여력 부족분은 설계상 다른 셀 잔여 여력에 비례 배분하고 잔여 오차를 그대로 기록한다. q나 신호를 축소하지 않는다. ETF80% 구현과 같은 직접 종목 수를 가진 상품이라고 부르지 않는다. 개별 MEGA 보존은 목표가 아니므로 그룹합·개별오차를 함께 감사한다.

실제 주식 주문을 순액 상계하고 원 종목 비용을 적용한다. 직접 복제 자체의 ETF 보수·추적·리밸런싱·현금 차이는 B−SPY에 남는다. **F−SPY=(F−B)+(B−SPY)**, F−원 구성, 동일 peer F 선택효과 및 동일 donor 표본을 보존해 proxy 추적 잔차를 선택력으로 부르지 않는다. 차입/공매도 overlay는 구현하지 않는다.

## 업종 모멘텀·칵테일·U1

업종 모멘텀은 원 common에서 평균 252세션 모멘텀이 가장 높은 업종 전원을 EW로 보유한다. 같은 선택 업종의 같은 전원 EW는 자기 자신이므로 종목 선택 대조가 될 수 없다. 설계 대조군은 **당시 선택 업종을 제외한 나머지 업종에 동일 비중**, 각 업종 안에서 같은 EW 방식이다. 양쪽 주식20%·SPY80%, 구성 이름 수 차이를 기록하며 업종 배분 효과로 해석한다.

원 COCKTAIL은 PRICE/업종모멘텀/VALUE/CASH 각각25%, 중복 이름의 비중을 합친 단일 주문이다. U1은 원 common cap top5 비중을 더하고 그 합만큼 전체 칵테일을 줄인다. 각 고정보유 순초과를 4슬리브 또는 4슬리브+CAP_TOP5로 정확히 합산하고 원 native 및 Q020 양쪽을 저장한다. 원 비용은 동일 endpoint에서 비중에 선형이므로 이 분해가 성립하지만 운용 NAV·CAGR 기여 분해로 해석하지 않는다.

## 재실행

```bash
python -m research.kr_us_exposure_preserving_v1.us_repair_price --private /workspace/batch-inputs/us --inputs /workspace/exposure-inputs/us
python -m research.kr_us_exposure_preserving_v1.us_prepare --private /workspace/batch-inputs/us --inputs /workspace/exposure-inputs/us
# 원 XML cache가 없으면 위 명령에 --fetch를 추가한다(원 28 URL/SHA 고정).
python -m research.kr_us_exposure_preserving_v1.us --private /workspace/batch-inputs/us --inputs /workspace/exposure-inputs/us
```

새 close 사본은 FISV 2025-11-12 null 한 칸만 `257.5199890136719`로 복구한다. 원 nonnull 3,943세션 재구성 최대 상대오차0이며 Yahoo cache 범위 밖 마지막3개 원 nonnull은 손대지 않는다. 원 close SHA `17b4dbcc…74b6c7e`, 원 features SHA `b0092244…b74ea9` 불변을 assert한다. source/기업행위/함수 SHA와 정확히 한 셀 차이는 `fisv-repair-applied.json`에 남는다. 전체 validation과 원·신규 성과 검산 상태는 최종 보고에서 구분한다.
