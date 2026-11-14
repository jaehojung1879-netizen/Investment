"""Track B re-audit: recount the US single-stock survivorship gap from committed evidence.

Reads only files already committed on main (no network, no price, no return):
- docs/results/alpha-opportunity-model-v3-survivorship-audit.json (identity-resolved US universe)
- data/us-unpriced-members.json (ticker-level unpriced count)
- docs/us-readiness/us-departed-dataset-admission-audit-v1.json (public price recovery admission)
- data/replay-corporate-actions.json (terminal consideration book)
Checks the accounting identities between them and writes results/track-b-reaudit.json.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FILES = {
    "survivorship": "docs/results/alpha-opportunity-model-v3-survivorship-audit.json",
    "unpriced": "data/us-unpriced-members.json",
    "admission": "docs/us-readiness/us-departed-dataset-admission-audit-v1.json",
    "corporateActions": "data/replay-corporate-actions.json",
}


def reaudit() -> dict:
    data, hashes = {}, {}
    for k, rel in FILES.items():
        raw = (ROOT / rel).read_bytes()
        hashes[rel] = hashlib.sha256(raw).hexdigest()
        data[k] = json.loads(raw)
    us = data["survivorship"]["regions"]["US"]
    uni, samp, ident = us["universe"], us["sampleSurvivorship"], us["identity"]["categoryCounts"]
    adm = data["admission"]
    unp = data["unpriced"]
    us_actions = [a for a in data["corporateActions"]["actions"] if a.get("region") == "US"]
    checks = {
        "currentPlusDepartedEqualsResolvedUnion": uni["currentMembers"] + uni["departedMembers"]
        == data["survivorship"]["usCountReconciliation"]["thisAudit"]["identityResolvedUnion"],
        "departedSplitsIntoPricedRenamedAndNoPanel": samp["departedPricedByOwnHistory"] + samp["departedPricedViaVerifiedRename"]
        + samp["noPanelDeparted"] == uni["departedMembers"],
        "noCurrentMemberLacksAPanel": samp["noPanelCurrent"] == 0,
        "noTerminatedCompanyInThePricedUsSample": us["terminations"]["terminatedInPanel"] == 0,
        "admissionAuditCoversTheSameNoPanelIdentities": adm["corporateActionUnresolvedIdentities"] == samp["noPanelDeparted"],
        "tickerLevelUnpricedAllDelisted": unp["unpricedAllHaveDelistedDate"] is True,
    }
    if not all(checks.values()):
        raise RuntimeError(f"TRACK_B_IDENTITY_BROKEN {checks}")
    return {
        "status": "TRACK_B_BLOCKED_NO_ELIGIBLE_DELISTING_INCLUSIVE_SOURCE",
        "independentHistoricalPerformanceComputed": False,
        "inputSha256": hashes,
        "identityChecks": checks,
        "usUniverse": {"resolvedIdentities": uni["currentMembers"] + uni["departedMembers"],
                       "current": uni["currentMembers"], "departed": uni["departedMembers"],
                       "departedPricedByOwnHistory": samp["departedPricedByOwnHistory"],
                       "departedPricedViaVerifiedRename": samp["departedPricedViaVerifiedRename"],
                       "departedNoPanel": samp["noPanelDeparted"],
                       "pNoPanelGivenDepartedPct": samp["pNoPanelGivenDeparted"],
                       "departedExitReasonUnresolved": samp["departedExitIdentityUnresolved"],
                       "identityCategories": ident,
                       "tickerLevel": {"members": unp["usMembers"], "servedByPanel": unp["servedByPanel"], "unpriced": unp["unpriced"]}},
        "departedOnlyNoPanelPctByYear": {y: v["departedOnlyNoPanelPct"] for y, v in us["memberDatesByYear"].items()},
        "publicPriceRecovery": {"verdict": adm["datasetGateVerdict"], "originalMissingSessions": adm["originalMissingSessions"],
                                "candidateRecoveredSessions": adm["candidateRecoveredSessions"],
                                "finalAdmittedSessions": adm["finalAdmittedSessions"],
                                "highestValueBlocker": adm["highestValueBlocker"]},
        "terminalConsideration": {"usActionsCited": len(us_actions), "examples": [a["ticker"] for a in us_actions],
                                  "departedWithoutCitedConsideration": samp["noPanelDeparted"]},
        "pitMembership": {"source": "derived (unofficial) S&P 500 snapshot history pinned in replay-v16; no announcement dates, CIK only from 2023-04-13",
                          "gapsOver45Days": adm["membershipLimitation"]["gapsOver45Days"],
                          "maxGapDays": adm["membershipLimitation"]["maxGapDays"]},
        "fundamentals": "Finnhub-served SEC filings with PIT acceptance dates exist for priced names; departed no-panel names are not covered by an admitted price basis, so no factor on them can be valued",
        "conclusion": ("Any S&P 500 history computed from the priced panel is conditional on survival: 212 of 324 departed identities "
                       "(65.4%) have no usable price and none of the priced US sample contains a failed or acquired company. "
                       "No Track B performance is computed until a licensed delisting-inclusive source with dated corporate "
                       "actions and terminal consideration is secured."),
    }


if __name__ == "__main__":
    out = reaudit()
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "track-b-reaudit.json").write_text(json.dumps(out, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    print(json.dumps(out["usUniverse"], indent=1))
