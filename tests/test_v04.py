"""Tests for v0.4: adaptive lead, laser dodging, kill chasing, sound facing."""
import math, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_bot import fixture, toy_world, prism, enemy, gun  # noqa: E402
from bot import Bot  # noqa: E402
from combat import Combat, LEAD_OPTIONS  # noqa: E402
from navigation import Navigator  # noqa: E402


def make_bot(prisms=()):
    hello, obs = fixture()
    bot = Bot(hello)
    bot.world = toy_world(list(prisms))
    bot.nav = Navigator(bot.world)
    bot.combat = Combat(bot.world)
    obs['self']['pos'] = [0, 0, 0]
    obs['self']['vel'] = [0, 0, 0]
    obs['self']['weapons'] = [gun(), None]
    obs['zone'].update(center=[0, 0], next_center=[0, 0], radius=90, next_radius=80)
    obs['events'] = []; obs['sounds'] = []; obs['beams'] = []; obs['projectiles'] = []
    return bot, obs


class LeadTests(unittest.TestCase):
    def test_hits_are_credited_to_the_option_that_fired(self):
        c = Combat(toy_world([]))
        c.pending.append((10.0, 5, 2))
        c.observe({'t': 10.1, 'events': [{'type': 'hit', 'target': 5, 'weapon': 'gun', 'amount': 45}]})
        self.assertGreater(c.lead_stats[2][0], 1.0)
        self.assertFalse(c.pending)

    def test_unhit_shots_count_as_misses(self):
        c = Combat(toy_world([]))
        c.pending.append((10.0, 5, 0))
        before = c.lead_stats[0][1]
        c.observe({'t': 11.0, 'events': []})
        self.assertGreater(c.lead_stats[0][1], before)

    def test_learns_best_lead(self):
        c = Combat(toy_world([]))
        c.lead_stats = [[1, 30], [1, 30], [25, 5]]
        picks = []
        for k in range(20):
            c.lead_until = -1
            picks.append(c.pick_lead(k))
        self.assertGreater(picks.count(2), 16)
        self.assertEqual(len(LEAD_OPTIONS), 3)


class LaserDodgeTests(unittest.TestCase):
    def test_steps_behind_wall_when_charger_aims_at_us(self):
        # Wall from x=6..10 covering y>=3: stepping north hides us from x=+60.
        bot, obs = make_bot([prism(6, 3, 10, 40)])
        foe = enemy(60, 0); foe['weapons'] = ['gun', 'laser']; foe['charging'] = True
        foe['aim'] = [math.pi, 0]
        obs['mechs'] = [foe]
        a = bot.act(obs)
        self.assertTrue(bot.dodging)
        self.assertGreater(a['move'][1], 0.3)

    def test_no_dodge_when_not_aimed_at_us(self):
        bot, obs = make_bot([prism(6, 3, 10, 40)])
        foe = enemy(60, 0); foe['weapons'] = ['gun', 'laser']; foe['charging'] = True
        foe['aim'] = [math.pi / 2, 0]
        obs['mechs'] = [foe]
        bot.act(obs)
        self.assertFalse(bot.dodging)


class ChaseTests(unittest.TestCase):
    def test_chases_wounded_target_behind_wall(self):
        bot, obs = make_bot([prism(20, -10, 25, 10)])
        bot.target_id = 5
        obs['mechs'] = [enemy(50, 0, hp=300)]
        bot.act(obs)
        self.assertEqual(bot.mode, 'CHASE')

    def test_does_not_chase_healthy_target(self):
        bot, obs = make_bot([prism(20, -10, 25, 10)])
        bot.target_id = 5
        obs['mechs'] = [enemy(50, 0, hp=1300)]
        bot.act(obs)
        self.assertNotEqual(bot.mode, 'CHASE')

    def test_finishes_weak_target_even_when_hurt(self):
        bot, obs = make_bot()
        obs['self']['hp'] = 600
        obs['mechs'] = [enemy(60, 0, hp=250)]
        bot.act(obs)
        self.assertEqual(bot.mode, 'FIGHT')


class SoundTests(unittest.TestCase):
    def test_faces_nearby_footsteps(self):
        bot, obs = make_bot()
        obs['mechs'] = []
        obs['sounds'] = [{'kind': 'step', 'bearing': 2.0, 'dist': 'near', 'age': 0.1}]
        a = bot.act(obs)
        self.assertAlmostEqual(a['aim'][0], 2.0, places=2)


if __name__ == '__main__':
    unittest.main()
