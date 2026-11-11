import numpy as np, pickle, os
from sim import *
def arr(x): return np.array([np.nan if v is None else v for v in x],float)
def ret(a,n): o=np.full(N,np.nan); o[n:]=a[n:]/a[:-n]-1; return o
def rmax(a,n): return np.array([np.nanmax(a[max(0,i-n+1):i+1]) for i in range(N)])
def rmin(a,n): return np.array([np.nanmin(a[max(0,i-n+1):i+1]) for i in range(N)])
def sma(a,n):
    o=np.full(N,np.nan); c=np.nancumsum(np.nan_to_num(a))
    for i in range(n-1,N): o[i]=(c[i]-(c[i-n] if i>=n else 0))/n
    return o
def rsi(a,n=14):
    o=np.full(len(a),np.nan); ag=al=0.0
    for j in range(1,len(a)):
        if np.isnan(a[j]) or np.isnan(a[j-1]): continue
        ch=a[j]-a[j-1]; g=max(ch,0); l=max(-ch,0)
        if j<=n: ag+=g/n; al+=l/n
        else: ag=(ag*(n-1)+g)/n; al=(al*(n-1)+l)/n
        if j>=n: o[j]=100 if al==0 else 100-100/(1+ag/al)
    return o
def vol(a,n):
    r=np.diff(np.log(a),prepend=np.nan); o=np.full(N,np.nan)
    for i in range(n,N): o[i]=np.nanstd(r[i-n+1:i+1])*252**.5
    return o
def zig(x,th):
    out=[];mode=0;idx=[i for i in range(N) if not np.isnan(x[i])];hi=lo=idx[0];ext=None
    for i in idx[1:]:
        if mode==0:
            if x[i]>x[hi]: hi=i
            if x[i]<x[lo]: lo=i
            if x[i]>=x[lo]*(1+th): out.append((lo,'L',i)); mode=1; ext=i
            elif x[i]<=x[hi]*(1-th): out.append((hi,'H',i)); mode=-1; ext=i
        elif mode==1:
            if x[i]>x[ext]: ext=i
            elif x[i]<=x[ext]*(1-th): out.append((ext,'H',i)); mode=-1; ext=i
        else:
            if x[i]<x[ext]: ext=i
            elif x[i]>=x[ext]*(1+th): out.append((ext,'L',i)); mode=1; ext=i
    return out
