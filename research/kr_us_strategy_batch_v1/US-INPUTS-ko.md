# 미국 입력 준비와 복구 경로

이번 입력 준비는 새 전략 성과를 계산하지 않는다. 원 연구의 후보 적격 함수와 가격·공시·특성 생성 함수를 재사용하며, 시총 대조군이나 노출 비중의 결과를 보고 입력을 바꾸지 않는다.

## 원천과 빈티지

- 고정 원천: signal-history `704d7db6d5b00def771aba5d2665d0846d6bc776`, replay-v16 manifest `f0781292f508a123c234ded6d28aa8e84a0dc3cc29500e14989dc0b68f53b4d2`. 2011-01-03부터 2026-09-14까지의 미국 가격과 같은 커밋의 Finnhub 공시를 읽는다. 가격은 3,947세션·635열이며 결측을 채우지 않는다.
- 구성·업종·신원: `research_specs/alpha-opportunity-model-v1-us-membership.json.gz`, `data/research/us-capital-allocation-alpha-v1/sp500-snapshot-sectors.json.gz` 및 원 파일럿의 신원·클래스 연결 파일. 구성 스냅숏은 관측일 기준이며 효력일 이력 전체를 복원한 자료가 아니다.
- 원 연구의 비공개 `us/features.pkl`, `us/yahoo/*.json.gz`는 이 작업공간, Git, GitHub Actions artifact와 release에서 확보하지 못했다. 따라서 2026-11-17 UTC(한국 시간 2026-11-18)에 원 `fetch_as_traded.py` URL·함수를 사용한 **새 Yahoo capture**를 별도로 보존한다. 원 비공개 캐시와 동일한 빈티지라고 주장하지 않는다.
- 원 Yahoo HTTP body, 원 fetch 함수의 parsed cache, 응답 SHA-256, URL, UTC 관측시각은 저장소 밖 `/workspace/batch-inputs/us/{yahoo-raw,yahoo}`에 둔다. 공개하는 것은 입력 감사 집계와 해시뿐이다.

## 입력 처리

`us_prepare.py`는 원 `features.PILOT.load_prices`, `load_filings`, 원 `fetch_as_traded.fetch`, 원 `features.main`을 호출한다. 원 `AsTraded` 검증기의 불일치·짧은 중복 구간·응답 실패 처리를 그대로 적용한다. 원종가나 시총을 역산 값으로 대체하거나, 원 연구의 결과와 종목 수를 맞추기 위해 admission을 바꾸지 않는다.

공시는 `max(availableFrom, acceptedDate)`가 판단일보다 엄격히 이전인 것만 보며 원 180일 신선도, CIK, 회계 완전성 조건을 유지한다. 시총은 원 방식인 공시의 가중평균 희석 주식 수 대용치와 판단일 as-traded 가격의 곱이다. 공시 가시일과 판단일 사이에 분할이 있으면 원 코드대로 시총을 보류한다. 기존 F1 심볼·클래스 연결 및 F2 같은 공시의 NI/EPS 희석 주식 수 보정도 유지한다.

봉인된 주식 가격에는 별도의 `rawClose`, `AdjClose`, 조정계수가 없다. 보존된 필드는 `Close`, `Open`, `High`, `Low`, `Volume`, `date`, `ticker`이다. `price_adjustment.to_total_return`의 FIRST_OBSERVED_SESSION anchor와 봉인된 as-traded 배당·분할을 이용해 원종가를 역산하고 새 Yahoo capture와 대조한다. 이 검산은 입력 감사이며 후보 admission에는 영향을 주지 않는다. SPY처럼 봉인된 기업행위가 없는 ETF의 원종가 역산은 성립하지 않으므로 원 ETF 총수익 지수를 그대로 쓴다.

거래량도 원 분할 처리 기준을 검산한다. `sealedVolume × 판단일까지 누적 분할비율`과 `freshYahooVolume ÷ 판단일 이후 분할비율`을 비교한다. 이는 원 `price_adjustment`의 거래량 기준을 확인하는 절차다. 원 특성 생성기에는 거래량·유동성 적격 필터가 없으며, 이번 입력 준비에서 새 필터를 추가하지 않는다.

원 상태 집계 `VERIFIED 607 / AS_TRADED_SERIES_MISMATCH 8 / AS_TRADED_OVERLAP_TOO_SHORT 13 / NOT_SERVED 7`, 연도별 공통 후보 수와 CIK 검산을 새 입력과 비교한다. 결과는 [us-input-preparation.json](results/us-input-preparation.json)에 저장한다. 전략 기준 수치 재현은 비교 설계가 고정된 뒤 별도로 수행한다.

## 재실행

캐시를 보유한 경우 같은 경로를 재사용한다. 캐시 없이 새로 실행하면 새로운 공급원 관측 빈티지가 생기므로 원 capture와 동일한 입력이라는 주장을 할 수 없다. 정확한 재실행에는 아래 밖의 비공개 입력 폴더와 그 manifest가 필요하다.

```bash
export OMP_NUM_THREADS=1
python -m research.kr_us_strategy_batch_v1.us_prepare \
  --private /workspace/batch-inputs/us \
  --out research/kr_us_strategy_batch_v1/results/us-input-preparation.json
```

