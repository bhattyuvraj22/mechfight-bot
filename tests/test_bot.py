import array
import copy
import gzip
import json
import math
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from bot import Bot
from combat import Combat, aim_at, center, intercept
from geometry import World, distance
from navigation import Navigator


def prism(x0,y0,x1,y1,base=0,top=20,holes=None):
    return {'base':base,'top':top,'ring':[x0,y0,x1,y0,x1,y1,x0,y1],
            'holes':holes or [],'kind':'building'}


def toy_world(prisms):
    directory=tempfile.TemporaryDirectory()
    p=Path(directory.name)/'v2'
    p.mkdir()
    data={'bounds':{'minX':-100,'minY':-100,'maxX':100,'maxY':100},
          'terrain':{'minX':-100,'minY':-100,'step':1,'nx':201,'ny':201,'scale':0.01},
          'prisms':prisms}
    (p/'world.json').write_text(json.dumps(data))
    (p/'terrain.i16').write_bytes(array.array('h',[0]*(201*201)).tobytes())
    world=World(directory.name)
    directory.cleanup()  # World eagerly loaded the bytes; tests need no live files.
    return world


def fixture():
    with gzip.open(ROOT/'check/stream.jsonl.gz','rt') as f:
        rows=[json.loads(line) for line in f]
    hello,obs=copy.deepcopy(rows[0]),copy.deepcopy(rows[1])
    hello['map']['dir']=str(ROOT/'arena')
    return hello,obs


def enemy(x=35,y=0,hp=1400):
    return {'id':5,'kind':'mech','pos':[x,y,0],'vel':[0,0,0],
            'hp':hp,'max_hp':1400,'weapons':['gun'],'aim':[math.pi,0],'cubes':0}


def gun():
    return {'kind':'gun','cooldown':0,'ammo':12,'reload':0,
            'stats':{'damage':45,'cooldown':0.24,'speed':252,'range':230,'mag':12}}


def laser(charge=0):
    return {'kind':'laser','cooldown':0,'charge':charge,
            'stats':{'charge':0.75,'range':280,'hold_s':2,'damage':315}}


def drop_at(x=20,y=0,holder=None,progress=0):
    return {'id':20000,'pos':[x,y,0],'radius':8,'lands_in':0,
            'capture_s':4,'progress':progress,'holder':holder}


class GeometryTests(unittest.TestCase):
    def test_wall_blocks_shots_but_not_over_roof(self):
        w=toy_world([prism(0,-8,1,8)])
        self.assertFalse(w.ray_clear([-10,0,7],[10,0,7]))
        self.assertTrue(w.ray_clear([-10,0,21],[10,0,21]))

    def test_thin_wall_cannot_be_skipped_by_sampling(self):
        w=toy_world([prism(0.01,-8,0.02,8)])
        self.assertFalse(w.ray_clear([-10,0,7],[10,0,7]))

    def test_holes_are_empty(self):
        w=toy_world([prism(-20,-20,20,20,holes=[[-10,-10,10,-10,10,10,-10,10]])])
        self.assertTrue(w.ground_free(0,0,2.5,9))
        self.assertTrue(w.ray_clear([-5,0,7],[5,0,7]))
        self.assertFalse(w.ray_clear([0,0,7],[25,0,7]))

    def test_bridge_clearance_changes_with_body_size(self):
        w=toy_world([prism(-10,-10,10,10,base=12,top=14)])
        self.assertTrue(w.ground_free(0,0,2.5,9))
        self.assertFalse(w.ground_free(0,0,4,13))
        self.assertTrue(w.ray_clear([-20,0,7],[20,0,7]))
        self.assertFalse(w.ray_clear([-20,0,13],[20,0,13]))

    def test_body_cannot_clip_building_corner(self):
        w=toy_world([prism(0,0,20,20)])
        self.assertFalse(w.ground_free(-1,-1,2.5,9))
        self.assertTrue(w.ground_free(-3,-3,2.5,9))

    def test_nav_finds_route_around_building(self):
        w=toy_world([prism(-6,-18,6,18)])
        nav=Navigator(w)
        start=(-30,0,0)
        for i in range(100):
            q=nav.waypoint(start,(30,0),2.5,9,50,i*0.1,budget=0.003)
            if nav.path:
                break
        self.assertTrue(nav.path,'bounded A* must eventually finish')
        points=[start]+nav.path
        self.assertTrue(all(w.ground_segment(a,b,2.5,9) for a,b in zip(points,points[1:])))
        self.assertTrue(any(abs(p[1])>20 for p in nav.path))

    def test_roof_spawn_can_walk_to_edge(self):
        w=toy_world([prism(-10,-10,10,10,top=15)])
        self.assertIsNotNone(w.motion([0,0,15],[5,0],2.5,9))
        self.assertIsNotNone(w.motion([8,0,15],[16,0],2.5,9))

    def test_route_does_not_skip_occluded_corner(self):
        w=toy_world([prism(-1,-20,1,20)])
        nav=Navigator(w)
        goal=(4,-24)
        nav.waypoint((-4,-24,0),goal,2.5,9,50,0)
        nav.goal=goal
        nav.path=[(-4,-24),goal]
        pos=(-4,-21,0)
        self.assertFalse(w.ground_segment(pos,goal,2.5,9))
        waypoint=nav.waypoint(pos,goal,2.5,9,50,0.1)
        self.assertTrue(w.ground_segment(pos,waypoint,2.5,9))
        self.assertEqual(waypoint,(-4,-24))


