# MVMA-v1 · 시장 밸류에이션 × 기업이익 × 거시환경 ETF 비중 조절 연구

**단계:** 첫 번째 PR — 데이터 적격성, 입력 보존, 사전등록. **수익률·NAV·성과는 계산하지 않았다.**
**상태:** 사전등록 사양은 그대로(`protocol.json`, 변경 없음). Phase 2는 별도 승인 파일 [`authorization-phase2.json`](authorization-phase2.json)로 실행. `EXPLORATORY_ON_OUTCOME_EXPOSED_HISTORY`, 승격 불가.

## 질문

시장 PER의 직전 5년 평균 대비 할인, 이익의 방향, 신용 스프레드를 보고 ETF 비중을 60/80/100%로 바꾸면, 비용과 위험을 고려해 고정 비중보다 나은가? 그 차이는 평균 노출(LEVEL)에서 오는가, 시점 선택(TIMING)에서 오는가?

## 이번 PR이 확정한 것

| 문서 | 내용 |
|---|---|
| [DATA-REGISTER.md](DATA-REGISTER.md) | 원천별 확보 경로(저장소 → Artifact·브랜치 → 기존 dispatch → 차단), 실측 커버리지·개정·공표 지연, 소유자가 실행할 dispatch 경로 |
| [EVIDENCE-GAP.md](EVIDENCE-GAP.md) | 선행연구(#316·#329·#331·#350~#356, 미국 C1)와의 중복·신규성 |
| [PREREGISTRATION.md](PREREGISTRATION.md) | 가설·정책·신호·추론·판정 기준. 기계 판독본은 [`protocol.json`](protocol.json)과 해시 사이드카 |

핵심 사실:

- **미국 입력은 확보·보존했다.** Shiller 후행 PER(두 빈티지, 4개월 분기말 지연), ALFRED BAA−GS10 판단일 빈티지 원장(212/212), BIL 원가격(#331 객체 재사용) + SSGA 공식 분배금을 보존했다. SPY 총수익은 저장소 원본을 그대로 쓴다.
- **예상 PER·예상 EPS는 미·한 모두 원천이 없다.** 원래 VM1/M1은 `SOURCE_BLOCKED`로 남긴다. 후행 EPS로 만든 VM1T/M1T를 별도 정책으로 등록했다.
- **한국은 원천이 막힌 것이 아니라 Phase D 거버넌스로 역사 검정이 `NOT_RUN`이다.** 국고채 3년은 기존 ECOS 실행으로 검증됐다. 회사채 AA-는 dispatch 1회로 검증할 수 있다. Top-120 합산 PER은 이미 수집된 KRX 시총과 DART 이익으로 구축할 수 있다.
- **결과 조회 전 준비도:** "싸지만 이익·신용 악화" 상태는 미국 창 152개월 중 1개월뿐이다. 제안서의 핵심 2×2 비교는 서술만 가능하다고 미리 고정했다.

## 재현

```bash
python -m research.market_valuation_macro_overlay_v1.source_probe --out research/market_valuation_macro_overlay_v1/evidence/source-probe.json
```

```bash
python -m research.market_valuation_macro_overlay_v1.collect_inputs --out-dir research/market_valuation_macro_overlay_v1/data
```

```bash
python -m research.market_valuation_macro_overlay_v1.build_signals --out research/market_valuation_macro_overlay_v1/evidence/us-signal-readiness.json
```

```bash
python -m pytest -q tests/test_mvma_v1_features_signals.py tests/test_mvma_v1_protocol_probe.py tests/test_mvma_v1_inputs.py
```

Shiller 파싱에는 `xlrd==2.0.1`이 필요하다. 저장소 requirements에는 넣지 않았으며 수집 단계에서만 쓴다. 네트워크 수집은 재실행할 때마다 수집 시각과 응답 해시가 바뀐다. 커밋된 원장이 이 연구의 고정 입력이다.

## 다음 단계 (두 번째 PR, 소유자 승인 후)

1. 소유자 실행 승인 파일. 사양 해시와 코드 해시를 고정한다.
2. BIL 총수익 재구성.
3. H1-US-TRAILING, H2-US-VM1T 1회 실행. LEVEL/TIMING은 #316 `market_timing.py`(blob `dabc7ee0`)를 사용한다.
4. 결과를 본 뒤 문턱·창·비중을 바꾸는 재실행은 하지 않는다.
