# 공통 투자 연구 환경 v1

**INPUT_READINESS_ONLY / HISTORICAL_EXECUTION_NOT_AUTHORIZED**

기준 main은 `002b56434e3aa3e845798ec2ea7ca6d9267e3f7a`, 원천은
`signal-history@1bf68f59cffa20239977e2cfaa0f35a07d0ec884`다.
Study A/B/C의 가설, 승자 문턱, 통계 검정, 모델·조합 프로토콜을 정하지 않는다.
Claude의 Strategy Research Blueprint 확정본을 해당 연구 명세의 우선 기준으로 삼는다.
기존 연구의 노출 이력·종료 판정·봉인·이용권·production 정책을 변경하지 않는다.
독립 PR A의 주간 시점 수정과 이 브랜치는 같은 main에서 분기했고 서로 의존하지 않는다.

## 재사용 지도

| 기존 자산 | 이번에 재사용하거나 연결할 경계 |
|---|---|
| `replay_calendar.sessions`, `regional_alpha_features.MembershipSnapshots` | 거래소별 달력과 신호일보다 엄격히 이전인 구성 스냅샷 선택 |
| `ledger/universe/kr`, `krx_universe`, `krx_prices` | 당시 KOSPI 시가총액 Top120, as-traded OHLCV·상장주식수. 전체 한국시장으로 확대하지 않음 |
| `dart_derive`, `accounting_quality`, `kr_value_quality_catalyst.accounting_values` | 원 접수일 필터, CFS/OFS 일관성, TTM rollforward·자산/부채 수준 |
| `kr_alpha_atlas_inputs/matrix/catalogue/bars` | 기존 76열 특징·가용일·결측 사유 및 분할 확인일/거래정지 마스킹. 새 특징 행렬 엔진을 만들지 않음 |
| `finnhub_derive`, `us_cash_profitability.visible_records/features_as_of` | max(availableFrom, acceptedDate)의 날짜보다 이후에만 사용; 단위·TTM·180일 보고서 신선도 |
| `pit_data.PriceView/FundamentalStore`, `replay_inputs`, `us_dual_benchmark_data.SealedReader` | 기존 데이터 경계·내용 주소 검증. 이번 실측은 원 입력 허용 목록만 읽으며 봉인 실행기를 호출하지 않음 |
| S&P 당시 구성·섹터 스냅샷 | 195개 당시 스냅샷. 현재 S&P 목록을 과거에 적용하지 않음 |
| `longterm`, `risk`, `regime`, `kr_market_risk_model`, `kr_market_risk_overlay` | 기존 알파·모멘텀·위험·시장 상태 정의를 후속 특징 어댑터에서 재사용. 이번에는 점수/예측을 실행하지 않음 |
| `benchmark_alpha.REALISTIC_COSTS`, `portfolio_validation._dated_cost_policy`, `weekly_decision.trade_cost_fraction` | 날짜·시장·매수/매도별 비용, ETF/개별 주식 세금 차이. 새 비용 공식을 만들지 않음 |
| `prospective_receipt_core`, `historical_store`, `weekly_decision` | canonical/digest, append-only JSONL, evidence class, 원장 generation·영수증 참조 |
| `us_daily_market_data`, `us_persistent_daily_collection` | 실제 관측시각·CIK+symbol 잠정 신원·quarantine·수집 승인 계약. 반복 수집은 활성화하지 않음 |

`FundamentalStore`의 단순 as-of 조회는 날짜 당일도 허용할 수 있다. 새 공시 행은
`filing_prefix`가 기존 엄격한 공개일 필터를 호출한 뒤 위 빌더에 전달한다.
whole-history derive 후 필터링하거나 production 현재 스냅샷을 역사 입력에 합치지 않는다.

해시·봉인은 그대로 연결한다. replay-v16 `inputs.json`은 component 내용 주소와 manifest digest를,
역사 month shard는 model/feature/data/replay version을 가진다. 연구 결과는 원 spec hash,
dependencyHashes·원천 snapshot과 execution-lock의 당시 커밋에 연결된다.
`research_specs/`와 `docs/results/` 전체를 보호하는 등록이 있어 이 PR의 새 파일은 별도 경로에 둔다.
PR A가 바꾼 주간 시간 검증 코드의 hash를 과거 weekly replay protocol/result에 다시 쓰지 않는다.
그 결과의 정확한 코드는 원 커밋에서 읽어야 하며 새 코드로 재실행하거나 동일 연구로 덮지 않는다.

