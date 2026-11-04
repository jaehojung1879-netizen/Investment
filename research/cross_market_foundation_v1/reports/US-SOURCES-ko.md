# 미국 원천 복구·연구 적격성 감사

새 수익률·라벨·모델·포트폴리오 outcome을 실행하지 않았다. 기존 결과를 바꾸지 않고, 실제 보유 바이트와 원천 경로를 결속하고 종목별 차단 조건을 분리했다. **이번 작업이 해소한 것은 기존 원천의 재현 가능한 접근·검증 경로이며, 212개 식별자의 연구 적격 가격 경로를 복구했다고 주장하지 않는다.**

## 고정 원천과 실제 확인 범위

| 원천 | 정확한 고정 커밋 | 실제 확인 |
|---|---|---|
| main의 생존편향·departed recovery/admission·권리 감사·멤버십 | `37f8cbf6b1c066f6b3c65235953648d17ebf2f69` | Git tree → path → blob → 실제 SHA-256 |
| #316 원천 inventory | `86c5983ffba643a58d9eba84a05dc60f4d8e9e6a` | `c2-source-inventory.json`을 읽기 전용 재사용 |
| #287 WID source gates·filing 오류·권리 | `9a10baef600078c132b6942e83f72b587cf0c581` | blocker-review-v3 metadata/source-funnel을 읽기 전용 재사용 |
| replay-v16 원천 | `1bf68f59cffa20239977e2cfaa0f35a07d0ec884` | `ledger/historical/replay-v16/inputs.json`, blob `76556e948fd89786d846a6275a0bc55f4bb56658`, 204,071B, SHA `d60ff99710baaf1417cb23d0b007e2d11766e7d76eb03c0d877e0d2495a929cd` |
| Finnhub 원천 | `704d7db6d5b00def771aba5d2665d0846d6bc776` | `ledger/fundamentals/us/finnhub-2011..2027.jsonl.gz` 17 shards, 40,220,964B; 각 path/blob/SHA는 inventory 참조 |

[실제 원천 inventory](../evidence/us-source-inventory.json)는 **price 189 + benchmark 189 + corporate-events 189 = 567 objects**, 압축 합계 **128,694,533B**의 Git tree 경로·blob·압축 SHA-256·해제 후 logical SHA-256을 모두 확인했다. logical SHA는 고정 inputs manifest의 content-address와 같다. 가격값을 이용한 수익 계산·특징·라벨 구성은 하지 않았다. 월별 objects에는 복수 지역이 포함될 수 있으므로 이 수를 미국 종목 수나 567개 미국 가격 패널이라고 부르지 않는다.

처음에는 source commit/tree가 클론에 없어 blob 보유와 원천 경로 결속을 확인할 수 없었다. 세 개의 정확한 기존 커밋만 `--filter=blob:none`으로 읽어 path 결속을 복구했고, 일부 미보유 Finnhub shard는 그 고정 tree에서만 읽었다. 전체 ledger checkout, 봉인 연구 재실행, 삭제·비공개 보류된 departed 가격 dangling object 복구는 하지 않았다. 이는 upstream 원천 부재와 클론 미확보를 구분한 실제 복구다.

주가·ETF 공개 benchmark와 Finnhub 바이트 보유는 원거래 가격·배당 완결성·증권 신원·보존/재사용 권리를 인증하지 않는다. Finnhub의 2027 파일명도 2027 정보가 현재 사용 가능하다는 증명이 아니다. 실제 사용일에는 개별 공시의 두 날짜·회계연도·당시 CIK를 다시 검사해야 한다.

## 212개의 정확한 의미와 종목별 분류

[전체 212개 행](../evidence/us-departed-212.json)은 원본 recovery와 admission 감사의 auditIdentifier/securityId를 일대일 결합한다. 현재 permanent security ID가 확보된 212개 증권, 212개 기업, 212개 실제 상장폐지라는 뜻이 아니다.

| 기준 | 기존 고정 증거의 수치 | 이번 확인 |
|---|---:|---|
| audit identifier | 212 | 중복·누락 없이 두 감사 파일의 cohort·securityId 결합 |
| 기존 identity category | 미해결 departed 181, ticker reuse 29, same-security rename 1, acquired/merged terminated 1 | 원본 category 보존; 새 이벤트 분류 추정 없음 |
| 후보 가격 CSV / 후보 identifier | 409 CSV / 175 identifier | 출처 중복과 식별자 수 구분; 원자료 재획득 수가 아님 |
| 후보 커버리지 | FULL 5 / PARTIAL 170 / NONE 37 | 메타데이터상의 당시 coverage이며 admission과 분리 |
| 원래 결측 / 후보 복구 / 후보 잔여 | 256,402 / 186,910 / 69,492 sessions | 행별 `covered + missing = expected` 및 전체 합계 재검증 |
| 보류 identity / 기업행동 미해결 / terminal triage 미해결 | 8 / 212 / 212 | 모든 독립 실패를 남김; 첫 실패 뒤 문제를 숨기지 않음 |
| admitted sessions | 0 | 기존 봉인 결과와 admission 변경 없음 |

