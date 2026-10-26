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

`contracts.py`는 미래 구현의 작은 합성 수용 기준이다.

## 측정 준비 코드 (2026-10-25 추가, `PREPARED_NOT_AUTHORIZED`)

| 파일 | 역할 |
| --- | --- |
| `study.py` | 연구 ID `industry-alpha-kr-next-v1`의 모든 수치·블록·소유자 결정 항목·결과 전 수정 이력. `spec_sha256()`로 고정 |
| `panel.py` | 봉인 산업 anatomy의 소속·동결 코호트·과거전용 특징·산업 타깃을 **import해 그대로** 호출. 월말 신호, 선도/후발 분할, 시장 문맥, 후발 바스켓 타깃, 코호트 제외 감사만 추가 |
| `evaluate.py` | 연도별 확장 walk-forward, label exit < 첫 test 신호 − 21세션, 훈련-only 대치·표준화, 날짜 중심화 타깃, 동일 행 paired 손실 차이, moving-block bootstrap, 36슬롯 Holm, 순차 게이트 |
| `inputs.py` | 모든 실입력을 git 객체에서 읽고 기존 pin과 대조: v4 소속(main), KRX 유니버스(`signal-history@4ea107ed`), replay-v16 가격, 수리된 회계(`fb6e8374`) |
| `input_check.py` | **라벨 없는** 실입력 검증. 개수·커버리지·달력 지원만 출력 |
| `run_study.py` | `synthetic` / `verify-inputs` / `execute`. `execute`는 승인 파일·코드·입력 해시·소유자 결정·main Actions·일회 잠금을 모두 통과해야 하며 지금은 거부 |

```bash
python -m research.industry_alpha_next_v1.run_study synthetic        # 합성 세계 전체 파이프라인
python -m research.industry_alpha_next_v1.run_study verify-inputs --output research/industry_alpha_next_v1/input-verification.json
python -m pytest -q research/industry_alpha_next_v1/
```

`verify-inputs`는 과거 가격으로 과거전용 특징을 만들지만 미래 수익을 계산하지 않는다. 결과는
`input-verification.json`(개수만)이며 승인 판단은 [approval-packet.md](approval-packet.md)에 있다.
테스트는 `verify-inputs`가 결과 함수에 들어가면 실패하도록 spy를 건다.

## 추론 보정과 종결 22종목 복구율 (2026-10-25 추가, 합성·원천 전용)

| 파일 | 역할 |
| --- | --- |
| `inference_calibration.py` | 등록 평가기 전체(`admit` → `oof_predictions` → `loss_differential`)를 KR 달력·H126/H252 중첩 라벨·결측이 있는 합성 산업 패널에 그대로 돌려, 등록 MBB(C0)와 사전 선언 대안 C1~C6의 제1종 오류·검정력을 잰다 |
| `inference-calibration-protocol.json` | 후보·DGP·효과 크기·seed·반복 수·판정 규칙을 정식 실행 **전에** 동결(digest `defdd9b1…`, 커밋 `a07d178`) |
| `inference-calibration-result.json` | 정식 실행 1회의 결과(16,800 replicates, seed 20261026) |
| `inference_mechanism_diagnostic.py` / `inference-mechanism-diagnostic.json` | 결과를 **본 뒤** 작성한 사후 진단(development seed). 동결 판정을 바꾸지 않는다 |
| `kr22_recovery.py` / `kr22-recovery.json` | 종결 22종목의 산업·종결 대가·배당 복구 현황을 커밋된 원천만으로 집계. 가격·결과·네트워크를 읽지 않는다 |

```bash
python -m research.industry_alpha_next_v1.inference_calibration critical-values
python -m research.industry_alpha_next_v1.inference_calibration formal --workers 4 --output /tmp/result.json   # 약 26분
python -m research.industry_alpha_next_v1.inference_mechanism_diagnostic --output /tmp/mech.json
python -m research.industry_alpha_next_v1.kr22_recovery --output /tmp/kr22.json
```

결과 해석과 다음 단계는 [approval-packet.md](approval-packet.md) §7에 있다.


## 원천 복구·수집 계획·경제성 설계 (2026-10-25~26 추가, 합성·원천 전용, 역사 결과 0)

| 파일 | 역할 |
| --- | --- |
| `kr22_source_recovery.py` / `kr22-source-recovery.json` | 승계 회사 상장주식수와 공시 신주 수를 대조한 실행 확인, 16종목 요청 목록 |
| `kr22_collection_plan.py` / `kr22-collection-plan.json` | 그 요청 목록을 digest로 고정한 수집 계획, 실패하면 닫는 수집기(DART 키 필요, 이 세션 미실행), 네트워크 없는 검증기, 산업·배당 진술 추출기 |
| `alternative_design.py` / `alternative-design-screen.json` | 적합 없는 달력시간 산업 순위 스프레드의 크기·검정력 스크린 |
| `inclusion_bound.py` / `inclusion-bound-screen.json` | 분류되지 않은 종결 종목을 버리지 않고 가장 불리한 산업에 넣는 포함 규칙: 실측 노출(구성원·시가총액만)과 합성 검정력 |
| `industry_economics.py` / `industry-economics-screen.json` | 롱온리 산업 기울기의 비용 차감 순능동, 시장·모멘텀 분해, 회전율·집중 |
| `industry-economics-prereg-draft.md` | 경제성 설계와 전향 독립 표본 사전등록 초안(미등록) |

```bash
python -m research.industry_alpha_next_v1.kr22_collection_plan build-plan     # 저장소 바이트만
python -m research.industry_alpha_next_v1.kr22_collection_plan verify --input <수집 디렉터리>
python -m research.industry_alpha_next_v1.inclusion_bound --output /tmp/bound.json        # 약 15분
python -m research.industry_alpha_next_v1.industry_economics --output /tmp/econ.json      # 약 4분
```

해석과 승인 필요사항은 [approval-packet.md](approval-packet.md) §8–§9에 있다.
