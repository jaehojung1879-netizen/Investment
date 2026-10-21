# PR #263 독립 수집기 감사

감사 대상: `5d10175aff57815aab143a7f1aa29c03ee855250`, 기존 브랜치
`claude/kr-collector-unpublished-session-guard`. #262 비교 기준:
`69015bf561bdd301a51488a514ab271e505649bc`.

실제 KRX/vendor API 호출, 기존 수집 자료 열람·수정·재수집, 역사 실험,
성과·outcome 접근, main 병합은 하지 않았다. Git으로 코드와 계약만 확인하고,
모든 실행 검증은 임시 디렉터리의 합성 응답·합성 가격 자료를 사용한다.

## 발견과 수정

| 우선순위 | 기존 동작과 합성 증거 | 수정 후 불변조건 |
|---|---|---|
| P1 | as-of 2026-10-19에 정상 개장일 10-15·10-14·09-01의 빈 응답이 `closed`와 done으로 확정된다. 3일 경과 여부는 휴장 증거가 아니다. | 기존 `replay_calendar.sessions(..., 'KR')`의 고정 달력으로 확인한 비거래일만 완료. 개장일 빈 응답은 나이에 관계없이 pending. |
| P1 | 월별 membership용 `served_date`는 첫 날짜만 읽고 없으면 요청일로 fallback한다. 다른 날짜 응답도 요청일 done을 생성한다. | daily 경계에서 모든 원응답 행의 BAS_DD/TRD_DD가 명시적으로 요청일과 일치해야 한다. 누락·혼합·상충 날짜는 중단, 저장·done 없음. |
| P1 | 일반 parser가 모든 행을 버리면 비어 있는 결과가 되고, 일부 행만 버려도 날짜를 완료할 수 있다. | 원행/파싱 행 개수 불일치, 중복, 잘못된 close는 중단. retained 행이 하나도 없으면 완료 근거가 없어 pending. |
| P1 | 손상된 done 파일을 빈 집합으로 읽어 재수집을 허용한다. shard/checkpoint 직접 쓰기는 중간 실패 시 이전 파일을 손상시킬 수 있다. | 손상·잘못된 형식·중복 날짜 checkpoint는 보존하고 중단. 동일 filesystem 임시 파일에 기존 canonical writer로 쓴 뒤 atomic replace. 모든 shard 기록 뒤에만 checkpoint 갱신. |
| P1 | 기존 done은 해당 개장일의 저장 행이 없어도 무조건 신뢰한다. | 요청 범위의 기존 done 개장일에 대응하는 저장 행이 없으면 `DONE_WITHOUT_SESSION_ROWS`로 중단. 기존 done 삭제·자료 수선·재수집은 하지 않는다. |
| P2 | 중복 target이 같은 실행의 pending에 중복되고, refused 요청이 calls에 안 잡힌다. pacing 이후에는 시간 예산을 다시 검사하지 않는다. | target 중복 제거, 거절도 시도 1회로 계수, pacing 뒤 시간 예산 재검사. 즉시 재시도 없이 다음 실행에서 미완료 날짜만 재시도. |

수정 전 회귀 재현은 **4 failed / 2 passed**였다. 정상 개장일의 오래된 빈 응답
3건과 다른 served date 1건이 실패했다. 기존 전체 collector 테스트 28개는
통과했지만 이 결함을 막지 못했다. 특히 기존 '오래된 빈 응답' 사례인
2026-10-05는 고정 달력상 휴장일이어서 정상 개장일의 음성 대조군이 아니었다.

`tests/test_krx_price_collection.py`의 기존 기대값 중 잘못된 served date의
자동 수용과 손상 checkpoint 초기화는 더 강한 거절·원본 보존 assertion으로
바꿨다. 연도별 shard 사례의 2013-12-31은 실제 고정 달력상 연말 휴장이므로
정상 개장일 2013-12-30으로 바꿔 같은 shard 분할 속성을 검증한다.

## 거래일·재시도·done 조건

- 주말, 공휴일, 고정 달력의 2026-07-17 보정, 연말 휴장을 외부 요청 없이
  분류한다. 달력 범위/근거가 불명확하면 평일 추정으로 대체하지 않고 중단한다.
