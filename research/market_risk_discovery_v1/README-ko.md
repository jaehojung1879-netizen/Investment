# Market Risk Discovery v1

현재 단계는 **Stage 1 완료(근거·원천 감사, 결과 미조회)**다. 출발점은 #362 Stage 0이다.

- 보고서: [STAGE-1-ko.md](STAGE-1-ko.md)
- 누적 지식: [KNOWLEDGE_LEDGER-ko.md](KNOWLEDGE_LEDGER-ko.md) / [`knowledge-ledger.json`](knowledge-ledger.json)
- 원천 감사(네트워크): `python -m research.market_risk_discovery_v1.source_audit`
- 사건·위험집합 집계(신호 미조회): `python -m research.market_risk_discovery_v1.label_census`, `python -m research.market_risk_discovery_v1.baseline_census`
- 다음 단계: Stage 2 사전등록 → 소유자 실행 승인 → Stage 3 1회 실행 → Stage 4 독립 감사
