# 독립 감사 대응 보고서 — PR #365 Stage 2 (P1)

- **감사 기준 HEAD:** `87c824c3f6f05c9993b458c61ac89dbf7bb0c09a` (PR #365). 감사 판정은 `NOT_READY`였다.
- **대응 브랜치:** `claude/market-risk-discovery-stage2-v2`. #365 위에 쌓은 별도 Draft PR이다.
- **보존한 것:** v1 사양(`protocol-stage2.json`, SHA-256 `e8bb2aee…c8f6`), v1 설계 문서, v1 증거는 바이트 그대로다. 비교 계산 코드(`stage2_design.py`)와 입력 구성 코드(`panels.py`)도 바꾸지 않았다.
- **바꾼 기존 파일 2개**
  - `stage3_execute.py`: v1 하네스를 영구 거부로 바꿨다.
  - `tests/test_market_risk_discovery_stage2.py`: v1 하네스 테스트를 영구 거부를 확인하는 테스트로 바꿨다.
- **결과 조회:** 실제 신용 경보와 실제 미래 하락 라벨을 결합한 계산은 0회다. Stage 3는 실행하지 않았다.
  - 확인 방법: `results/` 디렉터리와 승인 파일이 없다(테스트로 고정).
  - 실제 값을 요청하는 코드는 두 하네스뿐이다(AST 테스트).
  - v2 코드가 읽은 실제 자료는 신용·가격과 시점 기준(PIT) 위험집합 상태뿐이다.

REMEDIATION_BODY
