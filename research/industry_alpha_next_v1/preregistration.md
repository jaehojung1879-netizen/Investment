# Industry Alpha 다음 연구 — 사전등록 초안

**DRAFT, UNAPPROVED, NOT AN EXECUTABLE REGISTRATION.** 아래 수치·모형은
검토 가능한 제안이다. 자료 적격성·독립 감사·소유자 승인을 거쳐 별도 immutable
등록으로 동결하기 전에는 역사 라벨, fit, 수익률 검정에 사용하지 않는다.
기존에 측정된 특징은 같은 역사에서 “처음 발견한 특징”으로 다시 검정하지 않는다.
그 특징들을 조건부 기준모형의 입력으로 쓰는 새 질문만 별도 승인 대상으로 제안한다.

## 1. 예측 대상과 범위

지역은 KR과 US를 별도로 다룬다. KR reference population은 strictly prior KRX
Top120, US는 strictly prior 보존 S&P 500 membership이다. survivor union이나
현재 구성원 보충은 없다. 표본 밖 한국 전체 산업·미국 전체 경제로 일반화하지 않는다.
신호는 각 지역 달력의 마지막 월말 완료 세션 종가, 실행 e는 다음 지역 세션 종가,
청산은 e+H 지역 세션이며 H={126,252}다. 시각대와 완료 cutoff를 등록에 고정한다.

신호 시점 구성원 C(g,t), 양수 cap로 계산한 w(t)를 그 구간에 동결한다.
`R_g(t,H)=sum_i w_i(t)*R_i(e,e+H)`인 buy-and-hold 단순 총수익,
`Y_g=R_g−R_M`이 주 예측 대상이다. H126/H252는 별도 모델이다. 미래 membership이나
미래 cap로 가중치를 바꾸지 않는다. EW=1/N은 의무 민감도다. 종결 고려가 미해결인
peer가 하나라도 있으면 Y_g=null이며 나머지 peer에 재배분하지 않는다.

목표는 지역 시장을 초과할 **기대 상대수익 순위와 크기**다. 확률을 요청할 때는
별도 훈련-only 보정과 Brier/reliability 검증을 거친 후에만 `P(Y>cost)`를 발행한다.
이번 설계는 보정되지 않은 점수를 확률로 출력하지 않는다.

KR primary economic reference는 Phase C의 대조를 통과한 **정확한**
069500.KS 총배당 ETF 시계열·원천 빈티지다. replay-v16의 이름만 같은 계열은
대체하지 않는다. US는 배당/기업행동을 대조한 USD SPY 주주수익이다. 아직 새
입력 manifest에 두 시계열이 고정되지 않았으므로 실제 결과 실행은 BLOCKED다.
동일 원화/USD 기준, 환헤지·FX pooling 없음. 세금과 재투자 가정도 따로 명시한다.

대체 benchmark: KR broad KOSPI 및 KOSPI200, US broad-market index/ETF.
사전 고정한 compatible TR만 경제 민감도에 사용한다. price-index만 있으면 양쪽을
PRICE_RETURN으로 동기화한 기술 진단으로 한정한다. benchmark를 제외주와 함께
바꾸지 않는다. `R_g−beta_g(t)*R_M`(beta 과거252세션 추정)은 beta-exposure 진단,
`R_g−R_M`의 주 목표와 교체하지 않는다. benchmark가 모든 산업의 순위를 같이
이동시키지 않는다는 사실이 절대 초과수익/총수익 무결성을 인증하지는 않는다.

## 2. 정보와 최소 기준모형

산업 적격성: 신호일 strict 분류, 최소5증권/그룹, 최소8유효 그룹/일.
분류 confidence/유동성/기업행동 gate는 결과 이전 고정한다. 8개 미만이면
INELIGIBLE_DATE이며 섹터를 임의 병합하지 않는다. fundamental은 ≥3증권이며
≥60% cohort coverage에서 median을 쓴다. 미달은 null+missing indicator다.
이 숫자들은 과거 성과를 보지 않은 **새 초안 기준**이며 v4 gate 통과를 뜻하지 않는다.