각 행은 당시 issuer name/CIK(과거로 역대입하지 않음), membership interval의 관측 경계, identity hold와 symbol reuse, 후보 출처·고정 publisher, 관측 결측, 원주식 기준·corporate actions, terminal consideration, filing-to-price 링크, 권리·영구보관 상태를 별도로 보존한다. 일별 ticker 일치나 CIK 일치는 price issuer/share-class 증명이 아니다.

**terminal 미해결**은 평가 보유기간에 실제 경제적 종료가 발생할 때 필요한 대가·교환·분배의 근거가 검증되지 않았다는 뜻이다. 모든 S&P 이탈이 상장폐지·현금청산이라는 주장이 아니다. 이탈 후 거래 지속, rename, 다른 issuer의 ticker 재사용은 따로 확인해야 한다. 확인되지 않은 마지막 거래가·0원·후속 종목 가격으로 메우지 않는다.

과거 비공개 후보 원자료는 현재 checkout에 없다. raw archive는 21,264,444B, SHA `0fa0b576d04693cda88611b3ec19d2415d868c1af2189f0e29944f2d7ae835f4`, observations는 6,834,898B, SHA `41ef2da7e8bc6ee7a07ec58635e08a25452c7228cfb33d269a22e266f0b7aa59`이다. manifest·해시·외부 파일명만으로 payload 이용 가능성을 주장하지 않는다. 다른 소유자 저장소에 사본이 없는지까지 확인한 것은 아니다. 재현하려면 소유자가 정당한 권리와 영구 비공개 보관을 확인한 사본을 별도로 제공해야 한다.

## 실제 새로 연결한 원천과 코드

- [`us_sources.py`](../us_sources.py): 고정 Git source receipt, byte/logical hash 검증, 212개 독립 gate 분류, 기존 `parse_csv`를 이용한 관측 날짜 입력 어댑터, 공시 metadata 입력 어댑터, USD/KRW 비교 통화 gate. HTTP 수집기·outcome runner가 없다.
- [실제 공시 metadata 소표본](../evidence/us-filing-metadata-sample.json): 고정 Finnhub 2013 shard의 `A|0001090872-13-000005`를 날짜/CIK 등 9필드로만 투영했다. 원본 shard blob/SHA와 원본 JSONL 행 SHA를 기록했다. 원문 재무 수치·가격은 포함하지 않는다. `availableFrom=2013-03-06`, `acceptedDate=2013-03-05 20:37:31`이므로 2013-03-06에는 보류하고 다음 거래일부터 metadata만 가시화한다.
- [SEC 실제 header](../evidence/industry-sec-aapl-2023-header.sgml): 산업 작업에서 952B를 실제 복구했다. [probe receipt](../evidence/industry-sec-probe.json)의 HTTP200·hash와 CIK/SIC/acceptance/filing date를 구분한다. 과거 SEC403은 endpoint/time-specific 기록이다. 한 header의 성공으로 전체 SIC/공시/소유거래 패널 확보를 선언하지 않는다.

공시 adapter는 publication과 acceptance의 전체 timestamp를 검사하고 **원표기일과 New York 날짜 중 늦은 날 전체까지 보류**한다. 기존 `pipeline.replay_calendar`의 US/XNYS 거래일로 제공된 session 전체를 검증하여 주말·휴장일을 거부하고, 단축 거래일은 허용한다. 결측/0/16자리 CIK, 잘못된 시각, fiscalYear 1215 같은 미증명 회계연도, 중복 filing ID를 안전하게 거부한다. `PIT_METADATA_ONLY`를 반환해도 주가 증권 신원이나 outcome admission은 false다. 현재 ticker/CIK를 과거로 확장하는 기능은 없다.

#287이 이미 수정한 WID 실행기를 복제하거나 수정하지 않았다. 그 연구의 권리·price issuer/share-class·return basis 3개 차단은 유지한다. 고정된 127개 월별 action component의 SPY 이벤트 0건이라는 #287 발견을 재사용하며, 이 표본의 범위를 189개 전체로 확대해서 주장하지 않는다. 공개 dual-benchmark가 별도 존재한다는 사실도 기존 replay stock/ETF가 같은 원거래·분배 기준이라는 증명이 아니다.

