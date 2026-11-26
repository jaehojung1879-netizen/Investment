"""Regime-dependence audit of the Full Drawdown Atlas (#368). Descriptive only; the Atlas is read, never edited.

Question: does the difference between states WITHIN the same 10-20% drawdown (speed, stabilisation, credit, VIX)
repeat across independent market regimes, or does it live in 2000-02 and 2007-09?

Nothing new is introduced: the entry state is the Atlas's own (`atlas.state()`), the cells are the Atlas's own
(depth bucket x one axis x two sides) plus the union of its 10-15 and 15-20 buckets, and the outcomes are the
Atlas's own (forward return, loss probability, median further minimum). No p-value, threshold search, fitted
parameter, strategy or cost model. Every statement below is a count or a sign.

Views (each applied to every cell, each under two weightings and two execution assumptions):
  full                 the Atlas sample (must reproduce the Atlas numbers; asserted)
  excl_2000_02         drop entries dated 2000-01-01..2002-12-31
  excl_2007_09         drop entries dated 2007-01-01..2009-12-31
  excl_both            drop both windows
  excl_both_spells     drop every entry belonging to the two bear-market drawdown spells (2000-03 and 2007-10 peaks),
                       which also removes the 2003-06 and 2010-12 entries absorbed into them
  since_2013           entries dated 2013-01-01 or later
Weightings:
  days                 every eligible session counts once (the Atlas; overlapping, not independent)
  spells               each drawdown spell counts once: mean over spells of the spell's own mean
Execution:
  close_t              enter at the close of the signal day (the Atlas)
  close_t1             enter at the NEXT session's close; the state is still read at t; the t->t+1 move is reported

Reading rule, declared before the numbers: a contrast is only read when each side has at least MIN_SPELLS spells,
because fewer than three cannot be called a repeat. This is a reporting gate on language, not a test.

    python -m research.track_b_pilot.audit_atlas
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

from research.track_b_pilot import atlas as A

HERE = Path(__file__).resolve().parent
ATLAS_JSON = HERE / "drawdown-atlas.json"
ATLAS_SHA256 = "f3b666b935c6495c5fac16f066b6aea14deaf6380f28ad54ee389eaf03425ffc"
HORIZONS = A.HORIZONS
MIN_SPELLS = 3
EXCL_2000_02 = ("2000-01-01", "2002-12-31")
EXCL_2007_09 = ("2007-01-01", "2009-12-31")
SINCE = "2013-01-01"
SIDES = {  # axis -> (adverse side, benign side); "adverse" is the side the Atlas called worse
    "speed": ("slow", "fast"),
    "stabilisation": ("newLowWithin21", "stabilised"),
    "credit": ("aboveExpandingMedian", "atOrBelow"),
    "vix": ("aboveExpandingMedian", "atOrBelow"),
}
BUCKETS = {"10-15%": (0.10, 0.15), "15-20%": (0.15, 0.20), "10-20% (union)": (0.10, 0.20)}
VIEWS = ("full", "excl_2000_02", "excl_2007_09", "excl_both", "excl_both_spells", "since_2013")
STAY_PHASES = (("first_day", 1, 1), ("days_2_21", 2, 21), ("days_22_plus", 22, 10 ** 9))


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def forward_arrays(tr: np.ndarray, shift: int) -> dict:
    """fwd[h][i], fmin[h][i]: outcome of entering at close of i+shift; NaN when the window is not complete."""
    n = len(tr)
    out = {}
    for h in HORIZONS:
        f = np.full(n, np.nan)
        m = np.full(n, np.nan)
        for i in range(n):
            e = i + shift
            if e + h < n:
                f[i] = tr[e + h] / tr[e] - 1
                m[i] = tr[e + 1:e + h + 1].min() / tr[e] - 1
        out[h] = (f, m)
    return out


def bear_spells(s: dict) -> tuple[int, int]:
    """Spell ids of the two bear-market spells: the spells containing 2000-03-24-ish and 2007-10 peaks' drawdowns."""
    dates = s["dates"]
    ids = []
    for lo, hi in (("2000-03-01", "2002-10-31"), ("2007-10-01", "2009-03-31")):
        in_window = [int(s["spell"][i]) for i, d in enumerate(dates) if lo <= d <= hi and s["spell"][i] >= 0]
        ids.append(max(set(in_window), key=in_window.count))
    return ids[0], ids[1]


