# 단일 슬롯 S2 검증 기록

기준 `afb3ea39ef2033e696c4e26485b7e4ebb74134d8`, 계산 전 설계 `48e7f23`. 공개된 과거 표본의 후속 검산이며 새 전향 증거·운영 승격 검증이 아니다.

## 수치와 재사용 검사

- 원 S2 매칭을 날짜마다 재현해 기존 `decisions.csv`의 peer 목록과 일치.
- 모든 매칭에서 앞 순위 S2 보유·ETF 비중을 고정한 B/S/Q를 명시적으로 구성. 6개월 2,097개, 12개월 1,962개 유효 순위-날짜 비교에서 S와 Q의 변경 종목은 S2 해당 순위와 peer 두 이름뿐.
- 기존 원 전체 장부 성과 평균·CI는 `fixed.json`과 객체 단위로 동일. 원 매칭 차분과 새로운 한 슬롯 차이 평균·CI는 전 항목 기존 CSV 정밀도 내 일치.
- 원 가격·기업행위·ETF 총수익·날짜별 비용으로 직접 재구성한 장부와 기존 저장 값의 최대 차이 `1.22e-11`.
- 계산 중 날짜별 3항 분해 오차 `2.22e-16`. 저장 CSV를 독립 재검사한 최대 오차 `8.88e-16`.
- 직접 `20% × (S2 종목 순수익 − peer 순수익)`과 저장 선택 효과의 차이는 최대 `1.53e-11`(기존 CSV 12자리 저장 정밀도).
- 주 표 30개 CI(2기간×5순위×3항)를 저장 행과 동일 날짜 마스크로 재생한 최대 차이 `2.08e-17`.
- 후보 peer가 당시 후보 목록에 포함되고, 양쪽 시총 스냅샷이 판단일보다 엄격히 이전임을 검증.
- 전체/PRESENT/공통/시총 범위/이름 제외 표본 수를 별도 검사. 5위의 두 이름 비율은 기존과 일치(79.3339%/78.7069%).
- 원 v1 결과·코드·보고서의 읽은 파일 SHA256은 전후 동일. 원 폴더·기존 전향 기록·운영·봉인 파일 변경 없음.

원/실제 pickle SHA256을 보존하지만 직렬화 바이트가 같아야 한다고 강제하지 않는다. 의미상 source identity·행렬 digest·판단일·매칭과 모든 실제 비교 슬롯의 가격/비용 순수익을 검증한다. 이번 입력 캐시는 원 캐시의 바이트까지 동일했다.

수치 검사: [results/verification.json](results/verification.json). 입력·코드·원 산출물 기록: [results/provenance.json](results/provenance.json).

## 코드 및 전체 테스트

```bash
ruff check .
python -m compileall -q pipeline research/kr_s2_single_slot_matched_v1
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  pytest -q tests/test_kr_s2_single_slot_matched_v1.py tests/test_kr_s2_rank_ladder_v1.py
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 pytest -q -n 4
python scripts/make_seed.py
python -m pipeline.validate data/site-data.json --allow-seed
```

- 린트·컴파일·seed 생성·합성 산출물 검증 통과.
- 관련 테스트 **8 passed**(새 3개: 한 슬롯/앞 순위 고정, 비용 차감 단일 교체와 prefix 차분의 등가성, 부재/가격/시총 조건과 공통 날짜 분리).
- 저장소 전체 테스트 **6,813 passed / 4 skipped / 4 xfailed**, 실패·오류 0. 실행 1,117.10초. 이번에는 전체 실행 한 번에서 이 결과를 얻었다.
- 전체 테스트의 병렬 실행을 위해 작업용 환경에 `pytest-xdist==3.8.0`을 설치했다. 프로젝트 런타임 의존성·등록된 과학 환경·CI 파일은 바꾸지 않았다. `-n 4`는 테스트 실행 옵션이며 분석 계산은 단일 프로세스다.
- 수치 환경 CPython 3.12.14, pandas 2.3.0, numpy 2.3.1. 기존 CI의 Python과 완전히 동일한 환경이라고 주장하지 않는다. 원 숫자와 입력 identity를 직접 대조했다.

전체 및 관련 테스트·수치 검증 로그는 [validation/](validation/)의 gzip 파일이며 [logs.json](validation/logs.json)에 원본 SHA256과 마지막 결과 줄을 기록했다. 이전 작업의 전체 테스트 결과를 이번 검사로 대신 보고하지 않았다.

## 커밋 계보와 공유

설계는 새 분해 계산 전에 로컬 `48e7f23`으로 커밋했다. 기준 `afb3ea3` 및 설계 커밋의 원 Git commit 본문·tree hash는 [local-authoring-commits.json](validation/local-authoring-commits.json)에 보존했다. 해당 원문으로 Git commit SHA를 다시 검산할 수 있다. GitHub 공유가 별도 업로드 커밋으로 수행되면 원래 로컬 커밋이 업로드 이전부터 GitHub에 있었다고 주장하지 않으며, 최종 tree/파일 바이트 일치를 확인해 구분한다.

재실행: [reproduce.sh](reproduce.sh). 본 연구는 기존 순위 검증만 수행하며 종목 수·점수 가중치 튜닝은 수행하지 않았다.
