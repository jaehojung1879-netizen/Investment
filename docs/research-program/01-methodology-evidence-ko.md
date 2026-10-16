# 01 · 12개 방법론 비교와 학술 증거

**상태:** `DESIGN_ONLY_OUTCOME_BLIND`. 이 문서 작성 중 미래 수익률·라벨·모델 출력·포트폴리오 성과를 새로 읽지 않았다.
문헌 수치는 2026-10-16 웹 검색으로 원문 초록·출판 정보·저자 요약을 확인한 범위만 적었다. 전문(full text) 표까지 확인하지 못한 수치는 `원문 표 미확인`으로 표시한다.
저장소 수치는 각 문서에서 그대로 인용했고 재계산하지 않았다.

## 0. 먼저 고정할 해석 원칙

1. **문헌의 증거는 이 저장소의 증거가 아니다.** 미국 CRSP 전 종목·수십 년 표본의 결과를 S&P 500 생존자 표본이나 KRX 상위 120종목에 옮길 근거는 없다. 각 행의 "저장소 미검증" 칸이 진짜 공백이다.
2. **발표 후 감쇠는 기본값이다.** McLean–Pontiff(2016)는 97개 예측변수의 수익률이 표본 밖에서 26%, 발표 후 58% 낮았다고 보고했다. Hou–Xue–Zhang(2020)은 452개 이상현상 중 65%가 |t|≥1.96을 넘지 못했고 다중검정 기준 2.78에서는 82%가 실패했다고 보고했다. Harvey–Liu–Zhu(2016)는 새 팩터에 t>3.0을 요구한다. 아래 모든 방법론은 이 감쇠를 전제로 우선순위를 매긴다.
3. **대형주 유니버스는 대부분의 이상현상이 가장 약한 곳이다.** S&P 500과 KRX Top120은 이상현상 문헌이 주로 수익을 찾은 소형·저유동·저커버리지 종목을 거의 포함하지 않는다.
4. **6~12개월 표본은 독립 관측이 적다.** 미국 재정비 문서가 측정한 H126 HAC 유효 독립 날짜는 13.5년에 27개다. H252의 비중첩 연간 코호트는 미국 약 12~13개, 한국 재무 사용 가능 기간(2016~) 약 9~10개다. 방법론의 학술 증거가 강해도 이 저장소의 역사 표본으로 재확인할 검정력은 대부분 없다.

## 1. 요약 비교표

