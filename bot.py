"""Oval Sentinel v0.1: a deterministic, survival-oriented mechfight/1 bot."""
import math
import time
from collections import deque

import mechfight as mf
from combat import Combat, aim_at, center
from geometry import World, clamp, distance, unit
from navigation import Navigator


class Bot:
    name='Oval-Sentinel-v0.1'

    def __init__(self,hello):
        self.config=hello['config']
        self.world=World(hello['map']['dir'])
        self.nav=Navigator(self.world)
        self.combat=Combat(self.world)
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
        eye=[*me['pos'][:2],me['pos'][2]+self.stat(me,'eye_height',8)]
        actors=sorted(obs['mechs'],key=lambda e:distance(me['pos'],e['pos']))[:16]
        for e in actors:
            d=distance(me['pos'],e['pos'])
            if d>300:
                continue
            exposed=self.world.ray_clear(eye,center(e))
            # NPCs are locally dangerous but are not placement targets.
            if e['kind']=='npc' and d>60:
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
            return (t['dist']*0.65+hp*0.025+(40 if e['kind']=='npc' else 0)
                    -(14 if e['id']==self.target_id else 0)
                    -(60 if hp<180 else 0))
        target=min(candidates,key=score)['actor']
        self.target_id=target['id']
        return target

    def select_upgrade(self,obs):
        offer=obs.get('offer')
        if not offer:
            return None
        me=obs['self']
        ranks={'nanites':95,'servos':92,'armor':85,'jets':82,'plating':76,
               'reactor':72,'gun_damage':67,'gun_rate':64,'gun_mag':63,
               'laser_damage':66,'laser_charge':65,'lightning_range':70,
               'lightning_efficiency':69,'capacitor':61,'gun_velocity':60,
               'gyros':40,'sensors':38,'lightning_chain':35,'laser_pierce':30}
        if me['hp']/me['max_hp']<0.4:
            ranks['plating']+=18
        stacks=me.get('upgrades',[])
        return max(range(len(offer['choices'])),key=lambda i:
                   ranks.get(offer['choices'][i]['id'],20)-8*stacks.count(offer['choices'][i]['id']))

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
        return c[0]+r*dx,c[1]+r*dy

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
            dx,dy=unit(pos[0]-target['pos'][0],pos[1]-target['pos'][1])
            kinds=[w['kind'] for w in me['weapons'] if w]
            preferred=105 if 'laser' in kinds else 85
            if 'lightning' in kinds and me['energy']>55 and distance(pos,target['pos'])<55:
                preferred=34
            q=target['pos'][0]+dx*preferred,target['pos'][1]+dy*preferred
            # Never pursue a preferred range into the storm.
            if self.zone_cost(obs,q,6)<3:
                return q
            return anchor
        if self.mode=='COLLECT':
            options=[]
            has_secondary=any(w and w['kind']!='gun' for w in me['weapons'])
            for _,(kind,item,seen) in self.items.items():
                d=distance(pos,item['pos'])
                if d>70 or abs(pos[2]-item['pos'][2])>4 or self.zone_cost(obs,item['pos'],12)>0:
                    continue
                if kind=='pickups' and (has_secondary or item['kind'] not in ('laser','lightning')):
                    continue
                if kind=='crates' and me['hp']<0.88*me['max_hp']:
                    continue
                if any(distance(item['pos'],t['actor']['pos'])<65 for t in threats):
                    continue
                if not self.world.ground_free(*item['pos'][:2],radius+0.3,height):
                    continue
                bonus={'cubes':38,'pickups':32,'crates':10}[kind]
                options.append((d-bonus+(obs['t']-seen)*2,item['pos'][:2]))
            if options:
                return min(options,key=lambda t:t[0])[1]
        if self.mode in ('ESCAPE','HEAL','ROTATE'):
            deadline=min(self.deadline-0.012,time.perf_counter()+0.007)
            points=self.world.cover_points(pos,radius)+[anchor,tuple(pos[:2])]
            points.extend((pos[0]+24*math.cos(i*math.pi/4),pos[1]+24*math.sin(i*math.pi/4)) for i in range(8))
            candidates=[]
            for q in points:
                if candidates and time.perf_counter()>deadline:
                    break
                if not self.world.ground_free(*q,radius+0.3,height):
                    continue
                p=[*q,self.world.height(*q)]
                travel=distance(pos,q)
                score=travel*0.4+self.zone_cost(obs,q,max(8,travel/8))*14
                if self.mode=='ROTATE':
                    score+=distance(q,anchor)*1.8
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
                (self.mode=='ROTATE' and self.zone_cost(obs,pos,4)>0)))
        speed=self.stat(me,'boost_speed' if boost else 'walk_speed',19.5 if boost else 11.7)
        if any(w and w['kind']=='laser' and w.get('charge',0)>0 for w in me['weapons']):
            speed*=self.stat(me,'charge_move_mult',0.5)
        desired=unit(waypoint[0]-pos[0],waypoint[1]-pos[1])
        choices=[desired]+[(math.cos(i*math.pi/8),math.sin(i*math.pi/8)) for i in range(16)]+[(0,0)]
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
                p=self.world.motion(p,(p[0]+vx*0.2,p[1]+vy*0.2),r+0.15,h,
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

    def act(self,obs):
        # Reserve ~20 ms of the server's budget for transport, scheduling, and
        # machine variance. Expensive search/steering loops stop with a usable
        # candidate rather than trying to finish every possible calculation.
        self.deadline=time.perf_counter()+0.028
        me=obs['self']
        now=obs['t']
        pos=me['pos']
        self.update_items(obs)
        if any(e['type']=='damaged' for e in obs.get('events',[])):
            self.last_damage=now
        hp=me['hp']/max(1,me['max_hp'])
        if hp<0.53:
            self.healing=True
        elif hp>0.9:
            self.healing=False
        threats=self.threat_list(obs)
        target=self.choose_target(obs,threats)
        exposed=[t for t in threats if t['exposed']]
        close=[t for t in exposed if t['dist']<115 and t['actor']['kind']=='mech']
        z=obs['zone']
        travel=max(0,distance(pos,z['next_center'])-max(0,z['next_radius']-18))*1.6/max(1,self.stat(me,'walk_speed',11.7))
        urgent=(not me['in_zone'] or self.zone_cost(obs,pos,3)>0 or
                (travel>0 and z['shrink_end']-now<travel+12))
        if urgent:
            self.mode='ROTATE'
        elif self.healing:
            self.mode='ESCAPE' if exposed else 'HEAL'
        elif len(close)>=2:
            self.mode='ESCAPE'
        elif target is not None:
            self.mode='FIGHT'
        elif hp<0.88:
            self.mode='HEAL'
        else:
            self.mode='COLLECT'
        if self.goal is None or now-self.goal_at>0.8 or self.mode!=self.previous_mode:
            self.goal=self.choose_goal(obs,threats,target)
            self.goal_at=now
        self.previous_mode=self.mode
        # Keep the goal stable between strategic updates so A* can finish.
        waypoint=self.nav.waypoint(pos,self.goal,self.stat(me,'radius',2.5),self.stat(me,'height',9),
                                   self.stat(me,'max_slope_deg',50),now)
        action=self.steer(obs,waypoint,threats)
        self.history.append((now,tuple(pos[:2]),math.hypot(*action['move'])))
        while self.history and now-self.history[0][0]>1.5:
            self.history.popleft()
        if self.history and now-self.history[0][0]>1.2 and now-self.last_reset>2:
            if distance(pos,self.history[0][1])<1 and sum(p[2] for p in self.history)/len(self.history)>0.5:
                self.nav.reset()
                self.recover_until=now+1.2
                self.last_reset=now
                self.goal_at=-100
        facing=target or (threats[0]['actor'] if threats else None)
        if facing is not None:
            yaw=math.atan2(facing['pos'][1]-pos[1],facing['pos'][0]-pos[0])
        else:
            # Torso-only scan; movement does not depend on the look direction.
            yaw=(now*0.9+self.slot*0.7+math.pi)%(2*math.pi)-math.pi
            damage=next((e for e in reversed(obs.get('events',[])) if e['type']=='damaged' and e.get('bearing') is not None),None)
            if damage:
                yaw=damage['bearing']
        allow_fire=self.mode in ('FIGHT','ROTATE') and not self.healing
        # Shoot a nearby visible crate only when healthy and unthreatened. Never
        # use remembered crates for firing: they may already have been destroyed.
        if self.mode=='COLLECT' and not threats and hp>0.88:
            crates=[c for c in obs.get('crates',[]) if distance(pos,c['pos'])<65 and distance(c['pos'],self.goal)<8]
            if crates:
                target=min(crates,key=lambda c:distance(pos,c['pos']))
                allow_fire=True
        if target is None and facing is not None:
            target=facing
        action.update(self.combat.command(obs,target,allow_fire,yaw))
        # Reload early while safe, rather than entering a fight with two rounds.
        gun=next((w for w in me['weapons'] if w and w['kind']=='gun'),None)
        if gun and gun.get('reload',0)<=0:
            action['reload']=(gun.get('ammo',0)==0 or
                              (not any(action['fire']) and not close and gun.get('ammo',0)<gun['stats']['mag']*0.65))
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
