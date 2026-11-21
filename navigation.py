"""Incremental A*: bounded work per decision, cached clearance and graph edges."""
import heapq
import math
import time
from geometry import distance


class Navigator:
    STEP=4.0
    def __init__(self,world):
        self.world=world
        self.body=None
        self.free_cache={}
        self.edge_cache={}
        self.path=[]
        self.search=None
        self.goal=None
        self.failed_until=0

    def reset(self):
        self.path=[]
        self.search=None
        self.goal=None

    def node(self,p):
        return round(p[0]/self.STEP),round(p[1]/self.STEP)

    def point(self,n):
        return n[0]*self.STEP,n[1]*self.STEP

    def free(self,n):
        if n not in self.free_cache:
            self.free_cache[n]=self.world.ground_free(*self.point(n),*self.body[:2])
        return self.free_cache[n]

    def edge(self,a,b):
        key=tuple(sorted((a,b)))
        if key not in self.edge_cache:
            self.edge_cache[key]=self.world.ground_segment(self.point(a),self.point(b),*self.body)
        return self.edge_cache[key]

    def nearest(self,p,connected=False):
        a,b=self.node(p)
        candidates=[(a+i,b+j) for i in range(-2,3) for j in range(-2,3)]
        for n in sorted(candidates,key=lambda n:distance(p,self.point(n))):
            if self.free(n) and (not connected or self.world.ground_segment(p,self.point(n),*self.body)):
                return n
        return None

    def waypoint(self,pos,goal,r,h,slope,now,budget=0.004):
        body=(math.ceil((r+0.3)*4)/4,math.ceil(h*2)/2,slope)
        if body!=self.body:
            self.body=body
            self.free_cache.clear()
            self.edge_cache.clear()
            self.reset()
        # Aerial and rooftop movement uses the local surface-aware controller.
        if pos[2]-self.world.height(*pos[:2])>2:
            return goal
        if distance(pos,goal)<14 and self.world.ground_segment(pos,goal,*self.body):
            return goal
        if self.goal is None or distance(goal,self.goal)>12:
            self.reset()
            self.goal=goal
        if self.path and distance(pos,self.path[0])>24:
            self.path=[]
        while self.path and distance(pos,self.path[0])<4:
            self.path.pop(0)
        if self.path:
            for idx in range(min(3,len(self.path)-1),0,-1):
                if distance(pos,self.path[idx])<18 and self.world.ground_segment(pos,self.path[idx],*self.body):
                    self.path=self.path[idx:]
                    break
            return self.path[0]
        if now<self.failed_until:
            return goal
        deadline=time.perf_counter()+budget
        if self.search is None:
            start=self.nearest(pos,connected=True)
            end=self.nearest(goal)
            if start is None or end is None:
                self.failed_until=now+0.6
                return goal
            self.search={'heap':[(distance(self.point(start),self.point(end)),start)],
                         'g':{start:0},'parent':{},'closed':set(),'end':end,'start':start}
        s=self.search
        best=None
        for _ in range(100):
            if not s['heap'] or time.perf_counter()>deadline:
                break
            _,n=heapq.heappop(s['heap'])
            if n in s['closed']:
                continue
            s['closed'].add(n)
            if n==s['end']:
                best=n
                break
            for dx,dy in [(1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)]:
                m=n[0]+dx,n[1]+dy
                if m in s['closed'] or not self.free(m) or not self.edge(n,m):
                    continue
                cost=s['g'][n]+self.STEP*math.hypot(dx,dy)
                if cost<s['g'].get(m,float('inf')):
                    s['g'][m]=cost
                    s['parent'][m]=n
                    heapq.heappush(s['heap'],(cost+distance(self.point(m),self.point(s['end'])),m))
        if best is not None:
            path=[]
            while best!=s['start']:
                path.append(self.point(best))
                best=s['parent'][best]
            self.path=list(reversed(path))
            self.search=None
            # The mech can move while A* runs. Join only a currently reachable point.
            join=None
            for i,q in enumerate(self.path[:8]):
                if distance(pos,q)<20 and self.world.ground_segment(pos,q,*self.body):
                    join=i
            if join is not None:
                self.path=self.path[join:]
                return self.path[0]
            self.path=[]
        elif not s['heap'] or len(s['closed'])>12000:
            self.search=None
            self.failed_until=now+1
        return goal
