# 한국 재실행 입력 감사

주 입력은 #350 원본 `research/kr_us_strategy_batch_v1/results/KR/`와 기존 `/workspace/s2-inputs/` cache다. 새 어댑터는 원 책·peer·고정만기 수익을 재사용하고, 전체 positive-cap Top120 복제에 필요한 빠진 asset/date 수익만 같은 `kr.asset_payoff`로 계산한다. `_q`·재무완전성·Top5 조건으로 복제 기준을 줄이지 않는다. `adapter-input-audit.json`에 원본 SHA, source identity, 실행 runtime, 재현 오차를 남긴다.

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 /workspace/s2-venv/bin/python -m research.kr_us_exposure_preserving_v1.kr --scratch /workspace/s2-inputs
```

`--stage prepare`는 시장 입력과 선택력·매칭 감사까지만 준비하고, `--stage run`은 같은 코드·설계 SHA의 준비물을 재사용해 공통 엔진을 실행한다. 준비 cache와 NAV 입력은 `/workspace/exposure-inputs/kr/adapter-input.pkl`, `/workspace/exposure-inputs/kr/nav-input.pkl`이다. NAV 입력의 `ctx`를 pickle로 읽기 전 `research.kr_us_strategy_batch_v1.kr`를 import해야 동적 원 모듈이 등록된다. NAV suffix는 단순 기존 NAV slicing이 아니라2026-01-02부터 새 계정으로 시작하는 별도 보조 창이다.

`kodex-pcf/raw/`에는 Samsung 공식 endpoint가 반환한 서로 다른24개 전체 PCF JSON이 gzip으로 있다. `kodex-pcf/manifest.json`은 요청/반환 표시일, 본문 SHA, 관측 UTC 또는 원시각 미보존 상태, 원 URL을 기록한다. 원 공식 JS/HTML은 gzip으로, 전일 평가단가 비교·PCF 의미·HTTP429 중단 증거는 `evidence/`에 있다. 추가 다운로드 없이 `kr.official_audit`가 원본 SHA와 행 수를 검증하고 normalized/노출 감사를 재생성한다. 가용한 이전 공시만 최대120일 사용하며 stale 자료를 이후에 계속 적용하지 않는다.

PCF는 Portfolio Deposit File이며 설정·환매 basket이다. 특히2018-05-03의 삼성전자 행 누락과 원화예금27.9025% 때문에 실제 투자 보유와 같다고 주장하지 않는다. 공식 노출 표는 `actualFundHoldingsVerified=False`, 원 배포 빈티지 미검증으로 고정한다. 공시를 확보한 사실과 실제 ETF 전체 복제 수익을 계산한 사실은 다르다.

`replay-price-inventory.json`은 기존189개 월별 price panel의 SHA 확인 재고다. KR260종목 밖 추가 TR은 없었다. 더 넓은 raw KRX510종목 quote가 있어도 그것을 같은 TR이라고 바꾸지 않는다. `quote-hazards.json`은 설계 전 입력-only support 검사 결과이며, 어댑터가 quote/거래가능성 boolean만으로 다시 검산한다. 마지막 미해결 terminal session2025-12-15 이후 다음 연도 첫 판단일이2026-01-02다. 체결불능까지 없는 엄격 suffix는 데이터 내 존재하지 않는다.

검산은 다음 명령으로 결과 분해, PCF 직접+간접 합계, nearest funding의 셀 L1 최소값을 확인한다. peer 미매칭 날짜에는 peer 노출 행을 만들지 않으며 해당 공시 표의 peer 행 수는58보다 작을 수 있다.

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 /workspace/s2-venv/bin/python -m research.kr_us_exposure_preserving_v1.validate_kr
```
