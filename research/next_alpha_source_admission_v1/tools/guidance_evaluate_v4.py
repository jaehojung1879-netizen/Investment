"""Compare frozen guidance extractors, DOM tables and review routing on verified releases.

An official archival exhibit with a new digest is separate from a historical
HTTP capture. Old gold scopes are applied only to legacy comparisons. A fresh
holdout requires full-document annotations and a frozen, disjoint issuer roster.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

import doc_blocks
import guidance_extract_structured as dom
import guidance_extract_v2 as v2
import guidance_extract_v3 as v3
import guidance_extract_v4 as legacy_v4
from guidance_score import load_gold, match
from guidance_validation_protocol import issuer_bootstrap

ROOT = Path(__file__).resolve().parents[1]
KEY = ("target", "metric", "basis", "unit")
RELEASE_KEY = ("cik", "accession", "prior_accession", *KEY)
EXPLICIT_FORWARD = re.compile(
    r"\b(?:expect\w*|anticipat\w*|forecast\w*|project(?:s|ed)?|will be|guidance|outlook)\b", re.I,
)
COMPARISON = re.compile(
    r"\b(?:compared (?:with|to)|versus|vs\.?|last year|a year ago|prior[- ]year|"
    r"year[- ]over[- ]year|previously|revis(?:e|ed|ing) from)\b", re.I,
)
UNSUPPORTED_SCOPE = re.compile(r"\b(?:segment|excluding the impact|on a constant currency basis)\b", re.I)
SENTENCE_END = re.compile(r"[!?]\s+|(?<=[.])\s+(?=[A-Z])")
METRIC_PATTERNS = dict(v2.METRICS)
METRIC_SOURCE = {"gross_profit": "gross_margin"}


def fields(row, names=KEY):
    return tuple(row[name] for name in names)


def matches(left, right):
    return left["kind"] == right["kind"] and match(left, right)


def one_to_one(predicted, gold, compatible=matches):
    """Deterministic maximum-cardinality matching, including overlapping tolerances."""
    choices = [[j for j, label in enumerate(gold) if compatible(prediction, label)]
               for prediction in predicted]
    owners = {}

    def augment(index, visited):
        for j in choices[index]:
            if j not in visited:
                visited.add(j)
                if j not in owners or augment(owners[j], visited):
                    owners[j] = index
                    return True
        return False

    for i in range(len(predicted)):
        augment(i, set())
    return sorted((i, j) for j, i in owners.items())


def accuracy(tp, fp, fn):
    return {"tp": tp, "fp": fp, "fn": fn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None}


def score_rows(predicted, gold):
    pairs = one_to_one(predicted, gold)
    return accuracy(len(pairs), len(predicted) - len(pairs), len(gold) - len(pairs))


def block_kind(blocks, row):
    index = row.get("block")
    return blocks[index][0] if type(index) is int and 0 <= index < len(blocks) else None


def explicit_narrative_anchor(blocks, prediction):
    """Require a uniquely supported financial span in an explicit forecast sentence."""
    if prediction["kind"] != "CURRENT" or block_kind(blocks, prediction) != "p":
        return False
    if prediction["high"] is None:
        return False
    text = blocks[prediction["block"]][1]
    metric = METRIC_SOURCE.get(prediction["metric"], prediction["metric"])
    pattern = METRIC_PATTERNS.get(metric)
    if pattern is None:
        return False
    for sentence in SENTENCE_END.split(text):
        if not EXPLICIT_FORWARD.search(sentence) or COMPARISON.search(sentence) or UNSUPPORTED_SCOPE.search(sentence):
            continue
        label = re.search(pattern, sentence, re.I)
        if label is None:
            continue
        values = v2._values(sentence[label.end():], metric)
        if len(values) == 1:
            (low, high, pct, _, value_text), = values
            parsed_metric, unit = v2.unit_for(metric, pct, value_text)
            candidate = {**prediction, "metric": parsed_metric, "unit": unit, "low": low, "high": high}
            if matches(candidate, prediction):
                return True
    return False


def candidates(raw):
    old, newer = v2.extract(raw), v3.extract(raw)
    structured = dom.inspect(raw)
    tables = structured["predictions"]
    blocks = doc_blocks.blocks(raw)
    structured_blocks = {row["block"] for row in tables if row.get("block") is not None}
    # Use DOM where a row is structurally identified, otherwise keep v2's
    # proposal in the comparison. Automatic routing has a stricter threshold.
    hybrid = tables + [row for row in old if row.get("block") not in structured_blocks]
    prose = [row for row in old if explicit_narrative_anchor(blocks, row)
             and any(matches(row, other) and row.get("block") == other.get("block") for other in newer)]
    automatic = tables + prose
    conflicts = conflicting_keys(automatic)
    automatic = [row for row in automatic if fields(row) + (row["kind"],) not in conflicts]
    manual = []
    for row in old + newer + tables:
        if not any(matches(row, other) for other in automatic + manual):
            reason = "CONFLICTING_VALUES" if fields(row) + (row["kind"],) in conflicts else "REVIEW_SOURCE_CONTEXT"
            manual.append({**row, "reviewReason": reason})
    return {"v2": old, "v3": newer, "legacyV4": legacy_v4.extract(raw),
            "domTable": tables, "hybrid": hybrid, "automatic": automatic,
            "manualReviewCandidates": manual}, structured["needs_review"]


def conflicting_keys(facts):
    by_key = defaultdict(set)
    for row in facts:
        by_key[fields(row) + (row["kind"],)].add((row["low"], row["high"]))
    return {key for key, values in by_key.items() if len(values) > 1}


def distinct_facts(rows):
    return list({fields(row) + (row["kind"], row["low"], row["high"]): row for row in rows}.values())


def direction(earlier, later):
    period_change = later[0] + later[1] - earlier[0] - earlier[1]
    width_change = (later[1] - later[0]) - (earlier[1] - earlier[0])
    if abs(period_change) > 1e-9:
        return "RAISE" if period_change > 0 else "LOWER"
    if abs(width_change) > 1e-9:
        return "WIDEN" if width_change > 0 else "NARROW"
    return "MAINTAIN"


def revisions(by_accession, docs):
    """Link adjacent unambiguous observations of the same account and target."""
    timelines = defaultdict(list)
    conflicts = 0
    for accession, facts in by_accession.items():
        doc = docs[accession]
        stamp = datetime.fromisoformat(doc["acceptanceDateTime"])
        if stamp.tzinfo is None:
            raise ValueError(f"Missing timezone for {accession}")
        current = [row for row in facts if row["kind"] == "CURRENT"]
        groups = defaultdict(set)
        for row in current:
            groups[(int(doc["cik"]), *fields(row))].add((row["low"], row["high"]))
        for key, intervals in groups.items():
            # Retain ambiguities as timeline gaps. Neither side of a gap can
            # silently link over a conflicting or open-ended release.
            if len(intervals) != 1:
                conflicts += 1
            amount = next(iter(intervals)) if len(intervals) == 1 else (None, None)
            timelines[key].append((stamp, accession, amount))
    edges = []
    for (cik, *key), observations in sorted(timelines.items()):
        ordered = sorted(observations)
        simultaneous = Counter(stamp for stamp, _, _ in ordered)
        for (previous_date, prior, old), (current_date, current, new) in zip(ordered, ordered[1:]):
            if simultaneous[previous_date] > 1 or simultaneous[current_date] > 1 or old[1] is None or new[1] is None:
                continue
            edges.append({"cik": cik, "accession": current, "prior_accession": prior, **dict(zip(KEY, key)),
                          "direction": direction(old, new), "basisConfirmed": key[2] != "unstated"})
    return edges, conflicts


def score_revisions(predicted, gold):
    preds = {fields(row, RELEASE_KEY): row["direction"] for row in predicted}
    labels = {fields(row, RELEASE_KEY): row["direction"] for row in gold}
    correct_key = preds.keys() & labels.keys()
    good_direction = sum(preds[key] == labels[key] for key in correct_key)
    return {"links": accuracy(len(correct_key), len(preds) - len(correct_key), len(labels) - len(correct_key)),
            "directionEndToEnd": accuracy(good_direction, len(preds) - good_direction, len(labels) - good_direction),
            "directionGivenMatchedLink": good_direction / len(correct_key) if correct_key else None,
            "directionConfusions": dict(Counter(f"{labels[key]}->{preds[key]}" for key in sorted(correct_key))),
            "predictedLinksWithExplicitBasis": sum(row["basisConfirmed"] for row in predicted)}


def read_verified_sources(source_root):
    sources = {}
    for line in (source_root / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        accession = record["accession"]
        if accession in sources:
            old = sources[accession]
            if old.get("sectionSha256"):
                if record.get("sectionSha256") and old["sectionSha256"] != record["sectionSha256"]:
                    raise ValueError(f"Conflicting captured source variants for {accession}")
                continue
        sources[accession] = record
    return sources


def verified_body(record, doc, source_root):
    if int(record["cik"]) != int(doc["cik"]) or record["accession"] != doc["accession"]:
        raise ValueError(f"Source identity differs for {doc['accession']}")
    if record.get("status") != "OFFICIAL_ARCHIVE_SECTION":
        return None
    if record.get("registeredHttpSha256") != doc.get("sha256"):
        raise ValueError(f"Source registry differs for {doc['accession']}")
    digest = record["sectionSha256"]
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError(f"Invalid source digest for {doc['accession']}")
    data = (source_root / "sections" / digest).read_bytes()
    if hashlib.sha256(data).hexdigest() != digest or len(data) != record["sectionBytes"]:
        raise ValueError(f"Hash or byte length differs for {doc['accession']}")
    return data


def compare_documents(docs, gold, source_root, *, universe=None, incomplete_docs=()):
    sources = read_verified_sources(source_root)
    methods = defaultdict(dict)
    evaluated_docs = {}
    omitted = Counter()
    archived = 0
    outside = Counter()
    legacy_transitions = defaultdict(Counter)
    linkage_gaps = defaultdict(set)
    for row in incomplete_docs:
        linkage_gaps[int(row["cik"])].add(row["accession"])
    review_rows = 0
    for accession, doc in docs.items():
        record = sources.get(accession)
        body = verified_body(record, doc, source_root) if record else None
        if body is None:
            omitted[record.get("status", "MISSING_SOURCE") if record else "MISSING_SOURCE"] += 1
            linkage_gaps[int(doc["cik"])].add(accession)
            continue
        if doc.get("sha256") == record["sectionSha256"]:
            archived += 1
        allowed = set(universe[accession]) if universe is not None else None
        evaluated_docs[accession] = doc
        proposed, abstentions = candidates(body)
        review_rows += len(abstentions)
        for name, values in proposed.items():
            scoped = values if allowed is None else [row for row in values if row.get("block") in allowed]
            outside[name] += len(values) - len(scoped)
            methods[name][accession] = scoped if name in ("v2", "v3", "legacyV4") else distinct_facts(scoped)
        labels = [row for row in gold[accession] if row["kind"] == "CURRENT"]
        hits = {}
        for version in ("v2", "v3"):
            current = [row for row in methods[version][accession] if row["kind"] == "CURRENT"]
            hits[version] = {j for _, j in one_to_one(current, labels)}
        for key, values in (("lostGoldHits", hits["v2"] - hits["v3"]),
                            ("addedGoldHits", hits["v3"] - hits["v2"])):
            legacy_transitions[key].update(labels[j]["metric"] for j in values)
    results = {}
    link_docs = {accession: row for accession, row in evaluated_docs.items() if int(row["cik"]) not in linkage_gaps}
    gold_links, gold_conflicts = revisions({acc: gold[acc] for acc in link_docs}, link_docs)
    for name, by_accession in methods.items():
        totals = {"CURRENT": Counter(), "PRIOR": Counter()}
        issuer_tp_fp_fn = defaultdict(Counter)
        for accession, facts in by_accession.items():
            for kind in totals:
                counts = score_rows([row for row in facts if row["kind"] == kind],
                                    [row for row in gold[accession] if row["kind"] == kind])
                summed = {key: counts[key] for key in ("tp", "fp", "fn")}
                totals[kind].update(summed)
                if kind == "CURRENT":
                    doc = docs[accession]
                    issuer_tp_fp_fn[int(doc.get("issuerGroup", doc["cik"]))].update(summed)
        result = {kind: accuracy(*(counts[key] for key in ("tp", "fp", "fn"))) for kind, counts in totals.items()}
        result["outsideLegacyAnnotationScope"] = outside[name]
        result["issuerConfusion"] = issuer_tp_fp_fn
        if name != "manualReviewCandidates":
            result["issuerClusterBootstrapCurrent"] = issuer_bootstrap({
                issuer: tuple(counts[key] for key in ("tp", "fp", "fn"))
                for issuer, counts in issuer_tp_fp_fn.items()
            })
            links, conflict_count = revisions({acc: by_accession[acc] for acc in link_docs}, link_docs)
            result.update(score_revisions(links, gold_links))
            result["ambiguousPredictedKeys"] = conflict_count
        results[name] = result
    return {"goldDocuments": len(docs), "evaluatedDocuments": len(evaluated_docs),
            "historicalHttpBytesVerified": archived, "sourceOmissions": omitted,
            "allGoldCurrent": sum(row["kind"] == "CURRENT" for rows in gold.values() for row in rows),
            "evaluatedGoldCurrent": sum(row["kind"] == "CURRENT" for acc in evaluated_docs for row in gold[acc]),
            "v2ToV3GoldHitsByMetric": legacy_transitions,
            "domRowsForManualReview": review_rows,
            "linkIssuersOmittedForSourceGaps": sorted(linkage_gaps), "ambiguousGoldLinkKeys": gold_conflicts,
            "methods": results}


def compare_legacy(split, source_root):
    registry = json.loads((ROOT / "gold/gold-docs.json").read_bytes())
    docs = {row["accession"]: row for row in registry if row["split"] == split}
    universe = json.loads((ROOT / "gold/annotation-universe.json").read_bytes())["universe"]
    gold = defaultdict(list)
    for row in load_gold(split):
        gold[row["accession"]].append(row)
    return {"comparisonClass": "LEGACY_GOLD_AGAINST_RECAPTURED_OFFICIAL_ARCHIVE_SCOPED_DIAGNOSTIC",
            "split": split, **compare_documents(docs, gold, source_root, universe=universe)}


def compare_pilot(plan_path, plan_sha, gold_path, source_root):
    plan_bytes = plan_path.read_bytes()
    if hashlib.sha256(plan_bytes).hexdigest() != plan_sha:
        raise ValueError("Pilot roster does not match its pre-annotation SHA-256")
    plan = json.loads(plan_bytes)
    planned = {row["accession"]: row for row in plan["documents"]}
    actual = json.loads(gold_path.read_bytes())["documents"]
    annotated = {row["accession"]: row for row in actual}
    if len(annotated) != len(actual) or annotated.keys() != planned.keys():
        raise ValueError("Pilot annotation must account for every frozen accession exactly once")
    sources = read_verified_sources(source_root)
    docs, gold, incomplete = {}, {}, []
    status = Counter()
    for accession, record in annotated.items():
        frozen = planned[accession]
        if int(frozen["cik"]) != int(record["cik"]) or frozen["acceptanceDateTime"] != record["acceptanceDateTime"]:
            raise ValueError(f"Pilot annotation identity differs for {accession}")
        state = record["annotationStatus"]
        status[state] += 1
        if state != "COMPLETE":
            incomplete.append(frozen)
            continue
        if sources[accession].get("sectionSha256") != record["sectionSha256"]:
            raise ValueError(f"Pilot annotation source bytes differ for {accession}")
        docs[accession] = frozen
        gold[accession] = record["facts"]
    return {"comparisonClass": "RESTRICTED_BLIND_PILOT_FULL_DOCUMENT_DIAGNOSTIC",
            "pilotPlanSha256": plan_sha, "annotationSha256": hashlib.sha256(gold_path.read_bytes()).hexdigest(),
            "plannedDocuments": len(planned), "annotationStatus": status,
            **compare_documents(docs, gold, source_root, incomplete_docs=incomplete)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--split", choices=("dev", "test", "test2"), default="dev")
    parser.add_argument("--pilot-roster", type=Path)
    parser.add_argument("--pilot-roster-sha256")
    parser.add_argument("--pilot-annotations", type=Path)
    args = parser.parse_args()
    if any((args.pilot_roster, args.pilot_roster_sha256, args.pilot_annotations)):
        if not all((args.pilot_roster, args.pilot_roster_sha256, args.pilot_annotations)):
            parser.error("pilot roster, its frozen digest, and annotations are all required")
        result = compare_pilot(args.pilot_roster, args.pilot_roster_sha256, args.pilot_annotations, args.archive)
    else:
        result = compare_legacy(args.split, args.archive)
    print(json.dumps(result, indent=2, sort_keys=True))
