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


def manifests(root):
    """(annual-style manifests, chapter manifests): retained evidence only, never a network read."""
    annual=sorted((root/V1/'acquired-dart').glob('manifest-*.json'))+sorted((root/V2/'acquired-dart/annual').glob('batch-*/manifest-originals.json'))
    chapters=sorted((root/V2/'acquired-dart/chapters').glob('manifest-chapters.json'))
    return annual,chapters


def retained(root):
    objects,records,chapter_records=[],[],[]
    sources={}
    annual,chapters=manifests(root)
    for p in annual+chapters:
        m=json.loads(p.read_text()); raw=(p.parent/m['archive']).read_bytes()
        if V.digest(raw)!=m['archiveSha256']:
            raise ValueError('ACQUISITION_ARCHIVE_CHANGED')
        bodies=json.loads(gzip.decompress(raw))
        for sha,b64 in bodies.items():
            body=base64.b64decode(b64)
            if V.digest(body)!=sha:
                raise ValueError('SOURCE_SHA_CHANGED')
            sources[sha]=body
        (chapter_records if p in chapters else records).extend(m['records'])
        objects.append({'path':str(p.relative_to(root)),'sha256':V.digest(p.read_bytes()),'archiveSha256':m['archiveSha256']})
    return records,chapter_records,sources,objects


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


def observe(target,main_sha,main_status,sections,sources):
    """Shared by annual records and chapter supplements: identical admission, identical template."""
    receipt=target['receiptNos'][0];corp=target['corpCode']; ticker=target['ticker']
    raw=sources.get(main_sha)
    if main_status!=200 or raw is None or target.get('identityBasis')!='EXACT_STOCK_CODE':
        return [],'SOURCE_OR_IDENTITY_UNPROVEN'
    text=raw.decode('utf-8',errors='strict')
    identity="openCorpInfoNew('"+corp+"',"
    title=re.search(r'<title>(.*?)</title>',text,re.S)
    release=receipt[:4]+'-'+receipt[4:6]+'-'+receipt[6:8]
    if text.count(identity)!=1 or not title or '사업보고서' not in title[1] or release.replace('-','.') not in title[1]:
        return [],'DATED_ISSUER_RELEASE_UNPROVEN'
    output=[]
    for section_sha,section_url in sections:
        body=sources[section_sha];source=body.decode('utf-8',errors='strict')
        plain=re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]*>',' ',source)))
        for candidate in explicit_labels(plain):
            # Retain full exact section locator: unique even with repeated markers.
            row={'security_id':'KRX:'+ticker,'ticker':ticker,'corpCode':corp,'issuer_id':'DART:'+corp,
                 'reported_as_of':None,'fiscal_year_metadata':target['fiscalYear'],'report_period_status':'EXACT_REPORT_PERIOD_UNVERIFIED; NEVER_INFERRED_FROM_ENDPOINT_FISCAL_YEAR',
                 'receipt_no':receipt,'known_from':release,'release_timestamp_precision':'DAY; strictly subsequent signal only',
                 'subject_scope':'ISSUER','identity_status':'DATED_ISSUER_SECURITY','identity_source_sha256':main_sha,
                 'identity_locator':identity,'identity_bridge_basis':target['identityBasis'],
                 'source_sha256':section_sha,'source_locator':source,'source_url':section_url,
                 'taxonomy_name':'KSIC_AS_REPORTED','taxonomy_version':None,'taxonomy_version_status':'UNVERIFIED; never inferred from code prefix or filing year',
                 'evidence_tier':'DART_EXPLICIT_ISSUER_CLASSIFICATION' if candidate['reported_code'] else 'DART_EXPLICIT_ISSUER_LABEL','evidence_quality':'EXPLICIT_ISSUER_TEMPLATE_WITH_DATED_CORP_IDENTIFIER',
                 **candidate}
            admitted,reason=V.admit(row,sources,{})
            if admitted is None:
                raise ValueError(reason)
            output.append(admitted)
    return output,None


def observations_from_record(record,sources):
    target=record['target'];receipt=target['receiptNos'][0]
    main=record['responses'][0]
    sections=[]
    for section in record['sections']:
        if section['node']['rcpNo']!=receipt:
            raise ValueError('LATER_RECEIPT_NODE_REFUSED')
        sections.append((section['sha256'],next(r['url'] for r in record['responses'] if r.get('sha256')==section['sha256'])))
    return observe(target,main.get('sha256'),main.get('status'),sections,sources)


