# 미국 총자산(Total Assets) 출처 구제 — 증거 우선 타당성 v1

> 상태: **진단 경로만 준비됨. 실제 요청은 한 건도 실행하지 않았다.** 이 문서의 모든 "측정" 표기는 저장소에 기록된 과거 실행이거나 문서 조사이며,
> 이번 변경이 새로 측정한 값은 없다. 소유자 승인 항목은 맨 아래 "소유자가 승인할 것"이다.

## 한 줄 답

**"PIT를 잃지 않고, 출처가 증명되는 S&P 500 분기 총자산을 얻을 수 있는가?"** — 원리적으로는 *예, 단 SEC 공시(accession으로 묶인 값)에서만*.
벤더 경로 중 "원본 공시의 값 + 그 공시 자체의 제출일"을 시험이나 문서로 보인 경로는 아직 없다. 그리고 *SEC에 닿는 실행 환경이 있는가*가 아직 풀리지 않았다.
이번 변경은 그것을 풀지 않는다. 풀 수 있는 가장 작은 진단을 준비해 승인 앞에서 멈춘다.

## 출발점

Finnhub `financials-reported`는 2026-10-07 이후 처음 제공된 공시 619건에서 `bs`를 보내지 않는다. 소유자가 보고한 라이브 탐침(Actions run `38250579358`)은
12건 요청으로 `VENDOR_OMITS_BALANCE_SHEET_ENDPOINT_WIDE`를 확인했고 대체 키·`Assets`는 찾지 못했다(이 문서는 그 run을 다시 읽지 않았고, 그 탐침을 반복하지도 않는다).
따라서 다른 출처가 필요하다. 다른 출처가 허용되려면 값이 **하나의 공시(accession)** 와 **그 공시가 보이기 시작한 날**에 묶여야 한다.

## 데이터 계약 (`pipeline/us_total_assets_source.py`)

| 항목 | 규칙 |
|---|---|
| 동일성 | accession 일치만 `EXACT_ACCESSION`. CIK+기간말만 있으면 `WEAK`(값 대조용일 뿐 PIT 주장 불가). 티커만·기간말만은 `REJECTED` (APA처럼 한 티커가 두 CIK에 걸치는 경우를 테스트로 고정) |
| 가시 시점 | 그 accession의 제출일부터. `observedAt`(오늘 가져온 시각)은 기록만 하고 가용 시점으로 쓰지 않는다 (`visible_at`) |
| 원본 여부 | accession을 말하지 못하는 출처는 원본인지 정정본인지 가를 수 없다고 보고한다. 제출일이 저장된 값과 다르면 `PIT_FILING_DATE_IS_NOT_THE_ORIGINAL_FILING` |
| 값 | 단위·통화·기간말·CIK·티커·제출일·수락시각·출처 필드를 모두 기록하고, 저장된 보고값이 있는 통제군은 값 일치 여부까지 대조 |

## 고정 표본 (`docs/us-readiness/us-total-assets-source-sample-v1.json`)

저장된 Finnhub 원장(signal-history `9ca19d83`)에서 티커 해시 순서로 8개 티커 × 4개 그룹 = **32개 공시**. 어떤 출처의 응답이나 성과도 선택에 쓰이지 않는다.

| 그룹 | 의미 |
|---|---|
| `RECENTLY_MISSING` | 2026-10-01 이후 처음 제공되어 `Assets`가 없는 가장 최근 공시 (8) |
| `RECENT_COMPLETE` | 같은 티커의 직전 분기, 이전에는 완전했던 쪽 (8) |
| `HISTORICAL_EARLIEST` | 그 티커의 저장된 가장 이른 완전 공시 — 출처가 2013년까지 닿는가 (8) |
| `HISTORICAL_ANNUAL` | 2019년 말에 가장 가까운 10-K — 중간 시기 연간 통제군 (8) |

저장 모집단에는 정정 양식(10-K/A, 10-Q/A)이 0건이다. 그래서 "정정과 원본을 가를 수 있는가"는 저장 공시로는 검증되지 않고, SEC 응답이 같은 기간말에 여러 accession을 주는지로만 본다.

## 단계 A — SEC 재확인 (실행 대기)

과거 근거: 2026-09-04(모든 주소·헤더), 2026-09-13(4개 호스트), 2026-09-17(`data.sec.gov`·Archives·분기 ZIP 5/5, HTTP 403, 리다이렉트 없음, 0.4초 미만).
**블록이 사라졌다는 주장은 Actions의 실제 `data.sec.gov` HTTP 200 + 유효 페이로드가 있을 때만 한다** (`secBlockCleared`는 그 조건에서만 `true`).

