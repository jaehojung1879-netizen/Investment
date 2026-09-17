# 미국 생존편향: 194개 이름에 가격이 없다

한국은 닫혔다. `replay-v16`이 KRX 저장소를 배선하면서 KR `affectedObservations`는
100% → **2.29%**(MEDIUM)가 됐다. 같은 실행이 남은 구멍을 미국으로 옮겨 놓았을 뿐이다:
US는 constituent coverage **82.90%**, `affectedObservations` **17.30%**, HIGH.
2013년은 73.13%로 가장 나쁘다. `integrityGate`의 `historicalUniverse`는 그래서 닫혀 있다.

## 갭의 정체 — 추측이 아니라 봉인된 스냅샷에서 실측

`replay-v16`의 봉인 입력(`inputs.json`, through 2026-09-14)에서 **가격 패널이 실제로
들고 있는 티커**를 뽑아, 같은 스냅샷의 유니버스 멤버십과 대조했다.

```
US 멤버(역대)        829
가격 패널이 서빙       633
서빙 못 함            196   ← 이 중 티커가 아닌 항목 2개 제외 → 194
```

**194개 전부 `delisted` 날짜를 갖고 있고, 아직 지수에 남아 있는데 가격이 없는 이름은
0개다.** 이 한 줄이 갭의 성격을 확정한다 — 다운로드 버그가 아니라 정확히 생존편향이다.
목록과 측정 방법은 `data/us-unpriced-members.json`에 남겼다.

기간은 2012-12-27 ~ 2026-06-25에 걸쳐 있다. YHOO·SIVB·TWTR·ATVI처럼 실제로 거래가 끝난
이름과, KSU·NLSN·WBA처럼 인수·합병으로 지수에서만 사라진 이름이 섞여 있다.

## 리플레이가 이미 하고 있는 것 — 그래서 원인이 아닌 것

`run_replay`는 과거 멤버를 **이미 다운로드 목록에 넣는다**(`historical_only`,
"+N former index members to download"). `fetch_prices`는 실패한 배치를 작은 배치로
**한 번 더** 재시도한다. 벤더 응답과 패널 사이에 필터는 없다.

그러므로 이 194개는 *요청하지 않은* 이름이 아니라 **야후가 두 번 다 아무것도 돌려주지
않은** 이름이다. 재시도로 열리는 문이 아니다.

## 한국에서 배운 것

한국도 같은 모양이었고, 벤더를 **재시도**해서가 아니라 **바꿔서** 닫혔다.
FinanceDataReader는 상장폐지 한국 종목의 34.55%만 서빙했고, KRX Open API는
"그날 거래된 것"을 싣기 때문에 2014년에 사라진 이름이 2013년 응답에 그대로 있다 —
떠난 139종목 **100% 서빙**, 보정 감사 통과 84.2%.

미국에 대한 질문은 그래서 하나다: **어느 벤더가 죽은 미국 티커의 일별 이력을 파는가.**

## 프로브 — `us-delisted-prices`

`scripts/probe_us_delisted_prices.py`, `Probes` 워크플로의 드롭다운에 등록.
호스트가 Actions 풀에서 응답하는 것이 이미 확인된 벤더만 묻는다.

| 벤더 | 엔드포인트 | 키 |
|---|---|---|
| `stooq` | CSV export | **불필요** |
| `polygon` | `/v2/aggs/ticker/{t}/range/1/day/...` | `secrets.MASSIVE` |
| `finnhub` | `/stock/candle` | `secrets.FINNHUB` |
| `fmp` | `/stable/historical-price-eod/full` | `secrets.FMP` |
| `alphavantage` | `TIME_SERIES_DAILY` | `secrets.ALPHAVANTAGE` |

### 대조군 없이는 아무것도 판정하지 않는다

`YHOO`에 빈손인 벤더는 *죽은 티커를 거부*하는 것일 수도, *우리를 거부*하는 것일 수도
있다 — 키가 틀렸거나, 할당량이 끝났거나, 애초에 이력이 없는 플랜이거나. 그래서 모든
벤더에게 **살아 있고 패널이 이미 서빙하는** 이름(AAPL·JPM·XOM)을 같은 방식으로 묻는다.

```
OPEN                떠난 코호트와 대조군 둘 다 서빙
PLAN_LIMITED        이름은 갖고 있고 값을 부른다 — 벤더 탐색이 아니라 예산 문제
DEPARTED_REFUSED    대조군은 서빙, 떠난 이름은 못 주고, 플랜 얘기도 안 함 — 진짜 발견
VENDOR_UNUSABLE     대조군도 놓침 — 상장폐지에 대해 증명된 것이 없음
NO_KEY              자격증명이 없어 묻지 않음
```

