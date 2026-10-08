"""kr-alpha-atlas Phase B — assemble the machine-readable readiness report, the Phase C eligibility manifest and the Korean summary from a matrix.

Pure over (matrix, registry, supporting facts): no I/O except the code-identity hashing. Nothing here evaluates a return; the verdicts are counts of measured cells.
"""
from __future__ import annotations

from pathlib import Path

from . import kr_alpha_atlas_catalogue as C
from . import kr_alpha_atlas_readiness as RD

CONTRACT = "KR_ALPHA_ATLAS_PHASE_B_REPORT_V1"
ROOT = Path(__file__).resolve().parents[1]
CODE_FILES = ("pipeline/kr_alpha_atlas_bars.py", "pipeline/kr_alpha_atlas_catalogue.py", "pipeline/kr_alpha_atlas_inputs.py", "pipeline/kr_alpha_atlas_matrix.py",
              "pipeline/kr_alpha_atlas_readiness.py", "pipeline/kr_alpha_atlas_feasibility.py", "pipeline/kr_alpha_atlas_report.py", "pipeline/kr_alpha_atlas_dry_run.py",
              "scripts/build_kr_alpha_atlas_phase_b.py")
REGISTRY_PATH = "research_specs/kr-alpha-atlas-registry-v1.json"
CONSTRUCTION_ROLES = ("RISK_CONSTRUCTION", "COST_CAPACITY", "ELIGIBILITY_FILTER")


HUMAN_STEPS = [
    {"id": "OFFICIAL_TRADED_VALUE_RERUN", "required": "ONLY_IF_THE_PHASE_C_REGISTRATION_CHOOSES_OFFICIAL_ACC_TRDVAL",
     "why": "traded value in this report is the as-traded close x volume proxy; the official KRX ACC_TRDVAL exists only in the preserved raw-input artifact",
     "how": ["download the Actions artifact kr-model-raw-inputs-36844599518 (artifact id 11157875265, archive sha256 42eeb18b7a5c88816629036f472a93057b6a9be4768ad47292ba0d2750b4cce7, run 36844599518) "
             "and extract it to an empty directory <ART>",
             "python scripts/build_kr_alpha_atlas_phase_b.py --scratch <ART>   (the loader finds market/ and uses the official values; the git-pinned files it verifies are identical)",
             "compare tradingValueBasis and the matrix digest in the new report with this one; commit the new outputs as a separate revision, never over this one silently"],
     "blockedHere": "the authoring sandbox cannot reach the Actions artifact blob host (CONNECT 403); no official value was read"},
    {"id": "OPTIONAL_REPROBE_INVESTOR_FLOW", "required": "NO",
     "why": "latest evidence (signal-history manifest, 2026-09-24) is REFUSED: HTTP 400 LOGOUT with 0 records; it is sufficient, so none was repeated",
     "how": ["Actions > Probes > Run workflow: probe=kr-investor-flow, args empty (https://github.com/jaehojung1879-netizen/Investment/actions/workflows/probes.yml)",
             "anything other than SERVED leaves G01-G05 SOURCE_BLOCKED; at most ONE re-probe per source in Phase B"]},
    {"id": "OPTIONAL_REPROBE_SHORT_SELLING", "required": "NO", "why": "same as above for KRX short-selling statistics",
     "how": ["Actions > Probes > Run workflow: probe=kr-short-selling, args empty"]},
]


def code_identity(root=ROOT):
    return {f: RD.file_sha256(Path(root) / f) for f in CODE_FILES if (Path(root) / f).exists()}


