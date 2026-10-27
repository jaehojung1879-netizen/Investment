# 고정68 OpenDART 원본 검증 인계

공개 #294 영수증(9921cb76ec7eb7ddc0744a5025b7dfadeab6244f)은 고정 계획의 68개 신원과 모두 일치한다. 68개 SHA는 서로 다르며 총 14,350,491바이트를 선언한다. 이는 수집자 기록 검증이며, 현재 Codex가 원본을 재해시한 숫자는 0/68이다. 기존 공개첨부 HTTP200 빈본문 실패와 공식 API 원본 취득을 구분한다.

가장 먼저 Claude의 원본 임시 디렉터리를 소유자가 승인한 비공개 지속 보존 위치로 옮기고 manifest.json, 68개 receipt.bin, 공개 receipt.json의 정확한 바이트를 함께 보존해야 한다. Public Git에 원본을 넣지 않는다. 이 코드는 키나 새 수집을 요구하지 않고 로컬 바이트만 읽는다.

PR286 수정 checkout에 기존 pinned source Git objects가 있을 때:

```bash
python -m research.stock_working_capital_v1.portable_collection --verify-plan research/stock_working_capital_v1/xbrl_recovery_v2/portable-plan.json.gz
python -m research.stock_working_capital_v1.opendart_recovery --acquisition /private/original-wc68 --receipt /private/receipt.json
python -m research.stock_working_capital_v1.opendart_recovery --acquisition /private/original-wc68 --receipt /private/receipt.json --output /private/new-wc68-measurement
python -m research.stock_working_capital_v1.pit_join --verify /private/new-wc68-measurement
```

첫 검증은 0, 완전한 입력 측정은 F2 미선택 상태이므로 정상적으로 3을 반환한다. 4는 원천 또는 실행 인프라 오류다. 마지막 출력은 coverage.json, rows/cohorts.jsonl.gz, source-quality.json을 만들며 기존 파일을 덮어쓰지 않는다. 원본 ZIP은 수정/압축해제하지 않는다. 경로 역슬래시는 안전성 비교 시에만 메모리에서 정규화한다.

원본이 회수되어 사라졌다면 Claude가 이미 승인된 DART_API_KEY 환경에서 #294의 collect_receipt.py collect <동일 계획> <새 비공개 디렉터리>를 실행하고 receipt 단계로 다시 기록한다. 기존 공개 영수증 SHA와 68개 바이트를 각각 비교하여 달라진 원본은 새 vintage로 분리하고 동일 바이트 재현이라고 주장하지 않는다. Codex 네트워크 차단을 우회하거나 새 키를 요구하지 않는다.

검증 단계는 (1) exact receipt/기업/FY/공개일/계획, (2) 원본 hash/CRC/ZIP/신원/기간말, (3) 기존 pinned comparator의 raw API 금액 대 원본 XBRL 금액·KRW 단위·CFS/OFS·연간 context, (4) 고정51,360 모집단 PIT join, (5) 미선택 F2와 기타 gate를 구분한다. 단계2는 재무사실 적격이나 역사 vintage의 독립 서명이 아니다. 2019 IFRS 접두어만 바꿔 같은 경제 개념이라고 처리하지 않는다.

기존 `source-quality-v1.json`의 바이트와 해시는 보존했다. 종전 테스트는 과거 영수증의 producer hash를 현재 수정된 리더 코드와 비교하고 있어 수리 자체가 실패하는 오류였다. 이제 기존 PR286 HEAD `a5fef4a6d5c767056441d14e8e6aa8388f5507e9`의 실제 producer blob과 비교한다. 신규 `xbrl_recovery_v3/source-quality-v3.json`은 현재 리더로 과거 차단된 동일 manifest와 51,360행을 다시 검증한 별도 입력 진단이다. 기존 모든 신호 집계는 동일하고 CODE8/계획/봉인 해시를 바꾸지 않았다. 새 API68건을 실제 재해시했다는 주장이 아니다.

회귀 재현: 이전 source-quality 테스트는 타 acquisition을 양성 measurement에 붙여도 집계할 수 있었고 before 로그에서 이를 재현했다. 새 binding 테스트는 정확한 manifest/receipt/route와 원본 per-leg SHA가 없으면 거부한다. 신규 OpenDART 모듈의 전후 테스트는 기능 추가 전 import 오류(기능 미존재)와 구현 후 46 PASS를 기록한다. 경로 충돌·symlink·압축 폭탄·CRC 읽기·DTD(UTF8 BOM/UTF16/UTF32 포함)·틀린 기업/FY/공개일·Boolean 숫자·변조 SHA/크기·다른 acquisition 바인딩·KRW/연결별도/연간 문맥 오류·51,360 분모·append-only writer를 포함한다. 이는 합성 또는 기존 입력 영수증 테스트이며, 실68개 원본 독립 감사와 구분한다.

## 같은 연차 쌍의 통제변수와 실제 입력 진단

`baseline_panel`은 기존 `features.annual_pair/amount`를 재사용해 매출 성장, 현재 잔액/매출, 고정 전기 매출에서의 잔액 변화와 당기 잔액에서의 매출 분모 변화를 분리한다. 이 분해 순서는 대수적 귀속 규약이며 실제 회수·효율 개선의 증거가 아니다. 기존 제안의 sales-growth/focal-level controls를 구현하며 새 알파 가설이나 결과 검정을 추가하지 않는다.

고정 51,360행을 유지한 실입력 진단: 매출채권 통제는 9,589행/252개 연차 쌍, 재고 통제는 31,282행/775개 연차 쌍에서 읽을 수 있었다. 그중 비율이 개선됐지만 원래 잔액이 줄지 않은 경우는 각각 2,358행/65쌍, 5,438행/132쌍이다. 주간 반복 행을 독립 증거로 세지 않는다. 원본 신원·금액·연간 기간·F2 적격과 결과 검정은 별도이며, 여기서 source-admitted는 계속 0이다. [`same-pair-controls-readiness-v1.json`](same-pair-controls-readiness-v1.json)에 원천·측정 해시와 결측 원인을 기록했다.

```bash
python -m research.stock_working_capital_v1.baseline_panel --measurement research/stock_working_capital_v1/pit_measurement_v2 --output /private/new-wc-control-diagnostics
```

실제 과거 종목 수익률·예측력·가치/성장/수익성 알파를 새로 검정한 것이 아니다. 68개 ZIP의 비공개 지속 보존 및 위 로컬 검증이 다음 선행 작업이다. F2 정책·원천 권리·기업행동·벤치마크·표본/원천/code hash를 확정한 뒤에만 별도 연구 실행 승인을 요청할 수 있다.
