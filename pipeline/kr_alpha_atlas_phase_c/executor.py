"""One integrated scientific execution; partial blocked components remain explicit."""

from __future__ import annotations

import resource
import time
from dataclasses import asdict
from pathlib import Path
from threadpoolctl import threadpool_limits


from pipeline.kr_model_raw_snapshot import immutable_bytes
from . import economics, interactions, models, statistics
from .contract import EVIDENCE, VERDICTS, canonical, digest
from .labels import Counters, attrition, build_labels

SYNTHETIC_EVIDENCE = "SYNTHETIC_SOFTWARE_VALIDATION_ONLY"


class Budget:
    def __init__(self, spec):
        self.start = time.monotonic()
        self.config = spec["compute"]
        self.fits = 0
        self.projections = 0
        self.slopes = 0

    def check(self):
        if time.monotonic() - self.start > self.config["wallSeconds"]:
            raise RuntimeError("REGISTERED_WALL_LIMIT")
        if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024 > self.config["memoryBytes"]:
            raise RuntimeError("REGISTERED_MEMORY_LIMIT")

    def fit(self):
        self.check()
        self.fits += 1
        if self.fits > self.config["maxPredictiveFits"]:
            raise RuntimeError("REGISTERED_MODEL_FIT_LIMIT")

    def date_fit(self, kind):
        self.check()
        attribute = "projections" if kind == "projection" else "slopes"
        limit = "maxProjectionFits" if kind == "projection" else "maxConditionalSlopeFits"
        setattr(self, attribute, getattr(self, attribute) + 1)
        if getattr(self, attribute) > self.config[limit]:
            raise RuntimeError("REGISTERED_DATE_FIT_LIMIT")


def corrections(level1, level2, level3, spec):
    for family in sorted({f["family"] for f in spec["eligibleFeatures"]}):
        readings = {
            k: v
            for k, v in level1.items()
            if v["family"] == family and v["horizon"] in spec["inference"]["inferentialHorizons"]
        }
        q = statistics.adjust({k: v["statistics"]["tercileSpread"]["p"] for k, v in readings.items()}, "BY")
        for k, v in readings.items():
            v["adjustedP"] = q[k]
            v["multiplicityScope"] = family
    cells = {k: v for by_h in level2.values() for k, v in by_h["comparisons"].items()}
    adjusted = statistics.adjust({k: v["p"] for k, v in cells.items()}, "HOLM")
    for k, v in cells.items():
        v["adjustedP"] = adjusted[k]
    q = statistics.adjust({k: v["p"] for k, v in level3.items()}, "HOLM")
    for k, v in level3.items():
        v["adjustedP"] = q[k]
    return {
        "level1": {
            f: sum(
                v["family"] == f and v["horizon"] in spec["inference"]["inferentialHorizons"] for v in level1.values()
            )
            for f in sorted({v["family"] for v in level1.values()})
        },
        "level2Slots": len(cells),
        "level3Slots": len(level3),
        "blockedSlotsRetainedAsP1": True,
    }


def earlier_verdict(reading, comparison, residual=None):
    stat = reading["statistics"]["tercileSpread"]
    if stat["inferenceStatus"].startswith("BLOCKED") or stat["inferenceStatus"] == "DESCRIPTIVE_UNCALIBRATED":
        return "BLOCKED"
    if reading.get("adjustedP", 1) > 0.10 or stat["estimate"] <= 0 or stat["interval"]["lower"] <= 0:
        return "NO_DEVELOPMENT_EVIDENCE"
    if not reading["stability"]["stable"]:
        return "UNSTABLE"
    information = comparison["pairedMseImprovement"]
    if (
        comparison.get("identicalPredictionsOnCommonSample")
        and information["nDates"] >= 52
        and information["evaluableShare"] >= 0.8
    ):
        return "REDUNDANT"
    if any(
        comparison[k]["inferenceStatus"].startswith("BLOCKED")
        for k in ("pairedMseImprovement", "pairedRankWeightedSpreadImprovement")
    ):
        return "BLOCKED"
    if comparison["adjustedP"] > 0.05 or not comparison["positive"]:
        return "REDUNDANT"
    if residual is not None:
        information = residual["residualized"]["statistics"]["tercileSpread"]
        if information["nDates"] < 52 or information["evaluableShare"] is None or information["evaluableShare"] < 0.8:
            return "REDUNDANT"
        if information["estimate"] is None or information["estimate"] <= 0:
            return "REDUNDANT"
    return None


