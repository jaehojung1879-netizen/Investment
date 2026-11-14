# KR/US 산업 원천·입력 계약 — 연구 기반 스프린트

기준 main은 `37f8cbf6b1c066f6b3c65235953648d17ebf2f69`이다. 기존 v1~v4 판정·등록·교차표·실행 잠금은 수정하지 않았다. 산업 수익률, 종목 수익률, 알파 또는 역사 모델은 실행하지 않았다. 아래 새 계산 수치는 **분류 원천 커버리지**이며 투자 성과가 아니다.

## 1. 현재 가능한 범위

| 범위 | 이번 산출물 | 역사 산업 실증 판정 |
|---|---|---|
| KR | 보존된 KIND listing·증권 코드 viewer·변경 공지 body를 재검증한 80건/62증권의 공개 이후 분류 관측 어댑터 | `SOURCE_BLOCKED`: 전체 모집단 분류·종료 22증권·그룹 크기·총수익 원천 미충족 |
| US | 실제 SEC 역사 filing header 1건 복구와 SIC/CIK/acceptance/filing-date 파서 | `PARTIAL` 원천 가능성, 전체 증권 단위 역사 산업 패널은 `SOURCE_BLOCKED` |
| 공통 | 신호일 코호트, 공개·효력·투자 가능 기간, EW/CW, HHI·유효 구성원 수, 최대 종목 제거 진단, 시장/산업/종목의 겹치지 않는 귀속 | 입력 계약·합성 회귀검증 가능; 실제 역사 outcome 실행 불가 |

## 2. KR: 95.295%가 증명하지 않는 것

기존 문서와 원본 감사 파일을 그대로 읽었다.

| 버전 | 보존된 판정과 원인 |
|---|---|
| v1 | `DATA_FOUNDATION_INSUFFICIENT`; 413개 계획 DART 접수 자료를 수집했지만 분류의 신원·판본·경제적 기간·당시 공개가 모두 증명된 membership 0건 |
| v2 | `DATA_FOUNDATION_INSUFFICIENT_V2`; 79개 관측/6증권, 2,876/73,200 name-date(3.93%), 종료 증권 0/2,345, 충분한 그룹 없음 |
| v3 | `DATA_FOUNDATION_INSUFFICIENT_V3`; 재구성 68,807/73,200. 이 중 54,173은 현재 anchor와 변경 공지 부재에 의존하는 추론. 원 감사의 당시 공개 확인 event-interval name-date는 1,798이며 이것도 완전한 PIT 인증과 같지 않음 |
| v4 | `DATA_FOUNDATION_INSUFFICIENT_V4`; 69,756/73,200(95.295081967%). 우선주 4개/949 name-date 추가. 종료 22증권은 0/2,345. 398/610일에서 최소5명 그룹의 분류 구성원 비중이90% 미만. 공식 상위분류 코드 구조 증명도 실패 |

v4의 분류 69,756은 `54,173 inferred + 7,558 current-anchor + 7,076 event + 949 preferred`이다. 이 합계를 역사 PIT 적격률로 부르면 안 된다. 나머지 3,444에는 UNKNOWN 3,442와 identity-terminated 2가 있으며, 종료 2,345 name-date는 결측과 겹치는 별도 분모다. 이 숫자를 결측에 다시 더하지 않는다.

원본: `data/kr-industry-membership-foundation-v{3,4}/state/audit.json.gz`, `docs/kr-industry-membership-foundation-v{1,2,3,4}.md`. 새 `evidence/industry-source-audit.json`에 원본 해시·정확한 22증권·원래 사유를 보존했다. 모든 고정 입력 7개의 SHA256을 정확 main Git blob과 독립 대조했다.

### 새 어댑터가 실제로 보강한 것

`industry.kind_dated_memberships`는 새 원천을 찾았다고 주장하지 않는다. 이미 확보한 원본에 더 엄격한 공개 시점 투영을 제공한다.

1. 고정 events 원본과 67개 listing 원본을 manifest의 고정 해시로 검사한다. 이름만 있는 목록, 에러 페이지, 파일명만 있는 객체는 입장하지 않는다.
2. 각 변경 공지의 listing·viewer·body 3개 바이트를 모두 해시 검증한다. receipt 공개일, viewer의 정확 증권 코드, body의 전후 분류·효력일이 metadata와 일치해야 한다.
3. 최초 공지의 BEFORE 분류를 이전 기간에 소급하지 않는다. AFTER 분류만 `release_date < signal_date` 및 `effective_date <= signal_date`에 사용한다. 늦은 공시는 과거 신호를 재작성하지 않고, 미래 효력 공지는 효력일까지 기다린다.
4. 현재 anchor와 no-change 추론을 입력하지 않는다. KSIC 판본·공식 hierarchy는 미확인으로 유지하며 `KIND_LITERAL / REPORTED_UNVERSIONED`로 분리한다.