def assemble(matrix, registry, *, cutoff, universe, sources, termination, benchmark, input_audit=None, root=ROOT):
    features = RD.build_features_report(matrix, registry, cutoff)
    families = RD.family_summary(features, registry)
    interactions = RD.interaction_readiness(matrix, registry, features)
    baselines = RD.baseline_readiness(registry, features, matrix)
    recommendation = RD.recommendation(families)
    pit = RD.pit_checks(matrix)
    ready = [r for r in features.values() if r["measuredStatus"] == "MEASURED_READY"]
    eligible = [r for r in ready if r["role"] == "ALPHA_CANDIDATE" and r["registryReadinessStatus"] != "ALREADY_TESTED"]
    dates = sorted(matrix.rows.date.unique())
    horizons = {"H%d" % h: RD.last_maturable_signal_date(dates, h, cutoff) for h in (21, 63, 126, 252)}
    measured_ids = [f for f, r in features.items() if r["implementation"] in ("IMPLEMENTED", "COMPUTED_ALREADY_TESTED")]
    identity = {
        "registrySha256": RD.file_sha256(Path(root) / REGISTRY_PATH), "registryId": registry["registryId"], "inputs": matrix.identity, "matrixDigest": matrix.digest(),
        "catalogueSha256": RD.digest({k: v for k, v in C.CATALOGUE.items()}), "codeFileSha256": code_identity(root), "rules": RD.RULES,
        "tradingValueBasis": universe.get("_tradingValueBasis")}
    b08 = features["B08_valueBusinessConfirmation"]
    revisions = [{"id": "B08_DENOMINATOR_IS_THE_H2_CONTRACTS_OWN_ELIGIBLE_SET", "madeBefore": "any return was read; no outcome exists in this change",
                  "what": "the first full run measured B08 on every PIT member-date and read %s%% within its usable range (below the 60%% floor). B08 is a state defined only on names the sealed H2 "
                          "contract does not itself exclude (preferred share, untraded, below the liquidity floor, unclassified industry), so those exclusions are definitional, not data gaps. The "
                          "denominator was changed to that eligible set for B08 and for the X1 interaction only; every other feature and interaction keeps the all-member-rows denominator" % b08.get(
                              "coverageAllMemberRowsWithinUsableRangePct"),
                  "after": {"coverageWithinUsableRangePct": b08["coverageWithinUsableRangePct"], "status": b08["measuredStatus"]},
                  "disclosed": "both figures are published; the correction was decided on the definition, and a reader who prefers the all-member denominator can read it directly"}]
    report = {
        "contract": CONTRACT, "preOutcomeRevisions": revisions, "phase": "KR_ALPHA_ATLAS_PHASE_B", "evidenceClass": "OUTCOME_BLIND_DATA_READINESS", "outcomeAccess": "NONE",
        "statement": "Counts of measured point-in-time cells. Nothing here is a relationship to a return, and READY means 'enough data to attempt the registered comparison', never 'alpha'.",
        "identity": identity, "cutoff": cutoff,
        "matrix": {"grain": ["date", "ticker"], "dates": len(dates), "firstDate": dates[0], "lastDate": dates[-1], "memberDates": int(len(matrix.rows)),
                   "distinctTickers": int(matrix.rows.ticker.nunique()), "featureColumns": len(matrix.values.columns),
                   "lastMaturableSignalDate": horizons,
                   "labelWindowAssumption": "entry the session after the signal, exit H sessions after entry (replay_calendar.schedule convention)"},
        "inputAudit": input_audit or {}, "pitChecks": pit, "reasonChecks": RD.reason_checks(matrix), "universeCoverageByYear": _universe_by_year(matrix),
        "families": families, "features": features, "interactions": interactions, "baselines": baselines, "recommendation": recommendation,
        "overlap": RD.overlap_matrix(matrix, sorted(r["featureId"] for r in ready if r["role"] != "COST_CAPACITY")),
        "dateContextSummary": _context_summary(matrix),
    }
    manifest = {
        "contract": "KR_ALPHA_ATLAS_PHASE_C_ELIGIBILITY_MANIFEST_V1", "status": "OUTCOME_BLIND_MANIFEST_NOT_A_PREREGISTRATION",
        "statement": "Inputs the Phase C registration may pin. No feature was selected using a return; the eligible list is the set that cleared the declared coverage gates.",
        "recommendation": recommendation, "identity": identity, "preOutcomeRevisions": revisions,
        "referenceUniverse": {"universeId": "PIT_KRX_TOP120", "source": "KRX sto/stk_bydd_trd monthly snapshot strictly older than the signal date", "weeklyDates": len(dates),
                              "memberDates": int(len(matrix.rows)), "firstDate": dates[0], "lastDate": dates[-1], "broaderUniverse": universe["verdict"]},
        "eligibleDateRange": {"matrix": [dates[0], dates[-1]], "developmentCutoff": cutoff, "lastMaturableSignalDate": horizons,
                              "perFeatureUsableRanges": "see eligibleFeatures[*].usableRange; the Phase C registration freezes one range per comparison, never one global window"},
        "horizons": {fam: {"primary": registry["families"][fam]["primaryHorizon"], "secondary": registry["families"][fam]["secondaryHorizon"]} for fam in registry["families"]},
        "eligibleFeatures": [_eligible_entry(r) for r in sorted(eligible, key=lambda r: r["featureId"])],
        "baselineAndControlFeatures": sorted(r["featureId"] for r in features.values() if r["registryReadinessStatus"] == "ALREADY_TESTED"
                                             and r["measuredStatus"] == "ALREADY_TESTED_COMPUTED_READY"),
        "contextConditioningFeatures": sorted(r["featureId"] for r in ready if r["role"] == "CONTEXT_CONDITIONING"),
        "constructionAndEligibilityFeatures": {r["featureId"]: r["role"] for r in sorted(ready, key=lambda r: r["featureId"]) if r["role"] in CONSTRUCTION_ROLES},
        "excludedFeatures": [{"featureId": r["featureId"], "measuredStatus": r["measuredStatus"], "reason": r.get("notComputedReason") or _below_floor(r)}
                             for r in sorted(features.values(), key=lambda r: r["featureId"])
                             if r["measuredStatus"] not in ("MEASURED_READY", "ALREADY_TESTED_COMPUTED_READY", "REFERENCED_ALREADY_TESTED")],
        "baselines": {k: {"status": v["status"], "membersBelowFloor": v["membersBelowFloor"]} for k, v in baselines.items()},
        "interactions": {k: {"status": v["status"], "reason": v["reason"], "evaluableDates": v.get("evaluableDates"), "jointCoveragePct": v.get("jointCoveragePct"),
                             "evaluableRange": v.get("evaluableRange"), "thin": v.get("thin")} for k, v in interactions.items()},
        "sourceBlockers": [{"features": s["features"], "status": s["status"]} for s in sources["sources"]],
        "terminalEventRisks": termination, "benchmark": benchmark,
        "alreadyTestedPolicy": "ALREADY_TESTED features keep their sealed study references and are never re-run; those computed here enter Level 2 only as baselines or controls",
        "prerequisitesBeforePhaseC": _prerequisites(recommendation, universe, interactions, features),
        "humanTriggeredAcquisition": HUMAN_STEPS, "knownLimitations": KNOWN_LIMITATIONS,
        "computedFeatureCount": len(measured_ids),
    }
    return report, manifest