요청 11건 (`probe_sources=sec`, 키 없음):

| 범주 | 호스트 | 건수 |
|---|---|---|
| 작은 공개 자원 `files/company_tickers.json` (대용량 아님) | `www.sec.gov` | 1 |
| Company Concept `us-gaap/Assets` | `data.sec.gov` | 8 |
| Company Facts | `data.sec.gov` | 2 |

- User-Agent의 연락처는 **소유자가 입력**한다 (`sec_contact`). 비어 있거나 이메일이 아니거나 noreply·예시 주소면 SEC 요청은 하지 않는다. 코드는 연락처를 만들어내지 않는다.
- 초당 2건 간격(SEC 공개 상한 10건/초의 1/5), 재시도 없음, 프록시·우회 없음. 같은 호스트가 연속 두 번 차단 페이지를 주면 그 호스트는 더 묻지 않는다.
- 결과 분류: 유효 데이터 200 / SEC·CDN 403 / 그 밖의 HTTP 오류 / 프록시 오류 / 네트워크 오류 / 200이지만 페이로드 무효. 호스트·요청 범주·상태·크기·시각·차단 표지(응답 전문 아님)를 기록한다.

## 단계 B — 기존 벤더 (실행 대기, 문서 조사 완료)

| 벤더 | 요청 | 문서로 확인한 것 (2차 출처) | 시험 전 모르는 것 |
|---|---|---|---|
| Finnhub 표준화 | `/stock/financials?statement=bs&freq=quarterly` | 프리미엄 엔드포인트로 기술됨, 원 공시에서 가공한 표준 재무제표 | 이 키의 권한, 응답에 accession·제출일이 있는지 |
| Massive | `/stocks/financials/v1/balance-sheets` | 구 `/vX/reference/financials`는 2026-06-22 중단(404) — 쓰지 않음. 40필드, `total_assets`, `filing_date`. Financials & Ratios 애드온 또는 Stocks Advanced 이상 필요로 기술됨. `filing_date`는 **해당 기간을 포함한 최신 공시**일이라 최초 가시일이 아님 | 이 키의 플랜, 요청 파라미터(`cik` 등)가 문서와 맞는지 |
| FMP | `/stable/balance-sheet-statement` | 과거 측정: `filingDate` 제공, `limit` 상한 5분기, 가장 이른 기간 2025-06, 퇴장 종목은 구독 심볼 제한 | S&P 500 심볼 범위, 링크에서 accession이 읽히는지 |

- 키는 헤더(FMP는 기존 방식대로 쿼리)로만 보내고 보고서에는 쓰지 않는다. 벤더의 거절 문장은 자격 토큰 모양을 가린 채 **그대로** 기록한다.
- 첫 요청이 곧 권한 질문이다. 401/402/403/429면 그 벤더는 더 묻지 않는다 (속도 제한은 커버리지 발견이 아니다). FMP만 깊은 구간(`limit=120`) 거절을 "깊이 상한"이라는 답으로 기록하고 계속한다.
- 요청 한도: 출처당 기본 최대 20(이 계획은 SEC 11 / Finnhub 8 / Massive 8 / FMP 9), `max_calls=0`은 계획만.

## 단계 C — 계약 대조

표본 32건 각각에 대해 CIK·원 티커·accession·기간말·제출일(+수락시각)·값·단위/통화·출처 필드·정정 구분 가능성을 위 계약으로 판정한다
(`check_filing`). 오늘 관측으로 과거 신호일의 가용성을 만들지 않는다 (`visible_at`이 거절).

## 단계 D — 순위와 권고