| 블록 | 사전 지정 값 | 주요 혼입 방지 |
| --- | --- | --- |
| MOM | 같은 동결 cohort의 trailing126 수익−지역 시장 | 미래 구성원/최고 수익 산업 선택 금지 |
| BREADTH | trailing126 평균가격 위 종가인 구성원 비율 | 관측수/전체 N 동시 공개, halted/missing을 상승 아님으로 채우지 않음 |
| PROFIT | PIT TTM 순이익/positive 자산의 산업 median | financial statement basis/단위 혼합 금지 |
| CASH | PIT TTM OCF/positive 자산 median | 미공시 OCF=0 금지, 뒤의 정정 공시 소급 금지 |
| VALUE | PIT book equity/dated issue cap median | cap·share-class·분모 기준, negative equity는 별도 결측 이유 |
| CONCENTRATION | HHI=sum(w²), top1 share | cap/동일 issuer 집중도 구분 |

기존 OCF yield·earnings yield의 기술통계는 감사 문서에 보존한다. 가장 좋은 숫자를
보고 이 둘로 초안 입력을 바꾸지 않는다. 변경이 필요하면 outcome 접근 전 등록 diff와
사유를 독립 감사한다. 모든 특징은 source row와 원래 공개/계산 함수를 추적한다.
자료 적격성이 없는 블록은 p=1 슬롯으로 남고 다른 특징으로 치환하지 않는다.

고정 `ridge(lambda=10)` 선형모형을 지역×기간별로 학습한다. 목표는 훈련 날짜 내
산업 평균으로 중심화한 Y; 평가도 같은 날짜 내 중심화 MSE를 써 시장 공통 수익을
산업 정보로 오인하지 않는다. 절대 Y 보정/경제 진단은 별도로 보존한다.
날짜마다 같은 총 가중치, 그 안에서는 산업 동일 가중치다. trailing volatility126,
log constituent count, median log ADV60은 공통 nuisance이며 알파 특징으로 세지 않는다.

- N0: zero centered excess(무예측)와 단순 MOM 순위를 모두 대조군으로 공개.
- B: MOM + nuisance + CONCENTRATION. 가장 작은 운용 해석 기준.
- F: B + BREADTH + PROFIT + CASH + VALUE. 신규 복잡한 비선형 모형/탐색 없음.
- 각 block의 독립 정보는 F 대비 그 block만 뺀 모델의 **짝별 검증 오차 차이**다.
  CONCENTRATION도 제거 비교를 해 유용성을 검정하되, 다른 모든 비교에서는 통제한다.
  계수·raw IC의 유의성이나 상관 감소를 인과적 독립성으로 부르지 않는다.

훈련-only median imputation+고정 missing indicators+훈련 평균/표준편차를 사용한다.
모형별 완전관측 표본으로 바꾸지 않는다. missingness 자체가 산업·기간을 대리하는지
missing-indicator-only 대조를 기술 진단한다. 모든 입력이 비어도 데이터가 있는 것처럼
추천하지 않는다. λ·특징 방향·기간·모형 복잡도를 결과로 조정하지 않는다.

## 3. 순차 가설군 세 개

**H1 — 산업 정보의 추가성.** F에서 MOM, BREADTH, PROFIT, CASH, VALUE,
CONCENTRATION 각각을 뺐을 때보다 F의 date-balanced centered MSE가 낮은가?
각 비교의 기대 방향은 오차 감소다. HHI의 경제적 방향은 가정하지 않는다.
6 contrasts×2지역×2기간=24슬롯. 기존 marginal anatomy의 재발견을 주장하지 않는다.
N0/B/F의 paired IC·spread와 실현 상대수익을 전부 보고한다.

**H2 — 조건부 국면과 확산.** 별도 두 contrast다(2×2×2=8슬롯).

