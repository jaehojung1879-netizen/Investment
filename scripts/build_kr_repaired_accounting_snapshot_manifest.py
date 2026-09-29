"""Build or verify the frozen KR repaired accounting snapshot manifest.

Reads only accounting shards (from a directory tree or the pinned git object). It
never fetches, repairs, reselects or tunes data and touches no Alpha artifact.

  --from-git            materialise the pinned source commit's three accounting directories
  --write PATH          write the manifest (refuses to overwrite)
  --verify              recompute and require equality with research_specs/<study>.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import kr_repaired_accounting_snapshot as K  # noqa: E402

SPEC = ROOT / "research_specs" / (K.STUDY + ".json")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--from-git", action="store_true")
    p.add_argument("--merged-dir", type=Path)
    p.add_argument("--canonical-dir", type=Path)
    p.add_argument("--xbrl-dir", type=Path)
    p.add_argument("--write", type=Path)
    p.add_argument("--verify", action="store_true")
    args = p.parse_args(argv)
    with tempfile.TemporaryDirectory() as tmp:
        if args.from_git:
            dirs = K.materialize_from_git(ROOT, Path(tmp))
            merged, canonical, xbrl = dirs["merged"], dirs["canonical"], dirs["xbrl"]
        else:
            merged, canonical, xbrl = args.merged_dir, args.canonical_dir, args.xbrl_dir
        manifest = K.build_manifest(merged, canonical, xbrl, ROOT)
        regen = K.regenerate_and_compare(canonical, xbrl, merged, ROOT)
    manifest["regeneration"] = {"method": "scripts/merge_kr_candidate_snapshot.py from kr-canonical-v2 + kr-xbrl-original",
                                **regen}
    if not (regen["byteIdentical"] and regen["shardSetEqual"] and regen["mergeReportEqual"]
            and regen["contentSha256"] == manifest["snapshotContentSha256"]):
        print("REGENERATION_DIFFERS_FROM_FROZEN_SHARDS")
        return 4
    if manifest["candidateIdentitySha256"] != K.CANDIDATE_SHA256:
        print("CANDIDATE_IDENTITY_DIFFERS_FROM_VALIDATED_CANDIDATE")
        return 4
    text = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.write:
        if args.write.exists():
            p.error("refusing to overwrite an existing manifest")
        args.write.write_text(text, encoding="utf-8")
    if args.verify:
        frozen = json.loads(SPEC.read_text(encoding="utf-8"))
        current = json.loads(text)
        keys = ("candidateIdentitySha256", "snapshotContentSha256", "recordCount", "shards", "inputs", "code", "coverage", "coverageByShard")
        diff = [k for k in keys if frozen.get(k) != current.get(k)]
        if diff:
            print("MANIFEST_DIFFERS", diff)
            return 4
    print(json.dumps({"snapshotContentSha256": manifest["snapshotContentSha256"],
                      "candidateIdentitySha256": manifest["candidateIdentitySha256"],
                      "recordCount": manifest["recordCount"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
