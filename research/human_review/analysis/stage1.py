import itertools, json, sys, numpy as np
from multiprocessing import Pool
from search import *
PRn=np.array(PR); HRn={h:np.array(v) for h,v in HR.items()}
yrs=sorted(set(YR.tolist())); YI={y:np.where(YR==y)[0] for y in yrs}
def fast(st):
    """daily returns of plan + overlay (same timing and cost as sim)"""
    r=PRn.copy(); code=np.array([{'b':1,'g':2,'f':3,'c':4}.get(s,0) for s in st])
    pos=np.zeros(N,int); pos[2:]=code[:-2]
    for c,h in ((1,'b'),(2,'g'),(3,'f')): m=pos==c; r[m]=HRn[h][m]
    r[pos==4]=0.0
    sw=np.zeros(N,bool); sw[2:]=code[1:-1]!=code[:-2]; r=(1+r)*np.where(sw,1-0.003,1)-1
    return r
PY=np.array([np.prod(1+PRn[YI[y]])-1 for y in yrs])
def score(args):
    ex,rl,how,mh=args
    st=run(list(ex),list(rl),how,mh); r=fast(st)
    yr=np.array([np.prod(1+r[YI[y]])-1 for y in yrs])
    so=np.array([s is not None for s in st])
    tp=np.array([(so&UO&MARKA)[YI[y]].sum() for y in yrs]); fp=np.array([(so&~UO&MARKA)[YI[y]].sum() for y in yrs]); fn=np.array([(~so&UO&MARKA)[YI[y]].sum() for y in yrs])
    eq=np.cumprod(1+r); dd=(eq/np.maximum.accumulate(eq)-1).min()
    nsp=int(((so[1:])&(~so[:-1])).sum())
    return dict(ex=ex,rl=rl,how=how,mh=mh,yr=yr.round(4).tolist(),tp=tp.tolist(),fp=fp.tolist(),fn=fn.tolist(),dd=round(float(dd),4),n=nsp,out=round(float(so[260:].mean()),3))
if __name__=='__main__':
    exs=[(a,) for a in EXC]+list(itertools.combinations(EXC,2))
    rls=[(a,) for a in RLC]+list(itertools.combinations(RLC,2))
    jobs=[(e,r,'tltfirst',None) for e in exs for r in rls]
    print(len(jobs),'rules'); sys.stdout.flush()
    with Pool(4) as p: res=p.map(score,jobs,chunksize=500)
    json.dump(dict(yrs=yrs,plan=PY.round(4).tolist(),res=res),open('stage1.json','w'))
    print('done')
