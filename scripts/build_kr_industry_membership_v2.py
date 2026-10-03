"""Offline reproduction of v2 issuer information state, without outcomes."""
from __future__ import annotations
import argparse
import base64
from collections import Counter
import gzip
import html
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pipeline import kr_industry_membership_v2 as V  # noqa: E402
from pipeline.kr_industry_membership import top120_schedule  # noqa: E402

V1='data/kr-industry-membership-foundation-v1'
V2='data/kr-industry-membership-foundation-v2'
SPEC='research_specs/kr-industry-membership-foundation-v2'


def read(root,path):
    return json.loads((root/path).read_text())


def retained(root):
    objects,records=[],[]
    sources={}
    for directory in (V1+'/acquired-dart',V2+'/acquired-dart'):
        for p in sorted((root/directory).glob('manifest-*.json')):
            m=json.loads(p.read_text()); raw=(p.parent/m['archive']).read_bytes()
            if V.digest(raw)!=m['archiveSha256']:
                raise ValueError('ACQUISITION_ARCHIVE_CHANGED')
            bodies=json.loads(gzip.decompress(raw))
            for sha,b64 in bodies.items():
                body=base64.b64decode(b64)
                if V.digest(body)!=sha:
                    raise ValueError('SOURCE_SHA_CHANGED')
                sources[sha]=body
            records.extend(m['records']);objects.append({'path':str(p.relative_to(root)),'sha256':V.digest(p.read_bytes()),'archiveSha256':m['archiveSha256']})
    return records,sources,objects


# High precision issuer-only templates. No company-name, subsidiary, product,
# multiple-segment or code-prefix heuristics. Unmatched text stays a reading list.
ISSUER = r'(?:당사는|지배회사는|지배회사인\s*[^.。]{1,30}?는|당사의\s*(?:주된 생산제품 및 영업활동은|모든 생산제품은|사업\s*부문은))'
CLASSIFICATION = re.compile(ISSUER+r'\s*[^.。]{0,65}?(?:한국표준산업분류(?:표)?)(?P<body>[^.。]{5,200})')


def explicit_labels(plain):
    result=[]
    for match in CLASSIFICATION.finditer(plain):
        body=match['body']
        if any(word in body.split('해당')[0].split('분류되')[0] for word in ('종속회사','자회사','사업부문별','합병상대')):
            continue
        # Quoted assignment, or an assignment after the classification rule.
        quoted=re.search(r"['‘](?P<label>[^'’]{2,100}?업)(?:\s*\([^)]*\))?['’]",body)
        labelled=re.search(r'(?:에\s*의(?:거(?:하여)?|한)|상\s*|소분류인\s*)(?P<label>[^()\[\]「」\'’]{2,90}?업)(?:\s*\((?P<code>[A-U]?\d{2,5})\))?\s*(?:에\s*해당|으로\s*분류|을\s*주된)',body)
        selected=quoted or labelled
        if not selected:
            continue
        label=selected['label'].strip().strip('「」, ')
        label=re.sub(r'^(?:표\s*상의|동일한\s*소분류인|소분류에\s*의한|소분류에\s*의거,|분류표에\s*의한)\s*','',label)
        if len(label)>70 or '당사' in label or '한국표준' in label:
            continue
        code_match=re.search(r'(?:분류번호\s*:\s*|\()([A-U]?\d{2,5})\)',body)
        result.append({'reported_label':label,'reported_code':code_match[1] if code_match else None,'classification_level':'EXPLICIT_LITERAL_ISSUER_LABEL','sentence':match[0]})
    return result


def observations_from_record(record,sources):
    target=record['target'];receipt=target['receiptNos'][0];corp=target['corpCode']; ticker=target['ticker']
    main=record['responses'][0]
    raw=sources.get(main.get('sha256'))
    if main.get('status')!=200 or raw is None or target.get('identityBasis')!='EXACT_STOCK_CODE':
        return [],'SOURCE_OR_IDENTITY_UNPROVEN'
    text=raw.decode('utf-8',errors='strict')
    identity="openCorpInfoNew('"+corp+"',"
    title=re.search(r'<title>(.*?)</title>',text,re.S)
    release=receipt[:4]+'-'+receipt[4:6]+'-'+receipt[6:8]
    if text.count(identity)!=1 or not title or '사업보고서' not in title[1] or release.replace('-','.') not in title[1]:
        return [],'DATED_ISSUER_RELEASE_UNPROVEN'
    output=[]
    for section in record['sections']:
        if section['node']['rcpNo']!=receipt:
            raise ValueError('LATER_RECEIPT_NODE_REFUSED')
        body=sources[section['sha256']];source=body.decode('utf-8',errors='strict')
        plain=re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]*>',' ',source)))
        for candidate in explicit_labels(plain):
            # Retain full exact section locator: unique even with repeated markers.
            row={'security_id':'KRX:'+ticker,'ticker':ticker,'corpCode':corp,'issuer_id':'DART:'+corp,
                 'reported_as_of':None,'fiscal_year_metadata':target['fiscalYear'],'report_period_status':'EXACT_REPORT_PERIOD_UNVERIFIED; NEVER_INFERRED_FROM_ENDPOINT_FISCAL_YEAR',
                 'receipt_no':receipt,'known_from':release,'release_timestamp_precision':'DAY; strictly subsequent signal only',
                 'subject_scope':'ISSUER','identity_status':'DATED_ISSUER_SECURITY','identity_source_sha256':main['sha256'],
                 'identity_locator':identity,'identity_bridge_basis':target['identityBasis'],
                 'source_sha256':section['sha256'],'source_locator':source,'source_url':next(r['url'] for r in record['responses'] if r.get('sha256')==section['sha256']),
                 'taxonomy_name':'KSIC_AS_REPORTED','taxonomy_version':None,'taxonomy_version_status':'UNVERIFIED; never inferred from code prefix or filing year',
                 'evidence_tier':'DART_EXPLICIT_ISSUER_CLASSIFICATION' if candidate['reported_code'] else 'DART_EXPLICIT_ISSUER_LABEL','evidence_quality':'EXPLICIT_ISSUER_TEMPLATE_WITH_DATED_CORP_IDENTIFIER',
                 **candidate}
            admitted,reason=V.admit(row,sources,{})
            if admitted is None:
                raise ValueError(reason)
            output.append(admitted)
    return output,None


