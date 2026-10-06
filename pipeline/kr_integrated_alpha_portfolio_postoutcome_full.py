"""Read-only reconstruction half of the post-outcome concentration audit (runs only against the exact formal artifacts).

It replays the FROZEN model code (the formal execution commit's own functions, unchanged) over the exact raw snapshot, for architectures A and D only, and proves the
replay reproduces the formal result BEFORE it attributes anything. It never calls ``execute``, never creates, moves or deletes an execution lock, never calls
``load_market_values`` / ``claim_execution_lock`` / ``write_execution_marker`` and never writes into ``docs/results``: its only output is the file the caller names.

The one authorised counterfactual (D without Samsung Electronics and SK Hynix) is run through the same frozen functions inside
``kr_integrated_alpha_portfolio_postoutcome_audit.exclude_named_from_selection``.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import kr_integrated_alpha_portfolio_execution as E
from . import kr_integrated_alpha_portfolio_postoutcome_audit as A
from . import kr_integrated_alpha_portfolio_replay as R

ROOT = Path(__file__).resolve().parents[1]
ARCHITECTURES = ("A", "D")                                            # D is the question; A is its control (same book without the Industry layer)
LAYER = {"A": "S", "D": "I+S"}


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_formal_result(path, root=ROOT):
    """The formal result file must be byte-identical to the one the formal run's own log reported, and must belong to the frozen spec."""
    digest = sha256_file(path)
    if digest != A.FORMAL["resultFileSha256"]:
        raise ValueError("FORMAL_RESULT_BYTES_DIFFER: " + digest)
    result = json.loads(Path(path).read_text())
    spec, sha = E.load_spec(root)
    if sha != A.FORMAL["specSha256"] or result.get("specSha256") != sha:
        raise ValueError("FORMAL_RESULT_BELONGS_TO_A_DIFFERENT_SPEC")
    return result, spec, sha


def membership_by_signal(bundle, root):
    """The industry each member had at each signal date, from the same frozen membership functions the formal run used."""
    intervals, crosswalk, ends = E.IE.load_membership_inputs(root)
    table = E.I.membership_table(bundle["schedule"], intervals, crosswalk, ends)
    return {date: {r.ticker: (r.industry if isinstance(r.industry, str) else "UNCLASSIFIED") for r in group.itertuples()} for date, group in table.groupby("date")}


def replay_paths(bundle, spec, architectures=ARCHITECTURES):
    ctx = R.Context(bundle["prices"], bundle["market"], bundle["days"], spec["benchmark"])
    decisions = {"S": {s: p["S"] for s, p in bundle["decisions"].items()}, "I+S": {s: p["I+S"] for s, p in bundle["decisions"].items()}}
    paths = {}
    for arch in architectures:
        result = R.replay_architecture(arch, decisions[LAYER[arch]], bundle["anchors"], None, ctx)
        if not result["complete"]:
            raise ValueError("RECONSTRUCTED_PATH_INCOMPLETE: " + arch + ": " + str(result.get("reason")))
        paths[arch] = result["path"]
    return paths, ctx, decisions


def strategy_periods(path):
    nav = {r["date"]: r["nav"] for r in path}
    first = path[0]["date"]
    nav_with_open = dict(nav)
    nav_with_open[first] = 1.0                                          # the opening level before the first session's trade and cost
    return {"periods": A.period_decomposition(nav_with_open, first, path[-1]["date"]), "calendarYears": A.calendar_year_returns(nav_with_open, first, path[-1]["date"])}


def attribute(arch, path, ctx, membership, anchors, decisions_by_signal):
    spans = A.record_spans(path)
    industry_of = A.industry_map_provider(membership, anchors, path)
    contributions, daily = A.security_contributions(path, lambda t, day, prev: R.mark_price(ctx, t, day, prev), spans)
    industries = A.industry_contributions(daily, industry_of, spans)
    spells = A.holding_spells(path, industry_of, daily, decisions_by_signal, anchors)
    report = {"concentration": A.holdings_concentration(path, industry_of, spans), "namedExposure": A.named_exposure(path, spans=spans), "securityContributions": contributions,
              "industryContributions": industries, "periods": strategy_periods(path), "periodMetrics": A.period_metrics(path, spans),
              "namedSecurities": A.named_security_report(path, daily, contributions, decisions_by_signal, anchors), "gainConcentration": A.gain_concentration(contributions, industries),
              "holdingSpells": spells, "spellSummary": A.spell_summary(spells)}
    return report, contributions


