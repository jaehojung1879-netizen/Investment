# 미국 역사 가격 증거 pilot v1

**결론: 공식 issuer 독립 검증 0종목 / 승인 0세션. 확대 중단.** 원자료가 사라진 것이 아니라 공식 SEC·IR와 Yahoo 가격 정의 접근이 프록시 CONNECT 403에서 거부됐다. 자료가 없거나 회사가 틀렸다는 판정이 아니다. #241–#243가 병합된 실제 main `c14080cf9266e5d2b1b6babae8ae3c018c54b93c`에서 작업했다.

[실제 요청·증거 fingerprint·종목별 gate JSON](us-readiness/us-price-evidence-pilot-v1.json)을 제공한다. 이 pilot은 212종목 전체의 일반 준비 감사를 다시 만들지 않는다. JWN → ADS → CTXS를 첫 1–3종목으로 정하고, official source 접근이 실패해 나머지 5종목의 issuer/event 조사는 확대하지 않았다. 종목 교체나 기간 선택에 주가 성과를 사용하지 않았다.

## 실제로 한 독립 확인

**6개 외부 공식 source 요청, 모두 PROXY_CONNECT_403.** SEC submissions(JWN CIK 72333), SEC historical filing 후보 locator, Nordstrom dividend-history, Bread Financial filings, Citrix acquisition press-release 후보 locator, Yahoo 가격 정의 help 페이지를 시도했다. SEC/IR 문서 및 실제 event chain은 0개 확보했다. 프록시가 CONNECT 단계에서 거부해 provider의 HTTP 응답·문서 존재·provider User-Agent 허용 여부는 확인되지 않았다. 실패한 URL을 유효한 filing/announcement 증거로 채택하지 않는다. 다른 proxy, SEC mirror, remote runner로 우회하거나 반복 요청하지 않았다.

반면 허용된 GitHub에서 Source F/D의 지정된 producer와 publisher library 코드 4개를 실제로 읽고 revision·SHA·취득 시각을 남겼다. 회사 증거가 아니라 코드 증거다. 다음 두 가지 새로운 사실을 확인했다.

1. **Source F의 지정된 정상 재현 경로는 잘못됐다.** pinned generator `ace77714…/Working/StockMarketDataAnalysis_p06_GettingStockPricesSP500.py` SHA `23e2e98f913652a209cae8195ab801c71d055507a64cab71fa2ee9936c4c5c22`: line 61 DataReader와 line 62 CSV 저장은 line 57 `except KeyError` 안이다. try에는 ticker 출력만 있어 정상 문자열 출력 경로에서 다운로드가 실행되지 않는다. 제3자 코드를 실행하지 않고 AST로 확인했고 정상 구조를 오탐하지 않는 합성 테스트를 추가했다. **CSV가 가짜/가격이 틀렸다는 증거는 아니다.** 다른 당시 code version이나 manual export였을 수 있지만 실제 producer/version lineage가 없다. 기존의 “이 generator가 이 CSV를 재현한다”는 가정은 쓸 수 없다.
2. **8개 F 파일의 마지막 quote는 모두 2020-05-22**, producer의 end 설정은 2020-05-23이다. source query cutoff를 시사하며 8개 security가 같은 날 종료됐다는 증거가 아니다. index exit·ticker rename·계속 거래·인수·delisting·주식 취소는 별도 공식 증거가 필요하다. 마지막 quote 또는 index exit를 0/현금 payoff로 처리하지 않았다.