1. 시장 정보: F 대비 F + 시장의 trailing126 수익·vol126·SMA200 위/아래 상태와
   MOM×trend, BREADTH×trend의 고정 상호작용. 공통 시장 상태만 더해 생긴
   전체 시장 평균 예측을 산업 순위 개선으로 세지 않는다. 입력은 t까지 값만이며
   경기침체 사후 날짜, 수정된 ECOS/FRED, 미래 realized regime은 사용하지 않는다.
   상태별 손익·beta·지수상승 참여와 하락 방어는 전체 평균과 나란히 공개한다.
2. 확산: 리더는 t에 known cap 상위20%(ceil, 최소1개), 후발 집합은 나머지다.
   미래 상승 종목을 리더로 지정하지 않는다. 양쪽 최소2개인 그룹만 대상으로,
   `L=EW trailing63 leader return−EW trailing63 laggard return`을 정의한다.
   신호는 contemporaneous gap이며 후발 집합을 t에 동결한다. 타깃은
   `R_laggard(e,e+H)−R_M(e,e+H)`. 기준은 laggard 자체 MOM126/breadth,
   industry ex-leader MOM, HHI, liquidity, size, 시장 trend; 대안은 기준+L이다.
   같은 target/population에서 paired MSE가 개선되는지 검정한다. 리더 자신의 미래
   수익을 후발 타깃에 섞지 않는다. 전날/월 순위로 거슬러 “리더였음”을 지정하지 않는다.
   gap 부호별 후발 excess, signal-time leader identity와 concentration을 보고한다.
   산업 내 leader 라벨 permutation(훈련/검증 block 분리)·시간 역전 음성 대조는
   소프트웨어/공통 추세 혼입 진단이며 인과적 전파를 증명하지 않는다.

H2는 H1의 우수 특징만 골라 만들어지지 않는다. F와 정의를 미리 고정하고,
H1 부정/불충분이면 outcome 접근을 종료한다. H2를 진행하려면 그 부정 결과를
숨기지 않은 새 owner decision이 필요하다. 기존 실행 묶음의 범위를 늘리지 않는다.

정상 전진 규칙도 미리 동결한다. 해당 지역/기간의 H1에서 MOM·BREADTH·PROFIT·
CASH·VALUE 중 적어도 하나가 36-slot Holm .05와 양의 paired MSE 개선을 통과한
경우에만 같은 지역/기간의 H2 슬롯을 연다. CONCENTRATION만 통과하면 전진하지 않는다.
H3는 같은 H1 조건과 자료·비용 적격성을 요구하며, H2의 유불리에 따라 F 입력을
바꾸지 않는다. H2가 실패해도 H3를 묻는 것은 이미 등록한 별도 경제 질문이다.
음의 결과 뒤 새로운 범위를 제안한다면 새 Study ID·사전등록·독립 감사·소유자
승인이 모두 필요하고, 이 연구를 재시도하거나 부정 결과를 구제할 수 없다.

**H3 — 직접 종목 모델 대비 산업 추가의 순경제성.** 별도 승인된 최종 단계,
1contrast×2지역×2기간=4슬롯. 직접 모델 S는 종목 MOM126, book/cap,
net-income/assets, OCF/assets와 동일 nuisance로 stock−market을 예측한다.
대안 S+I는 같은 S 입력에 훈련 fold에서만 추정한 산업 excess 예측을 추가한다.
훈련 종목에 넣는 I는 반드시 내부 chronological out-of-fold 값이다. 산업 예측을
전체 훈련 결과로 fitted해 같은 행에 붙이는 stacking leakage는 금지한다.
LOO peer reference/동일 issuer 제외는 종목 residual 진단에 사용한다.