class CombatTests(unittest.TestCase):
    def setUp(self):
        self.hello,self.obs=fixture()
        self.obs['self']['pos']=[0,0,0]
        self.obs['self']['vel']=[0,0,0]
        self.obs['self']['weapons']=[gun(),None]
        self.world=toy_world([])
        self.combat=Combat(self.world)

    def test_intercept_hits_moving_target(self):
        origin=[0,0,7];target=[100,0,4.5];velocity=[0,12,0]
        hit=intercept(origin,target,velocity,252)
        t=math.dist(origin,hit)/252
        self.assertAlmostEqual(hit[1],12*t,places=8)
        self.assertGreater(hit[1],0)

    def test_unreachable_intercept(self):
        self.assertIsNone(intercept([0,0,0],[10,0,0],[300,0,0],252))

    def test_gun_waits_for_actual_torso_aim(self):
        e=enemy()
        self.obs['self']['aim']=[math.pi,0]
        a=self.combat.command(self.obs,e,True,0)
        self.assertFalse(a['fire'][0])
        self.obs['self']['aim']=aim_at([0,0,7],center(e))
        self.assertTrue(self.combat.command(self.obs,e,True,0)['fire'][0])

    def test_tracked_enemy_behind_wall_is_not_shot(self):
        self.combat=Combat(toy_world([prism(10,-10,12,10)]))
        e=enemy()
        self.obs['self']['aim']=aim_at([0,0,7],center(e))
        self.assertFalse(self.combat.command(self.obs,e,True,0)['fire'][0])

    def test_laser_charges_then_releases(self):
        e=enemy(80)
        self.obs['self']['aim']=aim_at([0,0,7],center(e))
        self.obs['self']['weapons'][1]=laser()
        self.assertTrue(self.combat.command(self.obs,e,True,0)['fire'][1])
        self.obs['self']['weapons'][1]['charge']=0.75
        self.assertFalse(self.combat.command(self.obs,e,True,0)['fire'][1])

    def test_gun_keeps_firing_during_early_laser_charge(self):
        e=enemy(80);e['vel']=[0,12,0]
        me=self.obs['self']
        me['weapons'][1]=laser(0.3)
        lead=intercept([0,0,7],center(e),e['vel'],252)
        me['aim']=aim_at([0,0,7],lead)
        action=self.combat.command(self.obs,e,True,0)
        self.assertEqual(action['fire'],[True,True])

    def test_retreat_does_not_start_laser_charge(self):
        e=enemy(80)
        me=self.obs['self']
        me['weapons'][1]=laser()
        me['aim']=aim_at([0,0,7],center(e))
        action=self.combat.command(self.obs,e,True,0,mobile=True)
        self.assertEqual(action['fire'],[True,False])

    def test_retreat_releases_existing_charge(self):
        e=enemy(80)
        self.obs['self']['weapons'][1]=laser(0.3)
        self.assertFalse(self.combat.command(self.obs,e,True,0,mobile=True)['fire'][1])

    def test_lightning_preserves_escape_energy(self):
        e=enemy(30)
        me=self.obs['self']
        me['aim']=aim_at([0,0,7],center(e))
        me['energy']=28
        me['weapons'][1]={'kind':'lightning','cooldown':0,'stats':{'range':45,'cone_deg':30,'energy':3}}
        self.assertFalse(self.combat.command(self.obs,e,True,0)['fire'][1])
        me['energy']=60
        self.assertTrue(self.combat.command(self.obs,e,True,0)['fire'][1])


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.hello,self.obs=fixture()
        self.bot=Bot(self.hello)
        self.bot.world=toy_world([])
        self.bot.nav=Navigator(self.bot.world)
        self.bot.combat=Combat(self.bot.world)
        self.obs['self']['pos']=[0,0,0]
        self.obs['zone'].update(center=[0,0],next_center=[0,0],radius=90,next_radius=80)

    def test_low_health_quiet_recovery_does_not_keep_firing(self):
        self.obs['self']['hp']=350
        self.obs['mechs']=[enemy(90)]
        self.obs['self']['aim']=aim_at([0,0,7],center(self.obs['mechs'][0]))
        action=self.bot.act(self.obs)
        self.assertEqual(self.bot.mode,'ESCAPE')
        self.assertEqual(action['fire'],[False,False])
        self.assertAlmostEqual(action['aim'][0],0)

    def test_healthy_retreat_returns_fire(self):
        self.obs['mechs']=[enemy(),dict(enemy(60,10),id=6)]
        self.obs['self']['aim']=aim_at([0,0,7],center(self.obs['mechs'][0]))
        a=self.bot.act(self.obs)
        self.assertEqual(self.bot.mode,'ESCAPE')
        self.assertTrue(a['fire'][0])

    def test_low_health_under_attack_returns_fire_then_goes_quiet(self):
        self.obs['self']['hp']=350
        self.obs['mechs']=[enemy(90)]
        self.obs['self']['aim']=aim_at([0,0,7],center(self.obs['mechs'][0]))
        self.obs['events']=[{'type':'damaged','amount':45,'weapon':'gun','by':5,'bearing':0}]
        self.assertTrue(self.bot.act(self.obs)['fire'][0])
        self.obs['events']=[]
        self.obs['t']=2
        self.obs['tick']=40
        self.assertFalse(self.bot.act(self.obs)['fire'][0])

    def test_empty_safe_area_is_explored(self):
        a=self.bot.act(self.obs)
        self.assertEqual(self.bot.mode,'COLLECT')
        self.assertGreater(distance(self.bot.goal,self.obs['self']['pos']),10)
        self.assertGreater(math.hypot(*a['move']),0)

    def test_nearby_weapon_is_collected_during_distant_fight(self):
        self.obs['mechs']=[enemy(80)]
        self.obs['pickups']=[{'id':8000,'kind':'lightning','pos':[-10,0,0]}]
        self.bot.act(self.obs)
        self.assertEqual(self.bot.mode,'FIGHT')
        self.assertEqual(list(self.bot.goal),[-10,0])

    def test_controller_slows_to_reach_wall_side_waypoint(self):
        self.bot.world=toy_world([prism(0,-30,20,30)])
        self.obs['self']['pos']=[-6,0,0]
        self.bot.deadline=time.perf_counter()+1
        self.bot.mode='COLLECT'
        a=self.bot.steer(self.obs,(-3,0),[])
        self.assertGreater(a['move'][0],0)
        self.assertLess(a['move'][0],1)
        self.assertAlmostEqual(a['move'][1],0)

    def test_zero_motion_with_distant_goal_triggers_recovery(self):
        self.bot.steer=lambda *args: {'move':[0,0],'boost':False,'jump':False}
        for i in range(18):
            self.obs['t']=i*0.1;self.obs['tick']=i*2
            self.bot.act(self.obs)
        self.assertGreater(self.bot.last_reset,0)

    def test_does_not_reload_just_because_aim_is_turning(self):
        self.obs['zone'].update(radius=300,next_radius=250)
        self.obs['mechs']=[enemy(150)]
        self.obs['self']['weapons'][0]['ammo']=6
        self.obs['self']['aim']=[math.pi,0]
        a=self.bot.act(self.obs)
        self.assertFalse(a['fire'][0])
        self.assertFalse(a['reload'])

    def test_ranged_escape_keeps_moving_out_of_open_fire(self):
        self.obs['zone'].update(radius=400,next_radius=300)
        self.obs['self']['hp']=350
        self.obs['mechs']=[enemy(170)]
        a=self.bot.act(self.obs)
        self.assertEqual(self.bot.mode,'ESCAPE')
        self.assertLess(self.bot.goal[0],-10)
        self.assertLess(a['move'][0],-0.5)
        self.assertTrue(a['boost'])

    def test_distant_enemy_does_not_override_equipment_acquisition(self):
        self.obs['zone'].update(radius=400,next_radius=300)
        self.obs['mechs']=[enemy(170)]
        self.obs['pickups']=[{'id':8000,'kind':'lightning','pos':[-40,0,0]}]
        a=self.bot.act(self.obs)
        self.assertEqual(self.bot.mode,'EQUIP')
        self.assertEqual(list(self.bot.goal),[-40,0])
        self.assertLess(a['move'][0],0)

    def test_close_enemy_still_takes_priority_over_distant_weapon(self):
        self.obs['mechs']=[enemy(50)]
        self.obs['pickups']=[{'id':8000,'kind':'lightning','pos':[-40,0,0]}]
        self.bot.act(self.obs)
        self.assertNotEqual(self.bot.mode,'EQUIP')

    def test_lone_ranged_duel_moves_across_fire(self):
        self.obs['zone'].update(radius=400,next_radius=300)
        self.obs['mechs']=[enemy(170)]
        action=self.bot.act(self.obs)
        self.assertGreater(abs(action['move'][1]),abs(action['move'][0]))
        x,y=self.bot.goal
        self.assertGreater(abs(y),2*abs(x))

    def test_two_ranged_mechs_trigger_escape(self):
        self.obs['mechs']=[enemy(150),dict(enemy(0,165),id=6)]
        self.bot.act(self.obs)
        self.assertEqual(self.bot.mode,'ESCAPE')

    def test_clear_laser_target_beyond_gun_range(self):
        self.obs['self']['weapons'][1]=laser()
        self.obs['mechs']=[enemy(260)]
        action=self.bot.act(self.obs)
        self.assertTrue(action['fire'][1])
        self.assertFalse(action['fire'][0])

    def test_sound_turns_torso_and_expires(self):
        self.obs['sounds']=[{'kind':'laser_charge','dist':'near','age':0.05,'bearing':-1.4}]
        action=self.bot.act(self.obs)
        self.assertEqual(action['aim'][0],-1.4)
        self.assertEqual(action['fire'],[False,False])
        self.obs.update(t=1.0,tick=20,sounds=[])
        self.assertNotEqual(self.bot.act(self.obs)['aim'][0],-1.4)

    def test_boost_recharges_before_restarting(self):
        b=self.bot;o=self.obs
        b.mode='ESCAPE';o['self']['hp']=350
        threat={'actor':enemy(80),'dist':80,'exposed':True}
        decisions=[]
        for energy in (100,25,20,35,65):
            o['self']['energy']=energy;b.deadline=time.perf_counter()+1
            decisions.append(b.steer(o,(-40,0),[threat])['boost'])
        self.assertEqual(decisions,[True,True,False,False,True])

    def test_low_health_approaches_uncontested_landed_drop(self):
        self.obs['self']['hp']=350
        self.obs['drops']=[drop_at()]
        a=self.bot.act(self.obs)
        self.assertEqual(self.bot.mode,'CAPTURE')
        self.assertGreater(a['move'][0],0)
        self.assertEqual(a['fire'],[False,False])

    def test_capture_holds_position_in_ring(self):
        self.obs['self']['hp']=350
        self.obs['drops']=[drop_at(0,holder=self.obs['self']['id'],progress=2)]
        a=self.bot.act(self.obs)
        self.assertEqual(self.bot.mode,'CAPTURE')
        self.assertEqual(a['move'],[0.0,0.0])

    def test_does_not_camp_waiting_for_drop_to_land(self):
        d=drop_at();d['lands_in']=10;self.obs['drops']=[d]
        self.bot.act(self.obs)
        self.assertNotEqual(self.bot.mode,'CAPTURE')

    def test_contested_drop_is_rejected(self):
        self.obs['drops']=[drop_at(holder=5,progress=2)]
        self.bot.act(self.obs)
        self.assertNotEqual(self.bot.mode,'CAPTURE')

    def test_exposed_enemy_prevents_capture_even_without_holder(self):
        self.obs['drops']=[drop_at()]
        self.obs['mechs']=[enemy(80)]
        self.bot.act(self.obs)
        self.assertNotEqual(self.bot.mode,'CAPTURE')

    def test_storm_rotation_overrides_supply_drop(self):
        self.obs['self']['pos']=[95,0,0]
        self.obs['self']['in_zone']=False
        self.obs['drops']=[drop_at(95)]
        a=self.bot.act(self.obs)
        self.assertEqual(self.bot.mode,'ROTATE')
        self.assertLess(a['move'][0],0)

    def test_reload_seeks_cover_without_usable_secondary(self):
        self.obs['mechs']=[enemy(80)]
        self.obs['self']['weapons'][0].update(ammo=0,reload=2)
        self.bot.act(self.obs)
        self.assertEqual(self.bot.mode,'RELOAD')
        self.assertLess(self.bot.goal[0],-10)

    def test_usable_laser_allows_fighting_during_gun_reload(self):
        self.obs['mechs']=[enemy(80)]
        self.obs['self']['weapons'][0].update(ammo=0,reload=2)
        self.obs['self']['weapons'][1]=laser()
        self.bot.act(self.obs)
        self.assertEqual(self.bot.mode,'FIGHT')

    def test_exposure_uses_configured_weapon_reach(self):
        t={'actor':enemy(170),'dist':170,'exposed':True}
        self.bot.config['weapons']['gun']['range']=100
        self.assertEqual(self.bot.exposure([0,0,0],[t],9),0)
        self.bot.config['weapons']['gun']['range']=230
        self.assertGreater(self.bot.exposure([0,0,0],[t],9),0)

    def test_zone_escape_takes_priority_over_loot(self):
        self.obs['self']['pos']=[95,0,0]
        self.obs['self']['in_zone']=False
        self.obs['cubes']=[{'id':5000,'pos':[98,0,0]}]
        action=self.bot.act(self.obs)
        self.assertEqual(self.bot.mode,'ROTATE')
        self.assertLess(action['move'][0],0)

    def test_future_zone_uses_remaining_shrink_time(self):
        self.obs['t']=75
        self.obs['zone'].update(center=[10,0],next_center=[20,0],radius=80,next_radius=40,shrink_start=50,shrink_end=100)
        c,r=self.bot.future_zone(self.obs,12.5)
        self.assertEqual(c,[15,0])
        self.assertEqual(r,60)

    def test_upgrade_and_weapon_pickup(self):
        self.obs['offer']={'choices':[{'id':'gun_rate'},{'id':'nanites'},{'id':'sensors'}]}
        self.obs['pickups']=[{'id':8000,'kind':'laser','pos':[1,0,0]}]
        a=self.bot.act(self.obs)
        self.assertEqual(a['pick'],1)
        self.assertEqual(a['take'],8000)

    def test_no_crate_farming_during_recovery(self):
        self.obs['self']['hp']=800
        self.obs['crates']=[{'id':1000,'pos':[15,0,0],'hp':300}]
        a=self.bot.act(self.obs)
        self.assertEqual(self.bot.mode,'HEAL')
        self.assertEqual(a['fire'],[False,False])


if __name__=='__main__':
    unittest.main()
