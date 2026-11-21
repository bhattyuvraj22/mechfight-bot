"""Unit tests for tactics.py (v0.3). Run: python3 -m unittest discover -s tests"""
import math, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tactics import Tactics, pick_upgrade, weapon_dps  # noqa: E402

CONFIG = {
    'cubes': {'damage_per_cube': 0.04, 'stat_cap': 10},
    'weapons': {
        'gun': {'damage': 45, 'cooldown': 0.24, 'speed': 252, 'range': 230, 'mag': 12, 'reload': 2.4},
        'laser': {'damage': 315, 'charge': 0.75, 'cooldown': 1.65, 'range': 280},
        'lightning': {'damage': 60, 'cooldown': 0.25, 'range': 45},
        'mortar': {'damage': 200, 'splash': 160, 'cooldown': 2.6, 'gravity': 22},
    },
}
GUN = {'kind': 'gun', 'cooldown': 0, 'ammo': 12, 'reload': 0, 'stats': dict(CONFIG['weapons']['gun'])}


def me(hp=1400, pos=(0, 0, 0)):
    return {'pos': list(pos), 'vel': [0, 0, 0], 'hp': hp, 'max_hp': 1400, 'cubes': 0,
            'weapons': [dict(GUN), None], 'stats': {'radius': 2.5, 'height': 9, 'armor': 0}}


def foe(x, hp=1400, i=5, weapons=('gun',)):
    return {'id': i, 'kind': 'mech', 'pos': [x, 0, 0], 'vel': [0, 0, 0], 'hp': hp,
            'max_hp': 1400, 'cubes': 0, 'weapons': list(weapons)}


class UpgradeTests(unittest.TestCase):
    def test_nanites_over_rate_and_sensors(self):   # matches test_bot expectation
        offer = {'choices': [{'id': 'gun_rate'}, {'id': 'nanites'}, {'id': 'sensors'}]}
        self.assertEqual(pick_upgrade(offer, ['gun']), 1)

    def test_drum_mag_preferred_over_rate(self):
        offer = {'choices': [{'id': 'gun_rate'}, {'id': 'sensors'}, {'id': 'gun_mag'}]}
        self.assertEqual(pick_upgrade(offer, ['gun']), 2)

    def test_plating_beats_utility(self):
        offer = {'choices': [{'id': 'servos'}, {'id': 'plating'}, {'id': 'jets'}]}
        self.assertEqual(pick_upgrade(offer), 1)

    def test_unknown_ids_never_crash(self):
        self.assertEqual(pick_upgrade({'choices': [{'id': 'zzz'}, {'id': 'yyy'}]}), 0)
        self.assertIsNone(pick_upgrade(None))

    def test_gun_dps_matches_rules(self):
        # 12 rounds x 45 over 12*0.24 + 2.4 s
        self.assertAlmostEqual(weapon_dps('gun', CONFIG['weapons']['gun']), 540 / 5.28, places=3)


class EngagementTests(unittest.TestCase):
    def setUp(self):
        self.t = Tactics(CONFIG, 7)

    def obs(self, my_hp, mechs, t=10):
        return {'t': t, 'self': me(my_hp), 'mechs': mechs, 'events': [], 'projectiles': []}

    def test_commits_against_weak_lone_enemy_even_when_hurt(self):
        self.t.evaluate(self.obs(600, [foe(80, hp=300)]))
        self.assertTrue(self.t.committed)

    def test_does_not_commit_against_fresh_enemy_when_hurt(self):
        self.t.evaluate(self.obs(600, [foe(80, hp=1400)]))
        self.assertFalse(self.t.committed)

    def test_never_commits_into_a_crowd(self):
        crowd = [foe(80, hp=100, i=i) for i in range(3)]
        self.t.evaluate(self.obs(1400, crowd))
        self.assertFalse(self.t.committed)

    def test_hysteresis_keeps_commitment(self):
        self.t.evaluate(self.obs(900, [foe(80, hp=400)]))
        self.assertTrue(self.t.committed)
        r = self.t.evaluate(self.obs(700, [foe(80, hp=520)]))
        self.assertTrue(1.0 <= r < 1.3 or self.t.committed)

    def test_npcs_ignored_for_commitment(self):
        o = self.obs(600, [dict(foe(40, hp=50), kind='npc')])
        self.t.evaluate(o)
        self.assertFalse(self.t.committed)

    def test_attacker_memory(self):
        o = self.obs(1400, [])
        o['events'] = [{'type': 'damaged', 'by': 9, 'amount': 45, 'bearing': 0}]
        self.t.note_events(o)
        self.assertTrue(self.t.recent_attacker(9, 11))
        self.assertFalse(self.t.recent_attacker(9, 14))

    def test_npc_reach(self):
        self.assertEqual(self.t.npc_reach(self.obs(1400, [])), 115)
        self.assertEqual(self.t.npc_reach(self.obs(1400, [foe(150)])), 60)
        self.assertEqual(self.t.npc_reach(self.obs(900, [])), 60)
        self.assertEqual(self.t.npc_reach(self.obs(1400, [], t=300)), 60)

    def test_kill_hp_scales_with_cubes(self):
        m = me(); base = self.t.kill_hp(m); m['cubes'] = 10
        self.assertGreater(self.t.kill_hp(m), base)


