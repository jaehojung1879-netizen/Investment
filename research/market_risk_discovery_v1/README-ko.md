# Market Risk Discovery v1

현재 단계는 **Stage 2 v2: 독립 감사 대응 완료, `NOT_READY_FOR_INFERENTIAL_STAGE_3`(결과 미조회)**다. Stage 3 추론 실행은 하지 않으며 P1은 전향 기록 대상이다.

## Stage 2 v2 (독립 감사 대응)

- 감사 대응: [AUDIT-REMEDIATION-ko.md](AUDIT-REMEDIATION-ko.md)
- 사전등록 v2: [STAGE-2-PREREGISTRATION-v2-ko.md](STAGE-2-PREREGISTRATION-v2-ko.md), 사양 [`protocol-stage2-v2.json`](protocol-stage2-v2.json)
- 검정 타당성: [NULL-VALIDATION-ko.md](NULL-VALIDATION-ko.md)
- 원장 추가: [`knowledge-ledger-stage2v2-addendum.json`](knowledge-ledger-stage2v2-addendum.json)
- 생성모형 선택(라벨 없음): `python -m research.market_risk_discovery_v1.stage2v2_generator_selection`
- 합성 귀무 검증: `python -m research.market_risk_discovery_v1.stage2v2_synthetic`
- 사양 재생성: `python -m research.market_risk_discovery_v1.stage2v2_protocol`
- 하네스 검증: `python -m research.market_risk_discovery_v1.stage3_execute_v2 --verify-only` (사양이 NOT_READY이므로 `--execute`는 거부)

## Stage 2 v1 (P1 사전등록, PR #365 — v2로 대체, 기록 보존)

- 사전등록: [STAGE-2-PREREGISTRATION-ko.md](STAGE-2-PREREGISTRATION-ko.md)
- 기계 판독 사양: [`protocol-stage2.json`](protocol-stage2.json), SHA-256은 `protocol-stage2.sha256`
- 설계 검토: [STAGE-2-DESIGN-REVIEW-ko.md](STAGE-2-DESIGN-REVIEW-ko.md)
- 지식 원장 정정·승계: [KNOWLEDGE_LEDGER-CORRECTION-stage2-ko.md](KNOWLEDGE_LEDGER-CORRECTION-stage2-ko.md) / [`knowledge-ledger-stage2.json`](knowledge-ledger-stage2.json)
- 결과 무관 점검(구조·지속성·기회 반영 귀무·가격 기준): `python -m research.market_risk_discovery_v1.stage2_readiness`
- 검정력(가상 신호): `python -m research.market_risk_discovery_v1.stage2_power`
- 사양 재생성: `python -m research.market_risk_discovery_v1.stage2_protocol`
- v1 하네스(`stage3_execute.py`)는 영구 거부된다.

## Stage 1 (근거·원천 감사, 변경 없음)

- 보고서: [STAGE-1-ko.md](STAGE-1-ko.md)
- 누적 지식(Stage 1 원본, 보존): [KNOWLEDGE_LEDGER-ko.md](KNOWLEDGE_LEDGER-ko.md) / [`knowledge-ledger.json`](knowledge-ledger.json)
- 원천 감사(네트워크): `python -m research.market_risk_discovery_v1.source_audit`
- 사건·위험집합 집계(신호 미조회): `python -m research.market_risk_discovery_v1.label_census`, `python -m research.market_risk_discovery_v1.baseline_census`
