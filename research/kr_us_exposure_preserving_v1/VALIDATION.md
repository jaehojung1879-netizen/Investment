# 실행 및 검증

기준 PR #350 `36ac329261f8f9000935e524d8a28c2005524c10`. 핵심 가설·비용·자금 조달은 성과 계산 전 `e3e572f`, FISV 입력 정정은 `ec9a221`에 기록했다. 이번 실행은 CPython 3.12 및 #350 가상환경의 NumPy 2.3.1, pandas 2.3.0으로 수행했다.

- 한국 9개 기존 책과 5개 기존 대조군의 유효 날짜를 재현했다. 원 고정보유 수익의 최대 오차 8.90e-12, 선택 차이 1.98e-12. 4,086개 책의 조달 최소오차 항등식, PCF 직접+간접 비중 합을 별도로 확인했다. [입력 대조](results/KR/adapter-input-audit.json) · [한국 검산](results/KR/adapter-validation.json)
- 미국 7개 기존 책과 4개 대조군의 유효 날짜를 재현했다. 최대 오차 2.39e-15. 원 칵테일·U1 슬리브 합산, SEC 공개일과 미매핑 비중, 자금 조달 수식도 확인했다. [입력 대조](results/US/prior-350-bridge.json) · [미국 검산](results/US/us-validation.json)
- 한국 장부는 기존 엔진을 호출했다. 전 기간 직접복제는 미해결 보유 종료 때문에 수익·낙폭을 미측정으로 표시했다. 2026년 보조 창은 해당 연도 첫 판단일부터 새 계정으로 실행했다. 미국 장부는 기존 거래비용 해법을 호출하고 보유 구간을 벡터화했다. 원 엔진과 겹치는 가격·거래·NAV 검산 최대 오차 2.00e-15. [한국 장부](results/KR/funded-ledgers.json) · [미국 장부](results/US/funded-ledgers.json)
- 통합 검산은 설계 바이트, 기존 전향 6개 파일의 SHA, 실제 명목 조달 예산, 정확 일치한 업종·대형주 노출, 각 날짜의 ETF 대비 차이 분해를 확인했다. [검산](results/verification.json) · [원본·코드 SHA](results/manifest.json)
- `ruff check .`, `python -m compileall -q pipeline research/kr_us_exposure_preserving_v1`, Bash 구문 검사, seed 생성, `pipeline.validate --allow-seed` 통과. 관련 테스트 21개 통과. [관련 테스트](validation/targeted.log)
- 전체 pytest 상태는 [로그](validation/pytest.log)에 기록한다.

## 재실행

저장소 루트에서 #350의 외부 입력 캐시를 재사용한다. Python 환경은 #350 검증 버전과 같다. 한국 입력이 없으면 #350의 `prepare_kr.sh` 및 원 캐시 재생성 절차, 미국 입력이 없으면 #350의 CTVA 정정까지 포함한 원 경로를 참고한다.

```bash
export PYTHON=/workspace/s2-venv/bin/python
export KR_INPUTS=/workspace/s2-inputs
export US_INPUTS=/workspace/batch-inputs/us
export US_EXPOSURE_INPUTS=/workspace/exposure-inputs/us
bash research/kr_us_exposure_preserving_v1/reproduce.sh
bash research/kr_us_exposure_preserving_v1/reproduce.sh report
```

첫 명령은 각 시장을 독립 실행하고 두 번째 명령은 커밋된 원본에서 표와 검산만 복원한다. 원 FISV HTTP 캐시와 봉인 기업행위로 사본을 만들 수 있다. [한국 입력](inputs/KR/) · [미국 입력과 원 SEC 재생성](US-INVENTORY-ko.md) · [#350 입력 재현](../kr_us_strategy_batch_v1/REPORT-ko.md)

```bash
"$PYTHON" -m research.kr_us_exposure_preserving_v1.validate_kr
"$PYTHON" -m research.kr_us_exposure_preserving_v1.us_validate --private "$US_INPUTS"
```