두 책은 같은 intended universe, 실행 시각, 최대5종목 동일 슬롯, 산업당 최대2,
같은 gross exposure=100%와 미배정 슬롯 passive, 같은 유동성/비용/세금·보유 기간을
쓴다. 최소5개의 positive cost-adjusted forecast가 없으면 적은 수를 허용하며
둘 다 공통 고정 hurdle `predicted excess > quoted roundtrip cost`를 쓴다.
대안의 현금/지수 배분이 다르면 allocation 효과를 별도로 분해한다. 시장 timing
overlay를 동시에 추가하지 않는다. 선택 후 결과 무효 종목을 다음 순위로 대체하지 않는다.
주 검정량은 동일 비중첩 블록에서 `(S+I net−ETF net)−(S net−ETF net)` 평균이며
36슬롯 중 마지막4다. paired 예측 MSE/IC는 보조 진단이고 비용 차감 우위의 대체물이 아니다.
산업 추가가 S보다 좋아도 ETF net 대비 양의 기회·위험/집중도·용량을 통과해야만
후속 전향 검토 자격이 있다. 최종 진단은 0개 후보/패시브도 허용한다.

## 4. 집중도와 같은 모집단 비교

모든 단계에서 FULL/CW가 주 정의, EW, 산업 최대 cap 1개 제거,
KR 005930·000660 고정 제거가 **의무 진단**이다. US는 t에 알려진 지역 cap 상위2를
제거한다(미래의 유명 기업 명단 사용 금지). 제거는 특성·랭크·cohort·target보다 먼저
하며 최소5명 gate를 다시 적용한다. benchmark는 그대로다. 효과가 좋다고 민감도를
주 정의로 승격하지 않는다. HHI/top1/issuer 집중도와 그룹 구성도 함께 공개한다.

예측은 결과 유효성 검사 이전에 freeze한다. 각 비교에서 base/alt 모두 예측하고
동일 target이 유효한 IDs/hash와 full intended 분모·pre-common 수를 공개한다.
FULL vs exclusion도 공통 group/date 표본의 짝 변화와 각 원래 가용 표본 결과를
나란히 낸다. 공통표본을 작게 만든 제거 실험을 “대형주와 무관”의 증거로 쓰지 않는다.
필요 peer 미해결은 두 책/비교에 대칭 적용한다. 전체 intended 경로가 막히면
valid 블록만 이어 붙여 CAGR/MDD/Sharpe를 만들지 않는다.

## 5. 시간 검증·다중검정·누설 방지

첫 훈련은 최소5년의 완료 라벨이 있는 구간으로 하고, 다음 연도 단위로 expanding
평가한다. 모든 산업은 같은 날짜 fold에 속한다. train label **exit < test_start−21세션**,
모든 H를 함께 쓰는 변환/stacking에는 최대252세션 maturity를 적용한다.
각 내부 fold에도 purge/embargo를 적용한다. 무작위 row CV, 미래 공시·기업행동을
이용한 특징 수정, 전체기간 imputation/scale/taxonomy 선택은 금지한다.
이미 노출된 역사에서의 out-of-fold는 **development validation**이며 독립 OOS가 아니다.

단 하나의 가족: H1 24 + H2 8 + H3 4 = **36개 예정 슬롯 전체 Holm .05**.
단계가 차단/중단되거나 표본이 부족한 슬롯도 p=1로 남긴다. 수익 부호·기간·지역·
제거 lens·benchmark 중 유리한 것만 뽑아 발견 수를 늘리지 않는다. 검정 방향은 미리
정한 오차 개선/순수익 개선으로 고정한다. H252를 H126 결과를 보고 선택하지 않는다.

월별 중첩 라벨과 산업 공통충격을 고려해 날짜별 paired 차이로 먼저 집계한다.
252세션 길이 moving-calendar-block bootstrap, 1,999 draws, seed=1879를 제안한다.
부트스트랩은 두 모형에 같은 날짜 블록을 쓰고 one-sided null-centered p에 +1
보정을 한다. 최소8개의 비중첩 H252 상당 블록 미만이면 추론 INSUFFICIENT_SUPPORT,
p=1이며 신뢰구간을 정밀하게 보이지 않는다. 8블록은 유의성 보장이 아니므로 독립
감사가 합성 autocorrelation/공통shock/null에서 small-tail 보정과 MDE를 검증해야 한다.
실패하면 결과를 보기 전에 별도 inference 설계를 수정/재동결한다. 신규 역사 Monte Carlo나
실제 수익률 기반 power 추정은 이번 PR에서 수행하지 않는다.

