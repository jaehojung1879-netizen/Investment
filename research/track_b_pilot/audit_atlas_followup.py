"""Follow-up robustness audit of the Full Drawdown Atlas (#368 at 4e084bcf). Descriptive; nothing is fitted.

Question: does "within a 10-20% drawdown, low credit spread / a stabilised decline did better afterwards" survive
removing the 2000 and 2007 bear markets?

What this adds to `audit_atlas.py` (#369), which it imports and does not change:
  * episode-level exclusion: every day of the Atlas's own full-recovery episode (2000-03 peak .. 2006-10 recovery,
    2007-10 peak .. 2012-08 recovery) is removed, not a calendar window;
  * a strict variant that ALSO removes entries whose forward window reaches into the excluded episode;
  * 63 / 126 / 252-session mean and median, loss probability, further minimum (median and p10), for both sides;
  * the depth-only baseline (every day in the same bucket, same view) next to each side;
  * pre-2000 vs 2000-onward vs 2013-onward;
  * redundancy between the three flags;
  * a three-way descriptive classification computed by a rule, not by eye.

Classification rule (written after the #369 numbers had been read; it is generic, names no cell, and is not a test):
  retained(view)   = on the 252-session horizon, adverse minus benign has mean return < 0 AND loss probability > 0,
                     under BOTH day weighting and spell weighting, with >= MIN_SPELLS spells on each side
  FULL_NOT_READABLE / DIRECTION_ABSENT_IN_FULL  -> no classification (stated as such)
  DEPENDS_ON_SPECIFIC_EPISODES  -> retained in `full`, and a readable exclusion view does NOT retain it
  SIMILAR_ACROSS_INDEPENDENT_EPISODES -> retained in `full`, in both single-episode exclusions AND with both episodes removed
                     (all three readable). REVISION 1: the first run only required the two single exclusions to be readable,
                     which labelled 15-20% credit and speed "similar" although removing both left 2 adverse spells (unreadable).
                     The revision can only move SIMILAR to INSUFFICIENT_SAMPLE; no other class and no number changed.
  INSUFFICIENT_SAMPLE -> anything else (a single-episode exclusion leaves < MIN_SPELLS on a side)
The classification is a description of this one exposed sample. It is not a statistical result.

    python -m research.track_b_pilot.audit_atlas_followup
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from research.track_b_pilot import atlas as A
from research.track_b_pilot import audit_atlas as AU

HERE = Path(__file__).resolve().parent
HZ = (63, 126, 252)
MIN_SPELLS = AU.MIN_SPELLS
AXES = ("credit", "stabilisation", "speed")
BUCKETS = {"10-15%": (0.10, 0.15), "15-20%": (0.15, 0.20), "10-20% (union)": (0.10, 0.20)}
VIEWS = ("full", "excl_2000_episode", "excl_2007_episode", "excl_both_episodes",
         "excl_2000_episode_strict", "excl_2007_episode_strict", "excl_both_episodes_strict",
         "before_2000", "from_2000", "since_2013")
DECISION_VIEWS = ("excl_2000_episode", "excl_2007_episode", "excl_both_episodes")


def episode_bounds(s: dict, sid: int) -> tuple[int, int]:
    ix = np.where(s["spell"] == sid)[0]
    return int(ix[0]), int(ix[-1])


def strict_arrays(fw: dict, shift: int, bounds: list[tuple[int, int]]) -> dict:
    """Copy of forward arrays with NaN for entries whose window [i+shift, i+shift+h] reaches an excluded episode."""
    out = {}
    for h, (f, m) in fw.items():
        f2, m2 = f.copy(), m.copy()
        for a, _b in bounds:
            lo = max(0, a - h - shift)
            f2[lo:a] = np.nan
            m2[lo:a] = np.nan
        out[h] = (f2, m2)
    return out


def metrics(s: dict, idx: np.ndarray, fw: dict, weighting: str) -> dict:
    out = {"nDays": int(len(idx)), "nSpells": int(len(set(s["spell"][idx].tolist())))}
    sp_all = s["spell"][idx]
    for h in HZ:
        f, m = fw[h]
        ok = ~np.isnan(f[idx])
        ii, sp = idx[ok], sp_all[ok]
        if not len(ii):
            out[str(h)] = None
            continue
        fv, mv = f[ii], m[ii]
        row = {"nDays": int(len(ii)), "nSpells": int(len(set(sp.tolist())))}
        if weighting == "days":
            row.update(mean=float(fv.mean()), median=float(np.median(fv)), loss=float((fv < 0).mean()),
                       furtherMinMedian=float(np.median(mv)), furtherMinP10=float(np.quantile(mv, 0.10)))
        else:
            ids = sorted(set(sp.tolist()))
            sm = np.array([fv[sp == k].mean() for k in ids])
            row.update(mean=float(sm.mean()), median=float(np.median(sm)),
                       loss=float(np.mean([(fv[sp == k] < 0).mean() for k in ids])),
                       furtherMinMedian=float(np.median([np.median(mv[sp == k]) for k in ids])), furtherMinP10=None)
        out[str(h)] = row
    return out


def gap(adv: dict, ben: dict, h: str) -> dict | None:
    a, b = adv.get(h), ben.get(h)
    if not a or not b:
        return None
    return {"mean": a["mean"] - b["mean"], "median": a["median"] - b["median"], "loss": a["loss"] - b["loss"],
            "furtherMinMedian": a["furtherMinMedian"] - b["furtherMinMedian"],
            "spellsAdverseBenign": [a["nSpells"], b["nSpells"]]}


def retained(g: dict | None) -> bool | None:
    """None = not readable; else whether the Atlas direction holds (worse adverse side) on mean AND loss."""
    if not g or min(g["spellsAdverseBenign"]) < MIN_SPELLS:
        return None
    return bool(g["mean"] < 0 and g["loss"] > 0)


def classify(views: dict) -> dict:
    flags = {}
    for v, cell in views.items():
        r = [retained(cell[f"close_t/{w}"]["gap"]["252"]) for w in ("days", "spells")]
        flags[v] = None if None in r else bool(all(r))
    if flags["full"] is None:
        return {"classification": "FULL_NOT_READABLE", "retainedByView": flags}
    if flags["full"] is False:
        return {"classification": "DIRECTION_ABSENT_IN_FULL", "retainedByView": flags}
    readable = {v: flags[v] for v in DECISION_VIEWS if flags[v] is not None}
    if any(x is False for x in readable.values()):
        cls = "DEPENDS_ON_SPECIFIC_EPISODES"
    elif all(flags[v] is True for v in DECISION_VIEWS):
        cls = "SIMILAR_ACROSS_INDEPENDENT_EPISODES"
    else:
        cls = "INSUFFICIENT_SAMPLE"
    return {"classification": cls, "retainedByView": flags}


def phi(x: np.ndarray, y: np.ndarray) -> float | None:
    n11, n10, n01, n00 = (int((x & y).sum()), int((x & ~y).sum()), int((~x & y).sum()), int((~x & ~y).sum()))
    d = (n11 + n10) * (n01 + n00) * (n11 + n01) * (n10 + n00)
    return None if d == 0 else float((n11 * n00 - n10 * n01) / d ** 0.5)


def build() -> dict:
    AU.build()
    s = A.state()
    tr = s["tr"]
    bears = AU.bear_spells(s)
    b2000, b2007 = episode_bounds(s, bears[0]), episode_bounds(s, bears[1])
    dates = np.array(s["dates"])
    sides = AU.side_masks(s)
    fw0, fw1 = AU.forward_arrays(tr, 0), AU.forward_arrays(tr, 1)
    fw = {0: {"plain": fw0, "e2000": strict_arrays(fw0, 0, [b2000]), "e2007": strict_arrays(fw0, 0, [b2007]),
              "both": strict_arrays(fw0, 0, [b2000, b2007])},
          1: {"plain": fw1, "e2000": strict_arrays(fw1, 1, [b2000]), "e2007": strict_arrays(fw1, 1, [b2007]),
              "both": strict_arrays(fw1, 1, [b2000, b2007])}}
    not_2000 = s["spell"] != bears[0]
    not_2007 = s["spell"] != bears[1]
    vmask = {"full": (np.ones(len(tr), bool), "plain"), "excl_2000_episode": (not_2000, "plain"),
             "excl_2007_episode": (not_2007, "plain"), "excl_both_episodes": (not_2000 & not_2007, "plain"),
             "excl_2000_episode_strict": (not_2000, "e2000"), "excl_2007_episode_strict": (not_2007, "e2007"),
             "excl_both_episodes_strict": (not_2000 & not_2007, "both"),
             "before_2000": (dates < "2000-01-01", "plain"), "from_2000": (dates >= "2000-01-01", "plain"),
             "since_2013": (dates >= AU.SINCE, "plain")}
    res = {"study": "full-drawdown-atlas-followup-robustness-audit", "baseRef": "PR #368 4e084bcf",
           "evidenceClass": "DESCRIPTIVE_ON_EXPOSED_HISTORY", "noPValues": True, "noStrategy": True, "noNewVariables": True,
           "classificationIsStatistical": False, "ruleRevision1": "SIMILAR now requires the both-episodes-removed view to be readable and retained; first run had labelled 15-20% credit and speed SIMILAR with 2 adverse spells left", "minSpells": MIN_SPELLS, "horizons": list(HZ),
           "episodes": {"2000": {"id": bears[0], "firstIdx": b2000[0], "start": s["dates"][b2000[0]], "end": s["dates"][b2000[1]]},
                        "2007": {"id": bears[1], "firstIdx": b2007[0], "start": s["dates"][b2007[0]], "end": s["dates"][b2007[1]]}},
           "cells": {}, "redundancy": {}, "verdicts": {}}
    for bname, (lo, hi) in BUCKETS.items():
        depth = -s["dd"]
        bm = (depth >= lo) & (depth < hi)
        res["cells"][bname] = {}
        res["verdicts"][bname] = {}
        for axis in AXES:
            adv_name, ben_name = AU.SIDES[axis]
            views = {}
            for v in VIEWS:
                vm, key = vmask[v]
                cell = {}
                for shift, sname in ((0, "close_t"), (1, "close_t1")):
                    arrs = fw[shift][key]
                    for w in ("days", "spells"):
                        ia = np.where(bm & sides[axis][adv_name] & vm)[0]
                        ib = np.where(bm & sides[axis][ben_name] & vm)[0]
                        ibase = np.where(bm & vm)[0]
                        a, b, c = metrics(s, ia, arrs, w), metrics(s, ib, arrs, w), metrics(s, ibase, arrs, w)
                        cell[f"{sname}/{w}"] = {"adverse": a, "benign": b, "depthOnlyBaseline": c,
                                                "gap": {str(h): gap(a, b, str(h)) for h in HZ}}
                views[v] = cell
            res["cells"][bname][axis] = {"adverseSide": adv_name, "benignSide": ben_name, "views": views}
            res["verdicts"][bname][axis] = classify(views)
            # same rule applied to next-session-close entry (state still read at t); a mismatch would mean execution lag matters
            nxt = classify({k: {f"close_t/{w}": cell[f"close_t1/{w}"] for w in ("days", "spells")} for k, cell in views.items()})
            res["verdicts"][bname][axis]["nextCloseClassification"] = nxt["classification"]
            res["verdicts"][bname][axis]["nextCloseSameClassification"] = bool(nxt["classification"] == res["verdicts"][bname][axis]["classification"])
    # redundancy between flags inside the union bucket (days where both flags are defined)
    ub = (-s["dd"] >= 0.10) & (-s["dd"] < 0.20)
    flag = {"creditHigh": sides["credit"]["aboveExpandingMedian"], "newLowWithin21": sides["stabilisation"]["newLowWithin21"],
            "slow": sides["speed"]["slow"]}
    defined = {"creditHigh": sides["credit"]["aboveExpandingMedian"] | sides["credit"]["atOrBelow"],
               "newLowWithin21": np.ones(len(tr), bool), "slow": np.ones(len(tr), bool)}
    for v in ("full", "excl_both_episodes"):
        vm = vmask[v][0]
        pairs = {}
        for x, y in (("creditHigh", "newLowWithin21"), ("creditHigh", "slow"), ("newLowWithin21", "slow")):
            m = ub & vm & defined[x] & defined[y]
            pairs[f"{x}~{y}"] = {"days": int(m.sum()), "phi": phi(flag[x][m], flag[y][m])}
        res["redundancy"][v] = pairs
    return res


def _p(x, d=1):
    return "n/a" if x is None else f"{x * 100:+.{d}f}"


def _side(m, h):
    x = m.get(h)
    if not x:
        return "비어 있음"
    return (f"{_p(x['mean'])} / {_p(x['median'])} / {x['loss'] * 100:.0f}% / {_p(x['furtherMinMedian'])}"
            f"{'' if x['furtherMinP10'] is None else ' / ' + _p(x['furtherMinP10'])} ({x['nSpells']})")


def render(res: dict) -> str:
    cn = {"SIMILAR_ACROSS_INDEPENDENT_EPISODES": "여러 독립 사건에서 유사한 방향", "DEPENDS_ON_SPECIFIC_EPISODES": "특정 사건에 과도하게 의존",
          "INSUFFICIENT_SAMPLE": "표본 부족으로 판단 불가", "FULL_NOT_READABLE": "전체 표본에서도 읽을 수 없음(분류 안 함)",
          "DIRECTION_ABSENT_IN_FULL": "원래 방향이 전체 표본에서 없음(분류 안 함)"}
    L = ["# Atlas 후속 견고성 감사 — 자동 생성 표 (`audit_atlas_followup.py`)", "",
         "수정 금지. 해석은 `ATLAS-FOLLOWUP-ko.md`. 모든 칸: 평균 / 중앙값 / 손실 확률 / 추가 최저 중앙값 [/ 추가 최저 p10(전체일만)] (사건 수). 단위 %.", "",
         "## 1. 분류 (규칙은 모듈 docstring; 서술적 판단이며 통계적 입증이 아니다)", "",
         "| 구간 | 축 | 분류 | full | 2000 사건 제외 | 2007 사건 제외 | 둘 다 제외 |", "|---|---|---|---|---|---|---|"]
    sym = {True: "유지", False: "깨짐", None: "읽을 수 없음"}
    for b, axes in res["verdicts"].items():
        for ax, v in axes.items():
            f = v["retainedByView"]
            L.append(f"| {b} | {ax} | **{cn[v['classification']]}** | {sym[f['full']]} | {sym[f['excl_2000_episode']]} | "
                     f"{sym[f['excl_2007_episode']]} | {sym[f['excl_both_episodes']]} |")
    L += ["", "유지 = 252일 평균 수익 차(불리−유리) < 0 이고 손실 확률 차 > 0, 전체일·사건별 가중 모두, 양쪽 3사건 이상.", ""]
    for b in res["cells"]:
        for ax, c in res["cells"][b].items():
            L += [f"## 2. {b} · {ax} (불리 `{c['adverseSide']}` / 유리 `{c['benignSide']}`) — 전체일 가중, t 종가", "",
                  "| 표본 | 기준(낙폭만) 252 | 불리 63 | 불리 126 | 불리 252 | 유리 63 | 유리 126 | 유리 252 | 차이(불리−유리) 252 평균/손실 | 사건 수 불리/유리 |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
            for v in VIEWS:
                d = c["views"][v]["close_t/days"]
                g = d["gap"]["252"]
                gs = "n/a" if not g else f"{_p(g['mean'])} / {_p(g['loss'])}"
                ns = "n/a" if not g else f"{g['spellsAdverseBenign'][0]}/{g['spellsAdverseBenign'][1]}"
                L.append(f"| {v} | {_side(d['depthOnlyBaseline'], '252')} | {_side(d['adverse'], '63')} | {_side(d['adverse'], '126')} | "
                         f"{_side(d['adverse'], '252')} | {_side(d['benign'], '63')} | {_side(d['benign'], '126')} | {_side(d['benign'], '252')} | {gs} | {ns} |")
            L += ["", "사건별 동일 가중, 252일:", "", "| 표본 | 불리 | 유리 | 기준 | t+1 종가 차이(전체일, 평균/손실) |", "|---|---|---|---|---|"]
            for v in VIEWS:
                sp, d1 = c["views"][v]["close_t/spells"], c["views"][v]["close_t1/days"]
                g1 = d1["gap"]["252"]
                L.append(f"| {v} | {_side(sp['adverse'], '252')} | {_side(sp['benign'], '252')} | {_side(sp['depthOnlyBaseline'], '252')} | "
                         f"{'n/a' if not g1 else _p(g1['mean']) + ' / ' + _p(g1['loss'])} |")
            L.append("")
    L += ["## 3. 변수 간 중복성 (10–20% 일, phi 계수)", "", "| 표본 | 쌍 | 일수 | phi |", "|---|---|---|---|"]
    for v, pairs in res["redundancy"].items():
        for k, x in pairs.items():
            ph = "n/a" if x["phi"] is None else format(x["phi"], "+.2f")
            L.append(f"| {v} | {k} | {x['days']} | {ph} |")
    return "\n".join(L) + "\n"


def main() -> int:
    out = build()
    (HERE / "atlas-followup-audit.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    (HERE / "ATLAS-FOLLOWUP-TABLES-ko.md").write_text(render(out))
    for b, axes in out["verdicts"].items():
        for ax, v in axes.items():
            print(f"{b:15s} {ax:14s} {v['classification']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
