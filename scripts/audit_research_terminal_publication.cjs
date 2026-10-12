/* Read-only verification of an explicitly acquired Git snapshot. No publication,
 * portfolio calculation, model import, historical replay or network requests.
 * Input directory: commit.json, tree.json and unchanged p1-*.json/jsonl bytes.
 * node scripts/audit_research_terminal_publication.cjs INPUT COMMIT MAIN
 */
const fs=require('node:fs'),path=require('node:path'),{createHash,webcrypto}=require('node:crypto');
globalThis.crypto=webcrypto;
const A=require('../app.js');
const hash=(bytes,algorithm='sha256')=>createHash(algorithm).update(bytes).digest('hex');
async function audit(directory,commit,main,now=Date.now()) {
  if(!/^[a-f0-9]{40}$/.test(commit)||!/^[a-f0-9]{40}$/.test(main)) throw Error('Explicit immutable commits required');
  const read=n=>fs.readFileSync(path.join(directory,n));
  const identity=JSON.parse(read('commit.json')),tree=JSON.parse(read('tree.json'));
  if(identity.sha!==commit||tree.sha!==identity.commit.tree.sha||tree.truncated||!Array.isArray(tree.tree)) throw Error('Incomplete or mismatched Git snapshot');
  const files={};
  for(const [name,local] of [['latest.json','p1-latest.json'],['publication-status.json','p1-publication.json'],['receipts.jsonl','p1-receipts.jsonl']]) {
    const bytes=read(local),entry=tree.tree.find(x=>x.path==='ledger/weekly-decisions/'+name&&x.type==='blob');
    if(!entry||hash(Buffer.concat([Buffer.from(`blob ${bytes.length}\0`),bytes]),'sha1')!==entry.sha) throw Error('Git blob mismatch: '+name);
    files[name]={bytes,sha256:hash(bytes),gitBlobSha:entry.sha};
  }
  const receipts=await A.parseReceipts(files['receipts.jsonl'].bytes.toString('utf8'));
  const latest=JSON.parse(files['latest.json'].bytes),publication=JSON.parse(files['publication-status.json'].bytes);
  const required=['latest.json','publication-status.json','receipts.jsonl'].map(n=>A.CHAMPION_PATH+n);
  const present=required.filter(p=>tree.tree.some(x=>x.path===p&&x.type==='blob'));
  return {
    schema:'RESEARCH_TERMINAL_PUBLICATION_AUDIT_V31',observedAt:new Date(now).toISOString(),mainCommit:main,signalHistoryCommit:commit,
    gitTreeSha:tree.sha,sourceKind:'ACTUAL_PUBLISHED_GIT_BYTES',readOnly:true,
    files:Object.fromEntries(Object.entries(files).map(([k,v])=>[k,{sha256:v.sha256,gitBlobSha:v.gitBlobSha}])),
    p1:{publicationStatus:publication.status,sourceObservedAt:latest.generatedAt,publicationAttemptedAt:publication.attemptedAt,digestVerifiedRecords:receipts.length,
      regions:Object.fromEntries(['KR','US'].map(m=>{const d=A.decisionState({latest,publication,receipts},m,now);return [m,{state:d.state,reason:d.reason||null,latestValidDecisionDate:d.last?.asOfDate||null,currentDecisionDate:d.receipt?.asOfDate||null,weights:d.receipt?.weights||null,digest:d.receipt?.digest||null,noTradeReason:d.receipt?.noTradeReason||null,freshness:d.freshness||null}];}))},
    research:{namespace:A.CHAMPION_PATH,presentFiles:present,missingFiles:required.filter(p=>!present.includes(p)),
      status:present.length===0?'NOT_PUBLISHED':present.length<3?'INCOMPLETE_PUBLICATION':'PRESENT_REQUIRES_CURRENT_INPUT_VERIFICATION',
      stockWeightParity:'NOT_MEASURED_NO_VERIFIED_CURRENT_PAIR',p1Dependency:'Separate accounting/publication namespace; P1 remains visible when research is unavailable'},
    limitations:['No current research allocation is derived by this audit.','Current site-data freshness cannot be inferred from historical state/latest.json.','Use browser/live verification for site-data availability; no source failure is treated as proof of missing publication.']
  };
}
module.exports={audit};
if(require.main===module) audit(...process.argv.slice(2)).then(r=>console.log(JSON.stringify(r,null,2))).catch(e=>{console.error(e.message);process.exitCode=1;});
