# 입력 계보·재실행·검증

## 입력

| 입력 | 버전·해시 | 저장 위치 |
|---|---|---|
| 미국 가격·특성·S&P 500 PIT 구성 | replay-v16 at signal-history `704d7db6`(#346·#347과 같음). `close.pkl` sha256 앞 16자리 `17b4dbcc534caa31` | git 밖(비공개) |
| 미국 분기 실적 | Finnhub financials-reported 원 제출(`filings.pkl` sha256 앞 16자리 `f0b1254ac5e73558`) | git 밖 |
| 미국 실적 발표 시각 | data.sec.gov 제출 목록 8-K Item 2.02, 수집 2026-11-21. 원본 JSON sha256 `45e80612f59eb9df…` | 압축 표 `inputs/us-8k-item202.csv.gz`(57,892행) |
| 한국 가격·유니버스·S2 | signal-history `4ea107ed` KR 입력 + OCI 정정(#346과 같음, `sg1-random-setup.pkl`) | git 밖 |
| 한국 분기 실적 | `kr-candidate-merged` DART 기록(연도별 jsonl.gz 묶음 해시 `c7aa2d0e…`) | git 밖 |
| 한국 잠정실적 공시 | DART `list.json`(공시유형 I), 2015-01-01 ~ 2026-11-21, 호출 3,031, 오류 0. 원본 JSON sha256 `757f24a0bcee0f59…` | 압축 표 `inputs/kr-prelim-disclosures.csv.gz`(11,200행) |

- 키(`DART_API_KEY`)는 환경 변수에서만 읽고 기록하지 않았다.
- SEC 요청은 일반 User-Agent `research audit`, 초당 4회 이하로 보냈다.

## 재실행

```
S=<git 밖 비공개 폴더: data/, us/ 를 담은 #346 scratch 구조>
python -m research.kr_us_earnings_expectations_v1.collect_us_8k --private $S --out $S/ee
python -m research.kr_us_earnings_expectations_v1.collect_kr_prelim --private $S --out $S/ee     # DART_API_KEY 필요
python -m research.kr_us_earnings_expectations_v1.analysis --market us --private $S --out research/kr_us_earnings_expectations_v1/results
python -m research.kr_us_earnings_expectations_v1.analysis --market kr --private $S --out research/kr_us_earnings_expectations_v1/results
python -m research.kr_us_earnings_expectations_v1.judge
```

## 검증

- **재현**
  - 미국 고정 칵테일 L26 −3.43%p/년, U1 L26 +0.33%p/년: 6차·#346 값과 같다.
  - 한국 S2 L26 −0.39%p/년, MDD −48.5%: #346 값과 같다.
- **시점**
  - 신호는 정기보고서 공개일 < 판단일인 사건만 쓴다(`analysis.fresh_sue`). 같은 날 공개분은 쓰지 않는다(테스트로 고정).
  - 같은 분기는 가장 먼저 공개된 제출만 쓴다.
  - 미국 발표는 뉴욕 16:00 이후 접수면 다음 날부터 반응한다(테스트로 고정).
  - 한국 발표는 기재정정을 뺀 원본 중 분기말 이후 정기보고서 이전 첫 공시다(테스트로 고정).
- **테스트**: `tests/test_kr_us_earnings_expectations_v1.py` 6건
- **저장소 검사**: `ruff check .`, 대상 테스트, `compileall pipeline`, 시드 생성, `validate --allow-seed`. 결과는 PR 본문과 CI를 따른다.
- **바꾸지 않은 것**: 기존 전향 기록·운영 전략·봉인 결과