def build(root=ROOT):
    root=Path(root);criteria=read(root,SPEC+'/criteria.json')
    raw=(root/SPEC/'criteria.json').read_bytes()
    if V.digest(raw)!=(root/SPEC/'criteria.json.sha256').read_text().strip():
        raise ValueError('FROZEN_V2_CRITERIA_CHANGED')
    if V.digest((root/V1/'top120-inputs.json').read_bytes())!=criteria['v1InputsSha256']:
        raise ValueError('EXISTING_KRX_PIT_UNIVERSE_CHANGED')
    if V.digest((root/V1/'identity-inventory.json').read_bytes())!=criteria['identityInventorySha256']:
        raise ValueError('EXISTING_IDENTITY_CHANGED')
    records,sources,manifest=retained(root);observations=[];reasons=Counter();receipts=set()
    for record in records:
        receipt=record['target']['receiptNos'][0]
        if receipt in receipts:
            continue
        receipts.add(receipt)
        obs,reason=observations_from_record(record,sources)
        observations.extend(obs)
        reasons[reason or ('EXPLICIT_ISSUER_LABEL_FOUND' if obs else 'NO_SAFE_ISSUER_TEMPLATE')]+=1
    # Same issuer/security/release/label can appear in two source sections.
    unique={ (r['security_id'],r['known_from'],r['reported_label'],r['reported_code']):r for r in observations }
    observations=sorted(unique.values(),key=lambda r:(r['security_id'],r['known_from'],r['reported_label']))
    inputs=read(root,V1+'/top120-inputs.json');schedule,_=top120_schedule(inputs)
    identity=read(root,V1+'/identity-inventory.json')
    terminal_ids=set(read(root,V1+'/identity-provenance.json')['terminalSecurities'])
    # Only proven terminal dates, not disappearance from Top120 rankings.
    ends={s['securityId']:s['delisted'] for i in identity['issuers'] for s in i['securities'] if s['ticker'] in terminal_ids and s.get('delisted')}
    audit=V.audit(observations,schedule,criteria,ends)
    audit.update(v1Decision=criteria['v1PreservedDecision'],criteriaSha256=V.digest(raw),universeSourceCommit=inputs['sourceCommit'],
                 everTop120Securities=len(inputs['securities']),sourceManifests=manifest,receiptReadingStatus=dict(reasons),
                 acquiredV2Receipts=sum(len(json.loads(p.read_text())['records']) for p in (root/V2/'acquired-dart').glob('manifest-*.json')),
                 retainedV1ReceiptCount=413,terminalDocumentsRetained=92,sourceReceiptsRead=len(receipts),
                 taxonomyChoice=None,globalTaxonomyEvidence=read(root,V2+'/taxonomy-sources/manifest.json'))
    if audit['signalDates']!=610 or audit['nameDates']!=73200:
        raise ValueError('FROZEN_RESEARCH_CALENDAR_CHANGED')
    return observations,audit


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--verify',action='store_true');a=p.parse_args()
    observations,audit=build();a.output.mkdir(parents=True,exist_ok=True)
    for name,value in [('observations.json.gz',observations),('audit.json.gz',audit)]:
        raw=gzip.compress((json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode(),mtime=0)
        path=a.output/name
        if a.verify:
            if path.read_bytes()!=raw:raise ValueError('OFFLINE_REPRODUCTION_CHANGED:'+name)
        else:path.write_bytes(raw)
    print(json.dumps({k:audit[k] for k in ('decision','admittedObservations','acquiredV2Receipts','annual','receiptReadingStatus')},ensure_ascii=False))
