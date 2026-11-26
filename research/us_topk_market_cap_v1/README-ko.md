# 미국 회사 시총 Top 100·10·5

회사 순위와 보유 증권을 미래 수익 접근 전에 고정하는 독립 분석이다.
기존 실험·원장·봉인 입력·결과·워크플로·화면을 수정하지 않는다.
새 유료 계정과 생산 writer를 사용하지 않는다.

주 실험은 당시 S&P 500 전체 회사이며 금융·부동산과 미완전 재무 자료를
제외하지 않는다. 공식 주차별 구성·증권 연결·IWF 시총이 없으면 주 실험은
미측정이다. SEC 실제 보통주 수×당시 실제 종가는 `보고 총시총 추정`이다.
기존 정정 재무 풀에만 순위를 매길 수 있으면 그 풀의 Top K로 표시한다.

신호는 완결 주의 마지막 미국 거래일, 체결은 다음 거래일 종가,
청산은 체결 인덱스+126/+252 종가, 성숙 기준일은 2026-11-13이다.
복수 클래스 회사는 한 번만 세고 보유 클래스는 지수 편입 심볼 사전순 첫째다.
매수 8bp·매도 8.3bp, 무이자 현금, 총수익 가격의 배당 중복 반영 금지,
미확인 단주·권리와 선택된 종목의 가격 공백은 실패로 남긴다.
누락 기업에 방어 가능한 상한이 없으면 K별 경계를 미확정으로 표시한다.

`protocol.json`과 `protocol.sha256`은 첫 순위/수익 실행 전 고정 규칙이다.
이전 보유 수익이 이미 노출됐으므로 탐색적 분석이며 새 표본외 검증이 아니다.

## 입력과 보관

`MARKET_PRIVATE`는 #340 패킷 2개를 포함해 이미 검증한 작업용 복사본이다.
기존 원본 840개와 정정 복사본 842개의 해시를 `verify`가 검사한다.
원래 개인키는 원본 환경에 두고 이 분석에는 필요하지 않다.
`TOPK_PRIVATE`에는 SEC 원문, 역산 실제 종가, 회사 순위, 개별 미래 수익을
보관한다. Git checkout 밖의 접근 제한 디렉터리를 사용한다.
`TOPK_OUTPUT`에는 집계·메타데이터만 남긴다.

SEC companyfacts는 실제 발행주식 수만 읽으며 EPS 가중평균 주식 수는
사용하지 않는다. 파일 공개일은 신호일보다 엄격하게 앞서야 한다.
복수 클래스 원문 공시는 클래스 수량을 따로 읽는다. 미상장 동일 경제권
클래스는 명시한 전환 비율로 상장 클래스 가격에 환산한 추정치다.
Up-C 회사의 LLC 권리는 명목 Class B 주식 수와 혼합하지 않는다.
SEC 현재 아카이브의 과거 accession/공개일을 보존하지만 별도의 당시
다운로드 빈티지를 보유했다고 주장하지 않는다.

## 재실행

아래 명령은 저장소 루트에서 실행한다. 비공개 경로는 실제 환경에 맞게
지정한다. `MARKET_UPLOADED`는 기존 사용자 ZIP의 추출본이다.
네트워크 수집은 캐시 파일을 재사용하며 초당 약 3.4건 이하로 제한한다.
같은 결과를 재검사할 때는 수집과 `rank`를 반복하지 않고 고정 순위를 사용한다.
선택적인 그림 생성에는 작업용 환경의 `matplotlib==3.10.7`이 필요하다.
등록된 NumPy·pandas 버전이나 저장소 의존성 파일은 변경하지 않았다.

```bash
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export MARKET_PRIVATE=/workspace/us-market-corrected-private-20261115
export MARKET_ORIGINAL=/workspace/us-market-private
export MARKET_UPLOADED=/workspace/us-recovery-input
export CORRECTED_OUTPUT=/workspace/us-corrected-results-20261115
export TOPK_PRIVATE=/workspace/us-topk-private-20261115
export TOPK_OUTPUT=/workspace/us-topk-results-20261115

# 공개 수집을 새로 시작할 경우에만 대상 목록을 준비한다. 기존 목록은 보존한다.
python -m research.us_topk_market_cap_v1.prepare_targets --private "$TOPK_PRIVATE" --uploaded "$MARKET_UPLOADED" --phase targets
python -m research.us_topk_market_cap_v1.collect_facts --private "$TOPK_PRIVATE"
python -m research.us_topk_market_cap_v1.prepare_targets --private "$TOPK_PRIVATE" --uploaded "$MARKET_UPLOADED" --phase classes
python -m research.us_topk_market_cap_v1.collect_filings --private "$TOPK_PRIVATE"
python -m research.us_topk_market_cap_v1.inputs --market-private "$MARKET_PRIVATE" --private "$TOPK_PRIVATE"
python -m research.us_topk_market_cap_v1.rank --market-private "$MARKET_PRIVATE" --private "$TOPK_PRIVATE" --output "$TOPK_OUTPUT"

# 순위 해시 확인 뒤에만 미래 보유 수익에 접근한다.
python -m research.us_topk_market_cap_v1.performance --market-private "$MARKET_PRIVATE" --private "$TOPK_PRIVATE" --output "$TOPK_OUTPUT"
python -m research.us_topk_market_cap_v1.financial_control --market-private "$MARKET_PRIVATE" --private "$TOPK_PRIVATE" --output "$TOPK_OUTPUT"

# 첫 성과표 이후 수행한 2018/2020/2022 원천 표본 점검.
python -m research.us_topk_market_cap_v1.extension --private "$TOPK_PRIVATE" --output "$TOPK_OUTPUT"
# 실제 확장에서는 extension-cik-targets.json의 113개도 받았다.
python -m research.us_topk_market_cap_v1.prepare_targets --private "$TOPK_PRIVATE" --uploaded "$MARKET_UPLOADED" --phase extension
python -m research.us_topk_market_cap_v1.collect_facts --private "$TOPK_PRIVATE" --targets extension-cik-targets.json --receipt-name extension-companyfacts-receipts.json
python -m research.us_topk_market_cap_v1.extension_audit --private "$TOPK_PRIVATE" --uploaded "$MARKET_UPLOADED" --output "$TOPK_OUTPUT"
python -m research.us_topk_market_cap_v1.report --market-private "$MARKET_PRIVATE" --private "$TOPK_PRIVATE" --corrected-results "$CORRECTED_OUTPUT" --output "$TOPK_OUTPUT"
python -m research.us_topk_market_cap_v1.figures --output "$TOPK_OUTPUT"
python -m research.us_topk_market_cap_v1.verify --private "$TOPK_PRIVATE" --market-private "$MARKET_PRIVATE" --original-private "$MARKET_ORIGINAL" --output "$TOPK_OUTPUT" --write-manifest
python -m research.us_topk_market_cap_v1.verify --private "$TOPK_PRIVATE" --market-private "$MARKET_PRIVATE" --original-private "$MARKET_ORIGINAL" --output "$TOPK_OUTPUT"
```

시작할 때의 입력 대상 목록·SEC 영수증·비공개 해시는 분석 환경에 보존했다.
집계는 `results/REPORT-ko.md`부터 읽는다. `results`의 가격/선정 없는 CSV와
검증 영수증만 재배포하며 원 시세·계정 응답·키·개별 미래수익은 포함하지 않는다.
원천별 라이선스는 원래 조건을 유지한다.
