from base import *
PR=[0.0]+[PEQ[i]/PEQ[i-1]-1 for i in range(1,N)]
HR={h:[0.0]+[(PX[h][i]/PX[h][i-1]-1) if PX[h][i-1] and PX[h][i] else 0.0 for i in range(1,N)] for h in 'bgf'}
def sim(state, cost=0.0015, i0=None, i1=None):
    """state[k]: None (plan runs) or haven code, decided at close k, traded at close k+1. Returns daily equity list (base 1) over cal."""
    eq=[1.0]*N; v=1.0
    for t in range(1,N):
        s=state[t-2] if t>=2 else None
        if s is None: r=PR[t]
        elif s=='c': r=0.0
        elif s=='h': r=0.5*HR['f'][t]+0.5*PR[t]
        else: r=HR[s][t]
        v*=1+r
        if t>=2 and state[t-1]!=state[t-2]: v*=1-2*cost   # out of one book, into the other
        eq[t]=v
    return eq
def stats(eq, a=0, b=None):
    b=N-1 if b is None else b
    yrs=(date.fromisoformat(cal[b])-date.fromisoformat(cal[a])).days/365.25
    cagr=(eq[b]/eq[a])**(1/yrs)-1
    pk=eq[a]; dd=0
    for i in range(a,b+1): pk=max(pk,eq[i]); dd=min(dd,eq[i]/pk-1)
    r=[eq[i]/eq[i-1]-1 for i in range(a+1,b+1)]; m=sum(r)/len(r); sd=(sum((x-m)**2 for x in r)/(len(r)-1))**.5
    return cagr, dd, (m-0.02/252)/sd*252**.5
def by_year(eq):
    out={}
    for y in range(2000,2027):
        ii=[i for i in range(N) if cal[i][:4]==str(y)]
        a=ii[0]-1 if ii[0]>0 else ii[0]; out[str(y)]=eq[ii[-1]]/eq[a]-1
    return out
