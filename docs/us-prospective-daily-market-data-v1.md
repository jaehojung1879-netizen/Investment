# US Prospective Daily Market Data Foundation v1

이 변경은 미국 일별 시장 데이터의 **격리 수집·불변 저장 기반**이다. 운영 스케줄이나 투자 판단에는 연결하지 않는다. 모델, 수익률, 미래 라벨, 기존 연구 등록·결과·실행 잠금은 다루지 않는다.

## 기준 상태와 재사용

착수 시 main `9086f5ead25c9d158b22e9230faa35868e7746d0`에서 PR #227 병합을 확인했다. 구현 중 PR #228 병합을 확인하여 최종 기준 main을 `21c8646d99b4bfe5bc65cc5136086679cae0b9d4`로 갱신했다. 다른 에이전트의 미병합 브랜치를 읽거나 의존하지 않았다.

기존 `ledger.yml`, `ledger.py`, KR 일별 가격·구성종목 수집기, US 구성종목·식별자 규칙, historical store 무결성 규칙을 검토했다. 읽기 전용 GitHub tree 조회에서 signal-history의 `ledger/prices`와 `ledger/universe`는 각각 `kr` 디렉터리만 포함했다. 이 관측은 고정 트리 시점의 디렉터리 메타데이터이며 과거 전체 데이터 가용성의 증명은 아니다. 신호·성과 레코드 내용은 조회하지 않았다.

| 기존 구성요소 | 재사용 방식 |
|---|---|
| `universe._us_symbol`, 최소 구성종목 수 | BRK.B 등 공급자 심볼 정규화와 불완전 목록 차단 |
| `datafeed.AS_TRADED_WITH_ACTIONS` | 동일 OHLCV·배당·분할 필드 계약 |
| pinned yfinance 0.2.65 | 동일 공급자, `auto_adjust=False`, `actions=True`; 오류는 숨기지 않음 |
| `price_adjustment.future_split_factor`, `ADJUSTMENT_VERSION` | 세션 **이후** 분할만으로 당시 가격·거래량 복원 |
| `market_dates.normalize_daily_index` | 뉴욕 현지 일별 날짜 보존 |
| `replay_calendar.sessions`, `CALENDAR_VERSION` | XNYS 휴일·DST·조기폐장과 독립적인 세션 검증 |
| `collector_outcomes` | 원문 오류와 거절 상태 분류 |
| `historical_store.encode/read_jsonl/MAX_SHARD_BYTES` | 기존 결정론적 gzip JSONL·48 MiB 상한 |

기존 historical-store의 갱신형 shard writer나 total-return을 생성하는 `fetch_prices(total_return=True)`는 이 저장 요구에 맞지 않으므로 호출하지 않는다. 새 저장 계층은 인코딩을 재사용하고 독점·원자 게시로 덮어쓰기를 방지한다. 운영·과학 코드, 공유 설정, 기존 워크플로는 수정하지 않는다.

## 실행과 인터페이스

```bash
python scripts/collect_us_daily_prices.py /tmp/us-market-stage \
  --max-calls 600 --max-minutes 15 --batch-size 40
# 최근 7개 완료 세션 안에서만 제한적 재확인 / 중단 후 재개
python scripts/collect_us_daily_prices.py /tmp/us-market-stage \
  --session 2026-10-09 --recheck
```

기본 대상은 마지막 완료 미국 세션 하나다. 완료는 XNYS 실제 폐장 시각 + 60분이며 DST·조기폐장을 포함한다. 지정 가능한 범위는 최근 완료 세션 7개뿐이다. 휴일은 거래소 달력으로 판단하며 빈 다운로드로 추정하지 않는다. 미완료 일별 봉, 중간 누락, 중복 날짜·열, 다른 통화·시간대·종목, 잘못된 OHLCV·기업행동은 거절한다.

출력 경로는 이 저장소 및 **모든 Git 체크아웃 밖**이어야 한다. signal-history 체크아웃으로 직접 실행할 수 없다. fixture는 별도 `-fixtures` namespace에 저장한다. 이 CLI는 실제 소스용이며 네트워크 없는 합성 검증은 주입 가능한 Python 인터페이스를 사용한다.

```python
from pipeline.us_daily_market_data import collect, ObservationStore
# MembershipResponse(raw CSV, source, source identity, UTC observation,
#                    source last-change time, explicit source kind)
# fetch(ticker, start, through) -> PriceResponse(frame, metadata, UTC acquisition)
manifest = collect(isolated_root, membership_response, fetch,
                   now=observation_utc, max_calls=600, max_seconds=900)
# 동일 as-of의 정보 집합은 이후 수집으로 바뀌지 않는다.
store = ObservationStore(isolated_root)
known_universe = store.snapshot_at(asof_utc)
known_prices = store.prices_at(asof_utc)
```

