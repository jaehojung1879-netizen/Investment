# 검증 기록

2026-11-18 KST. 기준 `d9ac3ed5`, 성과 계산 전 설계 `e6786ee`, 미국 원종가 입력 정정 `4710738`. 기존 운영·신호·전향 원장은 변경하지 않았다.

- 전체 기존 테스트와 당시 수집된 공통 연구 테스트: **6,819 passed, 4 skipped, 4 xfailed**, 1,458.15초. pytest-xdist 4 worker, OMP/BLAS/MKL 각1. [전체 로그](validation/full-pytest.log).
- 최종 추가 연구 테스트: **18 passed**. 원 주간 축의 떨어진 마스크를 보존하는 paired 블록 추정, 미확보 가설을 유지한 Holm41/115, strict 시총 범위·보유 제외·1대1 매칭, 만기 cutoff·최소104주·MDD 가드, 비용/일별 wealth 일치, 미해결 가격 abstention, short book 비중, 확인 미측정, 원 미국 엔진의 missing-held refusal, CTVA 출처 SHA·분할 보충의 반복 실행·원종가 복구를 검증했다. [연구 로그](validation/research-pytest.log). 전체 테스트 수집 후 추가된 시장별 테스트는 이 최종 실행으로 검증했으며 두 통과 수를 합산하지 않는다.
- `ruff check .`, pipeline 및 새 연구 compileall 통과. [ruff](validation/ruff.log), [compileall](validation/compileall.log).
- seed 생성과 `pipeline.validate data/site-data.json --allow-seed` 통과. 생성물은 기존 ignored 출력이며 연구 성과나 운영 자료가 아니다. [생성](validation/seed.log), [검증](validation/artifact-validation.log).
- [독립 산출물 검산](results/verification.json): 설계 바이트 고정, 검정 가족 수·Holm 재계산, 시장별 raw 평균/표본, 선택+대체 항등식, 기여 합, 매칭 범위·중복 제외, 모든 연간 fit의 만기 cutoff·가드, 원 전향6파일 SHA와 결과 manifest를 확인한다.
- 한국 원 S2 0~5의 모든 만기 고정보유 수익 및 일별 운용 NAV, K2/혼합 기준 집계를 검산했다. [고정보유](results/KR/source-reproduction-fixed.json), [운용](results/KR/source-reproduction-ledgers.json). 새 S3 종료가격 미해결은 대체하지 않았다.
- 미국 동일한 원 입력 빈티지가 없다는 한계와 원 집계 대비 차이를 숨기지 않는다. 원 TR·재무/CIK 규칙을 재사용하고 CTVA의 고정 조회 종료일 이후 분할 누락만 출처 응답으로 복구했다. 원 HTTP는 불변이며 [정정 영수증](results/us-ctva-repair-receipt.json)에 전후 SHA가 있다. 미국 결과의 source/harness 차이는 US summary/native ledger에 별도 보존한다.

재실행은 저장소 루트에서 한다.

```bash
export PYTHON=/workspace/s2-venv/bin/python
export KR_INPUTS=/workspace/s2-inputs
export US_INPUTS=/workspace/batch-inputs/us
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
bash research/kr_us_strategy_batch_v1/reproduce.sh all
$PYTHON -m pytest -q tests/test_kr_us_batch_common.py tests/test_kr_us_batch_kr.py tests/test_kr_us_batch_us.py
```

입력 캐시가 있으면 `compute`, 표·집계·검산만 다시 만들려면 `report`, 독립 검산만은 `verify`다. [실행 환경 버전](validation/environment.json). 재생성하지 않고 재사용한 대형 캐시의 정확 경로·source/feature SHA는 KR/US summary와 [미국 입력 문서](US-INPUTS-ko.md)에 있다. 외부 캐시를 보유하지 않은 경우 동일 빈티지 재실행이 제한됨을 명시한다.