이건 이 리포가 simfin에서 이미 배운 규율이다 — "최근 창 대조군은 서빙됐으므로 이력이
정말 없다"가 되어야 판정이 성립한다. `PLAN_LIMITED`는 run #1이 없어서 틀린 칸이고,
왜 필요한지는 아래 run #1 항목에 적었다.

### "응답했다"는 커버리지가 아니다

2년치를 주고도 서빙한 것처럼 보일 수 있다. 각 응답은 그 이름 **자신의 멤버십 구간**
(`listed`..`delisted`)에 대해 채점한다. 리플레이가 필요한 건 그 구간뿐이기 때문이다.

`FULL` 판정은 **양 끝에서 며칠이 비었는가**로 하고 비율로 하지 않는다. 비율은 길이에
따라 뜻이 달라진다 — 10년의 98%는 10주지만 1년의 98%는 일주일이라, 하나의 비율로는
"가입 일주일 뒤부터 시작하는 벤더는 허용한다"를 두 경우에 동시에 표현할 수 없다.
이 코호트는 하루짜리 멤버십부터 14년짜리까지 있다. 허용치는 양 끝 각각 **14일**이다.

### 레이트 리밋은 재는 것이지 가정하는 것이 아니다

Probes run #2는 polygon의 레이트 리밋에 걸린 코호트를 **벤더 판정으로 읽었다**. 그건
판정이 아니었다. 모든 요청은 `--delay`로 띄우고, 429는 백오프 재시도하며, 429로 끝난
이름은 `RATE_LIMITED`로 기록한다 — 절대 `EMPTY`가 아니다.

## 실행

```
Probes → us-delisted-prices
  args 기본값: --sample 12 --delay 13      (polygon 무료 티어 5 req/min)
  전체 코호트를 재려면: --sample 0
  한 벤더만:            --vendors stooq
```

## Run #1, 2026-09-16 — 답은 "아무도 안 판다"가 아니라 "돈을 안 냈다"

표본 12개(떠난 시기 전체에 균등) + 대조군 3개, 벤더 5곳. 12분.

| 벤더 | run #1 판정 | 벤더가 실제로 한 말 |
|---|---|---|
| `stooq` | `VENDOR_UNUSABLE` | AAPL·JPM·XOM까지 **전부 404** + HTML 페이지 |
| `polygon` | `DEPARTED_REFUSED` ← **틀린 판정** | 대조군은 2년치만(span 14.3%, 492행). 떠난 종목 12개 전부 403 `NOT_AUTHORIZED` — *"Your plan doesn't include this data timeframe. Please upgrade your plan"* |
| `finnhub` | `VENDOR_UNUSABLE` | 전부 403 `"You don't have access to this resource."` — candle 엔드포인트가 유료로 옮겨갔다 |
| `fmp` | `OPEN` | 대조군 **FULL, 3,437행, span 100%**. 떠난 종목은 VIAC만 PARTIAL(67.4%, 448행), 나머지 11개는 **HTTP 402** |
| `alphavantage` | `NO_KEY` | `secrets.ALPHAVANTAGE`가 비어 있다 |

**살아 있는 이름에는 13년치를 다 주면서 오래된 구간에는 402를 돌려주는 벤더는, 그
데이터가 없는 게 아니라 값을 부르는 것이다.** polygon은 문장으로 그렇게 말했고 fmp는
상태 코드로 말했다. 한국과 결정적으로 다른 지점이 여기다 — 거래소가 원본을 무료로
주던 자리에, 미국에서는 유료 플랜이 있다.

### run #1이 드러낸 것은 벤더만이 아니었다 — 프로브 결함 셋

1. **`DEPARTED_REFUSED`는 틀린 판정이었다.** polygon은 티커를 거부한 적이 없고
   기간을 거부했다. "다른 벤더를 찾아라"와 "이 벤더에 돈을 내라"는 정반대 행동인데
   같은 칸에 들어갔다. → `PLAN_LIMITED` 판정을 신설했다. 402, 그리고 플랜을 언급하는
   403이 여기 들어간다. 플랜을 언급하지 **않는** 403(finnhub의 인증 실패)은 여전히
   `ERROR`다 — 없는 가격표를 지어내지 않기 위해서다.
2. **`HTTP 402: unparseable body`를 열두 번 찍었다.** 에러 경로가 JSON인 본문만
   설명할 줄 알아서, 유료화와 장애를 가를 수 있는 **유일한 문장을 버렸다.** 이제
   어떤 본문이든 그대로 싣는다.
