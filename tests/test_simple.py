"""Two baseline fixes, using the actual protocol weapon stats."""
import unittest
from test_v04 import make_bot
from test_bot import enemy, prism
from combat import aim_at, center


def scene(walls=()):
    b,o=make_bot(walls)
    o['self']['weapons'][0]['stats']=dict(b.config['weapons']['gun'])
    return b,o


class SimpleStrategyTests(unittest.TestCase):
    def test_weak_hidden_enemy_does_not_justify_different_target(self):
        b,o=scene([prism(20,-10,25,10)])
        o['self']['hp']=600
        other=enemy(0,80);other['id']=6
        o['mechs']=[enemy(50,0,100),other]
        b.act(o)
        self.assertEqual(b.target_id,6)
        self.assertFalse(b.commit)
        self.assertEqual(b.mode,'ESCAPE')

    def test_no_shootable_target_does_not_commit(self):
        b,o=scene([prism(20,-10,25,10)])
        o['self']['hp']=600;o['mechs']=[enemy(50,0,100)]
        b.act(o);self.assertFalse(b.commit)

    def test_baseline_finish_threshold_preserved_and_fires(self):
        b,o=scene();o['self']['hp']=600
        target=enemy(60,0,450);other=enemy(0,150);other['id']=6
        o['mechs']=[target,other]
        o['self']['aim']=aim_at([0,0,o['self']['stats']['muzzle_height']],center(target))
        a=b.act(o)
        self.assertFalse(b.commit)
        self.assertTrue(b.healing)
        self.assertEqual(b.mode,'FIGHT')
        self.assertTrue(a['fire'][0])

    def test_winning_lone_fight_stays_aggressive(self):
        b,o=scene();o['self']['hp']=600;o['mechs']=[enemy(60,0,250)]
        b.act(o);self.assertTrue(b.commit);self.assertEqual(b.mode,'FIGHT')

    def test_heal_without_threat_still_holds_fire(self):
        b,o=scene();b.mode='HEAL';b.healing=True;b.now=o['t']
        self.assertFalse(b.should_fire(o,enemy(80,0,1400)))
