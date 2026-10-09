# Phase C — 결과 접근 전 가격 무결성 수정과 v2 입력 개정

PR #214 안에서 사용자가 명시적으로 허용한 **입력 무결성 수정·버전 개정**이다. 새 alpha 연구가 아니다. v1 원문·sidecar·113개 과학 의존성·235개 보호 파일을 보존한다. 이 문서의 수익률 숫자는 명시적으로 승인받은 **069500.KS 벤치마크만**의 감사다. 개별 주식 보유 수익률·미래 라벨·모형 적합·IC·스프레드·포트폴리오 성과를 계산하지 않았다.

**현 상태는 BLOCKED_PRE_OUTCOME이다.** 벤치마크는 모든 연도에 대조되었지만, 006800.KS의 알려진 가격 문제를 전 기간 차단하면 `H08_equalVsCapWeightIndustry`의 usable-range coverage가 **53.748789%**로 원래 Phase B 60% 기준 아래로 떨어진다. `H01_industryRelMom126`도 미달하여 B0/B4가 INSUFFICIENT_COVERAGE이고, X3도 coverage 부족이다. 수정 matrix/PIT 재구성과 정식 실행 readiness는 구분한다. 후보·baseline을 삭제하거나 기준을 낮춰 정식 실행하지 않는다.

기준 main은 `c9c636ec06a6118718ba009b12262d600cecbbfb`다. [초기 감사](kr-alpha-atlas-phase-c-integrity-audit-ko.md)와 당시 FAIL 증거를 보존한다. 아래의 수정 입력은 새 source vintage와 원래 고정 Git 자료에 대한 명시적 overlay이며, 새 파일을 기존 snapshot으로 재명명하지 않는다. production 취득/거래 코드는 수정하지 않는다.

## 원인과 수정 범위

1. **ETF:** `_naver_range_frame` → `korea_prices.acquire` → `price_adjustment.to_total_return`가 한국 가격을 분배금 미조정으로 가정한다. 069500.KS 네이버 가격에는 이미 현금 분배 조정이 있고, Yahoo actions를 다시 적용하면 중복 조정된다. 공식 시장 종가·분배금·vendor 조정 척도와 내부 척도 관측이 이 경로를 뒷받침한다. 원래 취득 당시 vendor 원응답과 ETF actions 전부가 보존되지 않아 과거 취득을 바이트 단위로 완전히 분해했다는 주장은 하지 않는다.
2. **개별 주식:** ETF 관측을 전체 주식에 일반화하지 않는다. 먼저 commit `60a5692`에 6종목·3개 창을 고정했다. Top120-ever 260개의 ID에서 고정 salted SHA 순위 4개와 삼성전자/NAVER 분할 통제 2개다. 일반 현금배당에서 동일 중복은 검출되지 않았다. 다만 006800.KS의 2026-03-16 vendor/raw 척도 변화는 단일 현금 factor `1.0043352601`, 내부/raw는 그 제곱 `1.0086763533`이다. 별도 주식배당 권리 `0.0073206`주와 현금배당을 같은 것으로 처리할 수 없다. 2018-03-28에도 등록 기업행위로 설명되지 않는 약 2.3512% source 척도 차이가 남는다.
3. **마지막 세션:** 별도 commit `714fff4`에 260종목의 2026-09-10/11/14 고정 날짜 source 검사를 선언했다. 비교 가능한 238종목의 앞 두 날짜 조정 척도는 일치하지만, 마지막 날짜 220종목은 다르다. 취득 시점 문제인지 vendor 정정인지는 원응답 부재로 확정하지 않는다. 기존 고정 KRX 원자료의 **동일 세션 OHLCV**를 직전 검증된 index 척도로 환산한다. 양의 거래량까지 확인된 235종목만 복원한다. `001570.KS`, `002410.KS`, `011810.KS`는 마지막 세션 거래량이 검증되지 않아 가격을 만들지 않는다.

006800.KS는 단일 사건 patch로 전 기간을 정상이라고 선언하지 않는다. **전 기간 OHLC 가격 기반 입력을 NaN으로 차단**한다. PIT universe의 이름·행은 남기고, 별도로 검증된 KRX 거래량/거래대금 proxy·회계 정보는 보존한다. 모든 모형의 결과 유효성 mask가 동일하게 적용된다. 이 이름을 선택하거나 유효하지 않은 industry reference가 필요한 paired 경제 비교는 BLOCKED다. 기존 22개 terminal 경제 문제와 마지막 세션 거래 정지 문제도 0 payoff나 last-price exit로 만들지 않는다.

