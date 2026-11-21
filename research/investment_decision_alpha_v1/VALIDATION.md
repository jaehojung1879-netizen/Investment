# 입력 계보·재실행·검증

## 입력

| 입력 | 해시·버전 | 위치 |
|---|---|---|
| 미국 가격 | `close.pkl` sha256 `17b4dbcc…74b6c7e`(#343~#354와 같음) | git 밖 |
| 미국 특징(#354가 읽은 원본) | `features.pkl` sha256 `49062dba…8bef8c0ac9` | git 밖 |
| 미국 특징(#353 정정 사본) | sha256 `05465a82…f55d55fc5`. 원본에서 `corrected-caps.csv` 943행의 `marketCap`만 교체 | git 밖(`lineage_353_354`가 생성) |
| #353 정정 파일 | `research/kr_us_public_buys_v1/results/WAT/corrected-caps.csv` sha256 `90876398…` | git |
| 미국 SIC | data.sec.gov 제출 메타데이터, 782개 발행사, 실패 0, 수집 2026-11-21. 일반 User-Agent `research audit`, 초당 4회 이하 | `inputs/us-sic.csv` |
| 미국 발표 시각 | #354의 8-K Item 2.02(`us-events.pkl`) | git 밖(원본 표는 #354 `inputs/`) |
| 한국 가격·S2 책 | #346·#354와 같은 `RC.setup`(OCI 정정) | git 밖 |
| 한국 재무·잠정실적 | #354와 같은 DART 기록·`kr-events.pkl` | git 밖 |

## 재실행

```
S=<git 밖 비공개 폴더: data/, us/, ee/ 를 담은 #354 scratch 구조>
python -m research.investment_decision_alpha_v1.lineage_353_354 --private $S --work $S/corr      # 정정 사본 + #354 미국 재계산(약 25분)
python -m research.investment_decision_alpha_v1.collect_us_sic --private $S --out research/investment_decision_alpha_v1/inputs
python -m research.investment_decision_alpha_v1.s1_industry_cycle --private $S/corr                  # 약 25분(무작위 대조 200회 포함)
python -m research.investment_decision_alpha_v1.s2_entry_timing --market us --private $S/corr --events $S/ee
python -m research.investment_decision_alpha_v1.s2_entry_timing --market kr --private $S --events $S/ee
python -m research.investment_decision_alpha_v1.s3_trim --private $S/corr
python -m research.investment_decision_alpha_v1.kr_semis_case --private $S
python -m research.investment_decision_alpha_v1.current_state --private $S/corr
python -m research.investment_decision_alpha_v1.judge
```

`lineage_353_354.compare()`가 `results/lineage-353-354-impact.json`을 쓴다.

## 검증

- **계보**
  - #354 입력에서 #353 정정 943행이 모두 발견됐고, 943행 모두 정정 전 값이었다.
  - 정정 사본 재실행은 별도 폴더에만 썼다. #354의 커밋된 결과와 `judgement.json`은 바꾸지 않았다(`git diff`로 확인).
- **재현**
  - 정정 전 입력으로 #354의 L26 장부를 다시 계산하면, BASE −2.83, SUE_TOP −0.52, PC_SUE −2.81이 원 값과 같다.
  - 정정으로 바뀌는 것은 시총 비중을 쓰는 책뿐이다.
- **시점**
  - 산업 상태는 판단일 d에 공개된 재무 특징만 쓴다(#343 특징 파일의 `sharesVisibleDay`·`reportAgeDays` 규칙).
  - 수익은 d 다음 세션부터 잰다.
  - 발표 반응일은 미국 8-K 접수 시각(뉴욕 16:00 이후는 다음 세션), 한국은 접수일 다음 세션이다.
- **테스트**: `tests/test_investment_decision_alpha_v1.py` 7건.
  - SIC3/SIC2 묶음 규칙
  - 신규 편입 사건 추출
  - 대기 매수의 가치 동일성과 비용
  - 발표가 없는 사건
  - 고점·저점 판정
  - 축소 시뮬레이션
- **저장소 검사**: `ruff check .`, `python -m compileall pipeline`, 전체 `pytest -q`, 시드 생성, `validate --allow-seed`. 결과는 PR 본문과 CI를 따른다.
- **git에 넣지 않은 것**: 종목별 가격·수익률(`kr-semis-case-quarters-with-returns.csv`는 비공개 폴더에만 있다)
