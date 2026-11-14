# ML Tournament v2 — Integrity Repair

고정된 네 전략의 원천·회계 정정이다. v1, 독립감사, 봉인 결과와 잠금은 보존한다. 새 대회·우승자·production 변경은 없다.

- **A_VERIFIED_CASH**: 원시 가격·주식/ETF 수량·현금·배당채권·실제 체결대금 비용. 완전한 원천이 없는 전략의 전체 성과는 SOURCE_BLOCKED다.
- **A_OBSERVED_PREFIX_INCOMPLETE_EVENT_COVERAGE**: 확인된 원시 가격을 따라 계산하되 처음 미확정 사건에서 중단한 조건부 초기 구간. 빈 날짜에 기업행동이 없었다는 증명은 아니다.
- **controlled-diagnostics.json**: v1 총수익 지수 위에서 회계 근사, 최종 가격, 006800의 2026 현금+주식 패키지만 하나씩 바꾼 통제 계산. 완전한 v2 주주수익이라고 부르지 않는다.
- **B**: 각 훈련 fold의 성숙한 과거 행만으로 입력 열을 선택하고 통계·결측 규칙·점수를 보존하는 고정 후보 재적합. 현재 원천은 차단돼 실제 적합을 하지 않는다. 정확 코드/설정/원천/환경 승인 패킷이 별도이며 원래 Atlas 실행 경로나 잠금을 사용하지 않는다.

회계는 연구용 소수 수량·세전 분배·0% 현금 이자이며, 시작 시 ETF를 이미 보유한다는 v1의 관행을 유지한다. 현금은 같은 결제일의 매매 약정을 상계한 trade-date buying power다. 실제 계좌·실제 체결 확인·거래소 정수 lot·개인 세후 성과가 아니다. 배당채권을 지급일 전에 재투자하지 않고, 주식배당은 인도일 전 별도 비거래 권리로 남긴다.

`vendor/shareholder_inputs.py`는 #328 순수 검증 함수의 경제적 계산을 그대로 재사용한다. 빠진 title-family 의존성 하나만 같은 PR의 순수 함수로 인라인했다. 원본 바이트/출처와 AST 동일성 회귀를 보존한다. `pipeline/kr_alpha_atlas_mirae_repair.py`의 기존 공식 원천 검증도 호출하되 formal/prepare/lock 함수는 호출하지 않는다.

```bash
pip install -r requirements.txt -r requirements-dev.txt -r research/ml_strategy_tournament_v2/requirements.txt
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONHASHSEED=1
python -m pytest -q tests/test_ml_tournament_v2.py tests/test_ml_strategy_tournament_v1.py tests/test_ml_tournament_independent_audit_v1.py
python -m research.ml_strategy_tournament_v2.run
python -m research.ml_strategy_tournament_v2.review
# run이 출력한 실행 디렉터리로 정확한 차단된 B 패킷을 생성한다.
python -m research.ml_strategy_tournament_v2.packet research/ml_strategy_tournament_v2/results/실행해시
```

소스 Git 객체 두 개는 `config.json`의 고정 커밋에 있어야 한다. 캐시는 존재 여부만으로 재사용되지 않는다. `identity.py`가 전체 로컬 import closure, 설정·원천·모델·fold·환경과 payload 해시를 대조한다. 불일치 시 새 파일에 덮어쓰지 않고 거절한다.

실행은 코드가 고정된 커밋에서 수행한다. `results/<execution-identity-sha256>/`의 JSONL gzip은 mtime=0으로 저장하고 결과 manifest로 고정한다. 같은 입력의 재실행은 완전히 같은 바이트여야 한다. 차단된 날짜도 계정·자산·미체결 행을 남기며, 미확인 수량/가치는 null이다. v1의 23.27%·19.36%를 이 결과로 덮어쓰지 않는다.

정식 보존 계산의 코드 커밋은 `8a8d506757585d523ecb7261e23e45b526e69a48`, Python은 **3.13.5**다. 정확 바이트 재현에는 해당 커밋의 별도 checkout과 [installed-environment.txt](installed-environment.txt)의 환경을 사용한다. 테스트용 Python 3.11.17 환경은 [installed-test-environment-python311.txt](installed-test-environment-python311.txt)로 분리했다. 다른 커밋·환경의 실행은 새 identity 디렉터리가 정상이다.

엔진을 import하지 않는 추가 대조는 저장소 루트에서 다음처럼 실행한다. `.py.txt`는 회계 엔진의 실행 코드 closure 밖에 보존한 독립 검사 원문이다.

```bash
python research/ml_strategy_tournament_v2/independent_etf_check.py.txt
python research/ml_strategy_tournament_v2/ledger_invariant_check.py.txt
python research/ml_strategy_tournament_v2/feature_pit_check.py.txt
```
