# 미국 판단일 정보 기반 종목 선택 가치 v1 (`us-selection-value-v1`)

**질문:** 판단일 종가 시점에 알 수 있던 정보만으로 종목을 골랐을 때, 향후 6·12개월 동안 거래비용을 뺀 SPY 대비 위험조정 성과가 좋아지는가.

- 증거 등급: `POST_HOC_EXPLORATORY_ON_OUTCOME_EXPOSED_US_HISTORY`. 승격·운영 변경은 없다.
- 사양 [`spec.json`](spec.json)은 미래 가격을 읽기 전에 고정했다(커밋 `e6c2f3ca`).
- 결과는 [`results/REPORT-ko.md`](results/REPORT-ko.md)에 있다.

## 입력 — 모두 이 환경에서 실제로 읽은 것

| 입력 | 원천 | 비고 |
|---|---|---|
| 가격 | replay-v16 at signal-history `704d7db6` | 순방향 총수익 지수, 2026-09-14까지 |
| 공시 | `ledger/fundamentals/us` at `704d7db6` | Finnhub financials-reported. 공개 시점 `max(availableFrom, acceptedDate)`, 판단일보다 엄격히 이전 |
| 구성·업종 | `research_specs/alpha-opportunity-model-v1-us-membership.json.gz`, `data/research/us-capital-allocation-alpha-v1/sp500-snapshot-sectors.json.gz` | 관측일 기준(효력일 아님) |
| SPY·QQQ | replay 종가 | QQQ는 2020-09-21 누락 분배금 0.38824달러를 한 번 반영(`docs/us-readiness/us-qqq-distribution-correction-v1.json`) |
| 원종가·분할 | Yahoo chart | 635개 전부 응답. **저장소 밖 비공개**(`$S/us/yahoo`). replay 경로와 대조해 607개 검증, 8개는 경로 불일치로 시총 없음 |

**#344(Codex)의 비공개 입력은 이 환경에 없다.** 해당 경로는 `/workspace/us-market-corrected-private-20261115`, `/workspace/us-topk-private-20261115`다. 대신 저장된 결과를 원 파일럿 입력으로 독립 재계산했다(`crosscheck_344.py`).

## 재사용 — 다시 구현하지 않음

- `scripts/run_us_decision_pilot.py`의 `load_prices`, `load_filings`, `AccountingCache`, `price_matrix_features`
- `pipeline/us_decision_pilot.py`의 `scores`(B1·B2), `simulate`(NAV)
- `pipeline/us_cash_profitability.py`의 현금수익성·시총 대용치
- `finnhub_derive`의 TTM

## 새 규칙 하나 — 2013–2022 신원 연결

구성 스냅숏 파일은 2023년부터만 CIK를 가진다. 그래서 파일럿 규칙(구성 CIK ∈ 공시 CIK)으로는 2013–2022년 적격 종목이 0개였다.
- CIK가 없는 스냅숏에서는 판단일 이전에 보이는 공시가 **모두 같은 CIK 하나**일 때만 받아들인다(`PIT_SINGLE_CIK`).
- CIK가 둘 이상이면 `CIK_AMBIGUOUS_EXCLUDED`로 제외한다.
- 두 규칙이 모두 적용되는 2023+ 이름-날짜에서 단일 CIK 규칙은 구성 CIK와 **73,415 / 73,981(99.23%)** 일치했다. 오분류는 약 0.8%다.

## 재실행

```bash
export OMP_NUM_THREADS=1
S=<저장소 밖 디렉터리>; mkdir -p $S/us
git fetch --depth=1 --filter=blob:none origin 704d7db6d5b00def771aba5d2665d0846d6bc776
python - <<'PY'   # 가격·공시 캐시 (파일럿 로더 그대로)
import importlib.util,pickle,sys; sys.path.insert(0,'.')
s=importlib.util.spec_from_file_location('p','scripts/run_us_decision_pilot.py'); P=importlib.util.module_from_spec(s); s.loader.exec_module(P)
import os; S=os.environ['S']+'/us/'
c,i=P.load_prices(); pickle.dump({'close':c,'ident':i},open(S+'close.pkl','wb'))
r,sh=P.load_filings(); pickle.dump({'raw':r,'shards':sh},open(S+'filings.pkl','wb'))
open(S+'tickers.txt','w').write('\n'.join(c.columns))
PY
python -m research.us_selection_value_v1.fetch_as_traded --tickers $S/us/tickers.txt --out $S/us/yahoo     # ~4분, 비공개
python -m research.us_selection_value_v1.features --private $S/us                                         # ~5분, 미래 가격 읽지 않음
python -m research.us_selection_value_v1.evaluate --private $S/us --out research/us_selection_value_v1/results
python -m research.us_selection_value_v1.crosscheck_344 --private $S/us --pr344-ref 4d13a440d96f9e732d03ec1707507435f69275be
python -m research.us_selection_value_v1.report
```

재배포하는 것은 집계 CSV·JSON뿐이다. 종목별 미래 수익과 Yahoo 응답은 `$S`에만 둔다.
