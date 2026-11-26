# S3 인수인계 · 연구 경계와 기존 증거 대조

2026-11-27 KST · Investment S3 · 담당 Codex

## 운영 계보와 전달

[#292 통합 원장](https://github.com/jaehojung1879-netizen/Investment/issues/292)에서 본 세션 기준 main `3150c70017432e3b73321fbda47ebea226bf8d2b` 및 [2026-11-27 #382 최신 인수인계](https://github.com/jaehojung1879-netizen/Investment/issues/292#issuecomment-7193162686)를 확인했다. [#380 병합·#381 승인 대기](https://github.com/jaehojung1879-netizen/Investment/issues/292#issuecomment-7187470889) 상태는 해당 코멘트 기준이다. #383의 최신 확인 헤드는 `ab8d420bdf4d3b35a8f4840eb07f5dc28b6ae458`다. S3는 독립 디렉터리의 추가 파일만 사용한다.

이전 약속은 원천 부족과 추출의 일반화 실패를 반복하지 않고 경제적 판단의 증분을 실제 원문에서 확인하는 것이었다. 이번에 검증된 변화는 연간 공시 쌍 0→6, 기존 EX-99 지원 원문 0→5, 독립적으로 채점할 수 있는 경제 예측 목표 0→1이다. 6개 발행인은 신규 홀드아웃 발행인이 아니다. 새로 얻은 경제적 판독은 공시 정의상 종속된 2개 수치가 하나의 물리 관측이라는 점, 연결 실적과 개별 중간변수 방향이 달라질 수 있다는 점이다. 판정은 `KEEP / SOURCE_ONLY`, 독립 성능에 대해서는 `INCONCLUSIVE`다. 최소 다음 작업 담당은 S3이며, 별도 표본 관리자와 고정된 허용 원천에서 근거 분리·결합 조건의 독립 라벨링을 확인한다. 병합 총괄 및 기존 운영 책임에는 위임 관계를 추가하지 않았다.

DART 기존 경로의 실행 증거는 [main fundamentals run 45826049165](https://github.com/jaehojung1879-netizen/Investment/actions/runs/45826049165)와 #292의 실제 출력을 확인했다. #292에 적힌 2026년 3분기 DART raw/canonical 241/241은 등록 재무 수치 수집의 증거다. 해당 원장·[워크플로](https://github.com/jaehojung1879-netizen/Investment/blob/3150c70017432e3b73321fbda47ebea226bf8d2b/.github/workflows/fundamentals.yml)는 S3의 삼성전자 FY2023·FY2024 사업보고서 본문 PDF 바이트를 새로 내보내는 경로가 아니다. 그 차이를 본문 접근 제한과 분리했다. 횟수 확대·별도 실행을 요청하지 않았다.

공통 Evidence Registry용 항목은 `S3-INTELLIGENCE-1 / US+KR+EIA / SOURCE_ONLY / OUTCOME_EXPOSED_DEVELOPMENT / G1 source verification only / G2 target n=1 / PASS_TO_PREREG 0`이다. 근거는 [보고서](REPORT-ko.md), [원천](SOURCE-MANIFEST.json), [비교](COMPARISON.json)다. 공통 레지스트리 삽입은 통합 담당자와 조율할 변경으로 남긴다.

## 기존 연구 전수 대조

[Evidence Registry 고정본](https://github.com/jaehojung1879-netizen/Investment/blob/3150c70017432e3b73321fbda47ebea226bf8d2b/research/next_alpha_program_v1/EVIDENCE-MAP-ko.md)과 각 PR의 본문을 읽었다. 아래 수치·상태는 기존 보고의 판독이며, 이번 작업의 새 역사 실행은 없다.

| 범위 | 기존 연구의 증거와 S3 적용 |
| --- | --- |
| [#150](https://github.com/jaehojung1879-netizen/Investment/pull/150), [#151](https://github.com/jaehojung1879-netizen/Investment/pull/151) | #150 자료 인벤토리와 #151 증빙·실행 상태 정정. 최초 원천·실행 증거를 확인한다. S3는 정보 가용성 목록을 넘어 관측된 경제 정의의 충돌과 연결을 검토한다. |
| [#206](https://github.com/jaehojung1879-netizen/Investment/pull/206), [#212](https://github.com/jaehojung1879-netizen/Investment/pull/212) | #206 모델 선택 토너먼트와 #212 KR Atlas PIT 매트릭스. S3는 해당 역사 후보를 다시 조합하지 않고 새로운 사건표현의 원천 자격을 검사한다. |
| [#343](https://github.com/jaehojung1879-netizen/Investment/pull/343)–[#346](https://github.com/jaehojung1879-netizen/Investment/pull/346) | #343 선택 가치·메커니즘, #344 별도 미국 Top-K 자료 감사, #345 무작위 대조·미국 이탈, #346 원형 S2·ETF 대조. 시총·생존편향 및 주도주를 가격 검정에서 통제할 필요가 있다. #344는 통합 계보 밖이다. |
| [#347](https://github.com/jaehojung1879-netizen/Investment/pull/347)–[#353](https://github.com/jaehojung1879-netizen/Investment/pull/353) | #347 액티브 펀드 공시, #348 공시 시각·업종/시총, #349 단일 슬롯, #350 한미 일괄과 CTVA 보정, #351 노출 유지, #352 SPY 복제 및 필터, #353 발행주식·공개매수. 투자 경제성에 쓰이는 종목 선택·주도주·시장 노출·리밸런싱을 이미 나눴다. S3 입력 문서의 원천과 최초 공개성은 새로운 측정이고, 해당 역사 성과에는 결합하지 않았다. |
| [#354](https://github.com/jaehojung1879-netizen/Investment/pull/354) | 시점별 추정치 수정·확산은 라이선스와 빈티지 부재로 차단. SUE와 실제 컨센서스 서프라이즈는 구별한다. ADT 원천 감사에서 2023-07-10 손상/정정이 2023-08-08 정상 Q2 8-K보다 29일 앞서 채택된 반례가 있다. US ANNOUNCE/E_H3의 발표 비교와 그 계보는 격리한다. S3의 10-K 비교와 기존 EX-99를 단순 결산일 이후 첫 2.02 규칙으로 잇지 않는다. |
| [#355](https://github.com/jaehojung1879-netizen/Investment/pull/355) | 산업 CAPEX와 매수 대기·축소 의사결정, S2 미래 발표 여부 누설 및 S3 v1 대조금액 오류 정정. US S2는 #354 격리 대상이다. S3의 설비·생산량 정의 대조는 그 성과와 별개다. |
| [#356](https://github.com/jaehojung1879-netizen/Investment/pull/356)–[#360](https://github.com/jaehojung1879-netizen/Investment/pull/360) | #356 연구 우선순위와 반도체 설계, #357 MVMA 설계, #358 최초 역사 판독, #359 보존 감사, #360 산업 최초 공표. EIA의 원공표·빈티지 분리를 #360과 같은 원칙으로 재현하되 기존 산업 알파나 밸류에이션 성과를 다시 계산하지 않았다. |
| [#361](https://github.com/jaehojung1879-netizen/Investment/pull/361)–[#367](https://github.com/jaehojung1879-netizen/Investment/pull/367) | #361 시장 충격 취약성·전달, #362~#363 위험발생 정의·원천, #364 보존형 원샷 수정, #365~#366 독립 감사·등록, #367 1회 실행에서 기저율/M1 초과 지지 없음. S3는 정보 해석의 비용과 구체 경제 변수에 한정한다. 시장 상태·위험은 가격 지연의 대안이다. |
| [#368](https://github.com/jaehojung1879-netizen/Investment/pull/368)–[#369](https://github.com/jaehojung1879-netizen/Investment/pull/369) | 충격 서술, Atlas 국면 의존성 및 시점 검산. S3의 6개 사례도 설명·정의 실측이며 시그널 추정에 쓰지 않는다. |
| [#372](https://github.com/jaehojung1879-netizen/Investment/pull/372) | 시스코·UPS 5개 EX-99에서 같은 발행인, 기간, 지표, basis, 단위를 키로 한 경영진 자체 가이던스 파일럿. 원문 사후 해시·실시간 영수증 범위가 제한됐다. S3는 같은 종류를 다시 자동 연결하지 않는다. |
| [#375](https://github.com/jaehojung1879-netizen/Investment/pull/375) | SEC Item 4.02의 회계 신뢰성과 수정·중복·범위. S3에서 보통 Item 9 응답은 음성 통제다. 4.02를 예측 신호로 복제하지 않는다. 공시의 정확한 형태와 정정은 각각 유지한다. |
| [#383 소스 감사](https://github.com/jaehojung1879-netizen/Investment/blob/ab8d420bdf4d3b35a8f4840eb07f5dc28b6ae458/research/next_alpha_source_admission_v1/GUIDANCE-SOURCE-AUDIT-ko.md) | 구 gold 64구간 재회수와 원 HTTP 해시 일치 0건. Test2 기존 주석에서 DOM P/R 83.6/40.4%, 자동 선별 81.7/43.0%. 별도 보류 12문서(3개 기업군)에서 v2 P/R 31.7/48.8%, DOM과 자동 선별의 정확 일치 0. 원 주석 scope에도 중간값 중복, 비동일 유기성장 지표 등 결함이 존재했다. 장부 388링크는 178개 공시였고 반도체 230링크는 98공시/10 CIK로 줄었다. 37개 잔여 기업군과 새로운 프롬프트는 접촉시키지 않았다. |

S3은 #383이 보존한 dev manifest, gold, 원문 복구 영수증 및 고정 회수 도구의 구간 식별과 v1 검출기를 그대로 사용했다. #383이 우선한 #354 accession catalog에서 S3 EX-99 5/5 접근번호를 대조했다. 카탈로그 `us-8k-item202.csv.gz` SHA-256은 `4fa79370feec010ab340b2ad9087bad0e32a691f67ddf9aac27dee2849f0ce09`다. #383의 최신 submissions manifest 1,869 페이지는 별도 감사 계보이며 이 파일럿에서 전수 수집을 다시 수행하지 않았다. [#354 접근번호 카탈로그](https://github.com/jaehojung1879-netizen/Investment/blob/a45f12760a3d27ad09fcfdfb1266308ae59b9e1d/research/kr_us_earnings_expectations_v1/inputs/us-8k-item202.csv.gz) · [#383 회수 기록](https://github.com/jaehojung1879-netizen/Investment/blob/ab8d420bdf4d3b35a8f4840eb07f5dc28b6ae458/research/next_alpha_source_admission_v1/results/guidance-legacy-gold-source-recovery.json)

## S1·S2·S4 인터페이스

S3 표준 사건의 최소 계약은 [JSON Schema](EVENT.schema.json)와 [예시 원장](ECONOMIC-EVENTS.jsonl)이다. `entityId`는 법적 SEC CIK·DART 회사코드, `sourceId`는 이번 원천 매니페스트 키다. 양쪽은 기존 [공통 연구 계약](https://github.com/jaehojung1879-netizen/Investment/blob/3150c70017432e3b73321fbda47ebea226bf8d2b/docs/research-program/04-common-research-contract-ko.md)의 사건 시점·가용일·정정·결측 규칙을 따라야 한다. `publishedAt`의 정밀도와 실증 가용성을 확인한 시각, 관측 시각을 명시한다. 제품·업체·시설 교차표와 공급망 엣지의 소유는 S1에 둔다. `sourceEvidence`는 재현 위치, `mechanism`은 해석, `outcome`은 별도 독립 해소다.

| 전달 | 최소 입력·키 | 검증 가능한 관계 |
| --- | --- | --- |
| S1 실물 네트워크 | `entityId, economicVariable, period, unit, release vintage, edge provenance`와 S1의 제품/시설/고객 키 | `wafer starts × good bits/wafer → package bit output`과 공시 항등식 `package output / time utilization = published capacity`를 구분한다. 범위가 맞는 S1 수요·재고·대체 가능성의 구간을 DCF 성장과 마진 조건에 연결한다. |
| S2 자본 제약 | `entityId, securityId as of release, public window, source novelty, the same economic event ID`와 S2의 구분된 기관 흐름·거래 제약 | 조달 충격이 미래 실물 변수에 남는 패턴과 기관 수급의 가격 역전 패턴을 분리한다. 정보 복잡성×예상 매도 압력의 상호작용은 가설이다. S2 요인과 시장 근접 거래만으로 인과 학습을 하지 않는다. |
| S4 수학적 구조 | 서로 다른 분모·단위·시점을 보존한 노드, 엣지 유형 `identity / reported association / hypothesized cause`, 검열 범위 및 공통 근거 ID | `NIM ≈ asset yield − funding cost`의 자산·부채 가중치 보정, 잔존기간별 라이선스·로열티 노출, 사용량 변화와 범주검열 NRR, 비용·초기의 반응률과 감쇠 속도, 가격 내재 성장–마진–재투자 등가치 표면. 같은 공시에 파생된 두 지표의 종속성을 모형에 명시한다. |

역산 입력 인터페이스는 `asOf, entityId, baseRevenue, EV range, tax range, r range, terminal growth/ROIC range, incremental capital needs, physical volume/price/mix intervals, provenance`다. S1의 실물 전망 구간을 외부 제약으로 받고 각 시나리오에서 가능한 가정 조합을 남긴다. S2의 수급 제약은 가격의 단기 비정보성 괴리를 설명하는 별도 후보이며 할인율·미래 물량 관측값으로 대체하지 않는다. S4에 인과 모형을 넘길 때 동일 공시의 파생 사실과 독립적인 확인을 구별한다.

## 검증 실행과 재현

`python research/market_structure_discovery_s3/verify.py`는 JSON Schema, 원천 참조, 누락 상태, 예측 점수 산술을 읽는다. `--raw-dir`에 매니페스트의 sourceId 이름으로 저장한 당회 원문을 제공하면 해시·크기, PDF/HTML 앵커 47개, accession에 붙은 Companyfacts 값 10개를 대조한다. 기본 의존성은 `jsonschema`이며 원문 모드에는 `lxml`과 `pdftotext`도 쓴다. 원문을 다시 수집하면 `observedAt`과 해시가 바뀔 수 있다. 이전 영수증을 덮어쓰거나 해시 불일치를 무시하지 않는다. EX-99는 고정한 [#383 원천 회수기](https://github.com/jaehojung1879-netizen/Investment/blob/ab8d420bdf4d3b35a8f4840eb07f5dc28b6ae458/research/next_alpha_source_admission_v1/tools/guidance_source_recovery.py)로 동일 구간을 고르고 [기존 검출기](https://github.com/jaehojung1879-netizen/Investment/blob/ab8d420bdf4d3b35a8f4840eb07f5dc28b6ae458/research/next_alpha_source_admission_v1/tools/guidance_detect.py)의 문서 플래그를 기존 dev gold의 `CURRENT` 유무와 대조한다. 미주석 USB는 gold 음성으로 사용하지 않는다.
