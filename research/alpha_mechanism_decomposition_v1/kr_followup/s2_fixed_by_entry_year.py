"""S2 vs KODEX 200 6/12-month fixed-holding excess by ENTRY YEAR (2022+), and the compounded chain of non-overlapping cohorts.

    python research/alpha_mechanism_decomposition_v1/kr_followup/s2_fixed_by_entry_year.py   (scratch path inside; reuses s2_decomposition.cohort)
"""
import importlib.util, sys, json
import numpy as np, pandas as pd
sys.path.insert(0,'.')
spec=importlib.util.spec_from_file_location("s2d","research/alpha_mechanism_decomposition_v1/kr_followup/s2_decomposition.py"); D=importlib.util.module_from_spec(spec); sys.modules['s2d']=D; spec.loader.exec_module(D)
I2,ctx2,base=D.RC.setup('/tmp/claude-0/-home-user-Investment/76059d7d-4cd1-55a9-b56d-5841074c0b7b/scratchpad/data')
out={}
for H in (126,252):
    rows=[]
    for d in base['dates']:
        if d < pd.Timestamp('2022-01-01'): continue
        a=D.cohort(I2,ctx2,base,base['s2'][d],d,H); b=D.cohort(I2,ctx2,base,{D.M.ETF:1.0},d,H)
        if a is None or b is None or 'unresolved' in a: continue
        rows.append({'entryYear':a['entry'].year,'s2':a['net'],'etf':b['net']})
    df=pd.DataFrame(rows); g=df.groupby('entryYear')
    out[H]={int(y):{'cohorts':len(x),'s2':round(float(x.s2.mean())*100,2),'etf':round(float(x.etf.mean())*100,2),'excess':round(float((x.s2-x.etf).mean())*100,2)} for y,x in g}
    # non-overlapping chain from the first cohort: compounding of every H/5-th cohort
    step=int(round(H/5)); ch=df.iloc[::step]
    out[f'{H}_chain']={'links':len(ch),'s2Annualised':float(np.prod(1+ch.s2)**(252/(H*len(ch)))-1),'etfAnnualised':float(np.prod(1+ch.etf)**(252/(H*len(ch)))-1)}
print(json.dumps(out,indent=0))
json.dump(out,open('research/alpha_mechanism_decomposition_v1/kr_followup/s2-fixed-by-entry-year.json','w'),indent=1)
