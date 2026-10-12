# US 전체 관측 구성종목 실소스 dry-run v1

실행 전 상태: NOT_MEASURED. 합성 테스트 성공은 Yahoo 연결 증거가 아니다.

현재 관측 S&P 500 구성 CSV 전체(공유 클래스 포함)와 SPY/QQQ를 기존
수집기로 검증한다. XNYS 종료 +60분을 지난 최근 세션 하루만 요청한다.
ETF 두 건이 유효해야 구성종목으로 진행한다. 공급자 어댑터 호출 간격은
최소 1초, 호출 상한 552, 시간 예산 1,200초, 공급자 timeout 20초다.
429는 내부 재시도 이전에 중단하며 다음 종목을 요청하지 않는다.
요청별 시간과 거부 원문, 유효 가격 및 소스 패널을 staging에 저장한다.
반복 저장 검증은 이미 받은 값만 재사용하며 추가 네트워크 요청을 하지 않는다.

실소스 실행은 PR opened 이벤트와 지정 브랜치, 동일 저장소, 첫 실행으로
한정된 임시 Tests job을 사용한다. 결과 보존 후 임시 job과 보호 테스트 변경은
전부 제거하고 기존 main 바이트로 복원할 예정이다. 새 workflow는 추가하지 않는다.

CLI: `python scripts/dry_run_us_full_universe.py --output /outside/checkout/fresh-stage`.
출력은 checkout 밖 새 디렉터리만 허용한다. source-audit.json,
attempts.json, provider-http-attempts.json, evidence-hashes.json과 기존 수집기의
불변 가격/구성/획득/manifest 파일을 Actions artifact에 보존한다.

구성 CSV는 보조 소스이고 관측 시점에만 적용된다. 공식 유효 편입일이나
역사적 PIT 구성, 영구 증권 식별자를 증명하지 않는다. CIK는 발행사 식별자이며
공유 클래스의 영구 ID가 아니다. 한 세션의 배당·분할 열 검증은 기업행동
전체성, 향후 정정, 스핀오프를 증명하지 않는다. 과거 #231의 35건 PASS는
기존 증거로 보존하며 이번 전체 dry-run의 결과와 구분한다.

실험, 수익률, 모델, 자동 일정, production signal-history 쓰기는 수행하지 않는다.
