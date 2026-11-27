import json, statistics
from fightsim import *
def avgwin(L,k,n=300):
    ws=[]
    for cls,names in SUBS.items():
        for nm in names:
            ws.append(run(lambda: [sub(cls,nm,L)]+[baseline(L) for _ in range(3)],L,k,n=n,seed=3)[0])
    return statistics.mean(ws)
out={"res":{},"k":{},"hd":{}}
for L in LV:
    lo,hi=0.5,4.0
    for _ in range(12):
        k=(lo+hi)/2
        if avgwin(L,k)>0.55: lo=k
        else: hi=k
    k=(lo+hi)/2; out["k"][L]=k
    for cls,names in SUBS.items():
        for nm in names:
            w,r,hd=run(lambda: [sub(cls,nm,L)]+[baseline(L) for _ in range(3)],L,k,n=2000,seed=11)
            out["res"].setdefault(nm,{})[L]=round(w,3); out["hd"].setdefault(nm,{})[L]=round(hd)
json.dump(out,open("simres2.json","w"),indent=1,ensure_ascii=False)
print({L:round(k,2) for L,k in out["k"].items()})
for cls,names in SUBS.items():
    print("##",cls, "class avg %.0f%%"%(100*statistics.mean(statistics.mean(out["res"][n].values()) for n in names)))
    for nm in names:
        r=out["res"][nm]; print(f"  {nm:16s}","  ".join(f"L{L}:{r[L]*100:4.0f}%" for L in LV),f"  avg {statistics.mean(r.values())*100:4.0f}%")
