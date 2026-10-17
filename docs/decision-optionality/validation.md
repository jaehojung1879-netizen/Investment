# Validation — Decision Optionality v1

환경: Python 3.12.14; 저장소 requirements의 pandas 2.3.0, NumPy 2.3.1,
exchange-calendars 4.11.1, pytest 8.4.1, ruff 0.15.8. 별도 venv는
`/workspace/.venvs/investment`다. BLAS/OMP/MKL thread 수는 각각 1로 제한했다.

| 검사 | 결과 |
|---|---|
| `ruff check .` | PASS |
| `python -m compileall -q pipeline` | PASS |
| 신규 `tests/test_decision_optionality.py` | 52개 합성 테스트. 관련 기존 3개 파일과 함께 **118 passed** |
| 전체 `pytest -q` | 실행 중; 완료 뒤 이 문서에 실제 집계를 기록 |
| `python -m scripts.run_decision_optionality --summary` | PASS; KR/US 각 4개 시나리오, 0~5종목, 결정 고정 뒤 양/음 경로 비교 |
| 반복 실행 | 전체 합성 보고서의 byte-equivalent dict 및 시나리오 digest 동일 |
| 전체 pipeline import / scripts 구문 검사 | PASS |
| 설치 재실행 / `pip check` | PASS; 고정 Git 객체 존재 시 재전송 생략, 의존성 충돌 없음 |
| 역사 reader/fitter 접근 금지 | `historical_store.load/read_jsonl`, `historical_calibration.calibrate`, `ValuationData.window`를 예외 spy로 교체해도 합성 실행 PASS, 호출 0 |
| 실제 subprocess CLI | PASS; `__main__` 동작 확인. `--historical`은 nonzero, 표준출력 없음 |
| seed 생성 | 기존 `scripts.make_seed`의 출력 ROOT만 임시 경로로 주입. `/tmp/investment-seed-gyguhmie/data/site-data.json` 생성, 기존 site-data 미변경 |
| seed artifact 개발 검증 | `python -m pipeline.validate <temp>/data/site-data.json --allow-seed`: PASS |
| seed artifact production 검증 | 예상 거절(exit 1): seed/synthetic 불허, modelsTrained=0 |

합성 검증은 정책의 실현 가능한 주문·비용 산술과 제약을 확인한다. 실제 역사 수익률,
연율 성과, MDD, 통계적 우위, 현실 예측 보정, 실전 readiness를 확인한 것이 아니다.
reader/fitter 호출 0은 실제 spy 테스트에서 확인했고, 실행기 출력에 임의의 접근 카운터를
하드코딩하여 증명한 것으로 표현하지 않는다.

전체 회귀 검증은 기존 저장소 테스트를 실행한다. 이것을 새 D1~D4 역사 정책 실행이나
미승인 outcome 열람으로 확대하지 않았다. 기존 예상 실패는 별도 집계하며 임의로 해제하거나
테스트/봉인을 고치지 않는다. 최종 신규 모듈의 국소 보완 뒤에는 관련 118개를 다시 실행했다.

클라우드 설정 초안에 검증한 `install_script`와 `start_skill`을 저장했다. 고정 의존성 설치,
CI integrity 검사의 고정 Git 객체 준비, venv 활성화·검사·임시 seed 검증과 별도 승인 경계를
포함한다. 기존 체크아웃을 사용하고 사용자가 요청하지 않은 worktree를 만들지 않는다.
PR 생성 경로 확인 중 `api.github.com` 허용도 초안에 추가했고, 이후 실제 API 읽기와 Draft PR
생성이 성공했다. 초안 저장과 환경 게시는 별개이며, 새 task snapshot 복원은 검증하지 않았다.