def strip(x,k0,k1):
    P=[(i,math.log(x[i])) for i in range(k0,k1+1) if not np.isnan(x[i])]
    if len(P)<5: return None
    cr=lambda o,a,b:(a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
    lo=[];up=[]
    for q in P:
        while len(lo)>=2 and cr(lo[-2],lo[-1],q)<=0: lo.pop()
        lo.append(q)
    for q in reversed(P):
        while len(up)>=2 and cr(up[-2],up[-1],q)<=0: up.pop()
        up.append(q)
    best=None
    for h in (lo,up):
        for a,b in zip(h,h[1:]):
            s=(b[1]-a[1])/(b[0]-a[0]); c=a[1]-s*a[0]; r=[y-(c+s*x_) for x_,y in P]; w=max(r)-min(r)
            if best is None or w<best[0]: best=(w,s,c+min(r),c+max(r))
    return best
def swing(x,th,pre):
    """swing structure and channels as known at each close (pivots confirmed by then; channel fitted to the day before)"""
    piv=zig(x,th); F={k:np.full(N,np.nan) for k in ('LH','HL','belowL','aboveH','legup','trbrk','trpos','trslope','lgbrk','lgslope','sinceH','sinceL')}
    j=0; conf=[]
    for k in range(N):
        while j<len(piv) and piv[j][2]<=k: conf.append(piv[j]); j+=1
        if len(conf)<4 or np.isnan(x[k]): continue
        Hs=[p for p in conf if p[1]=='H']; Ls=[p for p in conf if p[1]=='L']
        if len(Hs)<2 or len(Ls)<2: continue
        F['LH'][k]=x[Hs[-1][0]]<x[Hs[-2][0]]; F['HL'][k]=x[Ls[-1][0]]>x[Ls[-2][0]]
        F['belowL'][k]=x[k]<x[Ls[-1][0]]; F['aboveH'][k]=x[k]>x[Hs[-1][0]]; F['legup'][k]=conf[-1][1]=='L'
        F['sinceH'][k]=x[k]/x[Hs[-1][0]]-1; F['sinceL'][k]=x[k]/x[Ls[-1][0]]-1
        ps=[p[0] for p in conf]; q=len(ps)-2
        while q>0 and (k-1)-ps[q]<20: q-=1
        tr=strip(x,ps[q],k-1)
        if tr:
            y=math.log(x[k]); lo_=tr[2]+tr[1]*k; up_=tr[3]+tr[1]*k
            F['trpos'][k]=(y-lo_)/((up_-lo_) or 1e-9); F['trslope'][k]=math.exp(tr[1]*21)-1; F['trbrk'][k]=(tr[1]>0) and (y<lo_)
        if (k-1)-ps[-1]>=8:
            lg=strip(x,ps[-1],k-1)
            if lg: y=math.log(x[k]); F['lgslope'][k]=math.exp(lg[1]*21)-1; F['lgbrk'][k]=(lg[1]<0) and (y>lg[3]+lg[1]*k)
    return {pre+k:v for k,v in F.items()}
def build():
    F={}
    s=arr(PX['s'])
    for n in (5,10,21,63,126): F[f's_r{n}']=ret(s,n)
    F['s_dd252']=s/rmax(s,252)-1; F['s_dd63']=s/rmax(s,63)-1; F['s_up63']=s/rmin(s,63)-1
    m50=sma(s,50); m200=sma(s,200); F['s_ma50']=s/m50-1; F['s_ma200']=s/m200-1; F['s_ma50slope']=ret(m50,21); F['s_gc']=(m50>m200).astype(float)
    F['s_rsi']=rsi(s); wk=[i for i in range(N) if WK[i]]; rw=rsi(s[wk]); o=np.full(N,np.nan); last=np.nan; q=0
    for i in range(N):
        while q<len(wk) and wk[q]<=i: last=rw[q]; q+=1
        o[i]=last
    F['s_rsiw']=o
    F['s_vol21']=vol(s,21); F['s_volratio']=F['s_vol21']/vol(s,126)
    F['s_share']=np.minimum(.5*F['s_r21']+.5*F['s_r63'],F['s_r21']); F['s_mkt']=F['s_r21']
    r1=np.diff(s,prepend=np.nan); F['s_down10']=np.array([np.nansum(r1[max(0,i-9):i+1]<0) for i in range(N)],float)
    F.update(swing(s,0.05,'s5_')); F.update(swing(s,0.03,'s3_')); F.update(swing(s,0.08,'s8_'))
    for t in 'bgf':
        a=arr(PX[t])
        for n in (21,63,126): F[f'{t}_r{n}']=ret(a,n)
        F[f'{t}_share']=np.minimum(.5*F[f'{t}_r21']+.5*F[f'{t}_r63'],F[f'{t}_r21']); F[f'{t}_ma50']=a/sma(a,50)-1; F[f'{t}_ma200']=a/sma(a,200)-1
        F[f'{t}_rs21']=F[f'{t}_r21']-F['s_r21']; F[f'{t}_rs63']=F[f'{t}_r63']-F['s_r63']; F[f'{t}_dd252']=a/rmax(a,252)-1; F[f'{t}_rsi']=rsi(a)
        if t!='f': F.update({k:v for k,v in swing(a,0.04,f'{t}4_').items() if k.split('_')[1] in ('trslope','legup','LH','HL','trbrk','lgbrk','aboveH','belowL')})
    F['hav_up']=sum((np.nan_to_num(F[f'{t}_r21'])>0).astype(float) for t in 'bgf')
    F['hav_best21']=np.nanmax(np.vstack([np.nan_to_num(F[f'{t}_r21'],nan=-9) for t in 'bgf']),axis=0)
    F['hav_rs21']=F['hav_best21']-F['s_r21']
    p=arr(PEQ); F['p_in']=np.array([1.0 if x=='s' else 0.0 for x in PLAN]); F['p_r21']=ret(p,21); F['p_r5']=ret(p,5); F['p_dd']=p/np.maximum.accumulate(p)-1; F['p_ma50']=p/sma(p,50)-1
    return F
if __name__=='__main__':
    F=build(); pickle.dump(F,open('F.pkl','wb')); print(len(F),'features')