[pandas-datareader v0.8.1](https://github.com/pydata/pandas-datareader/blob/c2349174abd5648e88c2c08e75bb27e2e0801d28/pandas_datareader/yahoo/daily.py)의 adjust_price 기본값 False 및 Adj Close 기반 OHLC 변환, [yfinance v0.2.65](https://github.com/ranaroussi/yfinance/blob/ea4dc2d22ae47a84e38f969c509a78fb3ed59cc8/yfinance/utils.py)의 auto_adjust 변환을 실제 코드에서 확인했다. **그 version이 2020 CSV를 만들었다는 증거가 아니며 Yahoo upstream Close가 as-traded인지도 입증하지 않는다.** 컬럼 이름 또는 별도 Adj Close가 있다는 이유로 원거래 가격을 인증하지 않았다.

## 기존 파일 검증과 8종목 결과

`/workspace/pr241-nonpublic-preservation/`의 원본 archive·panel이 남아 있었고 main manifest의 raw SHA `0fa0b576…`, panel SHA `41ef2da7…`와 정확히 일치했다. 기존 admission 엔진을 8종목에만 적용하고 normalized 행을 해당 source CSV와 대조했다. **기존 engine/등록/입력은 수정하지 않았다.**

| 종목 | expected membership 세션 | 후보 양의 종가 | 고정 F publisher 관측 | H63 날짜 존재만 | 최종 ADMITTED |
|---|---:|---:|---:|---:|---:|
| JWN | 1,899 | 1,899 | 1,861 | 1,798 | 0 |
| ADS | 1,635 | 1,635 | 1,597 | 1,534 | 0 |
| CTXS | 2,514 | 2,455 | 1,861 | 1,798 | 0 |
| ALXN | 2,154 | 1,909 | 1,861 | 1,798 | 0 |
| ATVI | 1,924 | 1,784 | 1,070 | 1,007 | 0 |
| ABC | 2,686 | 2,576 | 1,861 | 1,798 | 0 |
| PXD | 2,854 | 2,576 | 1,861 | 1,798 | 0 |
| MRO | 2,995 | 2,575 | 1,861 | 1,798 | 0 |
| 합계 | **18,661** | **17,409** | **13,833** | **13,329** | **0** |

표의 고정 publisher 관측은 경제적으로 “usable”하다는 뜻이 아니다. 13,329개 창도 quote-date 존재만 확인한 것이며 issuer·basis·lineage를 통과한 유효 경제적 H63 창은 0개다. 수익률이나 label은 계산하지 않았다.

8종목 모두 **issuer-linked / verified price-basis / split-dividend lineage / PIT filing-issuer link 독립 통과 수 0**이다. cumulative 통과 수도 0이며 종목별로 JSON에 보관했다. content URL/hash 관문은 13,833세션, dated membership 관문은 17,409세션을 통과했지만 upstream publisher의 economic identity/basis 인증과 구분한다. source가 다른 공백 3,576세션을 splice하지 않았다.

후보 CIK는 JWN 72333, ADS 1101215, CTXS 877890, ALXN 899866, ATVI 718877, ABC 1140859, PXD 1038357, MRO 101778이다. 이는 기존 pinned Finnhub 및 membership metadata의 후보 연결이며 **새로운 공식 issuer/share-class 검증 결과가 아니다**. membership episode도 기존 strictly-earlier snapshot의 관측 구간이지 공식 index effective date가 아니다. actual acquisition/cash consideration/share exchange/delisting 날짜 및 지급액은 문서를 확보하지 못해 미검증으로 남겼다.

PIT filing의 acceptance/publication metadata는 기존 방식으로 읽었지만 price issuer에 연결하지 않았다. retrospective issuer 증거가 확보되어도 그것만으로 미래 financial values나 restatement를 과거 signal에 넣을 수 없다. dividends/splits는 missing 상태를 유지했고 zero event chain을 만들어 내지 않았다.

## 첫 admission을 위한 source 결정

**F 아카이브의 추가 확대를 멈춘다.** 먼저 환경 설정에 `data.sec.gov`, `www.sec.gov`, `press.nordstrom.com`, `investor.breadfinancial.com`, `www.citrix.com`, `help.yahoo.com`의 정상 direct 접근을 허용·적용해야 한다. 현재 editable allowlist를 확인할 수 없어 다른 domain을 덮어쓰는 설정 변경은 하지 않았다. 허용 후에도 provider 접근 성공은 미확인이므로 SEC의 식별 가능한 User-Agent/fair-access 조건을 지키고 provider 403/429이면 중단해야 한다.

재개하면 첫 1–3종목만 공식 historical issuer/class/CIK와 dated corporate-action chain을 확보하고, per-file provider/capture/version 및 as-traded price 정의를 확인한다. 가능한 좁은 기간에 모든 관문이 통과할 때만 HISTORICAL DEVELOPMENT ONLY로 admission한다. 기존 source의 오작동 경로를 고치거나 ticker 이름을 확인하는 것만으로 과거 CSV를 인증할 수 없다.

공식 자료·진짜 가격 basis contract를 확보할 수 없다면 **역사 복구 확대보다 기존 prospective US collection foundation의 owner-gated 보관·권리·운영 준비에 우선순위를 옮기는 것이 낫다**. prospective 데이터도 source terms와 실제 collection 승인 확인이 필요하며 이 PR은 활성화하지 않는다. 접근이 차단된 상태에서 59개 전체의 검증 가능성을 입증했다고 주장하지 않는다. shared F producer 검사만 확장 가능하고 issuer/event source의 scalability는 NOT_MEASURED다.

## 보존과 검증

원자료/파생 가격/제3자 code 전문은 공개하지 않았다. code source·request 기록은 checkout 외부 private staging에 있고 출력 JSON은 provenance/fingerprint/집계만 포함한다. private evidence record 파일을 복원한 경우 아래로 실제 감사 결과를 재현할 수 있다. 두 실행은 byte-identical이었다. 일시적 workspace는 영구 owner-controlled storage가 아니고 데이터 이용·재배포 권리는 새로 허가하지 않는다.

```bash
python scripts/run_us_price_evidence_pilot.py --private-artifacts /owner/private-price-files \
  --private-evidence /owner/private-pilot-evidence --report /tmp/pilot.json
```

raw bytes가 없으면 DATA_UNAVAILABLE을 명시하고 세션 검증 수는 미측정으로 남긴다. removed/dangling GitHub price objects는 사용하지 않았다. Source 요청·control-flow 합성 테스트와 기존 admission/recovery tests, Ruff·compileall·seed·import/script checks 및 전체 pytest/최종-head CI의 실제 완료 결과는 PR 본문에 기록한다. 연구 outcome·IC·calibration·P4·remote lock·model·backtest·production 변경은 없다.
