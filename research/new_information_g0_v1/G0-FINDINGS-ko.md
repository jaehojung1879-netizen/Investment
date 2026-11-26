# G0 초기 실행 결과와 분기 판단 — 2026-11-25

> Evidence status: **OUTCOME_BLIND_SOURCE_FEASIBILITY, PARTIAL**. 깃허브 기존 원장 및 공식 개발문서를 읽었으나, 비밀키가 필요한 DART 원문 ZIP 실측은 실행하지 않았다. 이것은 수익 예측이나 확증의 결과가 아니다.

## 1. 한국 보유목적 변경(N1): 기술 경로는 확보, 원문 사건 검증은 미완

- **공식** OpenDART 목록 API: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019001 — 공시유형 D, 상세 D001; 수정/정정 포함 수집할 때 last_reprt_at=N.
- **공식** 요약 API: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS004&apiId=2019021 — 보유비율·보고사유만 있고 목적 전환 전/후는 없음.
- **공식** 원문 ZIP: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019003 — rcept_no로 원문 조회가 가능. 이전 원문과 비교하고 현재 신고자의 관계·정정·계약 변경을 구분해야 한다.
- 2020 보유목적 분류, 2022-08-17 서식 개정, 2026 해석 변경은 본문 키워드/신호 생성에 시계열 비정상성을 만든다.
- 존재 가능성을 보여 주는 *2차 사본의 미확인 사례*: 2025-01-09 아이에이의 보유목적 변경(단순투자→경영참가) 보고: https://samara.kr/disclosure/20250109000059. 원문 공식 URL https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20250109000059 은 별도 일치 확인 필요. 사례의 존재를 근거로 PIT 사건 수를 +1로 계산하지 않았다.
- 현재: schema source feasible; **independent confirmed transitions = NOT_MEASURED, verified original ZIP = 0**.
- 결론: SOURCE_ONLY, **G0 1순위**. 계약·형식과 테스트 준비됨. 실제 원본 품질과 밀도를 확인하기 전에는 Gate 1 통과 불가.

## 2. 반도체 가격·재고(N2): 원공표 관측 일부 있지만 수준값/연속성 부족

기존 #360 원장 research/industry_alpha_discovery_v1/data/iip-industry-yoy.csv 를 실제 재집계:
- SEMI(반도체) 행: 50건. 2013-03 1건, 2021-09~2026-09 사이 49건. 2014~2020 기록 0건이며 2021~2026도 월별 연속이 아니다.
- 50건 모두 productionYoy, shipmentYoy, inventoryYoy 값이 있다. 하지만 **세 열은 전년동월대비 증가율이지 생산·출하·재고의 지수 수준(level)이 아니다**. 단순히 inventoryYoy / shipmentYoy 를 재고/출하 비율로 부를 수 없다.
- #360 eligibility.json: 2013-02~2026-10 총 165개월 중 보도자료 archive 내부 최초 반도체 월별 수출액 데이터 134건, 모든 빈티지 포함 값을 확인한 월 162건. 수출액 개정 중앙 절대값 0.023%, 최대 1.513%. (이는 종전 #356의 2023~2026 소표본 최대 0.2%와 기간·표본이 달라 모순이 아니다.)
- #360 H3 재고 관련 가설은 사전 표본 관문 60개월을 만족하지 못하여 NOT_ESTIMABLE였다.
- 국가데이터처 산업활동동향 공식 원공표 채널: https://mods.go.kr/board.es?act=view&bid=216&list_no=447747&mid=a10301050100. 정확 게시일 자료의 존재는 확인. 원 공표된 품목별 수준/계절조정 개정 이력은 미확인.
- 한국은행 DRAM·Flash 수출물가 과거 최초 빈티지와 세부 관세청 수출 중량/품목구성이 신규 핵심. 공식 원천에서 직접 획득한 최초치가 없으면 역사 수익 검정 **금지**. 통관 중량당 단가는 spot/contract 가격과 다름.
- 결론: SOURCE_ONLY, **신규 데이터 확인 전 수익 실험 차단**. 기존 #360 H2 수출액 실험 재실행 금지.

## 3. 임원·주요주주 군집 매수(N3): 차별성 미입증

- D002 소유 보고 목록/API 경로는 공식 조회 가능: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS004&apiId=2019022
- #316에서 전체 254사 중 24사의 원문 표본(5,133건 파싱)을 점검했고 G2 밀도 판정 UNCERTAIN. #353 단일 공개 매수의 선택 효과는 ETF 경제성으로 연결되지 않았다.
- 복수 독립 인물의 동일 기업 매수라는 조건은 공시자 1명/특수관계자 중복/거래일 지연과 구별해야 한다. 실제 이 조건의 사건 수는 아직 없다.
- 결론: HOLD. 기존 정보 재포장 우려가 해소되지 않으면 REPACKAGED_STOP.

## 단계 완료 판단

| 단계 | 결과 |
|---|---|
| Research audit: 과거 결과·중복 검토 | DONE: #316/#319/#327/#353~#369와 대조 |
| G0 규정·공식 API·데이터 구조 확인 | DONE: URL, 법령구간, 3개 후보 구조 및 #360 원장 계측 |
| 안전한 DART 기술 probe 구현 | DONE: 수익/가격 모듈 없음, 5시대×D001/D002 최대 10회 목록 + 최대 12개 원문, 원문 해시·힌트만 기록. 테스트 합성 fixture |
| 실제 공식 DART 원문/목적 전환 확인 | BLOCKED: 인증키를 이 채팅의 GitHub 도구로 조회/실행할 수 없음; 원문 0건 |
| 신규 N2 가격·재고 최초 레벨 빈티지 | PARTIAL: #360의 50개 원공표 증가율만 확인, 수준·장기 원본·제품가격 미확인 |
| 독립 사건 밀도/MDE | NOT_ESTIMABLE_YET; 모집단 사건·수익 오차 규모 미확인 |
| Gate 1 후보 PASS_TO_PREREG | **0개**. 추후 공식 원문 확보 시 재판정 |
| Conditional prereg template | PREPARED_ONLY (N1, 승인/봉인 아님) |
| 역사 수익률 검정 및 실전 운용 | NOT_RUN / NOT_AUTHORIZED |

## 다음 기계적 실행
- Codex: 이 PR의 source_probe.py를 **격리된 키 접근 환경**에서 최초 기술 실행; 다섯 제도 구간 D001/D002 소표본 원문 ZIP이 정상 내려오는지 확인. 개인 이름/원문 내용·비밀키는 공개 repo에 기록하지 않음. 20개 이상 API 요청, 대량 수집, 성과 조회 금지.
- Claude: #360 IIP·수출물가·통관단가 데이터 중 **원본의 최초 시점 수준값**과 개정 계보를 확인. 이미 계산된 H1/H2 성과 읽지 않음.
- 이 첫 G0가 통과한 후보에만 다음 소표본 원문 대조·독립 사건 밀도·MDE 단계가 허용됨. 결과가 아닌 **데이터 출처와 적격성**이 다음 승인 기준이다.
