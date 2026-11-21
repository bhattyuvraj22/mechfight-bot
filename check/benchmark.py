"""Direct policy checks and timing on recorded / synthetic observations.

This measures computation and decision invariants, NOT playing strength.
Synthetic scenes do not reproduce visibility, enemy AI, or server physics.
"""
import copy
import gzip
import json
import math
import random
import resource
import sys
import time
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from bot import Bot
from geometry import distance


def summarize(times):
    s=sorted(times)
    return {"decisions":len(s),"p50_ms":round(s[len(s)//2],3),
            "p99_ms":round(s[min(len(s)-1,int(len(s)*0.99))],3),
            "max_ms":round(s[-1],3),"over_50ms":sum(t>50 for t in s)}


def run(bot,observations):
    times=[]
    modes=Counter()
    for obs in observations:
        t=time.perf_counter()
        action=bot.act(obs)
        times.append((time.perf_counter()-t)*1000)
        modes[bot.mode]+=1
        assert action['tick']==obs['tick']
        assert math.hypot(*action['move'])<=1.000001
        assert all(math.isfinite(v) for v in action['aim']+action['move'])
        json.dumps(action,allow_nan=False)
    return dict(summarize(times),modes=dict(modes))


def main():
    with gzip.open(ROOT/'check/stream.jsonl.gz','rt') as f:
        rows=[json.loads(line) for line in f]
    hello=rows[0]
    hello['map']['dir']=str(ROOT/'arena')
    observations=[r for r in rows if r['type']=='obs']
    report={'recorded':run(Bot(hello),observations)}
    b=Bot(hello)
    rng=random.Random(42)
    scenes=[]
    # Crowd every synthetic scene with 15 actors, 48 shots and mixed weapons,
    # varying body size and map locations. All positions are on clear ground.
    clear=[]
    bounds=b.world.bounds
    while len(clear)<96:
        x=rng.uniform(bounds['minX']+12,bounds['maxX']-12)
        y=rng.uniform(bounds['minY']+12,bounds['maxY']-12)
        if b.world.ground_free(x,y,5,18):
            clear.append([x,y,b.world.height(x,y)])
    for i in range(240):
        o=copy.deepcopy(observations[0])
        o['tick']=i*2
        o['t']=i*0.1
        me=o['self']
        me['pos']=clear[(i//8)%len(clear)][:]
        me['hp']=420 if i%3 else 1400
        cubes=(i//40)%4
        me['cubes']=cubes
        for key in ('radius','height','eye_height','muzzle_height'):
            me['stats'][key]*=1+0.05*cubes
        near=sorted(clear,key=lambda p:distance(me['pos'],p))[1:16]
        o['mechs']=[{'id':j if j<3 else j+1,'kind':'mech','pos':p[:],
                     'vel':[rng.uniform(-12,12),rng.uniform(-12,12),0],
                     'hp':1000,'max_hp':1400,'aim':[0,0],
                     'weapons':['gun','laser'],'charging':True,'cubes':2}
                    for j,p in enumerate(near)]
        o['projectiles']=[{'id':100+j,'kind':'mortar' if j%4==0 else 'gun',
                           'pos':[me['pos'][0]+rng.uniform(-30,30),me['pos'][1]+rng.uniform(-30,30),me['pos'][2]+7],
                           'vel':[rng.uniform(-200,200),rng.uniform(-200,200),rng.uniform(-10,10)]}
                          for j in range(48)]
        if i%2:
            me['weapons'][1]={'kind':'laser','cooldown':0,'charge':0.75,
                              'stats':hello['config']['weapons']['laser'].copy()}
        else:
            me['weapons'][1]={'kind':'lightning','cooldown':0,
                              'stats':hello['config']['weapons']['lightning'].copy()}
        scenes.append(o)
    report['synthetic_stress']=run(b,scenes)
    rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    report['peak_rss_mib']=round(rss/(1024*1024 if sys.platform=='darwin' else 1024),2)
    report['notes']='Local direct calls; not Docker, not match simulation, not a practice score.'
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
