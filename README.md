# My Investment Insight

개인용 단기 트레이드 인사이트 대시보드입니다. `market_alert_system` 노트북의
멀티 호라이즌 LightGBM 알림 시스템을 재사용 가능한 파이프라인으로 이식하고,
국내(KR)/국외(US) 후보를 매일 스크리닝해 **무엇을 언제까지 보유할지**를 제안합니다.

GitHub Actions(Python)가 매일 데이터를 수집·모델링해 `data/site-data.json`을 만들고,
정적 GitHub Pages 사이트가 그것을 렌더링합니다. (서버·DB 불필요, 무료 호스팅)

## 화면

0. **글로벌 마켓** — S&P 500 · 나스닥 종합 · 다우 · 필라델피아 반도체 · 코스피 · 코스닥 · 원/달러 · VIX · **비트코인 · 금 · 달러인덱스**. 지수별 현재 레벨, 1D/1M/YTD 변화율, 52주 고점 대비 거리, 3개월 스파크라인. Yahoo Finance 실패 시 Stooq CSV로 자동 대체.
0.5. **투자 나침반 (방향성)** — 규칙 기반 자산배분 도구 4종을 하나의 판정으로 합성:
   - **듀얼 모멘텀 (Antonacci GEM)**: 미국/선진국/신흥국 주식 vs 현금(T-Bill) 12개월 절대+상대 모멘텀 → 주식에 돈을 둘 국면인지
   - **변동성 타게팅**: 벤치마크 실현변동성 vs 목표 12% → 기계적 주식 노출 상한 (매니지드볼 방식)
   - **KR/US 틸트**: 코스피 vs S&P500 3/6개월 상대 모멘텀
   - 추세(주요 지수 200일선 상회 비중)·공포탐욕·매크로 스탠스를 합쳐 0~100 점수 → **확대/중립/방어 + 권장 주식·현금 비중**
1. **오늘의 트레이드** — KR/US 후보를 트레이드 호라이즌(기본 10영업일)으로 스크리닝, 비용·확신 게이트를 통과한 것만 entry·hold-until·무효화 조건과 함께 제안. **½켈리 기준 제안 비중**(종목당 10% 상한) 표시.
1.5. **섹터 · 팩터 로테이션** — RRG(Relative Rotation Graph) 방식 4사분면(주도/약화/개선/부진)으로 미국 11개 SPDR 섹터(vs SPY)와 한국 KODEX 섹터 ETF(vs KODEX 200)의 자금 순환을 시각화. 스타일 ETF(모멘텀·가치·퀄리티·저변동·소형주)의 S&P500 대비 1/3/6개월 초과수익으로 어떤 팩터가 주도 중인지 표시.
2. **보유 종목** — core 종목 × 21/63/126D 캘리브레이션 확률 + 알림 + OOS 정밀도/lift/백테스트
3. **매크로** — FRED 국외(10Y/2Y·금리차·기준금리·HY스프레드·VIX) + 국내(원/달러·국고채 10Y/3M·금리차)
4. **자금 흐름(유동성 쏠림)** — 거래량 급증(최근 5일 vs 60일) + 상승 종목을 지역별로. 돈·관심이 어디로 몰리는지 자체 프록시. (실제 기관/외국인 수급·13F는 외부 소스 필요)
5. **공포·탐욕 지수 / 시장 국면** — 구루 인용 대신 유니버스 breadth·모멘텀 + 매크로(VIX·신용스프레드·원화)로 계산한 **공포·탐욕 지수**(US/KR, 0~100, 극도의 공포~극도의 탐욕)
6. **원칙·체크리스트** — `docs/investment-philosophy.md`에서 관리

유니버스는 `pipeline/universe_lists.py`에 S&P500 상위 ~120 / KOSPI ~68을 내장해, FinanceDataReader가 막혀도 `universeSize`(기본 120)개까지 스캔합니다. 스크리닝은 `screenHistoryStart`(기본 2019) 기간만 받아 다운로드를 가볍게 합니다.

