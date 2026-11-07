"""Offline, exact-byte packet verification. This never fetches or admits a study."""
from __future__ import annotations

import hashlib
import base64
import gzip
import io
import json
import os
import subprocess
from collections import Counter
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent
MANIFEST = "packet-receipts.json"


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def packet_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file()
                  and "__pycache__" not in p.parts and p.name != MANIFEST)


def verify(root: Path = ROOT) -> dict:
    """Detect missing, added, tampered or escaping files; no implicit network."""
    receipts = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    expected, errors = set(), []
    for row in receipts["files"]:
        relative = row["path"]
        path = PurePosixPath(relative)
        if (path.is_absolute() or ".." in path.parts or "\\" in relative
                or path.as_posix() != relative or relative in expected):
            raise ValueError("INVALID_OR_DUPLICATE_PACKET_PATH")
        expected.add(relative)
        target = root / relative
        if target.is_symlink() or not target.resolve().is_relative_to(root.resolve()):
            errors.append("PATH_ESCAPE:" + relative)
        elif not target.is_file():
            errors.append("MISSING:" + relative)
        else:
            raw = target.read_bytes()
            if len(raw) != row["bytes"] or digest(raw) != row["sha256"]:
                errors.append("DIGEST_MISMATCH:" + relative)
    actual = {p.relative_to(root).as_posix() for p in packet_files(root)}
    errors.extend("UNRECEIPTED:" + p for p in sorted(actual - expected))
    return {"status": "VERIFIED_BYTES" if not errors else "FAILED", "files": len(expected),
            "errors": errors, "researchAdmission": False, "economicReadiness": False}


def verify_fixed_filings(root: Path = ROOT) -> dict:
    """Replay actual retained filings, independently of stored parser output."""
    from .filings import load_filing, parse_filing

    evidence = root / "evidence"
    samples = json.loads((evidence / "filing-samples.json").read_text(encoding="utf-8"))["samples"]
    rows = []
    for sample in samples:
        row = parse_filing(load_filing(evidence, sample), sample)
        row.pop("raw_table_rows", None)
        rows.append(row)
    saved = json.loads((evidence / "parsed-filing-samples.json").read_text(encoding="utf-8"))
    if saved != rows:
        raise ValueError("PARSED_FIXED_SAMPLE_NOT_REPRODUCIBLE")
    return {"fixedFilingSamples": len(rows),
            "issuers": len({r["issuer_id"] for r in rows}),
            "parseStatuses": dict(sorted(Counter(r["parse_status"] for r in rows).items())),
            "eligibilityStatuses": dict(sorted(Counter(r["data_eligibility"] for r in rows).items())),
            "parsedSnapshotReproduced": True,
            "scope": "PURPOSIVE_PARSER_FIXTURE_NOT_EMPIRICAL_SAMPLE_OR_POWER_N"}


def verify_viewer_families(root: Path = ROOT) -> list[dict]:
    """Replay retained current menus; never treat them as historical PIT proof."""
    from .filings import parse_viewer_family

    raw = (root / 'evidence/viewer-family-sources.json.gz').read_bytes()
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
        unpacked = stream.read(1_000_001)
    if len(unpacked) > 1_000_000:
        raise ValueError('VIEWER_PACKET_SIZE_LIMIT')
    results = []
    for row in json.loads(unpacked)['sources']:
        body = base64.b64decode(row['rawBase64'], validate=True)
        if len(body) != row['bytes']:
            raise ValueError('VIEWER_SOURCE_SIZE_MISMATCH')
        result = parse_viewer_family(body, receipt=row['receipt'], sha256=row['sha256'])
        result.update(sourceUrl=row['url'], retrievedAtUtc=row['retrievedAtUtc'])
        results.append(result)
    saved = json.loads((root / 'evidence/viewer-family-links.json').read_text())
    if saved != results:
        raise ValueError('VIEWER_FAMILY_PROJECTION_NOT_REPRODUCIBLE')
    return results


