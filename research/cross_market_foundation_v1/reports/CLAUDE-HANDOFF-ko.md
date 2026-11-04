# Claude Opus handoff — outcome-free foundation

## 먼저 읽을 결론

새 실제 수익률/역사 라벨/C2 outcome은 실행하지 않았다. 원 연구 파일·결과·등록·보호 해시·실행 잠금은 그대로다. 통합 브랜치는 `research/cross-market-foundation-v1`, main 기준은 `37f8cbf6b1c066f6b3c65235953648d17ebf2f69`다. #316@`86c5983ffba643a58d9eba84a05dc60f4d8e9e6a`를 비롯한 고정 결과는 읽기 전용으로 재사용했다. #314/#315 및 다른 worktree에는 쓰지 않았다.

## 해결한 문제와 새로운 중요 사실

1. 미국 Git blob 보유와 실제 source commit→tree/path 결속을 구분했다. 과거 원천 commit의 얕은 메타데이터 및 필요한 기존 shard만 읽어567개 객체와17개 회계 shard의 결속을 복구했다. missing clone이 upstream 데이터 부재라는 잘못된 결론을 제거했다.
2. 212개 audit identifier 전부의 독립적인 신원·가격·기업행동·종결·권리 실패를 남겼다. 과거 후보175개/409CSV와 현재 raw 미보유를 구분한다. 새로 적격화한 departed 가격 session은0이다.
3. KIND80공지/62증권의 확인된 AFTER-label과 공개/효력일 입력을 연결했다. 10,093 name-date는 last-public 관측 투영이며 PIT_EXACT 적격률이 아니다. 현재 anchor나 무공지 추론으로 과거를 채우지 않는다.
4. SEC 과거 header952B에 실제 접근해 SIC/CIK/acceptance-time parser를 검증했다. 당시 SEC403을 현재 모든 SEC 원천의 불가능 판정으로 확대하지 않는다. 전체 패널 확보라는 뜻도 아니다.
5. 기존 main의 공식 KODEX200 NAV·종가5,918행과 배당JSON/XLS20건을 파싱·대조했다. #316의 NAV series ABSENT는 정정할 수 있다. ETF PDF(portfolio deposit file)는 `.pdf` 확장자 분배 문서와 다르며 그 과거 구성 공백과 실제 체결/PIT shareholder TR 공백은 유지한다.
6. KOFR 정식 공시는2021-11-26, 정식 공시 이전 잠정역사 공개는2022-04-18이다. 실제 repo 현금 경로는 여전히 없다. 인용금리의 관측 기간과 당시 투자 가능 기간을 혼동하지 않는다.
7. 비용은 모델별 수동 입력 대신 공통 tariff·자기금융 진입·만기 청산에서 산출한다. 주말 현금 누락, 오래된 investability의 무기한 사용, 원문과 다른 SEC URL 결속 문제를 회귀로 막았다.

## 아직 해결하지 못한 병목

| 우선순위 | 다음 작업 | 완료 조건 |
|---|---|---|
| P0 | US 기존 후보 raw/panel의 합법적 보관·재사용 확인 | 원 해시와 일치하는 실제 사본, historical price issuer/share-class, 원거래/배당/권리/종결 lineage. 생존자로 교체하지 않음 |
| P0 | KRW 현금 및 공통 shareholder TR | 투자자/상품/수수료/세금/출시·공개 시점/전체 기간이 명시된 실제 입력. reference rate로 소급 대체 금지 |
| P1 | KR 종료22 및 산업 분류 | #290 기존 후보/admission-rule 제안을 재사용. 필요한 별도 승인·공식 코드북·시점별 원문·총수익을 충족. 현재 적격0/22 유지 |
| P1 | US 역사 SIC와 증권 신원 | 실제 filing header 집계, 공개 시점, CIK→security→share-class 유효 기간. 현재 GICS를 소급하지 않음 |
| P1 | ETF 산업 중립 및 기여 입력 | 공식 dated ETF 구성/비중/P&L/비용. Top120 proxy를 ETF 구성으로 대체하지 않음 |
| 별도 운영 | Portfolio D 첫 전향 기록 | #306/#314 등의 소유자 검토·병합·활성화는 기존 release 담당이 수행. 실제 첫 receipt 이후 지역 ETF/비용/동일 시작일/만기 누적 |

## 즉시 사용 가능한 코드와 재현

- `us_sources.py`: 고정 source inventory 재생성·공시 metadata/date/CIK 입력·통화 gate.
- `industry.py`: `load_retained_kind`, `build_industry_source_audit`, `parse_sec_header`, `industry_plan`, 합성 귀속.
- `economics.py`: `parse_ecos_benchmark_quotes`, `build_cash_input_contract`, `adapt_issuer_distributions`, `reconcile_distribution_events`, `total_return_input_gate`.
- `comparison.py`: `prepare_comparison`, `maturity_status`, `price_execution_legs`, 읽기 전용 receipt 어댑터, `score_synthetic_fixture`.
- `audit.py`: evidence 무결성 및8개 readiness cell 검증. source admission/승인 도구가 아니다.

저장소 root에서:

```bash
git rev-parse HEAD
python -m research.cross_market_foundation_v1.audit --source-bytes
python -m pytest -q tests/test_cross_market_*.py
python -m research.cross_market_foundation_v1.us_sources --repo . --output /tmp/us-foundation-reproduction
```

US generator는 실제 blob이 로컬에 없으면 실패한다. source-only 재획득 절차와 정확 SHA/path는 US 보고서 및 inventory를 따른다. `score_synthetic_fixture`는 실제 outcome 클래스를 거부하며, 새 outcome runner를 추가하는 것은 다음 연구의 별도 범위다.

## 중복하지 말 것

#316 C2 계산/실행 guard·prereg, KR v1~v4 parser와 실패 판정, #287 recovery/admission, #290 종료종목 원천 제안, 기존 `industry_foundation`, `prospective_receipt_core`, 지역 달력을 재작성하지 않는다. #309/#311의 이미 노출된 결과를 독립 OOS 근거로 재포장하지 않는다. 기존 Portfolio D 운영 code를 연구 브랜치에서 변경하지 않는다.

## Owner에게 필요한 결정만

- 데이터 제공자의 연구 재사용·보관·필요 시 배포 범위를 증빙하고, 유료/대량 취득이 필요하면 별도 승인한다. 공개 URL 접근 성공은 이용권 승인과 다르다.
- 실제 투자자·현금 상품·세금·배당 재투자·체결 비용의 경제적 계약을 선택한다. BOK/KOFR/CD91 benchmark를 자동 채택하지 않는다.
- 기존 #290 조건부 admission-rule A/B를 채택할지는 별도 결정한다. 이번 브랜치는 채택하지 않았다.
- 새 실제 경제성 실행은 모든 원천 gate·독립 감사 뒤 정확 코드/입력/사전등록 해시로 별도 승인한다. 이번 산출물은 실행 허가가 아니다.
- 통합 PR의 검토·병합과 별도 운영 PR의 병합·배포는 소유자가 결정한다.

현재 실제 outcome 실행 준비 완료라고 보고할 연구는 없다. 즉시 진행 가능한 것은 원천 admission, 입력 재현, 합성 회귀와 기존 운영 담당의 전향 기록 준비다. 가장 먼저 원천을 통과시키고 그 다음 기존 고정 연구의 실행 적격성을 판단한다. 새 모델 탐색이나 임계값 변경을 먼저 하지 않는다.
