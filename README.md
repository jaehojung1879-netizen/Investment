# My Investment Insight

개인 포트폴리오용 투자 인사이트 대시보드입니다. `market_alert_system` 노트북의
멀티 호라이즌 LightGBM 알림 시스템을 재사용 가능한 파이프라인으로 이식해,
종목별 상승확률 신호·매크로 환경·리스크/국면 진단·투자 원칙을 한 화면에서 봅니다.

GitHub Actions(Python)가 데이터를 수집·모델링해 `data/site-data.json`을 만들고,
정적 GitHub Pages 사이트가 그것을 렌더링합니다. (서버·DB 불필요, 무료 호스팅)

## 화면

1. **오늘의 신호** — 종목 × 호라이즌(21/63/126D) 캘리브레이션 상승확률 + 동적 임계값 알림(STRONG BUY / HOLD / STRONG SELL), OOS 정밀도·lift·백테스트 동반 표시
2. **매크로 환경** — FRED 국채 10Y/2Y, 장단기 금리차, VIX, 거시 스탠스/플래그
3. **리스크·국면 진단** — 추세·변동성·낙폭·상대강도·RSI 기반 Bull/Transition/Bear 분류 + 리스크 플래그
4. **투자 원칙·체크리스트** — `docs/investment-philosophy.md`에서 관리

## 추적 종목 바꾸기

`config.json`의 `tickers` 배열만 수정하면 됩니다. `benchmark`/`primary`는 그 목록 안에 있어야 합니다.

```json
{ "tickers": ["QQQ", "SPY", "PLTR", "NVDA"], "benchmark": "SPY", "primary": "QQQ" }
```

## 구성

```
config.json                 추적 종목·호라이즌·모델 파라미터
pipeline/                   노트북 이식 ML 파이프라인
  config.py                 config.json + 환경변수 로딩
  datafeed.py               yfinance(가격) + FRED(매크로) 수집
  features.py               피처 엔지니어링 + 타깃
  model.py                  LightGBM walk-forward + 캘리브레이션 + 백테스트
  macro.py                  매크로 환경 요약
  risk.py                   국면·리스크 진단
  build.py                  오케스트레이터 → data/site-data.json
data/site-data.json         사이트가 읽는 산출물 (현재는 SEED 예시)
docs/investment-philosophy.md  투자 원칙·체크리스트(사이트가 렌더)
index.html / styles.css / app.js  대시보드
scripts/make_seed.py        합성 데이터로 파이프라인을 점검/시드 생성하는 개발 유틸
.github/workflows/pages.yml  데이터 빌드 후 Pages 배포
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
