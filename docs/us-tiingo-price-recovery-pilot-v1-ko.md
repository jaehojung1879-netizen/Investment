# 미국 Tiingo 역사 가격 복구 파일럿 v1

**상태: 도구 구현·오프라인 검증 완료 / 실제 Tiingo 응답 NOT_TESTED / 모든 데이터 NOT_ADMITTED.**

- 이 작업은 무료 Tiingo 계정으로 기존 결손을 얼마나 메울 수 있는지 **가능성만** 측정한다.
- 수익률·라벨·CAGR·IC를 계산하지 않는다.
- replay-v16·봉인 데이터셋·C1·WP1·WP2·#256–#258의 파일을 바꾸지 않는다.
- 실제 실행은 소유자 PC에서 아래 명령 1개로 한다(§5).

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
| 무료 EOD 범위·호출 한도 | NOT_VERIFIED. 2차 출처는 시간당 50회·일 1,000회·월 500종목 등 서로 다른 값을 적고 있어 쓰지 않는다 | 응답 상태, `ratelimit`/`retry-after` 계열 헤더 이름, 429 발생 여부. 공개 가격 페이지의 한도 관련 문장 발췌 |
| 상장폐지·재사용 ticker | NOT_VERIFIED | `supported_tickers.zip`의 ticker별 행 수와 기간. 같은 ticker가 회원 기간 안에 2번 이상 있으면 HOLD |
| 원종가·수정종가·현금배당·분할 정의 | NOT_VERIFIED(공개 클라이언트 라이브러리의 필드명 `close/adjClose/divCash/splitFactor` 기준) | 필드 존재 여부. 수정 계수(`adjClose/close`) 변화가 배당·분할일과 일치하는지 수 |
| 개인 연구 저장·재배포 제한 | NOT_VERIFIED | 이용 관련 문장을 발췌해 보고서에 남김. **해석하지 않으며 소유자가 확인한다** |
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

## 5. 실행 (Windows, 저장소 루트에서 명령 1개)

```
py -3 scripts\run_us_tiingo_recovery_pilot.py --run
```

- **입력:** Tiingo 토큰만 입력한다. 화면에 표시되지 않는 프롬프트로 묻고, `TIINGO_API_TOKEN` 환경변수가 있으면 그 값을 쓴다. 토큰은 `Authorization` 헤더로만 보내고 URL·로그·결과·Git에 쓰지 않는다. 보고서와 실행 기록은 쓰기 전에, 원자료는 쓴 뒤에 다시 검사해 토큰이 있으면 거부한다.
- **요구 환경:** Python 3.9 이상, 표준 라이브러리만 쓴다(설치 불필요). `--run`이 없으면 미리보기만 하며 요청 0회, 파일 0개다.
- **요청 순서와 상한:**

  | 순서 | 대상 | 상한 | 간격 |
  |---:|---|---|---|
  | 1 | Tiingo 지원 ticker 목록 | 1회 | — |
  | 2 | Tiingo meta·가격 | 20×2회(최대 42회) | 2초 |
  | 3 | SEC | 최대 30회 | 0.25초 |
  | 4 | OpenFIGI | 2회 | 3초 |
  | 5 | Tiingo 공개 페이지 | 2회 | — |

  - 재시도는 없다. 401/403/429/5xx, 접근 차단, 시간 초과가 나면 그 출처를 즉시 멈춘다.
  - ticker별 404는 정상 답변으로 기록하고 다음 ticker로 진행한다.