## 네 계층과 공통 키

공통 키는 **(market, signal_date, security_identity)**다. ticker는 표시 alias,
issuer ID는 발행사 연결이며, 주식 종류·개명·합병을 구분할 영구 증권 ID의 대용이 아니다.
영수증의 기존 (date, region, ticker, modelVersion)와는 별도 매핑 테이블로 연결한다.
기존 키·digest를 재작성하거나 issuer 수준으로 서로 다른 share class를 합치지 않는다.

| 계층 | 내용 | 물리적 분리 |
|---|---|---|
| Feature / Observation | `Key`, `Observation`, `Cell`, source/vintage, public available_at, 실제 observed_at, 당시 투자 가능 여부·산업·결측 | 미래 가격·수익·승자 라벨·예측 열 금지 |
| Label | `LabelReference`의 sample ID, H63/H126/H252, 체결/만기/공개시각, 종가·배당·분할·terminal 검증 참조 | 별도 파일/저장소. 현재는 값 reader·승자 라벨 빌더 자체가 없음 |
| Decision | 후속 연구의 예측·불확실성·판단시각·입력 hash·최대 5개 선택·ETF/현금 대안 | 실행 전향 영수증. 이번 코드에서는 예측/비중을 만들지 않음 |
| Portfolio Evaluation | 실제 체결·보유수량·기업행동 대가·비용·회전율·대안별 평가 | 모델 오차/종목 결과와 분리. 미해결 대가는 BLOCKED/UNRESOLVED |

`sample_identity`는 결측·탈락 행을 포함한 공통 표본의 키 digest다. 값/출처의 버전은
별도 `dataVersions` hash로 고정한다. Study A/B/C와 통제군은 같은 표본 ID 목록·자격 규칙을
사용하며, 결과가 알려진 뒤 탈락시키는 마스크를 각 전략마다 다르게 적용할 수 없다.
특정 연구가 필요한 셀과 자격은 Blueprint의 명세가 정한다. 공통 계약이 모든 결측을
일괄 삭제하거나 임의로 0을 넣지 않는다.

`PUBLIC_RECONSTRUCTION`은 당시 공개됐다고 재구성한 정보다. 취득일이 수년 뒤일 수 있으며
`PIT_EXACT` 또는 실제 전향 기록이라는 뜻이 아니다. `OBSERVED_PROSPECTIVE`는 사용된 원천의
실제 observed_at이 신호시각 이전이어야 한다. 실제 관측시각이 없으면 NOT_RETAINED이며
공개일/기간말을 관측시각으로 복제하지 않는다. 날짜만 있는 공시는 기존 필터대로 다음 날부터
사용한다. 정확한 intraday 시각의 별도 검증 없이는 당일 마감에 공개된 것으로 간주하지 않는다.

## 실제 입력 준비도

수치는 [readiness.json](readiness.json)의 원 입력 실측이다. 가격/공시 값, 역사 신호, 라벨,
성과·CAGR·모델 예측력을 산출하거나 게시하지 않았다. 분석에 쓴 스크립트는
[`inspect_experiment_sources.py`](../../scripts/inspect_experiment_sources.py)다.
Git 경로·내용 hash·원천 byte 수는 같은 JSON의 `sources`에 있다.

| 지표 | KR | US |
|---|---:|---:|
| 보존 가격 tape | 2011-01-03~2026-09-14 | 2011-01-03~2026-09-14 |
| 공통 주간 입력 범위 | 2013-01-04~2026-09-11 | 2013-01-04~2026-09-11 |
| 주간 날짜 / member-date / 당시 구성 종목 누적 | 714 / 85,680 / 260 | 715 / 359,526 / 829 |
| 대표 재무 core 가용률 | 42,768 / 85,680 = 49.916% | 254,629 / 359,526 = 70.824% |
| 가격+253세션 이력+core+산업 **라벨 존재** | 40,158 / 85,680 = 46.870% | 235,505 / 359,526 = 65.504% |
| 이 제한된 결합 입력 30개 이상 첫 날짜 | 2016-04-01 | 2013-02-15 |
| 같은 조건의 30개 이상 마지막 날짜 | 2026-09-11 | 2026-08-28 |
| 2026-09-11 구성원 / 재무 core / 결합 입력 | 120 / 114 / **110** | 503 / 12 / **11** |
| 검증된 PIT 거시를 추가한 결합 | 0 / 85,680 | 0 / 359,526 |

