# MCT-v1 · Market Causal Transmission

경제적 충격이 시장에 **어떤 경로로** 전달되는지와, 그 정보가 당시 이용 가능한 형태로 6~12개월 투자 판단에 가치를 주는지 검증한다.

| 단계 | 문서 |
|---|---|
| Stage A — 기존 연구·문헌 대조, 신규성, PIT 적격성 | [STAGE-A-ko.md](STAGE-A-ko.md) |
| Stage B — 사전등록 (결과 조회 전 커밋 `329605f5`) | [PREREGISTRATION-ko.md](PREREGISTRATION-ko.md), [`protocol.json`](protocol.json) |
| Stage C — 1회 실행 결과 | [REPORT-ko.md](REPORT-ko.md), [`results/mct-v1-result.json`](results/mct-v1-result.json) |

결론: 세 주 주장(H1-P, H2-P, H3-P)은 모두 미지지(Holm p 1.0)다. 증거 등급은 `EXPLORATORY_ON_OUTCOME_EXPOSED_HISTORY`이며 승격하지 않는다.

```bash
python -m research.market_causal_transmission_v1.readiness
```

```bash
python -m pytest -q tests/test_mct_v1.py tests/test_mct_v1_result.py
```