- **종목명을 클릭**하면 그 종목의 정량 지표(현재가·SMA·RSI·변동성·낙폭·상대강도·52주고점대비·호라이즌별 상승확률·리스크 플래그)가 팝업으로 뜹니다.
- 섹션 제목 옆 **ⓘ**/점선 용어(확률·edge·lift·OOS)도 클릭하면 설명 팝업. 상단에 데이터 기준일·유니버스 수가 표시되고, 갱신 실패 시 stale 배너가 뜹니다.

## 방법론 메모 (노트북 대비 수정점)

- **캘리브레이션 누수 제거**: 노트북은 모델이 학습한 데이터로 isotonic 보정을 해 확률이 0/1로 붕괴했음. 보정 구간을 학습에서 **제외**하도록 수정.
- **horizon embargo**: h일 선행 타깃이 학습/테스트 경계를 넘어 누수되지 않도록 walk-forward에 embargo 추가(purged WF).
- **비용 인지 의사결정**: 확률 0.5 초과는 우위가 아님. `EV = p·E[up] + (1−p)·E[down] − 비용허들` 이 양수이고 확신 하한·국면 조건을 만족할 때만 트레이드 제안(KR은 세금·수수료로 허들 ↑). 제안 비중은 **½켈리**(f\* = p − (1−p)/b의 절반, 종목당 10% 상한).
- **백테스트 회계 수정**: 진입 시 매수대금을 차감하지 않고 청산 시 `주식수×진입가`를 더해 자산이 트레이드마다 부풀던 버그를 수정(오버플로 가드로 가려져 있었음). 실시간 신호의 isotonic 보정 구간에도 walk-forward와 동일한 horizon embargo 적용.
- **데이터 수집 견고성**: yfinance 다운로드에 지수 백오프 재시도 + 누락 티커 소배치 2차 패스. 지수 테이프는 Yahoo → Stooq 폴백. 클래스 주식 심볼 정규화(BRK.B/BRKB → BRK-B). 빌드마다 유니버스 **커버리지(%)를 meta에 기록**하고 85% 미만이면 사이트에 경고 배너 표시.
- **매일 아침 갱신 보장**: 매일 22:00 UTC(미국장 마감 후, 07:00 KST 다음날 아침)에 **주말 포함 매일** 빌드해 아침마다 최신 미국장 데이터로 사이트가 갱신됨. 평일만 돌던 기존 스케줄에서는 일요일·월요일 아침 KST에 데이터가 밀렸으나 이를 해소.
- **KR 당일 반영**: 평일 07:10 UTC(16:10 KST, 한국장 마감 후)에도 빌드해 국내 데이터가 미국장 마감 빌드까지 하루 밀리지 않게 함.

## 종목 바꾸기

`config.json`만 수정합니다. KR 티커는 `.KS`(코스피)/`.KQ`(코스닥) 접미사를 씁니다.

```json
{
  "core": ["QQQ", "NVDA", "PLTR"],
  "universeSize": 40,
  "universe": { "US": ["QQQ", "AAPL", "..."], "KR": ["005930.KS", "000660.KS", "..."] },
  "names": { "005930.KS": "삼성전자", "000660.KS": "SK하이닉스" },
  "benchmark": "SPY", "primary": "QQQ", "tradeHorizon": 10,
  "fred": {
    "US": { "Treasury_10Y": "DGS10", "Treasury_2Y": "DGS2", "FedFunds": "DFF", "HY_Spread": "BAMLH0A0HYM2" },
    "KR": { "USD_KRW": "DEXKOUS", "Korea_10Y": "IRLTLT01KRM156N", "Korea_3M": "IR3TIB01KRM156N" }
  }
}
```

