# Industry Alpha — independent next-study design

**DESIGN_DRAFT / EXECUTION_DISABLED / NOT READY FOR MERGE.**

한국·미국에서 신호 당시 이용 가능한 산업 정보가 향후 H126/H252 지역 시장
초과수익을 예측하는지 검정하기 위한 독립 연구 축이다. 이번 PR은 자료·증거 감사,
실행 전 설계, 합성 계약 테스트만 추가한다. 종목 연구 #286·#287과 독립이며
두 PR의 코드·브랜치·결과·진행 상태를 변경하지 않는다.

| 문서 | 내용 |
| --- | --- |
| [증거 감사](evidence-audit.md) | 이미 측정된 사실, 최신 main/PR, 봉인과 최종 판정, 미측정 항목 |
| [자료 적격성과 복구](data-eligibility.md) | KR 재구성/종료 신원 분리, US 시점별 분류 스키마, 왜곡 측정 계획 |
| [사전등록 초안](preregistration.md) | 예측 대상, 간결한 기준모형, 세 연구 가설군, 동일 표본·비용·검증 |
| [승인 조건](approval-conditions.md) | 후속 데이터 작업과 결과 실행의 구별, 명시적 소유자 승인·독립 감사 |
| [기계 판독 초안](design.json) | 실행 비활성화, 예약 Study ID와 필수 게이트 |
| [메타데이터 감사](metadata-audit.json) | 기존 분류 파일의 관측 수·스키마 이상, 봉인 결과 SHA 검증 |
| [출처 목록](provenance.json) | 감사 시점의 main, 문서 Git blob, PR HEAD·파일 목록 |

핵심 판정은 **새 역사 결과 실행 불가**다. KR v4는 여전히
`DATA_FOUNDATION_INSUFFICIENT_V4`이며 US의 보존 분류도 전체 구간에 균일한
11-sector 패널이 아니다. 95% 분류율, 재현 가능한 결과, 합성 테스트 통과는
각각 PIT 적격성·투자 알파·실행 승인을 뜻하지 않는다.

Atlas Phase D #217은 이미 병합되어 한국 역사 탐색 종료가 유효하다. 이 설계는
종료를 해제하거나 봉인 산업 실험을 재실행하지 않는다. 기존 결과는 모두
outcome-exposed 개발 증거로만 사용한다. 신규 역사 검정도 새 Study ID·사전등록·
독립 감사·정확한 실행 묶음에 대한 소유자 승인 전에는 금지한다. 확증은
사전 기록한 새로운 미래 자료에서만 가능하다.

## 안전하게 확인하는 방법

저장소 루트에서 다음 두 명령은 합성 자료만 사용한다(표준 라이브러리만 필요).

```bash
python -m unittest research.industry_alpha_next_v1.test_contracts research.industry_alpha_next_v1.test_source_audit -v
python -m compileall -q research/industry_alpha_next_v1
```

기존 자료가 있는 완전한 checkout에서는 다음 명령으로 **메타데이터와 기존
봉인 파일의 SHA만** 감사한다. 가격, 미래 라벨, 모형을 만들지 않으며 원천을 수집하지 않는다.

```bash
python -m research.industry_alpha_next_v1.source_audit > /tmp/industry-alpha-metadata-audit.json
```

이번 환경에서는 Git 프록시 연결이 되지 않아 GitHub 커넥터로 고정된 main의
필요 파일만 읽었다. 기존 연구 실행기, 전체 pytest, seed/production 파이프라인은
실행하지 않았다. 전체 pytest는 기존 봉인 결과 재계산 테스트를 포함할 수 있어
이번 재실행 금지 범위와 충돌한다. 기존 CI/workflow도 변경하지 않는다.

검증: 합성 unittest 18개와 새 디렉터리 compileall 통과, metadata audit의 두
봉인 SHA 및 세 분류 입력 SHA 통과, upstream 이상 snapshot CSV SHA/502행/123라벨
독립 대조, 36슬롯 유일성·문서 상대링크·#286/#287 변경 경로 교집합0 확인.
로컬 ruff/pytest 실행 파일은 설치되지 않아 ruff 및 전체 저장소 검사는 미실행이다.
기존 자동 CI의 상태는 별도로 확인하며 로컬 합성 통과로 대체하지 않는다.

`contracts.py`는 미래 구현의 작은 합성 수용 기준이다. 실제 데이터 연결,
학습기, 예측 발행기, 결과 실행 CLI, workflow, 승인 우회 플래그는 제공하지 않는다.
