# 한국 S2 순위 기여 연구 검증 기록

코드 기준 PR #348 `3a3e9d8e60c90bf6707072efca9d1dabf3cb79ac`. 연구 계산 전 설계 `7a6ec28`. 실제 수치 실행은 CPython 3.12.14, pandas 2.3.0, numpy 2.3.1이다. CI의 Python과 동일 환경이라고 주장하지 않는다.

## 연구 검산

- 입력 행렬: 85,680행·76열, digest `32e49b57a7541eea66f76373baef50c6302a394247b313f6099f718d46d54b0c`.
- 입력 identity: `3e4d7aa35e2c4b273e4ecef0e2e8ea7a8a27077f0de14bb3d5ea6a696a97f1a5`. 기존 값과 정확 일치.
- 원 S2 6개월 평균 재현 차이 0, 12개월 차이 8.7e−18.
- ETF·S2의 L26/L52 CAGR·ETF 대비 차이·MDD·편도 회전율·연 비용: #348 대비 전 항목 차이 0.
- 날짜별 인접 기여의 합 및 선택/노출 분해가 전체 순초과와 일치. CSV 반올림 후 최대 절대 차이 약 1.1e−11.
- 판단일 이전 만기만 학습에 사용함을 모든 판단일에서 검사.
- 기존 전향 파일 6개가 기준 커밋과 바이트 동일. 실제 전향 관측 추가 0. preview를 전향 증거로 바꾸지 않음.
- 전체 값·산출물 SHA256: [verification.json](results/verification.json). 입력 캐시 SHA256: [inputs.json](results/inputs.json).

## 코드 검사

```bash
ruff check .
python -m compileall -q pipeline research/kr_s2_rank_ladder_v1
python -m pytest -q tests/test_kr_s2_rank_ladder_v1.py \
  tests/test_followup_round8_v1.py tests/test_alpha_mechanism_decomposition_v1.py
python scripts/make_seed.py
python -m pipeline.validate data/site-data.json --allow-seed
```

린트·컴파일·seed 생성·seed 산출물 검증 통과. 연구 관련 **29개 테스트 통과**(새 경제/누수 검증 5개 포함). 합성 산출물은 운영 배포에 사용하지 않았다.

## 저장소 전체 테스트: 초기 실패를 환경 복구 후 재검사

각 단계는 별도 실행이다. 한 번의 전체 실행이 처음부터 모두 통과했다고 보고하지 않는다.

|실행|결과|
|---|---|
|단일 스레드 전체 `pytest -q`|6,682 passed / 80 failed / 44 errors / 7 skipped / 4 xfailed|
|환경 접근을 허용해 실패·오류 124개만 `pytest -q --lf`|83 passed / 41 failed|
|아래 과거 Git 객체·보조 버전 보완 후 41개 `--lf`|38 passed / 3 failed|
|마지막 읽기 전용 과거 CLI 객체 보완 후 3개 `--lf`|3 passed|

**최종적으로 전체 범위 6,806개가 통과했고, 7 skipped·4 xfailed가 남는다(전체 실행과 실패 재검사 합산). 미해소 실패·오류는 없다.**

원인은 다음과 같았다. 수치 연구의 원천·규칙·기존 테스트 코드를 수정해 통과시키지 않았다.

- 제한된 실행 환경에서 로컬 HTTP 서버를 만들지 못해 FRED 복원력 테스트가 실패했다. 네트워크 접근을 허용한 재검사에서 통과했다.
- 일부 기존 봉인/Pages 감사 테스트는 `GIT_NO_LAZY_FETCH=1` 또는 `remote.origin.promisor=false`로 과거 Git 객체 자동 조회를 금지한다. 부분 복제에 해당 객체가 없으면 실패한다. 과거 객체만 읽어 Git 객체 캐시에 보완했다. 작업 트리·봉인 파일은 바꾸지 않았다.
- 대표 누락은 `23522002dcd2d9e0e16dfb9d325a235aef664f0c`의 `.github/workflows/pages.yml`·이전 유지보수 기록·검증기, `37f8cbf6b1c066f6b3c65235953648d17ebf2f69`의 원 등록 코드, `8b43d6ee55829b4db57a3b65cdb345b3523329d7`의 `pipeline/rp1_us_universe.py`·`scripts/rp1_inspect_us_universe.py`다.
- 설치된 보조 라이브러리가 `joblib 1.5.3`, `threadpoolctl 3.6.0`이라 기존 등록 버전 검사가 실패했다. 저장소 `constraints/ci-registered-numerics-v1.txt`가 정한 `joblib 1.6.0`, `threadpoolctl 3.7.0`을 설치해 해결했다. 이번 금융 계산 이후 테스트 환경 보완이며, 금융 결과를 재선택하거나 재추정하지 않았다.
- 과거 객체 누락 실패는 별도 무변경 기준 커밋 worktree에서도 재현했다. 최초 2 failed / 1 error, 별도 Pages 대표 검사 1 failed였다. 원 로그를 보존했다.

재실행 시 전체 테스트는 등록된 보조 버전과 과거 Git 객체가 있는 환경에서 실행한다.

```bash
pip install -c constraints/ci-registered-numerics-v1.txt \
  -r requirements.txt -r requirements-dev.txt
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 pytest -q
```

전체·재검사·기준 커밋 대조·연구 관련 테스트 원 로그는 [validation/](validation/)의 gzip 파일에 있으며, [log-manifest.json](validation/log-manifest.json)에 비압축 원본 SHA256과 마지막 결과 줄을 남겼다.

수치 연구 재실행은 [reproduce.sh](reproduce.sh)와 [보고서](REPORT-ko.md)의 명령을 따른다. 이 연구는 운영·승격·배포·미국 공시 구매를 실행하지 않았다.
