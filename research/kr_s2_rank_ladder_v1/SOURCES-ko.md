# 입력 계보와 복구 경로

연구 코드 기준: PR #348 `3a3e9d8e60c90bf6707072efca9d1dabf3cb79ac`. `research/followup_round8_v1/REPORT-ko.md` §3 → `kr_switch.py` → `alpha_search_round6_v1/kr.py` → `kr_followup/s2_decomposition.py` → `sg1_random_control.setup` → `alpha_mechanism_decomposition_v1/analyze.load` 경로를 확인했다.

## 판단일별 순위·적격

- `$S/matrix.pkl`의 `matrix.rows`와 `matrix.values`: #329 `0a1f494171576af6928fe531145a8c8f050253fd`의 `research/ml_strategy_tournament_v1/build_features.py`가 `pipeline.kr_alpha_atlas_inputs.load_inputs` 및 `kr_alpha_atlas_matrix.build_matrix`를 호출해 생성한다.
- 원천: `signal-history 4ea107ed0cde289f0a049a65ff13d2441a786710`의 `ledger/universe/kr/krx-universe-{2013..2026}.jsonl.gz`, `ledger/prices/kr/krx-prices-{2013..2026}.jsonl.gz`, `ledger/fundamentals/kr/shares.jsonl.gz`, 내용 주소 기반 replay 가격 객체. 회계는 별도로 `fb6e83743fd8cdba647d1522a4645b662a9d5647:ledger/fundamentals/kr-candidate-merged/dart-{2015..2026}.jsonl.gz`에 고정된다. 업종은 저장소의 v4 interval/crosswalk이며 frozen spec이 각 blob을 지정한다.
- 품질: 거래 가능, 우선주 제외, 양의 거래량 세션 20 이상, 정지/정체 위험 0 이하, 60세션 거래대금 중앙값 50억원 이상. 거래대금은 원래와 같은 종가×거래량 proxy이다.
- 사업 확인: 순이익·영업현금흐름·영업현금흐름 개선이 모두 양수(`b08Confirmed == 1`). 업종 내 장부가/시가 및 이익수익률 백분위 평균인 `B08_valueBusinessConfirmation`을 측정할 수 있어야 한다.
- `vendor/adaptive_cocktail_v1/cocktail.py:sleeve_book`를 직접 호출한다. 점수 내림차순 → 티커 오름차순, `WITHHELD`(006800.KS) 제외 후 상위 5. 종목 수가 모자라면 나머지 069500.
- `$S/sg1-random-setup.pkl`은 원형 S2·적격군 캐시일 뿐 **순위 파일이 아니다**. `sg1_random_control.stocks`가 티커 정렬하므로 그 목록 순서를 점수 순위로 쓰면 안 된다. 본 연구는 frozen 함수의 `picks` 순서를 사용하고 매일 캐시 보유·적격군과 일치를 검사한다.
- 판단일은 setup의 원래 4개 위상 합집합. 새로운 월말/주간 표본으로 교체하지 않는다.

## 가격·ETF 총수익

- `$S/dataset.pkl`: 같은 #329의 `prepare_dataset.py`가 검증된 raw와 matrix를 합쳐 생성. 주식은 replay-v16 조건부 조정 가격, 거래량·KR 세션을 함께 보존한다. replay manifest `f0781292f508a123c234ded6d28aa8e84a0dc3cc29500e14989dc0b68f53b4d2`, 가격 객체는 `ledger/replay-inputs/objects/<decompressed SHA256>.json.gz`다.
- **069500 입력은 replay의 원 ETF 가격이 아니다.** 생성기가 `docs/audits/kr-alpha-atlas-phase-c-integrity/benchmark-reconciliation-corrected.json`의 `correctedBenchmarkQuotes`를 사용한다. 원 replay는 `069500.KS@replay-v16` 별도 열로 남는다. 기준 보고서의 KODEX 200 총수익은 이 정정 시계열이다. 본 연구도 그대로 사용하며 외부 독립 인증 완료라고 재명명하지 않는다.
- `analyze.load`가 `docs/audits/kr-alpha-atlas-phase-c-integrity/corrected-inputs.json:finalSessionQuotes`를 적용한다.
- `sg1_random_control.setup` → `oci_corrected_nav.corrected_closes`가 `kr_followup/010060-corporate-action-reconciliation.json`의 양쪽 후속 증권 경제수익을 반영한다. 재상장 후 새 OCI를 구 OCI에 무비용 재투자한 근사이며 이후 각각의 후속 종목을 추적하는 장부는 아니다.
- `$S/macro_panel.pkl`, `$S/vix_fx.pkl`: #329 `load_sources.py`가 같은 고정 replay manifest의 macro/vix/fx 객체를 검증해 생성. 원 setup가 위상 계산 중 읽기 때문에 필요하다. 이번 종목 수 규칙에 새로운 미국 거시 신호를 추가하지 않는다.
- 무위험 이자는 `data/bok-policy-rates.json`. 비용은 원 frozen dated schedule. 종목 매수 5.5bp, 매도 5.5bp+해당일 세금; ETF 편도 2.5bp. 미래 세율을 과거에 덮어쓰지 않는다.

## 저장소 밖 파일을 요청하기 전에 확인한 것

작업 시작 시 `/workspace`에는 저장소와 기존 `$S` 캐시가 없었다. 기준 커밋의 트리에도 `matrix.pkl`, `dataset.pkl`, `sg1-random-setup.pkl`은 없다. 기존 집계 JSON과 preview 영수증은 일부 날짜·집계 결과만 있어 순위별 전체 계산을 대체할 수 없다. 다만 원천 Git 객체와 #329 생성 스크립트가 모두 남아 있으므로 구매·파일 요청 전에 이를 복구한다.

깨끗한 재실행에 필요한 경로는 아래와 같다. 모두 같은 공개 저장소의 고정 객체에서 재생성하며 임의의 최신 파일로 대체하지 않는다.

| 경로 | 생성/복구 |
|---|---|
| `$S/matrix.pkl` | #329 `build_features.py --scratch $S/raw --out $S/matrix.pkl` |
| `$S/raw/ledger/universe/kr/krx-universe-*.jsonl.gz` 및 raw accounting/replay 객체 | 위 verified loader가 materialize |
| `$S/dataset.pkl` | #329 `prepare_dataset.py --scratch $S` |
| `$S/macro_panel.pkl`, `$S/vix_fx.pkl` | #329 `load_sources.py --scratch $S` |
| `$S/sg1-random-setup.pkl` | 현재 기준 `sg1_random_control.setup($S)`가 없으면 생성 |

정확한 source commit·blob/content hash는 `research_specs/kr-model-overlay-portfolio-v1.json`, 행렬·입력·캐시 SHA256 및 실행 환경은 새 `results/inputs.json`에서 확인한다. 재실행은 `reproduce.sh`에 고정한다. Git 객체 접근 자체를 잃은 경우에는 위 다섯 캐시와 `$S/raw/ledger/universe/kr/`가 필요한 파일의 정확한 목록이다. 임의 pickle은 읽지 말고 신뢰하는 생성 경로로 만든 파일만 사용한다.