- **저장 위치:**
  - 원자료: `%LOCALAPPDATA%\InvestmentPrivate\us-tiingo-price-recovery-pilot-v1\run-<UTC>\`에만 SHA 주소로 둔다. Git 저장소 안은 거부한다.
  - 공개 보고서: `docs/us-readiness/us-tiingo-price-recovery-pilot-v1-report.json`과 `.md`. 수·날짜만 담고, 가격 수준·배당액·분할비·수익률 키가 있으면 거부한다.
- **재분석:** 같은 원자료로 요청 없이 보고서를 다시 만들 때는 `--from-raw <run 폴더> --force`를 쓴다.
- **종료 코드:** 0 완료(어떤 판정이든) / 2 Tiingo 인증 거부·접근 차단 / 3 사전 거부(토큰 없음, 보고서가 이미 있음, 저장 위치 위반 등).

## 6. 보고서가 답하는 8개 질문과 사전 고정 판정

보고서(`questions`)에는 다음이 자동으로 들어간다.

1. 가격 응답이 있는 종목 수(20개 중)
2. 기존 결손 대비 추가 확보 가능 세션. 하한–상한, 2024년 이후 세션 수 포함
3. 독립 신원 확인 / Tiingo만 / HOLD / 무응답
4. 기업행동 lineage 미해결(단일 공급자 필드는 검증으로 치지 않음) / 회원 기간 안에서 거래가 끝나 종결대가가 필요한 종목
5. 기존 175개 후보(PARTIAL·FULL)에 대한 가치. Tiingo 행 존재, 배당·분할 필드 존재, 설명되지 않는 조정 단계 수로 본다. 기존 Source A는 배당·분할 필드가 삭제된 상태였다
6. 사용 호출 수와 212개 확대 시 예상 호출(424회). 무료 한도는 NOT_VERIFIED로 둔다
7. 판정
8. 편입 전 검증 목록

**판정 규칙(요청 전 고정):**

- `STOP_SOURCE_NOT_REACHABLE_OR_REFUSED`: Tiingo 차단·401·403·429·응답 0
- `STOP_CONTROLS_NOT_REPRODUCED`: FULL 대조군이 행을 받지 못했거나 회원 세션의 1%를 넘게 누락
- `STOP_FREE_COVERAGE_TOO_THIN`: HOLD가 아닌 목표 15개 중 창 안 행이 있는 것이 4개 미만
- `EXPAND_TO_212_FREE_TIER_FEASIBILITY`: 15개 중 8개 이상에 행이 있고, 설명되지 않는 조정 단계가 관측 세션의 0.1% 이하
- `LIMITED_VALUE_REVIEW_BEFORE_EXPANSION`: 그 밖의 경우

어떤 판정도 데이터를 편입하지 않는다.

**확대 조건과 중단 조건(212개):**

- **확대:** EXPAND 판정, 소유자의 이용 조건 확인, 그리고 429 없이 끝난 실행이 모두 있을 때만 한다. 212개를 2회씩 묻는 424회를 무료 한도 안에서 여러 날로 나눠, 같은 상한·간격·무재시도 규칙으로 실행한다.
- **중단:** 위 STOP 판정 중 하나, 이용 조건이 개인 저장을 금지한다고 확인된 경우, 또는 대조군의 신원이 Tiingo 응답과 충돌하는 경우다. 이때 같은 문턱을 낮춰 재실행하지 않는다.

## 7. Tiingo가 부족할 때 무엇을 먼저 볼지

| 측정 결과 | 먼저 검토 | 이유 |
|---|---|---|
| NONE 목표 대부분에 행이 없음(상장폐지 커버리지 부족) | EODHD | 상장폐지 ticker를 제품 특징으로 내세움. 무료 범위·조건·비용 NOT_VERIFIED, 유료 가능성 높음 |
| 행은 있으나 신원 미해결 | SEC EDGAR 증거 | 무료·공식이며 가격 공급자가 주지 않는 CIK·이름 이력 연결 |
| 신원은 풀렸으나 기업행동·종결대가 미해결 | SEC EDGAR 후 QuantConnect | 8-K·합병 문서가 대가를 준다. QuantConnect의 map/factor 파일은 플랫폼 안에서만 대조용으로 쓴다(조건 NOT_VERIFIED) |
| Tiingo 차단·거부·한도 초과 | 접근 문제 해결 전 아무것도 안 함 | 접근 실패는 출처가 아니라 네트워크를 측정한 것. 우회 금지 |

유료 대안의 비용은 이 PR에서 확인하지 않았다(`us-real-source-preflight-v1.md`의 NOT_VERIFIED 상태 유지).

## 8. WP0/A1 편입 전 필요한 검증

1. Tiingo 이용 조건이 개인 연구용 로컬 저장을 허용함을 소유자가 확인한다(공개 PR 재배포는 계속 금지).
2. 회원 기간 안의 날짜로 공식 출처에서 issuer·share class–CIK 연결을 확인한다.
3. 공식 문서로 원거래 종가 정의를 확인하고 FULL 대조군에서 교차 확인한다.
4. 날짜가 붙은 분할·배당 사슬을 2번째 출처와 대조하고, 원종가와 이벤트로 수정 시계열을 재구성한다.
5. 회원 기간 안에서 거래가 끝난 모든 식별자의 종결대가(현금·주식·파산)를 증거로 확보한다.
6. PIT 조건: 어떤 이벤트·이름도 공개일 이전에 쓰지 않는다.
7. 새 content-addressed 입력 revision이 `us_departed_dataset_admission` AD1–AD8을 통과해야 한다.
8. 편입된 revision에서만 WP0 수익 기준 검사를 실행한다. 파일럿 자료로는 하지 않는다.

## 9. 다음 단계 담당과 자동화 범위

- **소유자(약 5분):** 위 명령 1개를 실행하고, 생성된 두 보고서 파일을 커밋하거나 내용을 알려 준다. 보고서의 이용 조건 발췌도 확인한다.
- **Claude(자동):** 보고서를 받아 판정 규칙대로 다음 일을 정한다.
  - EXPAND면 212개 계획 생성과 다일 분할 실행 도구를 만든다. 실행은 이 도구를 그대로 쓴다.
  - STOP이면 §7 표의 다음 출처 조사를 준비한다.
  - SEC 증거 수집은 Tiingo 결과와 무관하게 자동화할 수 있다. 다만 이 환경에서는 SEC가 차단되어 소유자 PC나 허용된 네트워크가 필요하다.
- **자동화 불가:** 토큰 입력, 이용 조건 판단, 유료 결제, 연구 편입 승인은 소유자만 할 수 있다. Tiingo 비밀값을 GitHub Actions에 넣는 방식은 이 작업 범위에서 금지(Secret 추가 금지)다.

## 10. 검증

- **오프라인 합성 테스트:** `tests/test_us_tiingo_recovery_pilot.py` 24개.
  - 미리보기 0회 요청
  - 401/403/429/503 즉시 중단·무재시도
  - 접근 차단 1회 시도 후 중단
  - 404·깨진 JSON 기록
  - 상한·간격 준수
  - SEC 연락처 없으면 미실행
  - 토큰 미기록
  - Git 안 저장 거부
  - 보고서 덮어쓰기 거부(요청 전에 판단)
  - 원자료 변조 거부
  - 행 검증(비거래일, 비양수, OHLC 모순, 분할 0, 중복, volume None 유지)
  - 조정 계수와 이벤트 대조
  - HOLD·이름·기간 불일치·중복 상장
  - SEC 과거 이름 날짜 조건·CIK 충돌
  - 비공개 세션 표 SHA 대조
  - 가격 키 누출 거부
  - 표준 라이브러리 전용
  - 계획 재현
- **실제 Tiingo 응답:** NOT_TESTED. 작성 환경에서 `api.tiingo.com` CONNECT가 프록시 403으로 거부되었다.
- **CI:** `main`의 Tests는 #255 이후 `tests/test_rp1_c1_us_wp4d.py`의 38개 설정 오류로 실패 중이다. 그 수정은 #258에 있다. 이 PR의 CI가 실패하면 그 38개와 이 PR 자체의 결과를 구분해 보고한다.
