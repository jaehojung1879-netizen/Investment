# 미국 가격·기업행동 복구 입력 v1

실행 기준: 2026-11-14 KST, 관측 종료 2026-11-13 미국 거래일. 실제 자료 수집과 검증을 수행한 독립 개발 입력이다. 새 모델·전략 평가, 기존 연구 재실행, 정식 데이터 편입 승인은 수행하지 않았다.

<!-- numerical-results -->
212개 중 **14개**에 새 가격 응답 또는 공식 사건 원문을 추가 확보했다(가격/행동 패킷 9개, 신규 사건 원문만 추가한 5개). 기존 파일 재확보 409개는 신규 수에서 제외했다.

| 전체 적격 보유 고정 분모 | 작업 전 완전 경로 | 작업 후 완전 경로 | 이번 추가 | 성숙 후 미해결 | 보유기간 미도래 |
|---|---:|---:|---:|---:|---:|
| H126 / 52,768건 | 45,536 | 48,753 | +3,217 | 44 | 3,971 |
| H252 / 52,768건 | 37,231 | 40,116 | +2,885 | 81 | 12,571 |

일반 종목 351개 후속 조회 중 349개는 전체 또는 필요한 최근 보유 구간을 검증했다. 작업 전 완전 경로는 모두 유지했다. 남은 성숙 공백은 H126 가격 18·MRO 단주 26건, H252 가격 10·MRO 단주 52·WBA DAP 19건이다. 정확한 범위는 remaining-gaps.csv에 있다. 미분류 사건 194개 및 212개 전체의 증권·기업행동 적격 검증은 남아 있으며, 정식 데이터 편입 기준은 아직 충족하지 못했다.

같은 고정 모집단에서 모든 종목 경로가 완전한 주간 날짜는 H126 54→126, H252 28→60개다. 개별 보유 완전 건수와 전체 날짜 적격을 혼동하지 않았다.
<!-- /numerical-results -->

이 표의 완전 경로는 `COMPLETE_ORIGINAL_RESEARCH_CONTRACT`다. 기존 연구의 가격 원천·관측 구성종목 한계를 승계한 조건부 재구성 건수이며, 독립적인 영구 증권 ID 검증이나 정식 연구 적격 승인을 뜻하지 않는다. 종목별 수익률·SPY 총수익·차이는 비공개 `holding-returns.json.gz`에 있다. 수익률이나 전략 우열을 공개 결과에 넣지 않았다.

## 보존한 기준과 분모

- 시작 main: `be46343031c3ec77a19f79ae102eecf6c3695be7`. main Tests와 Pages는 SUCCESS였다.
- 읽기 전용 #336: `148993572a625b914bbe6cd79610db7bf618f4b1`, pytest SUCCESS. 해당 619건은 이 브랜치로 복사하거나 병합하지 않았다.
- Claude의 PR, `signal-history`, 공용 원장, 확정 입력·결과·봉인은 수정하지 않았다. 관측 HEAD와 CI 링크는 [repository-observation.json](results/repository-observation.json)에 있다.
- 기존 캐시: `704d7db6d5b00def771aba5d2665d0846d6bc776`, replay-v16 manifest `f0781292f508a123c234ded6d28aa8e84a0dc3cc29500e14989dc0b68f53b4d2`, 종료일 2026-09-14. 570개 입력 구성요소, 미국 가격·벤치마크 2,266,907행을 읽었다. 최신 signal-history의 이 manifest도 같은 종료일이었다.
- 기존 #241의 409개 가격 후보 파일을 해시 일치로 재확보했다. 이전에 있던 자료이므로 신규 확보 수에 넣지 않았다. 원천 G는 기존 품질 제외 결정을 유지했다. 날짜가 있어도 증권·배당 기준이 검증됐다는 뜻은 아니다.
- 기존 `US_DECISION_PILOT_V1`의 **입력 함수만** 재사용했다. 주간 신호, 엄격히 이전에 관측된 S&P 구성 스냅샷, 금융·부동산·미분류 제외, 이전 253개 양의 가격, 기존 네 회계 요인 및 당시 CIK 일치, 30개 이상 완전 입력 조건을 유지했다. 다음 미국 거래일 종가 진입, 진입 인덱스+126/+252 종가 평가다.
- 가격·사건 수집 분모는 이탈 요청 212개다. H 분모는 종목×주간 신호별 전체 입력 적격 보유다. 입력 52,564→52,768건, 양쪽 합집합 52,768건을 각 H의 고정 비교 분모로 썼다. 작업 전 추가 204건은 `INPUT_NOT_ELIGIBLE`로 명시했다. 종목 수, 보유 건수, 두 H를 합한 건수는 서로 바꾸지 않았다.
- 원래 입력의 신호 종료일은 2026-09-14로 고정했다. 351개 추가 일반 종목 조회는 **만기가 도래한 보유 경로만** 연장한다. 입력 요인·신호·유니버스를 다시 선택하지 않는다. 공급원 전체 시계열을 쓰며 가격 수준을 이어 붙이지 않는다.
- 첨부 SEC 패널 40,846건·907 CIK와 262,457개 역사 종목-주를 영수증 검증과 식별 후보 대조에 사용했다. 첨부 `all_four`(자산·자본·순이익·영업현금흐름)는 기존 네 요인과 다르다. 이를 연구 적격으로 치환하지 않았다. 기존 입력 함수에서 2013~2022년 적격 주간 코호트는 0개다. 따라서 이 결과는 그 시대 전체 백테스트의 복원을 주장하지 않는다.

