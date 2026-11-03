# Cross-market research foundation v1

**입력 기반 구현 완료 / 새 실제 경제성 실증은 SOURCE_BLOCKED.** 연구 outcome·C2 귀속·P0~P5 역사 성과는 실행하지 않았다. 기존 봉인, 등록, 보호 해시, 실패 판정, 실행 잠금과 운영 파일을 변경하지 않았다.

기준 main은 `37f8cbf6b1c066f6b3c65235953648d17ebf2f69`, 재사용 #316은 `86c5983ffba643a58d9eba84a05dc60f4d8e9e6a`다. [전체 PR HEAD·CI 스냅샷](evidence/repository-snapshot.json)과 [고정 원천 SHA/blob/SHA-256](evidence/source-pins.json)을 제공한다. #287/#290/#309/#311은 닫힌 PR이어도 고정 Git 근거를 읽었으며, 코드나 결과를 새 브랜치에 병합·복제하지 않았다.

## A. Cross-market source report

| 영역 | 실제 확인·복구 | 여전히 해결되지 않은 문제 |
|---|---|---|
| US 기존 가격/benchmark/actions | 189개월 × 3종류 = 567개 객체, 압축 128,694,533B. 고정 source commit → tree/path → blob → 실제 압축 SHA 및 해제 logical SHA 모두 결속 | 이 수는 US 종목 수가 아니다. 증권 신원·주식 클래스·원가격 기준·수집권리를 자동 인증하지 않음 |
| US 회계·공시 | 고정 Finnhub 17 shard, 40,220,964B 실제 확보·검증. 공시 1건의 값 없는 metadata 투영 및 날짜/CIK 입력 builder | 보관·연구 재사용 허용 근거, 원 공시 대조, 가격 증권과의 historical share-class 연결 미확보 |
| US departed 212 | 212개 audit identifier를 종목별 다중 gate로 재분류. 기존 후보 FULL5/PARTIAL170/NONE37, 후보 186,910 sessions와 잔여69,492의 합계 재검증 | 후보 raw/panel은 현재 보유하지 않음. 212가 모두 실제 상장폐지라는 뜻이 아니며 admitted sessions는 계속0 |
| KR 산업 | 보존 KIND listing·viewer·body를 결속한80공지/62증권의 공개 이후 AFTER-label 입력 | 전체 과거 분류·분류판·종료22·최소 산업 구성원 수 실패 유지. last-public 관측 투영10,093/73,200=13.788%는 PIT_EXACT 적격률이 아님 |
| US 산업 | SEC 과거 10-K header952B 실제 HTTP200 확보. CIK/SIC/접수시각/filing-date와 URL 식별을 검증 | 단일 issuer 사실이다. historical SIC panel, 시점별 CIK→증권→share-class 링크, GICS 권리·원천은 없음 |
| KR ETF | 기존 main의 공식 종가/NAV5,918행(2002-10-14~2026-10-07), NAV 결측·중복0. 공식 배당JSON/XLS20건 gross금액 대조PASS | 당시 공개 vintage, 전체 investor shareholder TR, 과거 ETF 구성·산업 비중·실제 체결은 별도 미확보 |
| KRW 현금 | KOFR 공식 정의·공시 시작 및 잠정역사 공개 시점 확인. CD91/KOFR/BOK quote 파서와 실제 투자 payoff 계약 분리 | 실제 투자 가능한2013~2026 현금 경로 복구0. CD91 quotation·KOFR benchmark·BOK 정책금리를 투자자가 얻은 수익으로 대체 불가 |

상세 근거: [US](reports/US-SOURCES-ko.md), [산업](reports/INDUSTRY-ko.md), [현금·배당·ETF](reports/ECONOMIC-SOURCES-ko.md). 기존 #316의 NAV series `ABSENT`는 보존된 실제 NAV 바이트 확인으로 정정해야 한다. 반면 #316의 ETF PDF는 **portfolio deposit file**을 뜻하며 `.pdf` 확장자의 분배금 문서와 다르다. 분배금 PDF 존재는 #316도 이미 인정했고, 과거 ETF 구성/PDF 공백은 유지한다. 원 #316 파일은 그대로 보존했다. SEC403도 당시 endpoint/요청의 실패 기록이며 현재 전역 접근 차단으로 반복하지 않는다.

## B. Implemented data foundation

- [us_sources.py](us_sources.py): 기존 recovery/admission 파서 재사용,212개 cohort 보존, Git/tree/실제 payload 검증, 공시 metadata PIT 입력, USD와 KRW/FX 혼용 거부. 원자료 없는 후보를 가격 확보로 승격하지 않는다.
- [industry.py](industry.py): 기존 `industry_foundation` 및 KIND 파서 재사용. 공개/효력일 분리, 현재 anchor 소급 거부, 고정 원문 변형 거부, 투자 가능 유효기간·종료 검사, 산업 구성·HHI·최대구성원 제거, 합성 귀속의 중복 집계 차단.
- [economics.py](economics.py): 기존 ECOS/공식 ETF/배당 reconciliation 재사용. quote와 투자 payoff 분리, 일별 현금의 주말 포함 연속 grid, 배당 record/payment/ex-date 구분, unmatched 이벤트·조정가격 이중배당·미증명 terminal 차단.
- [comparison.py](comparison.py): 기존 hierarchy §7 제안을 실행 권한 없이 코드 계약으로 구체화. 기존 receipt digest 및 지역 거래일 달력 재사용. Portfolio D 운영 영수증은 읽기 전용으로 연결한다.
- [provenance.py](provenance.py) / [audit.py](audit.py): 원천 바이트·보존 evidence·준비도 표의 오프라인 검증. `CONSISTENT`는 패킷 무결성 판정이며 실증 적격성/승인/CI 우회가 아니다.

