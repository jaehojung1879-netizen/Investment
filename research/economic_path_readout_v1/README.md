# Economic path readout v1 — saved NAVs only

가격 수집·특징 탐색·학습·선정·전략 재실행 없이 저장 NAV만 읽는다. 원본과 봉인 결과는 수정하지 않는다. 종목 수의 목표나 상한을 설정하지 않으며, ETF 기본 정책을 새로운 최적화 결론으로 바꾸지 않는다. 모든 투자 적격/승격 판정은 `INSUFFICIENT_SOURCE_EVIDENCE_NO_PROMOTION`이다.

## 재현

저장소 루트에서 Python 3.12, exchange_calendars **4.11.1**(원 source 달력) 환경 사용. numpy/pandas는 기존 calendar 의존성뿐이며 새 가격·모델은 읽지 않는다. #286의 고정 Git 객체가 없을 때만 `git fetch origin 97aa2cfe2cabace05796f9179f2711cf83698d42`로 원래 결과 커밋을 확보한다. 자동 수집은 없다.

```sh
python -m research.economic_path_readout_v1.cli --repo . --out research/economic_path_readout_v1/results.json
python -m pytest -q research/economic_path_readout_v1/test_readout.py
(cd research/economic_path_readout_v1 && sha256sum -c SHA256SUMS)
```

출력은 이 독립 디렉터리 또는 `/tmp`로만 제한된다. 원 source/producer/ledger와 입력 파일 덮어쓰기는 거부한다. `results.json`은 요약, `results.windows.json.gz`는 모든 시작일·목표일·실제 종료일·상태·기간 수익이다. `source-pins.json`은 원 Git SHA와 39개 blob 해시, `readout-plan.json`은 회계/표본 규약이다.

## 원천·표본·기준

- A: main `37f8cbf6b1c066f6b3c65235953648d17ebf2f69`, `docs/weekly-decision/weekly-passive-first-v1-replay-corrected-benchmark.json`; 양 지역 각 경로 **715개 주간 관측치**. C1/C2는 이 파일의 CHAMPION/잔여 ETF 기술 경로이며 Market C1 정식 연구와 다르다. `studyId`, `sourceStudyId`, 원 `strategyId`, upstream content digest를 함께 기록한다.
- A는 **2013-01-11~2026-09-14** 첫/마지막 저장 관측치에서 각각 원금1로 재기준화한다. 원 replay 시작 2013-01-07에 NAV1을 덧붙이지 않으므로 원 headline CAGR과 다르다. NAV는 소수6자리 반올림, 끝의 짧은 주와 휴일 간격을 포함한다. 원 일별 MDD를 이 주간 표로 재인증하지 않는다.
- KR source status `DEFINITION_INTERNAL_REPLAY_V16`; US `SURVIVORSHIP_BIASED_PARTIAL`. **US도 KRW**이며 FX 포함 SPY 경로다. USD 비교나 QQQ 경로는 이 자료에 없고 UNAVAILABLE이다. `headlineEligible=true`는 원천/총수익 적격성 증명이 아니다.
- B: #286 `97aa2cfe2cabace05796f9179f2711cf83698d42`, historical-alpha-discovery-v1의 spec/summary/coverage/원 manifest와 complete NAV CSV. 96개 종목-vs-ETF 조합 중 **6개만 완전 경로**, 90개는 차단한다. 단독 block들을 이어 NAV를 만들지 않는다. source `from/through`, 관측수, 원 manifest 해시를 검사한다.
- B의 EX_POST_CONTINUING_NAME_CONDITIONAL은 종결22종목 및 006800의 사후 배제를 계승한다. PIT_WITH_UNRESOLVED_PATHS_BLOCKED도 완전 주주 총수익 인증이 아니다. 종목 부분 배당/분할 기준과 ETF gross 분배금의 불균형, 산업·PIT·종결 경제성 한계는 그대로 유지한다. 소스의 evaluation 명칭은 독립 OOS 선언이 아니다.
- `NET_ALREADY_CHARGED`: 원본 거래비용이 반영된 NAV에 비용을 다시 빼지 않는다. 배당의 gross는 거래비용 전 NAV라는 뜻이 아니다. B의1x/2x는 이미 존재하는 각각의 source 경로이고 추가 비용 stress를 NAV에서 역산한 것이 아니다. 투자자 배당세, 정밀 슬리피지, 3x 비용, 회전율, 선정 알파는 여기서 계산하지 않는다.