성공 종료 0은 `collectionComplete=True`일 때만이다. 부분·거절·식별 문제·수정 충돌은 비정상 종료이며 manifest에 명시한다. 수집 시작 시 대상 목록 전체와 SPY·QQQ를 등록한다. 벤치마크를 먼저 확인하고 하나라도 거절되면 개별 종목 요청을 중단한다. `max_calls`는 어댑터 호출 수이며 yfinance 내부 쿠키·시간대·재시도 HTTP 요청 수가 아니다. 시간 예산은 다음 호출 시작을 제한하며 진행 중인 공급자 요청을 강제로 끊지는 않는다. CLI 공급자 timeout은 20초, 구성종목 transport timeout은 30초다.

## 가격 기준과 기업행동

Yahoo `auto_adjust=False`는 배당 미조정이지만 **분할은 이미 조정된** 가격이다. 원 공급자 패널과 메타데이터·옵션·버전·수집 시각·SHA-256을 함께 보존한다. 공급자 응답의 분석용 정규화 패널이며 HTTP wire body 자체를 저장했다고 주장하지 않는다.

각 세션 이후 관측된 분할 곱 `f`에 대해 OHLC와 주당 현금배당은 `× f`, 거래량은 `÷ f`로 복원한다. 분할 당일에는 그 분할을 다시 적용하지 않는다. 가격·배당 단위는 USD/주, 거래량은 주이며 거래량은 공급자 분할 조정 및 복원으로 소수가 될 수 있다. 분할 없음은 공급자가 보고한 0을 명시적 비율 1로 변환한다. 배당·거래량의 보고된 0은 유지하고 누락 필드는 0으로 채우지 않는다. 선택적 `Capital Gains`도 보고된 값과 미보고 `None`을 구분한다. 미보고가 경제적 부재의 증명은 아니다.

`Adj Close`는 입력·저장 경제 가격에서 제외한다. 총수익률 지수는 생성하지 않는다. 향후 연구 adapter가 이미 as-traded인 이 패널을 기존 Yahoo→as-traded converter에 다시 넣으면 분할이 중복 적용될 수 있다. 따라서 명시적으로 기준을 확인하는 별도 통합 검증이 필요하다. 과거 봉은 **지금 수집된 증거**이고 당시 실시간 관측이라고 주장하지 않는다.

## 구성종목과 식별자

기존 secondary source인 `datasets/s-and-p-500-companies` CSV를 최신 파일 변경 Git commit에 고정해 원문을 보존한다. 공식 지수 공급자의 유효일·완전성을 독립 확인한 자료는 아니다. 필수 필드 오류, 중복, 450개 미만/550개 초과, 비정상 심볼·CIK는 목록 전체를 차단한다. 작은 정적 목록이나 수집 가능한 일부 종목으로 대체하지 않는다.

503개 **증권**과 500개 **발행자 CIK**는 서로 다른 단위다. `CIK:<issuer>|CLASS_SYMBOL:<ticker>`는 잠정 식별자이며 영구 share-class ID가 아니다. 원 심볼·발행자명·CIK를 별도로 보존한다. CSV의 Date added는 공급자 원문일 뿐, 소급 적용할 효력일로 사용하지 않는다. `availableFrom`은 실제 UTC 관측 시각, 뉴욕 관측 달력일은 별도 필드, `effectiveMembershipDate=None`이다. 구성종목이 과거 세션에도 유효했다고 판단하지 않는다. 가격 행의 membership/identity applicability도 현재 조회 집합이며 과거 세션의 영구 신원 증명이 아님을 명시한다.

이전 목록에서 사라진 종목은 검증된 제외로 처리하지 않고 요청 대상과 누락 manifest에 남긴다. 같은 티커의 다른 CIK, 이름 변경, 미확인 제외는 해당 가격 수집을 차단한다. 이 문제는 다음 반복 목록만으로 자동 해제되지 않는다. v1에는 암묵적 해결 기능이 없으며 근거 있는 버전별 신원 검토를 후속 작업으로 요구한다. 다른 CIK로 바뀐 가격을 이전 발행자와 접합하지 않는다.

## 불변 저장과 복구

```
<isolated-ledger-root>/
  prices/us/us-prospective-daily-market-data-v1/
    YYYY-MM/observations-YYYY-MM-DD-<gzip-sha>.jsonl.gz
    source-acquisitions/YYYY-MM/source-YYYY-MM-DD-<gzip-sha>.jsonl.gz
    quarantine/revision-<gzip-sha>.jsonl.gz
    manifests/run-<gzip-sha>.jsonl.gz
  universe/us/us-prospective-daily-market-data-v1/
    sources/<original-csv-sha>.csv
    YYYY-MM/snapshot-<record-digest>-<gzip-sha>.jsonl.gz
```

경제 관측 ID는 버전·세션·증권 ID로 결정하며 경제 내용, 원 패널, 소스 수집, 구성종목 및 전체 행에 각각 검증값을 둔다. gzip mtime=0·정렬 JSON·content-addressed 파일명으로 동일 입력이 동일 bytes를 생성한다. 공개 파일은 덮어쓰지 않는다. 한 저장소의 동시 수집은 잠금으로 거절하고 임시 파일 완성 후 exclusive hard-link로 게시한다.