데이터 수백 개를 재커밋하지 않았다. 새 SEC 소표본·공시 metadata 외에는 기존 Git 경로, 해시, 작은 감사 JSON만 추가했다. xlrd2.0.1은 기존 XLS 독립 확인용 `/tmp`에만 설치했으며 저장소 의존성은 추가하지 않았다.

## C. Industry research readiness

KR/US 전체 산업 선정 실증은 둘 다 **SOURCE_BLOCKED**다. KR 복구는 공개된 분류 진술의 보존·이용 가능성을 개선하며, 기존 v4 `DATA_FOUNDATION_INSUFFICIENT_V4`를 변경하지 않는다. #290에 이미 있는 종료종목 후보4/22·원천 검증1/22·최종 적격0/22와 조건부 승인 경로도 재구현하지 않았다.

US SIC는 SEC 신고 산업 분류이며 GICS와 다르다. 한 filing에서 보고된 SIC를 실제 산업 변경일이나 과거 전체 기간의 분류로 역대입하지 않는다. 경제적 종료·분류 변경·share-class·taxonomy edition을 연결하는 원천은 추가로 필요하다.

## D. Economic evaluation interface

[정확한 계약과 제한](reports/COMPARISON-ko.md): P0 ETF100%, P1 직접 종목, P2 신호일 시총 산업 바스켓, P3 산업→종목, P4 ETF 산업 중립, P5 고정 점수 결합을 검사한다. 공통 universe·signal/publication·통화·총수익·calendar·risk/cost/execution 해시와 대칭적인 결측 처리를 요구한다. 시장 위험 배수는1로 고정한다.

합성 계산은 공통 STOCK/ETF×BUY/SELL 요율로 자기금융 진입과 만기 전량 청산의 실제 notional 비용을 산출한다. 경로별 임의 비용 입력, NET 이중 차감, 미래 값, 서로 다른 ETF 시작일, 무근거 종결값, 일부 모델에만 유리한 결측 삭제를 거부한다. H126/H252는 지역 세션 및 관측 가용성을 검사하며 미성숙 시 성과는null이다.

실제 역사 evaluator/가격 fetch/모델 선택기/운영 writer는 없다. 합성 숫자는 계산식 회귀이며 경제적 성과 증거가 아니다. 중간 리밸런싱·실제 체결·슬리피지·FX·현금 경로 평가·가설 등록/통계 검정은 지원 범위 밖이다.

## E. Empirical readiness matrix

| 지역 | Market | Industry | Stock | Portfolio |
|---|---|---|---|---|
| KR | PARTIAL | SOURCE_BLOCKED | PARTIAL | SOURCE_BLOCKED |
| US | PARTIAL | SOURCE_BLOCKED | SOURCE_BLOCKED | SOURCE_BLOCKED |

PARTIAL은 기존 context/metadata와 소스 확인을 할 수 있다는 뜻이다. 새 outcome 실행 준비 완료를 뜻하지 않는다. [기계 판독 matrix](evidence/readiness-matrix.json)는 각 cell의 범위·실제 구현·실패 코드·근거·해결 조건·우선순위를 제공한다. US 세부6개 연구 상태는 [별도 표](evidence/us-readiness.json)에 있다. 권리가 없는 회계 입력은 RIGHTS_BLOCKED로 구분한다. 검정력을 측정하지 않은 표본은 UNDERPOWERED로 확정하지 않았다.

경제적 영향과 해소 가능성 기준 우선순위는 US 기존 private 후보의 원본·권리·신원 확인 → 투자 가능한 KRW 현금/공통 shareholder TR → KR 종료·PIT 분류/US SIC-security panel → 실제 ETF 구성 및 전향 기록이다. 더 많은 무신원 CSV, 생존종목 제한, BOK 현금 대체, 현재 GICS 소급은 해결책이 아니다.

## F–G. 실행 인계와 독립 감사

[Claude handoff](reports/CLAUDE-HANDOFF-ko.md)에 다음 실행 우선순위·Owner 결정·재현 명령을, [독립 감사 packet](reports/INDEPENDENT-AUDIT-ko.md)에 검증 범위·수정한 결함·잔여 위험을 기록했다. 최신 정확 HEAD 및 CI는 통합 PR과 최종 전달 메시지에서 확인한다. 코드·evidence 내용 자체는 [해시 영수증](evidence/evidence-receipts.json)으로 검증한다.

```bash
python -m research.cross_market_foundation_v1.audit
python -m research.cross_market_foundation_v1.audit --source-bytes
python -m pytest -q tests/test_cross_market_*.py
ruff check .
python -m compileall -q pipeline research/cross_market_foundation_v1
python -m pytest -q
```

`--source-bytes`는 고정 원천 Git 객체가 로컬에 있어야 한다. 검사 중 숨은 fetch/checkout/원천 갱신/결과 실행은 하지 않는다. 원천 재생성은 US/산업 보고서의 명령으로 `/tmp`에 출력해 비교한다. 원자료 파일을 읽는 검증과 새 역사 수익률 계산은 구분한다.
