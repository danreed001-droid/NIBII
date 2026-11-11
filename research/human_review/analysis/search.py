import pickle, numpy as np, json, itertools, random
from sim import *
F=pickle.load(open('F.pkl','rb'))
EXC={ # exit conditions (SPY weak / havens stronger)
 'rsi<50':F['s_rsi']<50,'rsi<45':F['s_rsi']<45,'rsi<40':F['s_rsi']<40,
 'r5<0':F['s_r5']<0,'r5<-1%':F['s_r5']<-.01,'r5<-2%':F['s_r5']<-.02,
 'chan3<.4':F['s3_trpos']<.4,'chan3<.25':F['s3_trpos']<.25,'chan3<0':F['s3_trpos']<0,'chan5<.4':F['s5_trpos']<.4,'chan5<0':F['s5_trpos']<0,
 'offhigh>2%':F['s3_sinceH']<-.02,'offhigh>3%':F['s3_sinceH']<-.03,'offhigh>4%':F['s3_sinceH']<-.04,
 'under50d':F['s_ma50']<0,'near50d':F['s_ma50']<.01,'r21<0':F['s_r21']<0,'share<0':F['s_share']<0,
 'dd63>3%':F['s_dd63']<-.03,'dd63>5%':F['s_dd63']<-.05,'hav>spy':F['hav_rs21']>0,'hav>spy2%':F['hav_rs21']>.02,
 'notabove':F['s3_aboveH']==0,'plan5<0':F['p_r5']<0,'LH3':F['s3_LH']==1,'legdn3':F['s3_legup']==0,'tltup':F['b_ma50']>0,
 'dd252<8%':F['s_dd252']>-.08,'dd252<12%':F['s_dd252']>-.12}
RLC={ # release conditions (SPY turning back up)
 'chan3>.5':F['s3_trpos']>.5,'chan3>.6':F['s3_trpos']>.6,'chan3>.75':F['s3_trpos']>.75,'r5>0':F['s_r5']>0,'r5>1%':F['s_r5']>.01,'r5>2%':F['s_r5']>.02,
 'legup3':F['s3_legup']==1,'lgbrk3':F['s3_lgbrk']==1,'lgbrk5':F['s5_lgbrk']==1,'rsi>45':F['s_rsi']>45,'rsi>50':F['s_rsi']>50,'rsi>55':F['s_rsi']>55,
 'plan5>1%':F['p_r5']>.01,'plan5>3%':F['p_r5']>.03,'over50d':F['s_ma50']>0,'r10>0':F['s_r10']>0,'above3':F['s3_aboveH']==1}
EXC={k:np.nan_to_num(v.astype(float))>0 for k,v in EXC.items()}; RLC={k:np.nan_to_num(v.astype(float))>0 for k,v in RLC.items()}
def haven(k,how):
    c={t:(F[f'{t}_share'][k],F[f'{t}_r21'][k],F[f'{t}_ma50'][k]) for t in 'bgf' if not np.isnan(F[f'{t}_r21'][k])}
    if how=='tlt': return 'b'
    if how=='tltfirst' and 'b' in c and c['b'][2]>0: return 'b'
    c2={t:v[1] for t,v in c.items() if v[1]>0}
    return max(c2,key=c2.get) if c2 else 'c'
def run(ex,rl,how='tltfirst',maxhold=None,minhold=3,cool=0,relmode='any',i0=260):
    """state per day: None = plan, else haven. Out when ALL exit conds hold; back when ANY (or ALL) release cond holds or after maxhold."""
    st=[None]*N; cur=None; since=0; lastback=-999
    e=np.ones(N,bool)
    for c in ex: e&=EXC[c]
    if relmode=='any':
        r=np.zeros(N,bool)
        for c in rl: r|=RLC[c]
    else:
        r=np.ones(N,bool)
        for c in rl: r&=RLC[c]
    for k in range(i0,N):
        if cur is None:
            if e[k] and k-lastback>=cool: cur=haven(k,how); since=0
        else:
            since+=1
            if (since>=minhold and r[k]) or (maxhold and since>=maxhold): cur=None; lastback=k
            elif since%5==0 and cur!='c' and F[f'{cur}_share'][k]<0:   # held haven's flow turned out: re-pick weekly
                cur=haven(k,how)
        st[k]=cur
    return st
MARKA=np.array(MARK); UO=np.array([u is not None for u in U])
def agree(st,mask=None):
    m=MARKA if mask is None else (MARKA&mask); so=np.array([s is not None for s in st])
    tp=(so&UO&m).sum(); fp=(so&~UO&m).sum(); fn=(~so&UO&m).sum()
    p=tp/max(1,tp+fp); r=tp/max(1,tp+fn); return 2*p*r/max(1e-9,p+r),p,r
YR=np.array([int(d[:4]) for d in cal])