def view_mask(s: dict, view: str, bears: tuple[int, int]) -> np.ndarray:
    d = np.array(s["dates"])
    ok = np.ones(len(d), dtype=bool)
    if view in ("excl_2000_02", "excl_both"):
        ok &= ~((d >= EXCL_2000_02[0]) & (d <= EXCL_2000_02[1]))
    if view in ("excl_2007_09", "excl_both"):
        ok &= ~((d >= EXCL_2007_09[0]) & (d <= EXCL_2007_09[1]))
    if view == "excl_both_spells":
        ok &= ~np.isin(s["spell"], list(bears))
    if view == "since_2013":
        ok &= d >= SINCE
    return ok


def side_masks(s: dict) -> dict:
    sp, sl = s["since_peak"], s["since_low"]
    cred = np.array([x is True for x in s["credit_high"]])
    cred_lo = np.array([x is False for x in s["credit_high"]])
    vix = np.array([x is True for x in s["vix_high"]])
    vix_lo = np.array([x is False for x in s["vix_high"]])
    stab = (sl >= A.STABLE_SESSIONS) & (s["dd"] < 0)
    return {
        "speed": {"slow": sp > A.FAST_SESSIONS, "fast": sp <= A.FAST_SESSIONS},
        "stabilisation": {"newLowWithin21": sl < A.STABLE_SESSIONS, "stabilised": stab},
        "credit": {"aboveExpandingMedian": cred, "atOrBelow": cred_lo},
        "vix": {"aboveExpandingMedian": vix, "atOrBelow": vix_lo},
    }


def metrics(s: dict, idx: np.ndarray, fw: dict, weighting: str, gap: np.ndarray | None = None) -> dict:
    spell_of = s["spell"][idx]
    out = {"nDays": int(len(idx)), "nSpells": int(len(set(spell_of.tolist())))}
    if gap is not None and len(idx):
        g = gap[idx]
        g = g[~np.isnan(g)]
        out["signalDayToNextCloseMean"] = float(g.mean()) if len(g) else None
    for h in HORIZONS:
        f, m = fw[h]
        ok = ~np.isnan(f[idx])
        ii, sp = idx[ok], spell_of[ok]
        if not len(ii):
            out[str(h)] = None
            continue
        fv, mv = f[ii], m[ii]
        row = {"nDays": int(len(ii)), "nSpells": int(len(set(sp.tolist())))}
        if weighting == "days":
            row.update(meanReturn=float(fv.mean()), medianReturn=float(np.median(fv)),
                       lossProbability=float((fv < 0).mean()), medianFurtherMin=float(np.median(mv)))
        else:
            ids = sorted(set(sp.tolist()))
            sm = np.array([fv[sp == k].mean() for k in ids])
            row.update(meanReturn=float(sm.mean()), medianReturn=float(np.median(sm)),
                       lossProbability=float(np.mean([(fv[sp == k] < 0).mean() for k in ids])),
                       medianFurtherMin=float(np.median([np.median(mv[sp == k]) for k in ids])))
        out[str(h)] = row
    return out


def contrast(adverse: dict, benign: dict, h: str = "252") -> dict:
    a, b = adverse.get(h), benign.get(h)
    if not a or not b:
        return {"status": "UNDEFINED_EMPTY_SIDE"}
    nsp = (a["nSpells"], b["nSpells"])
    d = {"meanReturn": a["meanReturn"] - b["meanReturn"], "lossProbability": a["lossProbability"] - b["lossProbability"],
         "medianFurtherMin": a["medianFurtherMin"] - b["medianFurtherMin"]}
    same = (d["meanReturn"] < 0, d["lossProbability"] > 0, d["medianFurtherMin"] < 0)  # Atlas direction
    if min(nsp) < MIN_SPELLS:
        status = "INSUFFICIENT_SPELLS_NOT_READ"
    elif all(same):
        status = "SAME_DIRECTION_ALL_THREE"
    elif not any(same):
        status = "REVERSED_ALL_THREE"
    else:
        status = "MIXED"
    return {"status": status, "spellsAdverseBenign": list(nsp), "diff": d}