def run(input_root, formal_result_path, output, root=ROOT):
    if not input_root or not formal_result_path:
        raise ValueError("FULL_MODE_REQUIRES_INPUTS_AND_FORMAL_RESULT")
    formal, spec, sha = verify_formal_result(formal_result_path, root)
    if E.X.input_identity(input_root)["sha256"] != spec["input"]["identitySha256"]:
        raise ValueError("INPUT_IDENTITY_MISMATCH")
    counters = E.Counters()
    bundle = E.build_signal_bundle(input_root, spec, root, counters)
    extracted = A.extract_formal(formal)
    paths, ctx, decisions = replay_paths(bundle, spec)
    reproduction = {}
    for arch in ARCHITECTURES:
        summary = R.summarize_path(paths[arch])
        reproduction[arch] = A.reproduction_check(extracted["summaries"][arch], extracted["monthEndNav"][arch], summary, E.month_end_nav(paths[arch]))
    report = {"studyId": A.STUDY, "scientificStatus": A.SCIENTIFIC_STATUS, "statement": A.STATEMENT, "formalIdentity": A.FORMAL, "formalReported": extracted,
              "reproduction": {"evidenceClass": A.RECONSTRUCTION, "tolerance": 1e-9, "architectures": reproduction}, "counters": E.asdict(counters)}
    if not all(r["reproduced"] for r in reproduction.values()):
        first = next(a for a, r in reproduction.items() if not r["reproduced"])
        report["status"] = A.D_PATH_RECONSTRUCTION_MISMATCH
        report["firstDivergence"] = {"architecture": first, **reproduction[first]["firstDivergence"]}
        report["attribution"] = A.NOT_RUN
        return _write(report, output)
    report["status"] = "RECONSTRUCTION_REPRODUCES_THE_FORMAL_A_AND_D_PATHS"
    membership = membership_by_signal(bundle, root)
    attribution, contributions = {}, {}
    for arch in ARCHITECTURES:
        attribution[arch], contributions[arch] = attribute(arch, paths[arch], ctx, membership, bundle["anchors"], decisions[LAYER[arch]])
    spans = A.record_spans(paths["D"])
    report["attribution"] = {"evidenceClass": A.RECONSTRUCTION, "architectures": attribution,
                             "dMinusA": A.d_minus_a(decisions["S"], decisions["I+S"], bundle["anchors"], paths["A"], paths["D"], contributions["A"], contributions["D"], spans)}
    full = report["attribution"]["dMinusA"]["D_full_window"]
    report["attribution"]["consistencyWithPriorAuditFacts"] = {
        "evidenceClass": A.RECONSTRUCTION, "note": "facts quoted from the earlier read-only audit, compared here with the reconstruction rather than trusted",
        "expectedAnchorsWithBothBooksAvailable": 108, "reconstructedAnchorsWithBothBooksAvailable": full["anchorsBothBooksHadAValidDecision"],
        "expectedAnchorsWithIdenticalSelection": 0, "reconstructedAnchorsWithIdenticalSelection": full["anchorsWithIdenticalSelection"],
        "expectedMeanDifferingNames": 3.2407, "reconstructedMeanDifferingNames": full["meanDifferingNames"],
        "agrees": full["anchorsBothBooksHadAValidDecision"] == 108 and full["anchorsWithIdenticalSelection"] == 0
                  and full["meanDifferingNames"] is not None and abs(full["meanDifferingNames"] - 3.2407) < 5e-4}
    # The ONE authorised counterfactual: the frozen functions, with the two named tickers removed after scoring and before selection.
    counters_excl = E.Counters()
    with A.exclude_named_from_selection():
        bundle_excl = E.build_signal_bundle(input_root, spec, root, counters_excl)
    paths_excl, ctx_excl, decisions_excl = replay_paths(bundle_excl, spec, ("D",))
    path_d_excl = paths_excl["D"]
    attribution_excl, _ = attribute("D", path_d_excl, ctx_excl, membership_by_signal(bundle_excl, root), bundle_excl["anchors"], decisions_excl["I+S"])
    summary_d, summary_excl = R.summarize_path(paths["D"]), R.summarize_path(path_d_excl)
    keys = ("cumulativeNetReturn", "netAnnualizedReturn", "maxDrawdown", "annualizedOneWayTurnover", "totalCostFractionOfNav", "averageHoldings")
    report["counterfactual"] = {
        "evidenceClass": A.COUNTERFACTUAL, "name": "D_EXCLUDE_SAMSUNG_HYNIX", "excluded": list(A.NAMED),
        "rule": "005930.KS and 000660.KS removed after stock and industry scoring and before selection; every other frozen rule unchanged; next eligible ranked names fill the book",
        "summary": {k: summary_excl[k] for k in keys}, "formalD": {k: summary_d[k] for k in keys},
        "differenceVersusD": {k: summary_excl[k] - summary_d[k] for k in keys if summary_excl[k] is not None and summary_d[k] is not None},
        "periods": strategy_periods(path_d_excl), "periodMetrics": attribution_excl["periodMetrics"], "concentration": attribution_excl["concentration"],
        "securityContributions": attribution_excl["securityContributions"], "namedSecurities": attribution_excl["namedSecurities"],
        "gainConcentration": attribution_excl["gainConcentration"], "spellSummary": attribution_excl["spellSummary"],
        "labels": ["POST_OUTCOME_DESCRIPTIVE_SENSITIVITY", "NOT_CONFIRMATORY", "NOT_ELIGIBLE_FOR_MODEL_SELECTION"],
        "signalAvailability": E.availability_audit(bundle_excl["decisions"], bundle_excl["anchors"], bundle_excl["depth"])["I+S"],
        "formalDecisionsUnchanged": True}
    return _write(report, output)


def _write(report, output):
    A.assert_clean_language(report)
    path = Path(output)
    path.mkdir(parents=True, exist_ok=True)
    target = path / "postoutcome-audit-full.json"
    text = json.dumps(A._round_floats(report), sort_keys=True, indent=2, ensure_ascii=False, default=str) + "\n"
    target.write_text(text)
    return {"status": report["status"], "file": str(target), "sha256": hashlib.sha256(text.encode()).hexdigest(), "bytes": len(text.encode())}

