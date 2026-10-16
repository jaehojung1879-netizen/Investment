"""Synthetic network/control-flow checks plus published non-price evidence integrity."""
import json
from pathlib import Path
import pytest
from pipeline import us_price_evidence_pilot as P
from scripts import run_us_price_evidence_pilot as S

BAD = '''def collect(tickers):
    for ticker in tickers:
        try:
            print(ticker)
        except KeyError:
            pass
            data = reader.DataReader(ticker)
            data.to_csv(ticker)
'''
GOOD = '''def collect(tickers):
    for ticker in tickers:
        print(ticker)
        data = reader.DataReader(ticker)
        data.to_csv(ticker)
'''


def test_static_control_flow_proof_not_third_party_execution():
    proof = P.inspect_generator(BAD)
    assert len(proof['findings']) == 1
    assert proof['findings'][0]['status'] == 'VERIFIED_INCORRECT_DECLARED_NORMAL_REPRODUCTION_PATH'
    assert P.inspect_generator(GOOD)['findings'] == []
    assert 'Prices incorrect' in proof['doesNotProve']
    assert P.inspect_generator(BAD.encode()) == proof


def test_proxy_denial_stops_host_no_retry_or_redirect(tmp_path):
    calls = []
    def fetch(url):
        calls.append(url)
        raise ConnectionError('Tunnel connection failed: 403 Forbidden')
    result = P.probe([('one','https://sec.invalid/a'),('two','https://sec.invalid/b')],
                     tmp_path,fetch=fetch,now=lambda:'SYNTHETIC',sleep=lambda _:None)
    assert len(calls) == 1
    assert result[0]['state'] == 'PROXY_CONNECT_403' and result[0]['responseSha256'] is None
    assert result[1]['state'] == 'NOT_ATTEMPTED_HOST_STOP'


def test_provider_403_not_proxy_and_retrieval_not_validation(tmp_path):
    result = P.probe([('one','https://issuer.invalid/a'),('two','https://other.invalid/a')], tmp_path,
        fetch=lambda url: (403,b'denied',None) if 'issuer' in url else (200,b'SYNTHETIC DOCUMENT',None),
        now=lambda:'SYNTHETIC',sleep=lambda _:None)
    assert result[0]['state'] == 'PROVIDER_HTTP_403'
    assert result[1]['state'] == 'RETRIEVED_NOT_YET_VALIDATED'
    assert (tmp_path/result[1]['localFilename']).read_bytes() == b'SYNTHETIC DOCUMENT'


def test_redirect_not_used_as_access_bypass(tmp_path):
    calls = []
    def fetch(url):
        calls.append(url);return 302,b'', 'https://somewhere.invalid/a'
    result = P.probe([('one','https://issuer.invalid/a')], tmp_path,fetch=fetch,now=lambda:'SYNTHETIC',sleep=lambda _:None)
    assert len(calls) == 1 and result[0]['state'] == 'REDIRECT_NOT_FOLLOWED'


def test_budget_and_checkout_guard(tmp_path):
    fetch = lambda _:pytest.fail('must reject before access')
    with pytest.raises(ValueError,match='REQUEST_BUDGET'):
        P.probe([('x','https://issuer.invalid/a')]*9,tmp_path,fetch=fetch,now=lambda:'SYNTHETIC',sleep=lambda _:None)
    checkout=tmp_path/'repo';checkout.mkdir();(checkout/'.git').mkdir();(checkout/'.git/HEAD').write_text('ref: refs/heads/test')
    with pytest.raises(ValueError,match='OUTSIDE_GIT'):
        P.probe([],checkout,fetch=fetch,now=lambda:'SYNTHETIC',sleep=lambda _:None)


def test_verified_producer_error_does_not_create_fake_issuer_pass():
    r=json.loads((S.ROOT/'docs/us-readiness/us-price-evidence-pilot-v1.json').read_bytes())
    assert r['newIndependentlyValidatedIssuers']==r['newVerifiedAsTradedSecurities']==0
    assert r['newVerifiedCorporateActionChains']==r['newVerifiedTerminalEvents']==0
    assert r['finalAdmittedSessions']==0 and r['verdict']=='BLOCKED_SOURCE_ACCESS'
    assert r['expectedMemberSessions']==sum(x['expectedMemberSessions']for x in r['securities'])
    assert r['candidateMemberSessions']==sum(x['candidatePositiveCloseSessions']for x in r['securities'])
    assert len(r['securities'])==8 and r['selection']['substitutions']==[]
    assert r['inputManifestSha256']==P.fingerprint(r['inputManifest'])
    assert all(v==0 for v in r['accessCounters'].values())
    for x in r['sourceAttempts']:
        assert x['failureClass']=='PROXY_CONNECT_403'
        assert x['providerResponseReceived'] is False and x['responseSha256'] is None
    assert all(x['sourceRevisionDate'] and x['acquiredAt'] for x in r['retrievedCodeDocuments']if x['status']==0)
    assert all(x['rawQuoteWindow']['last']=='2020-05-22' for x in r['securities'])
    # No third-party price values or full producer text published.
    forbidden={'close','adjClose','volume','payoff','forwardReturn','sourceText'}
    def check(value):
        if isinstance(value,dict):
            assert not forbidden.intersection(value)
            for child in value.values():check(child)
        elif isinstance(value,list):
            for child in value:check(child)
    check(r)


def test_no_outcome_or_exec_interface():
    source=Path(P.__file__).read_text()
    assert 'exec(' not in source and 'eval(' not in source
    assert 'forward_return' not in source and 'us_cash_profitability_exploratory' not in source
    assert P.PILOT[:3]==P.FOCUS
