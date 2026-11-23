# Market Risk Discovery v1

현재 단계는 **Stage 2 사전등록 완료(결과 미조회)**다. Stage 3 실행은 소유자의 명시적 승인을 기다린다.

## Stage 2 (P1 사전등록)

- 사전등록: [STAGE-2-PREREGISTRATION-ko.md](STAGE-2-PREREGISTRATION-ko.md)
- 기계 판독 사양: [`protocol-stage2.json`](protocol-stage2.json), SHA-256은 `protocol-stage2.sha256`
- 설계 검토: [STAGE-2-DESIGN-REVIEW-ko.md](STAGE-2-DESIGN-REVIEW-ko.md)
- 지식 원장 정정·승계: [KNOWLEDGE_LEDGER-CORRECTION-stage2-ko.md](KNOWLEDGE_LEDGER-CORRECTION-stage2-ko.md) / [`knowledge-ledger-stage2.json`](knowledge-ledger-stage2.json)
- 결과 무관 점검(구조·지속성·기회 반영 귀무·가격 기준): `python -m research.market_risk_discovery_v1.stage2_readiness`
- 검정력(가상 신호): `python -m research.market_risk_discovery_v1.stage2_power`
- 사양 재생성: `python -m research.market_risk_discovery_v1.stage2_protocol`
- Stage 3
  - 검증: `python -m research.market_risk_discovery_v1.stage3_execute --verify-only`
  - 실행: `--execute`. 승인 파일이 있어야 하고 1회만 실행된다.

## Stage 1 (근거·원천 감사, 변경 없음)

- 보고서: [STAGE-1-ko.md](STAGE-1-ko.md)
- 누적 지식(Stage 1 원본, 보존): [KNOWLEDGE_LEDGER-ko.md](KNOWLEDGE_LEDGER-ko.md) / [`knowledge-ledger.json`](knowledge-ledger.json)
- 원천 감사(네트워크): `python -m research.market_risk_discovery_v1.source_audit`
- 사건·위험집합 집계(신호 미조회): `python -m research.market_risk_discovery_v1.label_census`, `python -m research.market_risk_discovery_v1.baseline_census`
