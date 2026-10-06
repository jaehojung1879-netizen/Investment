"""Compact, permanent form of the COMPLETED post-outcome audit (Actions run 37451761441).

The full audit file the read-only workflow wrote is 539,839 bytes and stays an Actions-only artifact (it is hash-referenced here, not committed). This module turns it into the
small machine-readable record that the report is rendered from, so a future reader does not need the Actions logs. It is a pure function of the full file: it adds no number,
changes no number and reads nothing else; ``verify_full_bytes`` refuses any input whose bytes differ from the run's own printed byte count and SHA-256.

Evidence class of everything it carries is POST_OUTCOME_DIAGNOSTIC_RECONSTRUCTION (or the one POST_OUTCOME_COUNTERFACTUAL_SENSITIVITY); it is never confirmatory.
"""
from __future__ import annotations

import hashlib
import json

from . import kr_integrated_alpha_portfolio_postoutcome_audit as A

# What GitHub reported for the completed audit run, recorded by identity. The SHA-256 below is the value the run itself printed (AUDIT_FULL_JSON_SHA256) and that was
# recomputed from the file extracted from the run's job log. An earlier handoff message quoted a different digest; that was a transcription error only.
COMPLETED_RUN = {
    "workflowRunId": 37451761441, "workflow": "KR integrated alpha portfolio v1 post-outcome audit", "event": "workflow_dispatch", "conclusion": "success",
    "workflowDefinitionBranch": "main", "workflowDefinitionSha": "288204683c3ab49d8789b647dadd69a02c0a90f5",
    "auditRefRequested": "11b0d67a22be8079ef6c33a6f6bdb94e7eaaca64", "auditRefResolvedSha": "11b0d67a22be8079ef6c33a6f6bdb94e7eaaca64",
    "artifactId": 11406929754, "artifactName": "kr-integrated-alpha-portfolio-v1-postoutcome-audit-37451761441",
    "artifactArchiveDigest": "sha256:959069da0126b6aeb85f6819d488500016474d9fc7708ed6aa6604cff5397f0a", "artifactArchiveBytes": 73273,
    "fullAuditFile": "postoutcome-audit-full.json", "fullAuditJsonBytes": 539839,
    "fullAuditJsonSha256": "b316a6ef2ffbf77a0b4ce5646df5b7b6b0bfc079aa3a9e795727d0e7f7e39bbc",
    "status": "RECONSTRUCTION_REPRODUCES_THE_FORMAL_A_AND_D_PATHS",
    "howTheFileWasReadHere": ("the workflow printed the file (gzip + base64) to its job log; the authoring environment cannot download Actions artifacts (blob storage is unreachable), so "
                              "the file was decoded from the log and its byte count and SHA-256 were recomputed and found equal to the values the run printed itself"),
    "handoffDigestNote": "an earlier handoff message quoted a different SHA-256 for this file; that was a transcription error, and the run's own value above is authoritative",
}

PERIOD_KEYS = ("cumulativeNetReturn", "annualizedNetReturn", "cumulativePassiveReturn", "annualizedPassiveReturn", "maxDrawdownWithinSpan", "oneWayTurnoverSum", "annualizedOneWayTurnover",
               "costFractionSum", "replacements", "anchorRebalances", "signalUnavailableAnchors", "sessions", "years", "fromSession", "toSession")
CONCENTRATION_KEYS = ("sessions", "averageHoldings", "averageCashWeight", "meanHhi", "averageLargestNameWeightOfNav", "maximumLargestNameWeightOfNav", "meanTopIndustryShareOfInvested",
                      "maximumTopIndustryShareOfInvested", "shareOfHeldSessionsWithThreeOrMoreNamesInOneIndustry")
SUMMARY_KEYS = ("cumulativeNetReturn", "netAnnualizedReturn", "excessAnnualizedVsPassive", "maxDrawdown", "annualizedOneWayTurnover", "annualizedCostDrag", "replacements",
                "averageHoldings", "averageCashShare", "anchorRebalances", "noTradeSignalUnavailableAnchors", "firstDate", "lastDate", "sessions")


def verify_full_bytes(data):
    """The only admissible input is the exact file the completed run printed."""
    if len(data) != COMPLETED_RUN["fullAuditJsonBytes"] or hashlib.sha256(data).hexdigest() != COMPLETED_RUN["fullAuditJsonSha256"]:
        raise ValueError("FULL_AUDIT_JSON_DIFFERS_FROM_THE_COMPLETED_RUN")
    return json.loads(data)


