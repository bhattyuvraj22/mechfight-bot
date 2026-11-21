"""Oval Sentinel v0.4: adaptive lead, laser dodging, kill chasing, sound facing."""
import math
import time
from collections import deque

import mechfight as mf
from combat import Combat, aim_at, center
from geometry import World, clamp, distance, unit
from navigation import Navigator
from tactics import Tactics, pick_upgrade


class Bot:
    name='Oval-Sentinel-baseline-simple'

    def __init__(self,hello):
        self.config=hello['config']
        self.world=World(hello['map']['dir'])
        self.nav=Navigator(self.world)
        self.combat=Combat(self.world,hello.get('seed',0))
        self.slot=hello['slot']
        self.healing=False
        self.mode='COLLECT'
        self.goal=None
        self.goal_at=-100
        self.previous_mode=None
        self.target_id=None
        self.history=deque()
        self.recover_until=-1
        self.last_reset=-100
        self.last_damage=-100
        self.items={}
        self.visited={}
        self.explore_goal=None
        self.explore_until=-1
        self.last_self_hp=None
        self.damage_bearing=None
        self.damage_bearing_at=-100
        self.failed_goals={}
        self.last_waypoint=None
        self.tactics=Tactics(self.config,hello.get('seed',0))
        self.now=0
        self.commit=False
        self.kill_hp=220
        self.juking=False
        self.dodging=False
        self.dodge_until=-1

    def stat(self,me,key,default):
        return me['stats'].get(key,self.config['mech'].get(key,default))

    @staticmethod
    def future_zone(obs,seconds):
        z=obs['zone']
        now=obs['t']
        if now+seconds<=z['shrink_start']:
            return z['center'],z['radius']
        start=max(now,z['shrink_start'])
        f=clamp((now+seconds-start)/max(0.001,z['shrink_end']-start),0,1)
        return ([z['center'][i]+(z['next_center'][i]-z['center'][i])*f for i in range(2)],
                z['radius']+(z['next_radius']-z['radius'])*f)

    def zone_cost(self,obs,p,horizon=5):
        c,r=self.future_zone(obs,horizon)
        # Keep a margin that shrinks with the circle, so a zero-radius endgame
        # still points toward the centre rather than declaring every route invalid.
        margin=min(10,r*0.12)
        return max(0,distance(p,c)-max(0,r-margin))

    def threat_list(self,obs):
        me=obs['self']
        result=[]
        muzzle=[*me['pos'][:2],me['pos'][2]+self.stat(me,'muzzle_height',7)]
        actors=sorted(obs['mechs'],key=lambda e:distance(me['pos'],e['pos']))[:16]
        for e in actors:
            d=distance(me['pos'],e['pos'])
            if d>300:
                continue
            exposed=self.world.ray_clear(muzzle,center(e))
            # NPCs are locally dangerous but are not placement targets.
            if e['kind']=='npc' and d>self.tactics.npc_reach(obs):
                continue
            result.append({'actor':e,'dist':d,'exposed':exposed})
        return result

    def choose_target(self,obs,threats):
        candidates=[t for t in threats if t['exposed'] and t['dist']<240]
        if not candidates:
            return None
        def score(t):
            e=t['actor']
            hp=e.get('hp',1400)
            return (t['dist']*0.45+hp*0.045+(65 if e['kind']=='npc' else 0)
                    -(30 if e['id']==self.target_id else 0)
                    -(85 if hp<self.kill_hp else 0)
                    -(40 if self.tactics.recent_attacker(e['id'],self.now) else 0)
                    -(35 if e.get('charging') else 0))
        target=min(candidates,key=score)['actor']
        self.target_id=target['id']
        return target

    def chase_target(self,obs):
        """A wounded target that slipped out of sight: hunt it down before it
        regenerates. Every house bot that dies before us is a placement point."""
        me=obs['self']
        if self.target_id is None:
            return None
        t=next((m for m in obs['mechs'] if m['id']==self.target_id and m.get('kind')=='mech'),None)
        if t is None:
            return None
        hp=t.get('hp',1400)
        if (hp>0.45*t.get('max_hp',1400) or me['hp']<1.2*hp or me['hp']<0.35*me['max_hp']
                or distance(me['pos'],t['pos'])>170 or self.zone_cost(obs,t['pos'],4)>0):
            return None
        others=sum(1 for m in obs['mechs'] if m.get('kind')=='mech' and m['id']!=t['id']
                   and distance(m['pos'],t['pos'])<90)
        return t if others<=1 else None

    def select_upgrade(self,obs):
        offer=obs.get('offer')
        if not offer:
            return None
        return pick_upgrade(offer,[w['kind'] for w in obs['self']['weapons'] if w])

    def update_items(self,obs):
        now=obs['t']
        for kind in ('pickups','cubes','crates'):
            visible={item['id'] for item in obs.get(kind,[])}
            for item in obs.get(kind,[]):
                self.items[item['id']]=(kind,item,now)
            # At pickup range a missing object is no longer worth pursuing.
            for key,(k,item,seen) in list(self.items.items()):
                if now-seen>12 or (k==kind and key not in visible and distance(obs['self']['pos'],item['pos'])<5):
                    del self.items[key]

    def safe_anchor(self,obs):
        me=obs['self']
        z=obs['zone']
        c=z['next_center']
        dx,dy=unit(me['pos'][0]-c[0],me['pos'][1]-c[1])
        # Prefer the nearer side of the next circle, but with room to retreat.
        r=min(distance(me['pos'],c),max(0,z['next_radius']*0.55-12))
        q=c[0]+r*dx,c[1]+r*dy
        return self.walkable_goal(q,me)

    def walkable_goal(self,q,me):
        r,h=self.stat(me,'radius',2.5),self.stat(me,'height',9)
        if self.world.ground_free(*q,r+0.3,h):
            return q
        # A zone centre / combat range point can fall inside a solid building.
        # Find a usable nearby ground destination before asking A* to route there.
        for radius in (8,16,28,44):
            points=[(q[0]+radius*math.cos(i*math.pi/4),q[1]+radius*math.sin(i*math.pi/4)) for i in range(8)]
            for p in sorted(points,key=lambda p:distance(me['pos'],p)):
                if self.world.ground_free(*p,r+0.3,h):
                    return p
        return tuple(me['pos'][:2])

    @staticmethod
    def cell(p):
        return math.floor(p[0]/24),math.floor(p[1]/24)

    def loot_goal(self,obs,threats,near_only=False):
        me=obs['self'];pos=me['pos'];now=obs['t']
        r,h=self.stat(me,'radius',2.5),self.stat(me,'height',9)
        has_secondary=any(w and w['kind']!='gun' for w in me['weapons'])
        choices=[]
        for _,(kind,item,seen) in self.items.items():
            p=item['pos'];d=distance(pos,p)
            if d>(18 if near_only else 100) or abs(pos[2]-p[2])>4 or self.zone_cost(obs,p,12)>0:
                continue
            if self.failed_goals.get(self.cell(p),-1)>now:
                continue
            if kind=='pickups' and (has_secondary or item['kind'] not in ('laser','lightning')):
                continue
            if kind=='crates' and (near_only or me['hp']<0.75*me['max_hp']
                                   or any(t['actor']['kind']=='mech' for t in threats)):
                continue
            dangerous=False
            for t in threats[:4]:
                # A short detour away from a distant attacker can still equip us.
                enemy_distance=distance(p,t['actor']['pos'])
                if enemy_distance<45 or (t['exposed'] and enemy_distance<t['dist']-5):
                    dangerous=True
                    break
            if dangerous or not self.world.ground_free(*p[:2],r+0.3,h):
                continue
            if near_only and not self.world.ground_segment(pos,p,r+0.3,h):
                continue
            bonus={'cubes':40,'pickups':55,'crates':12}[kind]
            choices.append((d-bonus+(now-seen)*2,p[:2]))
        if not near_only:
            for p in self.drop_points(obs,threats):
                choices.append((distance(pos,p)-120,p))
        return min(choices,key=lambda it:it[0])[1] if choices else None

    def drop_points(self,obs,threats):
        # Supply drop: 3 cubes, full HP and full energy for 4 s alone in the ring.
        me=obs['self'];pos=me['pos'];out=[]
        r,h=self.stat(me,'radius',2.5),self.stat(me,'height',9)
        speed=max(1,self.stat(me,'walk_speed',11.7))
        for d in obs.get('drops',[]) or []:
            p=d['pos'];dist=distance(pos,p)
            if dist>170 or d.get('lands_in',0)>dist/speed+8 or self.zone_cost(obs,p,10)>0:
                continue
            if any(distance(p,t['actor']['pos'])<60 for t in threats[:4] if t['actor']['kind']=='mech'):
                continue
            if self.world.ground_free(*p[:2],r+0.3,h):
                out.append(tuple(p[:2]))
        return out

    def preferred_range(self,me,target):
        pos=me['pos']
        kinds=[w['kind'] for w in me['weapons'] if w]
        # Juking targets: lead error grows with flight time, so fight closer.
        preferred=95 if 'laser' in kinds else 65
        d=distance(pos,target['pos'])
        # Lightning: 240 DPS, auto-aimed inside 45 m. Close in and use it.
        if 'lightning' in kinds and me['energy']>40 and d<85:
            preferred=30
        thp=target.get('hp',1400)
        if target.get('kind')=='mech' and thp<0.35*target.get('max_hp',1400) and me['hp']>thp:
            preferred=min(preferred,40)
        return preferred

    def explore(self,obs,threats):
        now=obs['t'];me=obs['self'];pos=me['pos']
        if (self.explore_goal is not None and now<self.explore_until
                and distance(pos,self.explore_goal)>5 and self.zone_cost(obs,self.explore_goal,10)<1
                and self.failed_goals.get(self.cell(self.explore_goal),-1)<=now):
            return self.explore_goal
        r,h=self.stat(me,'radius',2.5),self.stat(me,'height',9)
        candidates=[]
        for i in range(12):
            angle=i*math.pi/6+self.slot*0.37
            q=pos[0]+42*math.cos(angle),pos[1]+42*math.sin(angle)
            if self.zone_cost(obs,q,12)>0 or self.failed_goals.get(self.cell(q),-1)>now:
                continue
            if not self.world.ground_free(*q,r+0.3,h):
                continue
            age=now-self.visited.get(self.cell(q),-1000)
            score=max(0,60-age)*1.2
            if not self.world.ground_segment(pos,q,r+0.3,h):
                score+=15
            score+=sum(max(0,100-distance(q,t['actor']['pos'])) for t in threats[:3])
            # Prefer space towards the next safe area, without treating the
            # current position as the final destination of resource collection.
            score+=distance(q,obs['zone']['next_center'])*0.03
            candidates.append((score,q))
        self.explore_goal=min(candidates,key=lambda it:it[0])[1] if candidates else self.safe_anchor(obs)
        self.explore_until=now+6
        return self.explore_goal

    def exposure(self,p,threats,height):
        value=0
        for threat in threats[:3]:
            e=threat['actor']
            d=distance(p,e['pos'])
            origin=center(e)
            origin[2]+=2
            if self.world.ray_clear(origin,[p[0],p[1],p[2]+height*0.5]):
                weight=0.5 if e['kind']=='npc' else 1
                value+=weight*(25+max(0,140-d)*0.55)
        return value

    def choose_goal(self,obs,threats,target):
        me=obs['self']
        pos=me['pos']
        radius=self.stat(me,'radius',2.5)
        height=self.stat(me,'height',9)
        anchor=self.safe_anchor(obs)
        if self.mode=='FIGHT' and target:
            loot=self.loot_goal(obs,threats,near_only=True)
            if loot is not None:
                return loot
            if target['kind']=='mech':
                dx,dy=unit(pos[0]-target['pos'][0],pos[1]-target['pos'][1])
                radial=clamp(self.preferred_range(me,target)-distance(pos,target['pos']),-16,12)
                sign=1 if int(obs['t']/1.8)%2==0 else -1
                for lateral in (14*sign,-14*sign):
                    q=(pos[0]+radial*dx-lateral*dy,pos[1]+radial*dy+lateral*dx)
                    if (self.zone_cost(obs,q,6)==0 and
                            self.world.ground_segment(pos,q,radius+0.3,height) and
                            self.world.ray_clear([*q,self.world.height(*q)+self.stat(me,'muzzle_height',7)],center(target))):
                        return q
            dx,dy=unit(pos[0]-target['pos'][0],pos[1]-target['pos'][1])
            preferred=self.preferred_range(me,target)
            q=self.walkable_goal((target['pos'][0]+dx*preferred,target['pos'][1]+dy*preferred),me)
            # Never pursue a preferred range into the storm.
            if self.zone_cost(obs,q,6)<3:
                return q
            return anchor
        if self.mode=='CHASE' and target:
            v=target.get('vel',[0,0,0])
            q=(target['pos'][0]+v[0]*1.0,target['pos'][1]+v[1]*1.0)
            return self.walkable_goal(q,me)
        if self.mode=='COLLECT':
            loot=self.loot_goal(obs,threats)
            return loot if loot is not None else self.explore(obs,threats)
        if self.mode in ('ESCAPE','HEAL','ROTATE'):
            deadline=min(self.deadline-0.012,time.perf_counter()+0.007)
            drops=self.drop_points(obs,threats) if self.mode=='HEAL' else []
            points=[anchor,tuple(pos[:2])]+drops+self.world.cover_points(pos,radius)
            points.extend((pos[0]+24*math.cos(i*math.pi/4),pos[1]+24*math.sin(i*math.pi/4)) for i in range(8))
            candidates=[]
            for q in points:
                if candidates and time.perf_counter()>deadline:
                    break
                if not self.world.ground_free(*q,radius+0.3,height):
                    continue
                if self.failed_goals.get(self.cell(q),-1)>obs['t']:
                    continue
                p=[*q,self.world.height(*q)]
                travel=distance(pos,q)
                score=travel*0.4+self.zone_cost(obs,q,max(8,travel/8))*14
                if not self.world.ground_segment(pos,q,radius+0.3,height):
                    score+=12  # A nearby point behind a wall may need a long detour.
                if self.mode=='ROTATE':
                    score+=distance(q,anchor)*1.8
                if q in drops:
                    score-=80  # a drop is a full heal
                score+=self.exposure(p,threats,height)*1.8
                if self.mode=='ESCAPE':
                    score+=sum(max(0,75-distance(q,t['actor']['pos'])) for t in threats[:3])
                if self.goal is not None:
                    score+=min(10,distance(q,self.goal)*0.2)
                candidates.append((score,q))
            if candidates:
                return min(candidates,key=lambda item:item[0])[1]
        return anchor

    def projectile_cost(self,obs,end):
        me=obs['self']
        radius=self.stat(me,'radius',2.5)
        height=self.stat(me,'height',9)
        cost=0
        vx,vy=(end[0]-me['pos'][0])/0.6,(end[1]-me['pos'][1])/0.6
        for shot in obs.get('projectiles',[])[:48]:
            q=shot['pos']
            v=shot['vel']
            rx,ry=q[0]-me['pos'][0],q[1]-me['pos'][1]
            dx,dy=v[0]-vx,v[1]-vy
            t=clamp(-(rx*dx+ry*dy)/(dx*dx+dy*dy or 1),0,0.6)
            z=q[2]+v[2]*t
            splash=0
            if shot['kind']=='mortar':
                z-=0.5*self.config['weapons']['mortar']['gravity']*t*t
                splash=self.config['weapons']['mortar']['splash_radius']
            if me['pos'][2]-splash<=z<=me['pos'][2]+height+splash:
                miss=math.hypot(rx+dx*t,ry+dy*t)
                cost+=max(0,radius+splash+2-miss)*10
        return cost

    def steer(self,obs,waypoint,threats):
        me=obs['self']
        pos=me['pos']
        r,h=self.stat(me,'radius',2.5),self.stat(me,'height',9)
        near=min((t['dist'] for t in threats if t['exposed']),default=999)
        boost=(me['grounded'] and me['energy']>32 and
               (not me['in_zone'] or (self.mode=='ESCAPE' and near<105) or
                (self.mode=='ROTATE' and self.zone_cost(obs,pos,4)>0) or
                (self.mode=='CHASE' and me['energy']>45)))
        speed=self.stat(me,'boost_speed' if boost else 'walk_speed',19.5 if boost else 11.7)
        if any(w and w['kind']=='laser' and w.get('charge',0)>0 for w in me['weapons']):
            speed*=self.stat(me,'charge_move_mult',0.5)
        desired=unit(waypoint[0]-pos[0],waypoint[1]-pos[1])
        approach=min(1,distance(pos,waypoint)/max(1,speed*0.6))
        # Full-speed-only rollouts reject a perfectly valid short approach to a
        # corner because they continue into the wall beyond it. Partial inputs
        # let us brake and reach the turning point instead of stopping early.
        choices=[(desired[0]*approach,desired[1]*approach),desired,(0,0)]
        for i in range(16):
            direction=(math.cos(i*math.pi/8),math.sin(i*math.pi/8))
            choices.append(direction)
            if i%2==0:
                choices.append((direction[0]*0.4,direction[1]*0.4))
        best=(float('inf'),(0,0))
        urgency=1.5 if self.mode=='ROTATE' else 1.0
        for direction in choices:
            if best[0]<float('inf') and time.perf_counter()>self.deadline-0.004:
                break
            p=tuple(pos)
            vx,vy=me['vel'][:2]
            valid=True
            for _ in range(3):
                ax,ay=direction[0]*speed-vx,direction[1]*speed-vy
                acc=self.stat(me,'ground_accel' if me['grounded'] else 'air_accel',58.5 if me['grounded'] else 12)*0.2
                factor=min(1,acc/(math.hypot(ax,ay) or 1))
                vx,vy=vx+ax*factor,vy+ay*factor
                p=self.world.motion(p,(p[0]+vx*0.2,p[1]+vy*0.2),r,h,
                                    self.stat(me,'step_up',1.2),self.stat(me,'max_slope_deg',50))
                if p is None:
                    valid=False
                    break
            if not valid:
                continue
            score=distance(p,waypoint)*urgency+self.zone_cost(obs,p,2)*18
            score+=self.projectile_cost(obs,p)
            for threat in threats[:3]:
                e=threat['actor']
                d=distance(p,e['pos'])
                if d<r+3:
                    score+=100
                if self.mode in ('ESCAPE','HEAL'):
                    score+=max(0,70-d)*0.65
            if self.mode in ('ESCAPE','HEAL') and threats:
                score+=self.exposure(p,threats[:2],h)*0.45
            if self.mode=='FIGHT' and threats:
                # A small alternating strafe preference at useful shooting range.
                e=threats[0]['actor']
                dx,dy=unit(pos[0]-e['pos'][0],pos[1]-e['pos'][1])
                side=1 if (int(obs['t']/2.7)+self.slot)%2 else -1
                score-=side*(-dy*direction[0]+dx*direction[1])*2.5
            if obs['t']<self.recover_until:
                angle=(self.slot+int(obs['t']))*2.39996
                score-=5*(direction[0]*math.cos(angle)+direction[1]*math.sin(angle))
            if score<best[0]:
                best=score,direction
        return {'move':list(best[1]),'boost':bool(boost and best[1]!=(0,0)),'jump':False}

    def should_fire(self,obs,target):
        if target is None or target.get('kind') not in ('mech','npc'):
            return False
        if self.mode in ('FIGHT','CHASE') or (not self.healing and self.mode!='HEAL'):
            return True
        if target.get('kind')=='mech' and (self.commit or target.get('hp',1400)<=self.kill_hp):
            return True  # a kill is a full placement point
        me=obs['self']
        # No healing can occur while storm damage keeps resetting the timer.
        # Return fire under continuing attack, but stop after breaking contact
        # so healing can actually start. Very close enemies merit self-defence.
        return (not me['in_zone'] or obs['t']-self.last_damage<1.2
                or distance(me['pos'],target['pos'])<45)

    def juke(self,obs,target,threats,action):
        """Replace the strafe with random full-speed headings, but only once the
        bullets we see are leading us; head-on shooters keep the HEAD strafe."""
        if (self.mode!='FIGHT' or target is None or target.get('kind')!='mech'
                or not self.tactics.should_juke()):
            return False
        if not any(t['exposed'] for t in threats[:3]):
            return False
        me=obs['self'];pos=me['pos']
        r,h=self.stat(me,'radius',2.5),self.stat(me,'height',9)
        speed=self.stat(me,'walk_speed',11.7)
        accel=self.stat(me,'ground_accel',58.5)
        muzzle=self.stat(me,'muzzle_height',7)
        opts=self.tactics.juke_options(obs,target['pos'],self.preferred_range(me,target),speed,accel)
        fallback=None
        for i,v in enumerate(opts[:6]):
            q=(pos[0]+v[0]*7,pos[1]+v[1]*7)
            if self.zone_cost(obs,q,6)>0 or not self.world.ground_segment(pos,q,r+0.3,h):
                if i==0:
                    self.tactics.flip(obs['t'])
                continue
            if self.world.ray_clear([*q,self.world.height(*q)+muzzle],center(target)):
                action['move']=[v[0],v[1]];action['boost']=False
                return True
            if fallback is None:
                fallback=v
        if fallback is not None:
            action['move']=[fallback[0],fallback[1]];action['boost']=False
            return True
        return False

    def laser_dodge(self,obs,action):
        """An enemy is charging a laser at us (315 hitscan, cannot be sidestepped
        once it tracks). The only defence is breaking line of sight before it
        releases (~0.75 s): find a short reachable step that hides us."""
        me=obs['self'];pos=me['pos'];now=obs['t']
        chargers=self.tactics.laser_threats(obs)
        if not chargers:
            return False
        r,h=self.stat(me,'radius',2.5),self.stat(me,'height',9)
        body=[pos[0],pos[1],pos[2]+h*0.5]
        def muzzle(m):
            return [m['pos'][0],m['pos'][1],m['pos'][2]+7*(1+0.05*m.get('cubes',0))]
        chargers=[m for m in chargers if self.world.ray_clear(muzzle(m),body)][:2]
        if not chargers:
            return False
        best=None
        deadline=self.deadline-0.006
        for step in (5,8):
            for i in range(16):
                if time.perf_counter()>deadline:
                    break
                a=i*math.pi/8
                d=(math.cos(a),math.sin(a))
                q=(pos[0]+d[0]*step,pos[1]+d[1]*step)
                if self.zone_cost(obs,q,3)>0 or not self.world.ground_segment(pos,q,r+0.3,h):
                    continue
                z=self.world.height(*q)
                if all(not self.world.ray_clear(muzzle(m),[q[0],q[1],z+h*0.5]) and
                       not self.world.ray_clear(muzzle(m),[q[0],q[1],z+h*0.9]) for m in chargers):
                    # Prefer steps close to our current heading (less braking).
                    v=me['vel']
                    cost=step-0.1*(d[0]*v[0]+d[1]*v[1])
                    if best is None or cost<best[0]:
                        best=(cost,d)
            if best is not None:
                break
        if best is None:
            return False
        action['move']=[best[1][0],best[1][1]]
        action['boost']=bool(me['grounded'] and me['energy']>12)
        self.dodge_until=now+0.5
        return True

    def act(self,obs):
        # Reserve ~20 ms of the server's budget for transport, scheduling, and
        # machine variance. Expensive search/steering loops stop with a usable
        # candidate rather than trying to finish every possible calculation.
        self.deadline=time.perf_counter()+0.028
        me=obs['self']
        now=obs['t']
        pos=me['pos']
        self.update_items(obs)
        self.visited[self.cell(pos)]=now
        self.failed_goals={k:v for k,v in self.failed_goals.items() if v>now}
        if (any(e['type']=='damaged' for e in obs.get('events',[])) or
                (self.last_self_hp is not None and me['hp']<self.last_self_hp)):
            self.last_damage=now
        self.last_self_hp=me['hp']
        damage=next((e for e in reversed(obs.get('events',[])) if e['type']=='damaged' and e.get('bearing') is not None),None)
        if damage:
            self.damage_bearing=damage['bearing']
            self.damage_bearing_at=now
        self.now=now
        self.tactics.note_events(obs)
        self.tactics.observe_shots(obs)
        self.combat.observe(obs)
        self.kill_hp=self.tactics.kill_hp(me)
        threats=self.threat_list(obs)
        target=self.choose_target(obs,threats)
        self.tactics.evaluate(obs,target=target if target is not None else {})
        self.commit=self.tactics.committed
        hp=me['hp']/max(1,me['max_hp'])
        if hp<0.53 and not self.commit:
            self.healing=True
        elif hp>0.9 or self.commit:
            self.healing=False  # a winning trade is finished, not fled
        exposed=[t for t in threats if t['exposed']]
        close=[t for t in exposed if t['dist']<115 and t['actor']['kind']=='mech']
        chase=self.chase_target(obs) if target is None else None
        # A clearly winnable kill is finished even when we are below the heal line.
        finish=(target is not None and target['kind']=='mech'
                and target.get('hp',1400)<0.4*target.get('max_hp',1400)
                and me['hp']>1.2*target.get('hp',1400) and len(close)<2)
        z=obs['zone']
        travel=max(0,distance(pos,z['next_center'])-max(0,z['next_radius']-18))*1.6/max(1,self.stat(me,'walk_speed',11.7))
        urgent=(not me['in_zone'] or self.zone_cost(obs,pos,3)>0 or
                (travel>0 and z['shrink_end']-now<travel+12))
        if urgent:
            self.mode='ROTATE'
        elif finish:
            self.mode='FIGHT'
        elif chase is not None and len(close)<2:
            self.mode='CHASE'
            target=chase
        elif self.healing:
            self.mode='ESCAPE' if exposed else 'HEAL'
        elif len(close)>=2 and not self.commit:
            self.mode='ESCAPE'
        elif target is not None:
            self.mode='FIGHT'
        elif hp<0.88:
            self.mode='HEAL'
        else:
            self.mode='COLLECT'
        if (self.goal is None or now-self.goal_at>(0.4 if self.mode=='CHASE' else 0.8)
                or self.mode!=self.previous_mode):
            self.goal=self.choose_goal(obs,threats,target)
            self.goal_at=now
        self.previous_mode=self.mode
        # Keep the goal stable between strategic updates so A* can finish.
        waypoint=self.nav.waypoint(pos,self.goal,self.stat(me,'radius',2.5),self.stat(me,'height',9),
                                   self.stat(me,'max_slope_deg',50),now)
        self.last_waypoint=waypoint
        action=self.steer(obs,waypoint,threats)
        self.juking=self.juke(obs,target,threats,action)
        self.dodging=self.laser_dodge(obs,action)
        wants_progress=(not self.juking) and (not self.dodging) and distance(pos,self.goal)>6 and distance(pos,waypoint)>1.5
        self.history.append((now,tuple(pos[:2]),float(wants_progress)))
        while self.history and now-self.history[0][0]>1.5:
            self.history.popleft()
        if self.history and now-self.history[0][0]>1.2 and now-self.last_reset>2:
            if distance(pos,self.history[0][1])<1 and sum(p[2] for p in self.history)/len(self.history)>0.5:
                self.nav.reset()
                self.recover_until=now+1.2
                self.last_reset=now
                self.goal_at=-100
                self.failed_goals[self.cell(self.goal)]=now+5
                self.explore_until=-1
        facing=target or (threats[0]['actor'] if threats else None)
        if facing is not None:
            yaw=math.atan2(facing['pos'][1]-pos[1],facing['pos'][0]-pos[0])
        else:
            # Torso-only scan; movement does not depend on the look direction.
            yaw=(now*0.9+self.slot*0.7+math.pi)%(2*math.pi)-math.pi
            heard=self.tactics.threat_bearing(now)
            if heard is not None:
                yaw=heard  # face hunters before they arrive: front armor + vision
            if self.damage_bearing is not None and now-self.damage_bearing_at<2:
                yaw=self.damage_bearing
        allow_fire=self.should_fire(obs,target)
        # Shoot a nearby visible crate only when healthy and unthreatened. Never
        # use remembered crates for firing: they may already have been destroyed.
        if (self.mode=='COLLECT' and hp>0.7
                and not any(t['actor']['kind']=='mech' for t in threats) and not exposed):
            crates=[c for c in obs.get('crates',[]) if distance(pos,c['pos'])<65 and distance(c['pos'],self.goal)<8]
            if crates:
                target=min(crates,key=lambda c:distance(pos,c['pos']))
                allow_fire=True
        if target is None and facing is not None:
            target=facing
        reserve=8 if self.mode in ('FIGHT','CHASE') else 28
        action.update(self.combat.command(obs,target,allow_fire,yaw,reserve=reserve,
                                         mobile=self.mode in ('ESCAPE','ROTATE') or action['boost']))
        # Reload early while safe, rather than entering a fight with two rounds.
        gun=next((w for w in me['weapons'] if w and w['kind']=='gun'),None)
        if gun and gun.get('reload',0)<=0:
            action['reload']=(gun.get('ammo',0)==0 or
                              (not any(action['fire']) and not exposed and gun.get('ammo',0)<gun['stats']['mag']*0.65))
        if any(w is None for w in me['weapons']):
            reach=self.config['loot']['pickup_radius']
            pickups=[p for p in obs.get('pickups',[]) if p['kind'] in ('laser','lightning')
                     and distance(pos,p['pos'])<=reach and abs(pos[2]-p['pos'][2])<=4
                     and not any(w and w['kind']==p['kind'] for w in me['weapons'])]
            if pickups:
                action['take']=min(pickups,key=lambda p:distance(pos,p['pos']))['id']
        pick=self.select_upgrade(obs)
        if pick is not None:
            action['pick']=pick
        action['tick']=obs['tick']
        return action


if __name__=='__main__':
    mf.run(Bot)
