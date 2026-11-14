"""Course settings propagation, tower geometry, and soft-cost preservation."""
from copy import deepcopy
import json
import tempfile
import unittest
from gcs.app.settings import defaults, validate_settings, effective_settings
from gcs.app.workspace import Workspace
from gcs.app.planner import generate
from shared.clearance import validate_route
from shared.course import gap
from shared.geometry import to_gps, to_local


class CourseSettingsTests(unittest.TestCase):
    def fixture(self):
        ref={'latitude':40.,'longitude':-86.}
        def gps(x,y):return to_gps(x,y,ref)
        tower={'id':'tower','object_type':'detector','type':'polygon','height_m':1,'centre':gps(10,0),
               'footprint':[gps(x,y) for x,y in [(9.5,-.5),(10.5,-.5),(10.5,.5),(9.5,.5)]]}
        m={'schema_version':3,'source':'live','geographic_reference':ref,'buoys':[{'id':'distant_buoy','object_type':'buoy','type':'cylinder','height_m':1,'radius_m':.2,'centre':gps(-10,-10)}],'obstacles':[tower]}
        d={'task':'custom','planner_task':'channel','direction':[1,0],'course_confirmed':True,'sizes_confirmed':True,
           'start':gps(0,0),'entry':gps(1,0),'exit':gps(19,0),'entry_radius_m':5,'exit_radius_m':5,
           'finish':gps(20,0),'finish_radius_m':.5,'speed_m_s':.5,'clearance_m':.5,'preferred_buffer_m':.5,
           'planning_area':[gps(x,y) for x,y in [(-2,-7),(22,-7),(22,7),(-2,7)]],
           'channel':[gps(x,y) for x,y in [(-1,-6),(21,-6),(21,6),(-1,6)]],'passages':[],'waypoints':[gps(20,0)],
           'tower_avoidance':{'hard_m':.6,'soft_m':5,'strength':25,'overrides':{}}}
        return m,d,gps

    def test_invalid_settings_rejected_without_persisting(self):
        for field,value in [('hard_m',-1),('soft_m',0),('strength',float('nan'))]:
            settings=defaults();settings['tower_avoidance'][field]=value
            with self.assertRaises(ValueError):validate_settings(settings)
        with tempfile.TemporaryDirectory() as directory:
            w=Workspace(directory);before=w.path.read_bytes()
            settings=defaults();settings['task_overrides']={'unexpected':{}}
            with self.assertRaises(ValueError):w.edit({'game_settings':settings})
            self.assertEqual(w.path.read_bytes(),before)

    def test_shared_settings_task_overrides_and_backup_preserve_routes(self):
        m,d,_=self.fixture()
        from gcs.app.imports import point_map
        m=point_map(m)
        with tempfile.TemporaryDirectory() as directory:
            from pathlib import Path
            path=Path(directory)/'workspace.json'
            original={'workspace_version':2,'map':m,'draft':d,'approval':None,'tasks':{'channel':d,'manual':{**d,'planner_task':None}},'course':{}}
            path.write_text(json.dumps(original));before=path.read_bytes()
            w=Workspace(directory)
            self.assertEqual(next(Path(directory).glob('workspace-before-course-settings-*')).read_bytes(),before)
            settings=defaults(d)
            settings['speed_m_s']=1.2
            settings['task_overrides']['channel']={'speed_m_s':.7}
            state=w.edit({'game_settings':settings})
            self.assertEqual(state['draft']['speed_m_s'],.7)
            self.assertEqual(state['tasks']['manual']['speed_m_s'],1.2)
            self.assertEqual(state['draft']['waypoints'],d['waypoints'])
            self.assertEqual(state['map'],m)
            self.assertFalse(state['draft']['course_confirmed'])
            self.assertEqual(Workspace(directory).read(),state)
            state=w.edit({'draft':{**state['draft'],'speed_m_s':99}})
            self.assertEqual(state['draft']['speed_m_s'],.7)
            self.assertEqual(effective_settings(settings,'gate')['speed_m_s'],1.2)

    def test_hard_tower_zone_uses_surface_and_individual_override(self):
        m,d,gps=self.fixture()
        d.pop('planner_task');d.pop('entry');d.pop('exit');d.pop('channel')
        d['start']=gps(0,1.2);d['finish']=gps(20,1.2);d['waypoints']=[d['finish']]
        self.assertTrue(validate_route(m,d)['valid'])
        d['tower_avoidance']['overrides']['tower']={'hard_m':1,'soft_m':5}
        self.assertFalse(validate_route(m,d)['valid'])
        d['start']=gps(0,2);d['finish']=gps(20,2);d['waypoints']=[d['finish']]
        result=validate_route(m,d)
        self.assertTrue(result['valid']);self.assertEqual(result['tower_shortfalls'][0]['object_id'],'tower')

    def test_strong_soft_avoidance_survives_simplification_and_yields_when_needed(self):
        m,d,_=self.fixture()
        results=[]
        for strength in (0,25):
            d['tower_avoidance']['strength']=strength
            result=generate(m,d,max_seconds=25)
            self.assertTrue(result['success'],result)
            route=[to_local(p,m['geographic_reference']) for p in [result['draft']['start'],*result['draft']['waypoints']]]
            results.append(min(gap(m['obstacles'][0],a,b,m['geographic_reference']) for a,b in zip(route,route[1:])))
            self.assertTrue(validate_route(m,result['draft'])['valid'])
        self.assertGreater(results[1],results[0]+1)
        d['tower_avoidance']['soft_m']=100
        result=generate(m,d,max_seconds=25)
        self.assertTrue(result['success'],result)
        self.assertTrue(result['validation']['tower_shortfalls'])
        d['tower_avoidance']['hard_m']=6
        self.assertFalse(generate(m,d,max_expansions=2000,max_seconds=5)['success'])

    def test_new_map_retains_shared_distances_without_old_tower_overrides(self):
        m,d,_=self.fixture()
        with tempfile.TemporaryDirectory() as directory:
            w=Workspace(directory)
            settings=defaults(d)
            settings['tower_avoidance']['overrides']['tower']={'hard_m':2,'soft_m':20}
            w.edit({'map':m,'game_settings':settings})
            state=w.edit({'map':m,'new_import':True})
            self.assertEqual(state['game_settings']['tower_avoidance']['hard_m'],.6)
            self.assertEqual(state['game_settings']['tower_avoidance']['overrides'],{})

    def test_circular_tower_hard_zone_and_finish_disk(self):
        m,d,gps=self.fixture()
        m['obstacles'][0]={'id':'tower','object_type':'detector','type':'cylinder','radius_m':.5,'height_m':1,'centre':gps(10,0)}
        d.pop('planner_task');d.pop('entry');d.pop('exit');d.pop('channel')
        d['start']=gps(0,1.2);d['finish']=gps(20,1.2);d['waypoints']=[d['finish']]
        self.assertTrue(validate_route(m,d)['valid'])
        d['finish']=gps(10,1.2);d['waypoints']=[d['finish']]
        self.assertFalse(validate_route(m,d)['valid'],'Finish disk must also fit outside the hard tower zone')
