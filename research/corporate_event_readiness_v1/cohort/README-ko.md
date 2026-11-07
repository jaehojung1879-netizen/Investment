# KR 기업 이벤트 cohort v1 — 자본배분(A)·대규모 공급계약(B)의 실제 표본

**판정: 원천·표본 단계 완료 / 역사 수익률 실행 BLOCKED(승인·가격측 원천).**
- 가격·수익률·라벨·NAV는 0회 읽었다.
- 2026-11-07 OpenDART API로 실제 공시를 수집했다.
- PIT KOSPI Top300 유니버스에서 날짜 기준 보수적 적격 후보 2,159건을 만들었다.
- 그중 발행사 embargo 후 독립 사건은 H126 기준 A1 323 / A2 522 / B1 464다.
- 작성자 자체 검증(`AUTHOR_VALIDATION_ONLY`)일 뿐 독립 승인이 아니다.

## 1. 무엇을 했나

| 단계 | 원천·코드 | 결과 |
|---|---|---|
| 모집단 | `signal-history@73b3907a` `ledger/universe/kr` 월별 PIT KOSPI Top300 스냅샷 164개(2013-01-02 ~ 2026-09-01). 날짜·코드·이름만 읽음 | 증권 624개. 기존 `dart_ownership_universe._resolve_security`로 발행사 601개에 매핑(정확 종목코드, 아니면 유일한 정확 사명). 미해결 23개는 전부 우선주 |
| 공시 인벤토리 | OpenDART `list.json` 발행사별 2013-01-01 ~ 2026-10-31. `pblntf_ty=B` + `pblntf_detail_ty=I001`. 기존 `fetch_all_pages`로 끝까지 순회 | 스캔 142,345건(B 12,975 / I001 129,370), API 2,222회. 자본배분·공급계약 계열 **27,322개 버전** |
| 원문 | OpenDART `document.xml`. 정체성 관문을 통과한 원공시와 진입 전 창(10일) 안의 정정공시만 요청 | 6,926건 요청 → 6,502건 확보. 424건은 DART가 `014 파일이 존재하지 않습니다`로 답함(아래 4절) |
| 파싱 | #320 `filings.parse_filing` 그대로 재사용 + 작은 어댑터 두 개(`bodies.py`) | 주요사항보고서 XML의 `<TE>/<TU>` 값 셀을 표 셀로 인식, 본문 자기진술 플래그(진행사항 공시·공시유보) |
| 교차검증 | DART DS005 `tsstkAqDecsn` 정형값 | 2015년 이후 자기주식취득결정 468건 중 DS005에 있는 **408건 전부** 보통주 수량과 '소각' 목적 판정이 일치. 60건은 DS005가 제공하지 않음 |
| 사건화 | `events.py` | 버전마다 처음 실패한 관문을 기록. 경제적 사건 분류(A1/A2/B1), 진입 규칙, 발행사·가설·기간별 embargo로 독립 N 산출 |

