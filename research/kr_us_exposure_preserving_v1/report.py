"""Integrate the fixed hypothesis family and render the Korean result tables."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from research.kr_us_strategy_batch_v1.common import holm, nav_window, stats
from research.kr_us_exposure_preserving_v1.engine import write_json

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / "kr_us_strategy_batch_v1/results"
KR = ["S2", "VALUE_ORIGINAL", "VALUE_COMPLETE", "CONFIRM_NEUTRAL", "FOUR_FACTOR"]
US = ["PRICE", "PRICE_CONFIRMED", "VALUE", "CASH_PROFITABILITY"]
BLENDS = ["SECTOR_MOMENTUM","COCKTAIL","U1"]
OPTIONAL = ["OW","OW_RESID"]
PAIRS = {"KR":["S2-VALUE_COMPLETE","CONFIRM_NEUTRAL-S2"],"US":["PRICE_CONFIRMED-PRICE","PRICE_CONFIRMED-VALUE"]}
DISPLAY = {
    "S2":"S2", "VALUE_ORIGINAL":"가치 단독", "VALUE_COMPLETE":"가치 단독·완전관측",
    "CONFIRM_NEUTRAL":"사업 확인 단독", "FOUR_FACTOR":"4요인",
    "PRICE":"가격", "PRICE_CONFIRMED":"가격+사업 확인", "VALUE":"가치",
    "CASH_PROFITABILITY":"현금수익성", "SECTOR_MOMENTUM":"업종 모멘텀",
    "COCKTAIL":"원 칵테일", "U1":"원 U1", "OW":"공시 OW", "OW_RESID":"공시 OW_RESID",
}


def read(path):
    return json.loads(path.read_text()) if path.exists() else {}


def pct(value):
    return "—" if value is None else f"{100*value:+.2f}"


def estimate(cell, ci=True):
    mean = cell.get("mean")
    if mean is None:
        return "미측정"
    interval = cell.get("ci")
    if ci:
        suffix = f" [{pct(interval[0])}, {pct(interval[1])}]" if interval else " [구간 미측정]"
    else:
        suffix = ""
    return pct(mean) + suffix


def both(cells, ci=True):
    return " / ".join(estimate(x, ci) for x in cells)


def table(headers, rows):
    return ["|"+"|".join(headers)+"|", "|"+"|".join(["---"]*len(headers))+"|",
            *("|"+"|".join(str(x).replace("|","/") for x in r)+"|" for r in rows), ""]


def claims(results):
    rows = []
    for h in ("126","252"):
        block = []
        for market, names in (("KR", KR), ("US", US+BLENDS+OPTIONAL)):
            section = results[market].get("horizons",{}).get(h,{})
            for name in names:
                if name not in ("COCKTAIL","U1"):
                    block.append((market,name,"선택력" if name != "SECTOR_MOMENTUM" else "업종 배분",
                                  section.get("selection",{}).get(name,{})))
                p = section.get("portfolios",{}).get(name,{})
                block.extend([(market,name,"복제교체−ETF",p.get("funded",{})),
                              (market,name,"복제교체−기존",p.get("fundedMinusLegacy",{}))])
            for pair in PAIRS[market]:
                block.append((market,pair,"선택력 차이",section.get("pairwise",{}).get(pair,{})))
        keys = ["|".join(b[:3]) for b in block]
        assert len(keys) == len(set(keys)) == 44
        p_values = {key: b[3].get("pOneSidedApprox") for key,b in zip(keys,block,strict=True)}
        adjusted = holm(p_values)
        for key,(market,name,comparison,statistic) in zip(keys,block,strict=True):
            raw = p_values[key]
            status = ("미측정" if raw is None else
                      "양의 우위" if adjusted[key] < .05 and statistic["mean"] > 0 else "불확실")
            rows.append({"horizon":int(h),"market":market,"name":name,"comparison":comparison,
                         **statistic,"holmP":adjusted[key],"status":status})
    return rows


def section_pair(results, market, group, name, metric=None):
    cells = []
    for h in ("126","252"):
        cell = results[market].get("horizons",{}).get(h,{}).get(group,{}).get(name,{})
        cells.append(cell if metric is None else cell.get(metric,{}))
    return cells


def pct_num(x):
    return float(x)*100


def matching_lines(market, results, folder):
    p = folder/"matching-audit.csv.gz"
    if not p.exists():
        p = OLD/market/"matching-audit.csv.gz"
    a = pd.read_csv(p, low_memory=False)
    if "ticker" not in a or "reason" not in a or "selector" not in a:
        a = pd.read_csv(OLD/market/"matching-audit.csv.gz")
    rows = []
    names = KR if market == "KR" else US
    for name in names:
        key = "config" if market == "KR" and "config" in a else "selector"
        g = a.loc[a[key].eq(name)]
        all_ok = g.assign(ok=g.reason.eq("MATCHED")).groupby("date").ok.all()
        successes = int(all_ok.sum())
        failures = g.loc[~g.reason.eq("MATCHED"),"reason"].value_counts().to_dict()
        cells = section_pair(results,market,"selection",name)
        rows.append([name,len(all_ok),successes,f"{successes/len(all_ok):.1%}" if len(all_ok) else "—",
                     "/".join(str(c.get("n",0)) for c in cells),
                     "/".join(str(c.get("independentBlocksApprox","—")) for c in cells),
                     both(cells),", ".join(f"{k} {v}" for k,v in failures.items()) or "—"])
    return table(["신호","대상 주","완전 매칭","매칭률","평가 가능 6/12주","주차÷블록길이 6/12",
                  "선택력 6/12개월 %p","실패 사유·leg 수"],rows)


def exposure_lines(folder):
    if not (folder/"exposure.csv.gz").exists():
        return []
    frame = pd.read_csv(folder/"exposure.csv.gz")
    rows = []
    for name, g in frame.groupby("config",sort=False):
        avg = lambda col: f"{pct_num(g[col].mean()):.2f}"
        older_error = (g.originalLeader-g.baseLeader).abs().mean()
        new_error = (g.fundedLeader-g.baseLeader).abs().mean()
        rows.append([name,len(g),f"{g.exactCells.mean():.1%}",f"{g.activeNames.mean():.1f}/{g.fundedNames.mean():.1f}",
                     avg("netActiveBuys"),avg("originalSectorL1")+" → "+avg("fundedSectorL1"),
                     f"{100*older_error:.2f} → {100*new_error:.2f}",
                     avg("originalIndividualLeaderL1")+" → "+avg("fundedIndividualLeaderL1"),
                     avg("baseLeader"),
                     avg("originalDirectLeader")+" + "+avg("originalIndirectLeader"),
                     avg("fundedLeader")])
    return table(["신호","판단 주","셀 정확","선택/직접 이름 수","순 적극 매수%",
                  "업종 L1 기존→복제 %p","주도주 그룹 오차 기존→복제 %p","주도주 개별 L1 기존→복제 %p",
                  "대용 ETF 주도주%","기존 주도주 직접+간접%","직접복제 주도주%"],rows)


def portfolio_lines(market, results):
    horizons = results[market].get("horizons",{})
    names = list(horizons.get("126",{}).get("portfolios",{}))
    rows = []
    for name in names:
        p = lambda k: section_pair(results,market,"portfolios",name,k)
        rows.append([name,"/".join(str(x.get("n",0)) for x in p("funded")),both(p("legacy")),
                     both(p("passive")),both(p("active")),both(p("funded")),both(p("fundedMinusLegacy")),
                     both(p("fundedSelection"))+" (n="+"/".join(str(x.get("n",0)) for x in p("fundedSelection"))+")",
                     both(p("fundedSharedDonorSelection"))+" (n="+"/".join(str(x.get("n",0)) for x in p("fundedSharedDonorSelection"))+")"])
    return table(["신호","공통 6/12주","기존−ETF","B−ETF","F−B","F−ETF","F−기존",
                  "복제교체−복제대조","동일 조달액 복제 대조"],rows)


def nav_lines(market, folder, names):
    v = read(folder/"funded-ledgers.json")
    old = read(OLD/market/"summary.json").get("ledgers",{})
    rows = []
    for cadence in ("L26","L52"):
        for name in ["ETF","PASSIVE",*names]:
            if name in ("ETF","PASSIVE"):
                key = "KR:ETF" if market == "KR" else "US:SPY"
            elif market == "US":
                key = f"US:{name}:Q020"
            else:
                selector, k = ("S2",name[-1]) if name.startswith("S2_K") else (name,5)
                key = f"KR:{selector}:FIXED20:K{k}"
            original = old.get(cadence,{}).get(key,{}).get("full",{}) if name != "PASSIVE" else {}
            funded = v.get(("FULL:" if market=="KR" else "")+cadence,{}).get(name,{})
            suffix = v.get("SUFFIX:"+cadence,{}).get(name,{})
            def fmt(c):
                if c.get("status") == "NOT_ESTIMABLE":
                    return "미측정 ("+c.get("reason","")+")"
                if c.get("turnoverDiagnostic",{}).get("terminalEvents"):
                    return "미측정 (미해결 보유 종료)"
                turn = c.get("oneWayTurnoverPerYear")
                return "/".join((pct(c.get("cagr")),pct(c.get("mdd")),f"{turn:.3f}" if turn is not None else "—"))
            rows.append([cadence,name,fmt(original),fmt(funded),fmt(suffix) if market == "KR" else pct(funded.get("qqqComparison",{}).get("cagrGap"))])
    lines = table(["장부","신호","기존 CAGR/MDD/편도회전율","복제교체 CAGR/MDD/편도회전율",
                   "2026 시작 복제교체" if market=="KR" else "복제교체 CAGR−QQQ"],rows)
    if market == "KR":
        local = []
        for cadence in ("L26","L52"):
            window = v.get("SUFFIX:"+cadence,{})
            for name in names:
                old = window.get(name+":ORIGINAL",{})
                new = window.get(name,{})
                local.append([cadence,name,fmt(old),fmt(new),new.get("targetNontradable","—")])
        lines += ["2026-01-05 체결부터 다시 시작한 짧은 창의 동일 기간 비교. L52는 52계정 중 아직 배치 차례가 오지 않은 계정도 ETF를 보유한다. 전 기간 성과를 대체하지 않으며, 원 엔진은 거래 불능 보유분을 잠근다.",""]
        lines += table(["장부","신호","기존 CAGR/MDD/편도회전율","복제교체 CAGR/MDD/편도회전율","체결 불가 목표 수"],local)
    return lines


def sensitivities(market, results):
    rows = []
    data = results[market].get("horizons",{})
    for h, section in data.items():
        for name,c in section["portfolios"].items():
            period = "NO_SEMI_LED" if market=="KR" else "EX_2021"
            subset = c.get("periods",{}).get(period,{})
            rows.append([name,h,estimate(c["funded"]),estimate(c.get("legacyExcludeLeaderContribution",{})),
                         estimate(c.get("excludeLeaderContribution",{})),c.get("maximumName","—"),
                         estimate(c.get("excludeMaximumName",{})),c.get("maximumEntryYear","—"),
                         estimate(c.get("excludeMaximumEntryYear",{})),estimate(subset.get("legacy",{})),estimate(subset.get("funded",{})),
                         subset.get("funded",{}).get("n",0)])
    return table(["신호","세션","복제교체−ETF","기존 주도주 기여 제외","복제교체 주도주 기여 제외",
                  "최대 이름","최대 이름 기여 제외","최대 진입년","최대 진입년 제외",
                  "주도기 제외 기존","주도기 제외 복제교체","주도기 제외 n"],rows)


def official_tables(out):
    lines = ["## 공시 자료로 확인 가능한 노출",""]
    path = out/"KR/official-pcf-exposure-audit.csv.gz"
    if path.exists():
        g = pd.read_csv(path)
        rows = []
        for name in ("ORIGINAL:S2","FUNDED:S2","FUNDED:PASSIVE"):
            f = g[g.config.eq(name)]
            if len(f):
                rows.append([name,len(f),pct(f.pcfBaselineLeaders.mean()),pct(f.totalLeaders.mean()),
                             pct(f.leaderAbsoluteGap.mean()),pct(f.officialPCFSectorL1.mean()),pct(f.industryUnknownWeight.mean())])
        lines += ["한국 공식 PCF 24개 중 최근 자료가 있는 58주. 바스켓 기준이며 펀드의 전체 보유 비중과 최초 공개 시각은 미검증이다.",""]
        lines += table(["구성","주","PCF 두 종목%","구성 두 종목%","평균 절대 차이 %p","업종 L1 %p","미분류 비중%"],rows)
    path = out/"US/actual-spy-partial-exposure-audit.csv.gz"
    if path.exists():
        g = pd.read_csv(path)
        rows = []
        for name in ("PRICE_CONFIRMED","FUNDED:PRICE_CONFIRMED","U1","FUNDED:U1","B"):
            f = g[g.config.eq(name)]
            if len(f):
                rows.append([name,len(f),pct(f.reportedMegaConditionalBaseWeight.mean()),
                             pct(f.directMegaWeight.mean()),pct(f.etfIndirectMegaConditionalWeight.mean()),
                             pct(f.totalMegaConditionalWeight.mean()),pct(f.conditionalActualMegaDifference.abs().mean()),
                             pct(f.reportedUnknownSectorNetWeight.mean())])
        lines += ["미국은 판단일 전 공개된 28개 공시 중 가용한 최신 보고를 사용한다. 353주, 보고 시차 중앙값 103일. 아래 값은 식별 가능한 공시 행의 비중으로, 전체 복제 가능 주는 0주다. 종목 코드 연결은 기존 CUSIP 지도에 조건부다.",""]
        lines += table(["구성","주","공시 주도주%","직접%","ETF 간접%","합계%","공시 대비 평균 절대 차이 %p","공시 미분류 비중%"],rows)
    return lines


def component_table(out):
    native = read(out/"US/native-components.json").get("summary",{})
    rows = []
    for name, by in native.items():
        for form, horizons in by.items():
            six, twelve = horizons.get("126",{}),horizons.get("252",{})
            for component in six:
                rows.append([name,form,component,both([six[component],twelve.get(component,{})])])
    lines = ["## 미국 칵테일과 U1 원 구성","",
            "슬리브별 SPY 대비 기여를 같은 날짜에서 합산했다. 원 칵테일 네 슬리브와 U1의 시총 상위5 및 잔여 칵테일이 책의 고정보유 순초과와 일치한다. 운용 CAGR 기여와는 별도다.",""]+table(
                ["구성","구현","슬리브","비용 차감 기여 6/12개월 %p"],rows)
    old = read(OLD/"US/summary.json")
    comparisons = []
    for name in ("US:NATIVE_COCKTAIL","US:NATIVE_U1"):
        a = [old.get("fixed",{}).get(h,{}).get(name,{}).get("common",{}) for h in ("126","252")]
        for cadence in ("L26","L52"):
            m = old.get("ledgers",{}).get(cadence,{}).get(name,{}).get("full",{})
            comparisons.append([name,cadence,both(a),pct(m.get("cagr")),pct(m.get("mdd")),
                                f"{m.get('oneWayTurnoverPerYear',0):.3f}" if m else "—"])
    return lines + ["원 native 100% 구성의 #350 고정보유·운용 장부를 재사용했다. 앞의 F 비교는 동일 명목 20%의 조달 진단이다.",""] + table(
        ["원 구성","장부","6/12개월 SPY 차이","CAGR%","MDD%","편도 회전율/년"],comparisons)


def funding_increment_table(market, folder):
    values = {}
    for h in (126,252):
        path = folder/f"cohorts-{h}.csv.gz"
        if not path.exists():
            return []
        raw = pd.read_csv(path, usecols=["config","date","active","legacy","funded","passive"])
        for name, g in raw.groupby("config",sort=False):
            common = g[["active","legacy","funded","passive"]].notna().all(axis=1)
            delta = (g.active-g.legacy).where(common)
            values.setdefault(name,[]).append(stats(delta,h))
    return ["복제 기준의 ETF 대비 차이까지 빼고 남은 조달 방식 차이는 (F−B)−(기존−ETF)로 계산했다. 동일 날짜의 진단이며 명목 구간이다.",""] + table(
        ["시장","신호","기준 차이 제거 후 조달 방식 차이 6/12개월 %p","n 6/12"],[
            [market,name,both(c),"/".join(str(s["n"]) for s in c)] for name,c in values.items()])


def qqq_table(results):
    if not results["US"]:
        return []
    names = results["US"]["horizons"]["126"]["portfolios"]
    a = lambda name,k: section_pair(results,"US","portfolios",name,k)
    return ["## QQQ 보조 비교","","수정된 기존 QQQ 총수익과 동일 체결·비용을 썼다. 주 검정 기준은 SPY다.",""] + table(
        ["구성","기존−QQQ 6/12개월 %p","복제교체−QQQ 6/12개월 %p"],
        [[name,both(a(name,"legacyVsQQQ")),both(a(name,"fundedVsQQQ"))] for name in names])


def verdicts(results):
    lines = []
    pick = lambda m,s,k: section_pair(results,m,"portfolios",s,k)
    if results["KR"]:
        conf = section_pair(results,"KR","selection","CONFIRM_NEUTRAL")
        aligned = pick("KR","CONFIRM_NEUTRAL","funded")
        lines += [
            f"**한국 — 사업 확인에는 방향성이 있었고 ETF 대비 우위는 불확실하다.** 사업 확인 단독의 대조군 차이는 {both(conf)}%p였다(n={conf[0]['n']}/{conf[1]['n']}). 추가 해시 8개의 평균은 모두 양수였지만 크기가 달랐고, 모두 매칭된 27/26주는 구간을 계산할 만큼 길지 않았다. 전체 직접복제 가격이 관측된 {aligned[0]['n']}/{aligned[1]['n']}주에서 사업 확인의 기존 ETF 초과는 {both(pick('KR','CONFIRM_NEUTRAL','legacy'),False)}%p, 복제교체는 {both(aligned)}%p였다. S2의 복제 기준 대비 효과는 {both(pick('KR','S2','active'),False)}%p였고, 복제 기준이 KODEX 200보다 {both(pick('KR','S2','passive'),False)}%p여서 ETF 대비로는 {both(pick('KR','S2','funded'))}%p가 남았다. 전체 운용 창은 미해결 종목 종료 때문에 판별 불가다.",
            ""]
    if results["US"]:
        name = "PRICE_CONFIRMED"
        sel = section_pair(results,"US","selection",name)
        aligned = pick("US",name,"funded")
        lines += [
            f"**미국 — 가격+사업 확인의 선택 효과는 양의 점추정이고, 복제교체의 SPY 대비 차이는 대부분 복제 기준에서 나왔다.** 대조군 차이는 {both(sel)}%p(n={sel[0]['n']}/{sel[1]['n']}), 기존 ETF 혼합은 {both(pick('US',name,'legacy'),False)}%p였다. 복제교체는 SPY 대비 {both(aligned)}%p였고, 이 중 복제 기준과 SPY의 차이가 {both(pick('US',name,'passive'),False)}%p, 신호 교체와 복제 기준의 차이가 {both(pick('US',name,'active'))}%p였다. 실제 SPY 보유를 맞춘 경우의 우위와 신호 자체의 우위는 이 자료로 확정할 수 없다.",
            ""]
        cocktail, u1 = (pick("US",n,"funded")[0] for n in ("COCKTAIL","U1"))
        a, b = (pick("US",n,"active")[0] for n in ("COCKTAIL","U1"))
        lines += [f"미국 칵테일과 U1 복제교체의 SPY 대비 6개월 차이는 각각 {pct(cocktail['mean'])}/{pct(u1['mean'])}%p였다. 같은 날짜의 대용치 기준만 보유한 차이는 {pct(pick('US',name,'passive')[0]['mean'])}%p, 신호 교체 추가분은 각각 {pct(a['mean'])}/{pct(b['mean'])}%p였다. 양의 ETF 초과가 관측된 경우에도 추가 신호 효과를 분리해서 읽어야 한다.",""]
        sector = section_pair(results,"US","selection","SECTOR_MOMENTUM")
        lines += [f"업종 모멘텀의 다른 업종 바구니 대비 차이는 {both(sector)}%p였다. 양쪽에 직접복제 조달을 적용하면 {both(pick('US','SECTOR_MOMENTUM','fundedSelection'))}%p였다. 업종 전체를 담는 시점의 조달 한도로 목표 셀 비중이 정확히 같았던 주는 0주다.",""]
    return lines


def verification(out):
    parent = HERE.parents[1]
    prior = read(OLD/"prospective-status.json")
    for path, digest in prior["existingFilesSha256"].items():
        assert hashlib.sha256((parent/path).read_bytes()).hexdigest() == digest, path
    write_json(out/"prospective-status.json",prior)
    import subprocess
    design = subprocess.check_output(["git","show","e3e572f:research/kr_us_exposure_preserving_v1/DESIGN-ko.md"],cwd=parent)
    assert design == (HERE/"DESIGN-ko.md").read_bytes()
    checks = {"prospectiveFilesByteUnchanged":True,"designCommit":"e3e572f","sourceBase":"36ac329261f8f9000935e524d8a28c2005524c10",
              "designSha256":hashlib.sha256(design).hexdigest()}
    for market in ("KR","US"):
        folder = out/market
        if not (folder/"summary.json").exists():
            checks[market] = {"status":"UNAVAILABLE"}
            continue
        check = {}
        exposure_file = pd.read_csv(folder/"exposure.csv.gz")
        exact = exposure_file.loc[exposure_file.exactCells]
        assert exact.fundedSectorL1.abs().max() < 1e-9
        assert (exact.fundedLeader-exact.baseLeader).abs().max() < 1e-9
        assert (exposure_file.nominalBudget-.2).abs().max() < 1e-9
        assert (exposure_file.netActiveBuys-exposure_file.nominalBudget).max() < 1e-9
        check["exactExposureRows"] = len(exact)
        check["fundingRows"] = len(exposure_file)
        for h in (126,252):
            frame = pd.read_csv(folder/f"cohorts-{h}.csv.gz")
            error = float((frame.funded-frame.passive-frame.active).abs().max())
            assert error < 1e-9
            check[str(h)] = {"bridgeMaximumError":error,"rows":len(frame)}
        ledgers = read(folder/"funded-ledgers.json")
        maximum_nav_error = 0.
        checks_nav = 0
        for label, by_name in ledgers.items():
            if not isinstance(by_name,dict):
                continue
            nav = pd.read_csv(folder/f"funded-nav-{label.replace(':','-')}.csv.gz",index_col=0,parse_dates=True)
            for name, stored in by_name.items():
                if stored["status"] != "MEASURED":
                    assert name not in nav
                    continue
                actual = nav_window(nav[name],nav["ETF"])
                error = max(abs(stored[key]-actual[key]) for key in (
                    "cagr","mdd","etfCagr","etfMdd","cagrGap","annualArithmeticDailyGap","compoundingRemainder"))
                assert error < 1e-9
                maximum_nav_error = max(maximum_nav_error,error)
                checks_nav += 1
        check["measuredNavsRecalculated"] = checks_nav
        check["maximumSavedNavMetricError"] = maximum_nav_error
        checks[market] = check
    write_json(out/"verification.json",checks)
    paths = [*out.rglob("*"), *(HERE/"inputs").rglob("*"), *HERE.glob("*.py"), HERE/"DESIGN-ko.md", HERE/"reproduce.sh"]
    write_json(out/"manifest.json",{str(p.relative_to(HERE)):hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in sorted(paths) if p.is_file() and p != out/"manifest.json"})


def main():
    out = HERE/"results"
    results = {m:read(out/m/"summary.json") for m in ("KR","US")}
    if not any(results.values()):
        raise ValueError("both markets lack results")
    hypotheses = claims(results)
    pd.DataFrame(hypotheses).to_csv(out/"hypotheses.csv",index=False)
    first = []
    for market,names in (("KR",KR),("US",US+BLENDS+OPTIONAL)):
        for name in names:
            s = section_pair(results,market,"selection",name)
            p = lambda k: section_pair(results,market,"portfolios",name,k)
            exclude = p("excludeLeaderContribution")
            periods = p("periods")
            label = "NO_SEMI_LED" if market=="KR" else "EX_2021"
            over = [d.get(label,{}).get("funded",{}) for d in periods]
            first.append([market,DISPLAY[name],both(s),both(p("legacy")),both(p("funded")),both(exclude,False),both(over,False)])
    primary = [row for row in hypotheses if row["horizon"] == 126]
    positives = [row for row in primary if row["status"] == "양의 우위"]
    lines = ["# 한·미 종목 선택력과 지수 노출 유지","",
             "PR #350 `36ac329` 기준. 비교 규칙은 새 계산 전에 `e3e572f`로 고정했다. 모든 수치는 기존에 살펴본 과거에서 재평가했다.","",
             "아래는 6개월 / 12개월 비용 차감 차이(%p)다. 대괄호는 명목 95% 이동블록 구간이다. 선택력에는 각 신호의 유효 매칭 날짜, 운용 비교에는 해당 신호의 기존·복제교체·복제 기준·ETF가 모두 관측된 날짜를 썼다.",""]
    lines += table(["시장","신호","선택/업종 배분","기존 방식−ETF","노출 유지 모사−ETF",
                    "주도주 기여 제외","반도체 주도기/2021 제외"],first)
    lines += [f"6개월 주 가설 44개 중 Holm 5%의 양의 우위는 {len(positives)}개, 검정 미측정은 {sum(x['status']=='미측정' for x in primary)}개였다. "
              + (", ".join(f"{r['market']} {r['name']} {r['comparison']} {pct(r['mean'])}%p (보정 p={r['holmP']:.3f})" for r in positives) if positives else "") + ".", "",
              "실제 ETF 전체 보유 비중으로 구성한 운용 성과는 두 시장 모두 자료로 판별 불가다. 한국 공식 자료는 설정·환매 바스켓이고 수집은 HTTP 429에서 중단됐다. 미국의 SEC 보고는 공개 시점이 확인된 과거 보유이지만 시차와 미매핑 종목이 남았다. 시총 대용치의 노출과 성과를 아래에서 평가한다.","",
              *verdicts(results),
              ("6개월 종목 선별 신호와 업종 배분에서 Holm 우위가 확인된 항목은 없었다." if not any(
                  row["comparison"] in ("선택력","업종 배분","선택력 차이") for row in positives) else
                  "6개월 종목 선별 신호와 업종 배분의 보정 결과는 위 통과 목록에 있다."),"",
              "미국 펀드 공시의 새 비교에 필요한 최소 입력은 `/workspace/batch-inputs/nport/round8/C2.pkl`이다. 파일이 없어 OW/OW_RESID는 미측정으로 남았다. SPY 개별 공시는 이 두 펀드 신호의 대체 자료로 쓸 수 없다.","",
              "## 자금 조달과 비용","",
              "기존 구성은 ETF 80%와 같은 선택 주식 20%다. 그 ETF의 업종·주도주 노출 중 20%가 비례해서 빠진다. 직접복제는 같은 선택 주식을 기존 지수 대용치 B에 얹고 같은 업종×주도주 그룹의 원 보유 비중에서 우선 자금을 뺀다. 셀 한도가 모자라면 남은 용량에 비례해 조달한다. 총 명목 교체액 20%를 유지하며 기존 보유와의 상계 후 실제 적극 매수 비중을 별도로 측정한다. F−ETF에서 F−B와 B−ETF를 분해해 복제 기준의 추적 차이와 자금 조달 효과를 볼 수 있다.","",
              "직접복제는 많은 종목의 주문이 필요하다. 한국 0~5개는 적극 선택 이름 수다. 실물 ETF와 같은 20% 주식만으로는 주식 슬리브가 ETF와 같은 노출인 날짜 외에 정확한 보존이 불가능하다. 모사의 종목 비용은 기존 연구의 매수·매도 및 한국 거래세를 적용했다. 매매의 세부 유동성·장중 가격은 기존 하네스의 범위에 따른다.","",
              "한국 대용치는 당시 양의 시총을 가진 Top120 전체다. 미국은 기존 가격 이력·CIK 적격 규칙·양의 시총을 충족한 구성원으로 금융·부동산을 포함한다. 미국 원 캐시의 공시 경과일 캐시와 초기 COR 신원 연결에 한계가 있다. 미국 FISV 한 가격 셀의 근거와 원본 불변 검산을 보존했다. [한국 입력 조사](KR-INVENTORY-ko.md) · [미국 입력 조사](US-INVENTORY-ko.md) · [FISV 정정](INPUT-REPAIR-FISV-ko.md)","",
              "## 전향 기록과 재실행","",
              "기존 전향 기록의 입력·영수증·기록기 6개 파일을 해시로 대조했다. 등록된 live 승인과 검증된 최신 입력이 없어 새 전향 관측은 0건이다. 기존 preview 7건은 별도 상태를 유지한다. [전향 상태](results/prospective-status.json)","",
              "```bash","PYTHON=/workspace/s2-venv/bin/python bash research/kr_us_exposure_preserving_v1/reproduce.sh","```","",
              "[전체 결과표](TABLES-ko.md) · [설계](DESIGN-ko.md) · [44개 주 가설과 12개월 보조](results/hypotheses.csv) · [검산](results/verification.json) · [검증 상태](VALIDATION.md)"]
    detail = ["# 전체 결과표","","단위는 %p 또는 %다. 수익 차이는 6/12개월 순서이며 95% 명목 구간을 함께 표시한다. L1은 절대 편차 합이다. 분모는 표별로 표시했다.",""]
    for market in ("KR","US"):
        folder = out/market
        detail += ["## "+market,"","### 선택력의 유효 표본과 매칭 실패",""]
        detail += matching_lines(market,results,folder)
        detail += ["### 동일 주식 비중의 자금 조달 비교",""]+portfolio_lines(market,results)
        detail += funding_increment_table(market,folder)
        detail += ["### 업종·주도주 비중 검산",""]+exposure_lines(folder)
        detail += ["### 운용 장부",""]+nav_lines(market,folder,list(results[market].get("horizons",{}).get("126",{}).get("portfolios",{})))
        detail += ["### 사후 민감도",""]+sensitivities(market,results)
    detail += ["## 복수 해시와 두 신호의 공통 날짜","","8개 해시 평균은 같은 날짜에 모든 해시 대조가 유효한 주의 평균이다. 반복 시드는 독립 관측으로 합치지 않았다.",""]
    seeds = []
    for name in results["KR"].get("horizons",{}).get("126",{}).get("selection",{}):
        if name.startswith("CONFIRM"):
            values = section_pair(results,"KR","selection",name)
            seeds.append([name,"/".join(str(s.get("n",0)) for s in values),both(values)])
    detail += table(["해시","n 6/12","선택력"],seeds)
    pairs = []
    for market in ("KR","US"):
        for name in PAIRS[market]:
            s = section_pair(results,market,"pairwise",name)
            pairs.append([market,name,"/".join(str(x.get("n",0)) for x in s),both(s)])
    detail += table(["시장","두 신호 선택력 차이","공통 n 6/12","차이"],pairs)
    detail += official_tables(out) + component_table(out) + qqq_table(results)
    detail += ["사후 종목 제외는 각 이름의 적극 비중 기여를 제거한다. 복제 기준의 기존 주도주 보유는 포함한다. 기간 제외는 해당 진입년 또는 원 보유 창 주도기 라벨을 제외한 날짜 비교다. 경제적 노출 표는 시작 목표 비중이며, 한국 운용 장부에서는 거래 불능 lock과 이후 가격 변화로 실현 비중이 달라진다.",""]
    detail += ["6개월 Holm 보정과 사용한 p는 [hypotheses.csv](results/hypotheses.csv)에 있다. 미측정은 가족 계산에서 p=1을 사용했다. 12개월은 보조다."]
    (HERE/"REPORT-ko.md").write_text("\n".join(lines)+"\n")
    (HERE/"TABLES-ko.md").write_text("\n".join(detail)+"\n")
    verification(out)


if __name__ == "__main__":
    main()