동일 경제 관측은 중복 저장하지 않는다. 새 수집 시각에서 경제 내용이 같아도 별도 소스 취득 증거는 보존한다. 내용이 달라지면 원본을 바꾸지 않고 후보를 quarantine한다. 수정 공개 이전 as-of 결과는 그대로 유지하고 이후에는 `REVISION_CONFLICT`로 사용을 차단한다. 자동 최신값 선택·충돌 해제는 없다.

중단·예산 소진·일부 종목 실패는 완료된 버퍼를 먼저 저장한다. 재개는 이미 게시된 ID를 건너뛴다. manifest의 저장 파일, 원 구성종목 CSV, 가격의 구성종목 참조·소스 취득 참조를 검증한다. 파일 삭제·손상·중복 ID가 있으면 이전 COMPLETE manifest만으로 성공을 반환하지 않는다. 모든 디렉터리 조회는 이 namespace에만 국한하며 수집 시 가격은 요청된 일별 청크만 조회한다. `snapshot_at` 및 전체 `prices_at` 조회는 초기 단순 스캔 구현이다; 장기간 운영 전에는 검증 가능한 인덱스와 규모 측정이 후속 과제다. 원자 게시·fsync는 로컬 파일시스템을 전제로 하며 원격 object store 지원을 주장하지 않는다.

## 실제 소스 관측

실측 근거는 [source audit](us-readiness/us-prospective-daily-market-data-source-audit-v1.json)에 있다. 합성 테스트 수치를 합치지 않았다.

- 구성종목: immutable source commit `36472b57910842f4025e8ca8303b93a692d2bbae`, CSV SHA-256 `a8045f043ea7e68d4254a07470a5e95ca5759ded4656657eac514162e6e82e06`, 503개 증권·500개 CIK, CIK 누락 0개.
- 가격: 2026-10-09 세션, 예상 505건, 어댑터 호출 2회(SPY·QQQ), 실제 유효 가격 0건, 모든 기대 관측 누락, PARTIAL.
- 두 벤치마크 모두 환경 프록시의 CONNECT 403. 개별 종목 503개에는 가격 요청을 수행하지 않았다. 이는 이 환경의 접근 결과이며 공급자 전체 장애의 증거가 아니다. 소스 경로를 바꾸거나 우회하지 않았다.
- 실측은 최종 타임스탬프·단위 보강 전 구현의 단일 제한 preflight다. 반복 실측이나 운영 성공을 주장하지 않는다. 원 CSV·불변 manifest는 저장소 밖 검증 디렉터리에만 남기며 production branch에는 쓰지 않았다.

## 검증과 활성화 후속 작업

새 테스트는 전부 명시적 합성 fixture다. 분할·배당 기준, 거래량 복원, 선택적 미보고 값, 달력, 세션·통화·소스 옵션 거절, identity 문제 지속, 멱등·부분 재개·KeyboardInterrupt, 수정 quarantine, 과거 as-of 불변성, 원본 삭제·손상, 예산·CLI 거절 및 protected 실행 경로 부재를 확인한다. 기존 인코딩·outcome·datafeed 테스트도 함께 실행한다. 기존 full-suite 및 lint·compile·import·seed validation은 최종 head에서 검증하고 실제 결과는 PR에 보고한다. 실측 가격 성공은 합성 통과로 대체하지 않는다.

**이 PR을 병합해도 자동 수집은 활성화되지 않는다.** owner 승인 후 최소 후속 작업은 다음과 같다.

1. 허용된 표준 공급자 접근 환경·이용 조건을 확인하고 격리 디렉터리에서 전체 503개 증권+SPY+QQQ dry-run 성공과 manifest·기업행동 기준을 확인한다. 영구 신원·공식 구성종목 효력일의 한계를 인정하거나 별도 소스 검토로 해결한다.
2. 별도 승인 PR에서 전용 US collector workflow를 추가한다. 최초 manual dry-run 후 스케줄(예: 매일 23:15 UTC, XNYS 새 완료 세션에서만 수집)을 활성화한다. 기존 ledger/build/weekly/model 연구 작업을 실행하지 않는다.
3. `$RUNNER_TEMP` 등 Git 밖에 출력한다. 저장 ID로 재개하려면 기존 **이 namespace의 검증된 파일만** isolated staging으로 읽기 복사한다. 새 파일의 digest·원본 참조를 검증한 뒤 fixture namespace를 제외한 `ledger/prices/us/<version>`과 `ledger/universe/us/<version>`만 signal-history에 append한다. 해당 버전 이외 경로·기존 파일 갱신을 거절한다. concurrency와 fast-forward-only commit, 부분 상태 경고를 둔다.
4. 운영 read-only 확인으로 수집 날짜·완전성·SPY/QQQ·부분 실패·소스 변경을 감시한다. 기존 과거 등록·결과·실행 잠금은 재생성하지 않는다. 연구 통합은 총수익률 중복 조정·신원·구성종목 가용성을 별도로 검증한 뒤 진행한다.
