# 미국 Tiingo 역사 가격 복구 파일럿 v1 (개정 1: Starter 라이선스·브라우저 실행)

**판정: Tiingo 무료(Starter) 계정으로 역사 가격을 보존하는 경로는 NO-GO다.** 무료 계정은 메모리 안에서만 쓰는 임시 조회만 허용한다. 보존 가능한 역사 가격에는 다른 원천이나, 저장을 서면으로 허용받은 유료 플랜이 필요하다.

**도구 상태:**
- 메모리 전용 실행으로 개정했고, 오프라인 합성 테스트를 마쳤다.
- 실제 Tiingo 응답은 NOT_TESTED이고, 모든 데이터는 NOT_ADMITTED다.
- 사전 고정한 20개 종목과 판정 규칙은 바꾸지 않았다(계획 파일 바이트 동일).
- 수익률·라벨·CAGR·IC를 계산하지 않는다.
- replay-v16·봉인 데이터셋·C1·WP1·WP2의 파일을 바꾸지 않는다.

## 0. 이용 약관 판정 (개정 1의 근거)

- **조항 원문 미확인:** 약관은 [Tiingo Terms of Use](https://app.tiingo.com/tos/)다. 이 작성 환경에서는 그 페이지에 직접 접근하지 못했다(DNS 실패·프록시 CONNECT 403). 아래 요약은 소유자가 지정한 조항(1.6(a), 1.6(c))을 검색 색인으로 확인한 것이며 **원문 인용이 아니다.** 소유자가 원문을 직접 읽어 확인해야 한다.
  - **1.6(a):** Starter와 체험 플랜은 Tiingo Data를 영구·지속 저장소에 보관하지 못한다. 저장소에는 로컬 장치, 데이터베이스, 로그, 큐, 백업, 재해 복구 시스템이 모두 포함된다. 처리는 휘발성 메모리나 비영속 임시 캐시에서만 할 수 있고, 계산이 끝나면, 늦어도 프로세스·작업·세션이 끝나기 전에 지워야 한다.
  - **1.6(c):** 파생물(Derived Products)도 같은 제한을 받는다. 계산과 일시 보유만 할 수 있고 영구 저장은 금지된다.
- **결론:**
  - 기존 CLI는 원자료를 `%LOCALAPPDATA%` 아래 파일로 보관했다. 이 구조는 1.6(a)에 어긋나므로 **삭제했다.** 이전 버전으로 실제 Tiingo를 호출한 적은 없으므로 지울 원자료도 없다.
  - 기존 보고서의 종목별 세션 수, 날짜, 이름 일치, 배당·분할 횟수는 Tiingo 응답에서 계산한 파생물이다. 따라서 1.6(c)상 **서면 허가 없이는 기록하지 않는다(fail-closed).**
  - Starter 계정으로 212개 결손을 메운 결과를 연구 데이터로 남기는 일은 약관상 불가능하다. **따라서 Tiingo Starter를 역사 연구 원천으로 쓰는 것은 NO-GO다.** 실행 결과와 관계없이 이 판정은 바뀌지 않는다.

### 무엇을 남기고 무엇을 버리는가

| 분류 | 예 | 처리 |
|---|---|---|
| 원본 응답 | meta·가격 JSON, `supported_tickers.zip` | 프로세스 메모리에만 존재한다. 디스크·로그·캐시에 쓰는 코드 경로가 없다(`Session`에 디렉터리 인자가 없다) |
| 파생 결과 | 종목별 세션 수·날짜·신원 판정·배당분할 횟수·판정 | 기본은 종료 시 폐기한다. `--show-transient-summary`를 주면 화면에만 출력한다. Tiingo의 서면 허가 파일(`--retention-authorization`)이 있을 때만 보고서로 쓴다 |
| 연결 기록 | 호출 수, 도달 여부, 인증 수락 여부, 429 여부, 중단 사유, 한도 헤더 **이름** | 항상 `docs/us-readiness/us-tiingo-price-recovery-pilot-v1-access.json`에 쓴다. 어떤 종목이 응답했는지, 무엇을 받았는지는 담지 않는다 |
| SEC·OpenFIGI 응답 | 이름·CIK·FIGI | Tiingo Data가 아니지만 같은 메모리 전용 경로를 쓴다. 결과 횟수만 연결 기록에 넣는다 |

- **화면 출력의 위험:** 터미널 스크롤백, 녹화, 복사도 "저장"이 될 수 있다. 그래서 화면 요약은 기본으로 꺼져 있다. 켜더라도 내용을 파일·채팅·메모에 옮기지 않아야 한다.
- **허가 파일의 조건:** 허가 파일에는 provider·plan·scope(`DERIVED_AGGREGATE_COUNTS_AND_DATES`)·허가자·증빙 번호·허가일이 모두 있어야 한다. 하나라도 비거나 형식이 틀리면 **첫 요청 전에** 거부한다. 원자료 보관(`coversRawResponses`)은 어떤 허가로도 이 도구에서 열리지 않는다.

## 1. 기존 작업 확인 (#241–#244)

- **#241:** 원래 212개 noPanel 식별자 중 175개에 후보 가격(186,910세션)이 생겼다. FULL 5 / PARTIAL 170 / NONE 37이다. 결측은 256,402세션에서 69,492세션으로 줄었다. 다만 2024–2026 개선은 0이다.
- **#243:** 이 후보 186,910세션 중 admission을 통과한 세션은 **0**이다. 신원·가격 기준·분할배당 lineage·PIT 연결 관문이 모두 0이다.
- **#244:** 공식 SEC·IR 접근이 PROXY_CONNECT_403으로 막혀 독립 검증은 0종목이다. Source F의 생성 코드는 정상 경로로 재현되지 않았다.
- **#242:** US 연구 재설계 문서가 이 결손을 전제 조건으로 명시한다.
- 이 파일럿은 기존 후보를 버리거나 같은 파일을 다시 받지 않는다. 기존 수치는 공개 감사 JSON에서 읽고, 새 출처(Tiingo)만 추가로 묻는다.
- **비공개 세션 표:** #243의 세션별 비공개 표(SHA `14d96bda…`)는 당시 임시 작업 공간에 있었고 이 환경에는 없다. 그래서 PARTIAL 종목의 "추가 확보 세션"은 **하한–상한 범위**로 보고한다. 소유자가 그 파일을 갖고 있으면 `--existing-session-table`로 넘길 수 있다. 이때 도구가 SHA를 대조한 뒤 정확한 수로 바꾼다.

## 2. 소스 이용 가능성 — 확인된 것과 확인 못 한 것

작성 환경에서 공식 문서를 직접 읽지 못했다.

| 대상 | 시도 | 결과 |
|---|---|---|
| `api.tiingo.com`, `www.tiingo.com`, `data.sec.gov`, `www.sec.gov`, `api.openfigi.com` | curl | 샌드박스 프록시가 CONNECT 403 |
| `www.tiingo.com`, `api.tiingo.com`, `www.sec.gov`, `www.openfigi.com` | 웹 조회 도구 | DNS 실패 |

따라서 아래는 **추정하지 않고** 상태만 적는다. 판정은 실제 실행 시 도구가 받은 응답으로만 한다.

| 확인 항목 | 작성 시점 상태 | 실행 시 도구가 측정하는 것 |
|---|---|---|
| 무료 EOD 범위·호출 한도 | NOT_VERIFIED. 2차 출처는 시간당 50회·일 1,000회·월 500종목 등 서로 다른 값을 적고 있어 쓰지 않는다 | 응답 상태, `ratelimit`/`retry-after` 계열 헤더 이름, 429 발생 여부(연결 기록에 남는 것은 헤더 이름과 429 여부뿐) |
| 상장폐지·재사용 ticker | NOT_VERIFIED | `supported_tickers.zip`의 ticker별 행 수와 기간. 같은 ticker가 회원 기간 안에 2번 이상 있으면 HOLD |
| 원종가·수정종가·현금배당·분할 정의 | NOT_VERIFIED(공개 클라이언트 라이브러리의 필드명 `close/adjClose/divCash/splitFactor` 기준) | 필드 존재 여부. 수정 계수(`adjClose/close`) 변화가 배당·분할일과 일치하는지 수 |
| 개인 연구 저장·재배포 제한 | **Starter는 영구 저장 금지**(약관 1.6(a), 파생물 1.6(c), §0) | 측정하지 않는다. 약관 페이지도 더 이상 받아 오지 않는다 |
| 영구 종목 식별자 | NOT_VERIFIED | meta 응답에 `perma*`·FIGI·CIK·ISIN·CUSIP 필드가 있는지 |
| SEC EDGAR | NOT_VERIFIED(공정 접근·User-Agent 조건) | `cik-lookup-data.txt`의 과거 이름–CIK, `submissions`의 현재·과거 이름과 사용 기간. 연락처 User-Agent는 이 저장소의 `git config user.email`에서 만들고, 없으면 SEC는 NOT_RUN |
| OpenFIGI | NOT_VERIFIED(키 없는 한도) | 키 없이 2회 요청(10개씩). 상장폐지 종목은 보통 매핑되지 않을 수 있으며 그것도 결과로 기록 |

자동 유료 가입이나 결제, 우회 경로, 다른 프록시는 쓰지 않는다. 접근 차단은 ACCESS_BLOCKED로 보고하고 해당 출처를 멈춘다.

## 3. 사전 고정한 20개 (어떤 요청보다 먼저 커밋)

선정 규칙은 공개 감사(`us-departed-public-price-recovery-v1.json`)의 회원·커버리지 사실만 읽는다. 가격·수익률·결과는 읽지 않으며, 동률은 식별자순으로 정한다.

- **NONE 10:** HOLD 표시가 없는 것 중 결측 창이 가장 큰 7개, HOLD 표시가 있는 것 중 가장 큰 3개. 뒤의 3개는 HOLD 경로를 검증하려고 넣었고, ticker만으로는 절대 연결하지 않는다.
- **PARTIAL 8:** HOLD 없음. 회원 종료가 2020년 이전인 4개와 이후인 4개, 각각 결측 최대순. #241이 측정한 무료 출처의 시대 경계를 반영한다.
- **FULL 2:** #244가 처음 다룬 JWN, ADS를 대조군으로 쓴다.

기대 세션은 원래 감사의 `expected_members`를 봉인 입력 그대로 다시 계산했다. 20개 모두 공개 수치(covered + missing = expected)와 일치하지 않으면 계획 생성이 실패한다. 파일럿 안의 기존 결측은 **14,689세션**이다. 구성은 NONE 비HOLD 2,903 / HOLD 4,335 / PARTIAL 7,451 / FULL 0이다.

| # | 층 | ID | 당시 기업명 | 후보 CIK | share class | 관측 회원 기간 | 기대/기존 결측 세션 | 선정 사유 | 처리 |
|---:|---|---|---|---|---|---|---|---|---|
| 1 | NONE | ANDV | Andeavor | — | 미표기(보통주 미검증) | 2018-04-03–2020-05-08 | 530 / 530 | 결측 창 최대(HOLD 없음) | 신원 일치 시 연결 후보 |
| 2 | NONE | BHGE | Baker Hughes, a GE Company | — | 미표기(보통주 미검증) | 2018-04-03–2020-05-08 | 530 / 530 | 결측 창 최대(HOLD 없음) | 신원 일치 시 연결 후보 |
| 3 | NONE | DWDP | DowDuPont | — | 미표기(보통주 미검증) | 2018-04-03–2020-05-08 | 530 / 530 | 결측 창 최대(HOLD 없음) | 신원 일치 시 연결 후보 |
| 4 | NONE | DAY | Dayforce | 1725057 | 미표기(보통주 미검증) | 2024-02-05–2026-03-04 | 521 / 521 | 결측 창 최대(HOLD 없음) | 신원 일치 시 연결 후보 |
| 5 | NONE | JDSU | JDS Uniphase Corp. | — | 미표기(보통주 미검증) | 2013-01-02–2014-01-17 | 264 / 264 | 결측 창 최대(HOLD 없음) | 신원 일치 시 연결 후보 |
| 6 | NONE | LTD | Limited Brands Inc. | — | 미표기(보통주 미검증) | 2013-01-02–2014-01-17 | 264 / 264 | 결측 창 최대(HOLD 없음) | 신원 일치 시 연결 후보 |
| 7 | NONE | MOLX | Molex Inc. | — | 미표기(보통주 미검증) | 2013-01-02–2014-01-17 | 264 / 264 | 결측 창 최대(HOLD 없음) | 신원 일치 시 연결 후보 |
| 8 | NONE | AGN | Allergan / Allergan Inc / Allergan plc / Allergan, Plc | — | 미표기(보통주 미검증) | 2013-01-02–2020-05-22 | 1861 / 1861 | 결측 창 최대(HOLD 경로 검증) | HOLD: SEALED_IDENTITY_HOLD |
| 9 | NONE | CHK | Chesapeake Energy | — | 미표기(보통주 미검증) | 2013-01-02–2018-04-02 | 1321 / 1321 | 결측 창 최대(HOLD 경로 검증) | HOLD: SEALED_IDENTITY_HOLD |
| 10 | NONE | CTRA | Coterra | 858470 | 미표기(보통주 미검증) | 2021-10-05–2026-05-08 | 1153 / 1153 | 결측 창 최대(HOLD 경로 검증) | HOLD: SEALED_IDENTITY_HOLD |
| 11 | PARTIAL | TWX | Time Warner / Time Warner Inc. | — | 미표기(보통주 미검증) | 2013-01-02–2020-05-08 | 1851 / 908 | 결측 최대, 회원 종료 ≤2020 | 신원 일치 시 연결 후보 |
| 12 | PARTIAL | ESRX | Express Scripts / Express Scripts Holding | — | 미표기(보통주 미검증) | 2013-01-02–2020-05-08 | 1851 / 867 | 결측 최대, 회원 종료 ≤2020 | 신원 일치 시 연결 후보 |
| 13 | PARTIAL | RTN | Raytheon Co / Raytheon Co. | — | 미표기(보통주 미검증) | 2013-01-02–2020-05-08 | 1851 / 803 | 결측 최대, 회원 종료 ≤2020 | 신원 일치 시 연결 후보 |
| 14 | PARTIAL | YHOO | Yahoo / Yahoo Inc. | — | 미표기(보통주 미검증) | 2013-01-02–2018-04-02 | 1321 / 679 | 결측 최대, 회원 종료 ≤2020 | 신원 일치 시 연결 후보 |
| 15 | PARTIAL | DISCK | Discovery (Series C) / Discovery Communications-C / Discovery Inc. (Class C) / Discovery Inc. (Series C) / Discovery Inc. Class C | — | 이름상 Series C | 2016-02-24–2022-12-23 | 1723 / 1576 | 결측 최대, 회원 종료 >2020 | 신원 일치 시 연결 후보 |
| 16 | PARTIAL | SIVB | SVB Financial | — | 미표기(보통주 미검증) | 2018-04-03–2023-04-13 | 1267 / 1120 | 결측 최대, 회원 종료 >2020 | 신원 일치 시 연결 후보 |
| 17 | PARTIAL | HOLX | Hologic | 859737 | 미표기(보통주 미검증) | 2016-06-13–2026-04-09 | 2470 / 762 | 결측 최대, 회원 종료 >2020 | 신원 일치 시 연결 후보 |
| 18 | PARTIAL | IPG | Interpublic Group / Interpublic Group of Companies (The) / Interpublic GroupCompanies / The Interpublic Group of Companies | 51644 | 미표기(보통주 미검증) | 2013-01-02–2026-03-04 | 3312 / 736 | 결측 최대, 회원 종료 >2020 | 신원 일치 시 연결 후보 |
| 19 | FULL | JWN | Nordstrom | 72333 | 미표기(보통주 미검증) | 2013-01-02–2020-07-17 | 1899 / 0 | 대조군(#244 첫 두 종목) | 신원 일치 시 연결 후보 |
| 20 | FULL | ADS | Alliance Data Systems / Alliance Data Systems Corp | 1101215 | 미표기(보통주 미검증) | 2014-01-21–2020-07-17 | 1635 / 0 | 대조군(#244 첫 두 종목) | 신원 일치 시 연결 후보 |

회원 기간은 strictly-earlier 스냅샷 관측 구간이며 공식 지수 편입·제외일이 아니다. CIK는 #241·#244의 후보 연결일 뿐 공식 확인이 아니다. 기계 판독 계획: [`docs/us-readiness/us-tiingo-price-recovery-pilot-v1-plan.json`](us-readiness/us-tiingo-price-recovery-pilot-v1-plan.json)

## 4. 신원 판정 (모두 NOT_ADMITTED)

| 상태 | 조건 | 복구 세션 집계 |
|---|---|---|
| `HOLD_TICKER_REUSE_OR_IDENTITY_CONFLICT` | 봉인 감사의 신원 HOLD·ticker 재사용 표시, 또는 회원 기간 안에 같은 ticker의 상장이 2개 이상 | 제외 |
| `HOLD_TIINGO_NAME_OR_DATES_DISAGREE` | Tiingo 기업명이 당시 이름과 다르거나 Tiingo 거래 기간이 회원 기간과 겹치지 않음(재사용 의심) | 제외 |
| `NO_TIINGO_RESPONSE` | meta·가격 모두 없음(404 등) | 제외 |
| `TIINGO_NAME_AND_DATES_ONLY_UNRESOLVED` | Tiingo 이름·기간은 맞지만 독립 출처 확인 없음 | 포함(미해결로 표시) |
| `INDEPENDENT_IDENTITY_CORROBORATED` | 위에 더해 SEC 현재 이름, 또는 회원 기간과 겹치는 SEC 과거 이름(정확히 1개 CIK), 또는 OpenFIGI 이름이 일치 | 포함 |

이름 비교는 #241과 같은 정규화와 별칭(`NAME_ALIASES`)을 재사용한다. 같은 ticker라는 이유만으로 연결하지 않는다.

## 5. 실행 — 브라우저 GitHub Codespaces (권장) 또는 Windows

### Codespaces 준비

1. 저장소 페이지에서 **Code → Codespaces → Create codespace on `research/us-tiingo-price-recovery-pilot-v1`**를 연다.
2. 기본 이미지의 `python3`만 쓰며, 설치할 것은 없다. 도구는 표준 라이브러리만 사용한다.
3. 터미널에서 먼저 연결만 확인한다. 이 단계는 토큰을 묻지 않고, 데이터를 받지 않으며, 파일도 쓰지 않는다.

```bash
python3 scripts/run_us_tiingo_recovery_pilot.py --check-connectivity
```

`tiingo`·`sec`·`openfigi`가 각각 `REACHABLE_HTTP_<코드>`로 나와야 한다. `BLOCKED_BEFORE_PROVIDER`가 나오면 그 네트워크에서는 실행하지 않는다(우회 금지). 참고로 이 작성 환경에서는 실제로 세 곳 모두 `BLOCKED_BEFORE_PROVIDER`였다.

### 실행

```bash
python3 scripts/run_us_tiingo_recovery_pilot.py --run
```

Windows에서는 `py -3 scripts\run_us_tiingo_recovery_pilot.py --run`으로 동일하게 실행한다.

- **토큰 입력:** `Tiingo API token (input hidden):` 프롬프트에 붙여 넣는다. 화면에 표시되지 않는다.
  - `export TIINGO_API_TOKEN=...` 방식은 쓰지 않는다. 셸 기록에 토큰이 남는다.
  - Codespaces 사용자 Secret도 쓸 수 있지만, 설정 변경이 필요하므로 이 작업에서는 권하지 않는다.
- **요청 순서와 상한:**

  | 순서 | 대상 | 상한 | 간격 |
  |---:|---|---|---|
  | 1 | Tiingo 지원 ticker 목록 | 1회 | — |
  | 2 | Tiingo meta·가격 | 20×2회(최대 42회) | 2초 |
  | 3 | SEC | 최대 30회 | 0.25초 |
  | 4 | OpenFIGI | 2회 | 3초 |

  - 재시도는 없다. 401/403/429/5xx, 접근 차단, 시간 초과가 나면 그 출처를 즉시 멈춘다.
  - 실행 시간은 약 2~4분이다.
- **쓰는 파일:** 연결 기록 1개(`…-access.json`)만 쓴다. 파생 보고서 두 개는 서면 허가 파일이 있을 때만 쓴다.
- **종료 코드:** 0 완료 / 2 Tiingo 인증 거부·접근 차단 / 3 사전 거부(토큰 없음, 출력 파일 존재, 허가 파일 결함).

### Codespaces 제약

- **무료 사용량:** GitHub 개인 Free 계정은 월 120 core-hour(2코어 기준 약 60시간)와 15 GB-month 저장 공간이 무료다([GitHub 문서](https://docs.github.com/en/billing/concepts/product-billing/github-codespaces)). 이 실행은 몇 분이면 끝난다. 실행 후 codespace를 **중지·삭제**한다.
- **디스크:** codespace 디스크는 삭제할 때까지 남는다. 그래서 도구는 응답을 쓰지 않는다. 사용자가 응답을 따로 저장하지 않는 한 디스크에 남는 것은 연결 기록뿐이다.
- **네트워크:** GitHub가 운영하는 VM이며 보통 외부 접속이 열려 있다. 실제 여부는 위의 연결 확인 명령으로 측정한다.
- **SEC 연락처:** SEC는 연락처가 있는 User-Agent를 요구한다. 도구는 codespace의 `git config user.email`을 쓴다. 이 값이 없으면 SEC 단계는 실행하지 않는다(NOT_RUN).

## 6. 사전 고정 판정과 확대·중단 조건 (규칙은 변경 없음)

**판정 규칙(요청 전 고정):**

- `STOP_SOURCE_NOT_REACHABLE_OR_REFUSED`: Tiingo 차단·401·403·429·응답 0
- `STOP_CONTROLS_NOT_REPRODUCED`: FULL 대조군이 행을 받지 못했거나 회원 세션의 1%를 넘게 누락
- `STOP_FREE_COVERAGE_TOO_THIN`: HOLD가 아닌 목표 15개 중 창 안 행이 있는 것이 4개 미만
- `EXPAND_TO_212_FREE_TIER_FEASIBILITY`: 15개 중 8개 이상에 행이 있고, 설명되지 않는 조정 단계가 관측 세션의 0.1% 이하
- `LIMITED_VALUE_REVIEW_BEFORE_EXPANSION`: 그 밖의 경우

이 규칙과 8개 질문 계산은 그대로 메모리에서 수행한다. 바뀐 것은 결과를 남기는 방식뿐이다.

**확대 조건:** Starter에서는 판정이 EXPAND여도 **212개 확대는 하지 않는다.** 결과를 남길 수 없는 확대는 연구 결손을 줄이지 못하기 때문이다. 확대는 아래 두 조건이 모두 있을 때만 한다.

1. 보관을 허용하는 원천을 확보했다. Tiingo 유료 플랜이면 서면 확인이 필요하고, 다른 공급자면 저장 조항이 필요하다.
2. 그 원천에 대해 같은 계획과 같은 규칙으로 다시 실행했다.

**중단 조건:** STOP 판정, 또는 서면 허가 불가 답변이다. 문턱을 낮춰 재실행하지 않는다.

## 7. 대체 공급자 비교 (보관 권한이 최우선 기준)

출처가 2차 자료인 값은 그렇게 표시한다. 어느 공급자도 이 환경에서 공식 약관 원문을 직접 읽지 못했다.

| 공급자 | 역사 데이터 보관 권한 | 가격 | 상장폐지 커버리지 | 근거·상태 |
|---|---|---|---|---|
| Tiingo Starter | **금지**(1.6(a), (c)) | 무료 | 미측정 | 약관 조항(검색 색인 요약) |
| Tiingo 유료(Power) | **미확인**: 1.6이 Starter·체험에만 적용되는지 서면 확인 필요 | 약 $30/월(2차 출처, 공식 미확인) | 미측정 | 지원팀 질문 §8 |
| EODHD 개인 플랜 | **미확인**: 저장·보관 조항을 찾지 못함 | EOD All World $19.99/월 또는 $199/년. 무료는 하루 20회, 최근 1년 | 미국 상장폐지 심볼 60,191개 목록 제공. 2018년 이전 상장폐지는 EOD만 제공. ticker 재사용 시 새 회사가 반환될 수 있음 | EODHD 가격표·문서(검색 요약) |
| QuantConnect | **미확인**: 데이터는 플랫폼 안에서만 쓰는 구조로 알려짐. 로컬 보관 불가로 간주 | 연구 계정 무료(미확인) | 미측정 | 대조용으로만 검토 |
| SEC EDGAR | 미국 정부 공개 자료로 보관 가능성이 높으나 **가격이 아님** | 무료 | 해당 없음(신원·종결대가 증거) | 신원·종결대가 관문용 |

**추천 순서:**

1. Tiingo 지원팀에 §8 질문을 보내 유료 플랜의 보관 허용 여부를 서면으로 받는다. 답이 오기 전에는 비용이 들지 않는다.
2. 동시에 EODHD 약관의 저장 조항을 서면으로 확인한다. EODHD는 상장폐지 커버리지를 제품으로 명시한다는 장점이 있지만, 2018년 이전 상장폐지는 EOD만 제공한다. ticker 재사용 함정도 직접 경고하고 있어, 신원 관문(§4)은 그대로 필요하다.
3. 어느 쪽이든 결제는 소유자만 결정한다. 보관 권한이 확인되기 전에는 아무것도 수집하지 않는다.

## 8. Tiingo 지원팀에 보낼 질문 (영문, 그대로 복사)

1. Section 1.6(a) prohibits persistent storage for Starter and trial plans. Does the same prohibition apply to the paid Power (individual) plan? Specifically, may a Power subscriber keep end-of-day history, including delisted US tickers, on a personal computer for private, non-commercial research that is never redistributed?
2. If storage is permitted on a paid plan, must the stored data be deleted when the subscription ends or is downgraded to Starter?
3. Section 1.6(c): is an internal count of trading days for which a ticker has an end-of-day record (no prices, no values) a "Derived Product"? May a Starter user keep such coverage counts, and the dates of the first and last available record?
4. Is ticker metadata from `/tiingo/daily/{ticker}` and `supported_tickers.zip` (name, exchange, start date, end date) "Tiingo Data" under Section 1.6(a)?
5. Are application logs that contain only HTTP status codes and request counts, and no data, acceptable under Section 1.6(a)?
6. Do you serve end-of-day history for delisted US equities under their historical tickers? How do you distinguish a reused ticker, and is a permanent security identifier (for example `permaTicker`) available through the API on the Starter or Power plan?
7. What are the current Starter limits (requests per hour, requests per day, unique symbols per month)?

## 9. WP0/A1 편입 전 필요한 검증

1. 개인 연구용 영구 보관을 허용하는 원천을 서면으로 확인한다. Tiingo Starter는 해당하지 않는다(1.6(a), (c)).
2. 회원 기간 안의 날짜로 공식 출처에서 issuer·share class–CIK 연결을 확인한다.
3. 공식 문서로 원거래 종가 정의를 확인하고 FULL 대조군에서 교차 확인한다.
4. 날짜가 붙은 분할·배당 사슬을 2번째 출처와 대조하고, 원종가와 이벤트로 수정 시계열을 재구성한다.
5. 회원 기간 안에서 거래가 끝난 모든 식별자의 종결대가(현금·주식·파산)를 증거로 확보한다.
6. PIT 조건: 어떤 이벤트·이름도 공개일 이전에 쓰지 않는다.
7. 새 content-addressed 입력 revision이 `us_departed_dataset_admission` AD1–AD8을 통과해야 한다.
8. 편입된 revision에서만 WP0 수익 기준 검사를 실행한다. 파일럿 자료로는 하지 않는다.

## 10. 소유자의 최소 행동과 자동화 범위

- **최소 행동(권장, 무료):**
  1. §8 질문을 Tiingo 지원팀에 보낸다.
  2. 답을 받으면 저에게 전달한다.
  - 이것만으로 "유료 Tiingo로 보존 가능한가"가 결정된다.
- **선택(무료, 결과는 남지 않음):**
  - Codespaces에서 `--check-connectivity` 후 `--run`을 실행한다.
  - 연결 기록(`…-access.json`)은 남기거나 커밋해도 된다. 여기에는 인증이 받아들여졌는지, 한도에 걸렸는지만 들어 있다.
  - 커버리지 수치는 `--show-transient-summary`로 화면에서만 볼 수 있으며 저장하면 안 된다. 연구 결손을 줄이는 결과는 아니다.
- **Claude(자동):**
  - 지원팀 답이 "유료 보관 허용"이면, 같은 20개 계획을 그 플랜용 보관 경로와 admission 관문으로 확장하는 설계를 만든다.
  - 답이 "불허"이면, EODHD 약관을 확인하는 단계로 넘어간다.
  - SEC 신원·종결대가 증거 수집은 언제든 자동화할 수 있다. 단, 이 환경에서는 SEC가 차단되어 Codespaces나 소유자 PC가 필요하다.
- **자동화 불가:** 토큰 입력, 약관 판단, 지원팀 문의, 결제, 연구 편입 승인은 소유자만 할 수 있다. GitHub Secret이나 Settings는 바꾸지 않는다.

## 11. 검증

- **오프라인 합성 테스트:** `tests/test_us_tiingo_recovery_pilot.py` 29개. 실제 토큰이나 시세는 쓰지 않았다.
  - **라이선스:**
    - 기본 실행은 연결 기록 1개만 쓴다.
    - 그 파일에는 종목명·세션·날짜·이름이 없다.
    - 응답 바이트가 어떤 파일에도 없다.
    - `--private-dir`·`--from-raw`가 없다.
    - 화면 요약은 파일로 쓰이지 않는다.
    - 결함 있는 허가 파일은 요청 전에 거부된다.
    - 연결 확인은 토큰 없이 실행되고 아무 파일도 쓰지 않는다.
  - **기존 항목 유지:**
    - 401/403/429/503 즉시 중단·무재시도
    - 차단 1회 후 중단
    - 404·깨진 JSON 기록
    - 상한·간격 준수
    - SEC 연락처 없으면 미실행
    - 토큰 미기록
    - 출력 덮어쓰기는 요청 전에 거부
    - 행 검증
    - 조정 계수와 이벤트 대조
    - HOLD·이름·기간·중복 상장
    - SEC 과거 이름 날짜 조건·CIK 충돌
    - 세션 표 SHA 대조
    - 가격 키 누출 거부
    - 표준 라이브러리 전용
    - 계획 재현
- **사전 고정 계획:** 계획 파일은 개정 전과 바이트 동일하다.
- **실제 Tiingo 응답:** NOT_TESTED. 이 환경의 연결 확인 결과는 세 호스트 모두 `BLOCKED_BEFORE_PROVIDER`다.