class JukeTests(unittest.TestCase):
    def setUp(self):
        self.t = Tactics(CONFIG, 3)

    def obs(self, t=1, vel=(0, 0, 0), projectiles=()):
        m = me(); m['vel'] = list(vel)
        return {'t': t, 'self': m, 'projectiles': list(projectiles)}

    def test_unit_length_and_holds_range(self):
        v = self.t.juke_options(self.obs(), [85, 0, 0], 85, 11.7, 58.5)[0]
        self.assertAlmostEqual(math.hypot(*v), 1, places=6)
        self.assertGreater(abs(v[1]), 0.5)               # mostly across the line of fire

    def test_closes_when_far_opens_when_near(self):
        far = self.t.juke_options(self.obs(), [160, 0, 0], 85, 11.7, 58.5)[0]
        self.t.until = -1
        near = self.t.juke_options(self.obs(), [30, 0, 0], 85, 11.7, 58.5)[0]
        self.assertGreater(far[0], 0.2)
        self.assertLess(near[0], -0.2)

    def test_new_heading_turns_away_from_current_velocity(self):
        for k in range(40):
            o = self.obs(t=k, vel=(0, 11.7, 0))
            self.t.until = -1
            v = self.t.juke_options(o, [85, 0, 0], 85, 11.7, 58.5)[0]
            turn = abs(math.atan2(v[1], v[0]) - math.pi / 2)
            self.assertGreaterEqual(min(turn, 2 * math.pi - turn) + 1e-9, self.t.TURN_MIN)

    def test_steers_away_from_incoming_bullet(self):
        bullet = {'id': 1, 'kind': 'gun', 'pos': [60, 3, 5], 'vel': [-252, 0, 0]}
        self.t.heading = math.pi / 2; self.t.until = 99      # currently heading north
        best = self.t.juke_options(self.obs(projectiles=[bullet]), [85, 0, 0], 85, 11.7, 58.5)[0]
        self.assertLess(best[1], 0)


class AimProfileTests(unittest.TestCase):
    def test_leading_bullets_enable_juke(self):
        t = Tactics(CONFIG, 1)
        for i in range(4):   # we move north at 11.7; bullet aimed at where we will be
            o = {'self': dict(me(), vel=[0, 11.7, 0]), 'projectiles': [
                {'id': i, 'kind': 'gun', 'pos': [100, 0, 5], 'vel': [-252, 11.7 * 252 / 100, 0]}]}
            t.observe_shots(o)
        self.assertTrue(t.should_juke())

    def test_head_on_bullets_keep_strafe(self):
        t = Tactics(CONFIG, 1)
        for i in range(4):
            o = {'self': dict(me(), vel=[0, 11.7, 0]), 'projectiles': [
                {'id': i, 'kind': 'gun', 'pos': [100, 0, 5], 'vel': [-252, 0, 0]}]}
            t.observe_shots(o)
        self.assertFalse(t.should_juke())

    def test_standing_still_teaches_nothing(self):
        t = Tactics(CONFIG, 1)
        t.observe_shots({'self': me(), 'projectiles': [
            {'id': 1, 'kind': 'gun', 'pos': [100, 0, 5], 'vel': [-252, 0, 0]}]})
        self.assertEqual(t.lead_votes + t.headon_votes, 0)


if __name__ == '__main__':
    unittest.main()