## 실제 결과

단위: 수익/CAGR/MDD는 %, 차이는 %p. MDD는 **관측 빈도** 기준이다. 아래 `B` 표기는 원 analysis window/sample/original horizon/cost scenario를 줄였으며 완전 ID/모든 source 한계는 JSON에 있다.

| 비교 | 후보 CAGR | ETF CAGR | 차이 %p | 후보 MDD | ETF MDD | 달력6M 평균 초과 %p | 달력12M 평균 초과 %p |
|---|---:|---:|---:|---:|---:|---:|---:|
| A/KR/C1-P0 | 10.5261 | 12.6144 | -2.0883 | -17.0446 | -34.2757 | -3.1018 | -5.9468 |
| A/KR/C2-P0 | 14.4326 | 12.6144 | +1.8181 | -27.9568 | -34.2757 | -0.5193 | -0.8804 |
| A/KR/P1-P0 | 12.5009 | 12.6144 | -0.1135 | -34.2757 | -34.2757 | -0.0774 | -0.2470 |
| A/US/C1-P0 | 7.2288 | 16.7064 | -9.4776 | -23.1345 | -28.5506 | -4.6898 | -9.9011 |
| A/US/C2-P0 | 12.9877 | 16.7064 | -3.7187 | -32.4759 | -28.5506 | -1.7829 | -3.9478 |
| A/US/P1-P0 | 16.7064 | 16.7064 | +0.0000 | -28.5506 | -28.5506 | +0.0000 | +0.0000 |
| B/EVAL/PIT-tag/원H252/1X/OVERNIGHT | 28.2808 | 36.4532 | -8.1724 | -43.0345 | -34.3280 | +0.2060 | +4.5387 |
| B/EVAL/PIT-tag/원H252/2X/OVERNIGHT | 27.7461 | 36.4023 | -8.6563 | -43.2682 | -34.3280 | -0.0248 | +4.0208 |
| B/DEV/조건부생존/원H126/1X/OVERNIGHT | -1.3358 | 3.2709 | -4.6067 | -52.3897 | -23.0992 | -1.0854 | -2.4679 |
| B/DEV/조건부생존/원H126/2X/OVERNIGHT | -2.3462 | 3.2288 | -5.5750 | -52.8940 | -23.0992 | -1.6058 | -3.5162 |
| B/EVAL/조건부생존/원H252/1X/OVERNIGHT | 27.1545 | 36.4532 | -9.2987 | -46.5269 | -34.3280 | -0.0794 | +3.4648 |
| B/EVAL/조건부생존/원H252/2X/OVERNIGHT | 26.6245 | 36.4023 | -9.7778 | -46.7732 | -34.3280 | -0.3093 | +2.9507 |

**서로 다른 측정의 결론을 혼동하지 않는다.** KR C2는 관측구간 전체 CAGR 차이가 +1.8181%p지만 6/12개월 rolling 평균 차이는 −0.5193/−0.8804%p다. 같은 시간 분할 후반 CAGR 차이는 −2.9206%p다. 이 세 측정은 가중·복리·시작/종료점이 달라 모순이 아니며 종목 선정 알파 분해도 아니다. US C2는 저장 관측치 기준 CAGR과 MDD 모두 SPY보다 나쁘다. B의 완전 OVERNIGHT 경로도 각 원 표본의 전체 CAGR이 ETF보다 낮다. 좋은 rolling 평균 하나로 funded compound 경로의 열위를 지우지 않는다.

## 기간 안정성 / 하위 꼬리 / 중첩

