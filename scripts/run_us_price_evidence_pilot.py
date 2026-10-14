"""Reproduce eight-name pilot counts and validate explicitly restored code evidence.

Input code/probe artifacts are local and explicit; the run does not fetch, execute
third-party programs, reconstruct omitted prices, or accept unverified issuer claims.
"""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import us_price_evidence_pilot as P  # noqa: E402
from pipeline import us_departed_dataset_admission as D  # noqa: E402
from pipeline import replay_calendar as RC  # noqa: E402
from scripts import audit_us_departed_dataset_admission as C  # noqa: E402


def build(artifacts, evidence_directory):
    root = Path(evidence_directory)
    recovery = C.load_json(ROOT / C.RECOVERY);manifest = C.load_json(ROOT / C.STORE)
    found = C.verify_local_artifacts(artifacts, manifest)
    probes = C.load_json(root / 'source-probe-records-v1.json')
    docs = C.load_json(root / 'github-evidence-records-v1.json')
    for doc in docs:
        if doc['status'] == 0:
            raw = (root / doc['localFile']).read_bytes()
            if D.digest(raw) != doc['sha256']: raise ValueError('DOCUMENT_CHECKSUM_MISMATCH')
            doc['supports'] = 'PRODUCER_OR_LIBRARY_CODE_ONLY_NOT_ISSUER_OR_PRICE_BASIS_CERTIFICATION'
    for record in probes:
        record['responseRetrieved'] = record.get('status') == 200
        record['providerResponseReceived'] = record.get('status') is not None
        record['responseSha256'] = record.get('sha256')
        record['requestRecordSha256'] = P.fingerprint(record)
    generator = (root / 'SOURCE_F_GENERATOR.py').read_bytes()
    finding = P.inspect_generator(generator)
    doc_f = next(x for x in docs if x['id'] == 'SOURCE_F_GENERATOR')
    if finding['sourceSha256'] != doc_f['sha256']: raise ValueError('GENERATOR_BYTES_MISMATCH')
    if not finding['findings']: raise ValueError('REPORTED_PRODUCER_FINDING_NOT_REPRODUCED')
    report = {'id': 'US_HISTORICAL_PRICE_EVIDENCE_PILOT_V1', 'verdict': 'BLOCKED_SOURCE_ACCESS',
        'selection': {'initial': list(P.PILOT), 'firstFocus': list(P.FOCUS), 'substitutions': [],
            'rule': 'No identity hold/reuse; D/F present; contiguous history; issuer evidence before expansion; no returns consulted'},
        'sourceAttempts': probes, 'retrievedCodeDocuments': docs, 'sourceFFinding': finding,
        'newIndependentlyValidatedIssuers': 0, 'newVerifiedAsTradedSecurities': 0,
        'newVerifiedCorporateActionChains': 0, 'newVerifiedTerminalEvents': 0,
        'finalAdmittedSessions': None, 'accessCounters': {'forwardOutcomes': 0, 'labels': 0, 'models': 0, 'portfolios': 0},
        'publicPricePayloads': False, 'permanentPrivateStorageConfirmed': False,
        'decision': 'STOP_F_ARCHIVE_EXPANSION; permit direct authoritative source access first; if unavailable prioritize owner-gated prospective capture, without activation',
        'requiredNetworkDomains': ['data.sec.gov', 'www.sec.gov', 'press.nordstrom.com',
                                  'investor.breadfinancial.com', 'www.citrix.com', 'help.yahoo.com'],
        'providerAccessAfterNetworkChange': 'NOT_MEASURED; comply with SEC User-Agent/fair access; stop provider denial',
        'newIssuerEvidenceState': 'NOT_RETRIEVED_PROXY_REFUSAL_NOT_NONEXISTENCE',
        'sourceScalability': 'Producer inspection scales to F candidates; issuer/event verification scalability NOT_MEASURED while official hosts blocked'}
    if found is None:
        report.update(dataState='DATA_UNAVAILABLE', ownerRestoreRequired=manifest, securities=[])
        return report
    paths, panel = found
    snapshots, identity = C.frozen_inputs(recovery)
    inventory = [i for i in recovery['inventory'] if i['auditIdentifier'] in P.PILOT]
    if len(inventory) != 8 or any(i['identityHold'] or i['symbolReuseFlagFromSealedAudit'] for i in inventory):
        raise ValueError('PILOT_PREDEFINED_IDENTITY_SCREEN_FAILED')
    narrowed = {**recovery, 'inventory': inventory}
    narrowed_panel = {**panel, 'rows': [row for row in panel['rows'] if row[1] in P.PILOT]}
    calendar = [str(d.date()) for d in RC.sessions('2013-01-01', '2027-12-31', 'US')]
    expected, _, _, _ = C.membership_grid(snapshots, calendar, set(P.PILOT))
    candidates, provenance, raw_dates = C.local_candidates(paths, narrowed_panel, narrowed,
                                {str(d.date()) for d in RC.sessions('1990-01-01', '2027-12-31', 'US')})
    filings, filing_files, _ = C.read_filing_metadata()
    evidence = {}
    for item in inventory:
        t = item['auditIdentifier'];dates, records = C.identity_evidence(item, identity)
        evidence[t] = {'securityId': item['securityId'], 'identityHold': False, 'identityDates': dates,
            'identityRecords': records, 'rawObservedDays': raw_dates[t], 'provenance': provenance[t],
            'filings': filings.get(t, []), 'basisEvidence': {}, 'lineage': {}, 'terminal': {}, 'memberDays': expected[t]}
    measured, tables = D.audit_sessions(expected, candidates, evidence, calendar)
    report.update(dataState='EXACT_LOCAL_BYTES_VERIFIED', finalAdmittedSessions=measured['finalAdmittedSessions'],
                  independentGateCounts=measured['independentGatePass'], cumulativeGateCounts=measured['cumulativeGatePass'],
                  expectedMemberSessions=measured['originalMissingSessions'], candidateMemberSessions=measured['candidateRecoveredSessions'],
                  states=measured['statusCounts'], securities=[])
    cumulative_by_t = {ticker: Counter() for ticker in P.PILOT}
    for row in tables:
        if row['status'] == 'NO_OBSERVATION': continue
        passed = True
        for gate in D.GATES:
            passed = passed and gate not in row['failedGates']
            cumulative_by_t[row['ticker']][gate] += bool(passed)
    measured_by_t = {i['ticker']: i for i in measured['identifiers']}
    for item in inventory:
        t = item['auditIdentifier'];m = measured_by_t[t]
        f = next(r for r in recovery['acquisition'] if r.get('source') == 'F' and r.get('ticker') == t)
        report['securities'].append({'ticker': t, 'securityId': item['securityId'],
            'issuerNamesCandidateOnly': item['historicalIssuerNames'], 'filingCiksCandidateOnly': m['filingCiks'],
            'observedMembershipEpisodesNotEffectiveDates': item['membershipIntervals'],
            'expectedMemberSessions': len(expected[t]), 'candidatePositiveCloseSessions': item['coveredSessions'],
            'onePublisherPositiveSessionsNotBasisVerified': m['independentGatePass']['SOURCE_PROVENANCE'],
            'selectedPublisher': m['selectedPublisher'], 'rawQuoteWindow': {k: f['quality'][k] for k in ('first', 'last', 'validRows')},
            'endpointInterpretation': 'COMMON_ARCHIVE_CUTOFF_CANDIDATE_NOT_A_TERMINATION_CERTIFICATE',
            'independentGateCounts': m['independentGatePass'], 'cumulativeGateCounts': {gate: cumulative_by_t[t][gate] for gate in D.GATES},
            'h63WindowCountsExistenceOnly': m['endpointCounts'], 'statusCounts': m['statusCounts'],
            'identityEvidence': 'NOT_VERIFIED_OFFICIAL_ACCESS_BLOCKED' if t in P.FOCUS else 'NOT_ATTEMPTED_EXPANSION_STOP',
            'priceBasis': 'NOT_VERIFIED_PACKAGE_VERSION_AND_YAHOO_CLOSE_SEMANTICS_UNKNOWN',
            'producerNormalPath': 'VERIFIED_INCORRECT; not proof prices incorrect',
            'splitDividendLineage': 'NOT_VERIFIED', 'departureAndTerminalEconomics': 'NOT_VERIFIED_DISTINCT_EVENTS_REQUIRED',
            'pitIssuerFilingLink': 'NOT_VERIFIED; existing accepted/available timestamps do not prove price issuer',
            'sourceProvenance': provenance[t], 'blocker': 'Direct official issuer/event access denied; pinned F generator does not reproduce normal downloads; exact price basis still unknown'})
    input_identity = {'mainManifestSha256': D.digest((ROOT / C.STORE).read_bytes()),
        'recoveryReportSha256': D.digest((ROOT / C.RECOVERY).read_bytes()),
        'admissionCodeSha256': D.digest(Path(D.__file__).read_bytes()),
        'pilotCodeSha256': D.digest(Path(P.__file__).read_bytes()), 'scriptSha256': D.digest(Path(__file__).read_bytes()),
        'localArtifacts': {k: {'sha256': manifest[k]['sha256'], 'bytes': manifest[k]['bytes']} for k in ('raw', 'panel')},
        'evidenceRecordsSha256': {p: D.digest((root / p).read_bytes()) for p in ('source-probe-records-v1.json', 'github-evidence-records-v1.json')},
        'fundamentalsFiles': filing_files}
    report.update(inputManifest=input_identity, inputManifestSha256=D.digest(D.canonical(input_identity)))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private-artifacts', type=Path, required=True)
    parser.add_argument('--private-evidence', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args(argv)
    result = build(args.private_artifacts, args.private_evidence)
    with args.report.open('xb') as handle: handle.write(D.canonical(result) + b'\n')
    print(json.dumps({k: result[k] for k in ('verdict', 'dataState', 'finalAdmittedSessions')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
