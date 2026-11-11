import json, numpy as np, sys
from search import *
from stage1 import fast, PRn, YI
D=json.load(open(sys.argv[1] if len(sys.argv)>1 else 'stage1.json')); yrs=D['yrs']; plan=np.array(D['plan']); R=D['res']
Y=np.array([r['yr'] for r in R]); TP=np.array([r['tp'] for r in R]); FP=np.array([r['fp'] for r in R]); FN=np.array([r['fn'] for r in R])
mine=np.array([np.prod(1+fast(U)[YI[y]])-1 for y in yrs])
yy=np.array(yrs)
folds={'all':yy>=2001,'even':(yy%2==0)&(yy>=2001),'odd':(yy%2==1)&(yy>=2001),'early':(yy>=2001)&(yy<=2012),'late':yy>=2013}
def g(v,m): return np.exp(np.log1p(v[...,m]).mean(axis=-1))-1
def f1(m):
    tp=TP[:,m].sum(1); fp=FP[:,m].sum(1); fn=FN[:,m].sum(1); p=tp/np.maximum(1,tp+fp); r=tp/np.maximum(1,tp+fn); return 2*p*r/np.maximum(1e-9,p+r),p,r
G={k:g(Y,m) for k,m in folds.items()}; PG={k:g(plan,m) for k,m in folds.items()}; MG={k:g(mine,m) for k,m in folds.items()}; F1={k:f1(m) for k,m in folds.items()}
print('per-year average return by group of years:'); 
for k in folds: print(f'  {k:6s} plan {PG[k]*100:5.1f}%  your picks {MG[k]*100:5.1f}%')
n=len(R); print(f'\n{n} rules. Beat the plan over all years: {(G["all"]>PG["all"]).sum()} ({(G["all"]>PG["all"]).mean()*100:.2f}%). Beat it in BOTH even and odd years: {((G["even"]>PG["even"])&(G["odd"]>PG["odd"])).sum()}. In BOTH early and late: {((G["early"]>PG["early"])&(G["late"]>PG["late"])).sum()}')
print('link between matching your out-days (F1) and return, all years: corr %.2f'%np.corrcoef(F1['all'][0],G['all'])[0,1])
def show(i,tag=''):
    r=R[i]; print(f"   {tag} OUT when {' & '.join(r['ex'])} | BACK when {' or '.join(r['rl'])} | spells {r['n']}, out {r['out']*100:.0f}% of days, worst drop {r['dd']*100:.0f}%")
    print('      '+'  '.join(f"{k}: F1 {F1[k][0][i]:.2f} ret {G[k][i]*100:.1f}% (plan {PG[k]*100:.1f})" for k in folds))
print('\nA. Best match to your out-days over all years:'); 
for i in np.argsort(-F1['all'][0])[:3]: show(i)
for tr,te in (('even','odd'),('odd','even'),('early','late'),('late','early')):
    print(f'\nB. Fitted to your picks on {tr} years, scored on {te} years:')
    top=np.argsort(-F1[tr][0])[:20]; show(top[0],'best:')
    print(f'      top 20 by match on {tr}: on {te} they average F1 {F1[te][0][top].mean():.2f}, return {G[te][top].mean()*100:.1f}% vs plan {PG[te]*100:.1f}% (your picks {MG[te]*100:.1f}%); {int((G[te][top]>PG[te]).sum())} of 20 beat the plan there')
for tr,te in (('even','odd'),('odd','even'),('early','late'),('late','early')):
    top=np.argsort(-G[tr])[:20]
    print(f'\nC. Chosen for best RETURN on {tr} years, scored on {te}: train {G[tr][top].mean()*100:.1f}% (plan {PG[tr]*100:.1f}), test {G[te][top].mean()*100:.1f}% vs plan {PG[te]*100:.1f}%; {int((G[te][top]>PG[te]).sum())} of 20 beat the plan on {te}')
    show(top[0],'best:')
both=np.where((G['even']>PG['even'])&(G['odd']>PG['odd'])&(G['early']>PG['early'])&(G['late']>PG['late']))[0]
print(f'\nD. Rules ahead of the plan in all four groups of years: {len(both)}')
for i in both[np.argsort(-G['all'][both])][:8]: show(i)
json.dump(dict(best_f1=[int(i) for i in np.argsort(-F1['all'][0])[:50]],robust=[int(i) for i in both[np.argsort(-G['all'][both])][:200]]),open('picks_'+(sys.argv[1] if len(sys.argv)>1 else 'stage1.json'),'w'))
