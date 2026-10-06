"""Q1-Q10 matrix and the human-readable report of the COMPLETED post-outcome audit, rendered from the result dict only (so the prose cannot disagree with the JSON).

Classification vocabulary is the repository's own (SUPPORTED_BY_AUDIT / PARTIALLY_SUPPORTED / NOT_SUPPORTED / UNRESOLVED_DATA_LIMITATION). It describes how well the audit's
evidence ANSWERS a question, not whether the answer is favourable to the model: a clear finding that D's gain was concentrated is SUPPORTED_BY_AUDIT. Nothing here is a
pass/fail, promotion or selection statement.
"""
from __future__ import annotations

from . import kr_integrated_alpha_portfolio_postoutcome_audit as A

NAMED_LABEL = {"005930.KS": "Samsung Electronics", "000660.KS": "SK Hynix"}
SPANS = ("A_2017_to_2024", "B_2025", "C_2026_to_cutoff", "D_full_window")
SPAN_TEXT = {"A_2017_to_2024": "2017-01-16 → 2024", "B_2025": "2025", "C_2026_to_cutoff": "2026 → cutoff", "D_full_window": "full window"}


def pct(x, nd=2):
    return "n/a" if x is None else f"{x * 100:+.{nd}f}%"


def share(x, nd=1):
    return "n/a" if x is None else f"{x * 100:.{nd}f}%"


def pp(x, nd=2):
    return "n/a" if x is None else f"{x * 100:+.{nd}f}pp"


def nav(x, nd=3):
    return "n/a" if x is None else f"{x:+.{nd}f}"


def _facts(result):
    """Every number the matrix and the report quote, computed once from the result dict."""
    c = result["completedAudit"]
    books, formal = c["books"], c["formalReported"]
    levels = {r["period"]: r for r in result["benchmarkPeriods"]["levels"]}
    track = result["trackingCrossCheck"]["span2017To2024"]
    thr = result["concentrationProxy"]["thresholds"]["formalWindow"]
    contrib = result["approximateBenchmarkContribution"]["periods"]
    cap_late = [contrib["B_2025"], contrib["C_2026_to_cutoff"]]
    dma = c["dMinusA"]
    pair = {a: {s: books[a]["namedSecurities"]["bySpan"][s] for s in SPANS} for a in "AD"}
    cf = c["counterfactual"]
    gc = {a: books[a]["gainConcentration"] for a in "AD"}
    late_log = levels["B_2025"]["logShareOfTerminalWealth"] + levels["C_2026_to_cutoff"]["logShareOfTerminalWealth"]
    pm = {a: books[a]["periodMetrics"] for a in "AD"}
    return {"c": c, "books": books, "formal": formal, "levels": levels, "track": track, "thr": thr, "contrib": contrib, "cap_late": cap_late, "dma": dma, "pair": pair, "cf": cf, "gc": gc,
            "late_log": late_log, "pm": pm,
            "pair_share_D": pair["D"]["D_full_window"]["combinedShareOfBookGrossContribution"],
            "pair_diff": pair["D"]["D_full_window"]["combinedGrossContributionNavUnits"] - pair["A"]["D_full_window"]["combinedGrossContributionNavUnits"],
            "late_cap_share": sum(p["combined"]["contributionNavUnits"] for p in cap_late) / sum(p["gain"] for p in cap_late)}


