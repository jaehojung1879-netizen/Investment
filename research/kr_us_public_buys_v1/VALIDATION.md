# 입력 계보, 재실행, 검증

기준은 PR #352 `e950496ecc7ba73532b4a4dce7bc578294ba9e8c`다. 비용·공시 범위·매칭·결측 처리 비교는 새 성과를 계산하기 전에 `3f0a751`에 고정했다. 원 가격·ETF 총수익·거래비용과 기업행위 정정의 계보를 재사용했다. [설계](DESIGN-ko.md) · [#352 입력과 검증](../kr_us_replica_filter_v1/VALIDATION.md)

이전 미국 연구는 Form 4를 원천 점검 단계까지 다뤘다. 당시 정정·거래 행·공개시점까지 연결한 수익 검정은 미확보였다. 한국 선행 소유 지표는 외부 투자자가 포함된 5% 대량보유 보고를 검토했다. 이번 검정은 국내 임원·주요주주 보고와 미국 적격 보고자의 확인된 현금 장내 취득을 비교한다. [미국 선행 원천 점검](../cross_market_foundation_v1/reports/US-SOURCES-ko.md) · [한국 선행 가설의 모집단](../../docs/alpha-information-inventory-v1-next-hypotheses.md)

## 재실행

```bash
export PYTHON=/workspace/s2-venv/bin/python
export KR_INPUTS=/workspace/s2-inputs
export US_INPUTS=/workspace/batch-inputs/us
export US_EXPOSURE_INPUTS=/workspace/exposure-inputs/us
bash research/kr_us_public_buys_v1/reproduce.sh
bash research/kr_us_public_buys_v1/reproduce.sh report
```

첫 명령은 정정·미국 공시 효과와 한국을 병렬로 계산하고 상태를 각각 남긴다. `KR`, `WAT`, `US` 인수로 계산 하나만 실행할 수 있다. `report`는 커밋된 원본으로 표와 검산을 다시 생성한다.

- 한국은 `$KR_INPUTS/kr-us-batch-v1-prepared.pkl` 및 저장소의 공시 입력 패널을 사용한다. 원문 재수집, 남은 접수번호와 파일, 거래일과 공개일 취급은 한국 상세를 참고한다. [한국 원천과 최소 누락 자료](KR-ko.md)
- 미국은 `$US_INPUTS/{close.pkl,features.pkl,filings.pkl}`과 `$US_EXPOSURE_INPUTS/{close-repaired.pkl,us-adapter-payload.pkl}`을 재사용한다. 기존 정정 캐시 재생성은 #352 경로를 따른다. 기준 파일과 원본 장부를 대조한 뒤 최종 선택을 평가한다. [미국 가격·시총 입력 계보](../kr_us_replica_filter_v1/US-ko.md#재실행)
- SEC 원천의 별도 섭취는 `bash research/kr_us_public_buys_v1/reproduce.sh source-US`로 재실행한다. 공식 분기 ZIP 캐시 기본 경로는 `/workspace/public-buys-inputs/US/bulk/`다. 파일의 SHA·범위·시점 정의와 샘플 원문 교차검증을 보존했다. [미국 공시 출처](US-SOURCES-ko.md) · [분기 파일 원천](inputs/US/source-manifest.json)
- 발행주식 수는 SEC 원문과 접수 정보로 확인했다. WAT 세 표지, 별도 동시기 회사 공시, 기타 시총 정정 행의 원문 근거·판단일 공개 여부 정보는 WAT 상세와 기계판독 자료에 있다. [주식 수 감사와 재현](US-WAT-ko.md) · [정정 시총](results/WAT/corrected-caps.csv)
- 전향 경로의 기존 6개 파일을 해시로 대조했다. 등록 승인과 검증된 최신 입력이 필요한 경로의 새 실거래 기록은 0건이다. [전향 기록 상태](results/prospective-status.json)

## 검증 결과

- 실행 환경은 CPython 3.12.14, NumPy 2.3.1, pandas 2.3.0, SciPy 1.16.0, exchange_calendars 4.11.1이다.
- 판단 가격 데이터에서 SEC 발행사 CIK 연결 후보 242,280 종목·주 전부를 원 공개 이력 또는 당시 지수 구성원 신원 기록으로 대조했다. XNYS 정규 종가와 원 판단일 654개를 일치시켰다.
- 한국 보조 날짜의 6·12개월 원 ETF 비용 차감 수익, 장부 선택·교체·전체 분해를 검산했다. 수집되지 않은 원문과 주 경계를 누락 목록에 보존했다.
- 6개월 주 가설은 두 시장 각각 세 비교를 같은 보정 묶음에 뒀다. 관측되지 않은 검정의 보정 자리에는 p=1을 남겼다. [가설별 원본](results/hypotheses-6m.csv)
- 캡 정정의 주식 수×종가, 공시 공개시각, 장부 선택·교체 분해와 편입 시점의 원시 CSV 재검산을 적용했다. [수치 검산](results/verification.json) · [산출물 SHA](results/artifact-manifest.json)

|검증|결과|
|---|---|
|재실행|한국은 동결 공시 패널에서 요약 바이트 일치. 미국은 동일 사건·정정 사본에서 핵심 코호트와 L26/L52 재현. 사후 선택 민감도는 선택이 실제로 비교된 주의 분모로 검산. [한국 로그](validation/kr-rerun.log) · [미국 로그](validation/us-run.log)|
|Form 4 원문 대조|52개 원문과 접수 시각 확인. 확인 매수 26개 전부 원 거래와 거래별 장내 근거 대조. [원문 대조](results/US/events-original-crosschecks.json)|
|미국 주식 수 정정|943행의 수량×종가와 공개 시각을 대조. B 및 U1 원 만기 결과 4개 책의 원본 대조, 정정 비중 합과 주간 증분 손익 계산 확인. [원 장부 검산](results/WAT/verification.json)|
|저장소 전체 테스트|4개 워커에서 6,840 통과, 4 건너뜀, 4 예상 실패. 1,691.72초. [로그](validation/full-pytest.log)|
|최종 연구 대상 테스트|13건 통과. 공시 시각·정정, 미확인 거래, 매칭과 장부 분해를 검증. [로그](validation/targeted.log)|
|정적 검사 및 seed|저장소 Ruff, Python compileall, Bash 구문 검사와 합성 seed 생성 검증을 통과. [seed 로그](validation/seed.log)|
