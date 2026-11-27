# 원천 권리와 보존 증거

## S1 원본 ZIP

`s1/Investment-network-pilot.zip`은 기존 36개 항목, 3,586,091바이트의 원본 ZIP입니다. SHA-256은 `1d1c725f7b70602333bbd73635d4ffe2e022f00d98ff6d16629344776898a7d8`입니다. S1 보고서 Markdown은 ZIP에서 같은 바이트를 꺼냈습니다. ZIP 안에는 작성한 분석·코드, 공공 파생행·관측 목록, 원천 URL 및 해시가 들어 있습니다.

- **OECD**. OECD (2023, 2025, 2026), *OECD Inter-Country Input-Output Tables*, regular vintages. 4개 국가·지역 재추출, 계수 계산과 산업 분류 대응은 Investment의 가공입니다. OECD Terms §3의 Data 규정은 별도 제한이 표시된 경우를 제외하고 출처를 밝힌 자료의 추출·가공·배포를 허용합니다. ICIO 페이지와 ZIP의 범위에서 별도의 제3자 배포 제한 표시를 찾지 못했습니다. [자료](https://www.oecd.org/en/data/datasets/inter-country-input-output-tables.html) · [이용 조건](https://www.oecd.org/en/about/terms-conditions.html)
- **BEA·BLS**. U.S. Bureau of Economic Analysis, *Use Table (Supply-Use Framework), 2017*. U.S. Bureau of Labor Statistics, *Major Work Stoppages, Detailed Monthly Listing*. BEA 공개 통계의 수치 및 BLS 공공영역 통계의 파생행을 배포합니다. [BEA 데이터](https://www.bea.gov/itable/input-output) · [BLS 저작권](https://www.bls.gov/bls/linksite.htm)
- **Dartmouth TNIC·ETNIC**. ZIP에 수록한 것은 행 수·기간·집계와 공식 주소·해시뿐입니다. 원 행렬·텍스트 및 WRDS/Compustat CIK–GVKEY 매핑은 포함하지 않았습니다. [Hoberg–Phillips Data Library](https://hobergphillips.tuck.dartmouth.edu/tnic_basedata.html)
- **SEC·DART·기업 보고서·특허·한국은행**. 공시·특허·보고서의 URL과 날짜, 식별자, SHA-256, 개별 사실과 작성자가 계산한 측정값을 보존합니다. 제3자 원문 HTML·PDF, 원문 DART 아카이브와 특허 파일은 ZIP에 없습니다. [SEC 접근 안내](https://www.sec.gov/about/developer-resources) · [OpenDART 이용약관](https://opendart.fss.or.kr/intro/terms.do) · [USPTO 문서](https://www.uspto.gov/patents/search/patent-document-authority-files)

## S2 파생자료

- **openFDA**. openFDA의 표시된 CC0 1.0 원칙을 확인했습니다. 출처는 FDA입니다. FDA 원본 ZIP, 연락처, 주소, 원문 조치 서술 대신 사건 날짜·관계·분류·회수 식별자, 출처, 가공 지표를 보존했습니다. [openFDA 라이선스](https://open.fda.gov/license/) · [다운로드](https://open.fda.gov/data/downloads/)
- **USAspending**. U.S. Department of the Treasury, USAspending.gov의 공개 연방 거래 사실과 출처입니다. API 코드·사이트 자산과 전체 원본 CSV를 재배포하지 않습니다. 회사 거래 필드만 제한적으로 보존하고 개인·개인사업자·미분류 수취인의 이름과 UEI, 그리고 연락처·주소·자유서술을 제외했습니다. 연방 의무액과 옵션 포함 금액의 의미는 보고서에 명시했습니다. [데이터 안내](https://www.usaspending.gov/data/about-the-data-download.pdf) · [API](https://api.usaspending.gov/docs/endpoints)
- **기업·노조·규제기관 원문**. 공시, 사이트 및 발표 원문은 주소와 각 로컬 응답의 SHA-256으로 식별했습니다. 저장소에는 사실 요약, 개시일·공지일 및 파생관계만 포함했습니다. 접근권 확인이 되지 않은 원천은 자료 매니페스트에 따로 표시합니다.