미국 경제 비교는 **USD 주식 총수익과 USD SPY 총수익**을 기본으로 한다. KRW 투자자 비교는 같은 native USD 기준에 별도 KRW_PER_USD FX 원천·관측일·가용일을 붙여야 하며, implicit FX 포함과 USD/원화 benchmark 혼용을 입력 단계에서 거부한다. FX 관측일 ≤ 보수적 공개일 < 신호일의 인과 순서를 강제하여 관측 전 공개·같은 날 공개를 허용하지 않는다. FX 수익을 주식 초과수익으로 부르지 않는다. 실제 환율·배당·종료·비용 적격성 검사는 공통 경제성 계약이 별도로 수행한다.

## 연구 준비도와 가장 가치 있는 다음 작업

[기계 판독 준비도](../evidence/us-readiness.json)의 PARTIAL은 입력 기반을 일부 구현할 수 있다는 뜻이며, outcome 실행 준비 완료나 승인이라는 뜻이 아니다.

| 연구 | 판정 | 실제 가능한 작업 / 남은 핵심 차단 |
|---|---|---|
| Market risk / exposure | PARTIAL | 기존 benchmark byte 재현·계약 가능; 공통 총수익 basis·권리·새 실행 승인 필요 |
| Industry selection | PARTIAL | SEC header 1건·issuer SIC parser 가능; dated 전체 SIC panel·security/share-class 링크 없음 |
| Direct stock selection | SOURCE_BLOCKED | 212개 종목별 실패 triage 완료; 검증된 native 가격/권리/기업행동/종료 입력 없음 |
| Earnings / fundamental changes | RIGHTS_BLOCKED | 기존 17 shard와 두 날짜 metadata adapter 확보; Finnhub 재사용 권리 및 price/share-class·총수익 gate 미충족 |
| Ownership / insider Form 4 | SOURCE_BLOCKED | 공시 접근 가능성은 일부 확인; 전체 retained 거래 패널·정정·코드·거래일/공시일 구분·검정력 미확보 |
| Portfolio D comparison | PARTIAL | 별도 운영 소유권을 유지하며 읽기 전용 입력/통화 계약 가능; 공통 분배·비용·만기 관측 필요 |

권리 차단과 물리적 source 차단을 동시에 보존했으며, source 존재만으로 READY를 부여하지 않았다. 적격 cohort가 없으므로 통계적 검정력은 아직 평가하지 않았다. 측정 없이 UNDERPOWERED를 확정하지 않는다.

우선순위는 (1) 기존 private 후보의 합법적 보존·재사용 확인, (2) D/F 후보 59개 identifier의 과거 issuer/share-class·원거래/분배 lineage 검증, (3) 실제 종료가 걸리는 기간의 종결대가 원문 연결, (4) 날짜별 SIC panel과 source-class mapping 확대다. 더 많은 무신원 ticker CSV나 생존자 제한은 해결책이 아니다. 실제 source가 부족하면 SOURCE_BLOCKED를 유지하고 metadata/parser 합성 검증을 계속한다. 비용·권리·대량 수집·outcome 실행은 별도 Owner 결정이다.

## 재현과 독립 검증

저장소의 기존 Python 환경을 사용한다. source commit이 없는 clean clone에서는 우선 세 고정 커밋을 blob 없이 fetch하고, 필요한 경로만 읽어야 한다. generator는 네트워크나 implicit lazy fetch를 사용하지 않으며 부재를 조용히 성공으로 바꾸지 않는다.

```bash
python -m research.cross_market_foundation_v1.us_sources --repo . --output /tmp/us-foundation-reproduction
python -m pytest -q tests/test_cross_market_us_sources.py tests/test_us_departed_price_recovery.py tests/test_us_departed_dataset_admission.py
ruff check research/cross_market_foundation_v1/us_sources.py tests/test_cross_market_us_sources.py
```

현재 신규 31개 + 재사용 엔진 회귀 50개 = **81개 통과**. 원천 감사 generator의 567개 hash/tree 검증과 실제 metadata 소표본 테스트는 합성 가격 계산과 구분했다. 재실행 보고서와 패키지 evidence의 byte equality도 확인한다. 테스트는 새 역사 수익률·C2·WID·기존 봉인 outcome을 실행하지 않는다. 코드 최종 통합 HEAD·추가 독립 검증은 root audit packet에 기록한다.

독립 감사 시 특히 (a) Git blob 존재가 권리/증권 신원으로 승격되지 않는지, (b) 212개 cohort가 탈락하지 않는지, (c) raw archive 부재와 예전 coverage 집계가 혼동되지 않는지, (d) PIT 날짜·CIK가 미래 정보로 보완되지 않는지, (e) 미국 USD 비교에 KRW FX가 섞이지 않는지를 확인한다.
