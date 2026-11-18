"""Combine independent market runs, retain closed testing families and Korean tables."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess

import pandas as pd

from research.kr_us_strategy_batch_v1 import common as C

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / "results"
REG = json.loads((HERE / "registry.json").read_text())
KR_PRIMARY = [f"KR:S2:SLOT20:K{k}" for k in range(1, 6)] + [
    f"KR:S2:FIXED20:K{k}" for k in range(1, 6)] + ["KR:K2", "KR:MIX_PRE", "KR:MIX_EXP"]
US_PRIMARY = [f"US:{s}:Q{q}" for s in ("PRICE_CONFIRMED", "COCKTAIL", "U1")
              for q in ("020", "050", "100")] + ["US:NATIVE_COCKTAIL", "US:NATIVE_U1"]


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1, allow_nan=False) + "\n")


def pct(x, signed=True):
    if x is None:
        return "미측정"
    x = 0.0 if abs(x) < 1e-12 else x
    return f"{x * 100:{'+' if signed else ''}.2f}"


def number(x):
    return "미측정" if x is None else f"{x:.3f}"


def effect(s):
    s = s or {}
    ci = s.get("ci")
    interval = f" [{pct(ci[0])}, {pct(ci[1])}]" if ci is not None else " [구간 미측정]"
    return pct(s.get("mean")) + interval


def table(headers, rows):
    return ["|" + "|".join(headers) + "|", "|" + "|".join(["---"] * len(headers)) + "|"] + [
        "|" + "|".join(str(v).replace("|", "/").replace("\n", " ") for v in row) + "|" for row in rows]


def empty():
    return {"n": 0, "mean": None, "ci": None, "pOneSidedApprox": None}


def core_cell(summaries, h, claim):
    market = summaries.get(claim["market"], {})
    cell = market.get("coreComparisons", {}).get(str(h), {}).get(claim["id"], {})
    return cell.get("common", cell) or empty()


def fixed_cell(summaries, h, config, sample="common"):
    return summaries.get(config.split(":")[0], {}).get("fixed", {}).get(str(h), {}).get(config, {}).get(sample, empty())


def broad_cell(summaries, h, config):
    if ":WF_" in config:
        claim = next(c for c in REG["coreClaims"] if c["a"] == config and c["kind"] == "policy")
        return core_cell(summaries, h, claim)
    return fixed_cell(summaries, h, config)


def probability(s):
    return s.get("pOneSidedApprox", s.get("pOneSided"))


def make_families(summaries):
    core, broad = [], []
    for h in (126, 252):
        cells = {c["id"]: core_cell(summaries, h, c) for c in REG["coreClaims"]}
        adjusted = C.holm({k: probability(v) for k, v in cells.items()})
        for claim in REG["coreClaims"]:
            s = cells[claim["id"]]
            core.append({**claim, "horizon": h, "familySize": 41, "n": s.get("n", 0),
                         "mean": s.get("mean"), "ciLow": (s.get("ci") or [None, None])[0],
                         "ciHigh": (s.get("ci") or [None, None])[1], "pRawApprox": probability(s),
                         "pUsedInFamily": probability(s) if probability(s) is not None else 1,
                         "pHolm": adjusted[claim["id"]],
                         "role": "PRIMARY" if h == 126 else "SUPPORTIVE_SEPARATE_HOLM_NOT_NEW_PRIMARY"})
        cells = {k: broad_cell(summaries, h, k) for k in REG["broadEtfClaims"]}
        adjusted = C.holm({k: probability(v) for k, v in cells.items()})
        for k, s in cells.items():
            broad.append({"id": k, "horizon": h, "familySize": 115, "n": s.get("n", 0),
                          "mean": s.get("mean"), "ciLow": (s.get("ci") or [None, None])[0],
                          "ciHigh": (s.get("ci") or [None, None])[1], "pRawApprox": probability(s),
                          "pUsedInFamily": probability(s) if probability(s) is not None else 1,
                          "pHolm": adjusted[k], "sample": "POST_FIT_COMMON" if ":WF_" in k else "PORTFOLIO_COMMON"})
    pd.DataFrame(core).to_csv(OUT / "core-comparisons.csv", index=False)
    pd.DataFrame(broad).to_csv(OUT / "broad-etf-comparisons.csv", index=False)
    return core, broad


def ledger_cell(summaries, market, cadence, config, sample="full"):
    cell = summaries.get(market, {}).get("ledgers", {}).get(cadence, {}).get(config, {})
    return cell.get(sample, {}) or {}


def matching_coverage(market):
    path = OUT / market / "matching-audit.csv.gz"
    if not path.exists():
        return {}
    f = pd.read_csv(path)
    result = {}
    for selector, g in f.groupby("selector"):
        matched = g.reason.eq("MATCHED")
        groups = matched.groupby(g.date)
        weight = float(g.weight.sum())
        result[selector] = {"nonemptyDecisionWeeks": int(groups.ngroups),
                            "completeMatchWeeks": int(groups.all().sum()),
                            "fullBookMatchRate": float(groups.all().mean()),
                            "matchedLegWeightRate": float(g.loc[matched, "weight"].sum() / weight) if weight > 0 else None,
                            "legFailureCounts": g.loc[~matched, "reason"].value_counts().to_dict()}
    return result


def prospective():
    old = json.loads((ROOT / "research/kr_s2_rank_ladder_v1/results/prospective-status.json").read_text())
    checks = {}
    for p, sha in old["existingFilesSha256"].items():
        now = hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
        assert now == sha, p
        checks[p] = now
    result = {**old, "checkedOnKST": "2026-11-18", "comparisonBase": REG["baseCommit"],
              "existingFilesByteUnchanged": True, "existingFilesSha256": checks,
              "newLiveReceipts": 0,
              "currentInputBlockers": ["Latest loader carries old fundamentals/industry without post-pin DART filings",
                                        "Benchmark extension is VENDOR_YAHOO_UNVERIFIED",
                                        "Stock extension lacks post-2026-09-14 distributions",
                                        "Registered live recorder authorization remains None; past write windows cannot be backdated"],
              "parallelPath": "latest_inputs.py -> weekly_records.py -> prospective/recorder.py"}
    dump(OUT / "prospective-status.json", result)
    return result


def selection_rows(summaries, coverage, market):
    rows = []
    for s in REG["krSelectors" if market == "KR" else "usSelectors"]:
        cells = [summaries.get(market, {}).get("selection", {}).get(str(h), {}).get(s, {}) for h in (126, 252)]
        own = [v.get("own", empty()) for v in cells]
        common = [v.get("common", empty()) for v in cells]
        cov = coverage.get(market, {}).get(s, {})
        rows.append([s, f"{own[0].get('n', 0)}/{own[1].get('n', 0)}", effect(own[0]), effect(own[1]),
                     pct(cov.get("fullBookMatchRate"), False),
                     f"{common[0].get('n', 0)}/{common[1].get('n', 0)}",
                     effect(common[0]), effect(common[1])])
    return rows


def configuration_rows(summaries, market, ids):
    rows = []
    baseline = "KR:ETF" if market == "KR" else "US:SPY"
    for config in [baseline, *ids]:
        a, b = (fixed_cell(summaries, h, config) for h in (126, 252))
        l26, l52 = (ledger_cell(summaries, market, c, config) for c in ("L26", "L52"))
        rows.append([config, f"{a.get('n', 0)}/{b.get('n', 0)}", effect(a), effect(b),
                     pct(l26.get("cagr")), pct(l26.get("cagrGap")), pct(l26.get("mdd")),
                     pct(l52.get("cagrGap")), pct(l52.get("mdd")),
                     number(l26.get("oneWayTurnoverPerYear"))])
    return rows


def sensitivity_cell(summaries, market, h, config):
    s = summaries.get(market, {}).get("sensitivity", {}).get(str(h), {}).get(config, {})
    if market == "KR":
        return {"group": s.get("exNamedTwoWeightToETF", empty()),
                "exclude": s.get("excludeNamedTwoCohorts", empty()),
                "name": s.get("maxContributorTickerPostHoc"),
                "exName": s.get("exMaxContributorWeightToETFPostHoc", empty()),
                "year": s.get("maxEntryYearPostHoc"),
                "exYear": s.get("excludeMaxEntryYearPostHoc", empty()),
                "share": s.get("namedTwoShareOfSignedTotal")}
    return {"group": s.get("fixedMegaWeightsReturnedToETF", empty()),
            "exclude": s.get("excludeDirectMegaCohorts", empty()),
            "name": s.get("postHocMaximumTicker"),
            "exName": s.get("maximumTickerWeightsReturnedToETF", empty()),
            "year": s.get("postHocMaximumEntryYear"),
            "exYear": s.get("excludeMaximumEntryYear", empty()),
            "share": s.get("fixedMegaSignedShareOfTotal")}


def sensitivity_rows(summaries, market, ids):
    rows = []
    for config in ids:
        for h in (126, 252):
            s = sensitivity_cell(summaries, market, h, config)
            rows.append([config, "6" if h == 126 else "12", pct(s["share"], False),
                         effect(s["group"]), f"{s['exclude'].get('n', 0)}: {effect(s['exclude'])}",
                         s["name"] or "미측정", effect(s["exName"]), s["year"] or "미측정",
                         effect(s["exYear"])])
    return rows


def policies_rows(summaries):
    rows = []
    for config in REG["policies"]:
        market = config.split(":")[0]
        claims = [next(c for c in REG["coreClaims"] if c["a"] == config and c["kind"] == "policy")]
        a, b = (core_cell(summaries, h, claims[0]) for h in (126, 252))
        fits = summaries.get(market, {}).get("policy", {}).get(config, {}).get("fits", [])
        if market == "KR":
            path = OUT / "KR" / f"policy-fits-{config.split(':')[-1]}.json"
            fits = json.loads(path.read_text()) if path.exists() else []
        choices = ", ".join(f"{f['year']}:{f['chosen']}" for f in fits)
        l26, l52 = (ledger_cell(summaries, market, c, config, "postWarmup") for c in ("L26", "L52"))
        rows.append([config, f"{a.get('n', 0)}/{b.get('n', 0)}", effect(a), effect(b),
                     pct(l26.get("cagrGap")), pct(l26.get("mdd")),
                     pct(l52.get("cagrGap")), pct(l52.get("mdd")), choices or "미측정"])
    return rows


def ledger_evidence(summaries):
    evidence = {}
    for config in REG["broadEtfClaims"]:
        market = config.split(":")[0]
        cells = [ledger_cell(summaries, market, c, config) for c in ("L26", "L52")]
        ready = all(s.get("cagrGap") is not None and s.get("mdd") is not None for s in cells)
        clean = ready and all(s.get("turnoverDiagnostic", {}).get("eligibleForRiskImprovementClaim", True) for s in cells)
        evidence[config] = {
            "bothLedgersMeasured": ready, "noUnresolvedTerminalZero": bool(clean),
            "bothCagrGapsPositive": bool(clean and all(s["cagrGap"] > 0 for s in cells)),
            "bothMddNotWorse": bool(clean and all(s["mdd"] >= s["etfMdd"] - 1e-12 for s in cells)),
            "bothMddStrictlyImproved": bool(clean and all(s["mdd"] > s["etfMdd"] + 1e-12 for s in cells)),
            "operationalPromotion": False}
    return evidence


def market_progress(summaries):
    result = {}
    for market in ("KR", "US"):
        s = summaries.get(market)
        if s is None:
            result[market] = {"status": "UNAVAILABLE", "available": False}
            continue
        fixed = s["fixed"]["126"]
        ids = [k for k in REG["broadEtfClaims"] if k.startswith(market + ":") and "common" in fixed.get(k, {})]
        expected = len(ids) + 1
        attempted = {c: len(s.get("ledgers", {}).get(c, {})) for c in ("L26", "L52")}
        measured = {c: sum("full" in x for x in s.get("ledgers", {}).get(c, {}).values()) for c in attempted}
        complete = all(n == expected for n in attempted.values())
        result[market] = {"available": True, "expectedBooksPerCadenceIncludingETF": expected,
                          "attempted": attempted, "measured": measured,
                          "status": "COMPLETE" if complete and measured == attempted else (
                              "COMPLETE_WITH_NOT_ESTIMABLE_BOOKS" if complete else "FIXED_COMPLETE_LEDGERS_PENDING")}
    return result


def ledger_detail_rows(summaries, market):
    rows = []
    for cadence, by in summaries.get(market, {}).get("ledgers", {}).items():
        for config, item in by.items():
            s = item.get("full", {})
            diag = s.get("turnoverDiagnostic", {})
            state = diag.get("navBasisStatus", s.get("status", item.get("status", "MEASURED")))
            rows.append([config, cadence, pct(s.get("cagrGap")), pct(s.get("annualArithmeticDailyGap")),
                         pct(s.get("compoundingRemainder")), number(s.get("oneWayTurnoverPerYear")),
                         pct(s.get("costPerYear"), False),
                         number(diag.get("nameReplacementShare", s.get("namesReplacedPerYear"))),
                         number(diag.get("meanRetainedAssetL1ResetApprox", s.get("carriedWeightRetargetPerYear"))), state])
    return rows


def write_tables(summaries, coverage, core, broad):
    lines = ["# 전체 결과표", "", "수익·차이는 % 또는 %p, 회전율은 편도/년. 6·12개월은 연율화하지 않은 보유기간 수익 차이. 대괄호는 명목 95% paired 이동 블록 구간. 공통 표본은 시장별이며 두 시장 날짜를 합치지 않는다.", ""]
    for market in ("KR", "US"):
        lines += [f"## {market} 신호 선택력", ""]
        lines += table(["신호", "own n 6/12", "own 6개월", "own 12개월", "판단일 전체 매칭률%", "공통 n 6/12", "공통 6개월", "공통 12개월"],
                       selection_rows(summaries, coverage, market)) + [""]
        lines += ["선택력은 주식20%·ETF80%에서 동일 업종·시총의 종목으로 모든 주식 leg를 바꾼 차이. own은 신호별 실제 매칭된 날짜, 공통은 준비된 모든 신호의 매칭이 성공한 날짜다. 전체 매칭률의 분모는 미만기 주를 포함한 비어 있지 않은 판단일이다. 미확보 공시 둘은 공통 교집합에서 제외하지만 검정 가족의 p=1 슬롯은 유지한다.", "",
                  f"## {market} 실행 후보 전체 — ETF 대비", ""]
        ids = [k for k in REG["broadEtfClaims"] if k.startswith(market + ":")]
        lines += table(["구성", "공통 n6/12", "6개월", "12개월", "L26 CAGR%", "L26 CAGR차%p", "L26 MDD%", "L52 CAGR차%p", "L52 MDD%", "L26 회전율"],
                       configuration_rows(summaries, market, ids)) + [""]
        lines += [f"## {market} 주도주·최대 기여 이름/년 민감도 — 모든 후보", ""]
        lines += table(["구성", "개월", "주도주/서명합%", "주도주 비중→ETF", "주도주 보유창 제외 n:차이", "사후 최대 이름", "최대 이름→ETF", "사후 최대 진입년", "그 해 제외"],
                       sensitivity_rows(summaries, market, ids)) + [""]
        lines += [f"## {market} 운용 차이의 산술·복리 분해와 비용", ""]
        lines += table(["구성", "장부", "CAGR차%p", "일수익차 연율%p", "복리잔여%p", "편도회전/년", "비용%/년", "이름 교체", "유지자산 재설정", "상태"],
                       ledger_detail_rows(summaries, market)) + [""]
        lines += ["한국 이름 교체는 이전 보유 이름 중 이탈 비율, 유지자산 재설정은 평균 L1 근사다. 미국은 계정당 이름 교체 횟수/년과 유지자산 목표 비중 변화/년이다. 단위가 다르므로 시장 간 크기를 직접 비교하지 않는다. 실제 거래비용의 가산 분해가 아니다.", ""]
    lines += ["## 핵심 비교 41개와 Holm", "", "6개월이 사전 고정 주 검정이다. 12개월은 같은 크기 가족의 보조 보정이며 별도의 새 주 주장으로 해석하지 않는다. 미측정 p는 가족 안에서 1이다.", ""]
    rows = []
    for row in core:
        s = {"mean": row["mean"], "ci": [row["ciLow"], row["ciHigh"]] if row["ciLow"] is not None else None}
        rows.append([row["id"], row["horizon"], row["n"], effect(s), number(row["pRawApprox"]), number(row["pHolm"])])
    lines += table(["주장", "세션", "n", "차이", "근사 p", "Holm(41)"], rows) + ["", "## 연간 만기 자료 규칙", ""]
    lines += table(["규칙", "post-fit n6/12", "6개월", "12개월", "L26 post CAGR차", "L26 post MDD", "L52 post CAGR차", "L52 post MDD", "연도별 선택"], policies_rows(summaries))
    lines += ["", "post 창은 기존 보유·계정을 이어받은 재기준 창이다. 고정 후보의 동일 창 결과와 전 후보 fit 점수는 시장 summary/policy-fits 및 NAV 파일에 보존한다.", "", "115개 broad ETF 검정 전체 원 p·보정 p: [broad-etf-comparisons.csv](results/broad-etf-comparisons.csv). 입력 없음/가격 미해결/작은 표본은 0 수익으로 채우지 않는다."]
    (HERE / "TABLES-ko.md").write_text("\n".join(lines) + "\n")


def manifest():
    files = {}
    for path in sorted(OUT.rglob("*")):
        if path.is_file() and "ledger-cache" not in path.parts and path.name not in ("artifact-manifest.json", "verification.json"):
            files[str(path.relative_to(HERE))] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}
    dump(OUT / "artifact-manifest.json", files)


def provenance(summaries):
    changed = subprocess.check_output(["git", "diff", "--name-only", REG["baseCommit"]], cwd=ROOT, text=True).splitlines()
    assert all(p.startswith(("research/kr_us_strategy_batch_v1/", "tests/test_kr_us_batch_")) for p in changed)
    code = [*HERE.glob("*.py"), *HERE.glob("*.sh"), HERE / "registry.json", HERE / "DESIGN-ko.md", HERE / "INPUT-REPAIR-ko.md"]
    anchors = ["pipeline/us_decision_pilot.py", "research/us_selection_value_v1/features.py",
               "research/us_selection_value_v1/evaluate.py", "research/us_selection_value_v1/cocktail.py",
               "research/us_selection_value_v1/fetch_as_traded.py", "research/followup_round8_v1/kr_switch.py",
               "research/kr_s2_rank_ladder_v1/run.py", "research/alpha_search_round6_v1/kr.py",
               "research/alpha_search_round6_v1/us.py"]
    value = {"generatedAtUTC": datetime.now(timezone.utc).isoformat(),
             "codeGitHead": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
             "sourceBase": REG["baseCommit"], "designCommit": "e6786ee", "inputRepairCommit": "4710738",
             "codeSha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in code},
             "reusedSourceCodeSha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in anchors},
             "priorResearchAndProductionTrackedFilesUnchanged": True,
             "marketProgress": market_progress(summaries),
             "dataPurchasePerformed": False, "operationalPromotion": False,
             "krInputIdentity": summaries.get("KR", {}).get("inputs", {}).get("identity"),
             "usInputVintage": summaries.get("US", {}).get("inputPreparation", {}).get("status"),
             "commands": {"all": "bash research/kr_us_strategy_batch_v1/reproduce.sh all",
                          "existingInputs": "bash research/kr_us_strategy_batch_v1/reproduce.sh compute",
                          "tablesAndVerification": "bash research/kr_us_strategy_batch_v1/reproduce.sh report"}}
    dump(OUT / "provenance.json", value)


def main():
    OUT.mkdir(exist_ok=True)
    summaries = {m: json.loads((OUT / m / "summary.json").read_text()) for m in ("KR", "US") if (OUT / m / "summary.json").exists()}
    if not summaries:
        raise ValueError("no completed market output")
    core, broad = make_families(summaries)
    coverage = {m: matching_coverage(m) for m in summaries}
    status = prospective()
    evidence = ledger_evidence(summaries)
    combined = {"designCommit": "e6786ee", "sourceBase": REG["baseCommit"], "label": REG["label"],
                "markets": market_progress(summaries),
                "core": core, "broad": broad, "matchingCoverage": coverage,
                "prospective": status, "ledgerEvidence": evidence, "coreFamilySize": 41, "broadFamilySize": 115}
    dump(OUT / "integrated.json", combined)
    write_tables(summaries, coverage, core, broad)
    from research.kr_us_strategy_batch_v1 import supplement
    supplement.run()
    from research.kr_us_strategy_batch_v1 import presentation
    presentation.write(summaries, coverage, core, broad, evidence)
    provenance(summaries)
    manifest()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    print(json.dumps({"completedMarkets": list(summaries), "coreRows": len(core), "broadRows": len(broad), "codeHead": head}))


if __name__ == "__main__":
    main()
