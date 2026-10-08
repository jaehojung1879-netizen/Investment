"""kr-alpha-atlas — the master information registry of the KR Alpha Research Completion Program: loader, validator, summary and map renderer.

`research_specs/kr-alpha-atlas-registry-v1.json` lists every candidate feature in ten information families with its economic mechanism, source,
existing code, point-in-time status, history, missingness, survivorship risk, prior evidence and data readiness. This module enforces the
registry's rules so that a readiness status can never be read as alpha evidence, a feature without point-in-time data can never be marked ready, a
feature a sealed study already measured can never be labelled untested, and a cost or eligibility quantity can never also enter an alpha model.

Pure: reads the registry and checks that referenced files exist. It reads no price, filing or outcome and computes no statistic.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = "research_specs/kr-alpha-atlas-registry-v1.json"
MAP_PATH = "docs/kr-alpha-atlas-information-map.md"
FAMILY_LETTERS = tuple("ABCDEFGHIJ")
REQUIRED_FEATURE_FIELDS = (
    "featureId", "family", "economicMechanism", "source", "sourceClass", "existingImplementation", "pitStatus", "availableFromSemantics",
    "historyCoverage", "missingnessStatus", "survivorshipRisk", "existingResearchStatus", "priorEvidenceReference", "incrementalInformationHypothesis",
    "primaryHorizon", "role", "readinessStatus", "blockingReason", "nextAction", "overlapsWith", "limitations")
NON_EMPTY_TEXT = ("economicMechanism", "source", "availableFromSemantics", "historyCoverage", "incrementalInformationHypothesis", "nextAction")
USABLE = ("READY", "DERIVABLE_FROM_EXISTING_DATA", "ALREADY_TESTED")
MEASURED = ("PRIOR_POSITIVE_DEVELOPMENT", "PRIOR_NEGATIVE_DEVELOPMENT", "PRIOR_INCONCLUSIVE")
MODEL_ROLES = ("ALPHA_CANDIDATE", "CONTROL")
INTERACTION_ROLES = ("ALPHA_CANDIDATE", "CONTROL", "CONTEXT_CONDITIONING")
# A data/readiness status is not an investment verdict, and a development reading is not confirmation. These words never appear in a registry value.
FORBIDDEN_VERDICT_WORDS = ("CONFIRMED_ALPHA", "VALIDATED_ALPHA", "PROMOTE", "PROMOTION_ELIGIBLE", "BEST_FEATURE", "WINNER", "PROVEN", "LIVE_VALIDATED_ALPHA")


def load(root=ROOT):
    return json.loads((Path(root) / REGISTRY_PATH).read_text(encoding="utf-8"))


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield str(k)
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def validate(registry, root=ROOT):
    """Raise ValueError naming the first broken rule; return True otherwise."""
    root = Path(root)
    readiness, prior_states, roles = set(registry["readinessStatuses"]), set(registry["priorEvidenceStatuses"]), set(registry["roles"])
    safe, unsafe = set(registry["pitStatuses"]["safe"]), set(registry["pitStatuses"]["unsafe"])
    families, priors = registry["families"], registry["priorStudies"]
    if sorted(families) != list(FAMILY_LETTERS):
        raise ValueError("FAMILIES_MUST_BE_EXACTLY_A_TO_J")
    for text in _strings(registry):
        if any(word in text.upper() for word in FORBIDDEN_VERDICT_WORDS):
            raise ValueError("VERDICT_VOCABULARY_IN_REGISTRY: " + text[:80])
    for sid, meta in priors.items():
        if not (root / meta["resultPath"]).exists():
            raise ValueError("PRIOR_STUDY_RESULT_MISSING: " + sid)
    features = {}
    for f in registry["features"]:
        missing = [k for k in REQUIRED_FEATURE_FIELDS if k not in f]
        if missing:
            raise ValueError("FEATURE_FIELD_MISSING: %s %s" % (f.get("featureId"), missing))
        fid = f["featureId"]
        if fid in features:
            raise ValueError("DUPLICATE_FEATURE: " + fid)
        features[fid] = f
        if f["family"] not in families or not fid.startswith(f["family"]):
            raise ValueError("FEATURE_FAMILY_MISMATCH: " + fid)
        for key in NON_EMPTY_TEXT:
            if not isinstance(f[key], str) or not f[key].strip():
                raise ValueError("FEATURE_TEXT_EMPTY: %s %s" % (fid, key))
        if f["readinessStatus"] not in readiness or f["existingResearchStatus"] not in prior_states or f["role"] not in roles:
            raise ValueError("FEATURE_STATUS_OUTSIDE_VOCABULARY: " + fid)
        if f["pitStatus"] not in safe | unsafe or f["missingnessStatus"] not in registry["missingnessStatuses"] \
                or f["survivorshipRisk"] not in registry["survivorshipRisks"]:
            raise ValueError("FEATURE_STATUS_OUTSIDE_VOCABULARY: " + fid)
        family = families[f["family"]]
        if f["primaryHorizon"] not in (family["primaryHorizon"], family["secondaryHorizon"]):
            raise ValueError("FEATURE_HORIZON_NOT_REGISTERED_FOR_ITS_FAMILY: " + fid)
        usable = f["readinessStatus"] in USABLE
        if usable == bool(f["blockingReason"]):
            raise ValueError("BLOCKING_REASON_REQUIRED_EXACTLY_WHEN_NOT_USABLE: " + fid)
        if usable and f["pitStatus"] not in safe:
            raise ValueError("NON_PIT_FEATURE_MARKED_USABLE: " + fid)
        if f["readinessStatus"] == "PIT_UNSAFE" and f["pitStatus"] not in unsafe:
            raise ValueError("PIT_UNSAFE_WITH_A_SAFE_PIT_STATUS: " + fid)
        if f["readinessStatus"] in ("READY", "ALREADY_TESTED") and not f["existingImplementation"]:
            raise ValueError("READY_WITHOUT_IMPLEMENTATION: " + fid)
        for path in f["existingImplementation"]:
            if not (root / path).exists():
                raise ValueError("IMPLEMENTATION_PATH_MISSING: %s %s" % (fid, path))
        for sid in f["priorEvidenceReference"]:
            if sid not in priors:
                raise ValueError("PRIOR_REFERENCE_UNRESOLVED: %s %s" % (fid, sid))
        status = f["existingResearchStatus"]
        if status in ("UNTESTED", "NOT_APPLICABLE", "BLOCKED") and f["priorEvidenceReference"]:
            raise ValueError("UNTESTED_FEATURE_CITES_PRIOR_EVIDENCE: " + fid)
        if status in MEASURED and not f["priorEvidenceReference"]:
            raise ValueError("PRIOR_EVIDENCE_WITHOUT_REFERENCE: " + fid)
        if status == "BLOCKED" and usable:
            raise ValueError("BLOCKED_EVIDENCE_ON_A_USABLE_FEATURE: " + fid)
        if f["family"] in registry["sourceClasses"] and f["sourceClass"] not in registry["sourceClasses"][f["family"]]:
            raise ValueError("FAMILY_SOURCE_CLASS_MISMATCH: " + fid)  # an OHLCV proxy is never investor flow
    for f in features.values():
        for other in f["overlapsWith"]:
            if other not in features:
                raise ValueError("OVERLAP_REFERENCE_UNRESOLVED: %s %s" % (f["featureId"], other))
    for sid, meta in priors.items():
        for fid in meta["featuresMeasuredIndividually"] + meta["featuresUsedJointly"]:
            if fid not in features:
                raise ValueError("PRIOR_STUDY_LISTS_UNKNOWN_FEATURE: %s %s" % (sid, fid))
            if sid not in features[fid]["priorEvidenceReference"]:
                raise ValueError("PRIOR_STUDY_NOT_CITED_BY_FEATURE: %s %s" % (sid, fid))
            if features[fid]["existingResearchStatus"] in ("UNTESTED", "BLOCKED", "NOT_APPLICABLE"):
                raise ValueError("TESTED_FEATURE_LABELLED_UNTESTED: %s %s" % (sid, fid))
    individually = {fid for meta in priors.values() for fid in meta["featuresMeasuredIndividually"]}
    for fid, f in features.items():
        if f["readinessStatus"] == "ALREADY_TESTED" and fid not in individually:
            raise ValueError("ALREADY_TESTED_WITHOUT_AN_INDIVIDUAL_MEASUREMENT: " + fid)
    for letter in FAMILY_LETTERS:
        if not any(f["family"] == letter for f in features.values()):
            raise ValueError("FAMILY_WITHOUT_FEATURES: " + letter)
    for name, members in registry["levelTwoBaselines"].items():
        for fid in members:
            f = features.get(fid)
            if f is None or f["role"] not in MODEL_ROLES or f["readinessStatus"] not in USABLE:
                raise ValueError("BASELINE_MEMBER_NOT_A_USABLE_MODEL_FEATURE: %s %s" % (name, fid))
    if len(registry["levelThreeInteractions"]) > registry["maxInteractions"]:
        raise ValueError("TOO_MANY_INTERACTIONS")
    for item in registry["levelThreeInteractions"]:
        if not item.get("economicArgument") or not item.get("negativeControl") or len(item["features"]) != 2:
            raise ValueError("INTERACTION_UNDERSPECIFIED: " + item["interactionId"])
        for fid in item["features"]:
            if fid not in features or features[fid]["role"] not in INTERACTION_ROLES:
                raise ValueError("INTERACTION_MEMBER_NOT_ALLOWED: %s %s" % (item["interactionId"], fid))
        horizons = {features[fid]["family"] for fid in item["features"]}
        if not any(item["horizon"] in (families[x]["primaryHorizon"], families[x]["secondaryHorizon"]) for x in horizons):
            raise ValueError("INTERACTION_HORIZON_NOT_REGISTERED: " + item["interactionId"])
    if not registry["multipleTesting"].get("declaredBeforeOutcomes"):
        raise ValueError("MULTIPLE_TESTING_NOT_DECLARED")
    for u in registry["universes"]:
        if u["readinessStatus"] not in readiness or (u["readinessStatus"] != "READY") != bool(u["blockingReason"]):
            raise ValueError("UNIVERSE_STATUS_INCONSISTENT: " + u["universeId"])
    return True


def interaction_status(registry, item):
    """READY_TO_REGISTER only when both members are usable; otherwise BLOCKED, naming the member that blocks it."""
    features = {f["featureId"]: f for f in registry["features"]}
    blocked = [fid for fid in item["features"] if features[fid]["readinessStatus"] not in USABLE]
    return ("BLOCKED", blocked) if blocked else ("READY_TO_REGISTER", [])


def summary(registry):
    features = registry["features"]
    by_family = {}
    for letter in FAMILY_LETTERS:
        rows = [f for f in features if f["family"] == letter]
        by_family[letter] = {"features": len(rows), "readiness": dict(sorted(Counter(f["readinessStatus"] for f in rows).items()))}
    return {"features": len(features),
            "readiness": dict(sorted(Counter(f["readinessStatus"] for f in features).items())),
            "priorEvidence": dict(sorted(Counter(f["existingResearchStatus"] for f in features).items())),
            "roles": dict(sorted(Counter(f["role"] for f in features).items())),
            "byFamily": by_family,
            "interactions": {i["interactionId"]: interaction_status(registry, i)[0] for i in registry["levelThreeInteractions"]}}


def _cell(value):
    text = "; ".join(value) if isinstance(value, list) else ("" if value is None else str(value))
    return text.replace("|", "/").replace("\n", " ")


def render_map(registry):
    """The human-readable information map, rendered only from the registry so the two cannot drift (a test compares the committed file)."""
    s = summary(registry)
    out = ["# kr-alpha-atlas — KR information map", "",
           "Rendered from `%s` by `scripts/render_kr_alpha_atlas_map.py`. Do not edit by hand." % REGISTRY_PATH, "",
           "> " + registry["statement"], "",
           "Benchmark `%s`; development cutoff %s; reference universe `PIT_KRX_TOP120`." % (registry["benchmark"], registry["developmentCutoff"]), "",
           "## Summary", "",
           "| Readiness | Features |", "|---|---:|"]
    out += ["| %s | %d |" % (k, v) for k, v in s["readiness"].items()]
    out += ["", "| Prior evidence (development only) | Features |", "|---|---:|"]
    out += ["| %s | %d |" % (k, v) for k, v in s["priorEvidence"].items()]
    out += ["", "| Role | Features |", "|---|---:|"]
    out += ["| %s | %d |" % (k, v) for k, v in s["roles"].items()]
    out += ["", "## Universes", "", "| Universe | Readiness | Evidence | Blocking reason |", "|---|---|---|---|"]
    out += ["| %s | %s | %s | %s |" % (u["universeId"], u["readinessStatus"], _cell(u["evidence"]), _cell(u["blockingReason"])) for u in registry["universes"]]
    for letter in FAMILY_LETTERS:
        fam = registry["families"][letter]
        out += ["", "## %s. %s" % (letter, fam["name"]), "",
                "Primary horizon H%s; secondary %s." % (fam["primaryHorizon"], ("H%s (%s)" % (fam["secondaryHorizon"], fam["secondaryJustification"]))
                                                       if fam["secondaryHorizon"] else "none"), "",
                "| Feature | Mechanism | PIT | Readiness | Prior evidence | Role | H | Blocking reason / limitation | Next action |",
                "|---|---|---|---|---|---|---:|---|---|"]
        for f in (f for f in registry["features"] if f["family"] == letter):
            note = f["blockingReason"] or f["limitations"]
            prior = f["existingResearchStatus"] + (" (" + ", ".join(f["priorEvidenceReference"]) + ")" if f["priorEvidenceReference"] else "")
            out.append("| `%s` | %s | %s | %s | %s | %s | %s | %s | %s |" % (f["featureId"], _cell(f["economicMechanism"]), f["pitStatus"],
                                                                         f["readinessStatus"], _cell(prior), f["role"], f["primaryHorizon"],
                                                                         _cell(note), _cell(f["nextAction"])))
    out += ["", "## Level 2 baselines", "", "| Baseline | Features |", "|---|---|"]
    out += ["| %s | %s |" % (k, ", ".join("`%s`" % x for x in v)) for k, v in registry["levelTwoBaselines"].items()]
    out += ["", "## Level 3 interactions (declared before outcomes; at most %d)" % registry["maxInteractions"], "",
            "| Interaction | Features | Economic argument | Negative control | H | Status |", "|---|---|---|---|---:|---|"]
    for item in registry["levelThreeInteractions"]:
        status, blocked = interaction_status(registry, item)
        out.append("| %s | %s | %s | %s | %s | %s |" % (item["interactionId"], ", ".join("`%s`" % x for x in item["features"]), _cell(item["economicArgument"]),
                                                     _cell(item["negativeControl"]), item["horizon"],
                                                     status + (" (" + ", ".join(blocked) + ")" if blocked else "")))
    out += ["", "## Prior studies", "", "| Study | Verdict | Evidence class | Measured individually | Used jointly | Result |", "|---|---|---|---:|---:|---|"]
    for sid, meta in registry["priorStudies"].items():
        out.append("| %s | %s | %s | %d | %d | `%s` |" % (sid, meta["verdict"], meta["evidenceClass"], len(meta["featuresMeasuredIndividually"]),
                                                       len(meta["featuresUsedJointly"]), meta["resultPath"]))
    mt = registry["multipleTesting"]
    out += ["", "## Multiple testing (declared before outcomes)", "", "- Level 1: `%s`" % mt["level1"], "- Level 2: `%s`" % mt["level2"],
            "- Level 3: `%s`" % mt["level3"], ""]
    return "\n".join(out)