def economic_verdict(economic):
    policies = {k: v for k, v in economic["policies"].items() if "_LOW_LIQUIDITY" not in k}
    if any(v["status"] == "BLOCKED" for v in policies.values()):
        return "BLOCKED"
    if any(v["netExcess"] is None or v["netExcess"] <= 0 for v in policies.values()):
        return "NOT_ECONOMIC"
    if any(v["arithmeticAttribution"]["C_stockSelection"] <= 0 for k, v in policies.items() if k.startswith("SLOTS")):
        return "NOT_ECONOMIC"
    if economic["benchmarkClaimStatus"] != "VERIFIED":
        return "BLOCKED"
    return "INDEPENDENT_DEVELOPMENT_SUPPORT"


@threadpool_limits.wrap(limits=1)
def execute(data, spec, permit, *, counters=None, budget=None, progress=None):
    permit.require()
    progress = progress or (lambda stage: None)
    progress("VALIDATE_AND_LABELS")
    if not permit.synthetic and permit.source_identity != data.source_identity:
        raise ValueError("FORMAL_PERMIT_IDENTITY_MISMATCH")
    counters = counters or Counters()
    budget = budget or Budget(spec)
    evidence_class = SYNTHETIC_EVIDENCE if permit.synthetic else EVIDENCE
    readiness = data.validate_features(spec)
    books = {}
    for h in spec["horizons"]:
        budget.check()
        books[h] = build_labels(data, h, spec["developmentCutoff"], permit, counters)
    l1 = {}
    l2 = {}
    residual = {}
    fits = []
    redundancy = {}
    predictions = {}
    ranks = statistics.percentiles(data)
    for h, book in books.items():
        progress(f"ANALYZE_H{h}")
        predictions[h], audit, red = models.predictions(data, book, spec, counters, permit, budget)
        fits.extend(audit)
        redundancy[str(h)] = red
        l2[str(h)] = models.incremental(data, book, predictions[h], spec)
        for feature in spec["eligibleFeatures"]:
            if h not in feature["registeredHorizons"]:
                continue
            budget.check()
            key = f"{feature['featureId']}_H{h}"
            l1[key] = statistics.factor_reading(data, book, feature, spec)
            residual[key] = models.residual_and_slopes(data, book, feature, spec, ranks=ranks, budget=budget)
    progress("INTERACTIONS_AND_DECISIONS")
    l3 = interactions.analyze(data, books, spec)
    multiplicity = corrections(l1, l2, l3, spec)
    l4 = {}
    verdicts = {}
    nominations = []
    earlier_passes = {}
    for feature in spec["eligibleFeatures"]:
        h = feature["registeredHorizons"][0]
        key = f"{feature['featureId']}_H{h}"
        pair = l2[str(h)]["comparisons"]["ADD_" + feature["family"] + "_H" + str(h)]
        verdict = earlier_verdict(l1[key], pair, residual[key])
        earlier_passes[feature["featureId"]] = verdict is None
        if verdict is None:
            budget.check()
            l4[key] = economics.evaluate(data, books[h], feature, predictions[h], spec)
            verdict = economic_verdict(l4[key])
        verdicts[feature["featureId"]] = {
            "verdict": verdict,
            "primaryHorizon": h,
            "level1Key": key,
            "level2Key": "ADD_" + feature["family"] + "_H" + str(h),
            "level4Status": "EXECUTED" if key in l4 else "NOT_TRIGGERED",
            "evidenceClass": evidence_class,
        }
        if verdict == "INDEPENDENT_DEVELOPMENT_SUPPORT":
            nominations.append(feature["featureId"])
    interaction_verdicts = {}
    for ix in spec["interactions"]:
        key = ix["interactionId"]
        r = l3[key]
        components = [f for f in ix["features"] if f in verdicts]
        supported = r["adjustedP"] <= 0.05 and r["p"] is not None
        candidates = [f for f in components if earlier_passes[f]]
        reason = "EARLIER_CONDITIONS_NOT_MET"
        if r["p"] is None:
            verdict = "BLOCKED"
            reason = r["status"]
        elif not components:
            verdict = "BLOCKED"
            reason = "CONTROL_ONLY_ALREADY_TESTED_COMPONENTS_NO_NEW_COMPONENT_GATE"
        elif not supported or not candidates:
            verdict = "NO_DEVELOPMENT_EVIDENCE"
        else:
            chosen = next(f for f in spec["eligibleFeatures"] if f["featureId"] == candidates[0])
            h = ix["horizon"]
            budget.check()
            l4[key] = economics.evaluate(data, books[h], chosen, predictions[h], spec, interaction=ix)
            verdict = economic_verdict(l4[key])
            reason = "REGISTERED_CONDITIONAL_POLICY_EXECUTED"
            if verdict == "INDEPENDENT_DEVELOPMENT_SUPPORT":
                nominations.append(key)
        interaction_verdicts[key] = {
            "verdict": verdict,
            "eligibleComponents": candidates,
            "reason": reason,
            "level4Status": "EXECUTED" if key in l4 else "NOT_TRIGGERED",
            "noAdditionalHypotheses": True,
        }
    result = {
        "schemaVersion": 1,
        "studyId": spec["studyId"],
        "evidenceClass": evidence_class,
        "mode": "SYNTHETIC" if permit.synthetic else "FORMAL_DEVELOPMENT",
        "registrationSha256": digest(spec),
        "inputIdentity": data.source_identity,
        "tradingValueBasis": spec["tradingValueBasis"],
        "cutoff": spec["developmentCutoff"],
        "readiness": readiness,
        "benchmarkIntegrity": spec["benchmarkIntegrity"],
        "labels": {
            "attrition": attrition(data, books),
            "horizons": spec["horizons"],
            "validityRecords": {
                str(h): b.table.astype(object).where(b.table.notna(), None).to_dict("records") for h, b in books.items()
            },
        },
        "level1": l1,
        "level2": l2,
        "residualInformation": residual,
        "trainingOnlyRedundancy": redundancy,
        "level3": l3,
        "level4": l4,
        "multiplicity": multiplicity,
        "verdicts": verdicts,
        "interactionVerdicts": interaction_verdicts,
        "prospectiveNominations": nominations,
        "modelAudit": fits,
        "compute": {
            "predictiveFits": budget.fits,
            "projectionFits": budget.projections,
            "conditionalSlopeFits": budget.slopes,
            "maxPredictiveFits": spec["compute"]["maxPredictiveFits"],
        },
        "counters": asdict(counters),
        "limitations": spec["sourceLimitations"],
        "closure": "Phase D must close KR historical exploration regardless of nominations; subsequent confirmation is prospective only.",
    }
    progress("SCHEMA_AND_PERSISTENCE_READY")
    validate_result(result, spec)
    budget.check()
    return result


