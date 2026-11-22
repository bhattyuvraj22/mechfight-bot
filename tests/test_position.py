import time
import unittest
from test_v04 import make_bot
from test_bot import enemy,prism
class PositionTests(unittest.TestCase):
 def test_corner_has_isolated_shot_and_exit(self):
  b,o=make_bot([prism(6,1,10,40)])
  a=enemy(60,0);c=enemy(60,20);c['id']=6;o['mechs']=[a,c]
  b.deadline=time.perf_counter()+1
  q=b.isolated_position(o,b.threat_list(o),a)
  self.assertIsNotNone(q)
 def test_open_ground_has_no_safe_exit(self):
  b,o=make_bot();a=enemy(60,0);o['mechs']=[a]
  b.deadline=time.perf_counter()+1
  self.assertIsNone(b.isolated_position(o,b.threat_list(o),a))
 def test_expired_budget_returns_fallback(self):
  b,o=make_bot();a=enemy(60,0);o['mechs']=[a];b.deadline=time.perf_counter()-1
  self.assertIsNone(b.isolated_position(o,b.threat_list(o),a))
 def test_hurt_bot_does_not_seek_duel(self):
  b,o=make_bot([prism(6,1,10,40)]);o['self']['hp']=300
  a=enemy(60,0);c=enemy(60,20);c['id']=6;o['mechs']=[a,c]
  b.act(o);self.assertIsNone(b.duel_goal);self.assertEqual(b.mode,'ESCAPE')
