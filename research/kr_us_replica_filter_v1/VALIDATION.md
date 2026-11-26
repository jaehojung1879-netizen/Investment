# 실행 및 검증

기준은 Investment PR #351 `0eceb6f135dd3bd08f35950997d36129bfe67f65`다. 비교 설계는 새 수익 계산 전에 `47548b1`에 커밋했다. 실행 환경은 CPython 3.12.14, NumPy 2.3.1, pandas 2.3.0, SciPy 1.16.0이다. 이전 연구의 가격·신호·공시·비용과 전향 기록을 읽기 전용으로 사용했다. [설계](DESIGN-ko.md) · [코드·원본 해시](results/artifact-manifest.json)

|검증|결과|
|---|---|
|미국 원 코호트 재현|654 판단일, 630/604 만기 주. 비용 차감 복제 기준−SPY를 원본과 대조한 CSV 오차는 3.1×10⁻¹⁶ 이하|
|미국 귀속|329/303주 5항 합, 전체 만기 주의 종목별 기여 합, 가격·분배·가격 출처 분해를 검산. 공시 공개일이 판단일보다 앞서고 보유 기준은 최대 180일 전인지 확인|
|한국 원 코호트·시드 재현|454×9개 기존 해시 장부 및 908개 진입·청산 달력 대조. 원본과 겹치는 개별 수익 37,733건, 오차 4.2×10⁻¹¹ 이하|
|한국 매칭·수익 분해|동일 업종, 시총비 [0.5,2], 중복 대조 금지, 관측된 통과·미통과 검산. 6·12개월 1,770개 코호트의 비용 차감 분해 검산. 필요한 만기 개별 가격 미해결 0건|
|병렬 재실행|KR=0, US=0. 한국 요약과 미국 원본 27개 파일의 SHA가 사전 실행과 일치. Optional 입력 상태 필드를 제외한 미국 요약 수치·범위도 일치. [로그](validation/reproduce.log)|
|대상 테스트|6개 통과. [로그](validation/targeted.log)|
|정적 검사와 seed|저장소 Ruff, Python compileall, Bash 구문 검사 통과. 임시 경로의 합성 seed 생성과 `pipeline.validate --allow-seed` 통과. [seed 로그](validation/seed.log)|
|저장소 전체 테스트|4개 워커에서 6,834 통과, 4 건너뜀, 4 예상 실패. 1,635.00초. 별도 대상 테스트 6건의 집계는 위 행에 표시. [전체 로그](validation/full-pytest.log)|

[수치 검산](results/verification.json) · [한국 원본 대조](results/KR/verification.json) · [미국 원본 대조](results/US/summary.json)

## 재실행

저장소 루트에서 아래를 실행한다. `all`은 시장별 계산을 병렬로 실행하고 양쪽 상태를 기록한다. `report`는 커밋된 두 시장 원본을 읽어 Markdown과 검산만 다시 만든다.

```bash
export PYTHON=/workspace/s2-venv/bin/python
export KR_INPUTS=/workspace/s2-inputs
export US_INPUTS=/workspace/batch-inputs/us
export US_EXPOSURE_INPUTS=/workspace/exposure-inputs/us
bash research/kr_us_replica_filter_v1/reproduce.sh all
bash research/kr_us_replica_filter_v1/reproduce.sh report
```

- 한국은 `$KR_INPUTS/kr-us-batch-v1-prepared.pkl`을 우선 쓴다. 준비 캐시가 없으면 선행 한국 연구의 동일 입력 준비 함수를 호출한다. [외부 원본 파일과 준비 명령](../kr_us_strategy_batch_v1/results/KR/REPRODUCE-ko.md)
- 미국은 `$US_INPUTS/{close.pkl,features.pkl,yahoo-capture-manifest.json,yahoo-raw/}`와 `$US_EXPOSURE_INPUTS/{close-repaired.pkl,us-adapter-payload.pkl}`을 쓴다. 후자 두 캐시가 없는 경우 #351 정정과 `--prepare-only`를 호출한다. 원 가격·피처·비용과 공시는 기존 자료의 봉인 범위다. [입력 계보](../kr_us_exposure_preserving_v1/US-INVENTORY-ko.md) · [FISV 정정](../kr_us_exposure_preserving_v1/INPUT-REPAIR-FISV-ko.md) · [가격과 공시 범위](US-ko.md)
- 전향 기록은 기존 별도 경로의 여섯 파일을 해시로 확인했다. 검증된 최신 입력과 등록된 실거래 기록 승인이 없어 새 전향 관측은 0건이다. [별도 기록 상태](results/prospective-status.json)
