# 미국 Tiingo 역사 가격 복구 파일럿 v1 (개정 2: Starter 라이선스 확정)

**판정: Tiingo Starter(무료)로 역사 가격을 보존하는 경로는 NO-GO다.**
- 무료 계정은 메모리 안에서만 쓰는 임시 조회만 할 수 있다.
- 보존 가능한 역사 데이터에는 다른 원천이 필요하다.
- Power(유료)는 구독 기간에만 보관할 수 있고, 구독이 끝나면 삭제해야 한다(§7).

**도구 상태:**
- 메모리 전용 실행이며, 결과 보존 옵션(`--retention-authorization`)은 **제거**했다.
- 오프라인 합성 테스트를 마쳤다.
- 실제 Tiingo 응답은 NOT_TESTED이고, 모든 데이터는 NOT_ADMITTED다.
- 사전 고정한 20개 종목과 판정 규칙은 바꾸지 않았다(계획 파일 바이트 동일).
- 수익률·라벨·CAGR·IC를 계산하지 않는다.
- replay-v16·봉인 데이터셋·C1·WP1·WP2의 파일을 바꾸지 않는다.

## 0. 이용 약관 판정

**근거와 그 한계:**
- 약관은 [Tiingo Terms of Use](https://app.tiingo.com/tos/)이며, 소유자가 원문을 직접 확인했다.
- 이 작성 환경에서는 그 페이지를 열 수 없었다(DNS 실패·프록시 CONNECT 403). 그래서 아래 내용은 두 가지를 근거로 한다.
  - **소유자가 확인한 사실:** 아래 표의 '확인 출처'가 소유자인 행.
  - **검색 색인에 노출된 약관 문장:** 원문 일부로 보이지만 페이지를 직접 열람하지 못했으므로, 인용은 아래 문구 수준으로만 한다.

| 조항 | 내용 | 확인 출처 |
|---|---|---|
| 1.6(a) Starter·체험 | Tiingo Data를 영구·지속 저장소(로컬 장치, DB, 로그, 큐, 백업, 재해 복구)에 보관 금지. 처리는 휘발성 메모리나 비영속 임시 캐시에서만 하며, 계산 직후, 늦어도 프로세스·작업·세션이 끝나기 전에 영구 삭제 | 소유자 + 검색 색인 |
| 1.6(c) 파생물 | Derived Products도 같은 제한. 계산·일시 보유만 가능하고 영구 저장 금지 | 소유자 + 검색 색인 |
| 유료 플랜(Power 등) | Starter·체험이 아닌 유료 플랜이 **유효한 동안만**, 그 플랜이 허용하는 범위에서 저장 가능 | 소유자 + 검색 색인("solely to the extent permitted by that Paid Plan") |
| 종료 시 | 유료 플랜이 만료·해지·종료되거나 Starter·체험으로 내려가면, 원본을 모든 시스템(운영 시스템, 로컬 저장소, 로그, 큐, 아카이브, 백업, 재해 복구, 법정 보존 시스템)에서 즉시 영구 삭제 | 소유자 + 검색 색인 |
| 예외 계약 | 다른 보존 기간은 별도 서면 계약으로만 가능. **Starter와 Power에는 제공되지 않으며**, Start-up·Enterprise·Institutional이 대상 | 소유자 |

**도구에 미치는 결론:**
1. **원본 저장 제거:** 원본 응답을 파일로 두던 첫 설계는 1.6(a) 위반이라 삭제했다(개정 1). 실제 호출은 한 번도 하지 않았으므로 지울 원자료는 없다.
2. **보존 옵션 제거:** 개정 1의 `--retention-authorization`은 사용자가 쓴 임의의 JSON을 "공급자 허가"로 받아들일 수 있었다. 그러나 Starter에는 예외 계약 자체가 없으므로, 그런 파일은 허가의 증거가 될 수 없다. 이 옵션과 파생 보고서 쓰기 경로를 **완전히 제거했다**(개정 2).
   - 이제 옵션을 주면 argparse가 거부한다.
   - 허가처럼 보이는 파일이 저장소에 있어도 아무 영향이 없다. 두 가지 모두 테스트로 확인했다.
3. **유료 경로는 별도 과제:** Power나 상위 계약을 위한 보존 경로는 별도 개발 과제로 남긴다. 그 과제는 구독 유효 기간 확인, 종료 시 삭제 절차, 원본과 파생물의 구분을 설계해야 한다(§7).
4. **판정:** Starter로 212개 결손을 메운 결과를 연구 데이터로 남기는 것은 약관상 불가능하다. **NO-GO.**

### 무엇을 남기고 무엇을 버리는가

| 분류 | 예 | 처리 |
|---|---|---|
| 원본 응답 | meta·가격 JSON, `supported_tickers.zip` | 프로세스 메모리에만 존재. 디스크·로그·캐시에 쓰는 코드 경로가 없다(`Session`에 디렉터리 인자 없음) |
| 파생 결과 | 종목별 세션 수·날짜·신원 판정·배당분할 횟수·판정 | 종료 시 폐기. `--show-transient-summary`를 주면 몇 개 수치를 화면에만 출력. **쓰는 경로가 없다** |
| 연결 기록 | 호출 수, 도달 여부, 인증 수락 여부, 429 여부, 중단 사유, 한도 헤더 **이름** | 항상 `docs/us-readiness/us-tiingo-price-recovery-pilot-v1-access.json`에 쓴다. 어떤 종목이 응답했는지, 무엇을 받았는지는 담지 않는다 |
| SEC·OpenFIGI 응답 | 이름·CIK·FIGI | 같은 메모리 전용 경로를 쓴다. 결과 횟수만 연결 기록에 남긴다 |

터미널 스크롤백, 녹화, 복사도 "저장"이 될 수 있다. 그래서 화면 요약은 기본으로 꺼져 있으며, 켜더라도 내용을 파일·채팅·메모에 옮기지 않아야 한다.

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
| 개인 연구 저장·재배포 제한 | **Starter는 원본·파생물 영구 저장 금지, 예외 계약 없음**(§0) | 측정하지 않는다. 약관 페이지도 받아 오지 않는다 |
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
- **쓰는 파일:** 연결 기록 1개(`…-access.json`)만 쓴다. 파생 결과를 보존하는 옵션은 이 무료 파일럿에 없다.
- **종료 코드:** 0 완료 / 2 Tiingo 인증 거부·접근 차단 / 3 사전 거부(토큰 없음, 연결 기록이 이미 있음).

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

이 규칙과 8개 질문은 그대로 메모리에서 계산한다. 결과를 남기는 방식만 바뀌었다.

- **Starter:** 판정이 EXPAND여도 212개 확대는 하지 않는다. 남길 수 없는 결과는 연구 결손을 줄이지 못한다.
- **중단 조건:** STOP 판정이 나오거나 보관 가능한 원천이 없으면 중단한다. 문턱을 낮춰 재실행하지 않는다.

## 7. 비용 대비 지속 가능한 복구 방안 비교

질문은 하나다. **역사 연구 결손을 줄이려면 결과를 계속 보관할 수 있어야 하는데, 어떤 원천이 그 권리를 주는가.**

| 방안 | 보관 권리 | 비용 | 상장폐지·결손 커버리지 | 판정 |
|---|---|---|---|---|
| Tiingo Starter | **금지**(원본·파생물), 예외 계약 없음 | 무료 | 미측정 | **NO-GO** |
| Tiingo Power | 구독 **유효 기간에만** 허용 범위 안에서 가능. 해지·만료·하향 시 원본 전부 삭제 의무 | 약 $30/월(2차 출처, 공식 미확인) → 보관을 유지하려면 계속 지불(약 $360/년+) | 미측정 | **조건부**: 구독을 유지하는 동안만 쓸 수 있는 "임대" 데이터. 해지하면 연구 입력이 사라진다. 파생물의 해지 후 보존은 미확인 |
| Start-up·Enterprise·Institutional + 예외 계약 | 서면 계약으로 다른 보존 기간 가능 | 견적 필요(미확인, 개인 연구에는 과다 가능성) | 미측정 | 비용 대비 비현실적일 가능성이 높다 |
| EODHD 개인 플랜 | **미확인**: 저장 조항을 찾지 못함 | EOD All World $19.99/월 또는 $199/년. 무료는 하루 20회, 최근 1년 | 미국 상장폐지 심볼 60,191개 목록. 2018년 이전 상장폐지는 EOD만 제공. ticker 재사용 시 새 회사가 반환될 위험 | 저장 조항을 서면으로 받기 전에는 보류. 받으면 가장 유력한 유료 후보 |
| QuantConnect | 플랫폼 안에서만 쓰는 구조로 알려짐(미확인) | 연구 계정 무료(미확인) | 미측정 | 로컬 보관이 필요한 이 연구에는 부적합. 교차 대조용으로만 검토 |
| **기존 #241 후보 + SEC EDGAR 증거** | 후보: 공개 아카이브에서 이미 확보한 186,910세션, 재배포 권리는 UNVERIFIED. SEC: 미국 정부 공개 자료 | **추가 비용 0** | 175/212 식별자에 후보 가격 있음. 2024–2026 개선 0, NONE 37 | **가장 저렴한 지속 경로.** 새 가격을 사지 않고, 이미 있는 후보를 신원·종결대가 증거로 admission하는 데 집중 |

**가장 비용이 적은 지속 가능한 복구 방안(권장):**

1. **(무료) 기존 후보를 먼저 살린다.** #243에서 이미 확보한 186,910세션이 admission을 0세션도 통과하지 못한 이유는 가격이 없어서가 아니다. 신원·기준·lineage 증거가 없어서다. SEC EDGAR의 이름 이력·CIK·8-K 합병 문서로 그 관문을 채우면 새 가격 없이도 결손이 줄어든다.
   - 단, SEC 접근은 이 환경에서 막혀 있어 Codespaces나 소유자 PC가 필요하다.
   - 기존 후보 원천의 저장 권리도 소유자가 확인해야 한다(#241 재배포 감사 UNVERIFIED).
2. **(유료, 서면 확인 후) 남는 결손만 EODHD로 보충한다.** 대상은 NONE 37개와 2024–2026 구간이다. 저장 조항이 서면으로 확인되면 연 $199 수준에서 영구 보관 가능한 원천이 될 수 있다. 확인 전에는 결제하지 않는다.
3. **(조건부) Tiingo Power는 단기 교차 검증용으로만 쓴다.** 예: 한 달 구독으로 대조군 가격 정의를 맞춰 본다. 구독이 끝나면 원본을 삭제해야 하므로, 장기 연구 입력으로 쓰면 해지 시점에 데이터셋이 깨진다.

## 8. 남은 확인 질문 (영문, 그대로 복사)

Tiingo에는 아래만 남는다. 앞서 묻던 Starter 저장 여부와 예외 계약 여부는 소유자 확인으로 해결되었다.

1. On a Power plan, are Derived Products (for example internal counts of trading days with an end-of-day record, with no prices) also subject to deletion when the subscription ends, or may they be kept?
2. Do you serve end-of-day history for delisted US equities under their historical tickers, and is a permanent security identifier (for example `permaTicker`) available on the Power plan?

EODHD에는 이것을 묻는다.

3. For an individual EOD All World subscription, may a subscriber keep downloaded end-of-day history, including delisted US tickers, on a personal computer for private, non-commercial research indefinitely, including after the subscription ends? Is there any deletion obligation on cancellation?

## 9. WP0/A1 편입 전 필요한 검증

1. 개인 연구용 영구 보관을 허용하는 원천을 서면으로 확인한다. Tiingo Starter는 해당하지 않고, Power는 구독 기간 한정이다.
2. 회원 기간 안의 날짜로 공식 출처에서 issuer·share class–CIK 연결을 확인한다.
3. 공식 문서로 원거래 종가 정의를 확인하고 FULL 대조군에서 교차 확인한다.
4. 날짜가 붙은 분할·배당 사슬을 2번째 출처와 대조하고, 원종가와 이벤트로 수정 시계열을 재구성한다.
5. 회원 기간 안에서 거래가 끝난 모든 식별자의 종결대가(현금·주식·파산)를 증거로 확보한다.
6. PIT 조건: 어떤 이벤트·이름도 공개일 이전에 쓰지 않는다.
7. 새 content-addressed 입력 revision이 `us_departed_dataset_admission` AD1–AD8을 통과해야 한다.
8. 편입된 revision에서만 WP0 수익 기준 검사를 실행한다. 파일럿 자료로는 하지 않는다.

## 10. 소유자의 최소 행동과 자동화 범위

- **최소 행동(무료):**
  1. 이 PR(#259)을 NO-GO 기록과 메모리 전용 도구로 병합한다.
  2. EODHD에 §8의 질문 3을 보낸다.
  - 실제 `--run`은 할 필요가 없다. 결과를 남길 수 없으므로 연구 결손에는 영향이 없다.
- **Claude(자동, 소유자 승인 후):**
  - 무료 경로인 §7-1의 "SEC 증거로 기존 후보 admission" 설계를 시작한다. 실제 수집은 SEC에 접근 가능한 환경(Codespaces 또는 소유자 PC)이 필요하다.
  - EODHD가 저장을 허용한다고 답하면, 같은 20개 계획으로 별도 유료 경로 PR을 설계한다. 그 설계에는 구독·보관·삭제 정책을 포함한다.
- **자동화 불가:** 토큰 입력, 약관 판단, 공급자 문의, 결제, 연구 편입 승인은 소유자만 할 수 있다. GitHub Secret이나 Settings는 바꾸지 않는다.

## 11. 검증

- **오프라인 합성 테스트:** `tests/test_us_tiingo_recovery_pilot.py` 25개. 실제 토큰이나 시세는 쓰지 않았다.
  - **라이선스:**
    - 실행은 연결 기록 1개만 쓴다. 그 파일에는 종목명·세션·날짜·이름이 없다.
    - `--retention-authorization`을 주면 argparse가 거부하고, 요청은 0회다.
    - 허가처럼 보이는 JSON 파일이 있어도 아무 영향이 없다.
    - 코드에 보존·원자료 경로 문자열이 없다.
    - 응답 바이트가 어떤 파일에도 없다.
    - 화면 요약은 파일로 쓰이지 않는다.
    - 연결 확인은 토큰 없이 실행되고 아무 파일도 쓰지 않는다.
  - **분석(메모리 안에서 검사):**
    - 8개 질문과 판정 계산
    - HOLD·이름·기간·중복 상장
    - SEC 과거 이름 날짜 조건·CIK 충돌
    - 조정 계수와 이벤트 대조
    - 세션 표 SHA 대조
    - 가격 키 누출 거부
  - **전송:**
    - 401/403/429/503 즉시 중단·무재시도
    - 차단 1회 후 중단
    - 404·깨진 JSON 기록
    - 상한·간격 준수
    - SEC 연락처 없으면 미실행
    - 토큰은 헤더로만 보냄
    - 연결 기록 덮어쓰기는 요청 전에 거부
  - **기타:** 표준 라이브러리 전용, 계획 재현.
- **사전 고정 계획:** 계획 파일은 개정 전과 바이트 동일하다.
- **실제 Tiingo 응답:** NOT_TESTED. 이 환경의 연결 확인 결과는 세 호스트 모두 `BLOCKED_BEFORE_PROVIDER`다.