core 정의는 예측 변수 선정이 아닌 준비도 점검용 대표 묶음이다. KR은 양의 자산과 NI/OCF TTM,
US는 기존 CP의 현금·발생주의·영업수익성/자산 3개 비율이다. 모든 Study의 필요 변수를 대변하지 않는다.
KR에 새 180일 stale 규칙을 넣지 않았고, US는 CP의 기존 180일을 유지했다.
산업 열 존재는 정확한 PIT 분류 또는 신원 admission을 뜻하지 않는다. 따라서 **110/11은
H126·H252 예측용 입력의 상한**이며 승인된 모델의 후보 수/종목 추천/결과 평가 가능 수가 아니다.
2026-10-16 현재 시세의 후보 수는 새 가격과 신원 admission이 없어 UNRESOLVED다.
이 census는 양의 가격(한국은 양의 거래량도 요구)과 연속 세션의 **존재**를 센다.
가격 특징 계산·분할 확인일 검증·종결 payoff·전체 라벨 유효성까지 통과했다는 뜻은 아니다.

만기 도래 능력은 거래소 달력만 세었다. 다음 세션 체결, H세션 뒤 마감이 원 가격 마감일까지
오는 주간 날짜 수는 KR H63/H126/H252 = 701/687/660, US = 701/688/662다.
종결 대가·실제 종료 종가·배당의 확인이나 라벨 유효 건수를 측정한 것이 아니다.

### 실제 결함과 영향

- KR 보존 DART 9,351행/250 ticker, 공개일 2015-04-29~2026-09-16,
  실제 취득 2026-09-27~28. 접수일 일치 결함 2행은 기존 visible 필터가 제외한다.
  2013~2015 입력은 재무 core가 거의 없고, full-history 가용률이 이 공백을 숨겨서는 안 된다.
- KR 발행사 bridge는 254개 증권을 매핑하며 전향적으로 날짜가 검증된 발행사 이력이 아니다.
  6/260 = 2.308%는 exact DART 연결이 없다. 보통주 연결을 우선주로 자동 확장하지 않았다.
  2026-09-11에는 117/120 ticker가 매핑된다. 식별 정확성 97.5%라는 인증으로 쓰지 않는다.
  원 신원 inventory의 `listed/delisted`는 유니버스 포함기간과 경제적 상장기간을 혼동할 수 있어
  raw 당시 Top120을 대체하는 필터로 쓰지 않는다.
- KR 상장종료 22/260 = 8.462%의 종결 경제적 대가는 미해결이다. 마지막 종가, 0원,
  후속 발행사 재무를 자동 승계하지 않는다. terminal 정지·분할 확인 지연은 기존 bars 사유로 유지한다.
- US 최신 보존 Finnhub 34,947행/782 ticker. 공개일 2012-01-31~2026-10-13,
  취득 2026-09-13~10-15다. 기존 파일럿의 34,945행과 2행 차이는 최신 보존 commit 차이다.
  acceptedDate가 없는 1행도 따로 기록했으며 정확한 접수시각 증거로 승격하지 않는다.
  10/07~10/10 취득 618행 모두 `bs=[]`; 10/11·10/15 각각 추가 1행도 비었다.
  원 HTTP 응답이 없어 공급자 누락과 미인식 schema를 확정 구분할 수 없다. 재수집하지 않았다.
- 이 결손은 10월 신호만의 문제가 아니다. 뒤늦게 취득된 6월 보고서를 그 공개일 이후로
  재구성하면 7~9월에도 최신 bs가 없어 자산·부채·ROE·자산성장·현금/자산 비율이 사라진다.
  같은 입력 결합은 US 7/17 436개 → 7/31 260 → 8/07 88 → 8/28 33 → 9/11 11개다.
  오래된 정상 장부로 자동 fallback하거나 zero-fill하면 별개의 전략과 결측 선택편향이 된다.
- US 당시 구성 829 ticker 중 원 심볼의 가격 panel이 전혀 없는 것은 196개다.
  이는 신원 안전성을 검사한 뒤의 결손 수와 다르다. 보존 신원 메타데이터에는
  미해결 이탈 181, 다른 발행사의 ticker 재사용 29, 불완전 자기 이력 2가 있어 총 212개가
  별도 차단 대상이다. 14개 동일 증권 개명 중 대체 심볼이 명시된 13개도 자동 적용하지 않았다.
  CIK는 issuer ID이며 영구 share-class ID가 아니다. 현재 panel을 과거 발행사에 붙이면 안 된다.
