# master-research-program-v1 — 독립 감사 패킷

**검증 수준:** 작성자 자체 검증(`AUTHOR_VALIDATION_ONLY`)이다. 독립 승인이 아니다. 감사자는 작성자가 아닌 별도 세션이어야 한다.
정확한 HEAD는 이 파일을 포함하는 커밋이며, PR #316 본문에 기록한다.

## 1. 파일 범위

이 변경이 추가하거나 수정한 경로는 아래뿐이다. 다른 경로는 건드리지 않았다.

| 경로 | 내용 |
|---|---|
| `research/master_research_program_v1/**` | 신규(아래 레인별) |
| `research/alpha_evidence_sprint_v2/kr_insider.py`, `test_kr_insider.py` | 격리 규칙 추가. `build_event`가 `Event` 또는 `Quarantine`을 반환하고, `state_at`은 `Quarantine`을 거부한다 |

수정하지 않은 것: `research_specs/`, `docs/results/`, `pipeline/`, `.github/`, `data/`, 봉인과 잠금, #315/#306/#314/#299/#307 코드, 기존 #316 산출물(`kr_insider.py` 제외).

| 레인 | 폴더 | 코드 | 산출물 |
|---|---|---|---|
| A 증거 지도·등록부 | `evidence_map/` | `build_evidence_map.py`, `register.py` | `EVIDENCE_MAP.md`, `evidence_map.json`, `REGISTER.md`, `register.json`, `register-entries.json` |
| B 시장·산업 | `market_industry/` | `market_timing.py`, `us_sector_membership.py`, `industry_relative.py`, `build_*.py` | `market_receipts_status.json`, `us-sector-foundation-v1.json`, `kr-industry-foundation-status-v1.json`, 계약 2개 |
| C 종목 정보축 | `stock/` | `insider_density_gate.py`, `kr_event_counts.py`, `stock_axis_audit.py` | `insider-density-gate-v1.json`, `evidence-insider-filing-summaries-v1.json.gz`, `kr-event-report-counts-v1.json`, `stock-axis-audit-v1.json`, `STOCK_AXES.md` |
| D 포트폴리오 | `portfolio/` | `comparison.py` | `portfolio-d-p0-p5-comparison-v1.json`, `report-interface-v1.json`, `c2-remaining-sources.md` |
| 요약 | `.` | | `EXECUTIVE_BRIEF.md`, `REGISTER_SCHEMA.md` |

## 2. 입력 원천

| 원천 | 식별자 | 사용처 |
|---|---|---|
| `main` | `37f8cbf6b1c066f6b3c65235953648d17ebf2f69` | 모든 레인의 기준 |
| `signal-history` | `0b10f54dfefdafa09470b1c0855bc26bf3c58ea5` | 전향 영수증 목록·날짜(A, B), `ledger/universe/kr` PIT Top-120 멤버십(C) |
| S&P 500 스냅샷 | `data/research/us-capital-allocation-alpha-v1/sp500-snapshot-sectors.json.gz`, 스냅샷 195개의 원본 CSV 해시 재검증 | B 미국 섹터 기반 |
| KR 산업 v4 | `data/kr-industry-membership-foundation-v4/` | B. 복사만 하고 재계산하지 않음 |
| 종결 감사 | `docs/results/alpha-opportunity-model-v3-survivorship-audit.json` | B. 퇴출 212개를 섹터별로 집계 |
| DART OpenAPI | `list.json`, `document.xml`, 2026-11-04 수집, 호출 5,517건(오류 0) | C. 원문은 커밋하지 않고 건별 요약만 커밋 |
| 기존 #316 | `86c5983f` | A 카탈로그, C 파서 v2, D C2 계약 |

읽지 않은 것: 수익률, NAV 값, 신호일 이후 가격, 라벨, IC, 모델 출력. 공시 원문의 취득·처분 단가는 공시 시점의 값이며, 상태 계산에는 쓰지 않는다(주식수만 사용).

