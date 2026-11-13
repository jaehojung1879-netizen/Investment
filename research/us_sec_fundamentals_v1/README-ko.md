# SEC 총자산 연구 입력

2026-11-14 Codex 작업공간에서 SEC 공개 `submissions.zip`, `companyfacts.zip`과 분기 재무 ZIP을 실제 다운로드해 확인했다. GitHub Actions에서 SEC에 접근할 수 있는지는 별도다.

`assets.jsonl`은 Finnhub 신호 이력 `9ca19d835d4642badac1e14ea60d4a9a70d5642c`에서 총자산이 빠진 619건의 SEC 수치다. 순서는 CIK, 접수번호, 보고기간 종료일, 제출일, 접수 시각(시간대 포함), USD 총자산, 출처다. 591건은 Company Facts와 제출 이력, 26건은 SEC 2026Q3 재무제표 데이터의 SUB·NUM·PRE, 2건은 해당 10-Q 원문이다. 저장소의 고정 비교군 24건은 기존 총자산과 모두 일치했다. SEC 접수 시각과 기존 시각이 4시간 차이 난 16건은 원래 시각을 보존하고 둘의 날짜 기준을 적용했다. 기존 관측일을 바꾸지 않았다.

- SEC Company Facts ZIP SHA-256 `4ccd1200cfafd0a4b566c0a755e88502b74ab339e26fb77315c9c85e1ec68531`
- SEC submissions ZIP SHA-256 `7fe68e3c02d0e988f7d89e1db49acea12f9ced0cde1c6269a1e2949b3cb85ad7`
- SEC 2026Q3 ZIP SHA-256 `b6ebdc56b78526a6423f5b99f6e355afcb0510e7264324300ee5f0d3bd1bad21`
- 원문 확인 [LEN](https://www.sec.gov/Archives/edgar/data/920760/000162828026064557/len-20260831.htm) · [QRVO](https://www.sec.gov/Archives/edgar/data/1604778/000162828026050166/rfmd-20260627.htm)
- [SEC 공개 API 및 일괄 ZIP 안내](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) · [분기 재무제표 데이터](https://www.sec.gov/data-research/sec-markets-data/financial-statement-data-sets)

`assets.features_as_of(records, as_of, load_assets(), cik=dated_cik)`가 기존 현금수익성 계산을 그대로 호출한다. CIK·접수번호·보고기간·제출일이 일치하고 양쪽 출처의 접수·제출일보다 신호일이 늦을 때, 총자산 항목이 없는 공시에만 보완한다. 호출자가 보유한 시점별 발행사 CIK로 재무를 제한한다. 거래 증권의 주식 클래스와 가격 경로의 검증은 별도다.

## 확인 명령

기존 Finnhub 입력에 대한 접근권이 있는 작업공간에서 저장소 루트 기준으로 실행한다.

```bash
git fetch origin 9ca19d835d4642badac1e14ea60d4a9a70d5642c
workdir=$(mktemp -d)
git archive 9ca19d835d4642badac1e14ea60d4a9a70d5642c ledger/fundamentals/us | tar -x -C "$workdir"
python -m research.us_sec_fundamentals_v1.check --store "$workdir/ledger/fundamentals/us"
```

2026-09-05 스냅샷의 503종목, 2026-10-09 판단일을 재현했다. CIK가 있는 501종목에 동일한 신원 제한을 적용했다. 현금수익성과 발생액/총자산 계산 가능 종목은 각각 4 → 479개, 영업이익/총자산은 4 → 457개였다. 이미 계산 가능했던 값은 기존 계산과 일치했다. 해당 날짜까지 617건을 보완할 수 있었다. 이는 당시 공시를 기준으로 재구성한 계산 가능성으로, 그날 실제 보완 데이터가 운영에 들어갔다는 뜻은 아니다.

2013~2022년 구성 스냅샷의 날짜별 CIK 연결과 이탈 증권의 일별 가격·종결 총수익이 역사 검증의 잔여 입력이다. 이번 경로는 명시적으로 호출하는 연구 입력이며 GitHub Actions의 SEC 호출 없이 저장된 SEC 수치를 읽는다.
