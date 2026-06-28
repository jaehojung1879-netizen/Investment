# Market Research Workbench

투자 철학 Markdown과 시장 데이터 JSON을 기반으로 QQQ 중심의 증시 상태를 분석하는 GitHub Pages용 정적 사이트입니다.

## 구성

- `docs/investment-philosophy.md`: 투자 철학, 분석 원칙, 행동 프레임워크의 원천 문서
- `scripts/fetch_market_data.py`: 공개 일간 CSV에서 QQQ/SPY 데이터를 가져와 지표를 계산하는 빌드 스크립트
- `data/market-data.json`: 사이트가 읽는 시장 데이터 및 분석 결과 artifact
- `index.html`, `styles.css`, `script.js`: Markdown과 JSON을 렌더링하는 대시보드
- `.github/workflows/pages.yml`: 시장 데이터 갱신 후 GitHub Pages에 배포하는 워크플로

## 배포

1. GitHub 저장소 Settings → Pages에서 Source를 **GitHub Actions**로 선택합니다.
2. `main` 브랜치에 push하거나 Actions에서 수동 실행합니다.
3. 워크플로가 `scripts/fetch_market_data.py`를 실행해 `data/market-data.json`을 갱신한 뒤 Pages artifact를 배포합니다.
4. 배포 후 `https://사용자명.github.io/저장소명/`에서 확인합니다.

## 로컬 확인

```bash
python3 scripts/fetch_market_data.py
python3 -m http.server 8000
```

이후 `http://127.0.0.1:8000/`에서 확인합니다.