- US 섹터 스냅샷은 label이 존재해도 sector/sub-industry, `Industries`, `Technology`,
  복수형 통신 표기 등이 혼재한다. JSON의 `industryLabelCensus`는 이를 별도로 센다.
  표준 coarse/구 통신 label 목록 밖 값은 3,777/359,526 member-date = 1.051%다.
  구성 파일에는 `American Airlines Group`, `RVTY (Previously PKI)`라는 비정상 심볼 문자열도 있어
  신원 metadata와 연결되지 않는다. 자동으로 AAL/RVTY로 고치거나 당시 구성에서 지우지 않았다.
  공식 S&P 편입/분류 기록의 독립 정확도와 taxonomy version은 UNRESOLVED다.
- macro 원 입력 5,736행에 release/vintage 필드가 있는 행은 0이다. 수정된 수치가 존재하는 것과
  당시 정보의 결합은 다르다. 이 경로에서 검증된 PIT 거시 결합은 차단한다. 기존 ALFRED 일부
  원천이 있다는 사실을 이 raw panel 전체가 PIT라는 주장으로 바꾸지 않는다.
- replay-v16은 내부 재구성 총수익 지수다. KODEX 200의 배당 이중 반영 감사와 별도 대조 시계열이
  이미 있으며, 새 연구가 수정본을 채택하려면 양쪽 leg의 같은 경제적 수익 정의·hash를 새로 고정해야 한다.
  SPY/US 원 종가의 배당 미조정 여부 외부 대조도 미완료다. 이번에는 가격/배당 값을 재해석하지 않았다.

연도별·산업별 분모와 비율은 JSON의 `byYear`, `byIndustry`에 전부 있다.
예: KR 금융업 core 32.847%(17,344 member-date), 지주/사업서비스 26.918%(3,024),
에너지/유틸리티 70.384%(2,708). US Financials 54.991%(51,985), Energy 57.328%(21,658),
Information Technology 79.907%(49,087). 분류 버전이 섞인 US raw 그룹을 정식 산업 간 비교로 사용하지 않는다.

### 있는 정보와 추가 준비

| 현재 보존/구현 | 남은 최소 준비 |
|---|---|
| 당시 구성·가격·공시 원 계정·공개일·일부 collectedAt | 영구 증권 신원, 개명/합병 날짜별 연결, raw 응답/수정 vintage admission |
| DART/Finnhub TTM·일부 성장·회계 품질·가격 위험 빌더 | Blueprint 필수 변수별 가용률, dependency별 public/observed 시간, source version 어댑터 |
| US 원 statement에는 일부 재고/매출채권 계정도 보임 | raw 존재만으로 공통 특징 구현 완료라 할 수 없음; KR 현재 canonical store에 없는 계정은 새 원천/허가 필요 |
| KRX 거래량·주식수·종가×거래량 proxy | 공식 거래대금 artifact·관측시점 근거, split 확인 지연 처리 계약 유지 |
| 과거/현재 receipt 형식·append-only 저장 | 새 연구 전향 승인과 spec/code/data hash, 실제 writer 시각, 원 데이터 vintage 보존, 만기 후 별도 결과 연결 |
| US 2026-10-09 505/505 일회성 수집 근거 | 반복 수집/보관 이용권·owner 승인·외부 영속 root·다일 운영 검증. 이번 작업에서 활성화하지 않음 |

결측 0 대체는 "미공시=사업 없음", "미측정 위험=무위험", "미해결 payoff=전액 손실/무수익"이라는
거짓 관측을 만든다. 허용된 train-only imputation은 후속 명세가 정하고 missing indicator와 사유를
유지해야 하며 source/label/경제적 대가 결손을 복구했다고 주장할 수 없다.

## A/B/C 준비 상태

| Study | 공통 기반 | 실제 실행을 막는 것 |
|---|---|---|
| A Winner / Fundamental Inflection | 공시 공개일 prefix, 재무 빌더, 동일 표본·별도 H 참조 준비 | 승자/비승자 정의 미확정, 최신 US bs 결손, issuer bridge·terminal·수익 기준 admission |
| B Conditional Regime | 같은 표본에 past-only 산업/가격 위험 특징을 연결 가능 | 일관된 산업 taxonomy 및 PIT 거시 release/vintage, Blueprint 조건/검정 확정 |
| C Dynamic Risk / Exposure | 기존 위험·비용·벤치마크 엔진과 Economics 계약 연결 가능 | 기대수익/불확실성의 승인된 공급자, 경제적 benchmark 대조, 실제 비중·회전율 평가 어댑터 |

