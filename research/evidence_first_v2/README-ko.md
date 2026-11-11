# Evidence-First Alpha Research & Decision System v2

목표: 6~12개월 동안 기준 ETF(KR 069500.KS, US SPY, QQQ는 별도 비교)를 이길 종목을 0~5개 찾는다. 0개도 정상 결과다.
이 폴더는 **왜 이 종목을 분석 대상으로 삼았는지, 어떤 근거가 있고, 어디까지 검증되었는지**를 파일과 화면에서 직접 확인할 수 있게 만든다.
통합감사(#333)는 다시 하지 않았고, 새 모델 토너먼트도 만들지 않았다. main, production, signal-history, workflow, lock, 봉인 연구, 11월 전향 기록은 수정하지 않았다.

## 파일

| 파일 | 내용 |
|---|---|
| `literature.json` | A. 선행연구 표 (읽은 원천과 그 범위만 기록) |
| `evidence-grades.json` · `contract.py` | B. E0~E5 등급 행렬, 순차 규칙 검증, 경로 이름 매핑, B3 AI 계약 |
| `census.py` → `results/census.json` | C. KR/US 유니버스 퍼널(제외 사유별 건수), B1 선별, production 관찰 목록과 비교 |
| `academic-path-protocol.json` · `academic_path.py` → `results/academic-path.json` | D. 사전 등록 후 실행한 학술 경로 번역 시험 |
| `ai-dossiers-2026-11.json` · `b3_dossiers.py` → `results/b3-dossiers.json` | E. AI(B3) 기업 분석과 반대 논거 |
| `test_evidence_first_v2.py` | 계약·재현성 테스트 16개 |
| `../decision_desk_v1/build_desk.py` · `desk.json` · `app.js` | F. 화면 (`evidenceFirst` 블록) |

## A. 선행연구

| 연구 | 읽은 곳 | 원 연구 구조 | 우리에게 옮길 때 |
|---|---|---|---|
| Fama-French 5요인 (2015) | Ken French 자료실 본문 | 2×3 정렬, 가치가중, 롱숏, 연 1회 리밸런싱 | 자료실의 롱온리 정렬 포트폴리오는 생존편향이 없고(CRSP) 공개 시점이 지연되어 있어 미국 번역 시험에 그대로 썼다. 한국은 해당 자료가 없다. |
| Jegadeesh-Titman (1993) | RePEc 초록 (Wiley 403) | 승자-패자 롱숏 | production 모멘텀 슬리브와 겹친다(국지 rank IC −0.0015). |
| QMJ (2019) | RePEc 초록 (Springer·SSRN 거부) | 롱숏 품질 요인, 24개국 | 우리 품질 슬리브는 수익성·안전성 일부만 담고 성장·배당 요소는 없다. |
| Novy-Marx GP (w15940) | NBER 초록 | 횡단면 정렬·회귀, 롱숏 | 총이익/자산은 PIT 저장소에 없어 ROE·영업이익률로 대신한다. |
| Novy-Marx 다중신호 (w21329) | NBER 초록 | 방법론 | 신호 결합은 과적합된다. 그래서 B1은 신호 하나, 시험은 주 포트폴리오 하나에 Bonferroni 기준으로 제한했다. |

다섯 연구 모두 **횡단면**(어떤 종목이 다른 종목보다 나은가)에 관한 것이며, 지수의 방향을 예측하는 **시계열** 연구가 아니다.
롱숏 결과를 0~5종목 롱온리에 옮기지 않았다. 롱온리로 번역할 때 생기는 차이는 D에서 따로 측정했다.

## B. E0~E5 등급

등급은 순서대로만 올라간다. 유명한 논문이 있어도 E2를 건너뛰지 않는다. 등급과 별도로 차단 상태(SOURCE_BLOCKED, PIT_UNSAFE, PIT_CONTAMINATED, GOVERNANCE_CLOSED)를 둔다.
판단에 쓰려면 E4 이상이면서 차단 상태가 없어야 한다. 현재 이 조건을 만족하는 항목은 **0개**이므로 기본값은 ETF다.

| 항목 | 등급 | 차단 |
|---|---|---|
| production 4요인 순위 KR | E1 | — (정렬 미확인, rank IC t 0.68) |
| production 4요인 순위 US | E1 | SOURCE_BLOCKED |
| KR ML v1 141개 | E0 | SOURCE_BLOCKED |
| KR 산업모멘텀 | E1 | SOURCE_BLOCKED (위상 의존) |
| KR 전략모멘텀 칵테일 | E0 | SOURCE_BLOCKED |
| KR S2 가치·확인 | E1 | SOURCE_BLOCKED (전향 기록 축적 중, 만기 없음) |
| KR 상태학습 전략선택 | E0 | — (OOS R² 9개 모두 음수) |
| 신규 KR 과거 종목 연구 | E0 | GOVERNANCE_CLOSED + SOURCE_BLOCKED |
| US 동적 멀티에셋 | E0 | — (비용 후 정적 S4 열위) |
| US 추세 낙폭방어 | E0 | — (2008 한 사건) |
| US 과거 개별주 | E0 | SOURCE_BLOCKED (퇴출 324개 중 212개 무가격) |
| 데스크 2026-11 AI 판단 | E0 | PIT_CONTAMINATED |
| B1 학술 수익성 US | E1 | — (D 판정: 발표 후 약함) |
| B1 학술 수익성 KR | E1 | GOVERNANCE_CLOSED |
| ETF 069500.KS / SPY | 기준 | — |

## C. 유니버스 퍼널 (KR 2026-10-30, US 2026-11-10)

| 단계 | KR | US | 주요 제외 사유 |
|---|---|---|---|
| 0 원래 유니버스 | 300 | 503 | KR 시총 상위 300 스냅샷, US 현재 S&P 500 |
| 1 보통주 신원 | 289 | 503 | 우선주 11 |
| 2 매매 가능 | 252 | 500 | KR 저거래대금 36, 최근 20일 거래 0 1 / US 종가 없음 3 |
| 3 가격 이력·기업행동 | 238 | 498 | KR 미해결 기업행동 12, 252일 미만 2 / US 252일 미만 2 |
| 4 PIT 재무·팩터 계산 가능 | 78 | 356 | KR PIT 공시 없음 121, 영업이익 정의 불일치 21, 수익성 결측 17 / US 장부가·부채 결측 60, 수익성 결측 40 |
| 5 (참고) 팩터별 상위 20% 합집합 | 42 | 188 | 정보용 |
| 6 B1 적격 | 61 | 206 | 4단계 통과 + 대형주 + 영업이익률>0 + 부채/자본≤2 |
| 7 심층검토 (B1 상위 5) | 5 | 5 | |
| 8 최종 연구 선정 | **0** | **0** | 어떤 경로도 E2에 도달하지 못함 → ETF_DEFAULT |

- `|영업이익률| > 1`을 회계정의 불일치로 처리하는 규칙은 자료를 본 뒤에 추가했다(SK스퀘어 27.0). 이 사실은 `rulesAddedAfterInspection`에 기록되어 있다.
- production 관찰 목록과 B1 상위 20%는 거의 겹치지 않는다(KR 공통 3 · B1만 9 · production만 9 / US 공통 1 · B1만 40 · production만 11). 두 선별의 기준이 다르다는 뜻이며, 수익에 대한 정보는 아니다.
- **생존편향**: US 센서스는 현재 구성종목만 담는다. 현재 화면용 선별에만 쓰고, 과거 성과 주장에는 쓰지 않는다.

## D. 측정한 경로

과거 개별 종목 경로는 KR이 GOVERNANCE_CLOSED, US가 SOURCE_BLOCKED여서, 측정 가능한 경로는 공개 자료로 수행한 학술 번역 시험 하나다.
프로토콜(`academic-path-protocol.json`)을 커밋 `1493d211`로 먼저 고정하고 나서 수익을 계산했다.
대상은 Ken French 자료실의 ME5×OP5 등 롱온리 가치가중 포트폴리오이고, 비교 기준은 시장(Mkt)이다. Newey-West HAC t(lag 12)를 썼다.

| 포트폴리오 | 발표 후 2013-01~2026-09 연 초과 | HAC t | 비용 0.5%p 후 | 12개월 양(+) 비율 | 최대 상대낙폭 |
|---|---|---|---|---|---|
| 대형 고수익성 (주 시험) | +1.03%p | 0.81 | +0.53%p | 61% | −13.7% |
| 고수익성 전체 규모 | +0.74%p | 0.64 | +0.24%p | 61% | −14.2% |
| 대형 가치 | +5.19%p | 1.10 | +4.69%p | 51% | −44.2% |
| 대형 승자 (비용 2%p) | +1.64%p | 0.79 | −0.36%p | 64% | −19.6% |

판정은 **WEAK_OR_ABSENT_AFTER_PUBLICATION**이다. 발표 후에는 어떤 포트폴리오도 Bonferroni 기준 |t|≥2.5를 넘지 못했다.
발표 전에는 대형 승자가 t 2.56으로 넘었다. 수익성은 E1에 머문다. 이 판정이 정하는 것은 E2 시도에 유료 원천을 쓸 가치가 있는지뿐이다.

## E. AI(B3)의 정보 가치와 미검증 영역

- AI는 B1이 고른 KR 5개(에이피알, HD현대일렉트릭, SK하이닉스, HD현대마린솔루션, 삼양식품)와 US 5개(NVDA, KLAC, IDXX, WDC, LRCX)**만** 검토했다. 화면에 나오는 숫자는 모두 센서스에서 생성된 사실 행이며 기준기간과 공개일이 붙어 있다. AI 문장에는 숫자를 쓸 수 없고, 쓰면 계약이 거부한다.
- 상태는 10개 모두 **HOLD_FOR_RESEARCH**다. 지명한 경로가 E1이므로 그 이상은 계약상 불가능하다.
- AI가 덧붙인 것:
  - 집중 위험: US 5개 중 4개가 반도체·장비·저장장치이고, KR 5개 중 2개가 HD현대 계열이다.
  - 경기순환 정점의 높은 ROE를 경계해야 한다(SK하이닉스, WDC).
  - 자본 축소가 ROE를 키웠을 가능성이 있다(KLAC, IDXX).
  - 가격 추세가 음수인 고수익성 종목이 있다(삼양식품, IDXX).
  - 각 종목의 훼손 조건과 모르는 것.
- 미검증 영역:
  - 배경 문장은 모델 지식이며 NOT_VERIFIED로 표시했다.
  - 컨센서스·가이던스·뉴스는 읽지 않았다(합법적 원천 없음).
  - 이 AI 판단이 B1이나 ETF보다 낫다는 증거는 없다. 판단 기록을 남겨 전향으로 평가해야만 알 수 있다.
  - 2026-11 TRV / KR-0 기록은 PIT_CONTAMINATED 그대로 두었다.
  - 삼성전기는 소급 등록하지 않았다(테스트로 확인).

## F. 화면

`desk.json`에 `evidenceFirst` 블록을 추가했다. 화면 순서는 다음과 같다.

1. 현재 production 판단
2. 데이터·모델 적격성
3. 유니버스 퍼널
4. 선행연구·학술 시험·B1
5. AI 기업 분석과 반대 논거
6. E0~E5
7. 탐색·정정·전향 성과
8. 현재 선택과 과거 선택

기존 원장 기록은 다시 쓰지 않았다. 이름만 매핑해 표시한다: 기존 B0 → v3.B0, 기존 B1 → v3.B2 production 규칙, 기존 B2/BX → v3.B3 AI 실험.
"현재 검증된 production 판단"은 "현재 production 판단 — 기준 ETF를 이긴다는 검증은 아님"으로 바꿨다. AI 비중은 "AI 실험 기록 비중"으로 표시한다.
웹 배포는 별도 운영 승인 후에만 한다(#321 Pages 복구가 선행 조건이다).

## G. 재현

```bash
python research/evidence_first_v2/census.py                 # signal-history 6398e94 + 동결된 US 가격(data/us-prices)
python research/evidence_first_v2/academic_path.py          # 동결된 French 파일(data/french, SHA-256 manifest)
python research/evidence_first_v2/b3_dossiers.py
python research/decision_desk_v1/build_desk.py              # desk.json 재생성 + 계약 검증
python -m pytest -q research/evidence_first_v2 research/decision_desk_v1
node --test tests/decision_desk.test.cjs
```

## H. Owner 결정 (최대 3개)

1. **#321 merge와 Pages 정상화.** 모든 연구 PR의 CI가 threadpoolctl 3.8.0 충돌로 실패한다. 이 화면의 실제 게시도 그 이후에야 가능하다.
2. **전향 원장 활성화와 월간 리뷰 담당 지정.** 2026-12 코호트부터 B0/B1/B2/B3를 signal-history에 사전 기록할지, 그리고 AI 리뷰를 누가 언제 커밋할지 정해야 한다. E4로 가는 유일한 길이다.
3. **유료 원천 여부.** US E2에는 생존편향 없는 개별주 원천(Norgate·Sharadar 등)이 필요하다. KR에는 기업행동 패키지가 필요하다. 라이선스 조건을 확인한 뒤 결정한다. D 판정이 약하므로 서두를 이유는 없다.
