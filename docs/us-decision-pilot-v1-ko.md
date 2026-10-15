# US Decision Pilot v1 — 수익률 비교 결과

## 1. 수익률 결론

| 전략 | 실제 CAGR / SPY 대비 / MDD / 변동성·Sharpe | 상태 |
|---|---|---|
| SPY 매수·보유 | 미산출 | NOT_ESTIMABLE |
| Price-only | 미산출 | NOT_ESTIMABLE |
| Multifactor | 미산출 | NOT_ESTIMABLE |
| 기대 순초과수익 관문을 적용한 0–5종목 | 미산출 | NOT_ESTIMABLE |
| 강제 상위 5종목 진단 | 미산출 | NOT_ESTIMABLE |

**최종 판정: NOT ESTIMABLE. 실제 전략 비교는 실행하지 않았다.** 따라서 “SPY를 이겼다/못 이겼다”, 순위가 틀렸다, 비용이 컸다, 관문이 보수적이었다는 결론도 내리지 않는다. 연도별 성과·회전율·비용·보유 수·현금 비중·연도별 결측률·H63/H126/H252 IC·상위 집단 스프레드·ablation은 모두 미측정이며 0으로 채우지 않았다.

[실행 상태 JSON](results/us-decision-pilot-v1/result.json) / [전략별 CSV](results/us-decision-pilot-v1/strategy-metrics.csv) / [사전 고정 규칙](us-decision-pilot-v1-protocol.json). 이들은 실제 백테스트 결과로 포장한 합성 결과가 아니다. 계산하지 못한 항목은 JSON `null`, CSV 빈칸이다. 단 한 건의 새 비교 예산도 아직 소비하지 않았다.

## 2. 가장 유용했던 팩터

**NOT_ESTIMABLE.** 미래 수익률을 읽지 않았으므로 가장 좋은 팩터를 고를 근거가 없다. 고정한 B1은 252세션 모멘텀과 낮은 252세션 변동성의 동일 가중 순위다. B2는 price / OCF÷자산 / 영업이익÷자산 / 낮은 자산성장 / 낮은 부채비율의 **5개 경제적 군에 각각 1/5**를 부여한다. value는 가격·주식수 basis 확인 전 보류한다. 각 군 제거도 원래의 동일 완전사례에서만 비교하도록 했다. 가중치·기간·종목 수 탐색은 없다.

## 3. 가장 문제가 컸던 부분 — 입력 사용 범위

이번 요청에는 다음 두 문장이 함께 있다.

> 역사 데이터의 기존 가격과 이미 확보된 PIT 팩터를 사용할 수 있다.

> 기존 replay-v16, US-MF-1, P4 one-shot 연구의 봉인된 데이터·실행 잠금·결과를 절대 수정하거나 소비하지 않는다.

**원자료를 읽기 전용으로 쓰는 것도 “소비”에 해당하는지 질문했지만, 아직 답변을 받지 못했다. 현재는 금지 쪽으로 적용했다.** 데이터가 없다는 판정이 아니며, source-access 또는 라이선스가 새로 실패했다는 판정도 아니다.

실제 코드를 확인하면 주식별 장기 가격 경로는 `scripts/audit_us_capital_allocation_overlap.py:load_sealed` → `pipeline/us_dual_benchmark_data.py:SealedReader` → `ledger/historical/replay-v16/inputs.json`이다. main의 별도 `data/research/us-dual-benchmark-v1/spy-qqq-total-return.csv.gz`도 manifest의 `builtFrom.replayManifestSha256`가 같은 replay-v16을 가리킨다. 파일을 복사하거나 다른 경로로 이름을 바꿔 금지를 우회하지 않았다. 원자료 가격·기존 봉인 연구 결과·P4 실행기는 읽거나 호출하지 않았다. 보호 **코드와 메타데이터**만 확인했다.

**기존 예산이 모든 새 연구를 막는다고 주장하지 않는다.** `AGENTS.md` v2.24는 닫힌 범위를 “기존 31개 특징 행렬”로 한정하며 새로운 accounting-quality 축은 별도 연구가 될 수 있다고 명시한다. 이 pilot의 중단 이유는 그 규정이 아니라 이번 요청의 입력 경계 미해결이다. US-MF-1 admission gate는 그대로 두었고, 복구 후보 가격을 적격 입력으로 편입하지 않았다. 이 pilot의 지시를 P4 승인이나 기존 결과·잠금의 사용 허가로 전용하지 않았다.

별도의 경제적 제한도 있다. B1/B2의 **순위는 기대 순초과수익률이 아니다**. 이 점수 전용으로 당시 사용할 수 있었던 기대수익 추정 없이 기존 production 관문을 통과했다고 만들 수 없다. 그 경우 관문 전략은 `NOT_ESTIMABLE`이며, “관문 때문에 전부 현금이고 CAGR 0%”라는 실측 결과가 아니다. 허용된 입력이 확인되면 강제 상위 5종목은 별도 진단으로만 계산해야 한다.

## 4. 오늘 매수 후보

**CURRENT_CANDIDATES_NOT_VERIFIED**, 후보 목록은 비어 있다. 2026-10-15 한국시간 검토 시점의 최신 완료 세션 가격·기업행위 basis·시점별 구성원/섹터·그때 공시된 PIT 재무자료·점수별 기대 순초과수익 근거가 함께 검증되지 않았다. 역사적 마지막 후보를 오늘의 매수 후보로 표시하지 않았다.

## 5. 다음에 고칠 단 하나의 문제

**기존 가격 원자료의 읽기 전용 재사용 범위를 확정한다.** 허용된다면 정확한 manifest를 고정한 기존 생존자 조건부 패널에서 새 ID의 비교만 수행한다. 금지된다면 같은 데이터를 복사한 파일이 아니라 독립적으로 사용이 허용된 패널이 필요하다. 어느 선택도 P4 실행·MF1 gate 완화·복구 후보 가격 편입·실전 투자를 허용하지 않는다. 추가적인 범용 데이터 준비도 감사는 다음 행동이 아니다.

## 6. 구현·재현·검증

수치 계산 코어는 source를 직접 열지 않는다. 합성 테스트는 미래 가격 변경에 대한 신호 불변성, 결측 대체 금지, 동일 완전사례, 실제 production selector의 섹터당 2개/최대 5개 제한, 다음 세션 종가 체결, 비용을 실제 자본에서 지급하는 자금 일치, 누락 종가/종결 대가에 대한 거부, 비측정 지표 `None`을 확인한다. 실제 거부 경로에는 payload 접근 spy 테스트가 있다.

현재 상태 재현:

```bash
python scripts/run_us_decision_pilot.py --report /tmp/us-decision-pilot.json \
  --csv /tmp/us-decision-pilot.csv
```

이는 **거부 상태를 재현하는 명령**이며 실제 성과 비교 실행 명령이 아니다. override 옵션이나 P4 잠금 생성 경로는 없다. 새 비교 규칙과 코드는 기록했지만 실제 결과를 산출했다고 주장하지 않는다. 실제 전략 실행을 재현하는 스크립트는 입력 경계가 해소되기 전에는 완성할 수 없다.

기준 main `c14080cf9266e5d2b1b6babae8ae3c018c54b93c`; #241/#242/#243 MERGED 확인. #244는 별도 Draft로 유지했고 그 branch·파일을 사용하거나 수정하지 않았다. 기존 workflow·등록·봉인 입력·결과·잠금·production 변경은 없다. 집중 테스트와 전체 저장소 검사, 최종-head GitHub CI의 실제 완료 결과는 PR 본문에 기록한다.
