import unittest
from test_v04 import make_bot
from test_bot import enemy
class IsolationTests(unittest.TestCase):
 def test_group_retreat(self):
  b,o=make_bot();a=enemy(60,0);c=enemy(60,30);c['id']=6;o['mechs']=[a,c]
  b.act(o);self.assertEqual(b.mode,'ESCAPE')
 def test_tiny_finish(self):
  b,o=make_bot();a=enemy(40,0,40);c=enemy(60,30);c['id']=6;o['mechs']=[a,c]
  b.act(o);self.assertEqual(b.mode,'FIGHT')
 def test_empty_gun_no_finish(self):
  b,o=make_bot();a=enemy(40,0,40);c=enemy(60,30);c['id']=6;o['mechs']=[a,c];o['self']['weapons'][0]['ammo']=0
  b.act(o);self.assertEqual(b.mode,'ESCAPE')
