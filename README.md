# Market Insight Lab

QQQ 중심의 다기간 투자 신호, 리스크 컨텍스트, 백테스트 관점을 한 화면에서 확인하기 위한 정적 리서치 사이트입니다.

## GitHub Pages 배포

1. 이 저장소를 GitHub에 push합니다.
2. GitHub 저장소의 **Settings → Pages**로 이동합니다.
3. **Build and deployment → Source**를 **GitHub Actions**로 선택합니다.
4. `main` 브랜치에 push하면 `.github/workflows/pages.yml` 워크플로가 정적 파일을 배포합니다.
5. 배포 후 `https://사용자명.github.io/저장소명/` 주소에서 사이트를 확인합니다.

## 향후 데이터 연결 방향

현재 화면은 샘플 데이터 기반입니다. 이후 노트북 또는 배치 작업에서 `market-data.json` 같은 산출물을 생성하고 `script.js`에서 해당 파일을 읽도록 바꾸면 실제 모델 확률, 리스크 지표, 백테스트 결과를 사이트에 반영할 수 있습니다.