- `core` = 보유 종목(전체 분석 + 보유 카드)
- **스크리닝 유니버스는 매일 자동 구성**: S&P500 + KOSPI 상위 `universeSize`개를 FinanceDataReader로 가져옴(종목명도 자동). 네트워크 실패 시 `universe.US/KR` 정적 목록으로 fallback
- `universeSize` = 지역별 스크리닝 종목 수. **클수록 매일 CI 시간이 길어짐**(40이면 수십초~수분)
- `names` = 자동 종목명 위에 덮어쓸 오버라이드(코드는 작게 같이 표시)
- `tradeHorizon` = 단기 트레이드 기본 보유 영업일
- `fred.US` / `fred.KR` = 지역별 매크로 시리즈. FRED 한 키로 미국·한국 모두 조회

## 구성

```
config.json                 core·universe(KR/US)·호라이즌·모델 파라미터
pipeline/                   노트북 이식 ML 파이프라인
  config.py                 config.json + 환경변수 로딩
  datafeed.py               yfinance(가격, 재시도·2차 패스) + FRED(매크로) 수집
  indices.py                글로벌 지수 테이프 (S&P500·나스닥·코스피 등, Yahoo→Stooq 폴백)
  features.py               피처 엔지니어링 + 타깃
  universe.py               S&P500/KOSPI 자동 구성(+종목명), 실패 시 fallback
  model.py                  LightGBM purged walk-forward + 캘리브레이션 + EV + 백테스트
  trade.py                  비용 인지 단기 트레이드 아이디어 엔진(KR/US) + ½켈리 사이징
  direction.py              투자 나침반: 듀얼 모멘텀·변동성 타게팅·KR/US 틸트 합성 판정
  rotation.py               섹터 로테이션(RRG 4사분면) + 팩터/스타일 모멘텀
  macro.py                  매크로 환경 요약(US/KR)
  sentiment.py              정량 시장심리(breadth·모멘텀·매크로) US/KR
  risk.py                   종목 국면·리스크 진단(+breadth 입력)
  build.py                  오케스트레이터 → data/site-data.json (+meta/stale)
data/site-data.json         사이트가 읽는 산출물 (현재는 SEED 예시)
docs/investment-philosophy.md  투자 원칙·체크리스트(사이트가 렌더)
index.html / styles.css / app.js  대시보드
scripts/make_seed.py        합성 데이터로 파이프라인을 점검/시드 생성하는 개발 유틸
.github/workflows/pages.yml  매일 데이터 빌드 후 Pages 배포
requirements.txt
```

## 🔑 FRED API 키 (매크로 데이터용)

매크로 패널(금리·금리차·VIX)을 채우려면 FRED API 키가 필요합니다. **코드에 넣지 마세요.**

1. https://fred.stlouisfed.org/docs/api/api_key.html 에서 무료 키 발급(노출된 기존 키는 재발급 권장).
2. GitHub 저장소 → Settings → Secrets and variables → Actions → New repository secret
   - Name: `FRED_API_KEY`
   - Value: 발급받은 키
3. 키가 없어도 파이프라인은 동작하며, 매크로 패널만 비어 있게 표시됩니다.

## 배포

1. Settings → Pages에서 Source를 **GitHub Actions**로 설정.
2. `main`에 push하거나 Actions에서 수동 실행(workflow_dispatch).
3. 워크플로가 `python -m pipeline.build`로 `data/site-data.json`을 갱신한 뒤 Pages에 배포.
4. `https://<사용자명>.github.io/<저장소명>/` 에서 확인.

## 로컬 확인

```bash
pip install -r requirements.txt
python3 scripts/make_seed.py     # 합성 데이터로 site-data.json 미리보기 생성 (선택)
# 실데이터:  FRED_API_KEY=... python3 -m pipeline.build
python3 -m http.server 8000      # http://127.0.0.1:8000/
```

## 면책

개인 리서치·교육 목적이며 투자 조언이 아닙니다. 과거 성과는 미래를 보장하지 않으며,
데이터 지연·오류 가능성이 있으므로 실제 주문 전 원천 데이터를 재확인하세요.