두 원문 경로(#320 공개 viewer, API `document.xml`)도 대조했다. #320 고정 표본 13건에서 원바이트는 13건 모두 다르지만(컨테이너 마크업) 파싱 필드 15개는 13건 모두 같았다(`data/document-route-crosscheck-v1.json`, `crosscheck_routes.py`).

## 2. Cohort funnel (PIT KOSPI Top300 유니버스, 2013-01-01 ~ 2026-10-31)

| 관문(처음 실패한 곳) | 버전 수 |
|---|---:|
| 전체 계열 버전 | **27,322** |
| 정정 버전(원공시 아님; 계보 기록만) | 10,707 |
| 자회사 주요경영사항(모회사 증권 사건 아님) | 3,462 |
| 공시 당시 PIT Top300이 아님(직전 월 스냅샷 기준) | 5,096 |
| 목록 수준만 집계(처분·유증·CB·EB·BW·감자·신탁해지·공급해지) | 2,127 |
| 원문 미제공(DART 014) | 151 |
| 필수 조건 미파싱 | 63 |
| 가설 분류 외(10% 미만 계약 3,177, 진행사항 공시 81, 공시유보 117, 비율 불일치 9, 임직원·기업행동 목적 72, 우선주만 소각 11) | 3,467 |
| 진입 전 정정 존재(본문 명시 연결 9, 미연결 보수 제외 80) | 89 |
| 진입일이 데이터 cutoff 이후 | 1 |
| **DATE_ONLY_CONSERVATIVE 후보** | **2,159** (A1 491 · A2 782 · B1 886) |
| **PIT_EXACT** | **0**. 어떤 원천도 공개 시각을 제공하지 않음 |

### 독립 사건(같은 발행사·같은 가설은 진입 후 H 세션 동안 1건)

| 집합 | N | 발행사 | 진입 주 | Value-up 전/후 | 2025~26 | H 만기 도달(2026-11-06 기준) | 최대 동시 보유 |
|---|---:|---:|---:|---:|---:|---:|---:|
| A1 H126 | **323** | 145 | 175 | 121 / 202 | 169 | 270 | 70 |
| A1 H252 | 252 | 145 | 152 | 99 / 153 | 128 | 165 | 88 |
| A2 H126 | 522 | 203 | 340 | 406 / 116 | 76 | 503 | 44 |
| B1 H126 | **464** | 117 | 312 | 337 / 127 | 93 | 441 | 34 |
| B1 H252 | 346 | 117 | 260 | 251 / 95 | 66 | 312 | 46 |

- **A1 구성:** 소각결정 269, 소각 목적 직접취득 47, 소각 목적 신탁 7. 소각 수량은 발행주식의 중앙값 1.65%(P10 0.33%, P90 5.91%).
- **B1:** 계약 규모는 매출 대비 중앙값 16.7%(P90 52%). 회계연도를 명시한 공시는 136/464건. 상위 발행사는 한국항공우주·삼성중공업·한화오션·현대로템 등 방산·조선·플랜트에 집중된다.
- **중복:** 두 가설에 모두 나오는 발행사는 24개다.

## 3. 검정력 (σ와 설계효과를 모르는 상태)

수익률을 읽지 않았으므로 σ(사건 H 잔차수익 SD)와 D(달력 군집 설계효과)는 미측정이다. MDE는 격자로만 공개한다. 산식은 `power.py`: MDE = (z_{1−.05/6} + z_.80)·σ·√(D/N), Holm 3슬롯, MEE H126 3pp / H252 4pp.

| 집합 | σ=15%, D=2 | σ=20%, D=2 | σ=25%, D=2 |
|---|---|---|---|
| A1 H126 (N=323) | 3.82pp MARGINAL | 5.09pp MARGINAL | 6.37pp NO_GO |
| B1 H126 (N=464) | 3.19pp MARGINAL | 4.25pp MARGINAL | 5.31pp MARGINAL |
| A1 Value-up 이전만 (N=121) | — | 8.32pp NO_GO | — |
| B1 Value-up 이후만 (N=127) | — | 8.12pp NO_GO | — |

**해석:**
- Top300 표본만으로는 두 가설 모두 POWER_MARGINAL이다. 역사 결과로 확증을 주장할 수 없고, 전향 표본 축적이 우선이다(#292 Owner 초안의 판정 규칙).
- A1은 표본의 63%가 Value-up 이후, 52%가 2025~26년이다. 사전 등록된 Value-up 분할 점검에서 이전 구간만 따로 보면 검정력이 부족하다(NO_GO). 따라서 A1의 역사 결과는 '소각 효과'와 'Value-up/2025~26 국면'을 분리하기 어렵다. 이것은 결과를 보기 전에 측정한 사실이다.

## 4. 새로 확인한 원천 사실

1. **#320 파서는 주요사항보고서(B형) 원문에서 값 대부분을 못 읽었다.**
   - DART 구조화 XML은 값을 `<TE ACODE>`/`<TU AUNIT>`에 담는데, #320의 표 판독기는 td/th만 본다.
   - 고정 표본 13건은 대부분 거래소 공시(I형) 또는 viewer HTML이라 이 결함이 드러나지 않았다.
   - 어댑터 적용 전에는 자기주식취득 508건, 신탁 523건의 수량·금액이 비어 A2가 14건이었다. 적용 후 782건이 됐다.
   - 원바이트와 해시는 그대로 기록한다.
2. **DART `document.xml` 014:** 6,926건 중 424건(6.1%)이 '파일 없음'이다. 2015~2019년 공급계약 정정과 신탁 원공시에 몰려 있다. 0이나 성공으로 바꾸지 않고 관문에서 집계한다. #320의 공개 viewer로 보완할 수 있는지는 미측정이다.
3. **PIT_EXACT 0:** list.json, document.xml, DS005 모두 접수 '일'만 준다. 공개 시각 원천(KIND)은 이 환경에서 403이다. 모든 후보는 보수적 날짜 규칙을 쓴다(접수일 다음 첫 세션 종가 신호, 그 다음 세션 종가 진입).
4. **전체 KOSPI·KOSDAQ 유동성 모집단은 SOURCE_BLOCKED:** KRX 데이터 포털이 이 환경에 `LOGOUT`으로 답한다. Top300은 PIT 하위 유니버스일 뿐 Owner 초안의 '전체 KOSPI·63세션 거래대금 ≥10억 원' 기준을 대신하지 않는다.
5. **list.json 행에는 상장폐지 발행사(`corp_cls=E`)도 종목코드가 남는다.** `rm`의 '유/코'는 공시가 어느 시장을 통해 나갔는지 보여준다. 현재 시장 구분으로 거르면 생존편향이 생기므로 거르지 않았다.

## 5. 아직 할 수 없는 것과 정확한 차단

역사 수익률 실행에는 다음이 모두 필요하다. 각각 **SOURCE_BLOCKED/PENDING**이다.
- 주식 총수익 기준: KRX 일봉(`ledger/prices/kr`)은 배당이 없다.
- 보유 중 상장폐지 종목의 종결대가
- 투자 가능한 원화 현금
- 투자자 세금·비용 계약(#317 economics와 공유)
- Top120 밖의 PIT 산업 라벨: B1은 산업 일치 검정이 없으면 지지 판정 불가
- σ·D 보정에 쓸 사건 이전 가격 읽기
- 비저자 독립 감사
- Owner의 정확 해시 기반 Phase D 신규 축 예외 승인

가격 원천(`ledger/prices/kr`, 상장폐지 포함, 배당 없음)의 종목별 커버리지는 가격 행을 열어야 확인할 수 있어 측정하지 않았다(UNKNOWN). 최종 연구 적격 사건 수도 UNKNOWN이다.

사전등록 후보: [`kr-corporate-information-events-v1-candidate.json`](kr-corporate-information-events-v1-candidate.json)
- `PROPOSED_NOT_REGISTERED`, 코드 18개·입력 9개의 SHA256을 고정했다.
- 등록에 필요한 승인 문구는 파일의 `approvalRequest`에 있다.
- 이 파일은 승인이 아니다.

## 6. 재현

```bash
# 네트워크 없이(캐시 필요) / 테스트
python -m pytest -q tests/test_corporate_event_cohort.py tests/test_corporate_event*.py
# 수집(DART_API_KEY 필요; 키는 어디에도 기록하지 않음)
python -m research.corporate_event_readiness_v1.cohort.collect_issuers --cache <cache> --universe <ledger/universe/kr> --out <out>
python -m research.corporate_event_readiness_v1.cohort.run_cohort --cache <cache> --universe <ledger/universe/kr> --index <out>/issuer-index-rows-v1.jsonl.gz --out <out2>
python -m research.corporate_event_readiness_v1.cohort.crosscheck_ds005 --cache <cache> --events <out2>/cohort-events-v1.jsonl.gz --out <out2>/ds005-crosscheck-v1.json
python -m research.corporate_event_readiness_v1.cohort.build_spec
```

- 같은 캐시로 오프라인 재빌드를 세 번 해서 산출 파일이 바이트 단위로 같음을 확인했다.
- 원응답 캐시(83MB; 페이지·원문 원바이트, SHA256 주소)는 저장소에 넣지 않았다. 대량 DART 원문 재배포 권리는 Owner 결정 사항이다.
- 모든 페이지 해시(`issuer-index-manifest-v1.json`)와 원문 해시(`body-receipts-v1.json.gz`)를 커밋했다. 재수집하면 바이트 차이를 검출할 수 있다.