KNOWN_LIMITATIONS = [
    "EVERY KOREAN DATE IS OUTCOME-EXPOSED DEVELOPMENT HISTORY (through 2026-09-14): whatever Phase C finds is EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY, never confirmation",
    "UNIVERSE: the PIT Top120 by monthly KRX market-cap snapshot strictly older than the signal date; the 22 securities that terminated inside it have unresolved terminal economics, so a label for a held terminating name cannot be valued (the Phase C registration must declare how it is withheld)",
    "INDUSTRY LABELS ARE RECONSTRUCTED (PIT_RECONSTRUCTED_MEMBERSHIP): current KRX/KIND anchors plus verified change events, not vendor-historical labels; 22 terminated names are unclassified; an industry cohort needs >= 5 classified members",
    "PRICE PANEL: replay-v16 closes are split-continuous and dividend-forward-accumulated, built with the listed-share count's LATER confirmation of each split; windows touching a split not confirmed at the signal date are masked here, but the panel is not itself a signal-date reproduction",
    "TRADED VALUE IS A PROXY (as-traded close x volume) because the official KRX ACC_TRDVAL exists only in the preserved raw-input artifact; the difference (closing price against the session's volume-weighted price) was not measured",
    "DART ACCOUNTING IS DARK 2013-2015 and mostly 2016 (DART serves from 2015 and the TTM roll-forward needs prior-year quarters), covers 250 collected tickers, and financials rarely state revenue or operating income, which is why margin, cash-conversion and capex-intensity features sit below the floor",
    "DART ACCOUNTING VISIBILITY: a filing is visible on the day AFTER its receipt date; a restatement arrives as its own filing; an amendment served in place of an original (27.6% of the sealed store by an earlier audit) is PIT-honest and costs coverage",
    "BENCHMARK 069500.KS is reproducible but its external reconciliation is unresolved (BENCHMARK_EXTERNAL_RECONCILIATION_UNRESOLVED); no corrected benchmark was built and none was changed",
    "THE READINESS THRESHOLDS ARE GATES, NOT TESTS: 60% coverage and 30 names per date are inherited; 52 evaluable dates and 3 names per 2x2 corner are introduced here and stated as such",
]


