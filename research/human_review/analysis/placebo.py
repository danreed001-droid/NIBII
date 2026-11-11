import json, random, numpy as np
from search import *
from stage1 import fast, PRn
ev=json.load(open('events.json')); sp=ev['sp']
def cagr(r,a=260):
    yrs=(date.fromisoformat(cal[-1])-date.fromisoformat(cal[a])).days/365.25
    eq=np.cumprod(1+r[a:]); return eq[-1]**(1/yrs)-1, (eq/np.maximum.accumulate(eq)-1).min()
base=cagr(PRn)[0]; mine=cagr(fast(U))
print('plan %.1f%%  your picks %.1f%% (worst drop %.1f%%)'%(base*100,mine[0]*100,mine[1]*100))
random.seed(7)
mk=[i for i in range(260,N-60) if MARK[i]]
def place(keep_haven):
    st=[None]*N
    for k,j,h in sp:
        L=j-k+1
        for _ in range(200):
            s=random.choice(mk)
            if s+L<N and all(st[q] is None for q in range(max(0,s-3),min(N,s+L+3))):
                hv=(h if h!='h' else 'f') if keep_haven else haven(s,'tltfirst')
                if hv=='f' and PX['f'][s] is None: hv='b'
                for q in range(s,s+L): st[q]=hv
                break
    return st
for keep,label in ((True,'same spells and havens, random dates'),(False,'same spell lengths, random dates, haven chosen by the simple picker')):
    xs=np.array([cagr(fast(place(keep)))[0] for _ in range(1500)])
    print(f'{label}: median {np.median(xs)*100:.1f}%, 5th-95th {np.percentile(xs,5)*100:.1f}% to {np.percentile(xs,95)*100:.1f}%, best {xs.max()*100:.1f}%; random beats the plan {np.mean(xs>base)*100:.0f}% of the time; beats your picks {np.mean(xs>mine[0])*100:.1f}%')
# shift your calls earlier / later
for sh in (-10,-5,-2,2,5,10,20):
    st=[None]*N
    for i in range(N):
        j=i-sh
        if 0<=j<N: st[i]=U[j]
    print(f'your calls shifted {sh:+d} days: {cagr(fast(st))[0]*100:.1f}%')
# always the same haven at your dates
for hv in 'bgc':
    st=[None if u is None else hv for u in U]; print('your dates, always',HN[hv],': %.1f%%'%(cagr(fast(st))[0]*100))
st=[None if u is None else haven(i,'tltfirst') for i,u in enumerate(U)]; print('your dates, haven by the simple picker: %.1f%%'%(cagr(fast(st))[0]*100))