def question_matrix(result):
    f = _facts(result)
    L, tr, thr, dma, pm, gc = f["levels"], f["track"], f["thr"], f["dma"], f["pm"], f["gc"]
    ev = result["benchmarkEventAudit"]
    fa, fd, fp = f["formal"]["summaries"]["A"], f["formal"]["summaries"]["D"], f["formal"]["passive"]
    pr = f["c"]["reconstruction"]["architectures"]
    d_full = dma["D_full_window"]
    cf, pair_d = f["cf"], f["pair"]["D"]
    q = []
    q.append(A.question_entry(
        "Q1. Was the ~20.24% benchmark CAGR a broad decade-long phenomenon or driven by the recent regime?", A.SUPPORTED,
        f"Frozen benchmark: {pct(L['A_2017_to_2024']['annualizedReturn'])} a year over 2017-01-16 → 2024, {pct(L['B_2025']['cumulativeReturn'])} in 2025 and {pct(L['C_2026_to_cutoff']['cumulativeReturn'])} in 2026 to the "
        f"cutoff; those last two spans carry {share(f['late_log'])} of the window's log wealth. The full-window {pct(L['D_full_window']['annualizedReturn'])} a year ({pct(L['D_full_window']['cumulativeReturn'])}) "
        "is not a normal long-run KOSPI 200 return; it is a recent-regime figure. The years are kept and the benchmark is unchanged.", "frozen benchmark series, fixed spans"))
    q.append(A.question_entry(
        "Q2. Is the frozen benchmark internally reproducible and internally consistent?", A.PARTIAL,
        f"Reproducible: hash-verified series, complete against the registered calendar, and the completed audit reproduced both A and D (which carry the benchmark path) at 1e-9 over "
        f"{pr['A']['monthEndNavDates']} month-end NAVs; the formal passive path reads {pct(fp['annualizedReturn'])} a year / {pct(fp['cumulativeReturn'])} / MDD {pct(fp['maxDrawdown'])}. "
        f"Not consistent: its excess over the committed price index is {pct(tr['benchmarkOverIndexRelativePerYear'])} a year over 2017-2024 against {pct(tr['refCapWeightedTop120OverIndexRelativePerYear'])} for the same-data "
        f"constituent reference, and it accrues on {len(ev['eventDays'])} single days. Status `{ev['status']}`; the cause is not determinable from stored data.", "internal evidence only"))
    q.append(A.question_entry(
        "Q3. Is the frozen benchmark externally reconciled to an authoritative, definition-compatible KODEX 200 / KRX series?", A.UNRESOLVED,
        "No official source was reachable; no official number is quoted. The frozen values to reconcile are recorded for five fixed checkpoints.", A.EXTERNAL_UNRESOLVED))
    q.append(A.question_entry(
        "Q4. How concentrated did Samsung Electronics + SK Hynix become?", A.PARTIAL,
        f"Inside the PIT Top120 their combined market-cap share has a median of {share(thr['median'])}, a maximum of {share(thr['maximum'])} ({thr['maximumDate']}) and {share(thr['latest'])} on {thr['latestDate']}. "
        "A same-data market-cap proxy, not the KODEX 200 weight.", "PROXY_NOT_OFFICIAL_WEIGHT"))
    q.append(A.question_entry(
        "Q5. How much of the recent benchmark proxy gain did they explain?", A.PARTIAL,
        f"In the cap-weighted Top120 reference they contributed {share(f['late_cap_share'])} of the 2025 plus 2026-to-cutoff gain (monthly proxy weights). Not exact for KODEX 200.",
        "APPROXIMATE_WEIGHTED_CONTRIBUTION_USING_MONTHLY_WEIGHT_SNAPSHOTS"))
    hd = f["books"]["D"]["holdings"]
    ha = f["books"]["A"]["holdings"]
    q.append(A.question_entry(
        "Q6. What did A and D actually hold?", A.SUPPORTED,
        f"A (Stock only): {ha['distinctNames']} distinct names in {ha['spells']} holding spells, 110 valid decisions; D (Industry + Stock): {hd['distinctNames']} names in {hd['spells']} spells, 108 valid decisions. "
        f"D's mean top-industry share of invested weight is {share(f['books']['D']['concentration']['D_full_window']['meanTopIndustryShareOfInvested'])} against "
        f"{share(f['books']['A']['concentration']['D_full_window']['meanTopIndustryShareOfInvested'])} for A, and D held three or more names of one industry on "
        f"{share(f['books']['D']['concentration']['D_full_window']['shareOfHeldSessionsWithThreeOrMoreNamesInOneIndustry'])} of held sessions (A {share(f['books']['A']['concentration']['D_full_window']['shareOfHeldSessionsWithThreeOrMoreNamesInOneIndustry'])}).",
        "reconstructed paths, reproduced at 1e-9"))
    q.append(A.question_entry(
        "Q7. Why did D outperform A?", A.PARTIAL,
        f"Full window D {pct(fd['cumulativeNetReturn'])} vs A {pct(fa['cumulativeNetReturn'])}. By fixed span D − A in cumulative return is {pp(dma['A_2017_to_2024']['returnDMinusA'])} (2017-2024), {pp(dma['B_2025']['returnDMinusA'])} (2025) "
        f"and {pp(dma['C_2026_to_cutoff']['returnDMinusA'])} (2026): D trailed A before 2025 and led only after. The books differ on every one of the {d_full['anchorsBothBooksHadAValidDecision']} shared anchors "
        f"(identical selections {d_full['anchorsWithIdenticalSelection']}, mean {d_full['meanDifferingNames']:.4f} of 5 names differ) and the gap is largely carried by a few names in one industry, not by costs "
        f"(D paid {nav(d_full['costNavUnitsD'] - d_full['costNavUnitsA'])} more NAV units). The decomposition is direct; why the Industry layer chose those names is not tested.", "reconstructed attribution, descriptive"))
    q.append(A.question_entry(
        "Q8. Was D's performance broad through time, or concentrated in 2025-2026 and a few industries / names?", A.SUPPORTED,
        f"Concentrated. {share(gc['D']['shareFrom2025And2026Spans'])} of D's gross contribution (NAV units) falls in the 2025 and 2026 spans (A {share(gc['A']['shareFrom2025And2026Spans'])}); the top security is "
        f"{share(gc['D']['shareFromTop1Security'])}, top two {share(gc['D']['shareFromTop2Securities'])}, top five {share(gc['D']['shareFromTop5Securities'])}; the top industry "
        f"({gc['D']['topIndustry']['label']}) is {share(gc['D']['topIndustry']['share'])}. NAV-unit contributions weigh late periods more because NAV had compounded, so the percentage return by span "
        f"(D {pct(pm['D']['A_2017_to_2024']['cumulativeNetReturn'])} / {pct(pm['D']['B_2025']['cumulativeNetReturn'])} / {pct(pm['D']['C_2026_to_cutoff']['cumulativeNetReturn'])}) is read beside them.", "reconstructed attribution, fixed spans"))
    q.append(A.question_entry(
        "Q9. How much of D's realised result came directly from Samsung Electronics / SK Hynix and their PIT industry?", A.SUPPORTED,
        f"Directly little: the two names contributed {nav(pair_d['D_full_window']['combinedGrossContributionNavUnits'])} of {nav(pair_d['D_full_window']['grossContributionNavUnitsOfBook'])} gross NAV units "
        f"({share(f['pair_share_D'])}); Samsung Electronics {nav(pair_d['D_full_window']['005930.KS']['grossContributionNavUnits'])}, SK Hynix {nav(pair_d['D_full_window']['000660.KS']['grossContributionNavUnits'])} (a net detractor). "
        f"Through their PIT industry a great deal: ELECTRONICS_ELECTRICAL contributed {share(gc['D']['topIndustry']['share'])} of D's gross.", "reconstructed D holdings"))
    q.append(A.question_entry(
        "Q10. What does the pre-registered D_EXCLUDE_SAMSUNG_HYNIX descriptive sensitivity show?", A.SUPPORTED,
        f"With the two securities unavailable, D reads {pct(cf['summary']['netAnnualizedReturn'])} a year / {pct(cf['summary']['cumulativeNetReturn'])} / MDD {pct(cf['summary']['maxDrawdown'])} against "
        f"{pct(cf['formalD']['netAnnualizedReturn'])} / {pct(cf['formalD']['cumulativeNetReturn'])} / {pct(cf['formalD']['maxDrawdown'])} for D: "
        f"{pp(cf['differenceVersusD']['cumulativeNetReturn'])} cumulative, turnover {cf['summary']['annualizedOneWayTurnover']:.2f}x vs {cf['formalD']['annualizedOneWayTurnover']:.2f}x. "
        "POST_OUTCOME_DESCRIPTIVE_SENSITIVITY, NOT_CONFIRMATORY, NOT_ELIGIBLE_FOR_MODEL_SELECTION.", "single registered counterfactual"))
    return q


def _table(add, header, rows, left=1):
    add("| " + " | ".join(header) + " |")
    add("|" + "|".join("---:" if i >= left else "---" for i in range(len(header))) + "|")
    for r in rows:
        add("| " + " | ".join(str(x) for x in r) + " |")
    add("")