3. **stooq의 404는 진짜 거부인지 확인되지 않았다.** urllib은 자신을
   `Python-urllib/3.11`로 소개하고, 적잖은 사이트가 경로와 무관하게 그걸 404/403으로
   답한다. 브라우저 User-Agent를 붙인다고 거부가 사라지지는 않지만, **거짓 거부의
   이유 하나는 제거된다.** 붙이고 다시 잰다.

## Run #2, 2026-09-16 — 답이 나왔다: 둘 다 판다

같은 표본 12개 + 대조군 3개. `PLAN_LIMITED` 판정과 본문 보존을 넣은 뒤 재실행. 11분.

| 벤더 | run #2 판정 | 벤더가 실제로 한 말 |
|---|---|---|
| `stooq` | `VENDOR_UNUSABLE` | 브라우저 UA를 붙여도 AAPL·JPM·XOM 전부 200 + `<noscript>` 페이지 — 봇 차단벽이지 데이터 부재가 아니다 |
| `polygon` | **`PLAN_LIMITED`** | 대조군 그대로 서빙(2년치). 떠난 12개 전부 403 `NOT_AUTHORIZED` — *"Your plan doesn't include this data timeframe. Please upgrade your plan at https://polygon.io/pricing"* |
| `finnhub` | `VENDOR_UNUSABLE` | 대조군까지 403 `"You don't have access to this resource."` — 플랜 언급이 없어 `ERROR`로 남는다. candle 엔드포인트 자체가 이 키로는 안 닿는다 |
| `fmp` | `OPEN` | 대조군 FULL(3,437행). 떠난 12개 중 11개가 402 — *"Premium Query Parameter: Special Endpoint... not available under your current subscription... upgrade your plan"*. VIAC 하나만 PARTIAL(67.4%, 448행) — 무료 조회창 안에 걸친 비교적 최근 종목 |
| `alphavantage` | `NO_KEY` | 시크릿 비어 있음, 안 물어봄 |

**두 벤더 다 데이터를 갖고 있고, 값을 직접 부른다.** polygon은 URL(`polygon.io/pricing`)까지
주면서 업그레이드를 안내하고, fmp는 상태 코드 402(Payment Required)로 같은 말을 한다.
VIAC가 부분적으로 뚫린 것도 이 해석과 정확히 맞는다 — fmp 무료 티어의 조회 가능 기간
안에 있는, 비교적 최근에 떠난 이름이기 때문이다.

**이건 이제 기술 문제가 아니라 예산 문제다.** 더 찾아볼 무료 벤더가 남아있지 않다 —
stooq는 봇 차단, finnhub는 이 키로 엔드포인트 자체가 안 열린다. polygon과 fmp,
둘 중 하나(또는 둘 다)의 유료 플랜이 유일하게 확인된 경로다.

## 아직 측정되지 않은 것

**얼마면 되는지.** 두 벤더 다 194개 코호트 전체·13년 전체 구간을 **어느 요금제부터**
커버하는지는 안 쟀다. polygon.io/pricing과 financialmodelingprep 구독 페이지를 직접
확인해야 한다. 그다음이 결정이다: 두 유료 벤더 중 하나에 얼마를 낼지는 이 리포지토리가
아니라 사람이 정할 일이다.

수집기도, 배선도, 새 `REPLAY_VERSION`도 그 결정 뒤의 일이다. `replay-v16`은 그대로
봉인돼 있다.

## 게이트는 이 결정과 별개로 이미 풀렸다 (2026-09-17)

위 "얼마면 되는지" 질문(유료 벤더 결제 여부)은 여전히 열려 있고 여전히 사람이 정할
일이다. 그런데 이 194개 결손이 `historicalUniverse` 게이트를 영구히 막고 있던
문제는 **별개로, 벤더 결제와 무관하게 이미 풀렸다.** `survivorshipBound`가
지금 측정된 전체 갭(US 17.3%, KR 2.29%)에서도 champion-challenger 비교를
뒤집지 못한다는 게 확인됐고(`replay-v16`: `NOTHING_TO_BOUND`), 이 194개 전부가
다운로드 버그가 아니라 진짜 상장폐지임이 이미 위에서 확인됐으므로, 게이트에
100% 대신 20% 허용 임계값(`pit_data.HISTORICAL_UNIVERSE_GAP_TOLERANCE_PCT`)을
두기로 사람이 결정했다. 자세한 내용과 근거는 README의 해당 항목 참고.

**이게 바꾸지 않는 것**: 이 문서의 "몇 개 종목에 가격이 없는가"라는 사실 자체는
그대로다. 벤더에 돈을 낼지는 여전히 별개의 예산 판단이고, 194개를 실제로
채우고 싶다면 이 문서의 나머지 내용이 여전히 유효한 조사 결과다.