## 실제 확보와 원천 검증

1. 212개 전수의 날짜·기존 후보·원천별 요청을 대조했다. Yahoo 원 심볼 및 확인된 후속 심볼, 후속 주식·SPY 조회 225건을 저장했다. 현재의 `SE`(Sea Ltd)는 과거 Spectra와 달라 격리했고, EA의 한 행이나 SBNY의 요청 기간 밖 호가도 복원 건수에 넣지 않았다.
2. 기존 계정 Probes에서 Finnhub 가격·배당·분할은 각각 AAPL 대조군부터 403이었다. 프로필은 전수 조회했으나 현재 법인 프로필을 과거 증권 ID로 쓰지 않았다. FMP EOD는 전수 요청 중 ATVI·MRO·TWTR·VIAC·WBA 5개에서 실 가격을 받았고 207개는 402였다. 5개 모두 배당·분할 endpoint를 별도로 확인했다. Polygon은 기존 대조군 일부만 가용하고 표본 이탈주는 요금제 제한이었다. Stooq 응답은 HTML challenge여서 CSV 성공으로 세지 않았다.
3. ABC→COR, BLL→BALL, CTL→LUMN, FB Class A→META는 공식 효력일 근거와 하나의 동일 공급원 전체 가격열로 연결했다. 이 네 후속 심볼의 기존 캐시도 참조했다. 신규 응답에는 기존 날짜와 겹치는 구간이 있으며, 14개 자료 확보가 14개 종목의 과거 가격이 전부 새로 생겼다는 뜻은 아니다. 4개 재연결과 FMP 5개를 합쳐 가격/행동 패킷 9개를 작성자가 검증했다. `formal_dataset_admission`은 미승인 상태다.
4. 보유 종료 캐시 공백을 메우기 위해 기존 적격 351개 종목을 추가 조회했다. HTTP 200과 데이터 검증 성공은 구분한다. 가격 통화 USD, 양의 거래량·OHLC, 배당 조정 대조, 기존 공통 253거래일 기준 일치 검사를 적용했다. 전체 역사 오류가 있는 경우 달력으로 정한 필요한 최근 보유 구간만 다시 검증하며, 옛 역사 거부 사유는 보존한다. 짧은 시계열로 과거 보유를 평가하거나 내부 결측을 다른 원천으로 숨기지 않는다.
5. 기존 등록 `price_adjustment.to_total_return`를 원 가격에 한 번만 적용했다. 이미 총수익인 원래 캐시에는 배당을 다시 넣지 않는다. Yahoo AdjClose 대조 허용치 1e-5는 가격 표현 정밀도 기준이다. FMP는 split-adjusted EOD와 adjDividend를 같이 사용했고 원천 응답·basis를 보존했다. 기존 D/F 원가격 후보와도 대조했다. WBA의 구 F 후보 한 날짜는 반올림 허용치를 벗어나며 신규 원천과 혼합하지 않았다.
6. SPY는 같은 달러·같은 보유기간 총수익이다. SSGA 공식 배당표 59건과 대조하여 2021-12-17의 Yahoo 1.633과 공식 1.636431의 차이를 확인했다. 새 비공개 벤치마크에 공식 값을 적용했으며 옛 봉인 입력은 보존했다.