def _below_floor(r):
    if r["measuredStatus"].endswith("BELOW_COVERAGE_FLOOR"):
        top = sorted(r["missingness"].items(), key=lambda kv: -kv[1])[:3]
        return "measured on %s%% of rows within its usable range over %d usable dates; main missingness: %s" % (
            r.get("coverageWithinUsableRangePct"), r["usableSignalDates"], ", ".join("%s=%d" % kv for kv in top))
    return r.get("blockingReason")


def _eligible_entry(r):
    return {"featureId": r["featureId"], "family": r["family"], "registeredHorizons": r["registeredHorizons"], "coveragePct": r["coveragePct"],
            "coverageWithinUsableRangePct": r["coverageWithinUsableRangePct"], "usableRange": [r["earliestUsableSignalDate"], r["latestUsableSignalDate"]],
            "usableSignalDates": r["usableSignalDates"], "usableYears": r["usableYears"],
            "horizonUsability": r["horizonUsability"], "pitSafetyVerdict": r["pitSafetyVerdict"]}


def _universe_by_year(matrix):
    rows = matrix.rows
    out = {}
    for year, g in rows.groupby(rows.date.str[:4]):
        out[year] = {"dates": int(g.date.nunique()), "memberDates": int(len(g)), "tradableAtSignalPct": RD._round(100.0 * g.tradableAtSignal.mean()),
                     "industryClassifiedPct": RD._round(100.0 * g.industry.notna().mean()), "industryCohortEligiblePct": RD._round(100.0 * g.industryEligible.mean()),
                     "preferredSharePct": RD._round(100.0 * g.isPreferredShare.fillna(False).astype(bool).mean())}
    return out


def _context_summary(matrix):
    ctx = matrix.date_context
    return {"industriesEligible": RD._dist(ctx.industriesEligible), "industriesWithRelMom": RD._dist(ctx.industriesWithRelMom),
            "breadthMeasuredNames": RD._dist(ctx.breadthMeasured), "datesWithAdverseMarketState": int((ctx.trendAdverse.eq(True) | ctx.volAdverse.eq(True)).sum())}


def _prerequisites(recommendation, universe, interactions, features):
    steps = []
    if recommendation["verdict"] == "PROCEED_TO_PHASE_C_PREREGISTRATION":
        steps.append("Phase C registration PR: freeze this manifest's identity, the eligible list, baselines B0-B4, horizons, Level 1-3 statistics, costs and verdict table BEFORE any outcome (docs/kr-alpha-atlas-methodology.md section 9)")
    else:
        steps.append("Phase C is formally BLOCKED; write Phase D from this report alone")
    steps.append("decide, before registering, whether the evaluation runs on the close x volume traded-value proxy used here or on the official KRX ACC_TRDVAL held only in the preserved raw-input artifact; the "
                 "choice is frozen in the registration, never made after a result")
    steps.append("build the label engine and the date-balanced baseline model OUTSIDE the sealed closures (the same arrangement alpha-opportunity-model-v4/v5 used); none exists yet")
    blocked = [k for k, v in interactions.items() if v["status"] != "READY"]
    if blocked:
        steps.append("interactions not READY are reported BLOCKED or INSUFFICIENT_COVERAGE in the evaluation, not repaired: " + ", ".join(blocked))
    return steps