def verify_extended_sources(root: Path = ROOT, *, verify_source_git: bool = False) -> dict:
    """Replay versioned bodies and cash-only history; Git reads are opt-in/offline."""
    from .filings import load_filing, version_terms, corroborate_family_index
    from .etf.source import inspect_distribution_history

    evidence = root / 'evidence'
    samples = {}
    for name in ('filing-samples.json', 'chain-body-samples-v1.json'):
        for row in json.loads((evidence / name).read_text())['samples']:
            samples[row['rcept_no']] = row
    saved = json.loads((evidence / 'version-terms-v1.json').read_text())
    actual = [version_terms(load_filing(evidence, samples[row['receipt']]), samples[row['receipt']])
              for row in saved]
    if actual != saved:
        raise ValueError('VERSIONED_TERMS_NOT_REPRODUCIBLE')
    history = json.loads((root / 'etf/distribution-history-pages-v1.json').read_text())
    result = inspect_distribution_history([json.dumps(p).encode() for p in history['pages']],
                                         product_source=(root / 'etf/issuer-projection.json').read_bytes())
    if result != json.loads((root / 'etf/distribution-history-readiness-v1.json').read_text()):
        raise ValueError('DISTRIBUTION_HISTORY_NOT_REPRODUCIBLE')
    indexes = json.loads((evidence / 'index-family-crosscheck-v1.json').read_text())
    if verify_source_git:
        from .build_inventory import LIST_REF, LIST_PATH
        families = {r['selectedReceipt']: r for r in verify_viewer_families(root)}
        repo = Path(__file__).resolve().parents[2]
        for index in indexes:
            family = next(r for r in families.values()
                          if sorted(v['receipt'] for v in r['versions']) == index['matchedReceipts'])
            anchor = samples[family['selectedReceipt']]
            if (index['sourceCommit'] != LIST_REF
                    or index['sourcePath'] != LIST_PATH + '/' + anchor['corp_code'] + '-I.jsonl.gz'
                    or index['issuer'] != anchor['corp_code']
                    or index['indexBlob'] != anchor['index_git_blob']):
                raise ValueError('EXACT_FIXED_INDEX_SCOPE_REQUIRED')
            cmd = ['git', '--no-replace-objects', '-c', 'remote.origin.promisor=false']
            env = {**os.environ, 'GIT_NO_LAZY_FETCH': '1', 'GIT_TERMINAL_PROMPT': '0'}
            ref = index['sourceCommit'] + ':' + index['sourcePath']
            try:
                size = int(subprocess.check_output(cmd + ['cat-file', '-s', ref], cwd=repo, env=env, stderr=subprocess.PIPE))
                if size > 1_000_000:
                    raise ValueError('FIXED_INDEX_BYTE_BUDGET_EXCEEDED')
                raw = subprocess.check_output(cmd + ['show', ref], cwd=repo, env=env, stderr=subprocess.PIPE)
            except subprocess.CalledProcessError as exc:
                raise ValueError('LOCAL_FIXED_INDEX_OBJECT_UNAVAILABLE') from exc
            verified = corroborate_family_index(family, raw, issuer=index['issuer'], expected_blob=index['indexBlob'])
            if any(verified[k] != index[k] for k in verified):
                raise ValueError('INDEX_FAMILY_PROJECTION_NOT_REPRODUCIBLE')
    return {'versionedBodiesReproduced': len(actual),
            'observedDistributions': result['coverage']['observedEvents'],
            'paginationCompleteAgainstCurrentDeclaredCount': True,
            'indexVersionLinks': sum(r['matchedVersionCount'] for r in indexes),
            'indexBytesReverifiedFromLocalGit': verify_source_git,
            'historicalPublicationVerified': False, 'researchAdmission': False}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-source-git', action='store_true')
    args = parser.parse_args()
    result = verify()
    if not result["errors"]:
        result["filings"] = verify_fixed_filings()
        result['viewerFamilies'] = verify_viewer_families()
        result['extendedSources'] = verify_extended_sources(verify_source_git=args.verify_source_git)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(bool(result["errors"]))
