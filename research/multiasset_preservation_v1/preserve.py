"""Preserve existing code/summary bytes; no strategy or metric calculations.

The requested Codex B files are checked separately. Another session's files
must never be relabelled as the missing twelve-strategy result. Raw vendor
inputs, price series and daily NAV are not included in this archive.
"""
import argparse
import gzip
import hashlib
import io
import json
import tarfile
from pathlib import Path

NAMES = ('REPORT-ko.md', 'FILE-MANIFEST.json', 'family.json', 'analyze.py', 'verify_results.py',
         'audit_sources.py', 'fetch_academic.py', 'fetch_public.py', 'replicate_mm17.py',
         'outputs/c2-analysis.json', 'outputs/academic-factors.json', 'outputs/mm17-original-sample.json',
         'outputs/validation.json', 'outputs/source-admission.json', 'outputs/runtime.json',
         'outputs/methodology-correction.json', 'us_etf_calculation_v1/REPORT-ko.md',
         'us_etf_calculation_v1/calculate.py', 'us_etf_calculation_v1/verify.py',
         'us_etf_calculation_v1/results.json', 'us_etf_calculation_v1/MANIFEST.json',
         'us_etf_calculation_v1/verification.json')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def preserve(source, output, workspace):
    source, output, workspace = Path(source), Path(output), Path(workspace)
    members, buffer = [], io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w') as tar:
        for name in NAMES:
            path = source / name
            if not path.is_file():
                continue
            if not path.resolve().is_relative_to(source.resolve()):
                raise ValueError('ARCHIVE_SOURCE_PATH_ESCAPE')
            data = path.read_bytes()
            info = tarfile.TarInfo('legacy_codex_a/' + name)
            info.size, info.mtime, info.mode = len(data), 0, 0o644
            tar.addfile(info, io.BytesIO(data))
            members.append({'path': info.name, 'bytes': len(data), 'sha256': sha(data)})
    archive = gzip.compress(buffer.getvalue(), mtime=0)
    output.mkdir(parents=True, exist_ok=True)
    target = output / 'legacy-codex-a-code-and-summaries.tar.gz'
    if target.exists() and target.read_bytes() != archive:
        raise ValueError('EXISTING_ARCHIVE_DIFFERS_VERSION_REQUIRED')
    target.write_bytes(archive)
    requested = [workspace / 'multi-asset-b/report.md', workspace / 'multi-asset-b/all-metrics.csv',
                 workspace / 'multi-asset-b-results.tar.gz']
    found = [{'path': str(p), 'exists': p.is_file(), 'sha256': sha(p.read_bytes()) if p.is_file() else None}
             for p in requested]
    result = {
        'requestedCodexB12StrategyResult': {
            'status': 'SOURCE_BLOCKED_ORIGINAL_FILES_ABSENT' if not all(r['exists'] for r in found)
                      else 'FILES_PRESENT_NOT_YET_VALIDATED',
            'checkedPaths': found, 'independentlyReproduced': False, 'navVerified': False,
            'sixOrTwelveMonthWindowsVerified': False, 'recoveryPeriodsVerified': False,
            'supplierRedistributionRightsVerified': False, 'newCalculations': 0},
        'separateLegacyCodexAArchive': {
            'status': 'EXACT_BYTE_PARTIAL_PRESERVATION_NOT_CODEX_B_12_STRATEGIES',
            'archive': target.name, 'sha256': sha(archive), 'files': members,
            'rawVendorFilesIncluded': False, 'dailyPriceOrNavFilesIncluded': False,
            'fullOriginalInputsIncluded': False, 'recalculated': False}}
    (output / 'preservation-manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--workspace', type=Path, default=Path('/workspace'))
    args = parser.parse_args()
    print(json.dumps(preserve(args.source, args.output, args.workspace), ensure_ascii=False))