- 미래 날짜는 요청·완료하지 않는다. 기본 as-of 날짜는 KST다. 이것은
  prospective 영수증의 세션 최종성·관측 시각 인증을 대신하지 않는다.
- 빈 개장일을 반복 실행해도 done에 넣지 않는다. 올바른 응답이 도착하면
  정확히 한 번 저장·완료하고, 이후 재실행은 API 요청과 파일 변경이 없다.
- 새 done은 **달력으로 확인한 휴장일 또는 요청일과 동일한 날짜의 검증된
  retained 행이 저장된 개장일**의 합집합이다. 실패한 저장 뒤에는 전진하지 않는다.
- 한 날짜의 빈 응답은 다른 독립 날짜 수집을 막지 않는다. call/time 예산은
  유지하며, 반복 target은 예산을 중복 소모하지 않는다.
- 전부 빈 개장일인 CLI 실행은 성공으로 보고하지 않는다. 일부 정상 수집 뒤
  중단된 경우에는 기존의 유용한 partial 자료 보존 방식을 유지하고 remaining과
  stopped/provisional을 명시한다. 프로세스 성공은 입력 전체 준비도 인증이 아니다.

## #262 KR A0 입력 무결성과의 연결

#262는 source commit `1bf68f59cffa20239977e2cfaa0f35a07d0ec884`, manifest
`f0781292f508a123c234ded6d28aa8e84a0dc3cc29500e14989dc0b68f53b4d2`를 고정한다.
`rp1_inspect_kr_a0.load_inputs`는 그 commit의 `ledger/prices/kr/krx-prices-*.jsonl.gz`를
읽고, `observations`는 공유 `TickerBars.quote/features_at`의 신호일 시가총액,
20-session 거래 가능성, 60-session 거래대금 입력을 H2 eligibility에 전달한다.
이 경로를 소스에서 확인했으며 #262 실행기나 고정 자료는 실행·열람하지 않았다.

합성 150-session 자료로 같은 공유 함수를 검증한다:

1. 정상 자료는 최근 20세션 거래·60세션 중앙 거래대금 20억원으로 적격이다.
2. 신호일 행을 빼면 quote/priceAsOf가 없고 `PRICE_NOT_ON_SIGNAL_DATE` 및
   `NOT_TRADED_EVERY_SESSION_20`로 보류된다.
3. 최근 20세션 안의 중간 행 하나를 빼면 거래 세션 수가 19, 60-session
   거래대금은 `None`·`GAP_OR_SUSPENSION_IN_WINDOW`이며 적격에서 제외된다.
   결측을 0이나 '정상 휴장'으로 바꾸지 않는다.

따라서 false done은 단순한 retry 문제를 넘어 KR A0의 적격 분모,
A-H1~H3 측정 가능성·사건 수·산업 peer 집합·층 구성에 영향을 줄 수 있다.
H3에는 업종 최소 적격 수 관문도 있어 한 종목 결측이 peer 집합을 보류시킬 수 있다.
영향의 방향·크기는 실제 자료를 감사하지 않고 정량 주장할 수 없다.
H2/H3의 trailing 126-session 입력은 별도 manifest 가격 패널도 사용하므로,
raw-bar 결측이 모든 과거수익 입력을 똑같이 훼손한다고 단정하지 않는다.

**#263의 수정은 #262의 기존 고정 입력이나 결과를 소급 수정·인증하지 않는다.**
해시 일치는 '그 바이트를 읽었다'는 증거이며 거래일 누락이 없다는 증거는 아니다.
이번 재현이 #262 고정 자료의 실제 오류를 입증한 것도 아니다. 기존 소스의
해당 누락 여부는 별도 승인된 읽기 전용 입력 완전성 감사가 필요하다.
새 자료·수선·재수집이 필요해도 기존 pin/결과를 덮어쓰지 말고 별도 검토한다.
KR A1 폐쇄, A0 임계값, MDE 미해결, A2 실제 기록 승인 관문은 그대로다.

## 경계와 남은 한계

