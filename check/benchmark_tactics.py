#!/usr/bin/env python3
"""Exercise active evasions missed by the crowd benchmark. Not a match scorer."""
import json
import math
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(ROOT/'check')]
from test_v04 import make_bot
from test_bot import enemy, prism, laser
from benchmark import summarize


def main():
    report={}
    for scenario in ('juke','juke_charging','laser_cover'):
        b,o=make_bot([prism(6,3,10,40)] if scenario=='laser_cover' else [])
        foe=enemy(60,0,800)
        if scenario=='laser_cover':
            foe.update(weapons=['gun','laser'],charging=True)
        o['mechs']=[foe]
        if scenario=='juke_charging':
            o['self']['weapons'][1]=laser(.5)
        o['projectiles']=[{'id':j,'kind':'gun','pos':[60,j*.2-6,5],'vel':[-252,0,0]} for j in range(64)]
        times=[];active=0
        for i in range(120):
            o['t']=20+i*.1;o['tick']=400+i*2
            b.tactics.lead_votes=20;b.tactics.headon_votes=0
            start=time.perf_counter();a=b.act(o);times.append((time.perf_counter()-start)*1000)
            active+=int(b.dodging if scenario=='laser_cover' else b.juking)
            assert a['tick']==o['tick'] and math.hypot(*a['move'])<=1.000001
        report[scenario]=dict(summarize(times),active_ticks=active)
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