def validate_result(result, spec):
    required = {
        "schemaVersion",
        "studyId",
        "evidenceClass",
        "mode",
        "registrationSha256",
        "inputIdentity",
        "tradingValueBasis",
        "cutoff",
        "readiness",
        "benchmarkIntegrity",
        "labels",
        "level1",
        "level2",
        "residualInformation",
        "trainingOnlyRedundancy",
        "level3",
        "level4",
        "multiplicity",
        "verdicts",
        "interactionVerdicts",
        "prospectiveNominations",
        "modelAudit",
        "compute",
        "counters",
        "limitations",
        "closure",
    }
    if set(result) != required or result["evidenceClass"] != (
        SYNTHETIC_EVIDENCE if result["mode"] == "SYNTHETIC" else EVIDENCE
    ):
        raise ValueError("INCOMPLETE_RESULT_SCHEMA")
    if (
        len(result["level1"]) != spec["compute"]["featureHorizonTests"]
        or len(result["level3"]) != 6
        or len(result["verdicts"]) != 38
    ):
        raise ValueError("MISSING_REGISTERED_RESULT_SLOT")
    if result["multiplicity"]["level2Slots"] != 30 or result["multiplicity"]["level3Slots"] != 6:
        raise ValueError("MULTIPLICITY_SCOPE_CHANGED")
    if any(v["verdict"] not in VERDICTS for v in result["verdicts"].values()):
        raise ValueError("UNREGISTERED_VERDICT")
    if result["mode"] == "SYNTHETIC" and any(
        result["counters"][k] for k in ("realOutcomeReads", "realLabels", "realModelFits")
    ):
        raise ValueError("SYNTHETIC_REAL_OUTCOME_CONTAMINATION")
    if any(
        v["horizon"] in (63, 252) and v["statistics"]["tercileSpread"]["p"] is not None
        for v in result["level1"].values()
    ):
        raise ValueError("UNSUPPORTED_INFERENTIAL_HORIZON")
    from .schema import validate
    from .contract import ROOT, RESULT_SCHEMA, read

    validate(result, read(ROOT, RESULT_SCHEMA))
    canonical(result)  # Recursively refuses NaN/infinity, including nested audit fields.
    return result


def persist(result, root, provenance):
    root = Path(root)
    raw = canonical(result) + b"\n"
    immutable_bytes(root / "result.json", raw)
    immutable_bytes(root / "provenance.json", canonical(provenance) + b"\n")
    immutable_bytes(
        root / "checksums.json",
        canonical({"result.json": digest_bytes(raw), "provenance.json": digest_bytes(canonical(provenance) + b"\n")})
        + b"\n",
    )
    return {"resultSha256": digest_bytes(raw), "durable": True, "path": str(root)}


def digest_bytes(raw):
    import hashlib

    return hashlib.sha256(raw).hexdigest()