기존 고정 Top120 schedule 610일 ×120 =73,200 name-date에서 새 **last-public 관측 입력** 커버리지는 10,093/73,200(13.788251366%)이며 신호일 최소1.667%, 최대27.5%다. 이 schedule의 실제 고유 증권은245이고, 전체 저장 inventory의260 ever-member와 같은 분모가 아니다. 종료22증권의 원천 관측은 여전히0이며, 충분한 그룹 비중 기준은610일 모두 실패한다.

**10,093은 PIT_EXACT 적격 name-date가 아니다.** 이름 기반으로 범위를 좁힌 공지 발견은 누락될 수 있고, last-public 진술은 그 후 실제 경제적 산업이 변하지 않았다는 증명이 아니다. 원 감사의1,798과는 다른 입력 정의라 증가분을 연구 승인 또는 적격률 개선으로 비교하면 안 된다. 이 어댑터는 확인된 자료를 재사용할 수 있게 할 뿐, 기존 판정이나 연구 모집단을 바꾸지 않는다.

### #290 후속 복구와 중복 방지

정확 HEAD `a72311c0d8873d33bd85577293fc1b00e179466c`의 `research/industry_alpha_next_v1/kr22-admission-recovery-status.md`와 `data-eligibility.md`도 확인했다. 이 후속 작업은 v4 이후의 후보를 이미 다루므로 새 DART 파서를 만들지 않았다.

- 후보는 4/22: `003450`, `012510`, `042670`, `057050`.
- 원천 검증된 산업 진술은 `012510`의8건(1/22). **최종 산업 적격은0/22**다.
- 기존 proposal A 승인 시1/22와28/535 member-month, A+B 및 공식 코드북 확인 시2/22와34/535까지 가능한 조건부 경로다. 이것은 본 스프린트에서 승인하거나 채택하지 않았다.
- 배당락일·총수익 라벨 적격은0/22. 산업 분류 후보의 존재가 총수익 확보를 뜻하지 않는다.
- 35개 미확보 종결 정정 공시 수집 계획·기존 parser가 있으므로 재작성하지 않는다. 새 수집 승인/환경/사람의 원문 검토 없이 종결 대가를 확정하지 않는다.

## 3. US: 작은 실제 복구와 남은 경계

2026-11-03 UTC에 다음 공식 SEC header를 **1회**, 본문64KiB 상한으로 요청했다. HTTP200, 실제952바이트를 확보했다. 과거의 SEC403 기록을 현재 모든 SEC 원천의 영구 차단으로 일반화하지 않는다.

- URL: <https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/0000320193-23-000106.hdr.sgml>
- raw: `evidence/industry-sec-aapl-2023-header.sgml`
- SHA256: `e4254ad253c7910000c0887662c49540cc78d7403df93e0fb3b968eefee7ed9a`
- accession: `0000320193-23-000106`; CIK: `0000320193`; reported SIC: `3571`.
- acceptance: `2023-11-02 18:08:27 America/New_York` = `2023-11-02T22:08:27Z`; filing-date는 `2023-11-03`.

`parse_sec_header`는 다수 FILER·중복 CIK·필드 누락·원본 변경을 거부한다. 또한 인용 URL의 CIK 경로, accession 디렉터리와 파일명이 원문 CIK/accession과 모두 일치해야 한다. 다른 SEC filing URL을 붙여 출처를 오인시키는 경우도 거부한다. `sec_issuer_at`는 date-only 판단에서 filing-date 다음날부터 last-disclosed issuer SIC만 반환한다. acceptance와 filing-date를 구분하며 acquisition 시각을 당시 공개로 대체하지 않는다. 실제 산업 변경일은 알 수 없으므로 `effective_change_date=None`이다. 정정·후속 filing은 공개 이후에만 supersede한다.

이 파일 하나는 **CIK→증권→share-class mapping, 역사 SIC 패널, 총수익 가격, 분배/종결, GICS 판본 또는 저장·재배포 권한**을 확보하지 않는다. SIC와 GICS는 별도 체계다. SIC의 공식 판본도 검증하지 않았으므로 현재 GICS나 SIC prefix를 과거 산업으로 자동 변환하지 않는다. 공개 HTTP 접근 및 작은 사실 원문 보존은 대량 재사용·재배포 권리의 확인과 별도다. `PUBLIC_ACCESS_CONFIRMED / RIGHTS_NOT_CLEARED`로 읽어야 한다.