# --------------------------------------------------------------------------- #
# Korean summary, rendered from the report so the two cannot disagree
# --------------------------------------------------------------------------- #
STATUS_KO = {"MEASURED_READY": "측정 완료·사용 가능", "MEASURED_BELOW_COVERAGE_FLOOR": "측정했으나 기준 미달", "ALREADY_TESTED_COMPUTED_READY": "기존 검증·비교용 계산",
             "ALREADY_TESTED_COMPUTED_BELOW_COVERAGE_FLOOR": "기존 검증·비교용(기준 미달)", "REFERENCED_ALREADY_TESTED": "기존 검증 결과만 인용",
             "NOT_COMPUTED_DATA_BUILD_REQUIRED": "데이터 구축 필요", "NOT_COMPUTED_SOURCE_BLOCKED": "출처 차단", "NOT_COMPUTED_PIT_UNSAFE": "시점 안전성 없음",
             "NOT_COMPUTED_NOT_FEASIBLE": "구할 수 없음", "NOT_A_MATRIX_COLUMN": "종목·날짜 단위 아님", "NOT_COMPUTED_OTHER": "계산 안 함"}
FAMILY_KO = {"A": "가격·모멘텀·반전", "B": "가치", "C": "수익성·회계 품질", "D": "거래량·거래 활동", "E": "유동성·미시구조", "F": "위험 특성", "G": "투자자 수급·지분",
             "H": "산업·횡단면 구조", "I": "거시·환율·글로벌", "J": "이벤트·대체 정보"}
SOURCE_KO = {"SOURCE_BLOCKED": "출처가 막혀 있어 계산하지 않았고, 다른 지표로 대체하지 않습니다.",
             "PIT_SAFE_BUT_HISTORY_TOO_SHORT": "시점은 안전하지만 제공 기간이 2024-09부터라 과거 평가가 불가능하고, '행 없음'이 '공시 없음'을 뜻하지 않아 0으로 읽을 수 없습니다. 앞으로 쌓아 가는 대상입니다.",
             "DATA_BUILD_REQUIRED": "수집·구축이 더 필요해 이번에 계산하지 않았습니다.",
             "SOURCE_AVAILABLE_NOT_COMPUTED": "저장소에 날짜가 붙은 정책금리 파일이 있어 시점 안전하게 만들 수 있지만, 등록된 비교가 읽지 않아 계산하지 않았습니다(정책금리 대용치이며 투자 가능한 금리가 아닙니다).",
             "PIT_UNSAFE": "수정된 값만 제공되거나 공표 시각이 확정되지 않아 시점 안전하지 않습니다.",
             "NOT_FEASIBLE": "시점 기준으로 쓸 수 있는 출처가 없습니다."}
INTERACTION_KO = {"READY": "준비됨", "INSUFFICIENT_COVERAGE": "표본 부족", "SOURCE_BLOCKED": "출처 차단", "PIT_UNSAFE": "시점 안전성 없음"}


