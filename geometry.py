"""Static arena geometry. Trees affect sight, but deliberately never stop bullets.

Prism intersections are polygon-exact; terrain rays and motion use sampled heights.
This is a conservative navigation model, not a replica of server physics.
"""
import array
import json
import math
import sys
from collections import defaultdict
from pathlib import Path


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def unit(x, y):
    n = math.hypot(x, y)
    return (x / n, y / n) if n > 1e-8 else (0.0, 0.0)


def inside(x, y, ring):
    yes = False
    ax, ay = ring[-1]
    for bx, by in ring:
        if (ay > y) != (by > y) and x < (bx-ax)*(y-ay)/(by-ay)+ax:
            yes = not yes
        ax, ay = bx, by
    return yes


def segment_distance2(x, y, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    t = clamp(((x-a[0])*dx+(y-a[1])*dy)/(dx*dx+dy*dy or 1), 0, 1)
    return (x-a[0]-t*dx)**2+(y-a[1]-t*dy)**2


class Prism:
    def __init__(self, data):
        self.base, self.top = data['base'], data['top']
        self.rings = [list(zip(r[::2], r[1::2]))
                      for r in [data['ring']] + data.get('holes', [])]
        r = self.rings[0]
        self.bounds = min(x for x,y in r), min(y for x,y in r), max(x for x,y in r), max(y for x,y in r)
        self.edges = [(r[i-1], r[i]) for r in self.rings for i in range(len(r))]

    def contains(self, x, y):
        return inside(x, y, self.rings[0]) and not any(inside(x, y, h) for h in self.rings[1:])

    def overlaps(self, x, y, radius):
        a,b,c,d = self.bounds
        if x < a-radius or x > c+radius or y < b-radius or y > d+radius:
            return False
        return self.contains(x,y) or any(segment_distance2(x,y,a,b) < radius*radius for a,b in self.edges)

    def intersects(self, a, b):
        # Clip the segment to the prism's vertical slab first, then partition its
        # horizontal projection at polygon edges. Midpoints handle courtyard holes.
        dz = b[2]-a[2]
        if abs(dz) < 1e-10:
            if not self.base <= a[2] <= self.top:
                return False
            lo,hi = 0.0,1.0
        else:
            u,v = (self.base-a[2])/dz,(self.top-a[2])/dz
            lo,hi = max(0,min(u,v)),min(1,max(u,v))
            if lo > hi:
                return False
        dx,dy = b[0]-a[0],b[1]-a[1]
        ts = [lo,hi]
        for p,q in self.edges:
            ex,ey = q[0]-p[0],q[1]-p[1]
            den = dx*ey-dy*ex
            if abs(den) < 1e-10:
                continue
            px,py = p[0]-a[0],p[1]-a[1]
            t,u = (px*ey-py*ex)/den,(px*dy-py*dx)/den
            if lo <= t <= hi and 0 <= u <= 1:
                ts.append(t)
        ts.sort()
        return any(self.contains(a[0]+dx*t, a[1]+dy*t)
                   for t in [lo,hi]+[(u+v)/2 for u,v in zip(ts,ts[1:])])


class World:
    BIN = 32

    def __init__(self, directory):
        root = Path(directory) / 'v2'
        data = json.loads((root/'world.json').read_text())
        self.bounds = data['bounds']
        self.terrain = data['terrain']
        self.heights = array.array('h')
        self.heights.frombytes((root/'terrain.i16').read_bytes())
        if sys.byteorder != 'little':
            self.heights.byteswap()
        assert len(self.heights) == self.terrain['nx']*self.terrain['ny']
        self.prisms = [Prism(p) for p in data['prisms']]
        self.bins = defaultdict(list)
        for i,p in enumerate(self.prisms):
            for cell in self.cells(*p.bounds):
                self.bins[cell].append(i)

    def cells(self, x0,y0,x1,y1):
        for i in range(math.floor(x0/self.BIN), math.floor(x1/self.BIN)+1):
            for j in range(math.floor(y0/self.BIN), math.floor(y1/self.BIN)+1):
                yield i,j

    def nearby(self, x0,y0,x1,y1):
        ids = set()
        for cell in self.cells(x0,y0,x1,y1):
            ids.update(self.bins.get(cell, ()))
        return (self.prisms[i] for i in sorted(ids))

    def height(self,x,y):
        t = self.terrain
        u = clamp((x-t['minX'])/t['step'],0,t['nx']-1.000001)
        v = clamp((y-t['minY'])/t['step'],0,t['ny']-1.000001)
        i,j = int(u),int(v)
        fx,fy = u-i,v-j
        k = j*t['nx']+i
        h = self.heights
        return ((h[k]*(1-fx)+h[k+1]*fx)*(1-fy)+(h[k+t['nx']]*(1-fx)+h[k+t['nx']+1]*fx)*fy)*t.get('scale',0.01)

    def in_bounds(self,x,y,r=0):
        b=self.bounds
        return b['minX']+r <= x <= b['maxX']-r and b['minY']+r <= y <= b['maxY']-r

    def clear_body(self,x,y,z,r,h,step=1.2):
        if not self.in_bounds(x,y,r):
            return False
        for p in self.nearby(x-r,y-r,x+r,y+r):
            if p.top > z+step and p.base < z+h+0.1 and p.overlaps(x,y,r):
                return False
        return True

    def ground_free(self,x,y,r,h):
        return self.clear_body(x,y,self.height(x,y),r,h,step=0.15)

    def ground_segment(self,a,b,r,h,slope=50):
        n=max(1,math.ceil(distance(a,b)/2))
        old=self.height(a[0],a[1])
        stride=distance(a,b)/n
        for i in range(1,n+1):
            f=i/n
            x,y=a[0]+(b[0]-a[0])*f,a[1]+(b[1]-a[1])*f
            z=self.height(x,y)
            if abs(z-old) > max(0.2,stride*math.tan(math.radians(slope))) or not self.ground_free(x,y,r,h):
                return False
            old=z
        return True

    def support(self,x,y,feet,step,radius=0):
        z=self.height(x,y)
        for p in self.nearby(x-radius,y-radius,x+radius,y+radius):
            # A descending mech still overhanging its roof lands on the edge.
            # Keep that support until the body clears it, rather than snapping
            # to ground and incorrectly treating the roof as a wall.
            supported=p.contains(x,y) or (feet>=p.top-0.1 and p.overlaps(x,y,radius))
            if z < p.top <= feet+step and supported:
                z=p.top
        return z

    def motion(self,a,b,r,h,step=1.2,slope=50):
        # Supports roof spawns and walking off a roof, without planning jet climbs.
        n=max(1,math.ceil(distance(a,b)/1.5))
        z=a[2]
        stride=distance(a,b)/n
        for i in range(1,n+1):
            f=i/n
            x,y=a[0]+(b[0]-a[0])*f,a[1]+(b[1]-a[1])*f
            nz=self.support(x,y,z,step,r)
            if nz-z > max(step,stride*math.tan(math.radians(slope))):
                return None
            if not self.clear_body(x,y,nz,r,h,step):
                return None
            z=nz
        return (b[0],b[1],z)

    def ray_clear(self,a,b):
        for p in self.nearby(min(a[0],b[0]),min(a[1],b[1]),max(a[0],b[0]),max(a[1],b[1])):
            if p.intersects(a,b):
                return False
        n=max(1,math.ceil(distance(a,b)/3))
        for i in range(1,n):
            f=i/n
            x,y,z=(a[k]+(b[k]-a[k])*f for k in range(3))
            if z < self.height(x,y)+0.08:
                return False
        return True

    def cover_points(self,pos,radius):
        x,y=pos[:2]
        candidates=[]
        for p in self.nearby(x-65,y-65,x+65,y+65):
            a,b,c,d=p.bounds
            pad=radius+4
            for q in [(a-pad,b-pad),(a-pad,d+pad),(c+pad,b-pad),(c+pad,d+pad)]:
                if distance(pos,q)<85:
                    candidates.append(q)
        return sorted(candidates,key=lambda q:distance(pos,q))[:12]
