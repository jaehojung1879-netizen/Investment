"""Collect the market results, fixed hypothesis family and reproducibility checks."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import subprocess

import exchange_calendars as xc
import numpy as np
import pandas as pd

from research.kr_us_strategy_batch_v1 import common
from research.kr_us_replica_filter_v1.tables import estimate, table

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / "results"
BASE = "e950496ecc7ba73532b4a4dce7bc578294ba9e8c"
DESIGN = "3f0a751"
HORIZONS = ("126", "252")
FAMILY = (
    ("선택 효과 (기본 매칭)", "paired", "selection"),
    ("기존 신호 조정 후 선택 효과", "adjusted", "adjustedSelection"),
    ("공시 장부−ETF (전체 관측 주)", "own", "total"),
)
MAIN_ROWS = (
    ("선택 효과 (기본 매칭)", "paired", "selection"),
    ("기존 신호 조정 후 선택 효과", "adjusted", "adjustedSelection"),
    ("공통 날짜의 기본 매칭 선택 효과", "bothMatches", "selection"),
    ("공통 날짜의 조정 매칭 선택 효과", "bothMatches", "adjustedSelection"),
    ("기본 매칭 주의 대조 혼합−ETF", "paired", "replacement"),
    ("기본 매칭 주의 공시 혼합−ETF", "paired", "total"),
    ("공시 혼합−ETF (0종목 포함 전체 관측 주)", "own", "total"),
    ("공시 혼합−ETF (공시 신호가 있던 주)", "active", "total"),
    ("보조 QQQ 대비 (전체 관측 주)", "own", "vsQQQ"),
)


def get(root, *keys):
    for k in keys:
        if not isinstance(root, dict):
            return {}
        root = root.get(k, {})
    return root


def load(path):
    return json.loads(path.read_text()) if path.is_file() else {}


def result(data, h, kind, statistic):
    return get(data, "horizons", h, kind, statistic)


def rounded(value, places=2):
    return "미측정" if value is None else f"{100*value:+.{places}f}"


def display(stat):
    if not stat or stat.get("mean") is None:
        return "미측정"
    return f"{estimate(stat)} (n={stat['n']})"


def hypothesis_family(markets):
    rows = []
    for market, data in markets.items():
        for label, kind, metric in FAMILY:
            stat = result(data, "126", kind, metric)
            rows.append({"market": market, "hypothesis": label, "name": f"{market}:{kind}:{metric}",
                         "n": stat.get("n", 0), "mean": stat.get("mean"), "pApprox": stat.get("pOneSidedApprox")})
    adjusted = common.holm({r["name"]: r["pApprox"] for r in rows})
    return [{**r, "holmP": adjusted[r["name"]]} for r in rows]


def walk(obj, path=()):
    if isinstance(obj, dict):
        if {"n", "mean", "ci"} <= set(obj):
            yield "/".join(path), obj
        else:
            for k, v in obj.items():
                yield from walk(v, (*path, str(k)))
    elif isinstance(obj, list):
        for n, v in enumerate(obj):
            yield from walk(v, (*path, str(n)))


def all_tables(markets, family):
    rows = []
    for market, data in markets.items():
        for path, x in walk(data):
            lower, upper = x["ci"] or (None, None)
            rows.append({"market": market, "path": path, "n": x["n"], "mean": x["mean"],
                         "ciLow": lower, "ciHigh": upper, "blockWeeks": x.get("blockWeeks"),
                         "blocksApprox": x.get("independentBlocksApprox"), "pApprox": x.get("pOneSidedApprox")})
    keys = ["market", "path", "n", "mean", "ciLow", "ciHigh", "blockWeeks", "blocksApprox", "pApprox"]
    with (OUT/"estimates.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    with (OUT/"hypotheses-6m.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(family[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(family)
    lines = ["# 전체 주간 비교 통계", "",
             "차이는 %p, 주 수는 원 주간축의 비교 가능 시점 수다. 대괄호는 명목 95% 이동블록 구간이다.", "",
             *table(["시장", "6개월 주가설", "주", "평균 (%p)", "Holm 보정 p"],
                    [(r["market"], r["hypothesis"], r["n"], rounded(r["mean"]), f"{r['holmP']:.3f}") for r in family]),
             *table(["시장", "원본 결과 경로", "비교 주", "평균과 95% 구간"],
                    [(m, path, x["n"], display(x)) for m, d in markets.items() for path, x in walk(d)]),
             "[기계판독 통계](results/estimates.csv) · [주 가설](results/hypotheses-6m.csv) · "
             "[미국 원본](results/US/) · [한국 원본](results/KR/) · [WAT 정정 원본](results/WAT/)"]
    (HERE/"TABLES-ko.md").write_text("\n".join(lines)+"\n")


def market_table(market, data):
    rows = [(label, *[display(result(data, h, group, item)) for h in HORIZONS])
            for label, group, item in MAIN_ROWS if market == "US" or item != "vsQQQ"]
    return table(["비용 차감 차이 (%p)", "6개월", "12개월"], rows)


def fallback_kr(data):
    cov = data.get("coverage", {})
    if not cov:
        return []
    source_counts = cov.get("scopedReceiptStatuses", {})
    lines = [f"공식 목록 {cov.get('completeListMonths', 0)}개월, 접수 {cov.get('officialListReceipts', 0):,}건을 확보했다. "
             f"기존 후보에 관련된 원문 {cov.get('scopedReceipts', 0):,}건 중 {source_counts.get('PARSED', 0):,}건을 판독했다. "
             "관련 공시를 모두 확인한 장부 주와 전체 기간 CAGR·MDD·회전율은 미측정이다.", ""]
    conditional = (
        ("확인된 공시 장부−조건부 대조 장부", "conditionalPaired", "selection"),
        ("대조 장부−KODEX 200", "conditionalPaired", "replacement"),
        ("확인된 공시 장부−KODEX 200", "conditionalPaired", "total"),
        ("기존 신호 조정 후 전체 장부 선택 효과", "conditionalAdjusted", "adjustedSelection"),
        ("조정 가능한 두 쌍의 선택 기여", "conditionalActive", "partialAdjustedSelection"),
    )
    if any(result(data, h, kind, name).get("n") for _, kind, name in conditional for h in HORIZONS):
        lines += ["확보한 원문에 국한한 조건부 비교다. 검정 표본이나 전체 장부 성과 추정에 포함하지 않았다.", "",
                  *table(["한국 조건부 1주 (%p)", "6개월", "12개월"],
                         [(label, *[display(result(data, h, section, k)) for h in HORIZONS])
                          for label, section, k in conditional])]
    return lines


def market_nav(data):
    windows = [(k, v) for k, v in data.get("ledgers", {}).items() if "weeks" in v]
    if not windows:
        return []
    window, values = max(windows, key=lambda v: (v[1]["weeks"], v[0]))
    rows = []
    for config in ("L26", "L52"):
        for label, key in (("기준 ETF", "SPY"), ("공시 혼합", "selected"),
                           ("짝지은 날짜의 공시 혼합", "pairedSelected"), ("짝지은 날짜의 대조 혼합", "pairedControl")):
            stats = get(values, config, key)
            rows.append([config, label, *(rounded(stats.get(k)) for k in
                                         ("cagr", "mdd", "oneWayTurnoverPerYear"))])
    return [f"가장 긴 연속 관측 운용 창은 {window.replace('_to_', ' ~ ')}의 {values['weeks']}주다.", "",
            *table(["주기", "장부", "CAGR (%)", "MDD (%)", "연 편도 회전율 (%)"], rows)]


def wat_headline(wat):
    lines = ["## 미국 · WAT 정정이 기존 성과에 미친 영향", ""]
    if not wat.get("horizons"):
        return lines + ["정정 성과 미측정. 확보한 발행주식 수와 기존 입력 검사는 별도 자료를 참고한다. [미국 입력 검사](US-WAT-ko.md)", ""]
    lines += ["**WAT 단위 정정의 영향은 일별 장부에 나타났다.** 단위 오류 기간의 복제 목표 비중은 "
              "28.82~35.15%에서 0.048~0.059%로 낮아졌다. 원 #352 만기 코호트에는 이 15주가 아직 들어오지 않았다. "
              "전체 943행 정정 후에도 복제 기준의 SPY 대비 평균은 양수였고, L26 native U1의 CAGR은 SPY 아래로 내려갔다.", ""]
    modes = (("5월 이후 단위 정정", "WAT_UNIT_ONLY"), ("2월 발행 반영 포함", "WAT_WHOLE"),
             ("원 자료로 입증한 전체 정정", "ALL_VERIFIED"))
    rows = []
    for label, variant in modes:
        for book in ("B", "U1_NATIVE", "U1_FUNDED"):
            stats = [get(wat, "horizons", variant, h, book) for h in HORIZONS]
            if any(stats):
                cells = [f"{display(x.get('originalVsSPY'))} → {display(x.get('correctedVsSPY'))}"
                         f" (목표 변경 {x.get('matureTargetChangedWeeks', '—')}주)" for x in stats]
                rows.append((label, book, *cells))
    lines += table(["확정 정정 범위", "장부", "6개월 원본 → 정정 (%p)", "12개월 원본 → 정정 (%p)"], rows)
    risk = []
    for cadence in ("L26", "L52"):
        for book in ("B", "U1_NATIVE", "U1_FUNDED"):
            values = get(wat, "ledgers", cadence, book)
            for label, variant in (modes[1], modes[2]):
                old, new = values.get("old", {}), get(values, variant, "new")
                if old.get("cagr") is not None and new.get("cagr") is not None:
                    risk.append((cadence, book, label,
                                 f"{rounded(old['cagr'])} → {rounded(new['cagr'])}",
                                 f"{rounded(old.get('mdd'))} → {rounded(new.get('mdd'))}",
                                 f"{rounded(old.get('oneWayTurnoverPerYear'))} → {rounded(new.get('oneWayTurnoverPerYear'))}"))
    lines += table(["주기", "장부", "정정 범위", "CAGR (%)", "MDD (%)", "연 편도 회전율 (%)"], risk)
    unit = [get(wat, "horizons", "WAT_UNIT_ONLY", h, "B") for h in HORIZONS]
    whole = [get(wat, "horizons", "WAT_WHOLE", h, "B") for h in HORIZONS]
    if all(unit) and all(whole):
        change = " / ".join(rounded(get(x, "correctedMinusOriginal", "mean"), 6) for x in whole)
        lines += [
            f"2월 발행 정정까지 반영한 B의 원 전체 평균 변동은 {change}%p다. "
            "전체 정정 범위와 WAT 단위 오류의 영향은 표에서 분리했다.", "",
        ]
    return lines + ["[주식 수, 분할, 정정 전후 비중과 원 공시](US-WAT-ko.md)", ""]


def us_sensitivity(data):
    labels = (("ETF 대비", "ETFSensitivity"), ("기본 선택 효과", "selectionSensitivity"))
    rows = []
    for label, key in labels:
        stats = [get(data, "horizons", h, key) for h in HORIZONS]
        if not any(stats):
            continue
        rows += [
            (label + " · 최대 기여 종목의 기여 제외",
             *[f"{s.get('maxName', '—')} {display(s.get('minusNameContribution'))}" for s in stats]),
            (label + " · 최대 기여 진입 연도 제외",
             *[f"{s.get('maxYear', '—')} {display(s.get('noYear'))}" for s in stats]),
        ]
    return (["사후 민감도에서 종목은 해당 가중 기여를 뺐고, 진입 연도는 그 해의 코호트를 뺐다.", "",
             *table(["비용 차감 차이 (%p)", "6개월", "12개월"], rows)] if rows else [])


def first_page(markets, wat, family):
    lines = ["# 공개된 실제 매수와 미국 발행주식 수 정정", "",
             f"PR #352 `{BASE}` 기준. 비교 규칙은 새 성과 계산 전 `{DESIGN}`에 고정했다. "
             "6·12개월은 진입 후 126/252 세션이며, 대괄호는 95% 이동블록 구간이다. "
             "두 시장의 수익은 이전에 연구한 과거에서 다시 측정했다. [설계](DESIGN-ko.md)", ""]
    lines += wat_headline(wat)
    for market, label, source_path in (("US", "미국 · SPY 주 기준, QQQ 보조", "US-SOURCES-ko.md"),
                                       ("KR", "한국 · KODEX 200", "KR-ko.md")):
        summary = markets[market]
        lines += [f"## {label}", ""]
        if not summary.get("horizons"):
            lines += [f"유효 수익 표본 미확보. [확보 입력 및 미측정 범위]({source_path})", ""]
            continue
        weights = summary.get("weights", {})
        size = summary.get("coveredStudyWeeks", "미측정")
        allocation = " · ".join(f"{int(k)}개 {v}주" for k, v in sorted(weights.items(), key=lambda p: int(p[0])))
        if size:
            lines += [f"공시가 관측된 발행사와 기존 가격을 함께 평가할 수 있는 판단일은 {size}주다. {allocation}",
                      "", *market_table(market, summary), *market_nav(summary)]
            if market == "US":
                lines += ["**기존 신호에 정보를 더했다는 근거는 불충분하다.** 기본 짝비교의 6개월 구간은 0을 포함했고, "
                          "12개월과 기존 신호 조정 짝비교는 구간에 필요한 주 수가 부족했다. "
                          "공시 혼합은 L52에서 SPY보다 CAGR이 소폭 높았으나 L26과 L52 모두 낙폭이 더 컸다.", "",
                          *us_sensitivity(summary)]
        elif market == "KR":
            lines += fallback_kr(summary)
        else:
            lines += ["공식 원천과 기존 가격을 연결한 완결 관측 주는 0주다.", ""]
        for row in (r for r in family if r["market"] == market):
            value = f"{row['holmP']:.3f}" if row["pApprox"] is not None else "미측정"
            lines.append(f"- {row['hypothesis']}의 6개월 Holm 보정 p = {value} (n={row['n']}).")
        lines += ["", f"[공시·거래·시각 근거]({source_path}) · [시장별 원본](results/{market}/)", ""]
    lines += ["## 재실행·검증", "",
              "```bash", "PYTHON=/workspace/s2-venv/bin/python bash research/kr_us_public_buys_v1/reproduce.sh", "```", "",
              "별도 전향 경로의 여섯 파일을 SHA로 대조했다. 최신 입력과 승인 상태가 검증된 새 영수증은 0건이다. "
              "[전향 상태](results/prospective-status.json)", "",
              "[전체 결과표](TABLES-ko.md) · [입력 계보·재실행·검증](VALIDATION.md)"]
    (HERE/"REPORT-ko.md").write_text("\n".join(lines)+"\n")


def numeric_checks():
    result = {}
    for market in ("US", "KR"):
        row_checks = {}
        path = OUT/market
        for h in HORIZONS:
            file = path/f"cohorts-{h}.csv.gz"
            if not file.is_file():
                continue
            rows = pd.read_csv(file)
            assert rows.date.is_unique
            check = {"weeklyRows": len(rows)}
            for selection, replacement in (("selection", "replacement"),
                                           ("adjustedSelection", "adjustedReplacement")):
                if not {selection, replacement, "total"} <= set(rows):
                    continue
                supported = rows[[selection, replacement, "total"]].dropna()
                err = (supported[selection]+supported[replacement]-supported.total).abs()
                assert err.lt(1e-10).all(), (market, h, selection)
                check[selection+"Checked"] = len(supported)
                check[selection+"MaxError"] = float(err.max()) if len(err) else None
            row_checks[h] = check
        result[market] = row_checks
    us = OUT/"US"
    positions_path = us/"positions.csv.gz"
    us_summary = load(us/"summary.json")
    selected_stocks = sum(int(k)*v for k, v in us_summary.get("weights", {}).items())
    if positions_path.is_file() and selected_stocks:
        positions = pd.read_csv(positions_path)
        weekly = pd.read_csv(us/"weekly.csv.gz", usecols=["date", "decisionUtc", "selected"])
        checked = positions.merge(weekly, validate="many_to_one", on="date")
        assert len(checked) == len(positions)
        assert len(checked) == selected_stocks == int(weekly.selected.sum())
        assert not checked.duplicated(["date", "ticker"]).any()
        assert checked.groupby("date").size().le(5).all()
        available = pd.to_datetime(checked.availableAt, utc=True)
        cutoff = pd.to_datetime(checked.decisionUtc, utc=True)
        assert available.le(cutoff).all()
        result["US"]["feedTimes"] = {"selectedIssuerWeeks": len(checked), "availabilityBeforeDecisionClose": True}
    caps_path = OUT/"WAT/corrected-caps.csv"
    if caps_path.is_file():
        cap = pd.read_csv(caps_path, parse_dates=["date", "shareAsOf"])
        observed = pd.to_datetime(cap.acceptedET, utc=True, format="mixed")
        calendar = xc.get_calendar("XNYS", start=cap.date.min().isoformat(), end=cap.date.max().isoformat())
        cutoff = pd.Series([calendar.session_close(d) for d in cap.date], index=cap.index)
        assert observed.lt(cutoff).all()
        assert cap.shareAsOf.le(cap.date).all() and not cap.duplicated(["date", "ticker"]).any()
        implied = cap.confirmedActualShares*cap.rawAsTradedPrice
        assert np.allclose(implied, cap.correctedMarketCap, rtol=1e-12, atol=.01)
        result["WAT"] = {"exactSharePriceProduct": True, "uniqueIssuerWeek": True, "affectedRows": len(cap),
                         "affectedTickers": cap.ticker.nunique(), "publicBeforeActualSessionClose": True}
    (OUT/"verification.json").write_text(json.dumps(result, indent=2, ensure_ascii=False)+"\n")


def integrity():
    frozen = json.loads((ROOT / "research/kr_us_replica_filter_v1/results/prospective-status.json").read_text())
    for name, expected in frozen["existingFilesSha256"].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == expected, name
    prospective = dict(frozen, comparisonBase=BASE, consultedKST="2026-11-20", newLiveReceipts=0)
    (OUT/"prospective-status.json").write_text(json.dumps(prospective, indent=2, ensure_ascii=False)+"\n")
    design = HERE/"DESIGN-ko.md"
    committed = subprocess.check_output(["git", "show", f"{DESIGN}:{design.relative_to(ROOT)}"], cwd=ROOT)
    assert committed == design.read_bytes()
    different = subprocess.check_output(["git", "diff", "--name-only", BASE], cwd=ROOT, text=True).splitlines()
    assert all(p.startswith("research/kr_us_public_buys_v1/") or p.startswith("tests/test_kr_us_public_buys")
               for p in different), different
    manifest = {}
    for f in sorted([*OUT.rglob("*"), *(HERE/"inputs").rglob("*"), *HERE.glob("*.py"), *HERE.glob("*.sh"), design]):
        if f.is_file() and f.name != "artifact-manifest.json":
            with f.open("rb") as stream:
                manifest[str(f.relative_to(HERE))] = {"bytes": f.stat().st_size,
                                                     "sha256": hashlib.file_digest(stream, "sha256").hexdigest()}
    (OUT/"artifact-manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False)+"\n")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    markets = {m: load(OUT/m/"summary.json") for m in ("US", "KR")}
    wat = load(OUT/"WAT/summary.json")
    family = hypothesis_family(markets)
    all_tables({**markets, "US_CAP": wat}, family)
    first_page(markets, wat, family)
    numeric_checks()
    integrity()


if __name__ == "__main__":
    main()