def _pick(d, keys):
    return {k: d.get(k) for k in keys}


def _spell_tables(spells, sessions):
    """Industry frequency / average weight and the named securities' spells, straight from the reconstructed holding spells."""
    by_industry = {}
    for sp in spells:
        d = by_industry.setdefault(sp["industry"], {"spells": 0, "nameSessions": 0, "weightSessions": 0.0})
        d["spells"] += 1
        d["nameSessions"] += sp["sessionsHeld"]
        d["weightSessions"] += sp["averageWeight"] * sp["sessionsHeld"]
    total_name_sessions = sum(v["nameSessions"] for v in by_industry.values())
    industries = {k: {"spells": v["spells"], "nameSessions": v["nameSessions"], "shareOfNameSessions": v["nameSessions"] / total_name_sessions,
                      "averageWeightOfNavOverAllSessions": v["weightSessions"] / sessions} for k, v in by_industry.items()}
    named = {t: [_pick(sp, ("entryDate", "lastHeldDate", "exitedOn", "sessionsHeld", "averageWeight", "maximumWeight", "grossContributionNavUnits", "allocatedCostNavUnits", "industry",
                            "entryRankAmongSelected", "targetWeightAtEntry")) for sp in spells if sp["ticker"] == t] for t in A.NAMED}
    return dict(sorted(industries.items(), key=lambda kv: -kv[1]["nameSessions"])), named


def _book(arch, full_arch, sessions):
    spells = full_arch["holdingSpells"]
    industries, named_spells = _spell_tables(spells, sessions)
    sc = full_arch["securityContributions"]
    exits = sum(1 for sp in spells if not sp["stillHeldAtCutoff"])
    return {
        "periodMetrics": {p: _pick(v, PERIOD_KEYS) for p, v in full_arch["periodMetrics"].items()},
        "concentration": {p: _pick(v, CONCENTRATION_KEYS) for p, v in full_arch["concentration"].items()},
        "gainConcentration": full_arch["gainConcentration"],
        "namedSecurities": full_arch["namedSecurities"],
        "namedCombinedExposure": {p: {k: v for k, v in e.items() if k != "description"} for p, e in full_arch["namedExposure"].items()},
        "namedSpells": named_spells,
        "industryHolding": industries,
        "industryContribution": {p: {"industriesTouched": len(v["byIndustry"]), "byIndustry": v["byIndustry"], "top": v["top"], "bottom": v["bottom"]} for p, v in full_arch["industryContributions"].items()},
        "securityContribution": {p: {"grossContributionNavUnits": v["grossContributionNavUnits"], "transactionCostNavUnits": v["transactionCostNavUnits"], "netChangeNavUnits": v["netChangeNavUnits"],
                                     "top10Contributors": v["top10Contributors"], "top10Detractors": v["top10Detractors"], "totalTradedNotionalNavUnits": v["totalTradedNotionalNavUnits"]}
                                 for p, v in sc.items()},
        "holdings": {"spells": len(spells), "entries": len(spells), "exits": exits, "stillHeldAtCutoff": len(spells) - exits,
                     **{k: full_arch["spellSummary"][k] for k in ("distinctNames", "namesHeldInMoreThanOneSpell", "shareOfSpellsThatAreRepeats", "medianSpellSessions")},
                     "topContributors": full_arch["spellSummary"]["topContributors"], "bottomContributors": full_arch["spellSummary"]["bottomContributors"]},
        "periodReturns": {"periods": [_pick(r, ("period", "fromSession", "toSession", "cumulativeReturn", "annualizedReturn", "years")) for r in full_arch["periods"]["periods"]],
                          "calendarYears": full_arch["periods"]["calendarYears"]},
    }


