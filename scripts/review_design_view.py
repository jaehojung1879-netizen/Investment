"""Conservative local review view: prose is metadata-only, JSON is allowlisted.

This is an exposure-reduction utility, not proof of outcome blindness. It never
executes repository code. Unknown paths, prose and unknown JSON keys fail closed.
Do not use a keyword-only redactor to certify that a mixed report is outcome-free.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

SPEC = re.compile(r"alpha-opportunity-model-v[1-4]\.json")
FEATURE = re.compile(r"[A-Za-z][A-Za-z0-9_]*\Z")
NUMERIC_MODEL_KEYS = {
    "C", "max_iter", "tol", "random_state", "alpha", "learning_rate",
    "max_leaf_nodes", "min_samples_leaf", "l2_regularization", "early_stopping",
    "max_depth",
}
ENUMS = {"solver": {"lbfgs", "lsqr"}, "penalty": {"l2"}}


def design_projection(document):
    """Only structural declarations; no arbitrary text leaves are emitted."""
    out = {}
    for key, allowed in (("regions", {"KR", "US"}), ("horizons", {21, 126})):
        value = document.get(key)
        if isinstance(value, list) and all(x in allowed for x in value):
            out[key] = value
    for prefix in (None, "carriedFromV1", "carriedFromV2", "carriedFromV3"):
        source = document if prefix is None else document.get(prefix, {})
        if not isinstance(source, dict):
            continue
        projected = {}
        models = source.get("models", {})
        if isinstance(models, dict):
            for family in ("ridge", "logistic", "histGradientBoosting"):
                config = models.get(family, {})
                if not isinstance(config, dict):
                    continue
                values = {}
                for key, value in config.items():
                    if key in NUMERIC_MODEL_KEYS and (value is None or type(value) in (int, float, bool)):
                        values[key] = value
                    elif key in ENUMS and isinstance(value, str) and value in ENUMS[key]:
                        values[key] = value
                projected[family] = values
        fields = source.get("allowedFeatures", {})
        if isinstance(fields, dict):
            projected["allowedFeatures"] = {}
            for region in ("KR", "US"):
                horizons = fields.get(region, {})
                if not isinstance(horizons, dict):
                    continue
                for horizon in ("21", "126"):
                    names = horizons.get(horizon)
                    if isinstance(names, list) and all(isinstance(x, str) and FEATURE.fullmatch(x) for x in names):
                        projected["allowedFeatures"].setdefault(region, {})[horizon] = names
        out[prefix or "direct"] = projected
    return out


def inspect(path, root):
    root = Path(root).resolve()
    path = Path(path).resolve()
    rel = path.relative_to(root)
    if any(x in rel.parts for x in (".git", "results", "ledger")):
        raise ValueError("REFUSED_ARTIFACT_PATH")
    if path.suffix not in {".md", ".json"}:
        raise ValueError("REFUSED_FILE_TYPE")
    raw = path.read_bytes()
    record = {"path": rel.as_posix(), "sha256": hashlib.sha256(raw).hexdigest(),
              "bytes": len(raw), "body": "WITHHELD", "blindnessCertification": False}
    if rel.parent.as_posix() == "research_specs" and SPEC.fullmatch(path.name):
        record["designProjection"] = design_projection(json.loads(raw))
    return record


def self_test():
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "research_specs").mkdir()
        path = root / "research_specs/alpha-opportunity-model-v4.json"
        path.write_text(json.dumps({"results": "SYNTHETIC_SECRET_OUTCOME",
            "regions": ["KR"], "horizons": [21, 126],
            "models": {"ridge": {"alpha": 10, "solver": "lsqr", "result": 777}},
            "carriedFromV3": {"models": {"logistic": {"C": "SYNTHETIC_SECRET_OUTCOME"}}}}))
        first = inspect(path, root)
        assert first == inspect(path, root)
        rendered = json.dumps(first)
        assert "SYNTHETIC_SECRET_OUTCOME" not in rendered and "777" not in rendered
        assert first["designProjection"]["direct"]["ridge"]["alpha"] == 10
        prose = root / "README.md"
        prose.write_text("Result without any number: the strategy beat the baseline.")
        assert "beat the baseline" not in json.dumps(inspect(prose, root))
        forbidden = root / "docs/results/test.md"
        forbidden.parent.mkdir(parents=True)
        forbidden.write_text("secret")
        try:
            inspect(forbidden, root)
        except ValueError:
            pass
        else:
            raise AssertionError("result path not blocked")
        outside = root.parent / "outside.md"
        try:
            inspect(outside, root)
        except ValueError:
            pass
        else:
            raise AssertionError("outside root not blocked")
    print("synthetic self-test: passed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*")
    parser.add_argument("--root", default=".")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    records = [inspect(Path(args.root) / p, args.root) for p in args.paths]
    print(json.dumps(records, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
