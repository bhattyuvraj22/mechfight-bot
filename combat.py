"""Projectile leading, shared-torso aim, and weapon trigger scheduling.

Experiment E1: fixed 60% lead for non-charging mechs.
The original adaptive-learning bookkeeping below is retained for an isolated
comparison; pick_lead bypasses its sampler.

Original v0.4 rationale: adaptive lead. House bots juke (new heading every ~0.7-1.0 s), so full
linear lead over a 0.3-0.6 s flight often misses. Each gun shot is tagged with
the lead fraction used; `hit` events are credited back to it, and Thompson
sampling picks the fraction that is actually landing in this match. A target
that is charging a laser moves straight at half speed: always lead it fully.
"""
import math
import random
from collections import deque
from geometry import clamp, distance

LEAD_OPTIONS=(1.0,0.6,0.3)


def angle_diff(a,b):
    return (a-b+math.pi)%(2*math.pi)-math.pi


def intercept(origin,target,velocity,speed):
    r=[target[i]-origin[i] for i in range(3)]
    a=sum(v*v for v in velocity)-speed*speed
    b=2*sum(r[i]*velocity[i] for i in range(3))
    c=sum(v*v for v in r)
    if abs(a)<1e-9:
        roots=[-c/b] if abs(b)>1e-9 else []
    else:
        disc=b*b-4*a*c
        roots=[] if disc<0 else [(-b-math.sqrt(disc))/(2*a),(-b+math.sqrt(disc))/(2*a)]
    positive=[t for t in roots if t>0]
    if not positive:
        return None
    t=min(positive)
    return [target[i]+velocity[i]*t for i in range(3)]


def center(actor):
    scale=1+0.05*actor.get('cubes',0)
    height=3.5 if actor.get('kind')=='npc' else 9*scale
    return [actor['pos'][0],actor['pos'][1],actor['pos'][2]+height/2]


def aim_at(origin,target):
    return [math.atan2(target[1]-origin[1],target[0]-origin[0]),
            math.atan2(target[2]-origin[2],distance(origin,target))]


def aligned(actual,desired,radius,dist):
    tolerance=max(0.008,math.atan2(radius*0.8,max(1,dist)))
    return abs(angle_diff(actual[0],desired[0]))<=tolerance and abs(actual[1]-desired[1])<=tolerance