고정 비중첩 원점은 각 지역 첫 사전등록 가능 월말 다음 session으로 소유자가
미리 지정한다. H3 보유 경로는 H마다 별도 nonoverlapping blocks, 샘플 끝에 맞춰
유리한 origin을 고르지 않는다. 공통 calendar, outcome maturity, unresolved ID·원인,
그룹별·연도별 손실과 유효 block 수를 전부 보존한다.

## 6. 비용과 경제 측정 제안

투자금 초안은 KR 5천만원/US 5만USD, 매 거래 ≤lagged ADV60의1%다.
기본 편도 가정은 KR commission5+half-spread5+impact5=15bp에 시행일별 매도세,
US commission1+half-spread5+impact4=10bp에 해당 시행일 regulatory fee다.
이는 검증된 호가 추정치가 아닌 **보수적 검토용 가정**이다. 무료 공식 세율/브로커
원천과 적용일을 등록에 hash로 묶고 시장별 비용 적격성 감사 전에는 실행하지 않는다.
#286에서 지적된 2019 tax 표제/코드 상충을 상속하지 않는다.

entry 비용을 슬롯 내부에서 조달, exit 실제 시행일 세율 적용, 재투자 규칙 고정,
1×/2×/3× cost를 모두 공개한다. ETF도 매매 비용/배당/보유를 같은 기준으로 평가하되
passive buy-and-hold와 active block 반복 매매의 차이를 보존한다. 비용 누락을0으로
채우지 않는다. 조정 지수를 체결가격·ADV로 사용하지 않는다.

industry 자체 경제 진단은 F 상위2 산업을 각50%, 그 안은 신호일 cap-weighted로
구현한다. 데이터/용량 때문에 미배정된 산업 슬롯은 passive다. 비용을 낸 차이가
순위 정보와 함께 남는지 보되, H3와 혼합 최적화하지 않는다. 이 진단은 별도
유의성 발견 슬롯이 아니며 H1 예측 개선만으로 순알파를 선언할 수 없다.

완성 경로에서만 net excess, turnover/비용, MDD, CVaR, Sharpe(동결한 rf),
베타/산업·종목·현금/지수 배분 기여와 복리 차이를 보고한다. 경로가 없으면 null이다.
미측정 terminal payoff에 임의 -100%, 정지 carry를 거래 가능한 청산으로 쓰지 않는다.

## 7. 사전등록 패키지와 합성 수용 기준

후속 등록은 데이터 manifest/원시 바이트, taxonomy/identity, model/feature/원천 함수,
학습·신호·실행 달력/정확한 시작·끝·cutoff, 36 hypothesis slots, 비용/세율,
sample/attrition policy, runtime/seed, 결과 스키마, code closure, audit·owner 승인을
하나의 해시 묶음에 포함한다. **이번 초안에는 실제 역사 시작/끝/실행 권한이 없다.**

현재 합성 테스트는 release/효력의 경계, 재구성 lane 분리, missing terminal,
zero와 missing 구별, frozen weights, mega-cap 제거 후 depth, 같은 IDs,
maturity/embargo, market rally의 zero alpha, 비용에 소멸하는 gross 우위,
리더/후발 집합 분리, real scope 거절과 US schema drift를 검사한다.
다음 구현의 필수 추가 acceptance: 미래 파일 append의 prefix stability,
분할/배당/합병 권리 보존, all-missing·empty-universe·생존자 삭제 실패,
훈련-only scaler/OOF stacking, 동일 시드 재현, bootstrap null/공통충격/MDE,
수수료 내부 조달·turnover, invalid held peer의 paired path 차단,
atomic lock 전 실패(미소비)/후 실패(소비), exact-byte persistence다.
합성 성공은 금융 가설 검정 성공이 아니다.
