"""Six fixed selected-anchor sizing checks only; no future-return calculation."""
import gzip
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import current_champion_decisions as C  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "docs/results/regional-standalone-paths.json.gz"
SHA = "7a09751f99f5d892821cac6bbb4f28359049d58364cb40db1814fac4f93210cb"


def audit():
    raw = (ROOT/SOURCE).read_bytes()
    if hashlib.sha256(raw).hexdigest() != SHA:
        raise ValueError("SEALED_ANCHOR_BYTES_CHANGED")
    frozen = json.loads(gzip.decompress(raw))
    checks = []
    cfg = C.methodology()
    for region in ("KR", "US"):
        for index in (0, 77, 154):
            anchor = frozen["regional"][region][index]
            # Projection is limited to recorded selection/sizing inputs. The
            # stored selected set implies POSITIVE; the full pool isn't available.
            inputs = [{**{k: r.get(k) for k in (
                "ticker", "region", "sector", "alphaPercentile", "evidenceCoverage", "entryState")},
                "longTermResearchView": "POSITIVE", "risk": {"downsideVolPct": r["downsideVolPct"]}}
                for r in anchor["selected"]]
            decision = C.allocation(region, inputs, cfg, {"regime": anchor["macroRegime"]})["C1"]
            expected_scores = {r["ticker"]: r["convictionScore"] for r in anchor["selected"]}
            actual_scores = {r["ticker"]: r["convictionScore"] for r in decision["holdings"]}
            match = (decision["stockWeights"] == anchor["weights"]
                     and decision["residualWeightPct"] == anchor["cashPct"] and actual_scores == expected_scores)
            checks.append({"region": region, "anchorIndex": index, "signalDate": anchor["signalDate"],
                           "executionDate": anchor["date"], "match": match,
                           "inputSha256": C.digest(inputs), "weights": decision["stockWeights"],
                           "cashPct": decision["residualWeightPct"], "convictionScores": actual_scores})
    return {"schema": "CURRENT_CHAMPION_SELECTED_SET_PARITY_V1", "sourcePath": SOURCE,
            "sourceFileSha256": SHA, "baseMain": "82b1aac4b2441f076064830b6af776f1cda1b0fe",
            "engineSha256": C.ENGINE_SHA, "configurationFileSha256": C.CONFIG_SHA,
            "scope": "SIX_FIXED_SELECTED_SET_SIZING_AND_SCORE_CHECKS_ONLY",
            "completeHistoricalCandidatePoolReproduced": False,
            "historicalExecutionSequenceReproduced": False, "futureReturnsCalculated": 0,
            "newModelFits": 0, "allChecksPass": all(r["match"] for r in checks), "checks": checks,
            "limitations": C.LIMITATIONS}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: audit_current_champion_parity.py OUTPUT_JSON")
    output = Path(sys.argv[1]).resolve()
    if any(output.is_relative_to(ROOT/p) for p in (
            "docs/results", "docs/research-specs", "research_specs", "data/research", "ledger")):
        raise ValueError("SEALED_OUTPUT_DIRECTORY_FORBIDDEN")
    result = audit()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(C.canonical(result)+b"\n")
    if not result["allChecksPass"]:
        raise SystemExit(1)
