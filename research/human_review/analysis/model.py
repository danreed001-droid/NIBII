import pickle, numpy as np, json
from search import *
from stage1 import fast, PRn, YI
F=pickle.load(open('F.pkl','rb'))
names=[k for k in F]; X=np.vstack([F[k] for k in names]).T.astype(float)
isn=np.isnan(X); X=np.where(isn,0,X)
# robust scale using days from 2001, clip
m0=np.arange(N)>=260
mu=np.nanmedian(np.where(isn,np.nan,X)[m0],axis=0); sd=np.nanstd(np.where(isn,np.nan,X)[m0],axis=0)+1e-9
X=np.clip((X-mu)/sd,-4,4); X[isn]=0
X=np.hstack([X,isn[:,[names.index('f_r21')]].astype(float),np.ones((N,1))]); names2=names+['no_dbmf','bias']
def fit(Xt,y,l2=3.0,it=600,lr=0.3):
    w=np.zeros(Xt.shape[1]); pw=(1-y.mean())/max(1e-9,y.mean()); sw=np.where(y==1,pw,1.0); sw/=sw.mean()
    for _ in range(it):
        p=1/(1+np.exp(-Xt@w)); g=Xt.T@((p-y)*sw)/len(y)+l2*w/len(y); g[-1]-=l2*w[-1]/len(y); w-=lr*g
    return w
def auc(s,y):
    r=s.argsort().argsort()+1.0; n1=y.sum(); n0=len(y)-n1
    return (r[y==1].sum()-n1*(n1+1)/2)/(n1*n0)
yrs=sorted(set(YR.tolist()))
def oof(y,mask,folds=5,l2=3.0):
    """out-of-fold scores: each year is scored by a model fitted on the other years only"""
    s=np.full(N,np.nan); ws=[]
    for f in range(folds):
        te=np.isin(YR,[yy for i,yy in enumerate(yrs) if i%folds==f]); tr=mask&~te
        w=fit(X[tr],y[tr],l2); s[te]=X[te]@w; ws.append(w)
    return s,np.mean(ws,axis=0)
MK=MARKA&m0
uo=UO.astype(float)
# target 1: your out-days
s1,w1=oof(uo,MK)
print('T1 your out-days: out-of-sample AUC %.2f (0.5 = no better than chance)'%auc(s1[MK],uo[MK]))
top=np.argsort(-np.abs(w1[:-2]))[:12]; print('   heaviest readings:',[(names2[i],round(float(w1[i]),2)) for i in top])
# target 2: you leave within the next 5 sessions
ev=json.load(open('events.json')); y2=np.zeros(N)
for e in ev['exits']: y2[max(0,e-5):e+1]=1
m2=MK&~(UO&(y2==0))
s2,w2=oof(y2,m2); print('T2 you leave within 5 days: out-of-sample AUC %.2f'%auc(s2[m2],y2[m2]))
# target 3: does the plan lose to TLT over the next 10 sessions by 3+ points (what an exit needs to be right about)
p=np.array(PEQ,float); b=np.array([np.nan if v is None else v for v in PX['b']],float)
fw=np.full(N,np.nan); fw[:-11]=(p[11:]/p[1:-10]-1)-(b[11:]/b[1:-10]-1)
y3=(fw<-.03).astype(float); m3=m0&~np.isnan(fw)
s3,w3=oof(y3,m3); print('T3 plan loses to TLT by 3+ points over the next 10 days (%.0f%% of days): out-of-sample AUC %.2f'%(y3[m3].mean()*100,auc(s3[m3],y3[m3])))
top=np.argsort(-np.abs(w3[:-2]))[:10]; print('   heaviest readings:',[(names2[i],round(float(w3[i]),2)) for i in top])
y4=(np.where(np.isnan(fw),0,(p*0)) ); 
fp_=np.full(N,np.nan); fp_[:-11]=p[11:]/p[1:-10]-1
y4=(fp_<-.05).astype(float); m4=m0&~np.isnan(fp_)
s4,w4=oof(y4,m4); print('T4 plan falls 5+%% over the next 10 days (%.0f%% of days): out-of-sample AUC %.2f'%(y4[m4].mean()*100,auc(s4[m4],y4[m4])))
pickle.dump(dict(s1=s1,s2=s2,s3=s3,s4=s4),open('scores.pkl','wb'))
# turn each out-of-sample score into an overlay and test it
def overlay(s,q_in,q_out,how='tltfirst',minhold=3):
    hi=np.nanquantile(s[m0],q_in); lo=np.nanquantile(s[m0],q_out); st=[None]*N; cur=None; since=0
    for k in range(260,N):
        if np.isnan(s[k]): st[k]=cur; continue
        if cur is None:
            if s[k]>=hi: cur=haven(k,how); since=0
        else:
            since+=1
            if since>=minhold and s[k]<=lo: cur=None
            elif since%5==0 and cur!='c' and F[f'{cur}_share'][k]<0: cur=haven(k,how)
        st[k]=cur
    return st
def cg(r,a=260):
    yrs_=(date.fromisoformat(cal[-1])-date.fromisoformat(cal[a])).days/365.25; eq=np.cumprod(1+r[a:]); return eq[-1]**(1/yrs_)-1,(eq/np.maximum.accumulate(eq)-1).min()
print('\nplan %.1f%%, your picks %.1f%%'%(cg(PRn)[0]*100,cg(fast(U))[0]*100))
for nm,s in (('T1 your out-days',s1),('T2 about to leave',s2),('T3 plan loses to TLT',s3),('T4 plan about to fall',s4)):
    for qi,qo in ((.75,.5),(.9,.6),(.95,.7),(.98,.8),(.99,.9)):
        st=overlay(s,qi,qo); c,d=cg(fast(st)); so=np.array([x is not None for x in st])
        print(f'  {nm:22s} out above the top {100-qi*100:.0f}% score, back under the {qo*100:.0f}% mark: {c*100:5.1f}%  worst drop {d*100:.0f}%  out {so[260:].mean()*100:.0f}% of days')