class Combat:
    def __init__(self,world,seed=0):
        self.world=world
        self.rng=random.Random((seed or 0)^0x1EAD)
        # Beta priors per lead option: [hits, misses]. Slight prior for 0.6.
        self.lead_stats=[[1.0,2.0],[1.3,2.0],[1.0,2.0]]
        self.lead_idx=1
        self.lead_until=-1.0
        self.pending=deque()   # (arrival_t, target_id, option)

    def observe(self,obs):
        """Credit gun hits to the lead option that fired them; expire misses."""
        now=obs['t']
        for e in obs.get('events',[]) or []:
            if e.get('type')!='hit' or e.get('weapon')!='gun':
                continue
            best=None
            for i,(arr,tid,opt) in enumerate(self.pending):
                if tid==e.get('target') and abs(arr-now)<0.4:
                    if best is None or abs(arr-now)<abs(self.pending[best][0]-now):
                        best=i
            if best is not None:
                _,_,opt=self.pending[best]
                del self.pending[best]
                self.lead_stats[opt][0]+=1
        while self.pending and self.pending[0][0]<now-0.4:
            _,_,opt=self.pending.popleft()
            self.lead_stats[opt][1]+=1
        # Forget slowly so the choice follows the current opponent.
        for st in self.lead_stats:
            if st[0]+st[1]>60:
                st[0]*=0.97; st[1]*=0.97

    def pick_lead(self,now):
        # Experiment E1: hold 60% lead for ordinary moving mechs. Charging
        # mechs and NPCs retain the existing full-intercept calculation.
        return 1  # LEAD_OPTIONS[1] == 0.6

    def command(self,obs,target,allow_fire,default_yaw,reserve=28,mobile=False):
        me=obs['self']
        stats=me['stats']
        origin=[*me['pos'][:2],me['pos'][2]+stats.get('muzzle_height',7)]
        out={'aim':[default_yaw,0.0],'fire':[False,False]}
        weapons=me['weapons']
        if target is None or not allow_fire:
            if target is not None:
                out['aim']=aim_at(origin,center(target))
            # Releasing an already charged laser can still cause one final shot.
            # There is no protocol action to cancel it; retain the threat-facing
            # aim for armor protection and don't initiate another charge.
            return out
        pt=center(target) if target.get('kind') in ('mech','npc') else [*target['pos'][:2],target['pos'][2]+1.0]
        vel=target.get('vel',[0,0,0])
        dist=math.dist(origin,pt)
        tr=1.8 if target.get('kind')=='npc' else 2.5*(1+0.05*target.get('cubes',0))
        gun_point=None
        laser_idx=next((i for i,w in enumerate(weapons) if w and w['kind']=='laser'),None)
        gun_idx=next((i for i,w in enumerate(weapons) if w and w['kind']=='gun'),None)
        laser=weapons[laser_idx] if laser_idx is not None else None
        # Returning fire while escaping must not initiate a movement-slowing
        # charge. An existing charge is released promptly to regain mobility.
        laser_active=laser is not None and (laser.get('charge',0)>0 or
                     (not mobile and laser['cooldown']<=0 and 50<dist<laser['stats']['range']))
        lead_opt=None
        if gun_idx is not None:
            gun=weapons[gun_idx]
            if target.get('kind')=='mech' and not target.get('charging'):
                lead_opt=self.pick_lead(obs['t'])
                f=LEAD_OPTIONS[lead_opt]
            else:
                f=1.0
            gun_point=intercept(origin,pt,[vel[0]*f,vel[1]*f,vel[2]*f],gun['stats']['speed'])
        # Keep leading the gun during most of the charge. Only transfer the
        # shared torso to hitscan aim just before releasing the laser.
        laser_aim=(laser_active and laser.get('charge',0)>0 and
                   (mobile or laser.get('charge',0)>=laser['stats']['charge']-0.1))
        point=pt if laser_aim or gun_point is None else gun_point
        desired=aim_at(origin,point)
        out['aim']=[desired[0],clamp(desired[1],stats.get('min_pitch',-0.7),stats.get('max_pitch',1.3))]
        for i,w in enumerate(weapons):
            if not w:
                continue
            ws=w['stats']
            if w['kind']=='gun':
                if gun_point is not None and w.get('reload',0)<=0 and w.get('ammo',0)>0:
                    # A trigger is held for two sim ticks. Require both current and
                    # commanded aim to fit the target, avoiding a sweep into a wall.
                    ga=aim_at(origin,gun_point)
                    out['fire'][i]=(math.dist(origin,gun_point)<=ws['range']
                                    and aligned(me['aim'],ga,tr,dist)
                                    and aligned(out['aim'],ga,tr,dist)
                                    and self.world.ray_clear(origin,gun_point))
                    if out['fire'][i] and lead_opt is not None and w.get('cooldown',0)<=0.1:
                        self.pending.append((obs['t']+math.dist(origin,gun_point)/ws['speed'],
                                             target.get('id'),lead_opt))
            elif w['kind']=='laser':
                charge=w.get('charge',0)
                clear=dist<=ws['range'] and self.world.ray_clear(origin,pt)
                if charge>0:
                    # False releases. Wait for full charge and an aligned shot,
                    # unless holding longer would hit the server's auto-fire cap.
                    release=mobile or (charge>=ws['charge'] and aligned(me['aim'],aim_at(origin,pt),tr,dist) and clear)
                    out['fire'][i]=not release
                elif laser_active and clear and w['cooldown']<=0:
                    out['fire'][i]=True
            elif w['kind']=='lightning':
                cone=math.radians(ws['cone_deg'])/2  # conservative if server uses half-angle
                out['fire'][i]=(dist<=ws['range'] and me['energy']>=reserve+ws['energy']
                                and abs(angle_diff(me['aim'][0],aim_at(origin,pt)[0]))<cone
                                and abs(angle_diff(out['aim'][0],aim_at(origin,pt)[0]))<cone
                                and self.world.ray_clear(origin,pt))
        return out