def observations_from_chapter(record,sources):
    """A frozen supplement: the parent business chapter of an already-retained original receipt."""
    target,response=record['target'],record['response']
    if record['node']['rcpNo']!=target['receiptNos'][0]:
        raise ValueError('LATER_RECEIPT_NODE_REFUSED')
    if response.get('status')!=200 or response.get('sha256') not in sources:
        return [],'CHAPTER_SOURCE_UNAVAILABLE'
    main=record['mainResponse']
    return observe(target,main['sha256'],main['status'],[(response['sha256'],response['url'])],sources)


def issuer_year_coverage(root,receipts_read):
    """Metadata-only counts of what the frozen inventory planned and the listing answered."""
    plan=read(root,SPEC+'/acquisition-plan.json');inventory=read(root,SPEC+'/issuer-year-inventory.json')
    selected=missing=0;listing=Counter();annual_receipts=set()
    for path in sorted((root/V2/'inventory').glob('batch-*/inventory.json')):
        for entry in json.loads(path.read_text()):
            listing[entry['listingStatus']]+=1
            selected+=len(entry['selected']);missing+=len(entry['missingYears'])
            annual_receipts.update(r['receiptNos'][0] for r in entry['selected'])
    return {'plannedIssuerYears':inventory['issuerYears'],'issuers':len(inventory['issuers']),
            'listedOriginalAnnualReceipts':len(annual_receipts),'listedSelectedIssuerYears':selected,
            'issuerYearsWithNoListedOriginal':missing,'listingStatus':dict(listing),
            'receiptsReadForClassification':len(receipts_read),
            'retainedBeforeV2':len(plan['retainedReceipts'])}


def taxonomy_evidence(root):
    manifest=read(root,V2+'/taxonomy-sources/manifest.json')
    source=root/manifest['derivedFrom']
    if V.digest(source.read_bytes())!=manifest['derivedFromSha256']:
        raise ValueError('TAXONOMY_EVIDENCE_NOT_DERIVED_FROM_RETAINED_SOURCES')
    return manifest


def build(root=ROOT):
    root=Path(root);criteria=read(root,SPEC+'/criteria.json')
    raw=(root/SPEC/'criteria.json').read_bytes()
    if V.digest(raw)!=(root/SPEC/'criteria.json.sha256').read_text().strip():
        raise ValueError('FROZEN_V2_CRITERIA_CHANGED')
    if V.digest((root/V1/'top120-inputs.json').read_bytes())!=criteria['v1InputsSha256']:
        raise ValueError('EXISTING_KRX_PIT_UNIVERSE_CHANGED')
    if V.digest((root/V1/'identity-inventory.json').read_bytes())!=criteria['identityInventorySha256']:
        raise ValueError('EXISTING_IDENTITY_CHANGED')
    records,chapter_records,sources,manifest=retained(root);observations=[];reasons=Counter();receipts=set();chapter_reasons=Counter();chapter_observations=0
    for record in records:
        receipt=record['target']['receiptNos'][0]
        if receipt in receipts:
            continue
        receipts.add(receipt)
        obs,reason=observations_from_record(record,sources)
        observations.extend(obs)
        reasons[reason or ('EXPLICIT_ISSUER_LABEL_FOUND' if obs else 'NO_SAFE_ISSUER_TEMPLATE')]+=1
    for record in chapter_records:
        obs,reason=observations_from_chapter(record,sources)
        observations.extend(obs);chapter_observations+=len(obs)
        chapter_reasons[reason or ('EXPLICIT_ISSUER_LABEL_FOUND' if obs else 'NO_SAFE_ISSUER_TEMPLATE')]+=1
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
                 acquiredV2Receipts=sum(len(json.loads(p.read_text())['records']) for p in (root/V2/'acquired-dart/annual').glob('batch-*/manifest-originals.json')),
                 chapterSupplement={'frozenTargets':len(chapter_records),'readingStatus':dict(chapter_reasons),'observations':chapter_observations},
                 issuerYearEvidence=issuer_year_coverage(root,receipts),
                 conflictedNameDates=sum(len(d['conflictedSecurityIds']) for d in audit['dates']),
                 retainedV1ReceiptCount=413,terminalDocumentsRetained=92,sourceReceiptsRead=len(receipts),
                 taxonomyChoice=None,globalTaxonomyEvidence=taxonomy_evidence(root))
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