봉인된 `krx_prices`, `krx_universe`, `replay_calendar`, A0 코드·사양·결과와
기존 workflow는 변경하지 않는다. 수정은 비봉인 daily collector와 합성 테스트뿐이다.
동시 writer 조정, 실제 endpoint의 전체 행 누락, keep 집합 확대에 대한 과거
완전성, 이미 잘못 기록된 source/date 및 실제 source 권리는 이번 감사로
인증하지 않는다. 기존 done 파일은 keep 집합의 hash를 기록하지 않으므로,
done 존재만으로 전체 A0 입력이나 확대된 유니버스의 수집 완료를 주장하면 안 된다.
이 감사는 수집 스케줄·외부 호출·데이터 수선을 활성화하는 승인이 아니다.

## 후속 수정: 비정상 수치와 단면 완전성 (감사 댓글 6318346502)

**Finding A — 비정상 수치 저장.** 봉인된 `parse_number`는 `"NaN"`·`"Infinity"`를
float로 돌려주고 `historical_store.encode`는 이를 비표준 JSON 토큰으로 쓴다.
`daily_bars`는 종가만 검사했으므로 시가·고가·저가·거래량·상장주식수의 NaN·무한대·
음수가 저장되고 그 날짜가 `done`이 되었다. 합성 응답 13가지로 재현했다.
수정은 수집기 경계(`bar_value_errors`)에서만 하며 봉인 파서·writer는 그대로다.

- 거부: 비유한값, 음수·소수 거래량, 0 이하·소수 상장주식수, 음수 가격,
  거래 행(거래량 > 0)의 0 가격·OHLC 범위 위반, 거래량 미기재 행의 0 가격.
- 허용: 거래량 0인 거래정지 행의 0 시가·고가·저가(KRX가 정지 종목도 직전
  종가로 싣는다), KRX가 비워 둔 필드는 None(0으로 대체하지 않음).
- 응답 안의 한 종목이라도 위반하면(유지 대상 밖이어도) 그날 전체를 거부한다.
  저장 없음, `done` 미진행, 실행 중단.
- 저장 직전 `allow_nan=False` 직렬화 검사를 한 번 더 둔다.

**Finding B — 단면 완전성.** `done`은 "유효 응답에서 유지 행이 하나 이상
저장됨"만 뜻한다. `done`의 의미는 바꾸지 않았다(상장폐지 종목을 영구 재요청하게
되므로). 대신 수집 결과와 `--diagnose`가 각 날짜를 그 이전 최신 멤버십
스냅샷과 비교한다. 빠진 회원이 있으면 `UNRESOLVED_PIT_MEMBERS_ABSENT`,
이전 스냅샷이 없으면 `UNRESOLVED_NO_PRIOR_PIT_SNAPSHOT`이다. 다음 스냅샷에도
있는 회원은 따로 보고한다. 최소 종목 수 기준이나 0 대체는 없다.
`COMPLETE_AGAINST_PRIOR_PIT_SNAPSHOT`은 스냅샷 이후 신규 상장 종목까지
증명하지 않는다. `--diagnose`는 API 키·호출·쓰기 없이 기존 저장소의
done/저장 행/스냅샷 정합성, 휴장일 행, 저장된 비유한값을 보고한다.

**남은 한계.** 실제 KRX 응답에서 거래정지 행의 시가 표기(0 또는 "-")는 확인하지
않았다. 실제 `signal-history` 저장소에 `--diagnose`를 돌리는 것은 별도 승인이
필요하다. 기존 저장 행은 수정하지 않는다.

## 재현 검증

```sh
.venv/bin/python -m pytest -q tests/test_collect_krx_daily_prices.py tests/test_krx_price_collection.py tests/test_krx_prices.py tests/test_krx_universe.py tests/test_krx_universe_collection.py
.venv/bin/ruff check .
.venv/bin/python -m compileall -q pipeline
.venv/bin/python scripts/make_seed.py
.venv/bin/python -m pipeline.validate data/site-data.json --allow-seed
```

최종 focused 결과: **170 passed (36.86초)**. Ruff, pipeline compileall, seed 생성·검증과
pipeline import/script compile 검사도 통과했다.

위 focused suite는 모든 API transport를 합성 대체하고, I/O 실패·checkpoint
원본 보존·중단 후 재개·중복 요청·현재 KR A0 공유 입력 관문의 결측 처리를 검증한다.
전체 연구 suite나 실제 #262 A0 측정 재실행, GitHub CI 성공은 이 focused 결과와
구분한다. 독립 감사의 발견·수정은 과학적 승인이나 main 병합 승인이 아니다.