def leave_one_spell_out(s, idx_a, idx_b, fw, h=252) -> dict:
    """Range of the (adverse - benign) mean-return gap when each spell present on either side is removed in turn."""
    f, _ = fw[h]
    gaps = {}
    for k in sorted(set(s["spell"][idx_a].tolist()) | set(s["spell"][idx_b].tolist())):
        a = idx_a[(s["spell"][idx_a] != k) & ~np.isnan(f[idx_a])]
        b = idx_b[(s["spell"][idx_b] != k) & ~np.isnan(f[idx_b])]
        if len(a) and len(b):
            gaps[int(k)] = float(f[a].mean() - f[b].mean())
    if not gaps:
        return {"status": "UNDEFINED"}
    worst = max(gaps, key=lambda k: gaps[k])
    return {"min": min(gaps.values()), "max": max(gaps.values()), "removingThisSpellMovesGapMost": worst,
            "stillNegativeAfterEveryRemoval": bool(max(gaps.values()) < 0)}


def spell_catalogue(s: dict, bears) -> dict:
    out = {}
    for k in sorted({int(x) for x in s["spell"] if x >= 0}):
        ix = np.where(s["spell"] == k)[0]
        out[str(k)] = {"start": s["dates"][ix[0]], "end": s["dates"][ix[-1]],
                       "maxDepth": float(s["dd"][ix].min()), "bear": bool(k in bears)}
    return out


