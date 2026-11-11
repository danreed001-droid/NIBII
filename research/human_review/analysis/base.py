import json, math, subprocess, bisect
from datetime import date
S='/tmp/claude-0/-home-user/1f2da134-018a-5788-9007-c5c63e249234/scratchpad/'; E=S+'work/engine/data/'
ph=json.loads(subprocess.run(['git','-C','/home/user/nibii','show','origin/main:data/plan_history.json'],capture_output=True,text=True).stdout)['prices']
spl=json.load(open(S+'work/side/spliced.json'))
cal=ph['dates']; N=len(cal)
def ff(a):
    o=[];v=None
    for x in a: v=x if x is not None else v; o.append(v)
    return o
dm={b[0][:10]:b[4] for b in spl['DBMF']}; f=[];last=None
for d in cal: last=dm.get(d,last); f.append(last if d>='2019-05-08' else None)
PX={'s':ff(ph['SPY']),'b':ff(ph['bonds']),'g':ff(ph['gold']),'f':f}
WK=[i+1>=N or date.fromisoformat(cal[i+1]).isocalendar()[:2]!=date.fromisoformat(cal[i]).isocalendar()[:2] for i in range(N)]
ix=lambda d: bisect.bisect_left(cal,d)
A=json.load(open(E+'fmodes_NBup_boost.json'))
PLAN=['s' if A.get(d,'boost')=='boost' else {'TLTX':'b','GLDX':'g','DBMF':'f'}.get(str(A.get(d)).replace('SIDE:',''),'c') for d in cal]
C=json.load(open(E+'curves_dump_hrd.json'))['series']
PEQ=dict(map(tuple,C['NBup_boost']['pre'])); PEQ=[PEQ.get(d) for d in cal]
HEQ=dict(map(tuple,C['MANall3p_boost']['pre'])); HEQ=[HEQ.get(d) for d in cal]
CODE={'boost':'p','PLAN':'p','TLTX':'b','GLDX':'g','DBMF':'f','CASH0':'c','WQ:0.5:DBMF':'h'}
blocks=json.load(open(S+'userrule/blocks_all.json'))
# user's override state per day: None = plan runs; else haven code
U=[None]*N; MARK=[False]*N
for st,end in blocks:
    st=sorted(st)
    for k in range(ix(st[0][0]), min(N, ix(end)+1)):
        m=CODE[[m for x,m in st if x<=cal[k]][-1]]
        MARK[k]=True; U[k]=None if m=='p' else m
YEARS=sorted({b[0][0][0][:4] for b in blocks})
HN={'b':'TLT','g':'gold','f':'DBMF','c':'cash','h':'half DBMF','s':'stocks','p':'plan'}
