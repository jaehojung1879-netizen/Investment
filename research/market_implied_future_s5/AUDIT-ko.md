# S5 원천 감사와 실행 결과

`AUTHOR_VALIDATION_ONLY` · 원천 및 측정 단계 · 미국 기준 세션 2026-11-25 종료까지. 2026-11-27 한국시간에 받은 파일을 사용했다. 가격 관측 이후의 투자 성과나 보호 라벨은 읽지 않았다. [#389](https://github.com/jaehojung1879-netizen/Investment/pull/389) · [#292 CLAIM](https://github.com/jaehojung1879-netizen/Investment/issues/292#issuecomment-7221060310)

## 기존 제출 전수 감사

기준 HEAD는 `545b00c6e8560e8d08841e2816f34cda34d7a7eb`, 기준 main은 `b4fde0acd22cf9f54ebf52a1a1885c9c42ba7cc0`이다. 추가 파일 네 개를 독립적으로 읽고 기준 테스트 21개를 실행했다. 최종 변경은 S5 연구 폴더와 기존 S5 테스트 한 파일에 한정했다. [기준 트리](https://github.com/jaehojung1879-netizen/Investment/tree/545b00c6e8560e8d08841e2816f34cda34d7a7eb/research/market_implied_future_s5)

| 대상 | 확인한 결함 또는 타당한 부분 | 변경 |
| --- | --- | --- |
| 기존 README | 전송 장애와 단건 FRED 화면 계산을 적절히 공개했다. 정확한 live 시작과 소급 행을 데이터로 나눌 수 없었다. | 공식 원본 기반 수치, 별도 문서와 영수증, 자료별 보수적 편입일 |
| 기존 수집 | 검증된 실바이트가 없었다. 6M/1Y 미검증 후보 URL과 Cboe 3M 누락이 있었고, 첫 성공으로 끝나 교차 대사가 불가능했다. | Cboe 10개, FRED 2개, CFE 6개를 각자 요청, 헤더·수집시각·바이트·SHA-256·시도 결과 기록. 호스트가 429 또는 챌린지를 돌려주면 그 호스트 요청 중단 |
| 기존 편입·기간구조 | 고정 스키마, 해시, 시간대, 소급 배제와 signed forward가 타당했다. 캘린더 분모가 관측 합집합이고 공표 시각은 미확인이다. | 원본과 영수증 재검증, 완결된 XNYS 기준 세션 분모, 미관측과 행 부재 분리, 현재 공표 스냅숏과 PIT 구분. FRED 일치도 별도 계산 |
| 기존 VRP·상태가격 | (Q-P)의 단위와 동일 가격을 만드는 서로 다른 $P$ 반례가 타당하다. 외부 호출자가 기대분산에 미래값을 넘기면 막을 수 없었다. | 별도 EWMA 기준에서 개별 관측 종료·입수 시각 검증. 호가 부등식을 만족하는 실제 SPXW 상태가격 선형계획, 음의 버터플라이 합성 반례 |
| 기존 테스트 | 실패 처리, 결측·음의 분산, 이론 반례와 FRED 화면 전사 검산 21건 통과 | 파일 변조, 캘린더, 공급자 제한, 선물 월물과 영점, 예측 입력 시각 및 LP에 대한 회귀 테스트 추가 |

## 편입 결과

아래는 원본 첫 행과 보수적 편입일을 별도로 표시한 것이다. 발표일의 일자가 원천에서 확인되지 않은 경우 월 또는 확인된 발표 범위를 기록했다. 10개 Cboe 지수, 2개 FRED 미러, 6개 CFE 계약 파일 모두 열어서 스키마와 단위를 검산했다. HTTP Date와 Last-Modified는 원본 내려받기에 대한 메타데이터다. 해당 거래일의 최초 공개시각이나 수정 전 값을 보장하지 않는다. [Cboe 공식 CSV 목록](https://www.cboe.com/tradable-products/vix/vix-historical-data/) · [만기별 방법론 §2, §6–7, 개정 부록](https://cdn.cboe.com/api/global/us_indices/governance/Volatility_Index_Methodology_Selected_SPX_Target_Expected_Volatility_Term_Indices.pdf) · [원천 대사 JSON](results/source-snapshot.json)

| 지수 | 원본 첫 날짜 | 최초 라이브 발표 근거 | 편입 시작 | 비결측 / XNYS 기준 | 단위 |
| --- | --- | --- | --- | ---: | --- |
| VIX9D | 2011-01-04 | 2013-10-01 VXST 출시 발표 | 2014-01-01 | 3,245/3,245 | 연율 변동성 % |
| VIX | 1990-01-02 | 1993년 OEX 원형, 2003-09-22 SPX 방식 도입 | 2004-01-01 | 5,762/5,762 | 연율 변동성 % |
| VIX3M | 2009-09-18 | 현행 Cboe 원천 방법론 2013-10, 전신 VXV는 2008 거래소 공문과 FRED 2007-12-04 행에서 확인. 전신 최초 공개 일자 미확정 | 2014-01-01 | 3,245/3,245 | 연율 변동성 % |
| VIX6M | 2008-01-02 | 2013-11-27 VXMT 출시 발표 | 2014-01-01 | 3,245/3,245 | 연율 변동성 % |
| VIX1Y | 2007-01-03 | 2018-04-17 공표 개시 | 2019-01-01 | 1,987/1,987 | 연율 변동성 % |
| SKEW | 1990-01-02 | 2011-02-23 공표 예정일이 CBOE 실적 공시에 명시. 실제 최초 틱 미확보. 2025·2026 개정·과거값 재작성 공지 참고 | 2012-01-01 | 3,743/3,747 | 변환 지수 수준 |
| VVIX | 2006-03-06 | Cboe 자료에 2012년 공개 사례. 최초 일자는 미확인 | 2013-01-01 | 3,496/3,497 | 연율 VIX 변동성 % |
| COR1M | 2006-01-03 | 2022-03-18 CSMI 공표 예정, 2022-07-18 확장 공표 확인. 같은 계열의 과거 행은 비라이브로 배제 | 2023-01-01 | 979/979 | 상관계수 ×100 |
| COR3M | 2006-01-03 | 2021-07-01 장중 공표 개시 발표 | 2022-01-01 | 1,230/1,230 | 상관계수 ×100 |
| DSPX | 2014-06-19 | 2023-09-27 출시 발표. 공개 원본의 2018년 0은 소급 구간에 있다 | 2024-01-01 | 729/729 | 연율 분산도 % |

출시 근거에는 서로 다른 VIX 방식과 명칭 변경이 포함된다. 2014-10-06 SPX Weeklys 추가, 2018-06-08 이전 심볼 VXST/VXV/VXMT 변경, 2025-02-10 행사가 선정 개정을 확인했다. 2025년 전후에는 공통 기간구조를 같은 방법론으로 간주할 수 없다. VIX 계열 공식 정상 세션 공표는 09:31–16:15 ET, 지수별 장외 공표 범위는 상이하다. VIX의 2016년 장외 공표 도입과 2021년 공표 종료시각 변경도 공급자 자료로 확인했다. CSV에는 거래일만 있으며, 역사적 공급망 지연과 수정, 정확한 휴장 단축 공표 시각은 미확인이다. [Cboe VIX 방식 연구](https://cdn.cboe.com/resources/education/research_publications/VIXInterpolationWhitepaper.pdf) · [이름 변경 공지](https://cdn.cboe.com/resources/index_values/2018/Reminder-Change-of-Symbols-on-CSMI-Main-Effective-June-8-2018.pdf) · [Cboe 장외 공표](https://ir.cboe.com/news/news-details/2016/CBOE-to-Start-Overnight-Dissemination-of-CBOE-Volatility-Index-VIX-April-15-04-13-2016/default.aspx) · [DataShop 시각·공급 FAQ](https://datashop.cboe.com/faqs) · [2025 개정 공지](https://cdn.cboe.com/resources/release_notes/2025/Modifications-to-the-Strike-Selection-in-Volatility-Index-Calculations.pdf)

[9D 발표](https://ir.cboe.com/news/news-details/2013/CBOE-Introduces-Short-Term-Volatility-Index-10-01-2013/default.aspx) · [6M 발표](https://ir.cboe.com/news/news-details/2013/CBOE-Introduces-The-CBOE-Mid-Term-Volatility-Index-11-27-2013/default.aspx) · [1Y 발표](https://ir.cboe.com/files/doc_financials/2018/Q1/1q18-prepared-remarks.pdf) · [VXV 문서](https://cdn.cboe.com/resources/regulation/rule_filings/approved/2008/SR-CBOE-2008-005.pdf) · [SKEW 공시](https://www.sec.gov/Archives/edgar/data/1374310/000110465911006091/a11-5698_1ex99d1.htm) · [SKEW 2025 결과](https://cdn.cboe.com/resources/release_notes/2025/Consultation-Results-Regarding-Proposed-Changes-to-the-Cboe-SKEW-Index-SKEW-.pdf) · [SKEW 2026 협의](https://cdn.cboe.com/resources/indices/governance/Consultation-Regarding-Proposed-Changes-to-the-Cboe-SKEW-Index-Part-2.pdf) · [VVIX 방법론](https://www.cboe.com/us/indices/dashboard/VVIX) · [COR1M 벤더 공지](https://cdn.cboe.com/resources/index_values/2022/03042022_CSMI_Index_Vendor_Notice_ImpliedCorr.pdf) · [COR 확장](https://ir.cboe.com/news/news-details/2022/Cboe-Expands-Implied-Correlation-Index-Suite-Adds-Eight-Additional-Volatility-Related-Indices-07-18-2022/default.aspx) · [COR3M 발표](https://ir.cboe.com/news/news-details/2021/Cboe-Announces-Launch-of-New-Cboe-3-Month-Implied-Correlation-Index-07-01-2021/default.aspx) · [DSPX 발표](https://www.cboe.com/insights/posts/strong-year-to-date-gains-for-cboes-vpd-vpn-spen-indices/)

FRED VIXCLS와 VXVCLS는 각 5,762일과 3,245일의 겹친 기준 세션에서 Cboe Close와 전부 정확히 일치한다. 두 채널의 일치는 같은 Cboe 계보의 전송 검산이다. ALFRED 당시 빈티지는 확보하지 않았다. 기준 기간 내 VIX 비기준일 관측 34개와 컷오프 뒤 추수감사절 날짜 1개를 별도 기록했다. 이 분류는 XNYS 참조 달력에 상대적이다. [VIXCLS](https://fred.stlouisfed.org/series/VIXCLS) · [VXVCLS](https://fred.stlouisfed.org/series/VXVCLS)

| CFE 표준 월물 만기 | 원본 행 | 만기 전 비결측 정산·거래량·미결제약정 / XNYS 기준 |
| --- | ---: | ---: |
| 2026-09-16 | 184 | 183/183 |
| 2026-10-21 | 187 | 186/186 |
| 2026-11-18 | 188 | 187/187 |
| 2026-12-16 | 173 | 173/173 |
| 2027-01-20 | 154 | 154/154 |
| 2027-02-17 | 129 | 129/129 |

정산은 지수 포인트, 거래량과 미결제약정은 계약 수다. 만기 전 정산 2개 이상 212일, 3개 이상 193일, 컷오프 현재 3개다. 2004-03-26 VX 거래 개시를 확인했다. 표본은 계약 여섯 개의 공개 CSV에 한정된다. 일별 통계 페이지는 공개 가능 시각을 약 10시로 별도 안내하고 시계열 스냅숏은 공개 일시, 시간대, 미결제약정 기준 시점을 행별로 보존하지 않는다. 통계값을 당일 체결에 사용하려면 별도 원본 입수 시각 자료가 필요하다. 만기 SOQ는 당일 오전의 특별 개시가 산출이며 야간·주간 세션과 월물 정산가의 거래일 경계도 다를 수 있다. [CFE 파일 목록](https://www.cboe.com/markets/us/futures/market-statistics/historical-data/futures) · [CFE 통계 공지](https://www.cboe.com/markets/us/futures/market-statistics/daily/futures/) · [VX 및 SOQ 규격](https://www.cboe.com/tradable-products/vix/vix-futures/) · [VX 출시 기록](https://www.federalregister.gov/documents/2010/09/22/2010-23603/)

VKOSPI는 KRX 제품 자료로 2009년 도입을 확인했고, KRX 선물 규격의 2014-11-17 상장을 확인했다. KOSPI 지수 일별 공식 OpenAPI에서 HTTP 401과 47바이트 JSON 인증 요구 응답을 받았다. 이 응답은 인증 의무를 확인하며, 인증 후 해당 API가 VKOSPI를 반환하는지는 미확인이다. KRX Data Marketplace와 금융위원회 파생상품지수 API는 원천 후보이며 공개 시각·소급 시작·제품 범위·이용권을 추가 확인해야 한다. 기존 저장소의 KR 도구는 독립 VKOSPI 원천을 등록하지 않았다. 이번에 편입된 한국 공식 일별 지수·선물 행은 각각 0건이다. [KRX 변동성지수](https://eindex.krx.co.kr/contents/GLB/02/0202/0202010101/GLB0202010101.jsp) · [V-KOSPI 선물](https://global.krx.co.kr/contents/GLB/02/0201/0201040301/GLB0201040301T1.jsp) · [KRX API 목록](https://openapi.krx.co.kr/contents/OPP/INFO/service/OPPINFO004.cmd) · [금융위원회 접근·권리](https://www.data.go.kr/data/15094807/openapi.do) · [응답 증빙](results/krx-access.json)

이 실행은 공식 CSV 배포와 명시된 DataShop 공개 샘플을 이용했다. Cboe 공개 지연 호가표의 자동다운로드 제한을 적용했다. 원본 파일·호가·일별 재구성 값은 작업공간에 보존했다. PR에는 원본 해시·시각·스키마·집계 및 제한된 예시 분석을 기록했다. 상시 이용·재배포·상업 이용과 한국 거래소 인증은 별도 라이선스 확인이 필요하다. [Cboe 시장데이터 정책](https://www.cboe.com/data/market-data-services/document-library) · [DataShop 정책](https://datashop.cboe.com/data-policies) · [FRED 이용조건](https://fred.stlouisfed.org/legal/)

## 기간구조 원본 재현

$v_T$는 연율 변동성 퍼센트, $W_T=(T/365)(v_T/100)^2$는 무차원 누적 분산이다. 인접 구간의 연율 선도 분산 대용치는 $365(W_b-W_a)/(b-a)$다. 만기 $T$는 9/30/93/184/366 달력일이고 $W_0=0$이다. 변동성 퍼센트를 직접 빼거나 계약별 내재 기대를 동일한 선도분산 거래로 취급하면 단위와 상품이 뒤섞인다. 한쪽 만기가 결측인 인접 구간은 결측이며, 음수는 그대로 남겨 진단한다.

| 구간 (일) | 양 끝 관측수 | 음의 부호 | 누적 분산 중앙값, 5만기 공통일 | 선도 연율 분산 중앙값, 각 구간 적격일 |
| --- | ---: | ---: | ---: | ---: |
| 0–9 | 3,245 | 0 | 0.000688 | 0.022261 |
| 9–30 | 3,245 | 0 | 0.002663 | 0.028307 |
| 30–93 | 3,245 | 0 | 0.010708 | 0.038208 |
| 93–184 | 3,245 | 0 | 0.025181 | 0.045366 |
| 184–366 | 1,987 | 0 | 0.054953 | 0.059372 |

5만기 공통은 2019-01-02~2026-11-25 1,987/1,987일이다. 서로 다른 옵션 선정·휴장·시각을 쓰므로, 부호가 모두 양이라는 사실로 달력 무차익을 확정할 수 없다. 정산된 VX 레벨과 선도분산의 차이에는 제곱근, 변동성의 볼록성, 선도 시작 시점, 만기 SOQ, 증거금과 유동성이 모두 관여한다. [계산값·표본수·해시](results/source-snapshot.json)

## SPX 실호가와 합성 반례

공개 데모 ZIP에는 실제 데이터의 일부만 들어갈 수 있다. 2023-08-25 15:45 ET의 SPXW 풋·콜, 2023-09-25 PM 만기 한 개를 지정했다. 행사가 118개, 호가 236건, 매수호가 0인 9건은 하한 0으로 그대로 사용했다. 미국형 주식 옵션과 AM 만기 SPX는 배제했다. 계약은 유럽형 현금결제다. 호가 원본, 계약 분류와 바이트 해시를 검증했다. 이는 거래될 때마다의 당시 관찰가능성을 확보하는 장기 빈티지 자료가 아니다. [Cboe 옵션 샘플](https://datashop.cboe.com/option-eod-summary) · [SPXW 규격](https://www.cboe.com/tradable-products/sp-500/spx-options/spx-specifications/) · [샘플 영수증과 LP 결과](results/option-sample.json)

같은 시각, 만기, 지수의 가격 상·하한을 한꺼번에 만족하는 비음수 $Q$를 찾았다. 할인계수 0.994–0.998, 만기 지수 상한 6,600과 8,800의 두 민감도에서 3,950–4,050 풋 스프레드의 단위 지급액 $Q$ 기댓값은 동일하게 **2.5078–2.9172%**였다. 이는 구간에서 선형으로 증가하는 0–1 지급함수의 기대이며 특정 사건 확률과 다르다. 지수 상한의 두 가정이 해당 지급 범위에 영향을 주지 않았다는 관측은 다른 지급함수 또는 지지집합에도 일반화되지 않는다. 할인구간은 가정이며 관측 금리로 추정하지 않았다. 합성 음의 버터플라이에서 LP는 불가능했고, 합성 $Q$에서 물리적 하방 확률 10%·35%를 만드는 서로 다른 양의 할인요소가 같은 상태가격을 만들었다. [LP와 합성 결과](results/option-sample.json)
