import itertools, json, sys, numpy as np
from multiprocessing import Pool
import search
from search import *
F=search.F
add={'bear10':F['s_dd252']<-.10,'bear15':F['s_dd252']<-.15,'under200d':F['s_ma200']<0,'deathx':F['s_gc']==0,'LH8':F['s8_LH']==1,
 'plan_in':F['p_in']==1,'plan<50d':F['p_ma50']<0,'plandd>5%':F['p_dd']<-.05,'plandd>10%':F['p_dd']<-.10,'plan21<0':F['p_r21']<0,'plan5<-3%':F['p_r5']<-.03,
 'tlt>200d':F['b_ma200']>0,'tltchanup':F['b4_trslope']>0,'tlt21>0':F['b_r21']>0,'gold21>0':F['g_r21']>0,'vol_up':F['s_volratio']>1.2}
for k,v in add.items(): search.EXC[k]=np.nan_to_num(v.astype(float))>0
search.RLC['plan>50d']=np.nan_to_num((F['p_ma50']>0).astype(float))>0; search.RLC['tlt21<0']=np.nan_to_num((F['b_r21']<0).astype(float))>0
import stage1
from stage1 import score
if __name__=='__main__':
    E2=list(add)+['chan5<0','chan3<0','LH3','rsi<40','r5<-2%','offhigh>4%','tltup','hav>spy2%']
    exs=list(itertools.combinations(E2,2))+list(itertools.combinations(E2,3))
    R2=['chan3>.5','r5>0','legup3','lgbrk3','rsi>50','plan5>1%','over50d','r10>0','above3','plan>50d','tlt21<0','chan3>.75']
    rls=[(a,) for a in R2]+list(itertools.combinations(R2,2))
    jobs=[(e,r,'tltfirst',mh) for e in exs for r in rls for mh in (None,15)]
    print(len(jobs),'rules'); sys.stdout.flush()
    with Pool(4) as p: res=p.map(score,jobs,chunksize=500)
    json.dump(dict(yrs=stage1.yrs,plan=stage1.PY.round(4).tolist(),res=res),open('stage2.json','w'))
    print('done')