계정 수집 실행: [대조군/기존 probe](https://github.com/jaehojung1879-netizen/Investment/actions/runs/43538004827), [212개](https://github.com/jaehojung1879-netizen/Investment/actions/runs/43539000217), [배당·분할 보충](https://github.com/jaehojung1879-netizen/Investment/actions/runs/43540781549). 모두 completed/success다. skipped 작업은 성공으로 세지 않는다. 새 결제는 없었다.

## 기업행동과 식별 보류

| 사례 | 확인한 처리 / 남은 공백 |
|---|---|
| ATVI / TWTR | 각각 공식 현금 95 / 54.20달러. 효력일·마지막 실거래를 적용하고 이후 무이자 달러 현금 보유. ATVI의 합병 후 거래량 0 호가는 제외 |
| MRO | 2024-11-22 COP 0.255주. 단주 현금 정산·기존 가상 보유에 적용할 규칙이 미확정인 교차 보유는 거부 |
| AGN / ESRX / XLNX | 첨부 현금·주식 조건을 보존하고 ABBV/CI/AMD 일별 가격·행동을 조회. 원 증권 가격·클래스·단주 계약이 부족해 교차 보유 확정 불가 |
| CELG | 현금 50+BMY 1주+CVR. 2021-01-01 CVR 종료 원문 추가 확보. 종료 전 평가일의 CVR 가격을 0으로 바꾸지 않음 |
| WBA | 2025-08-28 현금 11.45+VillageMD DAP 권리. DAP 미래 대가를 0이나 최대 대가로 가정하지 않음 |
| BTU / CHK | 구주 취소·무분배 원문을 확보. 새 BTU/CHK를 구주 가격에 연결하지 않음. 요청 기간 원 가격 부재는 계속 공백 |
| FRC / SIVB / SBNY | 2023년 은행 관리·폐쇄 근거와 일부 OTC 후보 확보. 은행 자산 매각이 보통주·모회사 주식의 대가를 입증하지 않으므로 회수액 0이나 인수회사 주식을 부여하지 않음 |
| VIAC | 2019-12-05 이후 CIK813828 Class B, 2022-02-17 PARA로 변경. 구 Viacom CIK1339947 및 Class A VIACA/PARAA와 구분 |
| XOM | 수집 212개 밖의 대조 사례. 같은 티커라도 2026-07-01 CIK34088→2115436의 1:1 재편 근거를 보존 |

전체 212개 식별 원장은 [security-lineage.json](results/security-lineage.json), 공식 원문 영수증은 [public-source-receipts.json](results/public-source-receipts.json)이다. CIK는 발행사 ID이며 주식 클래스의 영구 증권 ID를 대신하지 않는다. 미분류 사건 194개를 모두 합병·상장폐지로 단정하지 않았다.

확인된 은행 관리 공백 3개는 사건 효력년 2023년에 집중된다. 첨부 역사 종목-주에서 2022년 신호가 2023년 은행 사건을 가로지르는 후보는 H126 28건, H252 80건이다. 2018~2020년 혼합 합병 및 2021~2022년 주식 합병의 교차 구간도 별도 집계했다. 이 표는 회계·산업·증권 적격을 모두 통과한 H 분모가 아닌 누락 진단이다. 194개 미분류 때문에 전체 모집단의 연도 편향이 해소됐다고 결론 내릴 수 없다. [연도별 근거](results/missingness-by-year.json)

## 남은 파일을 한 번에 받는 방법

정확한 종목·필드·구간·확인한 공급원은 [remaining-gaps.csv](results/remaining-gaps.csv)의 각 행이다. 212개 요청 전체와 원천별 HTTP 상태·해시·획득 범위는 [results.json](results/results.json)의 inventory에 있다. 과거 감사 종료일을 최종 거래일로 가정하지 않는다. 만기가 도래했지만 없는 시세는 가격 공백이고, 2026-11-13 이후 평가일은 `NOT_MATURED`다.

| 기존 이용 서비스에서 받을 파일 | 필드 / 기간 |
|---|---|
| Finnhub 또는 FMP의 해당 이탈종목 포함 기존 이용권, 또는 이미 보유한 CRSP/기관 데이터 | CSV의 daily OHLCV 결측 구간. 원 종가·거래량·거래소·통화·가격 조정 기준, ex/pay date별 현금배당, split ratio, 마지막 거래일, delisting return/대가. 각 요청에는 252거래일 준비·후속 기간이 포함됨 |
| 같은 서비스의 증권 마스터·변경 이력 | 212개 각 요청 기간의 CUSIP/ISIN/PERMNO 등 증권 ID와 Class, CIK, 심볼, 효력 시작·종료일. AGN/SE/BTU/CHK/VIAC 및 XOM 재편을 구분 |
| 실제 중개/수탁사 기업행동 명세 또는 공식 합병·법원 문서 | MRO/XLNX/AGN/ESRX 단주 처분일·가격·후속 주식 수량; CELG CVR의 필요한 H 평가일 시세·처분/지급; WBA DAP 권리 및 당시 평가/실제 지급; FRC/SIVB/SBNY 보통주와 OTC 연결·회수 명세 |
| 가용한 가격 원천의 보완 파일 | label_followup_diagnostics에서 거부된 종목의 CSV 날짜 구간과 배당·분할·분사 내역. 가격만으로 조정 검증 실패를 해제하지 않음 |

현재 Finnhub는 세 endpoint 권한, FMP는 207개 심볼 접근 범위가 부족했다. 계정 연결·추가 다운로드가 없어도 가능한 수집은 끝냈다. 새 이용권 구매는 요청하거나 실행하지 않았다. 위 파일을 기존 권한으로 받을 수 있을 때만 비공개 폴더에 추가하고 원천·라이선스를 기록해야 한다. 2013~2022 전체 연구를 열려면 원천 가격 외에 해당 시점 주식 클래스 연결과 기존 네 회계 요인 입력 적격 검증도 필요하다.

## 재실행과 보관

`pip install -c constraints/ci-registered-numerics-v1.txt -r requirements.txt -r requirements-dev.txt openpyxl` 후 실행한다. 원 가격·계정 응답·수익률은 Git checkout 밖의 접근 제한 폴더에 둔다. 저장소에는 코드·요청·원천 해시·날짜·집계만 있다. 라이선스상 재배포 허가를 부여하지 않는다. `bundle-manifest.json`은 해시 검증과 비공개 입력 패키징 목록이다.

```bash
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export MARKET_PRIVATE=/absolute/path/outside/git/us-market-inputs
export MARKET_UPLOADED=/absolute/path/to/extracted/user-zip
export MARKET_RESULT=research/us_historical_market_recovery_v1/results
git fetch --no-tags --depth=1 --filter=blob:none origin 704d7db6d5b00def771aba5d2665d0846d6bc776
python -m research.us_historical_market_recovery_v1.prepare --private-root "$MARKET_PRIVATE"
python -m research.us_historical_market_recovery_v1.collect --input research/us_historical_market_recovery_v1/inputs/requests.json --private-root "$MARKET_PRIVATE" --existing-audit docs/us-readiness/us-departed-public-price-recovery-v1.json
python -m research.us_historical_market_recovery_v1.sources --private-root "$MARKET_PRIVATE"
# Existing-account response inputs are required before audit; reuse the private bundle.
# For fresh collection, use authenticated.py with existing env keys and a recipient certificate.
python -m research.us_historical_market_recovery_v1.audit --uploaded-dir "$MARKET_UPLOADED" --private-root "$MARKET_PRIVATE" --output "$MARKET_RESULT"
python -m research.us_historical_market_recovery_v1.collect --input research/us_historical_market_recovery_v1/inputs/requests.json --private-root "$MARKET_PRIVATE" --existing-audit docs/us-readiness/us-departed-public-price-recovery-v1.json --label-followup
python -m research.us_historical_market_recovery_v1.audit --uploaded-dir "$MARKET_UPLOADED" --private-root "$MARKET_PRIVATE" --output "$MARKET_RESULT"
python -m research.us_historical_market_recovery_v1.report --uploaded-dir "$MARKET_UPLOADED" --private-root "$MARKET_PRIVATE" --output "$MARKET_RESULT"
python -m research.us_historical_market_recovery_v1.verify --private-root "$MARKET_PRIVATE" --output "$MARKET_RESULT" --write-manifest
python -m research.us_historical_market_recovery_v1.verify --private-root "$MARKET_PRIVATE" --output "$MARKET_RESULT"
```

새 계정 조회가 필요하면 로컬에서 받거나 기존 read-only Probes의 선택형 `--market-recovery`를 사용한다. 워크플로·기본 probe 동작은 바꾸지 않았다. 수신자의 새 인증서 공개키를 `--transfer-cert`로 지정하고 개인키는 로컬에만 둔다. 응답은 CMS AES-256-GCM으로 암호화한 뒤 runner를 떠나며 공개 로그·artifact에는 암호문만 전달한다. `decrypt --input TRANSFER.json --private-key LOCAL_KEY --private-root "$MARKET_PRIVATE" --name authenticated` 및 supplement를 써서 해시 확인 후 복호화한다. 이미 받은 입력은 재수집하지 않고 재사용한다. 이 작업의 개인키와 원본은 커밋하지 않았다.

과거 연구 실행 게이트나 봉인 테스트를 현재 CI에 맞춰 고치지 않았다. `prepare`/`audit`는 재사용한 입력·보조 함수 해시만 검사하며 옛 연구 실행 허용 상태를 만들지 않는다. 합성 테스트는 미확인 대가, 단주, CVR, 무거래 호가, 중복 조정, 원천 연결을 거부하는지 확인한다. 전체 CI의 실제 최종 HEAD 결과는 Draft PR에 별도로 기록한다.