| 순위 | 경로 | 실제 접근성 시험 | 권한·비용 | 총자산 커버리지 | PIT 적합성 | 운영 복잡도 | 풀리지 않은 차단 요인 |
|---|---|---|---|---|---|---|---|
| 1 | **B. SEC 공식 벌크(Financial Statement Data Sets), 승인된 상시 호스트** | `NOT_TESTED` (Actions에서는 2026-09-04·17 ZIP 403) | 무료, 호스트는 소유자 것 | 2009년~ 분기별 sub/num (문서) | 최상: `adsh`·제출일·수락시각·정정 표지(`prevrpt`) | 중간 | SEC가 응답하는 호스트가 지정·시험된 적 없음, 최신 분기 공개 지연 미측정 |
| 2 | **A. SEC 직접 API, GitHub Actions** | `BLOCKED`(마지막 측정 2026-09-17), 재시험 대기 | 무료 | 문서상 전 XBRL 공시인, accession별 사실 | 최상: `accn`·`filed`·`form` | 낮음(닿는다면) | Actions 출구가 SEC 전 호스트에서 거절됨. 실제 200만이 해소 |
| 3 | **E. FMP (기존 키)** | 과거 측정으로 닿음·얕음 | 현 플랜 | 최근 5분기 — 누락 619건의 창과 같음, 2013 이력 불가 | 보통: 제출일·수락일·SEC 링크(accession 파싱 가능 여부 미시험) | 낮음 | 2025-06 이전 불가, S&P 500 심볼 범위 미측정 |
| 4 | C. Finnhub 표준화 | `NOT_TESTED` | 프리미엄으로 기술, 키 권한 불명 | 문서상 30년+ | 약함: accession·제출일 미기재(문서) → CIK+기간말 약한 동일성 | 호출은 쉽고 신뢰가 어려움 | 권한, accession 부재, 같은 공급원 위험 |
| 5 | D. Massive v1 | `NOT_TESTED` | 유료 애드온, 가격 미확인 | 2009년~, `total_assets` | 부적합(문서상): `filing_date`가 최신 공시일, accession 없음 | 호출 쉬움, 동일성 불가 | 플랜 권한, 최초 가시일 아님 |

**주 경로: B. 보조 경로: E.** (A는 Actions 진단이 실제 200을 받으면 주 경로로 승격 — 같은 출처 증명, 별도 호스트 불필요.)

- B가 주인 이유: 값이 accession·제출일·원본/정정 표지에 구조적으로 묶이고, 벤더가 필드를 다시 빼도 영향이 없다. 조건: SEC가 응답하는 호스트가 있어야 하며, 그 전까지 B는 *계획*이지 접근 가능한 출처가 아니다.
- E가 보조인 이유: 지금 닿고, 제출일과 SEC 링크가 오며, 5분기 창이 619건의 창과 일치한다. 조건: 링크에서 읽은 accession과 제출일이 저장값과 같은 공시에만 채택하고, 2013–2025 이력에 대한 주장은 하지 않는다.
- 기계 판독용: `docs/us-readiness/us-total-assets-source-decision-v1.json` (각 줄에 `evidenceBasis`: `TESTED_IN_REPOSITORY` / `DOCUMENTED_SECONDARY` / `NOT_TESTED`).

## 소유자가 승인할 것

1. 이 Draft PR 검토·병합 (변경: `fundamentals.yml`의 dispatch 전용 입력 2개 + 읽기 전용 작업 1개, 코드, 테스트, 문서. 예약 수집·PIT 원장·다른 작업은 바이트 동일).
2. main에서 **Collect fundamentals → region=`total-assets-source-probe`, probe_sources=`sec`, sec_contact=직접 확인하는 이메일** (SEC 11건, 키 없음) — "SEC 차단이 아직 있는가"에 답한다.
3. 같은 곳에서 probe_sources=`vendors` (max_calls 비움: Finnhub 8 + Massive 8 + FMP 9건, 키는 각 벤더 단계에만) — 권한과 제공 필드에 답한다.
4. 경로 B용 상시 호스트를 지정할지, 소유자 PC에서 1회 수동 내려받기로 시작할지 결정 (이 PR은 둘 다 만들지 않는다).

브랜치에서 실행하면 라이브 요청은 계획만 출력하고 키·연락처를 주입하지 않는다 (`LIVE_WITHHELD_NOT_MAIN_DISPATCH`). `max_calls`는 `00`·`21`·공백 포함을 게이트에서 거절한다.

## 하지 않은 것

예약 수집·백필 없음 / signal-history·Finnhub 원본 샤드 쓰기 없음 / 알파·IC·성과 계산 없음 / 동결된 H63·P4 결과 무변경 / 이 변경이 보낸 라이브 요청 0건 / Finnhub `financials-reported` 탐침 반복 없음.

## 알려진 한계

- 벤더 문서는 이 샌드박스에서 직접 열 수 없어(호스트 해석 불가) 검색 요약과 제3자 통합 문서로 확인했다. 권한 문구·필드 이름·정확한 파라미터(특히 Massive `cik`, Finnhub 응답 구조)는 **시험 전까지 추정**이며, 리더는 필드 후보 목록과 `fieldsSeen`을 기록하고 400류 응답은 벤더 문장 그대로 보고한다.
- 정정본 구분은 저장 모집단에 정정 양식이 없어 SEC 응답의 accession 다중성으로만 시험된다.
- B의 최신 분기 공개 지연, 가격, 벤더 약관은 확인하지 못했다.