[종목 source 보고서](audits/kr-alpha-atlas-phase-c-integrity/stock-price-integrity.json), [마지막 세션 보고서](audits/kr-alpha-atlas-phase-c-integrity/final-session-source-integrity.json), [표본 선언](audits/kr-alpha-atlas-phase-c-integrity/stock-price-audit-sample.json)이 검사 범위와 한계를 보존한다. 마지막 세션 복원 뒤 나머지 표본의 source 척도 잔차는 해소되며, 2018 NAVER의 약 0.000881% rounding 잔차는 남는다. 이 표본은 260종목의 모든 기업행위를 독립 인증한 자료가 아니다.

기업행위 근거는 [KRX 주식배당 공시](https://kind.krx.co.kr/external/2026/03/13/000897/20260313000999/61474.htm), [KRX 파생상품 조치](https://kind.krx.co.kr/external/2026/03/04/001478/20260304003383/70873.htm), [KOSCOM 배포 KRX 상장 공지](https://spn.stockplus.com/news/api/v1/disclosure_views/koscom/456410)다. 삼성선물의 HTTP 200 WAF 거부 응답은 기업행위 증거로 사용하지 않는다. URL·시각·raw bytes·SHA-256을 별도 manifest에 보존한다.

## 벤치마크 경제 정의와 독립 대조

벤치마크는 **069500.KS, KODEX 200 ETF** 그대로다. 삼성자산운용 [시장 종가 XLS](https://www.samsungfund.com/excel_standar.do?fId=2ETF01&gijunYMD=20261007)의 종가 열과 공식 gross 분배액을 사용한다. NAV·과표기준가·KOSPI200 PR/TR/NTR·vendor adjusted close는 서로 대체하지 않는다.

공식 [상품 API](https://www.samsungfund.com/api/v1/kodex/product/2ETF01.do)의 200개 월간 report index에서 2014–2022년 3월 PDF를 찾았다. 8개 정상 PDF의 각 최근 6회 실제 지급표를 겹쳐 검증했고, 2021–2026년 공식 20회 API 지급표와 연결했다. 2015 PDF는 429 거부지만 2016 PDF가 2014–2015년 지급을 포함한다. 2012–cutoff의 46개 지급이 완전 연결된다. 없는 지급을 0으로 추정하지 않는다. [PDF·추출 text·해시 계보](audits/kr-alpha-atlas-phase-c-integrity/benchmark-history/sources.json)를 보존한다. NAV 연간 성과 숫자는 사용하지 않는다.

수정 주계열은 공식 **raw ETF 시장 종가**와 gross cash entitlement를 이용한 `growth[t]=(P[t]+D[t])/P[t-1]`이다. 분배락 종가 재투자 총수익 관례이며, 지급일 이전 분배금 채권 인식을 포함한다. 실제 지급일 현금 receipt나 차입 거래 전략을 재현하는 것이 아니다. 투자자 배당세 전이며 ETF 자체 보수는 시장가격에 포함되고, benchmark 거래 비용 15bp씩은 기존 경제 엔진에서 별도 적용한다. 과거 vendor factor `P[t]/(P[t-1]-D[t])`와 경제 정의가 다르므로 그 차이는 NOT_COMPARABLE 진단에 둔다. 통과하기 좋은 식으로 정의를 선택하지 않았다.

독립 대조의 가격 publisher는 네이버다. 해당 adjusted-close 현금 factor를 같은 공식 지급으로 역변환하고 **자체 최신 endpoint**에서 출발한 raw 가격을 동일 재투자 식으로 계산한다. 2026-09-14의 두 raw 종가 모두 105,410원이며 다음 예정 분배 기준일 전 캡처다. issuer endpoint에 강제로 맞추지 않는다. 두 가격 publisher는 독립이지만 **분배 원천은 공유**한다. 현금 이력을 두 번 독립 관측했다고 주장하지 않으며, vendor 가격 반올림과 새 vintage 한계를 명시한다.

별도 [동일 세션 raw 가격 진단](audits/kr-alpha-atlas-phase-c-integrity/benchmark-same-session-source-diagnostic.json)에서도 3,612세션의 최대 상대 가격 차이는 약 0.045886%, 중앙값은 약 0.009814%다. 이는 source 정밀도 진단이며 새 통과 기준이나 stock alpha 통계가 아니다. 연간 등록 gate는 아래의 0.50pp만 사용한다.

연간 anchor는 전년 마지막 KRX 세션, 종료는 해당 연도 마지막 세션 또는 cutoff다. 모든 같은 세션을 요구한다. 고정 기준 **연간 절대 차이 ≤0.005, 즉 0.50pp**를 완화하지 않았다. 2026년은 cutoff까지의 부분 연도다. [완전 대조 JSON](audits/kr-alpha-atlas-phase-c-integrity/benchmark-reconciliation-corrected.json)에 source SHA·정의·세션 수·수익률·차이·상태가 있다.

| 연도 | 일치 세션 | 공식 ETF 총수익 % | 독립 가격 대조 총수익 % | 공식 minus 독립 pp | 상태 |
| --- | ---: | ---: | ---: | ---: | --- |
| 2013 | 247 | 1.095037 | 1.074322 | +0.020716 | PASS |
| 2014 | 245 | -6.581597 | -6.599115 | +0.017517 | PASS |
| 2015 | 248 | -0.117289 | -0.124552 | +0.007263 | PASS |
| 2016 | 246 | 10.187046 | 10.196246 | -0.009200 | PASS |
| 2017 | 243 | 27.100017 | 27.104107 | -0.004091 | PASS |
| 2018 | 244 | -17.321000 | -17.332722 | +0.011722 | PASS |
| 2019 | 246 | 14.399436 | 14.408391 | -0.008955 | PASS |
| 2020 | 248 | 35.532786 | 35.556449 | -0.023663 | PASS |
| 2021 | 248 | 2.999087 | 2.999633 | -0.000546 | PASS |
| 2022 | 246 | -24.149926 | -24.154224 | +0.004299 | PASS |
| 2023 | 245 | 24.842428 | 24.855570 | -0.013142 | PASS |
| 2024 | 244 | -9.371531 | -9.362387 | -0.009144 | PASS |
| 2025 | 242 | 94.206882 | 94.193585 | +0.013298 | PASS |
| 2026 | 172 | 74.409288 | 74.403364 | +0.005924 | PASS |

필수 평가 연도 2016–2026와 추가 2013–2015 모두 PASS, 최대 차이는 약 0.023663pp다. 이것은 benchmark integrity 증거다. 주식 alpha 증거가 아니다.

## v1 보존과 명시적 개정

원본 등록 SHA-256은 `b57be30ce54abf1dd26388954053e99d4b1bf71fa06f3598787317e953988db0`, 원본 matrix digest는 `32e49b57a7541eea66f76373baef50c6302a394247b313f6099f718d46d54b0c`다. 원본 JSON을 VERIFIED로 편집하거나 sidecar를 다시 만들지 않았다.

새 [v2 개정](../research_specs/kr-alpha-atlas-phase-c-v2-amendment.json)은 원본의 명시적 overlay다. 수정 source exact SHA, corrected input identity, corrected matrix, 추가 코드/workflow/test closure, effective contract hash를 별도 고정한다. 원본의 38후보·73개 feature/horizon reading·B0–B4·30 family comparison·X1–X6·cutoff·horizon·BY/Holm·결측 대체·훈련 연대기·선택 및 비용·capacity·decision threshold는 유지한다. X4는 SOURCE_BLOCKED다. H21/H126 추론, H63/H252 및 X6 descriptive 구분도 유지한다. 거래대금은 `PROXY_ASTRADED_CLOSE_X_VOLUME`이다.

바뀌는 것은 입력 계보/가격 유효성, benchmark gross TR의 경제 정의와 대조 evidence, 새로운 승인 파일 경로 및 이에 필요한 설명·추가 코드 해시다. v1의 benchmark gate는 BLOCKED_UNVERIFIED로 남는다. **v2 effective contract의 gate만** 검증된 증거를 근거로 VERIFIED다. 주식 gross label의 기존 partial-distribution index 정의는 유지되며 완전 주주 총수익으로 이름을 바꾸지 않는다. 주식 지급·terminal·PIT-reconstructed industry·vendor vintage 한계는 결과에 남는다. 경제 진단과 prospective nomination은 전체 기존 decision chain을 만족할 때만 가능하며, 검증된 미래 alpha나 실투자 세후 성과라는 주장은 할 수 없다.

첫 v2 초안 `119d66d6d338b1645704301656ef197e27b9617e415f99eae3bb740671f64b2d`로 full preflight를 실행했고, H08 coverage gate에서 실제로 거부됐다. 이 초안을 [authoring 기록](audits/kr-alpha-atlas-phase-c-integrity/proposed-amendment-before-source-refusal.json)에 보존한다. 아직 병합/실행하지 않은 같은 v2 개정에서 감사 보고 경로만 보완했다. source coverage의 BLOCKED 상태·숫자·이미 검증된 행렬을 기록한 뒤 CLI는 exit 2를 반환한다. 정식 경로는 기존과 같이 source gate 실패 시 claim 전에 예외를 내며, 가설·입력 값·threshold·원본 v1의 어떤 바이트도 바꾸지 않았다.

두 버전의 연구 ID, 결과 artifact prefix, 결과 path 및 **영구 global ref** `refs/tags/kr-alpha-atlas-phase-c-v1-execution-lock`는 같다. workflow concurrency group도 같다. v2 전용 영구 잠금으로 새 연구 기회를 만들지 않는다. v1과 v2 모두 정식 실행하는 것은 불가능하다. 수정 후에는 v1을 정식 실행 대상으로 승인하지 않는다. 가설 탐색을 재시작하지 않으며, 한 번의 development 평가 뒤 Phase D로 한국 역사 연구를 닫는다.

## 전체 수정 입력 준비 및 재현 명령

새 loader는 먼저 **기존 pin/원래 input identity를 완전히 검증**하고 명시적 correction만 적용한다. 단일 thread의 scoped injection으로 **기존 `preflight.prepare`와 `MX.build_matrix`를 그대로 호출**한다. 원본 raw snapshot은 덮어쓰지 않는다. 새 scientific engine을 복제하지 않는다.

수정 matrix를 고정하기 위한 전체 preparation과, 고정 후 별도 fresh directory에서의 production-equivalent full preflight를 구분한다. 후자는 actual main/조상 관계, v1·v2 closure, Git objects/schema, source hashes, runtime/thread, 실제 714 signal·85,680행·76열·260 universe ID, corrected digest, PIT visibility/결측 사유, calendar/maturity, StudyData·B4 coverage, 메모리/디스크 및 immutable persistence를 확인한다. hard firewall은 target/model/statistics/portfolio/formal permit/lock entry를 거부한다.

실제 측정 receipt와 검증 결과는 [corrected preflight](audits/kr-alpha-atlas-phase-c-integrity/corrected-full-input-preflight.json) 및 [validation receipt](audits/kr-alpha-atlas-phase-c-integrity/v2-validation.json)에 기록한다. H08 gate 실패는 숫자를 숨긴 generic error나 성공 상태로 바꾸지 않는다. B4 약 44.3%의 기존 공통 range 분모와 전체 행렬 분모를 구분한다. complete-case 삭제로 연구를 바꾸지 않고, 훈련 전용 결측 대체·missingness indicator와 동일 evaluation outcome mask를 사용한다. source 차단의 이름/연도/산업별 행 수도 공개한다.

최종 full preparation은 **1,021.935초**, 최대 RSS **1,744,629,760 bytes(약 1.625GiB)**다. 새 input SHA는 `0b41893469c551ce51c7e6f7d99bc3e90521ee5b880d25756443c69d052b8852`, 등록/실제 matrix 모두 `a7517a934089385f566f8969cc2407d7e3b5cea6ab926ad85480dfa9baa1a0ca`다. 805,676 filing-based 셀의 PIT 위반 0, 1,660,493 결측 셀의 이유 누락/미등록 이유 0을 확인했다. 직접 가격 차단은 FINANCIALS 714 name-date행(전체의 0.833333%)이며 peer 산업 특성에도 영향을 준다. 원래 결측 1,542,935셀에서 117,558셀 늘었다. B4 공통 65,400행의 완전 관측률은 **38.261468%**(전체 행렬은 29.205182%)이며, 원래 공통 분모의 44.319572%와 비교해야 한다. B4의 결측 지표/훈련 전용 대체는 유지하지만 필수 H01 source coverage gate 자체를 없애지 않는다. B1/B2/B3와 X1/X2/X5/X6의 source readiness는 READY, X4는 그대로 SOURCE_BLOCKED다. 수정 입력의 재구성은 PASS이며 정식 실행 readiness는 BLOCKED, CLI exit code는 2다.

```bash
python scripts/run_kr_alpha_atlas_phase_c.py validate
python scripts/run_kr_alpha_atlas_phase_c_amended.py validate
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  python scripts/run_kr_alpha_atlas_phase_c_amended.py preflight \
  --expected-main VERIFIED_MAIN_SHA --work /tmp/atlas-v2-fresh-preflight
python scripts/audit_kr_alpha_atlas_price_integrity.py benchmark \
  --output /tmp/atlas-benchmark-fresh.json
python scripts/audit_kr_alpha_atlas_price_integrity.py stock-source \
  --output /tmp/atlas-stock-source-fresh.json
```

benchmark 계산 명령은 benchmark-only 감사 승인이 있을 때만 사용한다. 감사용 `xlrd==2.0.2`는 issuer XLS 파싱에만 필요하고 정식 runtime 의존성을 변경하지 않는다. 위 명령은 승인 파일·영구 잠금·alpha 결과를 만들지 않는다. 실제 정식 엔진은 owner가 exact v2 contract를 승인한 후에만 실행 가능하다.

## 잠금 순서·예산·실패 정책

actual clean merged main → owner가 commit한 exact v2 승인/manual main actor → spec/source/dependency 확인 → v1/v2 이전 결과·global lock 확인 → exact runtime/resources → 같은 전체 수정 준비·PIT·합성·budget·기록 probe → main/lock/hash 재확인 → atomic global ref → 최초 허용 stock outcome 경계 → 동일 엔진 한 번 → exact-byte result/provenance persistence다.

Git 부재·download/체크섬·행렬·runtime/import·메모리/시간·합성·쓰기 실패는 **claim 전에** 거부한다. global ref가 만들어진 뒤 auxiliary ref/API verification이 실패해도 소비된 것으로 취급한다. 잠금 상태 불명은 거부하고 독립 ref 확인 전 재시도하지 않는다. 결과 저장/업로드 실패는 이미 계산된 exact byte의 복구만 허용하며, 재학습/재평가·잠금 삭제는 금지한다. 같은 `ordered_once`, `GitHub.claim`, permit 및 immutable writer를 재사용한다. 실제 잠금 시험은 하지 않았다.

등록된 90분/8GiB/최대 예측 적합 574회 및 workflow 110분은 유지한다. formal 예산은 preparation을 포함한다. 전체 실제 alpha runtime은 측정하지 않았으므로 합성 runtime이나 preparation 시간을 그 측정으로 제시하지 않는다. runner의 8GiB memory capacity 및 1GiB 이상의 준비 전 여유 disk를 먼저 확인한다. resource 초과는 scope 축소가 아닌 pre-outcome 거부다. 잠금 뒤 resource failure는 소비되며 자동 재실행하지 않는다.

Pages의 얕은 checkout/missing-pins 문제는 기존 #214 수정대로 full history와 두 정확한 source commit fetch만 추가한다. 역사 테스트·identity 보호를 약화하지 않는다. PR에서 Pages 배포를 실행하지 않는다. main의 기존 Pages 실패와 수정 PR Tests 결과를 구분한다.

신규 workflow를 문서화할 때 기존 두 inventory 파일이 각각 봉인/v1 계약에 고정되어 있다는 점도 보존한다. 별도 [inventory layer](workflow-inventory-phase-c-amendment.md)를 추가하고, 보호 파일이 아닌 census test의 문서 입력 목록만 확장했다. ACTIVE/RETIRED/on-disk 일치 조건을 삭제하거나 약화하지 않았다. 로컬 전체 pytest 최초 실행은 4,162 passed·2 inventory 문서 실패·1 skipped·4 xfailed였으며, 수정 후 관련 감사·개정·inventory 60개 테스트가 통과했다. 최종 head의 전체 CI는 별도로 확인한다.

## 사람이 해야 할 최소 다음 조치

현재 정식 실행 승인을 요청하지 않는다. H08 및 필수 baseline H01의 source coverage가 원래 기준을 통과하지 못하는 한 amended formal preflight도 반드시 잠금 전에 거부한다. 필요한 최소 조치는 006800.KS의 역사적 조정/기업행위 원천을 확보해 재현 가능한 가격 basis를 검증하거나, **H08·H01/B0/B4·X3를 삭제/완화하지 않고 명시적 source-blocked 결과로 남기는 부분 실행을 별도 결과 접근 전 등록 결정으로 승인할지** 사람이 정하는 것이다. H08만 빼도 해결되는 문제는 아니다. 그 결정/수정도 #214 안에서 해야 하며, 아직 그러한 부분 실행 개정을 구현하거나 승인하지 않았다. 양질의 입력이 없는 상황에서 이 PR을 준비 완료라고 표시하거나 merge/execute를 요청하지 않는다.

차단이 해소되고 수락/병합한 뒤에만 actual merged main에서 amended workflow의 **action=preflight만** 실행해 runner 준비 receipt를 확인할 수 있다. 이후 별도의 명시적 지시로 owner가 `research_specs/kr-alpha-atlas-phase-c-v2-execution-authorization.json`에 exact amendment/effective/dependency hashes를 commit하고, 동일 owner가 main에서 amended workflow의 action=execute를 한 번 수동 dispatch한다. 현재 승인 파일·잠금·정식 결과·dispatch는 모두 없다. 이 작업에서는 승인 파일 예시도 실제 파일로 생성하지 않는다.
