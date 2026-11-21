"""Regressions reproduced from the uploaded 3.77 baseline."""
import time
import unittest
from unittest.mock import patch
from test_v04 import make_bot
from test_bot import enemy, prism, laser
from combat import aim_at, center


class DecisionTests(unittest.TestCase):
    def test_hidden_weak_enemy_cannot_authorize_different_fight(self):
        b,o=make_bot([prism(20,-10,25,10)])
        o['self']['hp']=600
        visible=enemy(0,80);visible['id']=6
        o['mechs']=[enemy(50,0,100),visible]
        b.act(o)
        self.assertEqual(b.target_id,6)
        self.assertFalse(b.commit)
        self.assertEqual(b.mode,'ESCAPE')

    def test_no_shootable_target_cannot_authorize_commitment(self):
        b,o=make_bot([prism(20,-10,25,10)])
        o['self']['hp']=600;o['mechs']=[enemy(50,0,100)]
        b.act(o)
        self.assertFalse(b.commit)

    def test_empty_or_reloading_gun_cannot_authorize_finish(self):
        for reload in (0,2.4):
            with self.subTest(reload=reload):
                b,o=make_bot();o['self']['hp']=600;o['mechs']=[enemy(60,0,250)]
                o['self']['weapons'][0].update(ammo=0,reload=reload)
                b.act(o)
                self.assertFalse(b.commit)
                self.assertEqual(b.mode,'ESCAPE')

    def test_empty_lightning_adds_no_phantom_damage(self):
        b,o=make_bot();m=o['self'];m['energy']=0
        expected=b.tactics.my_dps(m,40)
        m['weapons'][1]={'kind':'lightning','cooldown':0,'stats':dict(b.config['weapons']['lightning'])}
        self.assertEqual(b.tactics.my_dps(m,40),expected)

    def test_cooldown_and_range_limit_available_damage(self):
        b,o=make_bot();m=o['self']
        self.assertEqual(b.tactics.ready_damage(m,300),0)
        m['weapons'][0]['cooldown']=3
        self.assertEqual(b.tactics.ready_damage(m,40),0)

    def test_accepted_finish_actually_fires(self):
        b,o=make_bot();m=o['self'];m['hp']=600
        e=enemy(60,0,250);o['mechs']=[e]
        m['aim']=aim_at([0,0,m['stats']['muzzle_height']],center(e))
        a=b.act(o)
        self.assertEqual(b.mode,'FIGHT')
        self.assertTrue(a['fire'][0])

    def test_two_enemy_finish_does_not_override_bad_trade(self):
        b,o=make_bot();o['self']['hp']=600
        second=enemy(0,150);second['id']=6
        o['mechs']=[enemy(60,0,450),second]
        b.act(o)
        self.assertEqual(b.mode,'ESCAPE')

    def test_target_change_does_not_inherit_commit_hysteresis(self):
        b,o=make_bot();o['self']['hp']=900;o['mechs']=[enemy(80,0,400)]
        b.tactics.evaluate(o,target=o['mechs'][0]);self.assertTrue(b.tactics.committed)
        o['self']['hp']=600;o['mechs']=[enemy(80,0,520)];o['mechs'][0]['id']=6
        b.tactics.evaluate(o,target=o['mechs'][0])
        self.assertGreater(b.tactics.ratio,1)
        self.assertFalse(b.tactics.committed)


class MovementAndDropTests(unittest.TestCase):
    def test_laser_cover_is_not_overwritten_by_juke(self):
        b,o=make_bot([prism(6,3,10,40)])
        e=enemy(60,0);e.update(weapons=['gun','laser'],charging=True)
        o['mechs']=[e];b.tactics.lead_votes=20
        with patch.object(b,'juke',side_effect=AssertionError('juke overwrote emergency')):
            a=b.act(o)
        self.assertTrue(b.dodging);self.assertGreater(a['move'][1],.3)

    def test_expired_juke_budget_keeps_existing_action(self):
        b,o=make_bot();o['projectiles']=[{'id':1,'kind':'gun','pos':[60,0,5],'vel':[-252,0,0]}]
        options=b.tactics.juke_options(o,[60,0,0],65,11.7,58.5,deadline=time.perf_counter()-1)
        self.assertEqual(options,[])

    def test_juke_prediction_uses_charge_slowdown(self):
        b,o=make_bot();e=enemy(60,0);o['self']['weapons'][1]=laser(.5)
        b.mode='FIGHT';b.tactics.lead_votes=20;b.deadline=time.perf_counter()+1
        with patch.object(b.tactics,'juke_options',return_value=[]) as choices:
            b.juke(o,e,[{'exposed':True}],{'move':[0,1],'boost':False})
        self.assertAlmostEqual(choices.call_args.args[3],b.stat(o['self'],'walk_speed',11.7)*.5)

    def test_enemy_owned_drop_rejected_even_without_visible_enemy(self):
        b,o=make_bot();o['drops']=[{'pos':[20,0,0],'holder':(b.slot+1)%16,'capture_s':4,'progress':3}]
        self.assertEqual(b.drop_points(o,[]),[])

    def test_drop_checks_fifth_threat(self):
        b,o=make_bot();o['drops']=[{'pos':[20,0,0],'holder':None}]
        threats=[{'actor':enemy(-90,90)} for _ in range(4)]+[{'actor':enemy(25,0)}]
        self.assertEqual(b.drop_points(o,threats),[])

    def test_drop_checks_zone_after_travel_and_capture(self):
        b,o=make_bot();o['drops']=[{'pos':[80,0,0],'holder':None,'capture_s':4,'lands_in':0}]
        o['zone'].update(radius=100,next_radius=20,shrink_start=o['t'],shrink_end=o['t']+15)
        self.assertEqual(b.drop_points(o,[]),[])

    def test_safe_uncontested_drop_still_available(self):
        b,o=make_bot();o['drops']=[{'pos':[20,0,0],'holder':None,'capture_s':4}]
        self.assertEqual(b.drop_points(o,[]),[(20,0)])
