import pickle, numpy as np, json
from sim import *
F=pickle.load(open('F.pkl','rb'))
eps=[];k=0
while k<N:
    if U[k] is not None:
        j=k
        while j+1<N and U[j+1]==U[k] and cal[j+1][:4]==cal[k][:4]: j+=1
        eps.append((k,j,U[k])); k=j+1
    else: k+=1
# merge back-to-back episodes (a haven swap) into one out-spell for exit / release analysis
sp=[]
for k,j,h in eps:
    if sp and sp[-1][1]+1==k: sp[-1]=(sp[-1][0],j,sp[-1][2])
    else: sp.append((k,j,h))
exits=[k for k,j,h in sp]; rel=[j+1 for k,j,h in sp if j+1<N and cal[j+1][:4]==cal[j][:4]]
outday=np.array([u is not None for u in U]); mark=np.array(MARK); wk=np.array(WK)
neg_exit=np.where(mark&wk&~outday)[0]; neg_exit=np.array([i for i in neg_exit if not any(0<=e-i<=5 for e in exits)])
neg_rel=np.where(mark&wk&outday)[0]
def auc(pos,neg):
    pos=pos[~np.isnan(pos)]; neg=neg[~np.isnan(neg)]
    if len(pos)<5 or len(neg)<5: return np.nan
    allv=np.concatenate([pos,neg]); r=allv.argsort().argsort()+1.0
    # ties: average ranks
    _,inv,cnt=np.unique(allv,return_inverse=True,return_counts=True); s=np.zeros(len(cnt)); np.add.at(s,inv,r); r=(s/cnt)[inv]
    return (r[:len(pos)].sum()-len(pos)*(len(pos)+1)/2)/(len(pos)*len(neg))
def table(ev,neg,title,top=24):
    rows=[]
    for f,v in F.items():
        a=auc(v[ev],v[neg])
        if np.isnan(a): continue
        rows.append((abs(a-.5),a,f,np.nanmedian(v[ev]),np.nanmedian(v[neg])))
    rows.sort(reverse=True)
    print(f'\n== {title}: {len(ev)} events vs {len(neg)} ordinary weeks. AUC 0.5 = no difference; median at your calls vs ordinary')
    for _,a,f,me,mn in rows[:top]: print(f'  {f:14s} AUC {a:.2f}   yours {me:+.3f}   ordinary {mn:+.3f}')
    return rows
print(len(sp),'out-spells;',len(rel),'releases before year end')
re_=table(np.array(exits),neg_exit,'EXITS (leaving the plan)')
rr_=table(np.array(rel),neg_rel,'RELEASES (back to the plan) vs weeks you stayed out')
# haven choice
print('\n== HAVEN CHOICE at each exit')
import collections
for k,j,h in eps:
    pass
ok=collections.Counter(); tot=0
def pick(k,how):
    c={t:(F[f'{t}_share'][k],F[f'{t}_r21'][k],F[f'{t}_ma50'][k],F[f'{t}_r63'][k]) for t in 'bgf' if not np.isnan(F[f'{t}_r21'][k])}
    if how=='share': c2={t:v[0] for t,v in c.items() if v[0]>0}
    elif how=='r21': c2={t:v[1] for t,v in c.items() if v[1]>0}
    elif how=='r63': c2={t:v[3] for t,v in c.items() if v[3]>0}
    elif how=='tltfirst':
        if 'b' in c and c['b'][2]>0: return 'b'
        c2={t:v[1] for t,v in c.items() if v[1]>0}
    elif how=='tltalways': return 'b'
    return max(c2,key=c2.get) if c2 else 'c'
for how in ('share','r21','r63','tltfirst','tltalways'):
    n=sum(pick(k,how)==(h if h!='h' else 'f') for k,j,h in eps); print(f'  picker {how:10s} matches your haven in {n} of {len(eps)}')
json.dump(dict(exits=[int(x) for x in exits],rel=[int(x) for x in rel],sp=[(int(a),int(b),c) for a,b,c in sp]),open('events.json','w'))
