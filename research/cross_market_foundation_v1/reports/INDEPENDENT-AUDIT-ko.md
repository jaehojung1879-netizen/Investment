# Independent audit packet

이 패킷은 구현자가 준비한 감사 자료다. 독립 승인이나 GitHub review를 대신하지 않는다. 정확한 최종 HEAD는 통합 PR의 head와 `git rev-parse HEAD`로 확인하고, CI의 `head_sha`가 동일한지 대조한다. 각 코드/evidence 파일의 최종 바이트는 `evidence/evidence-receipts.json`에 고정한다. 검사 결과·정확 HEAD·CI URL은 최종 인계 기록을 따른다.

## 범위와 변경 경계

기준 main `37f8cbf6b1c066f6b3c65235953648d17ebf2f69`. 새 파일은 `research/cross_market_foundation_v1/` 및 `tests/test_cross_market_*.py`뿐이다. 기존 pipeline/operations/workflow/data/results/registration/AGENTS/lock/protected hashes 수정0이다. #316/#287/#290/#309/#311을 병합하지 않고 exact source refs만 읽었다. 전체 ledger checkout, 새 역사 연구·C2 귀속·실제 P0~P5 평가, 실제 주문, workflow dispatch, 기존 PR push, main merge, force-push는 수행하지 않았다.

## 실제 재현한 결함과 수정

| 결함 | 수정·독립 재현 근거 |
|---|---|
| ECON-CASH-GRID: 금·월 일별 입력이 주말 accrual 누락을 숨김 | required calendar grid 연속성과 각 periodStart 연결을 검사. 누락 주말 거부/주말 전체 필요 회귀 |
| INVESTABILITY-STALE: 과거 available=True가 무기한 유지 가능 | source-backed valid-through/validity digest 및 terminated-on 경계 필수. stale/종료/유효기간 근거 누락 거부 |
| MODEL-COST-ASYMMETRY: caller가 경로별 비용을 다르게 선언 가능 | 공통 내용 해시로 봉인한 STOCK/ETF BUY/SELL tariff에서 실제 leg notional별 비용 산출. 경로별 override 거부, 자기금융 entry/terminal exit 검증 |
| SEC-CITATION: Apple 원문에 다른 회사 URL 결합 가능 | URL host/path/CIK/accession 디렉터리/파일명을 원문과 결속. 잘못된 issuer·accession·query·위장 host 회귀 |
| TERMINAL-REFERENCE: 임의 문자열을 terminal evidence로 인정 가능 | digest-reference 계약 강제. 이것도 실제 원문 검증·admission과 다름을 명시 |
| DISTRIBUTION-PARTIAL: 일부 배당 쌍 일치가 누락 이벤트를 가림 | unmatched 양쪽 이벤트 수·실패 코드와 completeness=false 유지 |

미국 원천 담당의 industry/economics 읽기 전용 교차 검토가 첫 두 외부 재현 사례를 포함했다. 이는 동료 코드 검토이며 비저자 최종 GitHub 승인으로 부르지 않는다. 수정 회귀 및 KR/US 통합 합성 테스트를 제공한다.

## 감사자가 확인할 잔여 위험

1. **SOURCE_BLOCKED:** 212개의 raw 후보 미보유·신원·원가격 기준·actions/terminal·이용권. 공개 Git hash만으로 source 확보나 적격성을 인정하면 안 된다.
2. **SOURCE_BLOCKED:** KIND last-public 관측과 역사 PIT_EXACT 분류를 혼동할 위험. 13.788%를 적격률로 사용하거나 원 v4 실패를 변경하면 안 된다. 종료22·분류판·최소 구성원·투자 가능성은 미해결이다.
3. **SOURCE_BLOCKED:** 한 SEC header는 회사 단위 SIC 사실이다. 전체 패널·GICS·가격 증권/share-class 연결은 아니다.
4. **SOURCE_BLOCKED:** NAV5,918행/공식20배당 확인과 full investor TR/공식 역사 구성/당시 공개 vintage/사용권은 다른 계약이다. 기존46배당 reconciled 연구 표본과20행 원문 window의 분모를 혼동하지 않는다.
5. **SOURCE_BLOCKED:** 실제 투자 KRW 현금·broker fills/slippage가 없다. 인용금리·모형 비용은 실제 체결/현금 경로의 대체가 아니다.
6. **설계 제한:** `prepare_comparison`은 입력 선언·해시·일관성을 검증한다. 선언된 SHA/PIT/권리의 진실성은 별도 원문 검증이 필요하다. 코드가 합성이라고 부르는 수치를 실제 실증으로 표시해서는 안 된다.
7. **계산 제한:** 합성 scorer는 전액 현금에서 봉인 entry-weight 진입 후 만기 청산만 지원한다. 중간 리밸런싱·FX·현금·실제 체결·미등록 통계 검정을 평가하지 않는다.
8. **권한 제한:** exact source hash 검증이나 pytest PASS는 연구 실행 승인도 소유자 merge/deploy 승인도 아니다. 예전 승인·봉인·종료를 새 연구에 전용할 수 없다.

## 재현 검증

```bash
python -m research.cross_market_foundation_v1.audit
python -m research.cross_market_foundation_v1.audit --source-bytes
python -m pytest -q tests/test_cross_market_*.py
ruff check .
python -m compileall -q pipeline research/cross_market_foundation_v1
python -m pytest -q
```

source bytes 검사는 네트워크를 호출하지 않는다. 고정 Git 원천이 없는 clone에서는 `SOURCE_OBJECT_UNAVAILABLE`을 숨기지 않고 필요한 exact commits/paths만 별도로 확보한다. source 재생성 결과와 보존 evidence의 byte equality를 확인한다. 기존 seed generator는 격리 출력에서 실행하고 seed 허용 검증PASS/production 검증거부를 모두 확인한다. 추적 중인 `data/site-data.json`을 갱신하지 않는다.

판정 범위: **코드·입력 계약 검토 가능, 새 실제 경제성 실증은 차단 유지.** 통과한 코드 계약을 연구의 수익성·검정력·사용권·운영 배포 승인으로 확대하지 않는다.