def build() -> dict:
    assert sha256_file(ATLAS_JSON) == ATLAS_SHA256, "ATLAS_JSON_CHANGED"
    s = A.state()
    tr = s["tr"]
    bears = bear_spells(s)
    fw = {0: forward_arrays(tr, 0), 1: forward_arrays(tr, 1)}
    gap = np.append(tr[1:] / tr[:-1] - 1, np.nan)
    sides = side_masks(s)
    cat = spell_catalogue(s, bears)
    res = {"study": "full-drawdown-atlas-regime-audit", "evidenceClass": "DESCRIPTIVE_ON_EXPOSED_HISTORY",
           "noPValues": True, "noStrategy": True, "noNewVariables": True, "minSpellsToRead": MIN_SPELLS,
           "atlasSha256Verified": ATLAS_SHA256, "window": [s["dates"][0], s["dates"][-1]], "sessions": len(tr),
           "bearSpells": {"2000": {"id": bears[0], **cat[str(bears[0])]}, "2007": {"id": bears[1], **cat[str(bears[1])]}},
           "views": {"excl_2000_02": list(EXCL_2000_02), "excl_2007_09": list(EXCL_2007_09), "since_2013": SINCE},
           "cells": {}, "decomposition": {}, "spellDetail": {}, "composition": {}}
    atlas = json.loads(ATLAS_JSON.read_text())
    for bname, (lo, hi) in BUCKETS.items():
        depth = -s["dd"]
        bmask = (depth >= lo) & (depth < hi)
        res["cells"][bname] = {}
        for axis, (adv, ben) in SIDES.items():
            res["cells"][bname][axis] = {"adverseSide": adv, "benignSide": ben, "views": {}}
            for view in VIEWS:
                vm = view_mask(s, view, bears)
                idx_a = np.where(bmask & sides[axis][adv] & vm)[0]
                idx_b = np.where(bmask & sides[axis][ben] & vm)[0]
                cell = {}
                for shift, sname in ((0, "close_t"), (1, "close_t1")):
                    for w in ("days", "spells"):
                        ma = metrics(s, idx_a, fw[shift], w, gap if shift else None)
                        mb = metrics(s, idx_b, fw[shift], w, gap if shift else None)
                        cell[f"{sname}/{w}"] = {"adverse": ma, "benign": mb,
                                                "contrast252": contrast(ma, mb),
                                                "contrast126": contrast(ma, mb, "126")}
                cell["leaveOneSpellOut252/close_t"] = leave_one_spell_out(s, idx_a, idx_b, fw[0])
                res["cells"][bname][axis]["views"][view] = cell
            # composition of the full-sample cells by regime (bear spell / other), in days and spells
            comp = {}
            for side, nm in ((adv, "adverse"), (ben, "benign")):
                idx = np.where(bmask & sides[axis][side])[0]
                sp = s["spell"][idx]
                ids = sorted(set(sp.tolist()))
                comp[nm] = {"days": int(len(idx)), "spells": len(ids),
                            "daysInBearSpells": int(np.isin(sp, list(bears)).sum()),
                            "spellsOutsideBears": [k for k in ids if k not in bears],
                            "perSpell": {str(k): {"days": int((sp == k).sum()), "start": cat[str(k)]["start"],
                                                  "mean252": (float(np.nanmean(fw[0][252][0][idx[sp == k]]))
                                                              if (~np.isnan(fw[0][252][0][idx[sp == k]])).any() else None)}
                                         for k in ids}}
            res["composition"].setdefault(bname, {})[axis] = comp
    # reproduce the Atlas's own numbers for its published cells (days weighting, close_t, full view)
    mism = []
    for bname in ("10-15%", "15-20%"):
        for axis, key, (adv, ben) in (("speed", "depthBySpeed", ("slow> 63", "fast<= 63")),
                                      ("stabilisation", "depthByStabilisation", ("newLowWithin21", "stabilised")),
                                      ("credit", "depthByCredit", ("aboveExpandingMedian", "atOrBelow")),
                                      ("vix", "depthByVix", ("aboveExpandingMedian", "atOrBelow"))):
            for side_a, side_k in zip((SIDES[axis][0], SIDES[axis][1]), (adv, ben)):
                mine = res["cells"][bname][axis]["views"]["full"]["close_t/days"]["adverse" if side_a == SIDES[axis][0] else "benign"]
                theirs = atlas[key][bname][side_k]
                for h in ("63", "126", "252"):
                    if theirs[h] and abs(theirs[h]["meanReturn"] - mine[h]["meanReturn"]) > 1e-12:
                        mism.append((bname, axis, side_k, h))
    assert not mism, f"ATLAS_NOT_REPRODUCED {mism}"
    res["atlasCellsReproducedExactly"] = True
    # item 4: first entry vs long stay, within the cell, days weighting and spell weighting, close_t
    for bname, (lo, hi) in BUCKETS.items():
        depth = -s["dd"]
        bmask = (depth >= lo) & (depth < hi)
        stay = np.zeros(len(tr), dtype=int)
        seen: dict = {}
        for i in np.where(bmask)[0]:  # stay day = running count of days this spell has spent in this bucket
            k = int(s["spell"][i])
            seen[k] = seen.get(k, 0) + 1
            stay[i] = seen[k]
        res["decomposition"][bname] = {}
        groups = {"all": bmask}
        for axis, (adv, ben) in SIDES.items():
            for side in (adv, ben):
                groups[f"{axis}:{side}"] = bmask & sides[axis][side]
        for gname, gm in groups.items():
            total = int(gm.sum())
            ph = {}
            for pname, a, b in STAY_PHASES:
                idx = np.where(gm & (stay >= a) & (stay <= b))[0]
                row = {"daysWeighted": metrics(s, idx, fw[0], "days"), "spellWeighted": metrics(s, idx, fw[0], "spells"),
                       "shareOfCellDays": (float(len(idx) / total) if total else None)}
                f252 = fw[0][252][0][idx]
                ok = ~np.isnan(f252)
                row["contributionTo252Mean"] = (float(f252[ok].sum() / max(1, (~np.isnan(fw[0][252][0][np.where(gm)[0]])).sum()))
                                                if ok.any() else None)
                ph[pname] = row
            res["decomposition"][bname][gname] = ph
    # joint census: sample sizes only, no outcome is read. Shows whether depth x credit x progress is even estimable.
    ub = (-s["dd"] >= 0.10) & (-s["dd"] < 0.20)
    joint = {}
    for cr in SIDES["credit"]:
        for st in SIDES["stabilisation"]:
            for sp_ in SIDES["speed"]:
                m = ub & sides["credit"][cr] & sides["stabilisation"][st] & sides["speed"][sp_]
                ids = sorted(set(s["spell"][m].tolist()))
                joint[f"credit:{cr} · progress:{st} · speed:{sp_}"] = {
                    "days": int(m.sum()), "spells": len(ids), "daysInBearSpells": int(np.isin(s["spell"][m], list(bears)).sum()),
                    "spellsOutsideBears": len([k for k in ids if k not in bears])}
    res["jointCensus10to20"] = {"note": "counts only; no outcome read; Atlas deliberately built no combination cells", "cells": joint}
    # first entry into 10-20% territory, one row per spell; both execution assumptions side by side
    first = A.first_entries(s, (-s["dd"] >= 0.10) & (-s["dd"] < 0.20))
    rows = []
    for i in first:
        row = {"spell": int(s["spell"][i]), "date": s["dates"][i], "depth": float(s["dd"][i]),
               "bear": bool(int(s["spell"][i]) in bears), "creditHigh": s["credit_high"][i],
               "newLowWithin21": bool(s["since_low"][i] < A.STABLE_SESSIONS), "slow": bool(s["since_peak"][i] > A.FAST_SESSIONS),
               "vixHigh": s["vix_high"][i], "signalDayToNextClose": (float(gap[i]) if not np.isnan(gap[i]) else None)}
        for sh, nm in ((0, "close_t"), (1, "close_t1")):
            for h in HORIZONS:
                f, m = fw[sh][h]
                row[f"{nm}/fwd{h}"] = None if np.isnan(f[i]) else float(f[i])
                row[f"{nm}/furtherMin{h}"] = None if np.isnan(m[i]) else float(m[i])
        rows.append(row)
    res["spellDetail"] = rows

    def agg(sel, nm, h=252):
        v = [r[f"{nm}/fwd{h}"] for r in sel if r[f"{nm}/fwd{h}"] is not None]
        mn = [r[f"{nm}/furtherMin{h}"] for r in sel if r[f"{nm}/furtherMin{h}"] is not None]
        if not v:
            return None
        return {"n": len(v), "meanReturn": float(np.mean(v)), "medianReturn": float(np.median(v)),
                "lossCount": int(sum(x < 0 for x in v)), "medianFurtherMin": float(np.median(mn))}

    def group(sel):
        return {nm: agg(sel, nm) for nm in ("close_t", "close_t1")}
    res["firstEntrySummary"] = {
        "all": group(rows), "creditHigh": group([r for r in rows if r["creditHigh"] is True]),
        "creditAtOrBelow": group([r for r in rows if r["creditHigh"] is False]),
        "creditUnavailable": group([r for r in rows if r["creditHigh"] is None]),
        "excludingTwoBears": group([r for r in rows if not r["bear"]]),
        "since2013": group([r for r in rows if r["date"] >= SINCE]),
        "creditHighExcludingBears": group([r for r in rows if r["creditHigh"] is True and not r["bear"]]),
        "note": "Every first entry has a new low within 21 sessions and none is slow (> 63 sessions): the stabilisation and "
                "speed axes therefore have no first-entry contrast; only credit and VIX vary."}
    return res


