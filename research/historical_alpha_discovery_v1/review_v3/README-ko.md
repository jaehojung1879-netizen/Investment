# #286 추가 원천 검토 — 전략 수익 경로는 계속 미완성

원 HEAD `a62e3688545d5034a5116283e71d35febad34167` 이후의 별도 source inventory다.
기존 명세·코드·결과 50개 및 review_v2 결과는 변경하지 않는다. 새 수익률/선택/모델은 계산하지 않는다.

[Claude 감사 B1](https://github.com/jaehojung1879-netizen/Investment/pull/286#issuecomment-6383911588)을 재현했다.
원 실행 PNG `results/measured-control.png`는 로컬에만 있고 `.gitignore`의 `*.png` 때문에 Git에 없었다.
보존된 원본 **268,852 bytes**, SHA-256 `e00ba653b110f212123b038a2e434a2c1702e310534df9bfdff0961927aae1ce`가
원 manifest와 정확히 일치함을 확인한 뒤 그 바이트를 포함했다. 그림을 재생성하거나 notebook 이미지를 대체하지 않았다.
manifest의 모든 파일이 Git에도 있는지 검사하는 회귀를 추가했다. 이전 50개 검증 주장은 로컬 존재 검사였고,
이 수정 전에는 저장소만으로 50개를 재현할 수 없었다.

`source_inventory.py`는 이미 보존된 009830·012450의 연차 공시 **46개 section**을 직접 검색하고,
manifest·archive·section SHA를 검증한다. 검색 범위는 저장된 회사 개요/주식 관련 section이며 모든 DART 공시가 아니다.
`source-inventory.json`의 URL·SHA로 조사 범위를 확인할 수 있다. 외부 요청이나 새 데이터 저장은 없다.

- **009830:** 발견된 FY2019 `0.6392187:0.3607813`은 자회사 한화글로벌에셋/한화큐셀앤드첨단소재 거래다.
  2023년 모회사 주주가 받을 갤러리아 권리로 사용할 수 없다. 정확한 배정·기준일·인도·단주 정산과 452260 가격 연결이 미확인이다.
- **012450:** 2024년 인적분할 사실은 확인되지만 저장된 section만으로 489790 주주 권리·단주 정산을 확정하지 못했다.
  상장주식 수 감소나 vendor `0.90028`에서 권리 비율을 추정하지 않는다.
- **002790/090430/006800:** 이전 감사의 제한된 종료 가치 검토를 유지한다. 정지 기간 일별 mark 및 전체 분배 기준이 해결된 것으로 승격하지 않는다.

따라서 원 H126 장중 전략의 24블록 중 4개 차단 및 전체 CAGR/Sharpe/MDD `null`은 유지한다.
주식 부분 분배와 ETF 총배당의 비교 한계, 2019 거래세 metadata 모순도 유지한다.
원래 **추가 알파 입증 실패**라는 결론을 바꾸거나 유효 블록만 연결하지 않는다.

**해석 정정:** H126의 19/24 유효 쌍은 기업 이벤트에 의존해 탈락한 complete-case 기술통계다. 미해결
5쌍을 포함한 전체 효과나 신뢰구간을 식별하지 못하며, 구간이 0을 포함한다는 사실을 전체 모집단의 검정으로
확대하지 않는다. 불리한 수익을 임의로 배정하는 민감도 계산도 새로 하지 않는다. 누락된 양(+) 배당만
놓고 보면 주식 부분 분배 기준은 완전 총배당 ETF보다 주식 책에 불리하지만, 종목별 누락액·그 영향의
크기는 입증하지 못했다. 기존 야간 책의 ETF 대비 격차를 순수 종목 선택 알파나 그 부재로 해석할 수 없다.

**2019 명세 정오표:** `2019ConservativeFullYear: 30`은 같은 명세의 note 및 결과 전 실행 코드와 모순된다.
실제 고정 실행은 2019-06-03부터 25bp를 적용했다. 원 명세/코드/결과를 수정하거나 비용 정책을 사후 선택하지 않는다.
소유자의 2026-10-24 새 역사 탐색 지시에 따른 별도 EXPLORATORY 연구이며 봉인 연구의 재개·재실행이 아니다.

재현은 전략 실행이 아닌 원천 inventory와 합성 무결성 검사다:

```bash
python -m research.historical_alpha_discovery_v1.review_v3.source_inventory
python -m pytest -q research/historical_alpha_discovery_v1/test_discovery.py research/historical_alpha_discovery_v1/review_v2/test_audit.py research/historical_alpha_discovery_v1/review_v3/test_source_inventory.py
```

다음 탐색은 이 장중 가설의 순위·기간·결측 정책을 조정해 구제하지 않는다. 우선순위는 #287의 이미 고정된
**영업이익 양전환 AND 현금흐름 마진 개선**이라는 별도 경제 가설이다. 현재 수준·모멘텀·규모 기준선에 대한
추가 정보, 동일 날짜/산업/규모 통제와 H126 비용 후 SPY 상대수익을 함께 검증한다. 기존 노출 역사이므로
시간순 분리만으로 독립 OOS라고 부르지 않는다. H252 확장은 새 사전 명세와 승인 없이 추가 실행하지 않는다.
WID source admission과 정확한 실행 manifest에 대한 소유자 승인이 완료되기 전에는 라벨/모델을 실행할 수 없다.

로컬 관련 테스트 **30개 통과**, 원 결과 50개 SHA 및 완성 NAV 30개 대조 통과. 전체 pytest는 기존 봉인
실자료 재계산 테스트가 포함되어 로컬에서 실행하지 않았다. Lint/compile 및 임시 경로의 합성 seed/validation을 확인한다.
위 감사의 B1에 대응했으며 수정된 HEAD의 독립 재감사는 별도다. GitHub CI는
반드시 새 HEAD에 대한 결과를 별도로 확인해야 하며 이 문서가 CI 성공이나 병합 승인을 뜻하지 않는다.