기존 KR 역사 개발 프로그램과 US 실패한 31변수 연구는 닫힌 상태를 유지한다.
새 인터페이스로 포장하거나 chronological split을 추가해 같은 정보축 연구를 재개하지 않는다.
기존 exposed history는 후속 승인을 받더라도 탐색적 개발 자료이며 untouched OOS가 아니다.

## 연구 실행 전 필수 규약

1. 예측일 당시 공개된 정보만 사용한다. 원 접수일·acceptedDate·가용시각·vintage를 검증한다.
2. 라벨은 별도 저장하고 만기 세션 실제 마감 이후에만 공개한다. `LabelReference`는 거래소 H세션과
   final 시각을 검증한다. `Fold`는 train cutoff < evaluation start, 공개 deadline의 엄격한 이전,
   중첩 구간 purge를 강제한다. embargo 기간과 모델은 Blueprint가 정한다.
3. 결측·표본탈락 사유와 분모를 기록한다. 생존기업만 남기는 universe 변경은 금지한다.
   같은 기간·같은 당시 자격의 통제군과 common sample hash를 사용한다.
4. SPY/069500.KS와 개별 종목의 배당·분할·종결 대가·통화 기준을 일치시킨다.
   현실적 날짜별 왕복/전환 비용과 회전율을 별도로 평가한다.
5. 실제 최종 선택은 최대 5개다. ETF 잔여와 현금/현금이자 대안은 별도로 기록한다.
   이번 계약은 새로운 allocator나 자동 추천기가 아니다.
6. 평가 불가 값은 BLOCKED/UNRESOLVED이며 0이 아니다. 미검증 가격/terminal/benchmark는
   `Economics`/`Fold`의 차단 사유를 유지한다.
7. strategy/spec hash, code hash, source/data version hashes, seed, sample hash, UTC 생성시각,
   명시적 절대 result path를 기록한다. `preview_manifest`는 항상 PREVIEW_ONLY이며 실행 권한을 만들지 않는다.
8. 연구 결과를 production으로 자동 승격하지 않는다. execution gate·허가·one-shot lock은
   기존 연구에서 빌리거나 소모하지 않는다. 새 실행기의 구현·승인은 별도 PR이다.

## 재현과 다음 단계

네트워크/원천 읽기 없는 기본 명령:

```bash
python scripts/inspect_experiment_sources.py
pytest -q tests/test_experiment_workbench.py
```

읽기 전용 준비도 재현(명시적 Git 원천 파일 읽기; 새 외부 가격 취득 아님):

```bash
python scripts/inspect_experiment_sources.py --inspect --repo /path/to/Investment > /tmp/workbench-readiness.json
```

필요한 두 고정 커밋과 `sources`에 적힌 원 blob이 로컬에 있어야 한다. reader는
`GIT_NO_LAZY_FETCH=1`로 자동 원격 fetch를 금지하고, 허용 경로 밖 결과/라벨 읽기를 거부한다.
소스 취득 절차는 이 CLI에 없다. 봉인된 결과를 이용해 누락된 입력을 보충하지 않는다.
새 기본 CLI·모듈에는 역사 라벨/수익률 실행, 모델 학습, backtest sweep, 배포, 수집·영속 저장 writer가 없다.

지금 바로 가능한 첫 작업은 Blueprint 필수 필드가 정해지기 전의 **입력 준비도 census와 합성
계약 검증**이다. 통계/예측 실험의 첫 실행은 Blueprint 확정 → 새로운 정보축/기존 노출 여부 검토 →
필수 원천·신원·경제적 수익 admission → exact spec/code/data hash와 검정·sample·비용 고정 →
owner의 별도 역사 outcome 접근 승인 순서가 필요하다. 현재 PR은 그 실행 권한을 요청하거나 부여하지 않는다.

검증: 합성 표적 26개, ruff, compileall, /tmp seed 생성 및 allow-seed 검증을 통과했다.
실측 JSON의 10개 코드 hash, 443개 원 입력 참조와 연도/산업 합계의 원 분모 일치를 확인했다.
Python 3.12.14·pandas 2.3.0·numpy 2.3.1·exchange-calendars 4.11.1에서 측정했다.
필수 전체 suite 결과는 PR 본문에 기록하며, 기존 고비용 연구 workflow는 dispatch하지 않았다.
