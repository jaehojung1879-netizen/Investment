"""Render complete paired-estimate tables from the saved market results."""
from __future__ import annotations

import csv
import json

from research.kr_us_replica_filter_v1.verify import HERE, OUT

MARKETS = ("US", "KR")


def read(path):
    return json.loads(path.read_text()) if path.is_file() else {}


def pct(x):
    return "—" if x is None else f"{100*x:+.2f}"


def estimate(s):
    s = s or {}
    if s.get("mean") is None:
        return "미측정"
    ci = s.get("ci")
    bounds = f"[{pct(ci[0])}, {pct(ci[1])}]" if ci else "[구간 미측정]"
    return f"{pct(s['mean'])} {bounds}"


def table(headers, rows):
    return ["|" + "|".join(headers) + "|", "|" + "|".join(["---"]*len(headers)) + "|",
            *("|" + "|".join(str(x).replace("|"," / ").replace("\n"," ") for x in row) + "|" for row in rows), ""]


def estimates(obj, path=()):
    if isinstance(obj, dict):
        if {"n","mean","ci"} <= set(obj):
            yield path, obj
        else:
            for key, value in obj.items():
                yield from estimates(value, path+(str(key),))
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            key = f"seed={value['seed']}" if isinstance(value, dict) and "seed" in value else str(i)
            yield from estimates(value, path+(key,))


def write_estimate_tables(summaries):
    rows = []
    for market, data in summaries.items():
        for path, value in estimates(data):
            ci = value["ci"] or (None,None)
            rows.append({"market":market,"resultPath":"/".join(path),
                         "n":value["n"],"mean":value["mean"],"ciLow":ci[0],"ciHigh":ci[1],
                         "blocksApprox":value.get("independentBlocksApprox"),"blockWeeks":value.get("blockWeeks"),
                         "pOneSidedApprox":value.get("pOneSidedApprox")})
    with (OUT/"estimates.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, lineterminator="\n",
                           fieldnames=["market", "resultPath", "n", "mean", "ciLow", "ciHigh",
                                       "blocksApprox", "blockWeeks", "pOneSidedApprox"])
        w.writeheader()
        w.writerows(rows)
    return rows


def main():
    summaries = {market:read(OUT/market/"summary.json") for market in MARKETS}
    if not any(summaries.values()):
        raise ValueError("No market summary is available")
    lines = [
        "# 전체 이동블록 결과표", "",
        "수익률과 수익 차이는 % 또는 %p다. 대괄호는 명목 95% 구간이며, 원 주간축의 유효 날짜를 평가했다. "
        "각 행의 식별자는 시장별 원본 JSON 경로다. 다중비교 처리는 한국의 6개월 주 가설 세 개에 적용한다.", "",
        "[첫 장 핵심 비교](REPORT-ko.md) · [미국 귀속 세부](US-ko.md) · [한국 필터 세부](KR-ko.md)", "",
    ]
    rows = write_estimate_tables(summaries)
    for market, data in summaries.items():
        lines += [f"## {market}",""]
        if not data:
            lines += ["이 시장의 결과가 미확보 상태다.",""]
            continue
        lines += table(["원본 결과 경로","유효 주","주÷블록 길이","평균 [95% 구간]"],
                       [[r["resultPath"],r["n"],r["blocksApprox"] if r["blocksApprox"] is not None else "—",
                         estimate({"mean":r["mean"],"ci":None if r["ciLow"] is None else [r["ciLow"],r["ciHigh"]]})]
                        for r in rows if r["market"] == market])
    lines += [
        "[기계판독 전체 통계](results/estimates.csv) · "
        "[미국 전체 요약](results/US/summary.json) · [한국 전체 요약](results/KR/summary.json) · "
        "[미국 날짜별 원본](results/US/) · [한국 날짜별 원본](results/KR/)",
    ]
    (HERE/"TABLES-ko.md").write_text("\n".join(lines)+"\n")


if __name__ == "__main__":
    main()