#290은 기존 `sp500-snapshot-sectors.json.gz` 195 snapshots/98,094행에서 분류 수준 혼합(2023-03-07의 Sector123개 라벨), snapshot/sourceCommit 중복 날짜 및 BRK-B/BF-B 연결 문제도 이미 검토했다. 이를 새 역사 산업 입력으로 복사하거나 현재11개 섹터에 맞춰 고치지 않는다. 해당 PR의 schema 격리·identity·판본 확인을 재사용해야 한다.

## 4. 코드 계약과 회귀검증

`industry_plan`은 기존 `pipeline.industry_foundation`의 `Membership`, `freeze_cohort`, `_weights`를 재사용한다. 전체 신호일 유니버스에 미분류가 하나라도 있으면 계획을 차단한다. 투자 가능 여부에는 관측·공개일뿐 아니라 **명시적 유효 종료일과 기간 근거 해시**가 필요하며, 기간 만료/상장종료 시 차단한다. cap-weight는 기존 signal-visible 양의 동일 통화 cap 규칙을 그대로 쓴다. 차단 결과에 weights/HHI를 넣지 않는다.

정상 입력에서 HHI, 유효 구성원 수, 최대 비중 종목, 최대 종목을 제거한 잔여 HHI와 최소 구성원 수 충족 여부를 반환한다. 제거는 집중도 진단이며 원래 실증에서 불리한 구성원을 제외하는 허가가 아니다.

`paired_synthetic_attribution`은 기존 `aggregate_industry/decompose`에 위임한다. 동일 entry/exit/통화의 완전한 총주주수익 및 신호일 이전에 관측·공개된 시장 국면이 필요하다. 시장수익 + 산업의 시장 초과 + 종목의 산업 초과 3개만 더한다. 종목의 시장 초과를 다시 더하는 중복 귀속은 거부한다. 미해결 종결·부분 배당·통화/기간 불일치는 차단하고, `scope!='SYNTHETIC'`이면 즉시 거부한다. 이 모듈에는 역사 outcome 실행 경로가 없다.

검증: `tests/test_cross_market_industry.py`는 실제 작은 SEC 원문 및 기존 KIND 원문 해시·신원·공개일 검증, 미래 효력/늦은 공개/정정/현재 분류 소급 거부, 전체 분모 보존, stale/terminated 투자 가능성, cap 시점 누수, 집중도, 합성 귀속·총수익/종결/통화 경계를 확인한다. 내부 `_weights`를 읽기 전용 재사용하므로 해당 기존 모듈 변경 시 이 회귀검증도 필요하다.

```bash
/workspace/Investment/.venv/bin/python -m pytest -q tests/test_cross_market_industry.py
/workspace/Investment/.venv/bin/ruff check research/cross_market_foundation_v1/industry.py tests/test_cross_market_industry.py
/workspace/Investment/.venv/bin/python -c 'from pathlib import Path; from research.cross_market_foundation_v1.industry import build_industry_source_audit; import json; print(json.dumps(build_industry_source_audit(Path(".")),ensure_ascii=False,indent=2))'
```

## 5. Claude/Owner 후속 결정

승인 없이 가능한 다음 작업은 원천 수준 raw/header 파서·신원 연결·배당/종결 증거 계약을 합성 입력에서 보강하는 일이다. 현재 완성된 인터페이스는 그 입력이 적격해졌을 때 재사용한다. 역사 산업 성과·선정 성능·P0~P5 결과 계산은 이번 산출물의 완료 범위가 아니다.

우선순위는 (1) #290의012510 표 기반 진술 A 승인 판단 및 필요한 배당락일 증거, (2)042670에 필요한 공식 판본 코드북과 B 승인 판단, (3)212 US departed 증권 신원/가격·종결과 SIC 패널을 같은 증권키로 연결, (4)원천이 실제 확보된 뒤 별도 등록의 분류 범위·최소 그룹/검정력·권한을 확정하는 순서다. 기존 frozen crosswalk나 그룹 기준을 바꿔 통과시키지 않는다. 대량 SEC/KRX 수집·인증·유료 원천, 새로운 taxonomy/admission 또는 역사 outcome 실행은 각각 필요한 Owner 결정과 범위를 먼저 확정한다.
