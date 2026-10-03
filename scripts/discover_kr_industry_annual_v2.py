"""DART annual-original metadata discovery for the frozen 254 issuer inventory."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.collect_dart_raw_statements import call_json  # noqa: E402
from scripts.collect_kr_industry_membership_sources import Collector  # noqa: E402


def select_originals(rows,issuer):
    targets={}
    for row in sorted(rows,key=lambda r:str(r.get('rcept_no',''))):
        name=row.get('report_nm','')
        match=re.fullmatch(r'사업보고서\s*\((\d{4})\.(\d{2})\)',name)
        if not match or int(match[1]) not in issuer['years'] or row.get('corp_code')!=issuer['corpCode']:
            continue
        receipt=row.get('rcept_no','');release=row.get('rcept_dt','')
        if not re.fullmatch(r'\d{14}',receipt) or release!=receipt[:8]:
            continue
        for ticker in issuer['tickers']:
            if row.get('stock_code')!=ticker.split('.')[0]:
                continue
            # Metadata is the report period; no assumption that all fiscal ends
            # are December. Exact reporting month is kept, daily period unknown.
            targets.setdefault((ticker,match[1]),{'ticker':ticker,'corpCode':issuer['corpCode'],'receiptNos':[receipt],
                'fiscalYear':int(match[1]),'reportPeriod':match[1]+'-'+match[2],'originalStatus':'EARLIEST_NON_CORRECTION_ANNUAL_LIST_ROW',
                'identityBasis':'EXACT_STOCK_CODE','availableFrom':release[:4]+'-'+release[4:6]+'-'+release[6:],
                'listingMetadata':row})
    return sorted(targets.values(),key=lambda r:(r['ticker'],r['fiscalYear']))


def discover(batch,output):
    key=os.environ.get('DART_API_KEY','')
    if not key:
        raise ValueError('DART_SECRET_NOT_MAPPED')
    base=ROOT/'research_specs/kr-industry-membership-foundation-v2'
    plan=json.loads((base/'acquisition-plan.json').read_text())
    inv_raw=(base/'issuer-year-inventory.json').read_bytes()
    if hashlib.sha256(inv_raw).hexdigest()!=plan['issuerInventorySha256']:
        raise ValueError('FROZEN_ISSUER_INVENTORY_CHANGED')
    issuers=json.loads(inv_raw)['issuers'][batch*10:(batch+1)*10]
    retained=set(plan['retainedReceipts'])
    retained.update(json.loads((base/'public-seed-checkpoint.json').read_text())['completedReceipts'])
    for p in (ROOT/'data/kr-industry-membership-foundation-v2/acquired-dart').glob('manifest-*.json'):
        retained.update(r['target']['receiptNos'][0] for r in json.loads(p.read_text())['records'])
    output.mkdir(parents=True,exist_ok=False);requests=0;targets=[];results=[]
    for issuer in issuers:
        pages=[];status=None
        for page in (1,2):
            requests+=1
            try:
                payload=call_json('list.json',{'crtfc_key':key,'corp_code':issuer['corpCode'],'bgn_de':plan['listingStart'],'end_de':plan['listingEnd'],
                    'pblntf_detail_ty':'A001','page_count':'100','page_no':str(page),'sort':'date','sort_mth':'asc'})
                # A credential-bearing response is neither logged nor retained.
                if key in json.dumps(payload):raise ValueError('UNSAFE_SOURCE_RESPONSE')
            except Exception as exc:
                status=type(exc).__name__;break
            status=str(payload.get('status'))
            pages.append(payload)
            if status!='000' or int(payload.get('total_page',0))<=page:break
        complete=bool(pages) and (status=='013' or (status=='000' and int(pages[-1].get('total_page',0))<=len(pages)))
        selected=select_originals([r for p in pages for r in p.get('list',[])],issuer) if complete else []
        results.append({'issuer':issuer,'listingStatus':status,'paginationComplete':complete,'sourcePages':pages,'selected':selected,
                        'missingYears':[y for y in issuer['years'] if y not in {r['fiscalYear'] for r in selected}]})
        targets.extend(r for r in selected if r['receiptNos'][0] not in retained)
    frozen={'contract':'KR_INDUSTRY_ORIGINAL_ANNUAL_REQUEST_LIST_V2','historicalOutcomeComputed':False,'maxWorkers':4,
            'targets':targets,'maxCalls':len(targets)*3,'timeoutSeconds':15,'maxBodyBytes':4000000,
            'discoveryRequests':requests,'issuerInventorySha256':plan['issuerInventorySha256'],'batch':batch}
    raw=(json.dumps(frozen,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode();(output/'remaining.json').write_bytes(raw)
    (output/'remaining.json.sha256').write_text(hashlib.sha256(raw).hexdigest()+'\n')
    (output/'inventory.json').write_text(json.dumps(results,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
    print(json.dumps({'batch':batch,'issuers':len(issuers),'selectedOriginals':sum(len(r['selected']) for r in results),'unretainedOriginals':len(targets),'listingRequests':requests,'requestListSha256':hashlib.sha256(raw).hexdigest()}))


def collect_serial(plan_path,output):
    # Four Actions jobs max-parallel=4, one public request worker per job.
    raw=plan_path.read_bytes();plan=json.loads(raw)
    if hashlib.sha256(raw).hexdigest()!=plan_path.with_suffix('.json.sha256').read_text().strip():raise ValueError('UNFROZEN_REQUEST_LIST')
    output.mkdir(parents=True,exist_ok=False)
    import base64
    import gzip
    objects,records={},[];collector=Collector(plan,plan['maxCalls'])
    for target in plan['targets']:
        r=collector.receipt(target)
        for response in r['responses']:
            body=response.pop('raw')
            if body is not None:objects[hashlib.sha256(body).hexdigest()]=base64.b64encode(body).decode()
        records.append(r)
        print(f'original annual source {len(records)}/{len(plan["targets"])}',flush=True)
    archive=output/'originals.json.gz';archive.write_bytes(gzip.compress(json.dumps(objects,sort_keys=True,separators=(',',':')).encode(),mtime=0))
    m={'contract':'KR_INDUSTRY_PUBLIC_DART_BATCH_V2','planSha256':hashlib.sha256(raw).hexdigest(),'records':records,'requests':collector.calls,'archive':archive.name,'archiveSha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'historicalOutcomeComputed':False}
    (output/'manifest-originals.json').write_text(json.dumps(m,ensure_ascii=False,sort_keys=True,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--batch',type=int);p.add_argument('--output',type=Path,required=True);p.add_argument('--plan',type=Path);a=p.parse_args()
    if a.plan:collect_serial(a.plan,a.output)
    else:discover(a.batch,a.output)