각 source 관측구간의 같은 경과시간 중간점을 두 half로 고정한다. 분할을 가로지르는 window는 `CROSSES_FIXED_TIME_SPLIT`; 누락으로 부르지 않는다. 전체·반기별 상세 MDD/회복/꼬리와 6/12M 모든 수치는 JSON에 보존한다. 위험회피 계수·최적 모델 선택 없이 CAGR/MDD/관측기간 lower-tail/관측기간 변동성의 부분 순서만 설명한다. OBSERVED_DOMINATES는 그 네 지표의 서술적 비교일 뿐, 투자 적격/모든 기간 우위/유의성 선언이 아니다.

| 비교 | 전반 CAGR 차이 %p | 후반 CAGR 차이 %p | 6M 승률 % | 6M 최하위5% 평균 차이 %p | 12M 승률 % | 12M 최하위5% 평균 차이 %p |
|---|---:|---:|---:|---:|---:|---:|
| A/KR/C1-P0 | +6.2191 | -11.0375 | 55.81 | -77.2411 | 54.53 | -155.2631 |
| A/KR/C2-P0 | +6.1083 | -2.9206 | 59.59 | -47.5337 | 61.18 | -95.7270 |
| A/KR/P1-P0 | +0.0000 | -0.2489 | 1.89 | -1.5961 | 0.60 | -3.7387 |
| A/US/C1-P0 | -7.2773 | -11.8017 | 26.45 | -21.6484 | 21.60 | -36.6246 |
| A/US/C2-P0 | -2.2962 | -5.3743 | 40.55 | -13.9204 | 32.33 | -23.5254 |
| A/US/P1-P0 | +0.0000 | +0.0000 | 0.00 | +0.0000 | 0.00 | +0.0000 |
| B/EVAL/PIT-tag/원H252/1X/OVERNIGHT | +9.9026 | -30.2086 | 50.90 | -57.5338 | 62.99 | -77.1848 |
| B/EVAL/PIT-tag/원H252/2X/OVERNIGHT | +9.3559 | -30.6249 | 50.25 | -57.5357 | 61.57 | -77.7745 |
| B/DEV/조건부생존/원H126/1X/OVERNIGHT | +3.3129 | -12.2474 | 44.41 | -23.1559 | 40.89 | -29.7109 |
| B/DEV/조건부생존/원H126/2X/OVERNIGHT | +2.3262 | -13.1960 | 42.59 | -23.5320 | 39.84 | -30.5119 |
| B/EVAL/조건부생존/원H252/1X/OVERNIGHT | +10.2453 | -32.8958 | 49.61 | -57.5338 | 56.93 | -79.5702 |
| B/EVAL/조건부생존/원H252/2X/OVERNIGHT | +9.6970 | -33.3024 | 48.82 | -57.5357 | 54.88 | -80.2140 |

A의 6M/12M measured rolling window는 **688/662개**, greedy disjoint 시간 구간은 **26/13개**다. 양 지역·다른 전략이 같은 날짜를 공유하므로 서로 독립 관측으로 합치지 않는다. Disjoint도 통계적 독립성 보장이 아니다. CI/p-value를 만들지 않는다.

B는 CSV 전체 날짜를 frozen XKRX source calendar(명시된2026 휴장3일 보정)와 일치 확인했다. 다음 H126/H252는 해당 NAV에서 **126/252 거래 세션 전이**이고, 원 book holding-horizon 라벨이나 주간26/52개를 바꿔 부른 것이 아니다. daily MDD는 이 원 경로의 일별 관측치만 설명한다.

