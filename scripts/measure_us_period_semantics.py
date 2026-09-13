"""Decide, from the collected filings, what a US 10-Q's income statement means.

WHY THIS RUNS BEFORE ANY DERIVATION. A US 10-Q is filed with two contexts for
every flow account: the three months just ended, and the year to date. The
vendor flattens one of them into `report.ic`, and which one it picked decides
how a trailing-twelve-month figure has to be built. Read a year-to-date cash
flow as if it were a quarter and free cash flow comes out roughly fourfold too
large in Q4, with nothing anywhere raising an error — the numbers stay
plausible and every downstream factor is quietly wrong.

WHY VALUE RATIOS AND NOT FIELD NAMES. The first collection slice established
that the FILING periods are cumulative: 4,971 filings split into 1,801 at a
quarter, 1,615 at a half and 1,553 at three quarters, which is the signature of
a period measured from the fiscal year start. But `report.ic` entries carry no
dates of their own, so that is evidence about the envelope, not about the
numbers inside it. DART posed exactly this question about Korean filings and
settled it with value ratios over 84 companies; the same method settles it
here, and the data to run it is already bought.

WHAT DECIDES. Within one ticker-year: half-year over first-quarter, and
three-quarter over first-quarter. Cumulative predicts about 2 and 3; three
independent quarters predict about 1 and 1. The statistic is the MEDIAN across
companies, never one company's ratio — no firm earns evenly through the year,
and a seasonal one would appear to contradict whichever reading it happened to
sit opposite.

Usage:
    python scripts/measure_us_period_semantics.py <store-dir> [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import finnhub_fundamentals as FF  # noqa: E402
from pipeline import historical_store as HS  # noqa: E402


def load_records(store: Path) -> list[dict]:
    rows: list[dict] = []
    for path in sorted(store.glob("finnhub-*.jsonl.gz")):
        rows.extend(HS.read_jsonl(path))
    return rows


def report(records: list[dict]) -> dict:
    """Every flow account measured, not just the one that answers first.

    A single account could be cumulative by coincidence of how one vendor maps
    a tag. Four accounts agreeing is the claim; four disagreeing is a finding
    that has to be looked at rather than averaged away.
    """
    per_concept = {key: FF.period_semantics(records, key) for key in FF.FLOW_CONCEPTS}
    verdicts = {key: result["verdict"] for key, result in per_concept.items()}
    decided = {v for v in verdicts.values() if v != FF.INCONCLUSIVE}
    settled = sum(1 for v in verdicts.values() if v != FF.INCONCLUSIVE)
    if len(decided) == 1:
        overall = decided.pop()
        # Says how many accounts decided, not "all of them": accounts with too
        # few ratios reported nothing, and counting silence as agreement would
        # make one account's answer read like four.
        agreement = f"판정을 낸 {settled}개 계정이 모두 같은 답을 냈습니다"
    elif not decided:
        overall = FF.INCONCLUSIVE
        agreement = "결론을 낸 계정이 없습니다"
    else:
        overall = FF.INCONCLUSIVE
        agreement = ("계정마다 답이 다릅니다 — 평균내지 말고 어떤 계정이 어떻게 "
                     "다른지 보십시오")
    return {"filings": len(records), "byConcept": per_concept,
            "verdict": overall, "agreement": agreement}


def _fmt(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def render(result: dict) -> str:
    lines = [f"공시 {result['filings']:,}건에서 기간 의미를 측정합니다", ""]
    lines.append(f"{'계정':<20} {'반기/1Q':>8} {'3Q/1Q':>8} {'3Q/연간':>8} "
                 f"{'표본':>6}  판정")
    for key, one in result["byConcept"].items():
        med, counts = one["medians"], one["counts"]
        sample = min(counts["halfOverFirst"], counts["threeQuartersOverFirst"])
        lines.append(f"{key:<20} {_fmt(med['halfOverFirst']):>8} "
                     f"{_fmt(med['threeQuartersOverFirst']):>8} "
                     f"{_fmt(med['threeQuartersOverYear']):>8} "
                     f"{sample:>6}  {one['verdict']}")
    lines += ["", f"종합 판정: {result['verdict']} — {result['agreement']}"]
    for key, one in result["byConcept"].items():
        if one["verdict"] != FF.INCONCLUSIVE or one["counts"]["tickerYears"]:
            lines.append(f"  {key}: {one['meaning']}")
    lines += ["",
              "기준: 누계라면 반기/1Q≈2.0, 3Q/1Q≈3.0 · 독립 분기라면 둘 다 ≈1.0",
              f"표본 하한 {FF.MIN_RATIOS}개 미만이면 판정하지 않습니다"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("store")
    parser.add_argument("--json", dest="json_out")
    args = parser.parse_args(argv)

    store = Path(args.store)
    if not store.exists():
        print(f"저장소가 없습니다: {store}")
        return 1
    records = load_records(store)
    if not records:
        print(f"{store} 에 공시가 없습니다 — 먼저 수집을 돌리십시오")
        return 1

    result = report(records)
    print(render(result))
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
    # A verdict that did not decide is not a failure of the run: it is the
    # honest output of too little data, and the exit code says so rather than
    # letting a green check imply an answer.
    return 0 if result["verdict"] != FF.INCONCLUSIVE else 2


if __name__ == "__main__":
    raise SystemExit(main())
