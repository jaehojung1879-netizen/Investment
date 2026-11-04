# 경제성 공통 원천 및 입력 계약 감사

기준 main은 `37f8cbf6b1c066f6b3c65235953648d17ebf2f69`, 읽기 전용 #316은 `86c5983ffba643a58d9eba84a05dc60f4d8e9e6a`다. 새 역사 수익률·C2 귀속·실제 체결은 실행하지 않았다. 원천의 행 수·날짜·해시와 계산 전제만 확인했다. 상세 원본 URL·캡처 시각·Git blob·SHA-256·실패 코드는 [원천 감사 JSON](../evidence/economic-source-audit.json)에 있다.

## 실제 확보와 적격성

| 항목 | 실제 확보·독립 검증 | 현재 판정 |
|---|---|---|
| KODEX200 공식 종가·NAV XLS | main에 원본 1,202,176바이트 보존. SHA-256 `cbdd7a0ce340228ddcfc714de637c512f73c2d691d84ae59a28cfb406d8437b9`. 기존 `issuer_prices`로 종가·NAV 각각 5,918행, 2002-10-14~2026-10-07, 유효 종가 대비 NAV 결측 0·중복 0 확인 | **PARTIAL**: 원본 존재. NAV 가격을 분배금 재투자 수익이나 투자자 순수익으로 승격하지 않음 |
| 공식 배당 API JSON/XLS | 원본 각각 3,020/15,360바이트, 두 형식의 gross 금액 20건 대조 PASS. record date 2021-10-29~2026-07-31 | **PARTIAL**: 실제 지급 근거지만 ex-date·투자자 세후현금·전체 기간 완전성과 사용권은 별도 |
| 과거 발행사 월간 분배금 문서(.pdf) | 기존 9개 응답 중 8개 HTTP200 문서와 2015년 HTTP429 응답 본문을 각각 해시 확인. 기존 메타데이터는 30개 지급 기록과 2011-04-29~2022-01-28 범위를 설명 | **PARTIAL**: 과거 지급표 원본이 실제 존재하며 #316도 이 문서들을 이미 인정한다. ETF PDF(Portfolio Deposit File)와 구분 |
| ETF 구성 | `issuer-product.json`에 2026-10-08 snapshot 202행, 월간 report index 200개 존재 | 과거 구성 패널 **SOURCE_BLOCKED**. 현재 snapshot이나 report 목록을 과거 구성원·비중으로 소급하지 않음 |
| KOFR | 공식 소개·공시 화면 메타데이터 HTTP200·바이트 해시 확보. 일별 금리 payload와 투자자 현금수익은 미수집 | 실제 투자 가능 현금 전체 기간 **SOURCE_BLOCKED**, 보존·재사용 권리 **UNVERIFIED** |
| CD91 | KOFIA frame HTTP200, 실제 MAIN 요청 timeout. ECOS 홈페이지 접근 확인. 검증된 정확한 CD91 table/item 및 일별 payload 미확보 | **SOURCE_BLOCKED**. 새 API 키·유료 자료·대량 요청 없이 종료 |
| 실제 체결·슬리피지 | broker order/fill/fee receipt 없음 | **SOURCE_BLOCKED**. 모델 비용과 실제 체결 성과를 구분 |

#316 inventory의 **KODEX200 NAV series 부재 표현**은 원천 바이트 기준으로 정정할 수 있다. 위 NAV XLS는 이미 같은 main에 보존되어 있었으며, 이번에는 원바이트 해시뿐 아니라 실제 열·기간·결측까지 판독했다. 등록된 연구 입력에 적격 NAV가 연결되었다는 뜻은 아니다.

#316의 **ETF PDF는 Portfolio Deposit File(포트폴리오 납입내역)**을 뜻한다. 월간 분배금 문서의 `.pdf` 확장자를 뜻하지 않으며, #316도 연간 분배금 문서의 존재를 이미 인정한다. 따라서 과거 분배금 PDF 8개를 근거로 #316의 ETF PDF 부재 판단이 틀렸다고 정정하지 않는다. 필요한 역사 구성원·비중 및 해당 시점의 Portfolio Deposit File 패널은 계속 미확보다. 2026-10-08 현재 구성 snapshot을 과거 연구 기간에 소급하지 않는다. NAV 원천 가용성 정정 역시 기존 봉인 결과·벤치마크·연구 판정의 변경을 뜻하지 않으며, 당시 이용 가능 vintage, 사용자 권리, 완전한 투자자 총수익은 여전히 확보되지 않았다.

