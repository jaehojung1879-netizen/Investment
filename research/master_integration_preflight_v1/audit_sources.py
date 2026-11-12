"""Git metadata preflight; never checks out or copies inherited raw datasets."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .preflight import _git
from . import adapters as A

MAIN = "37f8cbf6b1c066f6b3c65235953648d17ebf2f69"
PARENT308 = "f48b6f29993cf572d191f9724d19d2543f375f6c"
DATA = "research/alpha_mechanism_sprint_v1/data/"


def tree(repo, ref, prefix=None):
    args = ["ls-tree", "-r", ref]
    if prefix:
        args += ["--", prefix]
    result = {}
    for line in _git(repo, *args).decode().splitlines():
        meta, path = line.split("\t")
        mode, kind, blob = meta.split()
        if kind == "blob":
            result[path] = {"mode":mode,"blob":blob}
    return result


def changed(repo, ref):
    return set(_git(repo,"diff","--name-only",MAIN,ref).decode().splitlines())


def audit(repo):
    a, b = changed(repo,A.CANONICAL_COMMIT), changed(repo,A.FOUNDATION_COMMIT)
    current = tree(repo,A.CANONICAL_COMMIT,DATA)
    parent = tree(repo,PARENT308,DATA)
    if current != parent:
        raise ValueError("INHERITED_RAW_SOURCE_DRIFT")
    manifest = json.loads((Path(__file__).parent / "evidence/inherited-source-manifest.json").read_text())
    entries = manifest["entries"]
    indexed = {r["path"]:{"mode":r["mode"],"blob":r["blob"]} for r in entries}
    if manifest["commit"] != A.CANONICAL_COMMIT or len(indexed) != len(entries) or indexed != current:
        raise ValueError("INHERITED_TREE_METADATA_MISMATCH")
    if any(type(row["bytes"]) is not int or row["bytes"] < 0 for row in entries):
        raise ValueError("INVALID_METADATA_SIZE")
    main_blobs = {row["blob"] for row in tree(repo,MAIN).values()}
    other_blobs = {row["blob"] for row in tree(repo,A.FOUNDATION_COMMIT).values()}
    refs = {"316-contract":(A.CANONICAL_COMMIT,A.CANONICAL_PATH),
            "316-comparison":(A.CANONICAL_COMMIT,"research/master_research_program_v1/portfolio/comparison.py"),
            "316-sector":(A.CANONICAL_COMMIT,"research/master_research_program_v1/market_industry/us_sector_membership.py"),
            "317-comparison":(A.FOUNDATION_COMMIT,A.FOUNDATION_PATH),
            "317-industry":(A.FOUNDATION_COMMIT,"research/cross_market_foundation_v1/industry.py")}
    pins = {}
    for name,(sha,path) in refs.items():
        raw = _git(repo,"show",sha+":"+path)
        pins[name] = {"commit":sha,"path":path,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),
                      "url":f"https://github.com/jaehojung1879-netizen/Investment/blob/{sha}/{path}"}
    if pins["316-contract"]["sha256"] != A.CANONICAL_SHA256 or pins["317-comparison"]["sha256"] != A.FOUNDATION_SHA256:
        raise ValueError("PINNED_INTERFACE_BYTES_CHANGED")
    return {"schema":"MASTER_INTEGRATION_SOURCE_AUDIT_V1","base":MAIN,
            "changedPaths":{"316":len(a),"317":len(b),"directOverlap":sorted(a & b)},
            "inheritedRaw":{"parentCommit":PARENT308,"commit":A.CANONICAL_COMMIT,
                "prefix":DATA,"paths":len(current),"bytes":sum(v["bytes"] for v in entries),
                "byteSizeBasis":manifest["sizeBasis"],"payloadBytesVerified":False,
                "samePathModeBlobAsParent":True,"uniqueBlobs":len({v["blob"] for v in current.values()}),
                "blobOverlapWithMain":sum(v["blob"] in main_blobs for v in current.values()),
                "blobOverlapWith317":sum(v["blob"] in other_blobs for v in current.values()),
                "payloadsFetchedOrCopied":0,"rightsAdmission":"UNVERIFIED",
                "necessity":"Not needed by this metadata-only prototype. Static path absence is not proof that every upstream helper can run without these data.",
                "disposition":"Preserve exact parent source commitments; use small explicit hash-linked reads after rights/need review. No source deletion, rewrite, squash or bulk recommit."},
            "interfacePins":pins,"newHistoricalExecution":False}


if __name__ == "__main__":
    print(json.dumps(audit(Path(__file__).resolve().parents[2]),ensure_ascii=False,indent=2))
