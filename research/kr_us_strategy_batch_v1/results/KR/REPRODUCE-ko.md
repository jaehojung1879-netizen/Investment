# 한국 계산 재실행

사전 고정 설계는 `research/kr_us_strategy_batch_v1/DESIGN-ko.md`와 `registry.json`이다. 연구 전용 산출이며 기존 전향 장부를 변경하지 않는다.

저장소 루트에서 다음을 실행한다. Python 환경에는 저장소의 분석 의존성이 필요하다. 이번 실행 환경은 `/workspace/s2-venv/bin/python`을 사용했다.

```bash
OPENBLAS_NUM_THREADS=1 /workspace/s2-venv/bin/python -m research.kr_us_strategy_batch_v1.kr --scratch /workspace/s2-inputs --stage all
```

일반적인 전체 실행은 원 `RC.setup`을 한 번 호출한 뒤 후보·매칭·자산별 비용 차감 수익/일별 경로를 공유한다. 자산 경로는 수익을 보고 종목을 교체하지 않는다. 원 S2 0~5 장부의 모든 만기 주차와 원 K2/고정 혼합 평균을 먼저 대조한다. 새 운용 장부는 원 `A.multi_account`/`C.simulate`를 호출하며 동일한 책의 해시만 중복 제거한다.

중단 재개는 다음 명령을 쓴다. `fixed`가 생성한 준비 캐시는 `/workspace/s2-inputs/kr-us-batch-v1-prepared.pkl`이고, 재현에 필요한 독립 입력이 아니라 재생성 가능한 실행 캐시다.

```bash
OPENBLAS_NUM_THREADS=1 /workspace/s2-venv/bin/python -m research.kr_us_strategy_batch_v1.kr --scratch /workspace/s2-inputs --stage fixed
OPENBLAS_NUM_THREADS=1 /workspace/s2-venv/bin/python -m research.kr_us_strategy_batch_v1.kr --scratch /workspace/s2-inputs --stage ledgers
OPENBLAS_NUM_THREADS=1 /workspace/s2-venv/bin/python -m research.kr_us_strategy_batch_v1.kr --scratch /workspace/s2-inputs --stage summary
```

`finalize-fixed`는 자산 수익 계산이 완료되고 CSV가 모두 저장됐지만 요약 단계에서 중단된 경우에만 사용한다. `cohorts-*`, `cohort-mdd-*`, `matched-*`, `pername-cohort-*`와 원 책을 그대로 읽고 원 fixed 검산·정책·통계를 마무리한다. 저장 CSV는 12개 유효숫자이므로 재개 대수 검산은 절대 오차 `1e-10`을 허용한다. 이번 실행은 원 결과 JSON의 `fixed`/`ledgers` 래퍼 키를 맞춘 후 이 재개 경로를 이용했고, 자산 수익/가격 경로를 다시 계산하지 않았다.

```bash
OPENBLAS_NUM_THREADS=1 /workspace/s2-venv/bin/python -m research.kr_us_strategy_batch_v1.kr --scratch /workspace/s2-inputs --stage finalize-fixed
```

외부 원 입력은 `/workspace/s2-inputs/{matrix,dataset,macro_panel,vix_fx,sg1-random-setup}.pkl` 및 `/workspace/s2-inputs/raw/ledger/universe/kr/krx-universe-{2013..2026}.jsonl.gz`다. SHA256·의미상 identity는 `summary.json`에 남는다. 기업행위와 ETF 정정은 저장소의 기존 `research/alpha_mechanism_decomposition_v1/kr_followup/010060-corporate-action-reconciliation.json`, `docs/audits/kr-alpha-atlas-phase-c-integrity/{corrected-inputs,benchmark-reconciliation-corrected}.json`을 재사용한다.

`summary.json`의 수익·비용·비중은 소수 단위다. %와 %p 표시는 100을 곱한다. 454개 원 판단일 축에서 미만기와 미측정을 구분한다. `cohorts-{126,252}.csv.gz`의 `<후보 ID>_excess`는 같은 날짜 ETF 대비 순초과이며, `matched-*.csv`의 `<신호>_selection`은 같은 날짜·이름 수·비중의 업종/시총 peer 장부 대비 차이다. 선택 비교의 모든 신호 공통 표본은 portfolio 가격 공통 표본과 별개다.

주요 원본은 `books.json.gz`/`matched-books.json.gz`/`matching-audit.csv.gz`, `asset-payoffs.csv.gz`, `cohort-mdd-*.csv.gz`, `pername-cohort-*.csv.gz`, `exposures.csv.gz`, `policy-{trace,fits}-*`, `nav-L*.csv.gz`, `ledgers-L*.json`이다. `ledger-cache/*.pkl`은 원 엔진의 재개용 출력 캐시이며 최종 NAV·JSON 원본으로 다시 확인할 수 있다. NAV의 원 미해결 종료 ZERO가 발생하면 `turnoverDiagnostic.terminalEvents`에 계정/날짜/종목/소실액을 남기고 `eligibleForRiskImprovementClaim=false`로 표시한다.

```bash
/workspace/s2-venv/bin/python -m pytest -q tests/test_kr_us_batch_kr.py
/workspace/s2-venv/bin/ruff check research/kr_us_strategy_batch_v1/kr.py tests/test_kr_us_batch_kr.py
```