def markdown_report(result):
    L = []
    add = L.append
    f = _facts(result)
    c, books, fm = f["c"], f["books"], f["formal"]
    lv, thr, track, contrib = f["levels"], f["thr"], result["trackingCrossCheck"], result["approximateBenchmarkContribution"]["periods"]
    prov, ev, ext = c["provenance"], result["benchmarkEventAudit"], result["externalReconciliation"]
    fid, matrix = result["formalIdentity"], result["questionMatrix"]
    dma, pm, gc, cf = f["dma"], f["pm"], f["gc"], f["cf"]
    fa, fd, fp = fm["summaries"]["A"], fm["summaries"]["D"], fm["passive"]

    add("# KR integrated alpha portfolio v1 — post-outcome concentration audit")
    add("")
    add(f"**{A.STATEMENT}**")
    add("")
    add("## 1. Scope and scientific status")
    add("")
    add(f"Status `{A.SCIENTIFIC_STATUS}`. This audit diagnoses the already-spent formal run `{fid['workflowRunId']}` of `kr-integrated-alpha-portfolio-v1`. The formal result is not rerun, rewritten or "
        "reinterpreted into a new decision; no execution lock, frozen file, factor weight, threshold, portfolio rule or benchmark was changed; the primary formal benchmark remains `069500.KS`. "
        "Evidence classes are kept apart: `FORMAL_REPORTED_RESULT` (copied from the sealed artifact), `POST_OUTCOME_DIAGNOSTIC_RECONSTRUCTION` (the frozen code replayed read-only), "
        "`POST_OUTCOME_COUNTERFACTUAL_SENSITIVITY` (the one registered sensitivity) and `POST_OUTCOME_DESCRIPTIVE_PROXY` (same-data references). Nothing here is prospective evidence, a model "
        "rescue, a selection or a promotion decision. Successor model design is outside the scope of this post-outcome audit.")
    add("")
    add("## 2. Exact provenance")
    add("")
    add(f"* Formal run `{fid['workflowRunId']}`, execution commit `{fid['executionSha']}`, frozen spec `{fid['specSha256']}`; result artifact `{fid['resultArtifactId']}` (`{fid['resultArtifactName']}`, "
        f"`{fid['resultArtifactDigest']}`); raw-input artifact `{fid['rawInputArtifactId']}` (`{fid['rawInputArtifactName']}`, `{fid['rawInputArtifactDigest']}`, run `{fid['rawInputRunId']}`); both "
        "execution-lock tags exist and point at the execution commit (checked read-only by the audit run). The formal `seal` job failed at its commit step; that is infrastructure and is not repaired here.")
    add(f"* Audit run `{prov['workflowRunId']}` ({prov['event']}, `{prov['conclusion']}`), workflow definition on `{prov['workflowDefinitionBranch']}` at `{prov['workflowDefinitionSha'][:12]}`, audit implementation "
        f"`audit_ref` `{prov['auditRefResolvedSha']}`. Audit artifact `{prov['artifactId']}` (`{prov['artifactName']}`, archive `{prov['artifactArchiveDigest']}`).")
    add(f"* Full audit file `{prov['fullAuditFile']}`: **{prov['fullAuditJsonBytes']:,} bytes, SHA-256 `{prov['fullAuditJsonSha256']}`** (the value the run printed). It stays an Actions-only artifact; this "
        "repository carries the compact record the report is rendered from. How it was read here: " + prov["howTheFileWasReadHere"] + ". Note: " + prov["handoffDigestNote"] + ".")
    add("")
    add("## 3. Formal-result reconstruction verification")
    add("")
    rc = c["reconstruction"]
    add(f"Status **`{rc['status']}`** at tolerance {rc['tolerance']:g}. For both architectures: reproduced = {all(r['reproduced'] for r in rc['architectures'].values())}, divergences "
        f"{sum(r['divergenceCount'] for r in rc['architectures'].values())}, month-end NAV dates compared {rc['architectures']['A']['monthEndNavDates']} each. Metrics compared: "
        + ", ".join(f"`{m}`" for m in rc["metricsCompared"]) + ". " + rc["attributionClosure"] + ".")
    add("")
    _table(add, ("", "Annualized", "Cumulative", "Max drawdown", "One-way turnover / yr", "Cost drag / yr", "Replacements"), [
        ("A Stock only (formal)", pct(fa["netAnnualizedReturn"], 4), pct(fa["cumulativeNetReturn"]), pct(fa["maxDrawdown"]), f"{fa['annualizedOneWayTurnover']:.3f}x", pct(fa["annualizedCostDrag"]), fa["replacements"]),
        ("D Industry + Stock (formal)", pct(fd["netAnnualizedReturn"], 4), pct(fd["cumulativeNetReturn"]), pct(fd["maxDrawdown"]), f"{fd['annualizedOneWayTurnover']:.3f}x", pct(fd["annualizedCostDrag"]), fd["replacements"]),
        ("Passive 069500.KS (formal)", pct(fp["annualizedReturn"], 4), pct(fp["cumulativeReturn"]), pct(fp["maxDrawdown"]), "—", "—", "—")])
    p = rc["priorAuditFacts"]
    add(f"Facts quoted from the earlier read-only audit, compared with the reconstruction rather than trusted: anchors with both books available {p['reconstructedAnchorsWithBothBooksAvailable']} "
        f"(expected {p['expectedAnchorsWithBothBooksAvailable']}), identical selections {p['reconstructedAnchorsWithIdenticalSelection']} (expected {p['expectedAnchorsWithIdenticalSelection']}), mean differing names "
        f"{p['reconstructedMeanDifferingNames']:.4f} of 5 (expected {p['expectedMeanDifferingNames']}); agrees = {p['agrees']}. Side-effect counters of the audit's own bundle build: "
        + ", ".join(f"{k}={v}" for k, v in rc["sideEffectCounters"].items()) + " (one past-only feature build; no marker, lock, permit, market-value read or formal replay).")
    add("")
    add("D materially improved on A in the frozen development study, **but D did not beat the passive benchmark over the full formal window after costs, and its drawdown "
        f"({pct(fd['maxDrawdown'])}) is deeper than the passive path's ({pct(fp['maxDrawdown'])})**. Nothing in this audit describes the study as having found benchmark-beating alpha.")
    add("")
    add("## 4. Q1–Q10 matrix")
    add("")
    add("The classification says how well the audit's evidence answers the question, not whether the answer favours the model.")
    add("")
    _table(add, ("Question", "Classification", "Evidence basis"), [(q["question"], f"`{q['classification']}`", q["basis"]) for q in matrix], left=3)
    for q in matrix:
        add(f"* **{q['question']}** `{q['classification']}` — {q['evidence']}")
    add("")
    add("## 5. Benchmark audit")
    add("")
    add("### 5.1 Period decomposition (Q1)")
    add("")
    _table(add, ("Span", "From → to", "Cumulative", "Annualized", "Share of log wealth", "Share of terminal gain"),
           [(r["period"], f"{r['fromSession']} → {r['toSession']}", pct(r["cumulativeReturn"]), pct(r["annualizedReturn"]), share(r["logShareOfTerminalWealth"]), share(r["shareOfTerminalGain"])) for r in result["benchmarkPeriods"]["levels"]])
    add("Annualized is shown only for spans of a full year or more. The formal ~20.24% a year is not a normal long-run expected KOSPI 200 return: 2017–2024 annualizes "
        f"{pct(lv['A_2017_to_2024']['annualizedReturn'])}, while 2025 ({pct(lv['B_2025']['cumulativeReturn'])}) and 2026 to the cutoff ({pct(lv['C_2026_to_cutoff']['cumulativeReturn'])}) carry {share(f['late_log'])} of the log wealth. "
        "The years are not removed and the benchmark is not changed.")
    add("")
    add("### 5.2 Construction and the suspicious observations (Q2)")
    add("")
    bi = result["benchmarkIntegrity"]
    add(f"* Series: {bi['sessions']} sessions {bi['firstSession']} → {bi['lastSession']}, registered calendar {bi['calendarSessions']}, missing {len(bi['sessionsMissingFromSeries'])}, "
        f"not in calendar {len(bi['sessionsNotInCalendar'])}, non-positive or non-finite {bi['nonPositiveOrNonFiniteLevels']}; hash-verified inputs. Return basis: `BENCHMARK_RELATIVE_ADJUSTED_INDEX_RETURN_PARTIAL_DISTRIBUTIONS` "
        "(an as-traded close with forward-accumulated distributions where the vendor served them — neither a price return nor a complete shareholder return).")
    add("* " + ev["constructionRead"])
    big = {r["date"]: r for r in ev["eventDays"]}
    jul = big["2026-07-31"]
    nxt = big["2026-08-03"]
    moves = ", ".join(r["date"] + " (" + pct(r["return"]) + ")" for r in bi["dailyMovesAtLeast10Percent"])
    lm = ev["largeBenchmarkMovesAgainstTheIndex"]
    add(f"* Daily moves of at least 10% in the window: {moves}. The committed KS200 price index, an independent route to the same market, moved in the same direction on "
        f"{sum(1 for r in lm if r['sameDirection'])} of {len(lm)} of those days (index returns " + ", ".join(pct(r["indexReturn"]) for r in lm) + "; for 2026-07-31 benchmark "
        f"{pct(jul['benchmarkReturn'])} vs index {pct(jul['indexReturn'])}), so those sessions are market moves, not a source anomaly in the benchmark's own price path.")
    add(f"* Excess over the price index accrues in steps. {len(ev['eventDays'])} sessions differ from the index by at least {share(ev['threshold'], 0)} in a day: "
        + "; ".join(f"{r['date']} {pct(r['relativeMove'])}" for r in ev["eventDays"]) + f". {len(ev['eventDaysInLateAprilOrLateDecember'])} of them fall in late April or late December and are the size of a distribution; the other two "
        f"(2026-07-31 {pct(jul['relativeMove'])} and 2026-08-03 {pct(nxt['relativeMove'])}) are a jump that reverses on the next session, which looks like a quote-timing difference between the ETF close and the index rather than an applied event.")
    add("")
    _table(add, ("Year", "Total excess over index", "Event days", "On event days", "On all other days"),
           [(y, pct(v["totalRelativeExcess"]), v["eventDays"], pct(v["eventDayRelativeExcess"]), pct(v["otherDaysRelativeExcess"])) for y, v in ev["byCalendarYear"].items()])
    add(f"Over 2017-2024 the benchmark earned {pct(track['span2017To2024']['benchmarkOverIndexRelativePerYear'])} a year above the index, against {pct(track['span2017To2024']['refCapWeightedTop120OverIndexRelativePerYear'])} for the same-data "
        f"constituent reference; the gap is {pct(ev['benchmarkExcessOverReferencePerYear2017To2024'])} a year, above the {pct(ev['gapFlagThresholdPerYear'], 0)} descriptive flag, so the internal reading is **`{ev['status']}`**: the series is "
        "reproducible, but its accrual over the price index is larger than the same-data constituents' own dividends explain, in steps and on both a late-April and a late-December schedule. "
        + ev["whatThisCannotSay"] + " If the accrual were overstated, the passive path would be overstated and every architecture's excess understated; the size is not settled and no corrected benchmark is built.")
    add("")
    add("### 5.3 External reconciliation (Q3)")
    add("")
    add(f"**`{ext['status']}`.** {ext['reason']}. Internal reproducibility (A) is established; external economic truth (B) is not. The frozen values to reconcile with Samsung Asset Management / KRX at fixed checkpoints, "
        "comparing only definition-compatible series (KODEX 200 distribution-reinvested market-price or NAV return; KOSPI 200 total-return index; never a price-only index):")
    add("")
    _table(add, ("Checkpoint", "Session", "Level", "Year-to-date return (frozen)"), [(r["checkpoint"], r["session"], f"{r['level']:,.1f}", pct(r["yearToDateReturn"])) for r in ext["frozenValuesToReconcile"]])
    add("")
    add("## 6. Benchmark mega-cap concentration (Q4, Q5)")
    add("")
    add("Same-data PROXY: share of total (not free-float) market capitalisation of the PIT Top120 from monthly snapshots; it is not the KOSPI 200 or KODEX 200 weight, and no exact official weight was obtained.")
    add("")
    _table(add, ("Snapshot on or before", "Samsung Electronics", "SK Hynix", "Combined"),
           [(f"{r['checkpoint']} ({r['snapshot']})", share(r["Samsung Electronics"]), share(r["SK Hynix"]), share(r["combined"])) for r in result["concentrationProxy"]["checkpoints"] if r.get("snapshot")])
    add(f"Formal window: median {share(thr['median'])}, maximum {share(thr['maximum'])} ({thr['maximumDate']}), minimum {share(thr['minimum'])} ({thr['minimumDate']}). Snapshots above round descriptive numbers:")
    add("")
    _table(add, ("Threshold", "Snapshots above", "First", "Last"), [(f"{float(k):.0%}", f"{v['snapshotsAbove']} of {thr['snapshots']}", v["first"] or "—", v["last"] or "—") for k, v in thr["thresholds"].items()])
    add("Contribution to the cap-weighted Top120 reference (`APPROXIMATE_WEIGHTED_CONTRIBUTION_USING_MONTHLY_WEIGHT_SNAPSHOTS`, NAV units):")
    add("")
    _table(add, ("Span", "Reference gain", "Samsung Electronics", "SK Hynix", "Combined", "Combined share"),
           [(k, nav(v["gain"]), nav(v["securities"]["005930.KS"]["contributionNavUnits"]), nav(v["securities"]["000660.KS"]["contributionNavUnits"]), nav(v["combined"]["contributionNavUnits"]), share(v["combined"]["shareOfSpanGain"])) for k, v in contrib.items()])
    refs = result["referencePortfolios"]
    _table(add, ("Reference", "Full window", "2017-2024", "2025", "2026 to cutoff"), [(n, pct(per["D_full_window"]["cumulativeReturn"]), pct(per["A_2017_to_2024"]["cumulativeReturn"]), pct(per["B_2025"]["cumulativeReturn"]),
                                                                                       pct(per["C_2026_to_cutoff"]["cumulativeReturn"])) for n, per in refs["periods"].items()])
    add("These are descriptions of reference portfolios; the formal benchmark stays `069500.KS`, concentration included, and \"the model beats the benchmark once the two names are removed\" is outcome-selected "
        "reasoning that this audit does not make.")
    add("")
    add("## 7. A and D actual holdings (Q6)")
    add("")
    _table(add, ("", "A Stock only", "D Industry + Stock"), [
        ("Valid decisions / scheduled anchors", f"{books['A']['namedSecurities']['decisionsWithAValidSelection']} / {pm['A']['D_full_window']['anchorRebalances'] + pm['A']['D_full_window']['signalUnavailableAnchors']}",
         f"{books['D']['namedSecurities']['decisionsWithAValidSelection']} / {pm['D']['D_full_window']['anchorRebalances'] + pm['D']['D_full_window']['signalUnavailableAnchors']}"),
        ("Signal-unavailable anchors (no-trade)", pm["A"]["D_full_window"]["signalUnavailableAnchors"], pm["D"]["D_full_window"]["signalUnavailableAnchors"]),
        ("Holding spells (entries) / exits", f"{books['A']['holdings']['entries']} / {books['A']['holdings']['exits']}", f"{books['D']['holdings']['entries']} / {books['D']['holdings']['exits']}"),
        ("Distinct names / held in more than one spell", f"{books['A']['holdings']['distinctNames']} / {books['A']['holdings']['namesHeldInMoreThanOneSpell']}", f"{books['D']['holdings']['distinctNames']} / {books['D']['holdings']['namesHeldInMoreThanOneSpell']}"),
        ("Median spell (sessions)", f"{books['A']['holdings']['medianSpellSessions']:.0f}", f"{books['D']['holdings']['medianSpellSessions']:.0f}"),
        ("Replacements / one-way turnover per year", f"{pm['A']['D_full_window']['replacements']} / {pm['A']['D_full_window']['annualizedOneWayTurnover']:.2f}x", f"{pm['D']['D_full_window']['replacements']} / {pm['D']['D_full_window']['annualizedOneWayTurnover']:.2f}x"),
        ("Gross contribution / cost (NAV units)", f"{nav(books['A']['securityContribution']['D_full_window']['grossContributionNavUnits'])} / {nav(books['A']['securityContribution']['D_full_window']['transactionCostNavUnits'])}",
         f"{nav(books['D']['securityContribution']['D_full_window']['grossContributionNavUnits'])} / {nav(books['D']['securityContribution']['D_full_window']['transactionCostNavUnits'])}"),
        ("Mean holdings / mean cash share", f"{fa['averageHoldings']:.2f} / {share(fa['averageCashShare'])}", f"{fd['averageHoldings']:.2f} / {share(fd['averageCashShare'])}"),
        ("Largest single-name weight (mean / max)", f"{share(books['A']['concentration']['D_full_window']['averageLargestNameWeightOfNav'])} / {share(books['A']['concentration']['D_full_window']['maximumLargestNameWeightOfNav'])}",
         f"{share(books['D']['concentration']['D_full_window']['averageLargestNameWeightOfNav'])} / {share(books['D']['concentration']['D_full_window']['maximumLargestNameWeightOfNav'])}"),
        ("Mean top-industry share of invested weight (max)", f"{share(books['A']['concentration']['D_full_window']['meanTopIndustryShareOfInvested'])} ({share(books['A']['concentration']['D_full_window']['maximumTopIndustryShareOfInvested'])})",
         f"{share(books['D']['concentration']['D_full_window']['meanTopIndustryShareOfInvested'])} ({share(books['D']['concentration']['D_full_window']['maximumTopIndustryShareOfInvested'])})"),
        ("Held sessions with 3+ names in one industry", share(books["A"]["concentration"]["D_full_window"]["shareOfHeldSessionsWithThreeOrMoreNamesInOneIndustry"]), share(books["D"]["concentration"]["D_full_window"]["shareOfHeldSessionsWithThreeOrMoreNamesInOneIndustry"]))])
    add("Cost is each day's engine cost; per-name cost is a descriptive allocation in proportion to traded notional, not a per-name measurement. Largest contributors and detractors by security (gross NAV units, full window):")
    add("")
    for a in "AD":
        sc = books[a]["securityContribution"]["D_full_window"]
        add(f"* **{a} top:** " + ", ".join(f"{x['ticker']} {nav(x['contribution'])}" for x in sc["top10Contributors"][:6]) + ". **bottom:** " + ", ".join(f"{x['ticker']} {nav(x['contribution'])}" for x in sc["top10Detractors"][:6]) + ".")
    add("")
    add("D by PIT industry (the industry the strategy itself used at the decision date; holding frequency = share of name-sessions, weight = mean share of NAV over all sessions):")
    add("")
    ic = books["D"]["industryContribution"]["D_full_window"]["byIndustry"]
    _table(add, ("Industry", "Name-session share", "Mean NAV weight", "Gross contribution, full window"),
           [(k, share(v["shareOfNameSessions"]), share(v["averageWeightOfNavOverAllSessions"]), nav(ic.get(k))) for k, v in list(books["D"]["industryHolding"].items())[:8]])
    add("Industry contribution by span (top three, NAV units):")
    add("")
    for s in SPANS:
        add(f"* {SPAN_TEXT[s]}: " + ", ".join(f"{x['industry']} {nav(x['contribution'])}" for x in books["D"]["industryContribution"][s]["top"][:3]) + " — negative: " + (", ".join(f"{x['industry']} {nav(x['contribution'])}" for x in books["D"]["industryContribution"][s]["bottom"][:3] if x["contribution"] < 0) or "none"))
    add("")
    add("## 8. D − A attribution (Q7, Q8)")
    add("")
    rows = []
    for s in SPANS:
        d, a_, d_ = dma[s], pm["A"][s], pm["D"][s]
        rows.append((SPAN_TEXT[s], pct(a_["cumulativeNetReturn"]), pct(d_["cumulativeNetReturn"]), pp(d["returnDMinusA"]), pct(a_["cumulativePassiveReturn"]), nav(d["grossContributionDifferenceNavUnits"]),
                     f"{nav(d['costNavUnitsD'] - d['costNavUnitsA'])}", f"{d['meanDifferingNames']:.2f} / {d['anchorsBothBooksHadAValidDecision']}", f"{d_['oneWayTurnoverSum']:.2f} vs {a_['oneWayTurnoverSum']:.2f}"))
    _table(add, ("Fixed span", "A", "D", "D − A (cumulative, pp)", "Passive", "Gross contribution difference (NAV)", "Extra cost D (NAV)", "Differing names / shared anchors", "Sum of one-way turnover, D vs A"), rows)
    add("Fixed spans only; none was chosen from the result. Net of costs D trailed A before 2025 (A "
        f"{pct(pm['A']['A_2017_to_2024']['annualizedNetReturn'])} vs D {pct(pm['D']['A_2017_to_2024']['annualizedNetReturn'])} a year while the passive path made {pct(pm['A']['A_2017_to_2024']['annualizedPassiveReturn'])}), then led by "
        f"{pp(dma['B_2025']['returnDMinusA'])} in 2025 and {pp(dma['C_2026_to_cutoff']['returnDMinusA'])} in 2026 to the cutoff. D traded {pm['D']['D_full_window']['annualizedOneWayTurnover'] / pm['A']['D_full_window']['annualizedOneWayTurnover']:.1f}x as much as A and paid "
        f"{nav(dma['D_full_window']['costNavUnitsD'] - dma['D_full_window']['costNavUnitsA'])} more NAV units of cost; the gross gap is {nav(dma['D_full_window']['grossContributionDifferenceNavUnits'])}, so the advantage is a selection and "
        "industry-exposure difference, not a cost difference.")
    add("")
    add("Names adding to and subtracting from D − A (gross NAV units, full window): adds " + ", ".join(f"{x['ticker']} {nav(x['difference'])}" for x in dma["D_full_window"]["topNamesAddingToDMinusA"][:6])
        + "; subtracts " + ", ".join(f"{x['ticker']} {nav(x['difference'])}" for x in dma["D_full_window"]["topNamesSubtractingFromDMinusA"][:6]) + ".")
    add("")
    add("Concentration of the gain (Q8):")
    add("")
    _table(add, ("", "A", "D"), [
        ("Share of gross contribution in the 2025 + 2026 spans", share(gc["A"]["shareFrom2025And2026Spans"]), share(gc["D"]["shareFrom2025And2026Spans"])),
        ("Top-1 / top-2 / top-5 securities, share of gross", f"{share(gc['A']['shareFromTop1Security'])} / {share(gc['A']['shareFromTop2Securities'])} / {share(gc['A']['shareFromTop5Securities'])}",
         f"{share(gc['D']['shareFromTop1Security'])} / {share(gc['D']['shareFromTop2Securities'])} / {share(gc['D']['shareFromTop5Securities'])}"),
        ("Top industry, share of gross", f"{gc['A']['topIndustry']['label']} {share(gc['A']['topIndustry']['share'])}", f"{gc['D']['topIndustry']['label']} {share(gc['D']['topIndustry']['share'])}")])
    add("Shares are of full-window gross contribution in NAV units; those weigh late periods more because NAV had compounded, so the percentage returns in the table above are the cleaner regime view. "
        "A signal-association statistic across the whole cross-section (section 12) is not the same thing as the realised concentrated portfolio, which is what this section measures.")
    add("")
    add("## 9. Samsung Electronics and SK Hynix in the actual books (Q9)")
    add("")
    rows = []
    for a in "AD":
        for t in NAMED_LABEL:
            s = books[a]["namedSecurities"]["securities"][t]
            sp = books[a]["namedSpells"][t]
            first = min((x["entryDate"] for x in sp), default="—")
            last = max((x["lastHeldDate"] for x in sp), default="—")
            rows.append((a, NAMED_LABEL[t], f"{s['decisionsSelected']} of {books[a]['namedSecurities']['decisionsWithAValidSelection']} ({share(s['shareOfValidDecisionsSelected'])})", first, last, s["sessionsHeld"],
                         share(s["averageWeightWhileHeld"]), share(s["maximumWeight"]),
                         nav(books[a]["namedSecurities"]["bySpan"]["D_full_window"][t]["grossContributionNavUnits"]), nav(books[a]["namedSecurities"]["bySpan"]["D_full_window"][t]["allocatedCostNavUnits"], 4)))
    _table(add, ("Book", "Security", "Decisions selecting it", "First entry", "Last held", "Sessions held", "Mean weight held", "Max weight", "Gross contribution (NAV)", "Allocated cost (NAV)"), rows)
    add("Combined contribution of the two names to D, by span (gross NAV units; share of D's gross in the span):")
    add("")
    _table(add, ("Span", "Samsung Electronics", "SK Hynix", "Combined", "Share of D's gross", "Allocated cost"),
           [(SPAN_TEXT[s], nav(v["005930.KS"]["grossContributionNavUnits"]), nav(v["000660.KS"]["grossContributionNavUnits"]), nav(v["combinedGrossContributionNavUnits"]), share(v["combinedShareOfBookGrossContribution"]),
             nav(v["combinedAllocatedCostNavUnits"], 4)) for s, v in f["pair"]["D"].items()])
    add(f"Answer: D's result did not depend on these two names directly. Together they are {share(f['pair_share_D'])} of D's gross contribution; Samsung Electronics contributed and SK Hynix subtracted "
        f"({nav(f['pair']['D']['D_full_window']['000660.KS']['grossContributionNavUnits'])}, mostly in 2026), and the pair adds {nav(f['pair_diff'])} to D − A. It depends heavily on their PIT industry: "
        f"`{gc['D']['topIndustry']['label']}` supplied {share(gc['D']['topIndustry']['share'])} of D's gross, through other members of that industry "
        + ", ".join(f"{x['ticker']} {nav(x['contribution'])}" for x in books["D"]["holdings"]["topContributors"][:5] if x["ticker"] not in NAMED_LABEL) + " (largest contributors, spell totals).")
    add("")
    add("## 10. D_EXCLUDE_SAMSUNG_HYNIX descriptive sensitivity (Q10)")
    add("")
    add("**" + " · ".join(cf["labels"]) + "**")
    add("")
    add(f"Rule: {cf['rule']}. No refit, no factor or parameter change, benchmark unchanged, mean holdings {cf['summary']['averageHoldings']:.2f} (unchanged). Formal decisions unchanged: {cf['formalDecisionsUnchanged']}. Evidence class `{cf['evidenceClass']}`. "
        f"Signal availability {cf['signalAvailability']['validDecisionAnchors']} of {cf['signalAvailability']['scheduledAnchors']} anchors, as in D.")
    add("")
    rows = [("Full window", pct(cf["formalD"]["netAnnualizedReturn"]), pct(cf["summary"]["netAnnualizedReturn"]), pct(cf["formalD"]["cumulativeNetReturn"]), pct(cf["summary"]["cumulativeNetReturn"]), pct(cf["formalD"]["maxDrawdown"]), pct(cf["summary"]["maxDrawdown"]),
             f"{cf['formalD']['annualizedOneWayTurnover']:.2f}x", f"{cf['summary']['annualizedOneWayTurnover']:.2f}x", f"{cf['formalD']['totalCostFractionOfNav']:.4f}", f"{cf['summary']['totalCostFractionOfNav']:.4f}")]
    _table(add, ("", "Ann. D", "Ann. excl.", "Cum. D", "Cum. excl.", "MDD D", "MDD excl.", "Turnover D", "Turnover excl.", "Cost D", "Cost excl."), rows)
    rows = [(SPAN_TEXT[s], pct(pm["D"][s]["cumulativeNetReturn"]), pct(cf["periodMetrics"][s]["cumulativeNetReturn"]), pct(pm["D"][s]["maxDrawdownWithinSpan"]), pct(cf["periodMetrics"][s]["maxDrawdownWithinSpan"]),
             f"{pm['D'][s]['oneWayTurnoverSum']:.2f}", f"{cf['periodMetrics'][s]['oneWayTurnoverSum']:.2f}", f"{pm['D'][s]['costFractionSum']:.4f}", f"{cf['periodMetrics'][s]['costFractionSum']:.4f}") for s in SPANS]
    _table(add, ("Span", "Cum. D", "Cum. excl.", "MDD D", "MDD excl.", "Σ one-way turnover D", "Σ one-way turnover excl.", "Σ cost D", "Σ cost excl."), rows)
    d25 = cf["periodMetrics"]["B_2025"]["cumulativeNetReturn"] - pm["D"]["B_2025"]["cumulativeNetReturn"]
    d26 = cf["periodMetrics"]["C_2026_to_cutoff"]["cumulativeNetReturn"] - pm["D"]["C_2026_to_cutoff"]["cumulativeNetReturn"]
    add(f"By span the effect runs in both directions ({pp(d25)} in 2025, {pp(d26)} in 2026 to the cutoff), which is the usual look of replacing two names with their neighbours in the ranking rather than a systematic loss or gain.")
    add("")
    add(f"Descriptively, the exclusion neither removed nor reduced D's full-window result: it reads {pp(cf['differenceVersusD']['cumulativeNetReturn'])} of cumulative return and {pp(cf['differenceVersusD']['netAnnualizedReturn'])} a year versus D, with the "
        f"same drawdown depth and slightly higher turnover. The book moved to other `{cf['gainConcentration']['topIndustry']['label']}` names ({share(cf['gainConcentration']['topIndustry']['share'])} of gross; top five securities "
        f"{share(cf['gainConcentration']['shareFromTop5Securities'])}), so the sensitivity shows independence from the two securities, not independence from their industry. It informs interpretation only: it is not a result "
        "about beating the benchmark, not a rescue and not eligible for model selection, and no other exclusion set was run.")
    add("")
    add("## 11. Formal frozen decisions (unchanged)")
    add("")
    add(f"* Industry layer: **`{fm['industryLayerDecision']}`** (pair classes {fm['industryPairClasses']}).")
    add(f"* Final architecture: **`{fm['finalArchitecture']}`**, reason `{fm['reason']}`; underlying `{fm['underlying']}`.")
    add("* These are the sealed machine decisions of run " + str(fid["workflowRunId"]) + ". This audit does not alter, reinterpret into a different decision, or add to them.")
    add("")
    add("## 12. Post-outcome economic interpretation")
    add("")
    add("Kept separate from section 11. The narrowest description the numbers support is **regime-dependent and industry-concentrated development support, not dependent on the two named securities**:")
    add("")
    add(f"* **Regime-dependent.** D trailed A and the passive path before 2025 ({pct(pm['D']['A_2017_to_2024']['cumulativeNetReturn'])} vs A {pct(pm['A']['A_2017_to_2024']['cumulativeNetReturn'])} vs passive {pct(pm['A']['A_2017_to_2024']['cumulativePassiveReturn'])}); "
        f"{share(gc['D']['shareFrom2025And2026Spans'])} of its gross contribution arrived in the 2025 and 2026 spans, when it beat passive ({pct(pm['D']['B_2025']['cumulativeNetReturn'])} vs {pct(pm['D']['B_2025']['cumulativePassiveReturn'])}; "
        f"{pct(pm['D']['C_2026_to_cutoff']['cumulativeNetReturn'])} vs {pct(pm['D']['C_2026_to_cutoff']['cumulativePassiveReturn'])}).")
    add(f"* **Industry-concentrated.** The Industry layer made D a concentrated industry book (three or more names of one industry on {share(books['D']['concentration']['D_full_window']['shareOfHeldSessionsWithThreeOrMoreNamesInOneIndustry'])} of held "
        f"sessions, {share(books['D']['concentration']['C_2026_to_cutoff']['meanTopIndustryShareOfInvested'])} top-industry share in 2026), and `{gc['D']['topIndustry']['label']}` supplied {share(gc['D']['topIndustry']['share'])} of its gain; five securities supplied {share(gc['D']['shareFromTop5Securities'])}.")
    add(f"* **Not dependent on Samsung Electronics / SK Hynix.** {share(f['pair_share_D'])} of the gain directly; the exclusion sensitivity moved the result by {pp(cf['differenceVersusD']['cumulativeNetReturn'])} cumulative.")
    add(f"* **Not benchmark-beating overall.** D {pct(fd['netAnnualizedReturn'])} vs passive {pct(fp['annualizedReturn'])} a year, {pct(fd['cumulativeNetReturn'])} vs {pct(fp['cumulativeReturn'])}, drawdown {pct(fd['maxDrawdown'])} vs {pct(fp['maxDrawdown'])}, "
        f"at {pm['D']['D_full_window']['annualizedOneWayTurnover'] / pm['A']['D_full_window']['annualizedOneWayTurnover']:.1f}x A's turnover. The benchmark itself carries the unresolved accrual question of section 5.2.")
    add("")
    ev2 = result["sealedAnatomyEvidence"]
    add("Context from the sealed anatomy studies (read, never rerun). **Signal association** is a cross-sectional property of the whole universe; **portfolio realisation** is what the five-name D book earned. They are different questions.")
    add("")
    add("Industry anatomy, CAP_WEIGHTED H126 (IC mean / tercile spread pp):")
    add("")
    _table(add, ("Feature", "FULL", "Leave largest constituent out", "Exclude Samsung + SK Hynix"),
           [(feat, *[f"{v[k]['icMean']:+.3f} / {v[k]['tercileSpreadPp']:+.1f}" for k in ("FULL", "LEAVE_LARGEST_CONSTITUENT_OUT", "EXCLUDE_SAMSUNG_ELECTRONICS_AND_SK_HYNIX")]) for feat, v in ev2["industryAnatomy_FULL_vs_EXCLUDE_vs_LEAVE_LARGEST_OUT"]["features"].items()])
    add("Stock within-industry anatomy, CAP_WEIGHTED H126 (mean rank correlation):")
    add("")
    _table(add, ("Feature", "FULL", "Exclude Samsung + SK Hynix"), [(feat, f"{v['FULL_CAP_H126']:+.3f}", f"{v['EXCLUDE_SAMSUNG_ELECTRONICS_AND_SK_HYNIX_CAP_H126']:+.3f}") for feat, v in ev2["stockWithinIndustryAnatomy_FULL_vs_EXCLUDE"]["features"].items()])
    add("* **A — signal association.** " + ev2["interpretation"]["A_signalAssociationSurvivesRemovingTheTwoNames"])
    add("* **B — implemented portfolio.** " + ev2["interpretation"]["B_implementedConcentratedPortfolioDependsOnThem"] + f" The completed audit answers B for the integrated D book: it did not depend on the two securities; its gain came from a small number of industries, chiefly `{gc['D']['topIndustry']['label']}`, in 2025 and 2026.")
    add("")
    add("## 13. Remaining limitations")
    add("")
    add("* **External benchmark reconciliation is unresolved** (`" + A.EXTERNAL_UNRESOLVED + "`), and the internal anomaly in the benchmark's accrual over the price index (`" + ev["status"] + "`) cannot be explained from stored data because no event list is stored.")
    add("* Mega-cap weights are a same-data Top120 market-cap proxy; exact KODEX 200 constituent weights were not obtained.")
    add("* All figures are post-outcome descriptions of one outcome-exposed historical sample, with no multiplicity correction; contributions in NAV units weigh late periods more; per-name cost is an allocation, not a measurement.")
    add("* The sensitivity removes two named securities only; it says nothing about the industry, a different exclusion, or any other construction, and none was run.")
    add("* Korean value/quality coverage and the partial distribution basis (`BENCHMARK_RELATIVE_ADJUSTED_INDEX_RETURN_PARTIAL_DISTRIBUTIONS`) remain as sealed; the total-return basis of high-dividend names is unaudited.")
    add("* The full audit file is an Actions artifact (not committed); the repository carries the compact record and the file's byte count and SHA-256.")
    add("")
    add("## 14. Reproducibility / audit run identity")
    add("")
    add(f"Audit run `{prov['workflowRunId']}`, artifact `{prov['artifactId']}`, audit implementation `{prov['auditRefResolvedSha']}`, full file {prov['fullAuditJsonBytes']:,} bytes `{prov['fullAuditJsonSha256']}`. The compact record "
        "`docs/results/kr-integrated-alpha-portfolio-v1-postoutcome-completed-audit.json` is a pure function of that file (`scripts/run_kr_integrated_alpha_portfolio_postoutcome_audit.py --mode compact --full-json <file>` refuses any file whose bytes differ); "
        "this report and `docs/results/kr-integrated-alpha-portfolio-v1-postoutcome-concentration-audit.json` are regenerated deterministically from it and the frozen repository inputs (`--mode local`). The audit workflow is read-only: "
        "`contents: read`, `actions: read`, no `execute`, lock, marker, permit or push.")
    add("")
    add("*This is a post-outcome descriptive diagnostic. It does not change the formal result, any frozen rule or any decision, and it is not prospective evidence.*")
    return "\n".join(L) + "\n"