def compact(full):
    """The permanent compact record. Refuses a file that is not a reconstructed-and-reproduced audit."""
    if full["status"] != COMPLETED_RUN["status"]:
        raise ValueError("AUDIT_DID_NOT_REPRODUCE_THE_FORMAL_PATHS")
    rep = full["reproduction"]
    if not all(r["reproduced"] and r["divergenceCount"] == 0 for r in rep["architectures"].values()) or rep["tolerance"] != 1e-9:
        raise ValueError("RECONSTRUCTION_NOT_REPRODUCED_AT_THE_REGISTERED_TOLERANCE")
    if full["formalIdentity"]["specSha256"] != A.FORMAL["specSha256"] or full["formalIdentity"]["resultFileSha256"] != A.FORMAL["resultFileSha256"]:
        raise ValueError("AUDIT_BELONGS_TO_A_DIFFERENT_FORMAL_RESULT")
    arch = full["attribution"]["architectures"]
    sessions = arch["D"]["periodMetrics"]["D_full_window"]["sessions"]
    formal = full["formalReported"]
    cf = full["counterfactual"]
    layer = formal["layerDecisions"]
    out = {
        "evidenceClass": A.RECONSTRUCTION, "provenance": COMPLETED_RUN,
        "reconstruction": {"status": full["status"], "tolerance": rep["tolerance"], "metricsCompared": rep["architectures"]["A"]["metricsCompared"],
                           "architectures": {a: {"reproduced": r["reproduced"], "divergenceCount": r["divergenceCount"], "monthEndNavDates": r["monthEndNavDates"]} for a, r in rep["architectures"].items()},
                           "attributionClosure": "security_contributions raised on any day whose residual cost differed from the engine's costFraction x pre-trade NAV, and on any whole-path identity miss at 1e-9; neither raised",
                           "priorAuditFacts": full["attribution"]["consistencyWithPriorAuditFacts"],
                           "sideEffectCounters": full["counters"]},
        "formalReported": {"evidenceClass": A.FORMAL_REPORTED_RESULT, "summaries": {a: _pick(formal["summaries"][a], SUMMARY_KEYS) for a in ("A", "D")},
                           "passive": _pick(formal["passive"], ("annualizedReturn", "cumulativeReturn", "maxDrawdown", "annualizedVolatility", "returnBasis", "note")),
                           "finalArchitecture": formal["finalArchitecture"], "industryLayerDecision": layer["industry"]["layerDecision"], "industryPairClasses": layer["industry"]["pairClasses"],
                           "marketLayer": {k: layer["market"][k] for k in ("S", "I+S")}, "reason": layer["reason"], "underlying": layer["underlying"],
                           "signalAvailability": {k: _pick(v, ("scheduledAnchors", "validDecisionAnchors", "unavailableAnchors", "availabilityShare")) for k, v in formal["signalAvailability"].items() if k in ("S", "I+S")}},
        "books": {a: _book(a, arch[a], sessions) for a in ("A", "D")},
        "dMinusA": {p: {**{k: v for k, v in d.items() if k not in ("topNamesAddingToDMinusA", "topNamesSubtractingFromDMinusA", "description")},
                        "topNamesAddingToDMinusA": d["topNamesAddingToDMinusA"][:8], "topNamesSubtractingFromDMinusA": d["topNamesSubtractingFromDMinusA"][:8]}
                    for p, d in full["attribution"]["dMinusA"].items()},
        "counterfactual": {
            "name": cf["name"], "labels": cf["labels"], "evidenceClass": cf["evidenceClass"], "excluded": cf["excluded"], "rule": cf["rule"], "formalDecisionsUnchanged": cf["formalDecisionsUnchanged"],
            "summary": cf["summary"], "formalD": cf["formalD"], "differenceVersusD": cf["differenceVersusD"],
            "periodMetrics": {p: _pick(v, PERIOD_KEYS) for p, v in cf["periodMetrics"].items()},
            "concentration": {p: _pick(v, CONCENTRATION_KEYS) for p, v in cf["concentration"].items()},
            "gainConcentration": cf["gainConcentration"], "namedSecurities": cf["namedSecurities"]["securities"],
            "holdings": {k: cf["spellSummary"][k] for k in ("spells", "distinctNames", "namesHeldInMoreThanOneSpell", "shareOfSpellsThatAreRepeats", "medianSpellSessions")},
            "topContributors": cf["spellSummary"]["topContributors"][:8], "bottomContributors": cf["spellSummary"]["bottomContributors"][:8],
            "signalAvailability": _pick(cf["signalAvailability"], ("scheduledAnchors", "validDecisionAnchors", "unavailableAnchors", "availabilityShare", "meetsStudyCoverage", "unavailableCauses"))},
    }
    return A._round_floats(out)