| 코드 | 방법론 | 핵심 메커니즘 | 학술 증거의 강도 | 부정적·감쇠 증거 | 저장소 기존 결과 | 이 저장소 적합 목적 | 실행 판단 |
|---|---|---|---|---|---|---|---|
| A | 대형 승자 조기 탐지 | 개별주 수익의 양(+)의 왜도: 소수 종목이 시장 초과부를 모두 만듦 | 분포 사실은 강함, **사전 예측 가능성은 문헌이 입증하지 않음** | 승자 선택을 사후에 하면 종속변수 표집 편향 | 꼬리 분류로 검정한 적 없음 | 선택 정확도(상위 꼬리 적중), 좌측 꼬리 회피 | **Study A 목표·라벨로 채택**, 단독 신호 아님 |
| B | 재무·영업 변곡점 | 실적 변화에 대한 과소반응 | 중간(이익 모멘텀, F-score, 수익성) | 발표 후 감쇠, 소형주 집중 | 미국·한국 펀더멘털 가속 합성 Case D, KR Phase C C군 통과 0 | 기대수익·선택 | **Study A 1차 가설**, 단 기존 가속과의 구별성 선측정 |
| C | 실적 발표 후 표류(PEAD) | 이익 서프라이즈 과소반응 | 역사적으로 강함 | 대형주에서 2006년 이후 소멸 보고(Martineau 2022), 2025년 반론 존재 | 미검정 | 진입 시점(H21~H63) | 낮음. KR 잠정실적 시각 수집이 **유일한 저비용 KR 신정보축**이라 데이터 구축만 후보 |
| D | 산업 선도주·공급망 확산 | 산업 내 정보의 느린 확산 | 중간(산업 모멘텀, 산업 내 lead-lag, 고객 모멘텀) | 효과가 소형·저커버리지에 집중 | KR 산업층 개발 지지(2025~26·전기전자 집중), X3 무증거/차단 | 선택 | Study A 2차 가설(산업 확산), 공급망은 데이터 없음 |
| E | 저평가 해소·재평가 | 외삽 과잉 후 평균회귀 | 장기적으로 강했음 | 대형 가치 프리미엄 1991~2019 월 0.05%(Fama–French 2021) | KR B군 8평가 중 4 반대부호, X1 p=0.99 | 기대수익 | Study A 보조(설명용)만 |
| F | 과거 유사 사례 패턴 탐색 | 상태공간 최근접 이웃 | 확립된 주식 선택 증거 없음 | 유사도 정의 자체가 숨은 탐색, PBO 최대 | 없음 | — | **진행 금지** |
| G | 성장·물가·금리·신용 국면 조건부 | 위험프리미엄의 경기 의존 | 약~중간(제약·결합 시 작은 OOS 개선) | 대부분 예측변수 OOS 실패(Welch–Goyal 2008), 개정 데이터 누설 | 거시 빈티지 미구축, KR X6 기술통계만 | 노출·조건화 | Study B, 미국 빈티지 변수만, 기술통계 위주 |
| H | 추세·변동성 기반 노출 조절 | 변동성 군집, 하락장 지속 | 낙폭 감소는 비교적 견고, 수익 개선은 약함 | 103개 전략 OOS 무우위(Cederburg 외 2020), 비용 후 소멸 | KR 시장위험 모델 v1: C0 유지, 수동보유가 수익 더 높음 | 손실 위험(MDD/CVaR) | **Study C, 최우선 실험의 근거** |
| I | 금융위기 취약성·좌측 꼬리 | 신용·자산가격 동반 급등 후 위기 | 국가 패널에서 강함 | 한 국가 13년에는 위기 사례가 거의 없음 | KR 재가파름 플래그 AUROC 약 0.66(기술) | 손실 위험 | SLOW층 사전정보로만, 위기 예측 주장 금지 |
| J | 산업·시장 국면 전환 탐지 | 은닉 국면의 확률적 추정 | 자산배분에서 일부 OOS 지지 | 평활 확률의 미래 누설, 국면 수 적음 | 생산 `regime.py` 미검증 | 노출 | 낮음. 결정론적 과거전용 상태로 대체 |
| K | 확률·불확실성 기반 비중·청산 | 추정오차를 반영한 축소 | 원리 강함(BL, 1/N) | 최적화가 1/N을 못 이김(DeMiguel 외 2009) | 보정된 기대초과수익 없음 → Kelly 관문 미통과 | 비중 | 보정된 예측이 생긴 뒤에만 |
| L | 조건부 앙상블·동적 결합 | 모형 불확실성·불안정성 완화 | 단순 평균 결합의 OOS 이득(Rapach 외 2010) | 동적 가중은 추정오차 증가 | KR 토너먼트 BLOCKED, Phase C B4가 B0보다 오차 큼 | 예측 안정화 | 독립 검증 구성요소 ≥2개 이후 단순 평균만 |

## 2. 방법론별 상세

각 항목은 같은 순서다: 메커니즘 → 반증 가능한 가설 → 대표 문헌(원문 링크) → 부정적 후속 연구 → 저장소 미검증 부분 → 데이터·PIT → KR/US 구현 가능성 → 기존 팩터와 다른 정보 → 주요 위험 → 목적 → 최소비용 검증·중단 기준.

### A. 대형 승자 조기 탐지

