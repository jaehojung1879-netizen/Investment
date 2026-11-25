# next_alpha_source_admission_v1 — 신규 정보축 원천 적격성 실측 (2026-11-25)

**증거 등급:** SOURCE_ADMISSION_ONLY. 주가·수익률·IC·NAV·미래 라벨은 읽거나 계산하지 않았다. 봉인 파일, 운영 전략, 기존 연구, 다른 세션의 PR 브랜치는 수정하지 않았다.
측정값 전체: `results/source-admission-summary.json`. 원문 바이트는 git에 넣지 않았고 SHA-256만 기록했다.

## 재사용한 기존 자산
| 연구 | 재사용 | 수정 여부 |
|---|---|---|
| D 회계 신뢰성 | #375 `bulk_402.extract` (HEAD `2c5336b5`), #354 Item 2.02 카탈로그 (blob `e755d352`, 757 CIK) | 무수정 실행 |
| A 가이던스 | #372 `inspect_guidance.revisions` (HEAD `60ade4b4`) | 무수정 호출 |
| C 5% 보유목적 | #373 `source_probe.py` (HEAD `744badca`), signal-history `ledger/dart-ownership-events` (commit `5fd1984d`) | 무수정. 응답 캐시 래퍼만 추가 |
| B 반도체 | #371 N2 담당 세션의 IIP·BOK 산출물 | 재수집하지 않음 |

## 판정
| 후보 | 실측 표본 | 독립 단위 / MDE(SD) | 판정 |
|---|---|---|---|
| A 미국 경영진 가이던스 | Item 2.02 실적발표 2014–2026: 35,090건, 750개사. 층화 표본 319건 중 64.6%에 수치 가이던스. 무작위 30개사 패널(2022–25)에서 29개사 중 26개사가 가이던스 제시 | 52개 분기 0.39 / 150 issuer-year 0.23 | **SOURCE_ONLY**. 원천·PIT 시각은 충분함. 동일 대상 자동 연결은 재현율이 낮음(26개사 중 6개사, 25건). 수작업 대조 결과 정확. 하향을 스스로 표기한 사례는 0건(LOWER 0, UPDATE 34)이라 기업 자체 표기에 의존할 수 없음. 개정 시점은 모두 실적 서프라이즈(#354)와 같은 접수 시각 |
| B 반도체 실물 사이클 | ECOS 수출금액·물가·물량지수(반도체, 2013-01~2026-10, 현재 수정값). 금액 YoY 분산의 87.7%가 가격, 12.4%가 물량. 생산·고객사 실적발표 641건: META CAPEX 가이던스 27건, MU 30건 | 2014년 이후 가격 상승 전환 4회 → 1.40 | **BLOCKED**. 독립 사이클 수가 부족함. 가격 축은 기존 수출액과 대부분 중복됨. 빈티지가 없음. DRAMeXchange 계약가 이력은 유료이며 현물가는 전향 수집만 가능 |
| C 한국 5% 보유목적 변경 | 기존 원장 2,496건, 228개사(2024-09-24~2026-09-23). 보유목적 변경 61건 중 57건이 국민연금이며 모두 단순↔일반 전환. 경영권 영향 전환 0건 | 18개월 0.66 | **SOURCE_ONLY**(활동주의 축은 사건 0건). majorstock은 약 2년치만 제공. #373 프로브는 D001과 D002가 동일 목록을 반환하는 결함이 있음 |
| D 미국 회계 신뢰성 (Item 4.02) | 757개사 제출목록 1,869페이지 전수(누락 0). 4.02 공시 219건, 151개사. 2004–08년에 64%가 몰려 있고 2014년 이후는 44건(39개사). 365일 에피소드 182건, 2014년 이후 40건. 1년 내 10-K/A·10-Q/A 133/182(중앙값 17일) | 2014년 이후 40건 0.44 | **SOURCE_ONLY**. 원천은 완전함. 2014년 이후 대형주 사건 밀도가 낮아 검정력이 부족함. 영향 항목 자동 분류는 재현율 5/5, 과포함 |

PASS_TO_PREREG: **0개**. REPACKAGED_STOP: 해당 없음(B의 가격 축은 기존 수출액과 상당 부분 중복되는 것으로 측정됨).

## 재현
SEC 요청에는 선언된 User-Agent를 쓰고 10 req/s 미만으로 유지했다. DART는 승인된 범위(목록 10건, 원문 10건) 안에서만 호출했다.
```bash
git show a45f12760a3d27ad09fcfdfb1266308ae59b9e1d:research/kr_us_earnings_expectations_v1/inputs/us-8k-item202.csv.gz > W/us-8k-item202.csv.gz
git show 2c5336b5f076aa2ef2a934fca23e5d51607434d2:research/us_nonreliance_source_pilot_v1/bulk_402.py > tools/bulk_402_375.py
git show 60ade4b49dd8963649ccbd9bdfb635ac15489cd7:research/guidance_source_pilot_v1/inspect_guidance.py > tools/inspect_guidance_372.py
git show 744badca6008ee3031942396c39b668fd71f6ca6:research/new_information_g0_v1/source_probe.py > tools/source_probe_373.py
python tools/fetch_submissions.py W/us-8k-item202.csv.gz W/submissions.zip
python tools/bulk_402_375.py W/us-8k-item202.csv.gz W/submissions.zip --start 2004-08-23 --through 2026-11-21
```
직접 구성한 ZIP의 SHA-256은 `517817686cdd761b…`이다. 페이지별 해시는 `results/sec-submissions-page-manifest.json.gz`에 있다. SEC 원본은 호출 시점마다 갱신되므로, 같은 날 다시 받아야 같은 해시가 나온다.
