# C1c v2 합성 구현 인계

상태: **미등록 제안 / 실제 원천 미승인 / 실행·승격 비활성**.

사용자의 개발 지시에 따라 C0 일차·C1 보조를 고정했다. 기존 C1-only v1 제안은 노출된 설계 기록으로 보존한다. 신규 제안은 `market-research-c1c-v2.json`과 `market_research_c1c_contract`에 있고 `verify`가 코드와 계약 일치를 확인한다.

- B1: 같은 달력·입력·결측 규칙의 16개 cell을 전부 만든다. 결과로 대조군·가족을 선택하지 않는다. 세 가지 paired 연간 log-growth 대비를 양쪽 대조군·별도 가족마다 모두 산출하고 추론/승격은 하지 않는다.
- B3: 원래 무기억 대 주당 한 단계 복귀와 사후 20세션 돌파는 다른 가설이다. 원 격자는 40/70/100%; 강한 매도 상호작용에만 신설 0/40/70/100% 격자를 쓴다. 이 확장은 원 등록이 아니다. 한 단계 복귀는 더 느릴 수 있으며 돌파와 동의어가 아니다.
- B5/B6: 가격지수/현금0 복제와 ETF 총수익/지정 현금 경제 독해를 분리한다. 실제 원천/권리/해시 불일치를 합성 metadata로 승인하지 않는다. 두 독해 불일치 BASIS_DEPENDENT, KR/US 불일치 NO_PROMOTION이다. 정적 초기혼합 대조는 실제 interval weightStart 평균을 맞추고 기존 드리프트/비용 규칙을 따른다. 사후 matching은 예측/타이밍 알파 검정이 아니다.
- 고정 합성 사건의 급락 회피·반등 기회비용·100% 복귀 지연, whipsaw, 미성숙/PENDING과 진입·전환·청산 비용을 분리해 보존한다.
- B7: 2026-10-30 및 합성 authorizing merge 현지 날짜 이후 첫 주간 신호부터의 달력 계약이다. 첫 기술 독해는 52개 주간 신호의 각 H126/H252 성숙 후다. 별도 **새 제안** 지원 하한은 비중첩8블록이다. 승인 기준도 충분한 검정력 보장도 아니다. 결과 전에 소유자·독립 방법론 검토가 필요하다. KR/US 과거는 이미 노출됐으며 확증 자료로 바꾸지 않는다.
- 합성 영수증은 16개 cell, 계약/실제 코드 해시, fixture 해시, finality–next-open 창과 이전 영수증을 결합한다. 검증기는 값을 재계산한다. digest 재계산과 Python bool/숫자 동등성으로 바이트 변조를 숨길 수 없다. append는 순수 immutable preview다. 실제 clock/승인/source를 인증하거나 live ledger를 쓰지 않는다.

```
python scripts/check_market_research.py verify
python scripts/check_market_research.py synthetic-v2 --market KR
python scripts/check_market_research.py synthetic-v2 --market US
python -m pytest -q tests/test_market_research_c1c.py tests/test_market_research_reentry_structure.py tests/test_market_research_c1c_contract.py tests/test_market_research_c1c_diagnostics.py
```

현재 결과는 합성 실행 준비다. 실제 역사 runner, 원천 승인, live writer, 귀무/검정력 calibration, 소유자 실행 승인은 없다. 기존 봉인94개·워크플로·결과·잠금은 변경하지 않는다.

수치 독해 추가안(`market_research_c1c_decisions`)은 **미등록 제안**이다. net 연간
log-growth↑, funded MDD↑(덜 음수), 일간 순수익 최악 ceil(5%×interval 수)의 평균 손실↓를
고정 비교한다. 같은 가족 C0 BASE와 자기 평균 interval 노출을 맞춘 사후 정적 대조군에
완전한 비교는 `DESCRIPTIVE_SIGN_ONLY`이며 수치 방향·동등·상충은 별도
`numericalRelation`으로 보존한다. 경제 판정은 null이다. 결측·미성숙·기간/자산/현금/비용
불일치는 `INCONCLUSIVE`다. 이전 `IMPROVED`/`NOT_IMPROVED` 경제적 오독 경로는 제거했다. 1e-10은
수치 동등성 허용치로 경제적 허들·유의수준이 아니다. geometric 성장과 arithmetic attribution을
함께 보존하며 통계적 알파·검정력·독립 감사·소유자 승인·실제 성과를 의미하지 않는다.
두 가족 모두 `REENTRY−BASE`, `COMBINED−HARD_EXIT`를 비교해 매도 규칙을 같게 고정한다.
구조적 한 단계 복귀는 무기억보다 느리거나 같고, 별도 사후 돌파는 FAST=1+과거20종가
돌파일 때 빠르게 복귀한다. 두 가족·C0의 모든 팔을 남기고 C1을 결과로 선택하지 않는다.
KR 현금0은 실제 단기금리 수익이 아닌 기회비용 시나리오다. 양수 금리는 명시적 미검증
합성 민감도로만 허용한다. 실제 현금은 당시 공개 원천·known-at·이자·보수·세금 검증이
필요하다. US prior-known DTB3/ACT360 표기를 KR에 전용하지 않는다. 초기 진입과 최종
청산 비용은 누적 순수익·MDD에 포함하며 초기 진입을 CVaR의 가짜 하루로 추가하지 않는다.

교차 공학 검토에서 서로 다른 결정·실행 일정도 같은 가격/현금 basis로 비교할 수 있는
반례를 재현했다. 비교 basis에 전체 일정 SHA를 추가해 거부하고, 허용된 정수값 비용
배수의 보고 자료형을 정수로 통일했다. 이 검토는 Claude 감사·GitHub APPROVE가 아니다.