`--stage core|capture|repair|features|audit|report`로 준비 단계를 나누어 재실행할 수 있다. 원 HTTP 원문은 덮어쓰지 않는다. 입력 준비 요약의 파일별 SHA-256으로 캐시를 식별한다.

## CTVA 분할 기준 정정

전략 성과 해석 전 별도 커밋 `4710738`의 [INPUT-REPAIR-ko.md](INPUT-REPAIR-ko.md)로 입력 정정을 고정했다. 2026-10-01의 `6665:1000` 분할이 고정 Yahoo 조회 종료일 이후라 누락되어 과거 원종가가1/6.665배로 보였다. 원 검증기는 레벨 오차를 보지 않으므로 VERIFIED607·후보 수가 같아도 시총/가치 입력은 같지 않을 수 있다.

원 응답이 확인한 event 하나만 parsed CTVA의 splits에 출처와 함께 보충하고, 원 AsTraded.close_on 및 특성 생성기를 다시 호출했다. 봉인 역산 가격으로 대체하거나 admission을 바꾸지 않았다. 정정은 반복 실행해도 중복되지 않는다. 이전 features/meta/CTVA parsed 입력은 `/workspace/batch-inputs/us/pre-ctva-split-fix/`에 보존했고 SHA는 입력 정정 영수증에 남겼다. 첫 잘못된 입력의 새 전략 계산은 결과 해석 전에 중단됐으며 완료된 성과로 보고하지 않는다.

정확한 이 빈티지 재실행에는 `/workspace/batch-inputs/us/ctva-postcutoff-event-probe.response.json.gz`와 `.receipt.json`도 필요하다. 원문 SHA는 `c8f9f48f042a7d9c9843ee7777c73d26852987880c9c30aad910966f99956fa5`다. probe URL과 event 사실은 [공개 영수증](results/us-ctva-probe-receipt.json)에 있다. 새로 조회하면 응답 바이트가 달라질 수 있으므로 동일 SHA 재현으로 부르지 않는다. 이 파일은 입력 진단에서 이미 확보했으며 추가 구매가 아니다.

```bash
python -m research.kr_us_strategy_batch_v1.us_prepare --private /workspace/batch-inputs/us --stage repair
python -m research.kr_us_strategy_batch_v1.us_prepare --private /workspace/batch-inputs/us --stage features
python -m research.kr_us_strategy_batch_v1.us_prepare --private /workspace/batch-inputs/us --stage audit
python -m research.kr_us_strategy_batch_v1.us_prepare --private /workspace/batch-inputs/us --stage report --out research/kr_us_strategy_batch_v1/results/us-input-preparation.json
```

정정 후 CTVA 원종가 기준의 최대 상대 오차는 약 `1.96e-7`(공급원 반올림 수준), 다른625 ticker는 `1e-8` 미만이었다. SPY는 봉인 기업행위가 없어 원종가 역산이 성립하지 않는 별도 항목이다. FISV 거래량은 최대0.184% 차이가 남지만 원 특성은 거래량을 사용하지 않는다. admission/후보 연도별 통계와 CIK 통계는 원 집계와 같았으며 원 published 성과와의 차이는 별도로 보고한다.

## 미국 펀드 공시

이번 새 비교에 필요한 최소 파일은 `/workspace/batch-inputs/nport/round8/C2.pkl`이다. 이 파일에는 공개 시점에 맞게 수정된 메타데이터와 accession별 active-weight 벡터가 있어야 한다. 현재는 확보하지 못했으므로 새 N-PORT 비교는 `BLOCKED_OPTIONAL_C2_INPUT_ABSENT`다.

재생성은 원 `research.followup_round8_v1.us_audit` 경로를 따른다. 원 입력은 `nport/x/funds.parquet`, `nport/x/ec-*.parquet`, 기존 `nport/{filings.parquet,sample-holdings.parquet,bench.pkl}`, 위 `us/` 캐시다. 추출 원본은 GCAP 공개 N-PORT ZIP(Google Drive ID `1dGUfDFPqreYzJClEs46JWBivEJXhyNM7`, 7,402,820,315바이트, 2019Q3~2026Q3 분기 파일 29개)이다. 현재 공간에 전체 ZIP을 받지 않았으며 추가 데이터를 구매하지 않는다.

기존 `research/followup_round8_v1/results/us-{audit,eval}.json`과 `research/active_fund_disclosure_v1/results/us-*.json`의 집계는 참고 결과로 재사용할 수 있다. 날짜별 픽·보유·수익 원본이 없어 새 공통 날짜·시총 범위 매칭·노출 비중 비교를 이 JSON에서 복원할 수는 없다.

원 입력이 모두 있는 경우 C2 재생성 명령은 다음과 같다. 출력은 기존 연구 폴더 밖으로 지정한다. 이번 작업에서는 원 parquet와 C2가 없어 이 단계를 실행하지 않았다.

```bash
python -m research.followup_round8_v1.us_audit --private /workspace/batch-inputs --out /workspace/batch-inputs/nport-regeneration-results
```

이 경로는 `/workspace/batch-inputs/nport/round8/C2.pkl`을 만든다. 현재 batch는 미확보 OW/OW_RESID 슬롯을 유지하며 새 후보를 대신 넣지 않는다.