- **메커니즘.** 개별 종목 수익률은 월간 수익의 왜도와 복리 효과로 강한 양의 왜도를 가진다. 중앙값 종목은 현금도 이기지 못하고, 시장 전체 초과부는 극소수가 만든다. 따라서 무작위 5종목 책은 승자를 놓칠 확률이 높고 지수를 이기기 구조적으로 어렵다. 이것은 **수동보유 기본값의 이론적 근거**이기도 하다.
- **반증 가설.** 사전 조건 S가 같은 날짜·업종·규모 대조군 대비 `P(상위 10% 벤치마크 초과 | S)`를 높이면서 `P(하위 10% | S)`를 같은 비율로 높이지 않는다. `LOR(승자) − LOR(대형손실) ≤ 0`이면 S는 선택 정보가 아니라 변동성 대용이다.
- **문헌.**
  - Bessembinder (2018), *Do stocks outperform Treasury bills?*, JFE 129, 440–457. 1926~2016 CRSP에서 상위 약 4%(1,092개, 약 4.3%)가 순 초과부 전부를 설명, 58%가 생애 수익으로 T-bill에 못 미침. [ASU 요약](https://news.wpcarey.asu.edu/20180917-do-stocks-outperform-treasury-bills) · [원문 PDF](https://wpcarey.asu.edu/sites/default/files/2021-10/do-stocks-outperform-treasury-bills.pdf)
  - Bessembinder, Chen, Choi, Wei (2023), *Long-term shareholder returns: Evidence from 64,000 global stocks*, FAJ 79(3). 1990~2020 전 세계 64,000여 종목 중 2.4%가 순 부 창출 전부, 미국 55%·비미국 57%가 T-bill 미달. [CFA Institute](https://rpc.cfainstitute.org/research/financial-analysts-journal/2023/long-term-shareholder-returns-evidence-from-64000-global-stocks)
- **부정적 측면.** 두 논문은 **분포를 기술**할 뿐 승자를 사전에 맞히는 방법을 제시하지 않는다. 승자를 먼저 고르고 공통점을 찾는 사례 연구는 종속변수 표집으로, `P(S | 승자)`를 `P(승자 | S)`로 오독하게 만든다.
- **저장소 미검증.** 어떤 연구도 꼬리 사건 분류를 1차 목표로 측정하지 않았다(KR Phase C는 삼분위 평균 스프레드, 미국은 순위 IC).
- **데이터·PIT.** 상장폐지 수익을 포함한 생애 총수익이 필요하다. KR 종결 22종목의 종결 대가 미해결, 미국 퇴출 신원 324개 중 212개 무가격(`NOT_ADMITTED`). **좌측 꼬리가 잘린 표본**이라 대형손실 기저율이 과소 측정된다.
- **구현.** KR: 역사 검정은 Phase D 종료로 불가, 전향만. US: 생존 조건부 개발 증거로만.
- **신규 정보.** 없음. 정보가 아니라 **목표 함수(꼬리)와 평가 방식**의 변경이다.
- **위험.** 사례 우선 표본, 생존편향, 절대 임계값의 국면 의존(상승장에선 누구나 +50%), H252 중첩.
- **목적.** 선택 정확도(상위 정밀도), 손실 위험(좌측 꼬리 회피).
- **최소비용 검증·중단.** 결과를 읽지 않는 측정력·최소검출효과(MDE) 사전검사(A0) 후 단 1회의 상대 꼬리 농축 검정. MDE가 사전 기대 효과보다 크면 역사 검정을 건너뛰고 전향 기록만 한다.

### B. 재무·영업실적 변곡점

- **메커니즘.** 투자자가 이익·현금흐름 추세 전환을 늦게 반영한다(보수주의·과소반응).
- **반증 가설.** TTM 영업이익 전년비 증가율이 최근 공시에서 ≤0에서 >0으로 바뀌고 TTM 영업현금흐름이 양수인 사건(현금 확인 변곡점)은 매칭 대조군보다 H126/H252 초과수익이 높다.
- **문헌.**
  - Chan, Jegadeesh, Lakonishok (1996), *Momentum strategies*, JF 51(5), 1681–1713. 과거 수익률과 과거 이익 서프라이즈가 서로를 통제해도 각자 표류를 예측, 애널리스트 예측도 느리게 반응. [RePEc](https://ideas.repec.org/a/bla/jfinan/v51y1996i5p1681-1713.html)
  - Piotroski (2000), *Value investing: The use of historical financial statement information to separate winners from losers*, JAR. 고 B/M 종목 중 9개 회계 신호 점수로 승자·패자 구분. 성과 수치(연 +7.5% 등)는 2차 요약에서만 확인 → `원문 표 미확인`. [요약](https://blog.validea.com/joseph-piotroski-separating-winners-from-losers-in-value-investing/)
  - Novy-Marx (2013), *The other side of value: The gross profitability premium*, JFE 108(1), 1–28. 매출총이익/자산이 B/M과 비슷한 예측력. [요약](https://academicnewsletter.sufe.edu.cn/info/356633)
- **부정적 증거.** McLean–Pontiff 감쇠, Hou–Xue–Zhang 재현 실패율. 저장소 자체: 펀더멘털 가속 합성(미국 IC −0.0056 [−0.0295, +0.0183], 한국 Case D), KR Phase C C군 BY/Holm 통과 0.
- **저장소 미검증.** "연속 변화량 z점수"가 아니라 **부호 전환 사건 + 현금 확인**의 사건 정의는 검정되지 않았다. 다만 이것이 정말 다른 정보인지는 측정 전엔 모른다 → A0에서 기존 가속·성장 특성과의 순위상관을 먼저 잰다(|ρ|>0.70이면 재명명으로 보고 중단).
- **데이터·PIT.** KR DART(접수일 다음 날, 2015~, 2016 성장 계열은 구조적 공백), US Finnhub(`max(availableFrom, acceptedDate)` 다음 날, 2011~). 미국 전향은 2026-10-07 이후 재무상태표 누락으로 차단.
- **위험.** 정정 공시 누설(최초 공개본만), 연결/별도 혼용, 분모 음수, 주식수 기준.
- **목적.** 기대수익, 선택 정확도.
- **최소비용 검증·중단.** A0 구별성·커버리지 → A1 미국 단회 검정. 구별성 실패 또는 MDE 과대 시 역사 검정 생략.

### C. 실적 발표 후 표류(PEAD)

- **메커니즘.** 이익 서프라이즈가 발표 후 수주~수개월에 걸쳐 가격에 반영.
- **반증 가설.** 계절 랜덤워크 기준 표준화 서프라이즈(SUE) 상위 분위가 발표 다음 거래일부터 H63 동안 업종 매칭 대조군보다 초과수익이 높다.
- **문헌.** Bernard–Thomas (1989), JAR(SUE 십분위 표류). Chan 외(1996)가 가격 모멘텀 통제 후에도 표류 잔존 보고.
- **부정적 증거.** Martineau (2022), *Rest in peace post-earnings announcement drift*, Critical Finance Review 11, 613–646: 대형주에서 2006년 이후 표류 부재, 초소형주에서도 최근 소멸. [RePEc](https://ideas.repec.org/a/now/jnlcfr/104.00000122.html) · 2025년 두 논문이 반론(연구설계 차이로 해석) [UCLA Anderson Review](https://anderson-review.ucla.edu/is-post-earnings-announcement-drift-a-thing-again/)
- **저장소 미검증.** 전부.
- **데이터·PIT.** 발표 **시각**이 필수. 미국 8-K는 SEC 차단(403), 10-Q `acceptedDate`는 실적 발표보다 수일~수주 늦어 이미 반영된 뒤다 → 미국은 "공시 후 표류"이지 PEAD가 아니다. 한국은 DART `list.json`의 영업(잠정)실적 공정공시 접수 시각으로 구축 가능(동일 키·확인된 엔드포인트, 본문 파싱은 미확인).
- **기존 팩터와 다른 정보.** KR에서는 **사건 시각**이라는 새 정보축. Phase D가 허용하는 "실제 새로운 정보축"에 해당할 수 있다.
- **위험.** 대형주 효과 소멸, 컨센서스 부재(계절 랜덤워크는 약한 기대 모형), 지평 불일치(H63 ≠ 6~12개월).
- **목적.** 진입 시점·선택의 보조.
- **최소비용 검증·중단.** KR 잠정실적 공시의 커버리지·시각 정밀도 감사(결과 없음)만 먼저. 커버리지 <60% 또는 시각이 장중/장후 구분 불가하면 중단.

### D. 산업 선도주·공급망·후발 수혜 확산

- **메커니즘.** 산업 공통 정보가 대형·주목받는 종목에 먼저 반영되고, 덜 주목받는 동종·공급망 종목에 늦게 확산.
- **반증 가설.** 같은 산업의 대형 선도주(시가총액 상위)가 직전 126일 벤치마크 대비 상위 삼분위인데 자기 자신은 산업 중앙값 이하였던 종목(후발주)은 산업 매칭 대조군보다 H126 초과수익이 높다.
- **문헌.**
  - Moskowitz–Grinblatt (1999), *Do industries explain momentum?*, JF 54(4), 1249–1290 (2차 인용으로 확인).
  - Hou (2007), *Industry information diffusion and the lead-lag effect in stock returns*, RFS 20(4), 1113–1138: 대형→소형 lead-lag는 주로 산업 내 현상, 부정적 뉴스의 느린 반영, 경쟁이 약하고 소외된 산업에서 강함. [RePEc](https://ideas.repec.org/a/oup/rfinst/v20y2007i4p1113-1138.html)
  - Cohen–Frazzini (2008), *Economic links and predictable returns*, JF 63, 1977–2011: 고객 충격 후 공급사 매매 월 150bp 이상 알파, SFAS 131 고객 공시 이용. [AQR](https://www.aqr.com/Insights/Research/Journal-Article/Economic-Links-and-Predictable-Returns)
- **부정적 증거.** Parsons–Sabbatucci–Titman(2020 WP)은 산업 lead-lag가 소형·저거래·저커버리지 종목에서 가장 강하다고 보고(Hou 인용 맥락) → 대형주 유니버스에서 약할 가능성. 저장소: KR 산업층 개발 지지는 2025~2026·전기전자에 집중, Phase C X3 무증거/차단, H08 반대 부호.
- **저장소 미검증.** "선도 대 후발" 비대칭 정의, 미국에서는 산업 정보 자체가 미검정.
- **데이터·PIT.** KR: KRX 산업 소속 재구성(v4) 사용 가능. US: 스냅샷의 GICS **섹터(11개)**만, 하위산업 없음 → 확산 검정에는 거침. 공급망: 미국 SEC 고객 공시 차단, 한국 소스 없음 → `NOT_FEASIBLE`.
- **위험.** 산업 분류 소급, 산업 내 종목 수 부족, 선도주 정의의 자유도.
- **목적.** 선택.
- **최소비용 검증·중단.** Study A의 두 번째 가설로 같은 실행 안에서 Holm 보정. 산업당 유효 종목 <5인 날짜 비중 >30%면 미국에서 비평가.

### E. 저평가 해소·평가배수 재평가

- **메커니즘.** 투자자가 과거 성장을 과도하게 외삽 → 저평가 종목의 평균 회귀.
- **문헌.** Lakonishok–Shleifer–Vishny (1994, JF) 외삽 가설(2차 인용으로 확인). Asness–Moskowitz–Pedersen (2013), *Value and momentum everywhere*, JF, 929–985: 8개 시장에서 가치·모멘텀 프리미엄, 둘은 음의 상관. [원문 PDF](https://pages.stern.nyu.edu/~lpederse/papers/ValMomEverywhere.pdf)
- **부정적 증거.** Fama–French (2021), *The value premium*, RAPS 11(1), 105–121: 1963~2019 표본 후반에 대형 가치 프리미엄이 월 0.36%→0.05%로 하락, 그러나 변동성이 커서 두 기간의 기대 프리미엄이 같다는 가설을 기각 못함. [RePEc](https://ideas.repec.org/a/oup/rasset/v11y2021i1p105-121..html)
- **저장소.** KR B군 8평가 중 4 반대부호, X1(가치×사업건전성) p=0.9895. 미국 가치는 재구성 가격·가중평균 주식수 기준(검증 안 됨).
- **목적·판단.** 기대수익. 독립 가설로는 낮음. Study A에서 변곡점 사건의 **효과 이질성 설명용**(저평가 구간에서 더 큰가) 기술통계로만.

### F. 과거 유사 사례 기반 상태·순서 패턴 탐색

- **메커니즘.** 현재 상태와 가장 비슷한 과거 사례의 사후 경로를 예측으로 사용.
- **증거.** 주식 횡단면 선택에서 확립된 학술 근거를 찾지 못했다. 비모수 ML 비교(Gu–Kelly–Xiu 2020)에서도 표준 방법으로 다뤄지지 않는다.
- **부정적 증거.** Bailey, Borwein, López de Prado, Zhu, *The probability of backtest overfitting*(J. Computational Finance): 다수 시도 중 표본 내 최우수가 표본 밖 중앙값 이하일 확률(PBO)을 CSCV로 측정. 유사도 척도·창·이웃 수 선택은 모두 숨은 시도다. [SSRN](https://papers.ssrn.com/abstract=2326253)
- **판단.** **진행 금지.** H252 독립 코호트 10여 개로 유사도 공간을 탐색하는 것은 과최적화 그 자체다. Study A의 동결 모형이 나온 뒤 "가장 비슷했던 과거 사례 3개"를 보여주는 **설명용 출력**만 허용.

### G. 성장·인플레이션·금리·신용 국면 조건부 수익 예측

- **메커니즘.** 위험프리미엄과 팩터 보상이 경기·금리·신용 상태에 따라 달라진다.
- **문헌.**
  - Welch–Goyal (2008), RFS: 대부분의 주식 프리미엄 예측변수가 표본 내외 모두 부진·불안정. [원문 PDF](https://www.johnhcochrane.com/s/Goyal_Welch.pdf)
  - Campbell–Thompson (2008), RFS 21: 계수·예측 부호 제약 시 작지만 경제적으로 의미 있는 OOS 개선. [NBER](https://nber.org/papers/w11468)
  - Rapach–Strauss–Zhou (2010), RFS 23(2), 821–862: 예측 결합이 역사 평균 대비 통계·경제적 OOS 이득. [RePEc](https://ideas.repec.org/a/oup/rfinst/v23y2010i2p821-862.html)
  - 실시간 데이터: Croushore–Stark (2001), J. Econometrics, 실시간 빈티지 데이터셋. [Philadelphia Fed WP](https://www.philadelphiafed.org/-/media/frbp/assets/working-papers/1999/wp99-4.pdf?la=en) · Ghysels–Horan–Moench (2018), *Forecasting through the rearview mirror: Data revisions and bond return predictability*, RFS 31(2) (서지 정보만 확인).
- **부정적 증거.** Welch–Goyal 자체. 개정된 거시 데이터로 과거를 재구성하면 당시 알 수 없던 정보를 쓴다.
- **저장소.** 미국 거시 패널 28열 중 10열은 ALFRED에 빈티지가 전혀 없음(AGENTS v2.9 측정), `macroVintageSeries`는 비어 있음. KR ECOS는 빈티지 없음 → `PIT_UNSAFE`. FRED의 ICE HY/IG 스프레드는 2023-10 이후만 유효(KR 시장위험 설계 기록).
- **목적.** 노출 조절과 신호 조건화. **Study B**에서 시장 관측 변수와 진짜 거시 변수를 분리해 다룬다.
- **최소비용 검증·중단.** 미국 ALFRED 빈티지 열을 시작일 기준으로 재구성해 커버리지를 측정(결과 없음). 상태별 비중첩 H블록 <6이면 추론하지 않고 기술통계만.

### H. 시장 추세·변동성 기반 노출 조절

- **메커니즘.** 변동성은 지속되고 기대수익과 비례하지 않으므로 고변동기 노출을 줄이면 위험 대비 수익이 개선될 수 있다. 추세 이탈은 장기 하락의 초기 신호일 수 있다.
- **문헌.**
  - Moreira–Muir (2017), JF, 변동성 관리 포트폴리오의 스패닝 회귀 알파(배경지식, 원문 미재확인).
  - Faber (2007), 10개월 이동평균 규칙: 수익은 비슷하고 낙폭·변동성 감소(2차 요약). 2018 갱신에서 2008~09에 크게 이겼으나 이후 8년 중 6년 열세. [요약](https://www.etf.com/sections/index-investor-corner/swedroe-why-financial-trends-persist)
  - Moskowitz–Ooi–Pedersen (2012), 시계열 모멘텀.
  - Daniel–Moskowitz (2016), *Momentum crashes*, JFE 122(2), 221–247; Barroso–Santa-Clara (2015), *Momentum has its moments*, JFE 116(1), 111–120: 모멘텀 위험은 예측 가능하고 위험 관리로 붕괴 완화. [NBER](https://www.nber.org/papers/w20439) · [요약](https://academicnewsletter.sufe.edu.cn/info/356496)
- **부정적 증거.** Cederburg, O'Doherty, Wang, Yan (2020), JFE: 103개 주식 전략에서 변동성 관리 버전이 원 전략을 체계적으로 이기지 못함, 스패닝 회귀의 구조적 불안정이 원인. Barroso–Detzel(2020)은 거래비용 후 소멸 보고(2차 인용). [저자 PDF](https://www.lehigh.edu/~xuy219/research/COWY.pdf) · Huang, Li, Wang, Zhou (2020), *Time series momentum: Is it there?*: 자산별 회귀에서 TSM 증거 미약, 표본평균 전략과 성과 비슷. [WUSTL](https://profiles.wustl.edu/en/publications/time-series-momentum-is-it-there/)
- **저장소.** `kr-market-risk-model-v1`(2007~2026, 가격지수·현금 0%): 수동 9.73%/MDD −52.9%, C0 6.73%/−40.9%(감축 세션 50.2%), C1 7.14%/−36.8%(28.2%). 판정 `NO_CANDIDATE_NOMINATED_CONTROL_RETAINED`. 즉 **낙폭은 줄이고 수익은 잃는 교환**이 재현되었다.
- **목적.** 손실 위험. 수익 개선 주장은 하지 않는다.
- **최소비용 검증·중단.** 이미 봉인된 KR 규칙을 **파라미터 그대로** 미국 지수에 적용하는 복제(최우선 실험, 문서 05).

### I. 금융위기 취약성·좌측 꼬리손실 탐지

- **문헌.** Schularick–Taylor (2012), *Credit booms gone bust*, AER 102(2), 1029–1061: 14개국 1870~2008, 신용 증가가 위기를 예측. [재현 데이터](https://journaldata.zbw.eu/dataset/37c37bdb-c67b-42c3-a8c1-e560ef3b1462) · Greenwood, Hanson, Shleifer, Sørensen (2022), *Predictable financial crises*, JF 77(2): 직전 3년 신용과 자산가격 동반 급등 시 3년 내 위기 확률 약 40%(평시 약 7%). [NBER WP](https://www.nber.org/system/files/working_papers/w27396/w27396.pdf)
- **한계.** 증거는 **수십 개국 × 백 년 이상**의 연간 패널이다. 한 국가 13~35년에는 위기가 0~2회다.
- **저장소.** KR 시장위험 해부 v2의 재가파름 플래그(H252 ≤−15% 사건률 56.2% vs 23.5%, AUROC 0.66)는 기술통계, 낙폭 사건 8~13회.
- **판단.** 이미 봉인된 SLOW층으로만 사용. 위기 예측 능력 주장 금지. BIS 신용/GDP는 분기·개정 데이터로 빈티지 없음 → `PIT_UNSAFE`.

### J. 산업·시장 국면 전환 탐지

- **문헌.** Ang–Bekaert (2002), RFS 15(4), 국면 전환 국제 자산배분. Guidolin–Timmermann (2007), JEDC 31(11): 주식·채권 결합 분포에 붕괴·저성장·강세·회복 4개 국면 필요. [UCSD PDF](https://rady.ucsd.edu/_files/faculty-research/timmermann/regime-switching.pdf)
- **위험.** 평활(양방향) 국면 확률은 미래 정보를 쓴다. 필터링 확률만 허용해야 하며, 라벨 전환·국면 수 선택이 숨은 자유도다.
- **판단.** 낮음. 저장소의 결정론적·과거전용 상태(FAST/SLOW/TRANSITION)가 같은 역할을 더 적은 자유도로 한다.

### K. 확률·불확실성 기반 종목 비중·청산

- **문헌.** Black–Litterman (1992, FAJ) 균형 기대수익에 견해와 확신도를 결합(배경지식, 원문 미재확인). DeMiguel–Garlappi–Uppal (2009), RFS 22(5), 1915–1953: 14개 최적화 모형이 Sharpe·CEQ·회전율에서 1/N을 일관되게 못 이김, 25개 자산이면 약 3,000개월 추정창 필요. [RePEc](https://ideas.repec.org/a/oup/rfinst/v22y2009i5p1915-1953.html)
- **원칙.** 확신도 0인 견해의 BL 해는 벤치마크다. 보정된 기대초과수익과 표준오차가 없으면 **최적 활성 비중은 0**이다. 이것이 `weekly-passive-first-v1`이 709/713주 지수 100%였던 이유와 같다.
- **확률 평가.** 확률은 적절한 점수규칙(Brier, 로그손실)과 신뢰도 도표로 평가한다: Gneiting–Raftery (2007), JASA 102(477). [요약](https://academicnewsletter.sufe.edu.cn/info/445563) · 희소사건 로지스틱의 확률 과소추정: King–Zeng (2001), Political Analysis 9(2). [Harvard](https://gking.harvard.edu/publication/logistic-regression-in-rare-events-data/)
- **판단.** 보정된 예측이 생긴 뒤에만. 청산 규칙(손절)은 별도 가설로 추가하지 않는다.

### L. 여러 전략의 조건부 앙상블·동적 결합

- **문헌.** Rapach–Strauss–Zhou (2010) 결합 예측. Gu–Kelly–Xiu (2020), *Empirical asset pricing via machine learning*, RFS 33, 2223–2273: 트리·신경망이 최선, 지배적 신호는 모멘텀·유동성·변동성 변형. [NBER](https://www.nber.org/papers/w25398.pdf)
- **부정적 증거.** 동적 가중치는 추정오차를 늘린다(DeMiguel 외). 저장소: KR Phase C B4 복합모형 MSE가 모든 기간에서 B0보다 큼(H126 +0.66%), KR 토너먼트 `BLOCKED_BY_DATA_INTEGRITY`.
- **판단.** 각자 독립 지지를 받은 구성요소가 **2개 이상** 생긴 뒤, 사전 고정한 **동일가중** 결합만. 동적·조건부 가중은 금지.

## 3. 결론: 목적별 배치

| 목적 | 채택 방법론 | 배치 |
|---|---|---|
| 기대수익·선택 정확도 | A(목표), B(1차), D(2차), E(설명) | Study A |
| 신호의 조건부 성과 | G(미국 빈티지만), 시장 관측 상태 | Study B |
| 손실 위험·노출 | H(1차), I(SLOW 사전정보), J(대체됨) | Study C |
| 비중·결합 | K, L | 독립 검증 후 후속 단계 |
| 진행 금지 | F | — |
| 데이터 구축 후보 | C(KR 잠정실적 시각) | 정보축 구축 트랙 |
