import unittest
from test_v04 import make_bot
from test_bot import enemy
class SpacingRecoveryTests(unittest.TestCase):
 def test_lightning_enemy_not_chased_to_40(self):
  b,o=make_bot();e=enemy(60,0,200);e['weapons']=['lightning']
  self.assertGreaterEqual(b.preferred_range(o['self'],e),64)
 def test_mortar_enemy_spacing(self):
  b,o=make_bot();e=enemy(60,0,200);e['weapons']=['mortar']
  self.assertGreaterEqual(b.preferred_range(o['self'],e),80)
 def test_npc_distance(self):
  b,o=make_bot();e=enemy();e['kind']='npc'
  self.assertEqual(b.preferred_range(o['self'],e),58)
 def test_cover_hold_survives_lost_contact_then_expires(self):
  b,o=make_bot();a=enemy(60,0);c=enemy(60,30);c['id']=6;o['mechs']=[a,c]
  b.act(o);self.assertEqual(b.mode,'ESCAPE')
  o['t']+=.1;o['tick']+=2;o['mechs']=[]
  b.act(o);self.assertEqual(b.mode,'HEAL')
  o['t']+=3;o['tick']+=60
  b.act(o);self.assertEqual(b.mode,'COLLECT')
 def test_zone_wins_over_hold(self):
  b,o=make_bot();b.cover_hold_until=o['t']+10;o['self']['in_zone']=False
  b.act(o);self.assertEqual(b.mode,'ROTATE')
