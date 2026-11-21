"""Oval Sentinel v0.3 tactics: pure helpers with no world/navigation imports.

Practice score = number of house bots that die before us (they never fight
each other), so every kill is a full point. These helpers exist to
(1) stay in fights we will win instead of fleeing them, (2) be hard to hit
while fighting, (3) grow stronger early (drones, drops, sane upgrades).
"""
import math
import random
import time


def _clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def _dist2(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _unit(x, y):
    n = math.hypot(x, y)
    return (x / n, y / n) if n > 1e-9 else (0.0, 0.0)


# Gun math (12 rounds / 0.24 s, 2.4 s reload): drum magazine is worth ~+31%
# sustained DPS, far more than rotary feed (~+8%). Plating is +15% EHP.
# Nanites stay high because the bot still disengages to regenerate.
UPGRADE_PRIORITY = [
    'gun_mag', 'plating', 'armor', 'nanites', 'gun_damage', 'lightning_efficiency',
    'laser_damage', 'laser_charge', 'servos', 'gun_rate', 'gun_velocity',
    'lightning_range', 'jets', 'reactor', 'gyros', 'capacitor', 'lightning_chain',
    'sensors', 'laser_pierce', 'mortar_reload', 'mortar_velocity', 'mortar_splash',
]
# Sounds that mean "a mech is here and probably coming for us".
THREAT_SOUNDS = {'step': 3.0, 'boost': 2.5, 'laser_charge': 3.0, 'gun': 1.5,
                 'lightning': 2.0, 'laser': 1.5, 'jet': 1.5, 'reload': 2.0}


def pick_upgrade(offer, held_kinds=()):
    choices = (offer or {}).get('choices') or []
    if not choices:
        return None
    order = list(UPGRADE_PRIORITY)
    if 'lightning' in held_kinds:  # lightning is energy-limited; fix that early
        for i, cid in enumerate(('lightning_efficiency', 'reactor', 'capacitor')):
            order.remove(cid)
            order.insert(1 + i, cid)

    def rank(i):
        cid = choices[i].get('id')
        return order.index(cid) if cid in order else len(order)
    return min(range(len(choices)), key=rank)


def hit_prob(kind, dist, rng=45):
    if kind == 'gun':
        return _clamp(1.0 - dist / 260.0, 0.2, 0.9)
    if kind == 'laser':
        return _clamp(0.95 - dist / 600.0, 0.4, 0.9) if dist <= 280 else 0.0
    if kind == 'lightning':
        return 1.0 if dist <= rng else 0.0
    if kind == 'mortar':
        return _clamp(0.6 - dist / 400.0, 0.1, 0.5) if dist > 25 else 0.1
    return 0.0


def weapon_dps(kind, s):
    """Sustained DPS of one weapon from its stats dict (before cube scaling)."""
    try:
        if kind == 'gun':
            cycle = s['mag'] * s['cooldown']
            return s['damage'] / s['cooldown'] * cycle / (cycle + s['reload'])
        if kind == 'laser':
            return s['damage'] / (s['charge'] + s['cooldown'])
        if kind == 'lightning':
            return s['damage'] / s['cooldown']
        if kind == 'mortar':
            return (0.5 * s['damage'] + 0.5 * s['splash']) / s['cooldown']
    except (KeyError, TypeError, ZeroDivisionError):
        pass
    return 0.0


class Tactics:
    JUKE_MIN, JUKE_MAX, TURN_MIN = 0.25, 0.6, math.radians(50)
    def __init__(self, config, seed=0):
        self.config = config or {}
        self.rng = random.Random((seed or 0) ^ 0x5EED)
        self.heading = None
        self.until = -1.0
        self.attackers = {}
        self.seen_shots = set()
        self.lead_votes = 0.0     # bullets aimed where we were going
        self.headon_votes = 0.0   # bullets aimed where we were
        self.committed = False
        self.ratio = 0.0
        self.commit_target = None
        self.last_beam = {}       # enemy id -> time its laser last fired
        self.heard = []           # (t, bearing, weight)

    # ---------------------------------------------------------------- memory
    def note_events(self, obs):
        now = obs.get('t', 0)
        for e in obs.get('events', []) or []:
            if e.get('type') == 'damaged' and e.get('by') is not None:
                self.attackers[e['by']] = now
                if e.get('weapon') == 'laser':
                    self.last_beam[e['by']] = now
        for b in obs.get('beams', []) or []:
            if b.get('kind') == 'laser' and b.get('by') is not None:
                self.last_beam[b['by']] = now - b.get('age', 0)
        for snd in obs.get('sounds', []) or []:
            w = THREAT_SOUNDS.get(snd.get('kind'))
            if w and snd.get('dist') in ('near', 'mid') and snd.get('bearing') is not None:
                if snd.get('dist') == 'near':
                    w *= 2
                self.heard.append((now - snd.get('age', 0), snd['bearing'], w))
        self.heard = [h for h in self.heard if now - h[0] < 2.0][-24:]

    def threat_bearing(self, now):
        """Weighted mean bearing of recent threatening sounds, or None."""
        sx = sy = 0.0
        for t, b, w in self.heard:
            k = w * max(0.0, 1 - (now - t) / 2.0)
            sx += k * math.cos(b)
            sy += k * math.sin(b)
        if math.hypot(sx, sy) < 1.5:
            return None
        return math.atan2(sy, sx)

    def laser_ready(self, enemy, now):
        """Could this enemy fire a laser at us in the next ~0.8 s?"""
        if 'laser' not in (enemy.get('weapons') or []):
            return False
        if enemy.get('charging'):
            return True
        cd = self.config.get('weapons', {}).get('laser', {}).get('cooldown', 1.65)
        return now - self.last_beam.get(enemy['id'], -100) > cd - 0.3

    def laser_threats(self, obs):
        """Visible enemies charging a laser with their torso pointed at us."""
        me = obs['self']
        out = []
        for m in obs.get('mechs', []) or []:
            if m.get('kind') != 'mech' or not m.get('charging'):
                continue
            d = _dist2(me['pos'], m['pos'])
            if d > 300:
                continue
            bearing = math.atan2(me['pos'][1] - m['pos'][1], me['pos'][0] - m['pos'][0])
            off = abs((m['aim'][0] - bearing + math.pi) % (2 * math.pi) - math.pi)
            # They slew at 4 rad/s, so anything within ~35 deg is on us by release.
            if off < math.radians(35):
                out.append(m)
        return out

    def recent_attacker(self, mech_id, now, window=2.5):
        return now - self.attackers.get(mech_id, -100) < window

    # ----------------------------------------------------------- engagements
    def cube_mult(self, cubes):
        c = self.config.get('cubes', {})
        return 1 + c.get('damage_per_cube', 0.04) * min(cubes or 0, c.get('stat_cap', 10))

    def ready_damage(self, me, dist, horizon=2.0, reserve=8):
        """Conservative damage available before a short engagement ends.

        Do not borrow future energy regeneration or a fresh magazine from beyond
        the horizon. Opponent readiness is unobserved; enemy_dps stays separate.
        """
        total = 0.0
        for w in me.get('weapons') or []:
            if not w:
                continue
            kind = w['kind']
            s = dict(self.config.get('weapons', {}).get(kind, {}))
            s.update(w.get('stats') or {})
            if dist > s.get('range', 0):
                continue
            cd = max(0.01, s.get('cooldown', 1))
            delay = max(0.0, w.get('cooldown', 0))
            if kind == 'gun':
                delay = max(delay, w.get('reload', 0))
                delay += dist / max(1, s.get('speed', 252))
                ammo = s.get('mag', 0) if w.get('reload', 0) > 0 else w.get('ammo', 0)
                shots = min(ammo, max(0, math.ceil((horizon-delay)/cd)))
            elif kind == 'laser':
                delay += max(0, s.get('charge', .75)-w.get('charge', 0))
                shots = max(0, math.ceil((horizon-delay)/(cd+s.get('charge', .75))))
            elif kind == 'lightning':
                shots = min(max(0, math.ceil((horizon-delay)/cd)),
                            int(max(0, me.get('energy', 0)-reserve)/max(.01, s.get('energy', 3))))
            else:
                continue  # command() does not yet aim or fire mortars
            total += shots*s.get('damage', 0)*hit_prob(kind, dist, s.get('range', 45))
        return total*self.cube_mult(me.get('cubes', 0))

    def my_dps(self, me, dist):
        total = 0.0
        for w in me.get('weapons') or []:
            if not w or w['kind'] == 'mortar':
                continue
            s = dict(self.config.get('weapons', {}).get(w['kind'], {}))
            s.update(w.get('stats') or {})
            if dist <= s.get('range', 0):
                sustained = weapon_dps(w['kind'], s)*hit_prob(w['kind'], dist, s.get('range', 45))*self.cube_mult(me.get('cubes', 0))
                total += min(sustained, self.ready_damage(dict(me, weapons=[w]), dist)/2)
        return total

    def enemy_dps(self, e, dist):
        base = self.config.get('weapons', {})
        total = 0.0
        for kind in e.get('weapons') or ['gun']:
            s = base.get(kind) or {}
            total += weapon_dps(kind, s) * hit_prob(kind, dist, s.get('range', 45))
        return total * self.cube_mult(e.get('cubes', 0))

    def evaluate(self, obs, radius=170, target=None):
        """Evaluate the selected, shootable target; never borrow another kill."""
        me = obs['self']
        foes = [m for m in obs.get('mechs', []) if m.get('kind') == 'mech'
                and _dist2(me['pos'], m['pos']) < radius]
        # Standalone callers may omit target; the bot always supplies its choice.
        if target is None and foes:
            target = min(foes, key=lambda m: m.get('hp', 1400))
        tid = target.get('id') if target else None
        keep = self.committed and tid == self.commit_target
        self.commit_target = tid
        self.ratio = 0.0
        if target and target.get('kind') == 'mech' and len(foes) <= 2 and target in foes:
            armor = _clamp((me.get('stats') or {}).get('armor', 0), 0, .9)
            incoming = sum(self.enemy_dps(m, _dist2(me['pos'], m['pos'])) for m in foes)*(1-armor)
            out = self.my_dps(me, _dist2(me['pos'], target['pos']))
            if out > 0:
                self.ratio = (me['hp']/max(1, incoming))/(max(1, target.get('hp', 1400))/out)
        self.committed = self.ratio >= (1.0 if keep else 1.3)
        return self.ratio

    def kill_hp(self, me):
        """Enemy HP we can finish in roughly 1.5 s of gun fire."""
        gun = next((w for w in me.get('weapons') or [] if w and w['kind'] == 'gun'), None)
        dmg = (gun or {}).get('stats', {}).get('damage', 45)
        return max(220.0, 6 * dmg * self.cube_mult(me.get('cubes', 0)))

    def npc_reach(self, obs):
        """Hunt drones further away early on, when no mech is around."""
        me = obs['self']
        if obs.get('t', 0) > 210 or me['hp'] < 0.75 * me['max_hp']:
            return 60
        if any(m.get('kind') == 'mech' and _dist2(me['pos'], m['pos']) < 220
               for m in obs.get('mechs', [])):
            return 60
        return 115

    # -------------------------------------------------------- aim profiling
    def observe_shots(self, obs):
        """Classify each newly seen enemy bullet as lead-aimed or head-on.

        Lead-aimed fire is beaten by frequent random heading changes (juke);
        head-on fire is beaten by simply moving fast in one direction, which
        the existing fight movement already does. Votes decay so the profile
        follows whoever is shooting at us now.
        """
        me = obs['self']
        px, py = me['pos'][:2]
        vx, vy = me.get('vel', [0, 0, 0])[:2]
        if math.hypot(vx, vy) < 4:
            return
        for p in obs.get('projectiles') or []:
            if p.get('kind') != 'gun' or p.get('id') in self.seen_shots:
                continue
            self.seen_shots.add(p.get('id'))
            (bx, by), (wx, wy) = p['pos'][:2], p['vel'][:2]
            rx, ry = bx - px, by - py
            ww = wx * wx + wy * wy
            if ww < 1e-6:
                continue
            t_still = -(rx * wx + ry * wy) / ww
            if t_still < 0.12:      # already passing or too late to tell
                continue
            miss_still = math.hypot(rx + wx * t_still, ry + wy * t_still)
            ux, uy = wx - vx, wy - vy
            uu = ux * ux + uy * uy
            t_move = max(0.0, -(rx * ux + ry * uy) / uu)
            miss_move = math.hypot(rx + ux * t_move, ry + uy * t_move)
            if min(miss_still, miss_move) > 8 or abs(miss_still - miss_move) < 1.0:
                continue            # not aimed at us, or ambiguous
            self.lead_votes *= 0.9
            self.headon_votes *= 0.9
            if miss_move < miss_still:
                self.lead_votes += 1
            else:
                self.headon_votes += 1
        if len(self.seen_shots) > 4000:
            self.seen_shots.clear()

    def should_juke(self):
        """Juke only once enemy fire has been seen leading us."""
        return self.lead_votes >= 2 and self.lead_votes > 1.5 * self.headon_votes

    # ------------------------------------------------------------- dodging
    def _danger(self, me, direction, speed, accel, projectiles, horizon=0.8, dt=0.05):
        """Expected damage from visible enemy projectiles if we steer `direction`."""
        if not projectiles:
            return 0.0
        g = self.config.get('weapons', {}).get('mortar', {}).get('gravity', 22)
        r = (me.get('stats') or {}).get('radius', 2.5) + 0.6
        h = (me.get('stats') or {}).get('height', 9)
        px, py, pz = me['pos']
        vx, vy = me.get('vel', [0, 0, 0])[:2]
        tx, ty = direction[0] * speed, direction[1] * speed
        hits = 0.0
        path = []  # (t0, x0, y0, vx, vy) per step: our own piecewise-linear motion
        t = 0.0
        while t < horizon:
            ax, ay = tx - vx, ty - vy
            n = math.hypot(ax, ay)
            if n > accel * dt:
                ax, ay = ax / n * accel * dt, ay / n * accel * dt
            vx, vy = vx + ax, vy + ay
            path.append((t, px, py, vx, vy))
            px, py = px + vx * dt, py + vy * dt
            t += dt
        for p in projectiles:
            kind = p.get('kind')
            weight = 200 if kind == 'mortar' else 45 if kind == 'gun' else 25
            reach = r + (5.0 if kind == 'mortar' else 0.0)  # mortar splash
            (bx, by, bz), (bvx, bvy, bvz) = p['pos'], p['vel']
            for t0, mx, my, mvx, mvy in path:
                # Swept test: a 252 m/s bullet moves 12.6 m per step, so
                # point sampling would let it tunnel straight past us.
                rx, ry = bx + bvx * t0 - mx, by + bvy * t0 - my
                wx, wy = bvx - mvx, bvy - mvy
                ww = wx * wx + wy * wy
                s = _clamp(-(rx * wx + ry * wy) / ww, 0.0, dt) if ww > 1e-9 else 0.0
                if math.hypot(rx + wx * s, ry + wy * s) >= reach:
                    continue
                tt = t0 + s
                qz = bz + bvz * tt - (0.5 * g * tt * tt if kind == 'mortar' else 0.0)
                if pz - 1 <= qz <= pz + h + 1:
                    hits += weight
                    break
        return hits

    def juke_options(self, obs, target_pos, preferred, speed, accel, deadline=float("inf")):
        """Ordered move directions for an exposed fight, best first.

        Linear-lead aim assumes our velocity holds until the bullet lands.
        Re-picking a random heading every JUKE_MIN..JUKE_MAX s, at full speed,
        at least TURN_MIN away from where we are already heading, breaks that
        prediction quickly (a slow full reversal does not: it costs 0.4 s of
        near-zero speed). Headings are biased to hold `preferred` range, and
        visible bullets/shells re-rank them every tick.
        """
        me = obs['self']
        now = obs.get('t', 0)
        pos = me['pos']
        dist = _dist2(pos, target_pos)
        bearing = math.atan2(target_pos[1] - pos[1], target_pos[0] - pos[0])
        # Relative angles to the line of sight. 90 = pure strafe; <90 closes.
        # Moving tangentially always widens range, so the neutral band leans in.
        if dist > preferred + 8:
            rel = (30, 45, 60, 75)
        elif dist < preferred - 8:
            rel = (105, 120, 135, 150)
        else:
            rel = (50, 65, 80, 95, 110)
        candidates = [bearing + math.radians(a) * s for a in rel for s in (1, -1)]
        vx, vy = me.get('vel', [0, 0, 0])[:2]
        moving = math.hypot(vx, vy) > 3
        heading_now = math.atan2(vy, vx)
        if now >= self.until or self.heading is None:
            pool = [c for c in candidates if not moving or
                    abs((c - heading_now + math.pi) % (2 * math.pi) - math.pi) >= self.TURN_MIN]
            self.heading = self.rng.choice(pool or candidates)
            self.until = now + self.rng.uniform(self.JUKE_MIN, self.JUKE_MAX)
        opts = [self.heading] + sorted(candidates, key=lambda c: abs((c - self.heading + math.pi) % (2 * math.pi) - math.pi))
        opts = [(math.cos(a), math.sin(a)) for a in opts]
        projectiles = obs.get('projectiles') or []
        if len(projectiles) > 30:  # bound the per-tick cost
            projectiles = sorted(projectiles, key=lambda q: _dist2(pos, q['pos']))[:30]
        if projectiles:
            danger = []
            for i, o in enumerate(opts):
                if time.perf_counter() >= deadline:
                    break
                danger.append((self._danger(me, o, speed, accel, projectiles), i, o))
            if not danger:
                return []  # keep the already validated steer action
            danger.sort()
            if danger[0][0] < danger[[d[1] for d in danger].index(0)][0]:
                best = danger[0][2]
                self.heading = math.atan2(best[1], best[0])
            opts = [d[2] for d in danger]
        return opts

    def flip(self, now):
        """Current heading is blocked: re-pick on the next call."""
        self.until = now
