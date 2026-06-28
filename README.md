# My Investment Insight

개인용 단기 트레이드 인사이트 대시보드입니다. `market_alert_system` 노트북의
멀티 호라이즌 LightGBM 알림 시스템을 재사용 가능한 파이프라인으로 이식하고,
국내(KR)/국외(US) 후보를 매일 스크리닝해 **무엇을 언제까지 보유할지**를 제안합니다.

GitHub Actions(Python)가 매일 데이터를 수집·모델링해 `data/site-data.json`을 만들고,
정적 GitHub Pages 사이트가 그것을 렌더링합니다. (서버·DB 불필요, 무료 호스팅)

## 화면

1. **오늘의 트레이드** — KR/US 후보를 트레이드 호라이즌(기본 10영업일)으로 스크리닝, 비용·확신 게이트를 통과한 것만 entry·hold-until·무효화 조건과 함께 제안
2. **보유 종목** — core 종목 × 21/63/126D 캘리브레이션 확률 + 알림 + OOS 정밀도/lift/백테스트
3. **매크로** — FRED 국외(10Y/2Y·금리차·기준금리·HY스프레드·VIX) + 국내(원/달러·국고채 10Y/3M·금리차)
4. **시장 국면** — 구루 인용 대신 유니버스 breadth(추세 위 비중)·모멘텀 + 매크로로 계산한 **정량 시장심리**(US/KR, 0~100·강세/중립/약세)
5. **원칙·체크리스트** — `docs/investment-philosophy.md`에서 관리

설명은 섹션 제목 옆 **?** 또는 점선 용어(확률·edge·lift·OOS 등)를 **클릭하면 팝업**으로 뜹니다. 상단에 데이터 기준일·유니버스 수·모델 학습 횟수가 표시되고, 갱신 실패 시 stale 배너가 뜹니다.

## 방법론 메모 (노트북 대비 수정점)

- **캘리브레이션 누수 제거**: 노트북은 모델이 학습한 데이터로 isotonic 보정을 해 확률이 0/1로 붕괴했음. 보정 구간을 학습에서 **제외**하도록 수정.
- **horizon embargo**: h일 선행 타깃이 학습/테스트 경계를 넘어 누수되지 않도록 walk-forward에 embargo 추가(purged WF).
- **비용 인지 의사결정**: 확률 0.5 초과는 우위가 아님. `EV = p·E[up] + (1−p)·E[down] − 비용허들` 이 양수이고 확신 하한·국면 조건을 만족할 때만 트레이드 제안(KR은 세금·수수료로 허들 ↑).

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
  datafeed.py               yfinance(가격) + FRED(매크로) 수집
  features.py               피처 엔지니어링 + 타깃
  universe.py               S&P500/KOSPI 자동 구성(+종목명), 실패 시 fallback
  model.py                  LightGBM purged walk-forward + 캘리브레이션 + EV + 백테스트
  trade.py                  비용 인지 단기 트레이드 아이디어 엔진(KR/US)
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
