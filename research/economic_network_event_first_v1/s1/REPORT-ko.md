# 기업·산업 충격 전달과 시장의 정보 반영 지연

2026-11-27 KST · Investment 원천 연구 · main `3150c70017432e3b73321fbda47ebea226bf8d2b`

## 요약

**원천 파일럿은 계속할 가치가 있고, 확증 실증과 정식 사전등록은 보류합니다.** SEC 연차공시 125건에서 충격 전 확인 가능한 기업 관계를 복원했습니다. 2024-04-02 UTC 스냅샷에는 25개 기업 노드와 23개 방향 관계가 있으며, 이 중 17개는 명시된 판매·구매 관계입니다. 한국에서는 삼성전자 FY2023 보고서의 사업부별 공급관계 11개 행과 Investment의 한국 산업분류 260종목 중 ICIO에 대응시킬 수 있는 131종목을 별도로 확보했습니다.

**가장 유력한 새 후보는 ‘공급 대체에 걸리는 시간’과 ‘동일 공장의 제한으로 동시에 막히는 대체 경로’입니다.** Spirit → Boeing → 항공사에서는 직접·간접 경로를 같은 충격 안에서 비교할 수 있습니다. Southwest의 단일 기종과 United의 혼합 기종은 출발점입니다. 기존 기종의 보유 사실이 예정 인도를 대체할 수 있는 능력을 보장하지 않으므로, 기종 인증·인도 슬롯·임차 가능성까지 충격 전에 기록해야 합니다. [Spirit FY2022 10-K](https://www.sec.gov/Archives/edgar/data/1364885/000162828023004051/spr-20221231.htm) · [Southwest FY2022 10-K](https://www.sec.gov/Archives/edgar/data/92380/000009238023000010/luv-20221231.htm) · [United FY2022 10-K](https://www.sec.gov/Archives/edgar/data/319687/000010051723000048/ual-20221231.htm)

**사건 수가 병목입니다.** BLS 작업중단 94건을 고용주·노조·Local과 90일 규칙으로 접어 91개 후보 에피소드를 얻었습니다. 별도 사건 원장에는 8개 충격과 18개 경로 검토 행이 있으며, 충격 전 명시적 관계와 전달 방향을 확인한 것은 4개 충격·9개 경로입니다. 4개는 인과적으로 독립인 확증 표본으로 인정되지 않습니다. 독립 4건을 가정해도 80% 검정력의 최소 효과는 2.72 사건 표준편차입니다. 성과를 조회하거나 계산한 건수와 정식 사전등록 관문을 통과한 가설은 각각 0입니다. [BLS 상세 원장](https://www.bls.gov/web/wkstp/monthly-listing.htm)

## Stage 0 · Investment의 기존 연구와 중복 여부

| 기존 연구 | 이번 연구에서 달라지는 관측 단위와 비교 |
|---|---|
| #188 시장·산업 기반, #193 산업 상대 모멘텀, #212 PIT 특성 행렬 | #188의 ECOS 최신 개정 이력은 최초 공표일이 확인되지 않았습니다. #193의 산업 수익률·지수 집중 효과와 #212의 기존 요인은 향후 통제입니다. 이번 입력은 공시된 **거래 방향·제품·사업부**와 실제 생산 차질입니다. |
| #343–#346, #349–#352 | S2 분해, 동업종·동규모 매칭, ETF 복제와 한 슬롯 교체는 비교 설계에 참고합니다. 기존 종목 순위·슬롯·비중 실험은 그대로 보존합니다. #344는 별도 미국 Top-K 자료 감사입니다. |
| #347–#348, #353–#354 | 펀드 보유, 내부자 장내매수, 자체 실적 기대·서프라이즈는 별도 정보입니다. #348과 #353의 공개일·CUSIP·중복·시총 정정은 향후 비교군 검증에 적용할 교훈입니다. |
| #355–#356, #360과 #371 N2 | 설비투자 사이클, 반도체 수출 가속도, 수출 속보, 생산·출하·재고는 산업×월 비교입니다. 같은 수출 가속도와 재고 가설은 봉인 상태로 둡니다. 이번 분석의 단위는 충격×기업×방향 경로입니다. #371의 IIP 보강은 담당 연구 기록을 사용합니다. |
| #357–#359 및 #361 | Shiller/ALFRED 기반 ETF 비중·시장 위험 및 Jarociński–Karadi 계열 거시 충격 연구와 달리, 공장·노조·규제·자연재해에서 시작해 미시 경로와 공통 산업 노출을 비교합니다. |
| #310, #327 | #310은 동업종의 조기 자체 실적을 이용했고, 효과가 일부 산업에 집중됐습니다. #327은 공시한 기업 자신의 대형 공급계약을 시험했으며 H126 주장은 종료가격 원천으로 막혔습니다. 이번 관계의 공시는 충격 전에 고정하고 외부 거래상대·설비에서 시작한 사건에 연결합니다. |
| #371·#383 | N1 보유목적, N2 반도체 실물, N3 군집 매수, N4 가이던스, Item 4.02 원천 검증을 재수행하지 않았습니다. #383 v4의 발행사 분리 test3 F1 0.39와 PASS_TO_PREREG 0을 반영해 가이던스 파서와 분기 전망치를 핵심 입력에서 제외했습니다. |

최신 #292에서 Claude가 병합 순서를 관리하고 #382·#383을 별도 Codex 작업으로 맡긴 기록 및 #382의 11월 27일 인계를 확인했습니다. 이번 작업은 해당 브랜치와 수집기, 봉인 결과, 전향 원장, 운영 정책을 건드리지 않은 읽기 전용 소스 연구입니다. [증거 원장](https://github.com/jaehojung1879-netizen/Investment/blob/3150c70017432e3b73321fbda47ebea226bf8d2b/research/next_alpha_program_v1/EVIDENCE-MAP-ko.md) · [Control Tower #292](https://github.com/jaehojung1879-netizen/Investment/issues/292#issuecomment-7193162686) · [#371 분담과 복구](https://github.com/jaehojung1879-netizen/Investment/issues/371#issuecomment-7140929708) · [#383](https://github.com/jaehojung1879-netizen/Investment/pull/383)

## 선행연구와 이번 설계의 차이

| 연구 | 설계에 반영한 관찰과 한계 |
|---|---|
| Cohen & Frazzini (2008), Hou·Xue·Zhang (2020), `Customer Momentum` (2023) | 고객 주가의 공급사 후행 관계는 원 연구와 일부 재현 문헌에서 관측됐습니다. 2023 연구에서는 발견 후 표본의 크기와 유의성이 떨어졌습니다. 기업별 과거 수익률을 외생 충격으로 두면 공통 뉴스, 원 종목의 드리프트, 위험 노출을 함께 가져올 수 있습니다. [원 연구](https://doi.org/10.1111/j.1540-6261.2008.01379.x) · [재현](https://academic.oup.com/rfs/article/33/5/2019/5236964) · [후속 표본](https://arxiv.org/abs/2301.11394) |
| Acemoglu 외 (2012), Barrot & Sauvagnat (2016), Boehm·Flaaen·Pandalai-Nayar (2019) | 중심도에 따른 총량 증폭, 투입 특수성과 고객사 실적, 도호쿠 이후 수입 투입이 생산에 미친 충격을 각각 제시합니다. 산업 평균 투입 비중, 기업 관계, 특정 품목의 실제 대체 가능성을 다른 변수로 둡니다. [Acemoglu 외](https://doi.org/10.3982/ECTA9623) · [Barrot & Sauvagnat](https://doi.org/10.1093/qje/qjw018) · [Boehm 외](https://doi.org/10.1162/rest_a_00750) |
| Hoberg & Phillips (2018), Lee·Sun·Wang·Zhang (2019), Cohen & Lou (2012) | 텍스트 경쟁사, 특허 지식 근접도, 다사업부 기업의 정보처리 복잡성은 서로 다른 설명입니다. 제품 텍스트와 특허를 별도 대조로 사용하고, 사업부 수와 내부거래 제거 전후 비중을 기록합니다. [텍스트 모멘텀](https://doi.org/10.1017/S0022109018000479) · [기술 연결](https://www.sciencedirect.com/science/article/pii/S0304405X18303167) · [다사업부 기업](https://www.nber.org/papers/w16749) |
| Carvalho 외 (2021), Lafrogne-Joussier 외 (2023), Baqaee & Farhi (2022), Pichler 외 (2022) | 일본 지진의 상·하류 네트워크, 중국 초기 봉쇄에 노출된 프랑스 수입기업의 재고 완충, 공급·수요 제약의 동시 작동, 재고를 반영한 동적 IO를 비교했습니다. 단기 생산 차질과 재고 소진 후의 반응을 별도 시계로 설정합니다. [일본 생산망](https://doi.org/10.1093/qje/qjaa044) · [프랑스 수입기업](https://www.insee.fr/en/statistiques/7452519) · [비선형 생산경제](https://www.aeaweb.org/articles?id=10.1257%2Faer.20201229) · [동적 IO](https://doi.org/10.1016/j.jedc.2022.104527) |
| Cen·Hertzel·Schiller (2025), Inoue & Todo (2024), Wu·Shi·Luo·Zhao (2026 온라인) | 주의력의 외생 변동, 공급망 뉴스의 전달, 자회사 거래를 상장 모회사에 연결한 간접 경로까지 이미 문헌에 있습니다. 새 가설의 범위는 **공장·품목별 충격, 대체 가능성, 경로 길이와 공통 병목의 상호작용**입니다. 2026 온라인 논문은 단계가 깊을수록 가격 반영이 덜 초기에 집중된다고 보고합니다. 상세 비용 검증은 공개 초록에서 확인되지 않았습니다. [주의력](https://doi.org/10.1287/mnsc.2023.00291) · [공급망 뉴스](https://www.rieti.go.jp/jp/publications/dp/24e077.pdf) · [Tier-1 이후](https://doi.org/10.1016/j.pacfin.2026.103355) |
| Herskovic 외 (2020), McLean & Pontiff (2016), Chen & Velikov (2023) | 고객 집중은 기업 변동성의 설명이기도 합니다. 알려진 이상현상의 발표 후 감쇠와 마찰 후 성과 축소를 별도로 고려합니다. 공급망 수익률 차이가 나타나면 시장 하락기에 함께 나빠지는 노출, 유동성, 반전, 거래비용을 경쟁 설명으로 검정합니다. [네트워크 위험](https://doi.org/10.1086/710345) · [발표 후 감쇠](https://doi.org/10.1111/jofi.12365) · [비용](https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/zeroing-in-on-the-expected-returns-of-anomalies/945133D5A3ECEEAF466AEE91551FD225) |

네트워크 과학의 기업 단위 모형은 공급사 교체와 병목의 비선형성을 강조합니다. 시스템 식별에서는 알려진 입력 충격과 충분히 독립적인 방향별 변동이 있어야 지연 커널을 추정할 수 있습니다. 공통 기점의 기업 여러 곳을 독립 변동으로 세지 않는 것은 shift-share 설계에서도 핵심입니다. 2026년 미 Census 작업논문은 자연재해의 국경 간 전파를 다룹니다. 이 결과는 외부 연구 증거이며 Investment 표본의 성과 증거가 아닙니다. [Inoue & Todo 기업망](https://doi.org/10.1038/s41893-019-0351-x) · [Borusyak·Hull·Jaravel](https://www.nber.org/papers/w24997) · [US Census WP 26-55](https://www.test.census.gov/library/working-papers/2026/adrm/CES-WP-26-55.html)

## Stage 1 · 실제로 구축한 다층 연결망

| 층 | 확보한 연결과 품질 |
|---|---|
| 실제 공급·구매 | SEC 32개 CIK의 2022–25 연차공시 125/125건 확보. 초기 32개 중 21개가 망의 단말이며 4개는 추가로 이름을 확인한 거래상대입니다. 달력 2024-04-02 UTC 이전 공개 및 결산일 550일 규칙으로 23개 관계·25개 노드. 판매 12, 구매 5, OEM과 Tier 1 혼합 3, 최종고객 2, 실명 고객이지만 송장 상대 미확인 1. 16/23개에 공급사 매출 등 명시된 분모가 있습니다. 구매사 점유율과 혼용하지 않습니다. |
| 산업 투입산출 | BEA 2017 Use 상세표에서 397개 상품 코드와 대응 구매산업의 양수 43,541셀, 음수 조정 3셀. OECD ICIO의 KR·US·JP·TW 2026판 2024 거래에는 200개 노드와 양수 36,569셀. 산업 평균 투입과 회사 거래는 서로 다른 관측입니다. |
| 제품시장 | Dartmouth TNIC-3와 ETNIC-3 원본을 받아 1988–2023 범위를 확인했습니다. 2023년 자기연결·대칭 복제를 제외한 행은 각각 333,025 / 328,870입니다. 허가된 시점별 GVKEY–CIK 연결은 0개 검증. 공시 Item 1에서 독립 TF-IDF를 만들었고 26/32개 및 전체 325쌍을 산출했습니다. DAL–LUV 0.554, ADNT–LEA 0.496, QRVO–SWKS 0.494가 나왔으나 BDX–WMT도 0.519입니다. 이 오류 가능성 때문에 텍스트는 경쟁사의 확정표가 아닌 대조 후보입니다. |
| 기술 | USPTO 원문 14개·조직 7곳의 공개일과 표지 CPC를 확인했습니다. 표지의 선택 CPC 교집합 4쌍에 Boeing–Hexcel(B29C), Qorvo–Skyworks(H04B)가 들어갑니다. 키워드로 선정한 특허의 제한된 예시이며 특허 포트폴리오 대표성이나 상업적 대체를 판정할 수 없습니다. |
| 공통 고객·수요 | SEC 망에서 공통고객 17개 기업쌍–고객 삼중항, 기업쌍 16개입니다. 텍스트 점수를 붙일 수 있었던 것은 12/17개 삼중항입니다. P&G·Colgate·Kimberly-Clark·Kraft Heinz는 Walmart로 모입니다. Cirrus·Qorvo의 Apple 노출은 계약제조사를 통하는 최종 수요입니다. 공통 고객 관측은 공통 충격 실현과 구별합니다. |

삼성전자 영문 원문은 2024-04-30 공개가 확인됩니다. 11개 공급관계 예시 중 상장 심볼 참조 9개, 비상장·모회사 미연결 2개입니다. 삼성전기 1개는 특수관계사로 표기했습니다. DS의 웨이퍼 13.7%와 화학품 15.7%는 **DS 원재료 항목의 비중**입니다. SUMCO, SK Siltron 또는 Soulbrain 개별사의 몫으로 배분할 근거가 없습니다. 매출은 DX 65.7%, DS 25.7%, SDC 12.0%, Harman 5.6%, 내부거래 등 −9.0%로 공시돼 사업부별 합계의 분모를 대사했습니다. 따라서 회사 단일 산업 분류로 공급 대체성이나 매출 노출을 대표시키지 않습니다. [삼성전자 공개 게시물](https://www.samsung.com/global/ir/reports-disclosures/public-disclosure-view.84175/) · [사업보고서 24–26쪽](https://images.samsung.com/is/content/samsung/assets/global/ir/docs/2023_4Q_Interim_Report.pdf)

### 원천별 공개 시점·재현성

| 원천 | 확보, 공개와 이용 조건 | 연결·적격성 |
|---|---|---|
| 한국은행 | 2020 기준년 최초 발표 2024-04-29, 해설 PDF 2024-09-30 확보. 2024 연장표와 2010/15/20 접속표는 별도 발표입니다. 거래·계수 행렬은 해설에서 빠지고 ECOS에 있습니다. #188의 기존 ECOS Actions 원천 검사 성공을 확인했으나 6축 거시 통계용이고 대상 거래행렬의 최초 바이트 증거는 없습니다. 첨부별 공공누리·이용 조건과 ECOS 수집 경로를 따라야 합니다. | 한국은행 거래행렬 적격 0개. OECD 한국 블록과 분리. [2020 발표](https://www.bok.or.kr/portal/bbs/B0000501/view.do?menuNo=201264&nttId=10083834) · [2024 연장표](https://www.bok.or.kr/portal/bbs/B0000501/view.do?menuNo=201264&nttId=11064895) · [기존 Action](https://github.com/jaehojung1879-netizen/Investment/actions/runs/37080934658) |
| OECD ICIO | OECD 공개 CSV ZIP에서 2023·2025·2026 regular 빈티지 3개를 받았습니다. 2026판 전체 1995–2024, 최신 regular 95개 경제권, 이번 분석은 4개 경제권입니다. 2025판 공개 글은 2025년 11월이며 확보한 2025판 2020 CSV는 2026년 1월 제작본입니다. 2023판 2020 CSV는 ZIP 내부 2024-02, 2026판은 내부 2026-10입니다. 내부 생성일과 HTTP 수정 시각은 최초 공개 시각의 대용으로 쓰지 않습니다. OECD 용어에 따른 출처·판본 표시와 제3자 권리 예외를 따릅니다. | 2020년을 공통 180노드로 맞춘 뒤 일본 전자 → 한국 전자 투입/구매산업 산출이 1.0335% → 0.6269% → 0.5894%로 달랐습니다. 대만 → 한국 전자는 1.3971% → 0.9622% → 0.9046%. 2026판을 과거 사건에 붙인 PIT 관측 0개. [판본·파일](https://www.oecd.org/en/data/datasets/inter-country-input-output-tables.html) · [2025 공개 글](https://www.oecd.org/en/blogs/2025/11/oecd-inter-country-input-output-icio-tables-and-trade-in-value-added-tiva-database-launch-of-the-2025-edition.html) · [이용 조건](https://www.oecd.org/en/about/terms-conditions.html) |
| BEA | 2007/2012/2017 기준년 Use XLSX에 접근했습니다. 2023 종합 수정은 공개 일정이 있으나 확보 파일의 Last-Modified는 2024-05-23입니다. 이번 2017 표는 상품×사용산업이며 행과 열의 상품·산업 코드 대응을 맞췄습니다. 주석이 없는 빈 셀은 양수 연결을 세는 용도로만 0 처리했습니다. | 397×397 중 코드 비대응, 무산출, 조정·최종수요를 제외한 표. 시점별 원본 파일 미확인, 과거 기점의 정밀 PIT 적격 0개. [BEA 계정](https://www.bea.gov/itable/input-output) · [종합 갱신 공지](https://www.bea.gov/information-updates-national-economic-accounts-2023) |
| TNIC·ETNIC | 연구실 공개 ZIP과 README를 확보. TNIC-3 27,161,830행, ETNIC-3 37,248,753행. 파일 Last-Modified 2024-11-20 / 2025-01-10은 확보본 식별용입니다. 원래 매핑은 WRDS의 확장 CIK–GVKEY를 이용합니다. ETNIC는 연도별 doc2vec을 학습하고 2025년 초기 배포로 표시됩니다. 판본 공개일과 각 10-K 공개일을 함께 검증해야 합니다. | 공개 다운로드 조건에서 학술 출처를 표기했습니다. 제3자 GVKEY 연결·재배포 권리를 확인하지 못해 공급자 원본은 링크·해시로 남겼습니다. [TNIC](https://hobergphillips.tuck.dartmouth.edu/tnic_basedata.html) · [ETNIC](https://hobergphillips.tuck.dartmouth.edu/tnic_doc2vec.html) |
| SEC | 공개 EDGAR submissions/10-K·20-F·40-F을 받았고 접수 시각 UTC와 accession별 원문 해시를 기록했습니다. SEC fair access의 10req/s 상한과 이용 안내가 적용됩니다. 수정본·8-K 전출이나 실제 공개 지연이 확인되면 늦은 시각을 사용합니다. | 직접 관계 17개는 **이 파일럿에서 찾아낸 수**입니다. 임의 산업 모집단의 발견율이나 비공개 거래의 부재로 해석할 수 없습니다. [SEC API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) · [SEC 접근 정책](https://www.sec.gov/about/developer-resources) |
| DART·Investment | OpenDART는 키 필요. 공개 뷰어 직접 접근에서 503을 관찰했습니다. 기존 main의 DART 연차보고서 매니페스트 26개에서 2013–25, 253종목·2,533건 사업 섹션 HTTP 200 기록을 확인했습니다. batch-13 압축본과 7개 사례의 사업 섹션 원문을 해시 대조했습니다. 일부는 ‘사업의 개요’ 하위 섹션만 보존돼 있어 거래처 표를 통과한 것으로 계산하지 않았습니다. #292의 DART 회계 Actions는 사업부·거래처 표를 받는 워크플로가 아닙니다. | V4 한국 코드 131/260은 현재 기준 보수적 라벨 매핑, 18개 ICIO 산업입니다. 역사적 공개일·연속 상장 식별·사업부 가중치까지 확인한 종목은 0입니다. OpenDART 새 인증 호출 없이 기존 원본과 삼성 IR을 이용했습니다. [OpenDART 약관](https://opendart.fss.or.kr/intro/terms.do) · [DART 보존 매니페스트](https://github.com/jaehojung1879-netizen/Investment/blob/3150c70017432e3b73321fbda47ebea226bf8d2b/data/kr-industry-membership-foundation-v2/acquired-dart/annual/batch-13/manifest-originals.json) |
| 공식 특허 | USPTO 공개 공보 PDF의 공개일·표지 CPC·출원인/양수인을 보존했습니다. USPTO가 안내하는 현재 PatentsView는 ODP입니다. 구 S3 bulk 엔드포인트는 403이었고 ODP의 전체 패널 취득은 이번 파일럿에서 확인하지 못했습니다. 공보의 공개일을 사용했으며 출원일이나 현재 CPC의 소급 적용을 배제합니다. | 14 문서·7 조직 데모. 전체 공개특허→역사적 모회사와 패밀리 중복 제거는 미충족. [USPTO PatentsView](https://www.uspto.gov/ip-policy/economic-research/patentsview) · [공보 예시](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/20220069849) |

### 기업 계약이 드러낸 산업표의 맹점

BEA 2017표에서 항공기 제조 상품(336411) → 항공운송(481000)의 **중간사용**은 16억 8,200만 달러로 구매산업 산출의 0.784%입니다. 항공기 부품(336413) → 항공기 제조(336411)는 같은 기준 12.15%입니다. 반면 Southwest 사업보고서에는 전체 운항 기종과 향후 확정 인도가 Boeing 737에 묶여 있습니다. 중간투입만으로는 신규 항공기가 고정투자로 취급되는 부분과 기존 기단의 교체 지연을 포착하기 어렵습니다. **고정자본의 교체 지연**을 별도 후보로 둡니다. 원재료·부품의 조업 지연이 회복된 뒤에도, 취소할 수 없는 인도 슬롯과 기종별 인증에 묶인 구매사는 6~12개월 공급능력 제약을 겪을 수 있습니다. 반증은 대체 기종·임차·인도 슬롯으로 예정 공급능력을 회복하는 사례입니다. [BEA Use XLSX](https://apps.bea.gov/industry/xls/io-annual/Use_SUT_Framework_2017_DET.xlsx) · [Southwest 10-K](https://www.sec.gov/Archives/edgar/data/92380/000009238024000027/luv-20231231.htm)

## Stage 2 · 실제 사건과 전달 방향

BLS 2023/24/25에 33/31/30개 작업중단 행이 있습니다. 동일 고용주 문자열·노조·Local의 중단이 90일 이내 이어지면 접었습니다. Prime Healthcare 2행과 University of California Health 3행이 각각 하나로 줄었습니다. 복수 노조나 유사 고용주명 병합은 보수적으로 제한했으므로 91은 확증 독립 수가 아닌 원장상의 후보 수입니다. UAW의 3개 완성차사 및 후속 파업 확대는 같은 교섭 에피소드입니다. [BLS 원장](https://www.bls.gov/web/wkstp/monthly-listing.htm) · [UAW 발표](https://uaw-newsroom.prgloo.com/press-release/uaw-launches-historic-stand-up-strike-against-big-three-automakers) · [연준 사건 연구](https://www.federalreserve.gov/econres/notes/feds-notes/tapping-the-brakes-the-effect-of-the-2023-united-auto-workers-strike-on-economic-activity-20240416.html)

| 충격 | 첫 공개 확인과 사전 전달경로 | 판정 |
|---|---|---|
| 2023-06 Spirit Wichita | 회사 발표 06-22 06:24 UTC. BLS 중단일 06-23. Spirit→Boeing 직접, Boeing→Southwest·United의 MAX 주문을 통한 2단계. | 경로 확인. 중단 기간과 실제 항공사 인도 효과는 미검정. [발표](https://www.prnewswire.com/news-releases/spirit-aerosystems-to-suspend-factory-operations-301857718.html) |
| 2023-09 UAW | 09-15 시작. GM·Ford·Stellantis→Lear, Stellantis→Adient 수요 방향. Gentex는 GM 직판과 Tier 1이 섞여 별도. | 경로 확인. 공급사별 해당 공장 노출·협상 예상 시각 보강 필요. [Lear 원 공시](https://www.sec.gov/Archives/edgar/data/842162/000084216223000011/lear-20221231.htm) |
| 2024-04 Hualien | 진원 발생 04-02 23:58:12 UTC. USGS 보존 상품의 초기 origin 갱신 04-03 00:09:47 UTC, TSMC 6-K 접수 04-03 15:13:36 UTC. TSMC→Cirrus 직접. Cirrus→계약제조사→Apple은 경로 가설. | 기업 경로 확인. 최초 공개 거래 시각 및 영향 공장·라인의 매칭은 보류. [USGS](https://earthquake.usgs.gov/earthquakes/eventpage/us7000m9g4) · [TSMC 첫 6-K](https://www.sec.gov/Archives/edgar/data/1046179/000104617924000034/a20240403.htm) |
| 2024-09 Boeing 상업기 | 09-13 중단. Boeing→항공사 공급, Boeing에서 Spirit 방향 주문 충격. HXL의 혼합 OEM 노출과 ATI의 프로그램 미식별은 보조. | 경로 확인. 09-08 잠정합의와 표결 전 기대를 반영할 별도 시계 필요. [Boeing 잠정합의](https://boeing.mediaroom.com/Boeing-Historic-Contract-Offer-and-Tentative-Agreement-with-IAM-Districts-751-W24) · [IAM 원문](https://www.iam751.org/Aero%20Mechanic/2024/September_2024_AeroMechanic_Web.pdf) |
| 보류 4개 | Wabtec–Union Pacific 주문은 있었으나 Erie 중단이 해당 주문에 미친 범위 미확인. FAA MAX 증산 금지는 1월 사고·초기 조치와 같은 정보군으로 기록. Helene Baxter는 IV·투석액 업종 노출만 확인. 2025 Boeing St. Louis 방산 파업은 상업기 관계를 적용할 수 없음. | 상기 4개와 분리. [Wabtec 고객 주문](https://www.up.com/press-releases/service/wabtec-battery-electric-nr220128) · [FAA](https://www.faa.gov/newsroom/faa-halts-boeing-max-production-expansion-improve-quality-control-also-lays-out-extensive) · [Baxter](https://www.sec.gov/Archives/edgar/data/10456/000162828024041545/bax-20240929xex991.htm) · [IAM 방산](https://www.goiam.org/press-releases/iam-district-837-members-in-st-louis-reject-latest-boeing-offer-strike-for-fair-contract/) |

Spirit와 Boeing은 기점은 다르지만 Boeing 경로를 공유합니다. 공급·수요 양방향, 여러 고객, 반복 보도, 기록 정정을 개별 shock으로 올리지 않았습니다. 짧은 창에서는 날짜 겹침, 긴 창에서는 같은 네트워크와 시장 기간의 의존성으로 유효 N이 줄 수 있습니다. 4개 독립을 가정하면 양측 5% MDE는 2.13 SD, 두 가설 보수적 가족 기준 2.5%에서는 2.72 SD입니다. 4개 부호 무작위화의 최소 양측 p값도 0.125입니다. 0.50 SD에는 독립 41개, 0.30 SD에는 109개가 필요합니다. 최소 경제효과에 필요한 실제 분산은 성과와 결과 라벨을 열지 않아 미산정입니다.

## Stage 3 · 사전등록에 포함할 조건부 명세

**상태는 `SOURCE_ONLY`입니다. 정식 등록 통과 0건.** 아래는 사건 원천이 관문을 넘으면 동결할 설계이며, 파일럿 8개는 규칙·크기·분류 진단용으로 격리합니다.

| 검증 질문 | 사전 정의와 반증 기준 |
|---|---|
| 수요·공급 방향과 대체 가능성 | 독립 공장중단의 고객사 인도·생산, 고객사 가동중단의 공급사 주문·출하를 각각 부호화합니다. 1차 물리 지표는 제품별 출하/인도의 20거래일 또는 가장 가까운 월 관측입니다. 사건에서 공급 복구를 기다린 시간과 대체 설비 승인 소요의 상호작용을 비교합니다. 고대체·저대체의 충격 차이 기준 후보는 5%p 인도율입니다. |
| 단계 수와 정보 처리 | 1단계와 2단계는 사전에 문서로 연결된 것만 포함합니다. 직접과 간접의 실제 조업 시계가 같을 때만 공시·가격 반영의 지연과 정보 불투명도를 비교합니다. 공개 지점부터 [0,1], [2,5], [6,20] 거래일 구간을 고정하며 20일 지연 효과의 경제 기준 후보는 25bp입니다. 가격 검정은 별도 승인과 충분한 표본 이후입니다. |
| 공통 산업·제품 경쟁·공통 고객 | 같은 세부업종·시총·공시 빈도에서 거래 경로가 확인되지 않은 집단과, 동등한 정보 범위 안에서 적극적으로 거래관계가 배제된 집단을 구분합니다. 산업 노출만 있는 셀, 제품 유사 공급사, 같은 고객의 비영향 프로그램 및 같은 업종·차수·가중치 구간을 보존한 방향 네트워크를 대조합니다. 공개된 경로 수준이나 날짜를 섞어 돌린 플라시보와 충격 전 추세를 비교합니다. |
| 새로운 반증 가능한 가설 | **공통 병목**: 대체 공급사가 여러 곳이어도 같은 공장·항만·인증 설비를 쓰면 납기 완충이 약합니다. **용량 예약의 비대칭**: 최소 구매가 있는 예약은 공급 부족 시 구매사를 보호할 수 있고, 수요 급감 시 의무 구매·재고 부담을 구매사에 남길 수 있습니다. Cirrus의 용량 계약에는 실제 최소 구매·미달 지급 조건이 있어 조항 존재를 확인할 수 있습니다. [Cirrus 10-K](https://www.sec.gov/Archives/edgar/data/772406/000077240623000019/crus-20230325.htm) |

공개시각은 실제 발생, 최초 사건 공지, 원천 수집, 수정 시각을 각각 저장합니다. 장중 시각 불명은 현지 날짜 종료의 보수적 상한과 다음 거래 가능 세션을 사용합니다. 공시 원문·기기/사업부·거래 방향·궁극 모회사·상장 증권 유효 구간을 사건 전 동결합니다. 공시 당시 연도 기반·단위·미공개 비중·변경일을 기록합니다. 예고된 파업은 최초 새 정보와 시작일을 각각 기록하고 위험 방향의 선행 추세 검사를 명시합니다. 자기 기업 실적, 시장×날짜, 산업×날짜, 사전 시총·유동성·모멘텀·가치·수익성을 통제합니다. 동시 자기 공시 기업 제외를 주 분석에 넣을 수 있으나 충격 뒤 실적은 매개변수로 별도 추정합니다.

사건 블록에 동일 가중을 먼저 부여하고 기업·기간의 반복을 묶습니다. 두 방향의 사전 가설을 Holm으로 통제하고, 소표본에는 사건 무작위화 또는 wild-cluster 추론을 적용하며 공통 산업/시계열 의존성에 민감도를 보고합니다. N≥41은 0.50 SD의 독립 사례 기준이고 방향별로 확인해야 합니다. 최종 요구 N은 사건률·적격 통제군·의존성과 본 연구와 독립인 결과 분산을 사용해 승인 전에 다시 정합니다. 역사 표본은 새 독립 원천이라도 같은 종목·시기의 기존 결과가 노출됐으면 탐색입니다. 새 분쟁/재해의 전향 입력은 별도 승인 후 전진 기록하며 소급 입력을 증거로 세지 않습니다.

물리적 전달 확인 뒤에만 정보 반영을 검정합니다. 6개월 비용 후 효과를 주 경제성 검정으로, 12개월을 고정 보조로 둡니다. 초기 최소효과 후보는 동일 시장·산업·β 기준의 비용 후 H126 +1.5%p이며, 회전율·유동성에 따른 스프레드와 시장충격·한국 날짜별 세금·종결대가를 반영합니다. KR 069500.KS와 US SPY를 기준으로 하고 QQQ는 보조입니다. 사전 고정 비용 1배/2배, 낙폭, 하락기 β, 최악 기간, 자금·ETF 노출 일치도 및 총수익·종료대가를 점검합니다. 물리 전달 성공, 정보 지연 성공, 위험조정·비용 후 경제성 성공을 각각 판정합니다.

## 후속 수학적 탐색

기업 간 상품 흐름 (W_{ij})는 공급사 (i)에서 구매사 (j)로 둡니다. 공급 충격은 그 방향, 구매사 수요 충격은 역방향으로 전달되므로 두 전달 행렬을 독립적으로 제한합니다. 산업 거래 (Z_{ij})에서 (A_{ij}=Z_{ij}/x_j)를 계산하고, 정태 수요의 ((I-A)^{-1})은 산업 공통 노출 기준으로 씁니다. 이상적 대체를 가정하기 어려운 공급 충격은 재고·생산능력·최소 구매 약정과 경로 지연이 있는 제약을 둡니다. 소수 경로와 정상 방향을 제약한 분산시차 추정 또는 사건 기반 local projection으로 단계별 충격 반응을 교차 검증합니다.

사업부 경제량과 거래 네트워크를 곱해 직접·간접 경로의 영향 크기를 계산할 때 동일 공장과 최종 모회사에서 합쳐지는 두 경로의 중복을 제거합니다. 네트워크 잔차의 방향과 부호는 시장·산업 공통 요인 및 위험 요인 통제 뒤 확인합니다. 가격 지연을 검정하기 앞서, 동일한 실제 전달인데 공시 시차만 다른 설계와 두 번의 원천 재취득으로 식별 범위를 좁힙니다.

## 진행 판정

**KEEP — 데이터·메커니즘.** 원천 0에서 SEC 사전 관측 23관계, 한국 사업부 11관계, 산업 IO 그래프 및 4개 사건의 9개 명시 경로를 확보했습니다. **INCONCLUSIVE — 외생적 실물 효과·정보 지연·순성과.** 주요 차단은 최초 공표 원본 빈티지, 공장–품목–고객 배분 가중치, 충분히 독립적인 사건 수입니다. 다음 최소 작업의 담당은 Codex입니다. 기존 BLS 91개 원장에서 현재 핵심 4개에 대해 최초 공개 상한과 제품·공장 사전 링크를 직접 확인할 수 있는 원천 증거를 보강합니다. 충격·입력·검정·비용 기준과 해시 동결, 독립 검토, 소유자 별도 승인이 이후 실증의 조건입니다. [연구 계약](https://github.com/jaehojung1879-netizen/Investment/blob/3150c70017432e3b73321fbda47ebea226bf8d2b/docs/research-program/README.md)
