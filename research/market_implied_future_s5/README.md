# Investment S5 · Market-Implied Future & Risk Pricing Discovery

`AUTHOR_VALIDATION_ONLY`

[원천·기준 코드 감사](AUDIT-ko.md) · [가설·중복 판정과 사전등록 후보](RESEARCH-ko.md) · [PR #389](https://github.com/jaehojung1879-netizen/Investment/pull/389) · [조정 장부 #292](https://github.com/jaehojung1879-netizen/Investment/issues/292)

- [원천 대사·거래일·기간구조·검정력](results/source-snapshot.json)
- [실제 SPXW 샘플·상태가격 LP·합성 반례](results/option-sample.json)
- [KRX 공식 API 접근 결과](results/krx-access.json)

최초 제출 `545b00c6e8560e8d08841e2816f34cda34d7a7eb`의 원천 접속 장애를 해결해 Cboe/CFE/FRED 18개 다운로드를 편입했다. 과거 당시 빈티지를 재구축하지 않았으며, 최신 파일의 역사값으로만 표시한다. 기준일 2026-11-25의 미국 5만기 완결 거래일은 1,987일이다. 실제 SPXW 데모의 호가로부터 단일 만기 풋 스프레드의 $Q$ 기대 지급 범위를 재현했다. 한국 자료, 충분한 독립 표본, 물리 확률 $P$ 검증은 대기 상태다.

## Reproduce source measurements

From the repository root with the project requirements installed. Choose a new local directory outside the repository. Keep the downloaded files and daily curves there. Each report records whether a fresh downloaded file matches the bytes used here via SHA-256. A later publisher update can change hashes and raw row counts even with a fixed cutoff.

```bash
raw_dir=$(mktemp -d)/s5-raw
report_dir=$(mktemp -d)
python -m research.market_implied_future_s5.acquire --out "$raw_dir"
python -m research.market_implied_future_s5.snapshot \
  --raw-dir "$raw_dir" --cutoff 2026-11-25 \
  --report "$report_dir/source-snapshot.json" --private-curves "$raw_dir/curves.json"
python -m research.market_implied_future_s5.state_prices \
  --raw-dir "$raw_dir" --fetch --report "$report_dir/option-sample.json"
python -m research.market_implied_future_s5.krx_probe --report "$report_dir/krx-access.json"
python -m pytest -q tests/test_market_implied_future_s5.py
```

For an exact archived replay, retain the receipted files, acquisition manifest and attempt log, and the option sample receipt in the same local directory. Skip the acquisition and omit `--fetch` from the state-price command. The term-only legacy interface remains available with `python -m research.market_implied_future_s5.foundation --manifest "$raw_dir/manifest.json"`. The forward proxy preserves missing values and its sign. The daily source curves are optional and stay outside the repository.

## Evidence Registry handoff entry

S5 #389 · 시장 내재 기간구조, 상태가격 및 분산 위험가격. 승인된 범위는 공식 원천 검산과 합성 조건 검정이다. 18/18 파일, XNYS 공통 1,987일, 1일·1만기 SPX 실호가 데모의 제한된 지급 범위, KRX SOURCE_BLOCKED. #367 수준 반복 제외. 짧은 예측·체결 및 6~12개월 이후 투자가치 미계량. 독립 리뷰와 공표시각·표본 입증 후 30–93일 위험 연구 검토. [원천 검산](AUDIT-ko.md) · [G0~G6](RESEARCH-ko.md)
