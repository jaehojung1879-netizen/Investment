# #286 추가 원천 검토 — 전략 수익 경로는 계속 미완성

원 HEAD `a62e3688545d5034a5116283e71d35febad34167` 이후의 별도 source inventory다.
기존 명세·코드·결과 50개 및 review_v2 결과는 변경하지 않는다. 새 수익률/선택/모델은 계산하지 않는다.

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

로컬 관련 테스트 **29개 통과**, 원 결과 50개 SHA 및 완성 NAV 30개 대조 통과. 전체 pytest는 기존 봉인
실자료 재계산 테스트가 포함되어 로컬에서 실행하지 않았다. Lint/compile 및 임시 경로의 합성 seed/validation을 확인한다.
Claude의 독립 감사 요청 댓글은 확인했으나 이 변경 시점에 최종 감사 판정은 게시되지 않았다. GitHub CI는
반드시 새 HEAD에 대한 결과를 별도로 확인해야 하며 이 문서가 CI 성공이나 병합 승인을 뜻하지 않는다.