def _pct(x, d=1):
    return "n/a" if x is None else f"{x * 100:+.{d}f}"


def _cell(m):
    if not m or not m.get("252"):
        return "비어 있음"
    x = m["252"]
    return f"{_pct(x['meanReturn'])} / {x['lossProbability'] * 100:.0f}% / {_pct(x['medianFurtherMin'])} ({x['nSpells']}사건)"


def render(res: dict) -> str:
    sym = {"SAME_DIRECTION_ALL_THREE": "S", "REVERSED_ALL_THREE": "R", "MIXED": "M",
           "INSUFFICIENT_SPELLS_NOT_READ": "–", "UNDEFINED_EMPTY_SIDE": "∅"}
    L = ["# Atlas 국면 의존성 감사 — 자동 생성 표 (`audit_atlas.py` → `atlas-regime-audit.json`)", "",
         "수정 금지: 이 파일은 코드가 만든다. 해석은 `ATLAS-AUDIT-ko.md`.", "",
         "## A. 방향 일치 행렬 (252일, 불리한 쪽 − 유리한 쪽)", "",
         "S 세 지표(평균 수익·손실 확률·추가 최저)가 모두 Atlas 방향 / R 모두 반대 / M 엇갈림 / – 한쪽이 "
         f"{MIN_SPELLS}사건 미만이라 읽지 않음 / ∅ 한쪽이 비어 있음.", "",
         "| 구간 | 축 | 가중·체결 | " + " | ".join(VIEWS) + " |", "|---|---|---|" + "---|" * len(VIEWS)]
    for b, axes in res["cells"].items():
        for ax, c in axes.items():
            for k, nm in (("close_t/days", "전체일·t"), ("close_t/spells", "사건별·t"), ("close_t1/days", "전체일·t+1"),
                          ("close_t1/spells", "사건별·t+1")):
                L.append(f"| {b} | {ax} | {nm} | " + " | ".join(sym[c["views"][v][k]["contrast252"]["status"]] for v in VIEWS) + " |")
    L += ["", "## B. 10–20% 합집합, 252일: 평균 수익 / 손실 확률 / 추가 최저 중앙값 (사건 수)", ""]
    for ax in ("credit", "stabilisation", "speed", "vix"):
        c = res["cells"]["10-20% (union)"][ax]
        L += [f"**{ax}** — 불리: `{c['adverseSide']}`, 유리: `{c['benignSide']}`", "",
              "| 표본 | 전체일 불리 | 전체일 유리 | 사건별 불리 | 사건별 유리 |", "|---|---|---|---|---|"]
        for v in VIEWS:
            d, s_ = c["views"][v]["close_t/days"], c["views"][v]["close_t/spells"]
            L.append(f"| {v} | {_cell(d['adverse'])} | {_cell(d['benign'])} | {_cell(s_['adverse'])} | {_cell(s_['benign'])} |")
        L.append("")
    L += ["## C. 다음 종가 체결: 같은 칸, 252일 (t → t+1)", "", "| 구간·축·표본 | t (전체일) | t+1 (전체일) | 신호일→다음 종가 평균 |", "|---|---|---|---|"]
    for ax in ("credit", "stabilisation"):
        for v in ("full", "excl_both_spells", "since_2013"):
            c = res["cells"]["10-20% (union)"][ax]["views"][v]
            for side in ("adverse", "benign"):
                g = c["close_t1/days"][side].get("signalDayToNextCloseMean")
                L.append(f"| 10–20% {ax} {side} {v} | {_cell(c['close_t/days'][side])} | {_cell(c['close_t1/days'][side])} | {_pct(g, 2)} |")
    L += ["", "## D. 첫 진입(10–20% 구간 진입 사건, 사건당 1건)", "",
          "| 날짜 | 약세장 | 낙폭 | 신용 높음 | 신저점≤21일 | t 252일 수익 | t 추가 최저 | t+1 252일 수익 | 신호일→다음 종가 |", "|---|---|---|---|---|---|---|---|---|"]
    for r in res["spellDetail"]:
        L.append(f"| {r['date']} | {'예' if r['bear'] else ''} | {_pct(r['depth'])} | {r['creditHigh']} | {r['newLowWithin21']} | "
                 f"{_pct(r['close_t/fwd252'])} | {_pct(r['close_t/furtherMin252'])} | {_pct(r['close_t1/fwd252'])} | {_pct(r['signalDayToNextClose'], 2)} |")
    L += ["", "| 집합 | n | 평균 252일 (t) | 손실 건수 | 추가 최저 중앙 | 평균 252일 (t+1) |", "|---|---|---|---|---|---|"]
    for k, v in res["firstEntrySummary"].items():
        if k == "note" or not v["close_t"]:
            continue
        L.append(f"| {k} | {v['close_t']['n']} | {_pct(v['close_t']['meanReturn'])} | {v['close_t']['lossCount']} | "
                 f"{_pct(v['close_t']['medianFurtherMin'])} | {_pct(v['close_t1']['meanReturn'])} |")
    L += ["", res["firstEntrySummary"]["note"], "", "## E. 첫 진입 vs 체류일 분해 (252일, 전체일 가중; 구간 안 체류 일차 기준)", "",
          "| 구간 | 집단 | 국면 | 칸 일수 비중 | 평균 / 손실 / 추가 최저 (사건) | 칸 평균에 대한 기여 |", "|---|---|---|---|---|---|"]
    names = {"first_day": "첫 진입일", "days_2_21": "체류 2–21일차", "days_22_plus": "체류 22일차 이후"}
    for b, groups in res["decomposition"].items():
        for gname in ("all", "credit:aboveExpandingMedian", "credit:atOrBelow", "stabilisation:newLowWithin21", "stabilisation:stabilised"):
            for pname, row in groups[gname].items():
                L.append(f"| {b} | {gname} | {names[pname]} | {_pct(row['shareOfCellDays'], 1).replace('+', '')}"
                         f" | {_cell(row['daysWeighted'])} | {_pct(row['contributionTo252Mean'])} |")
    L += ["", "## F. 10–20% 합집합 구성: 사건별 기여 일수와 252일 평균", ""]
    for ax in ("credit", "stabilisation"):
        for side, v in res["composition"]["10-20% (union)"][ax].items():
            L.append(f"**{ax} / {side}** — {v['days']}일, {v['spells']}사건, 약세장 2개 소속 {v['daysInBearSpells']}일")
            L += ["", "| 사건 시작 | 일수 | 252일 평균 |", "|---|---|---|"]
            for k, p in v["perSpell"].items():
                L.append(f"| {p['start']}{' (약세장)' if int(k) in (res['bearSpells']['2000']['id'], res['bearSpells']['2007']['id']) else ''} | {p['days']} | {_pct(p['mean252'])} |")
            L.append("")
    L += ["## G. 결합 칸 표본 센서스 (10–20%, 수익률 미사용)", "", "| 결합 상태 | 일수 | 사건 | 약세장 2개 소속 일수 | 약세장 밖 사건 |", "|---|---|---|---|---|"]
    for k, v in res["jointCensus10to20"]["cells"].items():
        L.append(f"| {k} | {v['days']} | {v['spells']} | {v['daysInBearSpells']} | {v['spellsOutsideBears']} |")
    L += ["", "## H. 한 사건을 빼도 부호가 유지되는가 (252일 평균 차이, 10–20%, 전체일)", "", "| 축 | 최소 | 최대 | 어느 사건을 빼도 음수 |", "|---|---|---|---|"]
    for ax in ("credit", "stabilisation", "speed", "vix"):
        x = res["cells"]["10-20% (union)"][ax]["views"]["full"]["leaveOneSpellOut252/close_t"]
        L.append(f"| {ax} | {_pct(x.get('min'))} | {_pct(x.get('max'))} | {x.get('stillNegativeAfterEveryRemoval')} |")
    return "\n".join(L) + "\n"


def main() -> int:
    out = build()
    (HERE / "atlas-regime-audit.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    (HERE / "ATLAS-AUDIT-TABLES-ko.md").write_text(render(out))
    print("ok", out["window"], out["sessions"], "bears", out["bearSpells"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