def render_summary_ko(report, manifest, universe, sources):
    f = report["features"]
    fam = report["families"]
    m = report["matrix"]
    rec = report["recommendation"]
    lines = ["# 한국 주식 알파 아틀라스 — Phase B 데이터 준비 보고서", "",
             "**이 문서는 데이터가 충분한지만 말합니다. 어떤 특성이 수익을 예측하는지는 전혀 계산하지 않았고(미래 수익률·라벨·모형 학습 없음), 투자 판단이나 매매도 바꾸지 않았습니다.**",
             "기계 판독용 원본은 `docs/results/kr-alpha-atlas-phase-b-readiness.json`이며, 이 문서는 그 파일에서 자동으로 만들어집니다.", "",
             "## 한눈에 보기", "",
             "- 판정: **%s** — %s" % (
                 "Phase C 사전등록으로 진행 가능" if rec["verdict"] == "PROCEED_TO_PHASE_C_PREREGISTRATION" else "등록된 차단 경로(BLOCKED)",
                 "알파 후보가 행의 %.0f%% 이상에서 측정되고 평가 가능한 주가 %d주 이상인 정보군이 %d개(%s)입니다." % (100 * RD.MIN_FEATURE_COVERAGE, RD.MIN_EVALUABLE_DATES,
                                                                                       len(rec["familiesWithUsableReadyFeature"]), ", ".join(rec["familiesWithUsableReadyFeature"]))
                 if rec["verdict"] == "PROCEED_TO_PHASE_C_PREREGISTRATION" else "사용 가능한 정보군이 2개 미만이라 Phase C는 공식적으로 차단되고, Phase D는 이 보고서만으로 씁니다."),
             "- 기준 유니버스: 시점 기준 KRX 시가총액 상위 120종목, 매주 신호일 %d개(%s ~ %s), 종목·날짜 %s건, 서로 다른 종목 %d개." % (
                 m["dates"], m["firstDate"], m["lastDate"], format(m["memberDates"], ","), m["distinctTickers"]),
             "- 계산한 특성 %d개 / 등록 %d개. 나머지는 이유와 함께 아래에 기록했습니다." % (m["featureColumns"], len(f)),
             "- 시점(PIT) 점검: 공시가 신호일 이전에 공개된 칸 %s개를 검사했고 위반 %d건, 유니버스 스냅샷 위반 %d건 — %s." % (
                 format(report["pitChecks"]["filingBasedCellsChecked"], ","), report["pitChecks"]["availableFromNotBeforeSignalDate"],
                 report["pitChecks"]["membershipSnapshotNotOlderThanSignalDate"], "통과" if report["pitChecks"]["pass"] else "실패"),
             "- 거래대금은 **%s** 입니다(공식 KRX 거래대금 파일은 Actions 산출물에만 있어 이 환경에서 읽지 못했습니다)." % (
                 "종가×거래량 대용치" if "PROXY" in (report["identity"].get("tradingValueBasis") or "") else "공식 KRX 거래대금"), "",
             "## 상태 구분 (코드 구현 / 실제 데이터로 검증 / 미달 / 차단)", "",
             "- **실제 데이터로 측정 완료·사용 가능** (코드 구현됨 + 실제 입력으로 계산, 커버리지 기준 통과): " + ", ".join(sorted(k for k, r in f.items() if r["measuredStatus"] in ("MEASURED_READY", "ALREADY_TESTED_COMPUTED_READY"))),
             "- **코드는 구현됐지만 커버리지 기준 미달 (NOT_READY)**: " + (", ".join("%s(%s%%)" % (k, r["coverageWithinUsableRangePct"]) for k, r in sorted(f.items()) if r["measuredStatus"].endswith("BELOW_COVERAGE_FLOOR")) or "없음"),
             "- **출처 차단 (SOURCE_BLOCKED)**: " + ", ".join(sorted(k for k, r in f.items() if r["measuredStatus"] == "NOT_COMPUTED_SOURCE_BLOCKED")),
             "- **시점 안전성 없음 (PIT_UNSAFE)**: " + ", ".join(sorted(k for k, r in f.items() if r["measuredStatus"] == "NOT_COMPUTED_PIT_UNSAFE")),
             "- **데이터 구축 필요 / 구할 수 없음**: " + ", ".join(sorted(k for k, r in f.items() if r["measuredStatus"] in ("NOT_COMPUTED_DATA_BUILD_REQUIRED", "NOT_COMPUTED_NOT_FEASIBLE"))),
             "- **기존 연구 결과만 인용(재계산 안 함)**: " + ", ".join(sorted(k for k, r in f.items() if r["measuredStatus"] == "REFERENCED_ALREADY_TESTED")),
             "- 사전 수정(결과를 보기 전): " + "; ".join(x["id"] for x in report["preOutcomeRevisions"]) + " — 자세한 내용은 JSON의 `preOutcomeRevisions`.", "",
             "## 정보군별 결과", "",
             "| 정보군 | 등록 | 사용 가능 후보 | 사용 가능 특성 |", "|---|---:|---:|---|"]
    for k, v in fam.items():
        lines.append("| %s %s | %d | %d | %s |" % (k, FAMILY_KO[k], v["registered"], len(v["eligibleAlphaCandidates"]), ", ".join(v["eligibleAlphaCandidates"]) or "—"))
    lines += ["", "사용 가능 후보는 '알파 후보' 역할이면서 기준(행의 60% 이상, 30개 이상 종목, 52주 이상)을 넘은 특성입니다. 위험·비용·적격성 지표는 후보에 넣지 않습니다.", "",
              "## 특성별 커버리지 (계산한 특성)", "", "| 특성 | 역할 | 전체 커버리지 | 사용 범위 내 커버리지 | 사용 가능 기간 | 상태 |", "|---|---|---:|---:|---|---|"]
    for r in sorted((r for r in f.values() if "coveragePct" in r), key=lambda r: r["featureId"]):
        lines.append("| %s | %s | %s%% | %s%% | %s ~ %s | %s%s |" % (r["featureId"], r["role"], r["coveragePct"], r["coverageWithinUsableRangePct"],
                                                                  r["earliestUsableSignalDate"], r["latestUsableSignalDate"], STATUS_KO[r["measuredStatus"]],
                                                                  " (얇음)" if r.get("thinOverFloor") and r["measuredStatus"].endswith("READY") else ""))
    lines += ["", "## 6개 상호작용 (Level 3) — 미래 수익률은 보지 않고 표본 충분성만 판정", "", "| 상호작용 | 판정 | 평가 가능 주 | 결합 커버리지 | 사유 |", "|---|---|---:|---:|---|"]
    for k, v in report["interactions"].items():
        why = ("구성 특성 %s의 출처가 차단됨 — OHLCV 매집 지표(D11)로 대체하지 않음" % ", ".join(f for f in v["features"] if f.startswith("G"))) if v["status"] == "SOURCE_BLOCKED" else (
            "구성 특성의 시점 안전성 없음" if v["status"] == "PIT_UNSAFE" else
            "평가 가능 %s주(기준 %d주), 평가 구간 내 결합 커버리지 %s%%(기준 %.0f%%), 표본 구간 %s ~ %s" % (
                v.get("evaluableDates"), RD.MIN_EVALUABLE_DATES, v.get("jointCoverageWithinEvaluableRangePct"), 100 * RD.MIN_FEATURE_COVERAGE,
                (v.get("evaluableRange") or ["—", "—"])[0], (v.get("evaluableRange") or ["—", "—"])[1]))
        lines.append("| %s | %s%s | %s | %s | %s |" % (k, INTERACTION_KO[v["status"]], " (얇음)" if v.get("thin") else "", v.get("evaluableDates", "—"),
                                                      ("%s%%" % v["jointCoveragePct"]) if v.get("jointCoveragePct") is not None else "—", why))
    lines += ["", "'얇음'은 기준을 통과했지만 여유가 5%p 미만이거나 평가 가능 주가 104주 미만이라는 뜻입니다.", "",
              "## 비교 기준선 (Level 2)", "", "| 기준선 | 판정 | 기준 미달 구성원 | 구성원 전부가 있는 비율(공통 기간) |", "|---|---|---|---:|"]
    for k, v in report["baselines"].items():
        lines.append("| %s | %s | %s | %s |" % (k, INTERACTION_KO[v["status"]], ", ".join(v["membersBelowFloor"]) or "—",
                                                 "%s%%" % v["completeCaseCoverageWithinCommonRangePct"] if v.get("completeCaseCoverageWithinCommonRangePct") is not None else "—"))
    lines += ["", "## 계산하지 못한 특성과 데이터 출처", ""]
    for s in sources["sources"]:
        lines.append("- **%s** — %s: %s" % (", ".join(s["features"]), s["status"], SOURCE_KO.get(s["status"], s["source"])))
    lines += ["", "외국인·기관 순매수와 공매도는 최신 기록(%s)에서도 KRX 포털이 접근을 거부해(`%s`) **출처 차단**으로 유지합니다. 이번 단계에서 다시 확인하지 않았고, 일봉으로 만든 매집 지표(D11)를 투자자 수급 대용으로 쓰지 않습니다. 한 번 더 확인하려면 Actions의 `Probes` 워크플로우에서 `probe=kr-investor-flow` 또는 `kr-short-selling`을 선택해 실행합니다." % (
        sources["sources"][0]["latestEvidence"].get("updatedAt"), sources["sources"][0]["latestEvidence"].get("stopReason")), "",
              "## 더 넓은 유니버스 가능성 (평가만 함, Phase C에는 넣지 않음)", "", "- 판정: **상위 120 기준 유지 — 더 넓은 유니버스는 아직 준비되지 않음** (`%s`)" % universe["verdict"]["status"], "- %s" % universe["verdict"]["reason_ko"],
              "- 유동성 기준(60거래일 거래대금 중앙값 10억 원) 통과 종목 중 상위 120 밖은 연도별로 아래와 같습니다.", "", "| 연도 | 통과 종목(평균) | 상위120 밖(평균) | 밖 종목의 DART 공시 보유 | 밖 종목의 산업 라벨 |", "|---|---:|---:|---:|---:|"]
    for y, v in universe["byYear"].items():
        lines.append("| %s | %s | %s | %s%% | %s%% |" % (y, v["meanQualifiedNames"], v["meanQualifiedOutsideTop120"], v["outsideVisibleDartFilingPct"], v["outsideIndustryLabelPct"]))
    a = universe["acquisitionEstimate"]
    lines += ["", "- 추가 DART 수집이 필요한 종목 %d개(수집기 호출 구조로 계산한 **추정 상한** 약 %s회, 1회 실행 1,500회 기준 최대 %d회 실행). 가격 패널·산업 분류·상장폐지 대가 자료도 별도로 필요합니다." % (
        a["extraTickersNeedingDartCollection"], format(a["callsUpperBound"], ","), a["runsUpperBound"]), "",
              "## 시점·생존편향 한계", "",
              "- 한국 과거 데이터는 모두 이미 결과가 공개된 기간(2026-09-14까지)이라, 이후 평가에서 무엇이 나와도 확인이 아니라 탐색적 개발 증거입니다.",
              "- 산업 라벨은 벤더의 과거 분류가 아니라 현재 분류와 검증된 변경 이력으로 재구성한 것입니다(상장폐지 22개 종목은 분류 없음).",
              "- DART 재무는 2013~2015년이 비어 있고 2016년도 대부분 비어 있습니다. 금융업은 매출·영업이익 계정이 거의 없어 마진·현금전환·설비투자 계열이 기준에 못 미칩니다.",
              "- 유니버스는 신호일보다 앞선 월별 스냅샷의 시가총액 상위 120종목입니다. 오늘 살아남은 종목으로 과거를 채우지 않았습니다.",
              "- 상장폐지 22개 종목은 종결 대가(교환비율 등)가 `BLOCKED`입니다. 수익률 라벨을 만드는 단계에서 이 종목들을 어떻게 다룰지는 Phase C 등록에서 정해야 하며, 이번에 고치지 않았습니다.",
              "- 액면분할은 '가격이 정수 비율로 변했다'는 사실은 당일 알 수 있지만, 상장주식수 갱신이 늦어 확정은 며칠~몇 주 뒤입니다. 확정 전 창은 값을 보정하지 않고 비워 두었습니다(`UNCONFIRMED_CORPORATE_ACTION_IN_WINDOW`).",
              "- 가격 계열(`replay-v16`)은 분할을 사후 확정으로 보정해 만든 것입니다. 같은 이유로 확정 전 창은 비웠지만, 이 입력 자체가 신호일 시점의 재현이 아니라는 점은 남는 한계입니다.",
              "- 벤치마크 `069500.KS`의 외부 대조는 `%s` 상태입니다." % manifest["benchmark"]["reconciliationStatus"], "",
              "## Phase C 전에 남은 일", ""]
    lines += ["- " + s for s in manifest["prerequisitesBeforePhaseC"]]
    lines += ["", "## 사람이 직접 실행해야 하는 절차 (필수 아님)", ""]
    for step in manifest["humanTriggeredAcquisition"]:
        lines.append("- **%s** (필수 여부: %s) — %s" % (step["id"], step["required"], step["why"]))
        lines += ["  - " + h for h in step["how"]]
    return "\n".join(lines) + "\n"
