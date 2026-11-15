"""Render results/result.json into results/*.csv and the numeric tables used by REPORT-ko.md (tables only; prose is written by hand).

    python -m research.us_selection_value_v1.report
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RES = HERE / "results"
STRATS = ("PRICE", "SECTOR_MOMENTUM_BASKET", "WITHIN_SECTOR_VALUE", "CASH_PROFITABILITY", "VALUE_CONFIRMED", "PRICE_CONFIRMED", "B2_MULTIFACTOR")
KO = {"PRICE": "가격 신호(B1)", "SECTOR_MOMENTUM_BASKET": "업종 모멘텀 바스켓", "WITHIN_SECTOR_VALUE": "업종 내 가치", "CASH_PROFITABILITY": "현금수익성",
      "VALUE_CONFIRMED": "가치+사업 확인", "PRICE_CONFIRMED": "가격+사업 확인", "B2_MULTIFACTOR": "기존 다요인 B2"}
PERIODS = ("P1", "P2", "P3", "exclude2023Plus", "ALL")


def pct(v, d=2):
    return "—" if v is None else f"{v * 100:+.{d}f}"


def ci(v):
    return "—" if not v else f"[{v[0] * 100:+.1f}, {v[1] * 100:+.1f}]"


def main():
    r = json.loads((RES / "result.json").read_text())
    fh = r["fixedHolding"]
    rows = []
    for k, v in fh.items():
        s, b, H, p = k.split("|")
        rows.append({"strategy": s, "book": b, "H": H, "period": p, **{kk: (json.dumps(vv) if isinstance(vv, list) else vv) for kk, vv in v.items()}})
    keys = sorted({kk for x in rows for kk in x})
    with open(RES / "fixed-holding.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["strategy", "book", "H", "period"] + [k for k in keys if k not in ("strategy", "book", "H", "period")])
        w.writeheader()
        w.writerows(rows)
    nav_rows = []
    for k, v in r["nav"].items():
        s, b, p = k.split("|")
        nav_rows.append({"strategy": s, "book": b, "period": p, **{kk: vv for kk, vv in v.items() if kk != "yearly"}})
    with open(RES / "rebalancing-nav.csv", "w", newline="") as f:
        fields = sorted({kk for x in nav_rows for kk in x})
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(nav_rows)
    with open(RES / "year-sample.csv", "w", newline="") as f:
        fields = ["year"] + sorted({k for v in r["yearSample"].values() for k in v} | {"x_" + k for v in r["exclusionReasonsByYear"].values() for k in v})
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for y in sorted(set(r["yearSample"]) | set(r["exclusionReasonsByYear"])):
            w.writerow({"year": y, **r["yearSample"].get(y, {}), **{"x_" + k: v for k, v in r["exclusionReasonsByYear"].get(y, {}).items()}})
    out = []
    for b in ("TOP5", "TOP_QUINTILE"):
        for H in ("126", "252"):
            out.append(f"\n**{b} · H{H} — SPY 대비 순초과수익 평균(%p), 코호트 수**\n")
            out.append("| 전략 | 2013–19 | 2020–22 | 2023– | 2023 제외 | 전체 | 전체 구간(블록) | 승률 | QQQ 대비 |")
            out.append("|---|---:|---:|---:|---:|---:|---|---:|---:|")
            for s in STRATS:
                c = [fh.get(f"{s}|{b}|{H}|{p}", {}) for p in PERIODS]
                cells = [f"{pct(x.get('meanNetExcessSPY'))} ({x.get('cohorts', 0)})" for x in c]
                a = c[-1]
                out.append(f"| {KO[s]} | " + " | ".join(cells) + f" | {ci(a.get('ciMeanNetExcessSPY'))} | {pct(a.get('winRateSPY'), 0)} | {pct(a.get('meanNetExcessQQQ'))} |")
    out.append("\n**귀속(H126, 전체 기간, 평균 %p): SPY 대비 = 대형주·유니버스 + 업종 배분 + 업종 내 선택 + 비용 (+ 잔여 상호작용)**\n")
    out.append("| 전략 | 책 | 순초과 | 대형주·유니버스 | 업종 배분 | 업종 내 선택 | 비용 | 동업종·동규모 대비 선택 | 그 구간 |")
    out.append("|---|---|---:|---:|---:|---:|---:|---:|---|")
    for b in ("TOP5", "TOP_QUINTILE"):
        for s in STRATS:
            for p in ("ALL", "exclude2023Plus"):
                x = fh.get(f"{s}|{b}|126|{p}", {})
                if not x.get("cohorts"):
                    continue
                out.append(f"| {KO[s]}{' (2023 제외)' if p != 'ALL' else ''} | {b} | {pct(x['meanNetExcessSPY'])} | {pct(x['mean_largeCapAndUniverse'])} | "
                           f"{pct(x['mean_sectorAllocation'])} | {pct(x['mean_withinSectorSelection'])} | {pct(x['mean_costs'])} | "
                           f"{pct(x['mean_peerSelection'])} | {ci(x.get('ciMeanPeerSelection'))} |")
    (RES / "tables-ko.md").write_text("\n".join(out) + "\n")
    print("ok")


if __name__ == "__main__":
    main()