| 일별 비교 | H126 평균 차이 %p | H126 승률 % | measured / disjoint | H252 평균 차이 %p | H252 승률 % | measured / disjoint |
|---|---:|---:|---:|---:|---:|---:|
| B/EVAL/PIT-tag/원H252/1X/OVERNIGHT | +0.5938 | 52.42 | 1387/12 | +5.2272 | 63.76 | 1261/6 |
| B/EVAL/PIT-tag/원H252/2X/OVERNIGHT | +0.3550 | 51.33 | 1387/12 | +4.6873 | 62.73 | 1261/6 |
| B/DEV/조건부생존/원H126/1X/OVERNIGHT | -1.1295 | 46.00 | 1261/11 | -2.5492 | 40.09 | 1135/5 |
| B/DEV/조건부생존/원H126/2X/OVERNIGHT | -1.6637 | 44.33 | 1261/11 | -3.6280 | 39.12 | 1135/5 |
| B/EVAL/조건부생존/원H252/1X/OVERNIGHT | +0.2599 | 50.47 | 1387/12 | +4.0302 | 57.49 | 1261/6 |
| B/EVAL/조건부생존/원H252/2X/OVERNIGHT | +0.0222 | 49.96 | 1387/12 | +3.4948 | 55.91 | 1261/6 |

### 누락과 만기 정산

A의12M 시작715개는 measured662, as-of 이후 미성숙46, 목표일은 지났으나 원 경로에 endpoint가 없는7개로 정산된다. H126/H252는 일별 원 경로 밖에 있는 만기를 임의 연장하지 않고 `BEYOND_STORED_PATH_MATURITY_UNKNOWN`로 남긴다. 비교 시작점 누락·안쪽 누락·불명확한 gap·endpoint 지연은 각각 상태로 남으며 inner join/보간/0 대체를 하지 않는다. 모든 window의 statusCounts 합은 scheduledOrigins와 같다.

90개 불완전 B 조합에는 예를 들어 FULL/PIT-tag/원H126/1x INTRADAY가 있다: 원24개 block 중 priced20, missing4이다. 유효한20개를 이어 완전 NAV나 전체 PIT 초과수익을 만들지 않았다. 각 차단 조합의 scheduled/priced/missing과 source 해시는 JSON에서 확인한다.

## Claude 입력 계약과 호출

`candidate`와 `benchmark` 각각 공통 필드: `region`(KR/US), `strategyId`, **`studyId`**, `currency`, `frequency`(DAILY/WEEKLY), `returnBasis`(불명이면 UNKNOWN), `costBasis`(NET_ALREADY_CHARGED/GROSS/UNKNOWN), `evidenceClass`, `sourceCommit`(40hex 또는 UNKNOWN), `hashes`(원 파일별 SHA256), `nav`(`[[ISO-date, positive NAV level], ...]`). 결측은 null이며 중복/역순/비정상 수치는 거부한다. 선택 `calendarPolicy`: XKRX/XNYS; 원 #286 자료에만 XKRX_DISCOVERY_V1. source certificate나 caller metadata가 새 투자 승인으로 바뀌지는 않는다.

CLI JSON 형식은 `{ "asOfDate": "2026-11-01", "candidate": <위 계약>, "benchmark": <같은 계약 + instrument> }`이다. benchmark.instrument는 KR069500.KS, USSPY 또는 **별도 QQQ**다. 승률은 엄격한 우위의 비율이고 동률은 별도다. US P1의 승률0%는 전부 동률이지 전부 패배가 아니다. 산술 반올림 오차만 1e-10%p 이내를 동률로 분류하며 경제성 허들이 아니다. 원금은 첫 저장 관측치에서 각각1로 normalize하므로 단위 원금 차이는 성과로 오인하지 않는다. 거래비용 반영 여부가 불명인 원본에 NET 표시를 임의 부여하지 않는다. JSON 입력 자체의 SHA도 보존한다.

```sh
python -m research.economic_path_readout_v1.cli --input /tmp/claude-nav-pair.json --out /tmp/claude-nav-readout.json
```

새 NAV가 아직 없으면 실제 A 입력으로 계약을 재현할 수 있다:

```python
import json
from pathlib import Path
from research.economic_path_readout_v1.adapters import GitSources, weekly_pairs
p = Path("research/economic_path_readout_v1/source-pins.json")
source = GitSources(Path("."), json.loads(p.read_text()))
_, candidate, benchmark = next(x for x in weekly_pairs(source) if x[0] == "A/KR/C2-P0")
Path("/tmp/claude-nav-pair.json").write_text(json.dumps({
    "asOfDate": "2026-11-01", "candidate": candidate, "benchmark": benchmark}))
```