## 3. 재현 명령

네트워크가 필요 없는 명령은 해시 시드와 무관하게 바이트가 동일한 출력을 낸다. 감사 전에 확인했다.

```sh
cd <repo>
python3 research/master_research_program_v1/evidence_map/build_evidence_map.py --check   # UP_TO_DATE
python3 research/master_research_program_v1/evidence_map/register.py --write
python -m research.master_research_program_v1.market_industry.build_industry_foundation
python -m research.master_research_program_v1.market_industry.build_contracts
python -m research.master_research_program_v1.stock.stock_axis_audit
git fetch --depth=1 --filter=blob:none origin signal-history
python -m research.master_research_program_v1.market_industry.build_market_receipts_status --commit 0b10f54dfefdafa09470b1c0855bc26bf3c58ea5
# DART가 필요한 명령 (outcome-free, 약 5,500호출)
DART_API_KEY=... python research/master_research_program_v1/stock/insider_density_gate.py collect --cache <dir> --max-calls 7000
python research/master_research_program_v1/stock/insider_density_gate.py analyze --cache <dir> --universe <ledger/universe/kr dir> --out <file>
DART_API_KEY=... python research/master_research_program_v1/stock/kr_event_counts.py --out <file>
# 검사
ruff check . && python -m compileall -q pipeline research
python -m pytest -q research/master_research_program_v1 research/alpha_evidence_sprint_v2
```

## 4. 감사 중점 사항

1. **시장 계약:** 레벨 + 타이밍 = 평균 초과수익이 성립하는지(`market_timing.py`). 노출이 그 시점에 알려진 상태만 쓰는지(`exposure_at`).
2. **미국 섹터 표:** 이후 스냅샷이 과거 멤버십을 바꾸지 않는지(`members_on`). 라벨 정규화가 스스로 밝힌 1건(`Telecommunications Services`)뿐인지. 하위산업 열이 섞인 2023-03-07 스냅샷을 "섹터 없음"으로 처리했는지.
3. **내부자 게이트:**
   - Wilson 구간과 PIT 멤버십 조건화가 맞는지.
   - 격리 규칙이 판정을 바꾸지 않는지(규칙을 꺼도 UNCERTAIN).
   - 격리 128건 중 115건이 결제일 기재 패턴인지.
4. **P0–P5 엔진:**
   - 라벨을 바꿔도 경로가 같은지.
   - 미가격 보유 종목이 경로를 막는지, 그때 재정규화가 없는지.
   - Holm 보정과 영수증 다이제스트가 `prospective_receipt_core`와 같은 방식인지.
5. **증거 지도와 등록부:** 각 연구의 분류가 인용한 판정 문자열과 맞는지(`CATALOGUE_MAP`). VERIFIED가 0인지.

## 5. 차단 조건 (실행하지 않은 이유)

| 항목 | 차단 | 해제 조건 |
|---|---|---|
| 모든 KR 역사 outcome | Phase D 종료 | 정확한 해시가 박힌 Owner 승인 + KR Phase D 예외 |
| C2 귀속 | 위 조건 + 투자 가능 KRW 현금 | `AUTHORIZATION-c2.json`; ECOS CD91 항목 검증(`probes.yml`, Owner 실행) |
| 내부자 역사 검정 | G2 `UNCERTAIN` | 나머지 230개 발행사 수집(약 49,000호출) 후 게이트 재판정 |
| 시장 타이밍 전향 | KR C1 SLOW·TRANSITION과 미국 상태의 기록기 없음 | 기록기 구현·병합, 계약 등록 |
| 산업 전향 | KR 소규모 산업 규칙 미정, 미국 섹터 영수증 기록기 없음 | Owner 규칙 결정, 기록기 |
| P0–P5 | 승인된 입력 0개 | 연구 전용 영수증 시작 결정 |
| 미국 역사 | 생존편향(퇴출 212개 가격 없음), #287 권리·식별 | 원천 복구 |