## KOFR·CD91의 경제적 경계

[공식 KOFR 소개](https://www.kofr.kr/intro/RFRinfo.jsp)의 공개 본문 `https://www.kofr.kr/pub/intro/RFRinfo_01_kr.xml`을 확인했다. 정식 공시 시작은 **2021-11-26**이고, 정식 공시 전 RP 결제자료로 계산한 잠정치는 **2022-04-18**부터 제공했다. 공시일 전 영업일의 국채·통안증권 담보 익일물 원화 RP 거래를 사용하며 오전 11시에 공시한다. 이 설명의 SHA-256은 `dd4a42cc72aea816243d165547847110fcca870a9d10ea0c6c492a400ce167d1`이다.

따라서 공시 전 계산된 역사 금리를 2013년에 이미 공개된 정보로 취급할 수 없다. 일별 금리의 거래 기준일과 공개일도 동일하지 않다. 이번에는 금리 관측값을 수집하지 않았으므로 최초 데이터 관측일·전체 역사 커버리지를 주장하지 않는다. 공식 사이트의 copyright 문구나 HTTP200은 연구 보존·재배포 허가의 증거가 아니다.

KOFR는 금융기관 RP 실거래 기반 참조금리다. 개인 연구 포트폴리오가 담보·거래 접근성·비용 없이 그 금리를 그대로 획득했다는 증거가 아니다. CD91 역시 91일물 호가·수익률을 일별 재투자 현금 성과로 바꾸려면 실제 상품, 만기, 롤, 거래일, 비용·세금 및 자금 가용성 계약이 필요하다. BOK 기준금리는 정책 대용지표이며 실제 현금수익으로 허용하지 않는다. 2013~2026 기간을 한 금리·한 상품으로 소급 연결하지 않았다.

## 구현과 기존 코드 재사용

[economics.py](../economics.py)는 다음 입력 계약을 제공한다.

- `parse_ecos_benchmark_quotes`: 기존 `pipeline/ecos_macro.py`의 selector 검증·응답 parser를 재사용한다. 정확한 table/item/단위/일자를 대조하고, 미요청 secondary selector·중복·결측을 거부한다. 출력은 `REFERENCE_RATE_QUOTE`, `investable=False`, `REVISED_HISTORY`, 공개 vintage 미검증 상태다.
- `build_cash_input_contract`: 실제 상품·기간·비용·세금·권리·원본 digest가 선언된 투자 가능 payoff/NAV-return 입력만 검사한다. 주말을 포함한 연속 calendar-day grid와 기간 연결을 강제한다. KOFR/CD91/정책금리를 직접 현금수익으로 전달하면 `REFERENCE_RATE_NOT_INVESTABLE_CASH`로 거부한다. 공백을 forward fill하거나 비용을 0으로 만들지 않는다. 영업일 NAV만 있고 주말 귀속이 없으면 현재 daily 계약으로는 거부하며, 3일 누적 수익을 근거 없이 일별 분해하지 않는다. 상품·권리의 선언은 별도 원본 감사와 결합해야 하며 함수 호출 자체가 진실성을 인증하지 않는다.
- `adapt_issuer_distributions`: 공식 API의 gross 금액, taxable 금액, record/payment date를 분리 보존한다. taxable amount를 세후 지급액으로 취급하지 않고, 직전 거래일을 임의 ex-date로 만들지 않는다. `availableOn`과 ex-date는 근거가 없으면 `None`이다.
- `verify_existing_benchmark_snapshot`: 기존 `pipeline/kr_alpha_atlas_benchmark_audit.py`의 원본 해시 검증기를 재사용한다. 기존 benchmark outcome 함수는 호출하지 않는다.
- `reconcile_distribution_events`: 기존 `pipeline/kr_dividend_reconciliation.py`를 감싸 신원·event ID·통화·주당/ETF-unit 기준·gross·명시적 ex-date 근거를 먼저 대조한다. unmatched 양쪽 수와 실패 코드를 보존한다. 일치한 일부 이벤트도 `completenessCertified=False`다.
- `total_return_input_gate`: 배당 완전성, corporate actions, 총수익 가격에 raw event 재가산 방지, 세금 기준 및 종결 원본 digest 참조를 점검한다. `0`, `last price`, `ASSUMED_ZERO`는 종결 근거로 거부한다. 이 단계는 선언·digest 참조 계약이며 `sourcePayloadVerified=False`를 명시한다. 실제 receipt 해석은 기존 `pipeline/kr_terminal_corporate_actions.py`가 담당하며 재구현하지 않았다.

모든 계산 전 계약은 `outcomeExecutionAuthorized=False`다. #316의 `c2_attribution.py`, 사전등록, 실행 승인·해시·기존 결과를 복제하거나 변경하지 않았다.

## 남는 경제적으로 중요한 차단

#316의 원천 감사상 C2 보유 72종목 중 `000030`, `000060`, `002550`, `047040`, `207940`에는 dividend event가 0개다. 이는 배당이 없었다는 검증이 아니다. 종료 22종목 문제와 전체 주식의 분배금 완전성은 그대로 남는다. C2가 보유했던 종료 종목 3개는 종료 1.5년 이상 전에 매도했으므로 그 보유창에 종결 경제가 필요 없다는 기존 판단과, 전체 유니버스의 종결 자료 공백은 구분해야 한다.

수정 benchmark에는 기존 첫 anchor 전에 251개 quote만 있으며, 253개 return에는 254개 close가 필요하다는 #316 공백도 보존한다. 새 NAV XLS 발견만으로 등록된 corrected gross-TR benchmark의 warmup을 대체·연결하지 않는다.

기존 C2 비용은 수수료 1.5bp, spread 8bp의 절반과 날짜별 매도세를 적용하는 모델이다. 실제 주문시각·체결단가·체결량·시장충격·비용 누락 검증은 별도 receipt가 없으므로 완료하지 않았다. gross ETF 시장가격 TR, raw NAV 가격, vendor adjusted price, KOSPI200 PR/TR/NTR 및 투자자 세후 수익은 같은 기준이 아니다.

## 재현과 Claude 인계

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 /workspace/Investment/.venv/bin/python -m pytest -q tests/test_cross_market_economics.py
/workspace/Investment/.venv/bin/ruff check research/cross_market_foundation_v1/economics.py tests/test_cross_market_economics.py
```

영향 테스트 48개 통과, ruff 통과. 진짜 고정 원본 테스트는 저장된 source manifest 전체 해시와 공식 20개 distribution의 date semantics만 읽으며 수익률을 계산하지 않는다. 나머지는 합성 입력으로 미래 공개, 통화 혼동, 선택자 오류, 결측·주말 누락, 중복 지급, net/gross 혼동, 미확인 종결과 배당 중복 적용을 거부하는지 확인한다.

NAV XLS 독립 판독에는 저장소 의존성을 변경하지 않고 `/tmp/foundation-xls-tools`에만 `xlrd==2.0.1`을 설치해 기존 `issuer_prices`와 `crosscheck_distributions`를 호출했다. 표준 회귀 테스트에는 xlrd가 필요 없다. XLS metadata 검증은 다음 코드로 반복할 수 있다(수익 계산 없음).

```python
import sys
sys.path.insert(0, '/tmp/foundation-xls-tools')
from pipeline.kr_alpha_atlas_benchmark_audit import issuer_prices, crosscheck_distributions
from pathlib import Path
p = Path('docs/audits/kr-alpha-atlas-phase-c-integrity/sources')
market, nav = issuer_prices(p / 'issuer-standard.xls')
print(len(market), min(market.index), max(market.index))
print(len(nav), min(nav.index), max(nav.index), len(set(market.index) - set(nav.index)))
print(crosscheck_distributions(p / 'issuer-dividends.json', p / 'issuer-dividends.xls'))
```

Claude는 먼저 정확한 기간의 투자 가능 현금 상품 원본·실제 비용/세금·권리를 확보하고 본 계약에 연결할 수 있다. 기존 ETF 가격·NAV 원본과 월간 분배금 문서(.pdf)를 중복 수집할 필요는 없다. 분배금 ex-date, 과거 구성·Portfolio Deposit File 및 당시 공개 시점 증거를 별도로 보강해야 한다. 새 역사 경제성 실행과 봉인 입력 대체는 정확한 코드·입력 해시 및 기존 연구 규칙에 따른 별도 Owner 승인 뒤에만 진행한다. 현재는 **인터페이스 구현 완료 / full 경제성 연구 SOURCE_BLOCKED**다.