API는 `core.compare(candidate, benchmark, as_of)`이며 요약과 window 상세를 반환하고 파일은 쓰지 않는다. 결정·종목·비중만 있는 #304 artifact는 NAV가 아니다. 나중에 actual date/nav 및 ETF 대응 경로와 비용·통화·원천 메타데이터가 생기면 같은 계약으로 연결한다. 현재 N을 고정하거나 비중을 수익률로 변환하지 않는다.

## 검증 범위

단위/%·비용 이중 차감·빈도/달력·날짜 누락/중복·미성숙/미관측·0 대체·반기 경계·회복·통화 혼합·원본 덮어쓰기 방지를 회귀 시험한다. 합성 시험 PASS는 실데이터 적격성이나 투자 성과 인증이 아니다. 결과표는 위 고정된 실제 Git blob에서 계산했다. independent review/required CI는 PR에서 별도 확인한다.

Result SHA256: `1267f449b4c2be285f95fa12bfb5f3e093ff05b81c805ff7830bea39343a7431`.

## #304 고정 HEAD 연결 검증 (한 차례, producer 수정 없음)

`d3783d00ff8217d555160e898c02386e63219279`의 실제 `nav-daily.csv.gz`와 부모 spec/result를 각각 해시로 고정하여 연결했다. 별도 `claude_connection.py`는 이 고정 artifact만 읽으며 producer 코드를 실행하지 않는다. source가 선언한 primary reference control인 KR ENTRY_IN_RANK/N5/ETF 한 쌍만 기술 검증했다. N5가 최적이거나 영구 상한이라는 뜻이 아니다. 원 CSV에 없는 studyId/hashes는 부모 artifact에서 부착하고, 명시된 NO_TRADE_NO_COST는 초기 ETF 보유·거래 없음이라는 source 규약에 한해 0 trading cost의 NET_ALREADY_CHARGED로 정규화하며 raw label도 보존한다.

원 공통 관측 격자의 후보 CAGR **13.3402%**, 자체 ETF **14.8660%**, 차이 **-1.5257%p**로 연결된다. 이는 A의 corrected ETF나 다른 N에 붙이거나 승격할 결과가 아니다.

- returnBasis는 `REPLAY_V16_CLOSE_WITH_FORWARD_ACCUMULATED_DISTRIBUTIONS_PARTIAL`이며 원 ETF headline14.8663%는 기존 replay-v16 값이다. A의 phase-C corrected headline12.507%와 다르다. 보정된 ETF를 후보의 잔여 자산이나 비교군에 조용히 이어 붙이지 않았다. 기존 결과를 고쳐 쓰지 않는다.
- 3,547개 공통 관측일에는 raw XKRX4.11.1의 지역 거래일이 아닌184개 날짜가 있다(예:2013-03-01,2013-06-06). 따라서 원 공통 격자의126개는 지역의126 거래 세션이라는 증명이 아니다. 이 연결에서 regional H126/H252와 dailyMdd 인증은 UNAVAILABLE이고, 원 격자 관측 MDD/CAGR만 서술한다.
- raw calendar가 missing으로 보는2026-05-25는 이미 알려진 KRX 휴장 보정이며 producer 데이터 결함으로 부르지 않는다. 가격 보간/0 대체 없이 source의 완전 공통 격자만 별도로 읽었다.
- 계약/해시/달력 차이와 수치 결과는 `claude-connection.json`에 있다. #304에 전달할 것은 기준·세션 의미의 명시 및 입력 envelope이며, source 봉인/과거 결과 재작성·새 실행 승인이 아니다.

기술 재현(같은 Git 객체가 로컬에 있을 때): `python -m research.economic_path_readout_v1.claude_connection`. A/B 기본 CLI 결과와 별도로 보존되며 새로운 모델·정책·과거 전략 실행을 하지 않는다.
