"""Planner and independent final-route validation regressions."""
from copy import deepcopy
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from gcs.app.imports import import_points
from gcs.app.planner import generate, suggest
from gcs.app.workspace import Workspace
from shared.clearance import validate_route
from shared.geometry import to_gps, to_local


class PlannerTests(unittest.TestCase):
    def fixture(self, angle=0, width=4, radius=.3):
        ref={'latitude':40.,'longitude':-86.}
        def gps(x,y):
            c,s=math.cos(angle),math.sin(angle)
            return to_gps(c*x-s*y,s*x+c*y,ref)
        m=import_points(json.dumps([{'id':'a','latitude':gps(4,-width/2)['latitude'],'longitude':gps(4,-width/2)['longitude'],'radius_m':radius},
                                   {'id':'b','latitude':gps(4,width/2)['latitude'],'longitude':gps(4,width/2)['longitude'],'radius_m':.2}]))
        d={'task':'custom','planner_task':'gate','direction':[math.cos(angle),math.sin(angle)],'course_confirmed':True,'sizes_confirmed':True,
           'start':gps(0,0),'exit':gps(7,0),'entry':gps(1,0),'entry_radius_m':1,'finish':gps(8,0),'finish_radius_m':.5,'speed_m_s':.5,
           'clearance_m':.8,'preferred_buffer_m':.8,'planning_area':[gps(x,y) for x,y in [(-2,-5),(10,-5),(10,5),(-2,5)]],
           'passages':[{'id':'gate','kind':'gate','red':'a','green':'b'}],'waypoints':[gps(8,0)]}
        return m,d,gps

    def test_rotated_and_perturbed_unequal_gates(self):
        for angle in [0,.4,1.57,2.4,3.7]:
            with self.subTest(angle=angle):
                m,d,gps=self.fixture(angle,width=2.5,radius=.6)
                r=generate(m,d)
                self.assertTrue(r['success'],r)
                self.assertTrue(validate_route(m,r['draft'])['valid'])
                self.assertEqual(r['draft']['clearance_m'],.8)

    def test_blocked_opening_proof_vs_search_exhaustion(self):
        m,d,_=self.fixture(width=1)
        self.assertIn('insufficient gate opening',generate(m,d)['diagnostics'][0])
        m,d,_=self.fixture()
        r=generate(m,d,max_expansions=1)
        self.assertFalse(r['success']);self.assertEqual([a['spacing_m'] for a in r['attempts']],[.25,.10,.05])
        self.assertIn('not proven',r['diagnostics'][0])

    def test_wrong_side_order_reverse_and_channel_escape(self):
        m,d,gps=self.fixture()
        d['passages']=[{'id':'turn','kind':'turn','buoy':'a','side':'right'}]
        self.assertFalse(validate_route(m,d)['valid'])
        d['passages']=[{'id':'late','kind':'turn','buoy':'b','side':'right'},{'id':'early','kind':'gate','red':'a','green':'b'}]
        self.assertFalse(validate_route(m,d)['valid'])
        d['passages']=[]; d['planner_task']='channel'
        d['channel']=[gps(x,y) for x,y in [(-1.5,-1.5),(9.5,-1.5),(9.5,1.5),(-1.5,1.5)]]
        d['waypoints']=[gps(3,2),gps(8,0)]
        self.assertFalse(validate_route(m,d)['valid'])
        d['waypoints']=[gps(8,0)]
        self.assertTrue(generate(m,d)['success'])
        d['start']=gps(5,0)
        self.assertFalse(generate(m,d,resolutions=(.25,),max_expansions=200)['success'])

    def test_proven_blocked_entry_window(self):
        m,d,gps=self.fixture()
        m['buoys'].append({**m['buoys'][0], 'id':'blocker','centre':gps(1,0),'radius_m':1.1})
        result=generate(m,d)
        self.assertIn('obstructed approach',result['diagnostics'][0])

    def test_unsafe_start_and_finish(self):
        m,d,gps=self.fixture()
        d['start']=m['buoys'][0]['centre']
        self.assertIn('obstructed approach',generate(m,d)['diagnostics'][0])
        d['start']=gps(0,0);d['finish']=m['buoys'][0]['centre']
        self.assertIn('unsafe finish',generate(m,d)['diagnostics'][0])

    def test_preferred_shortfall_and_detector_never_override_required(self):
        m,d,gps=self.fixture(width=2.5,radius=.6)
        d['preferred_buffer_m']=2
        m['buoys'][1]['object_type']='detector'
        r=generate(m,d)
        self.assertTrue(r['success'],r)
        self.assertTrue(r['validation']['preferred_shortfalls'])
        self.assertGreaterEqual(min(s['clearance_m'] for s in r['validation']['preferred_shortfalls']),.8-1e-7)
        d['clearance_m']=1.2
        self.assertFalse(generate(m,d)['success'])

    def test_unlabeled_import_defaults_and_original_persistence(self):
        m=import_points('latitude,longitude\n40,-86\n40.0001,-86\n','csv')
        self.assertEqual(m['schema_version'],3);self.assertNotIn('alignment',m)
        self.assertEqual(m['buoys'][0]['object_type'],'unknown')
        self.assertEqual(m['buoys'][0]['radius_m'],.5)
        with tempfile.TemporaryDirectory() as tmp:
            w=Workspace(tmp);w.edit({'map':m,'new_import':True})
            changed=deepcopy(m);changed['buoys'][0].update(radius_m=1,category='red',object_type='buoy')
            w.edit({'map':changed})
            restored=Workspace(tmp).read()
            self.assertEqual(restored['original_map'],m)
            self.assertEqual(restored['map'],changed)

    def test_course_tasks_persist_revoke_and_retry(self):
        m,d,gps=self.fixture()
        with tempfile.TemporaryDirectory() as tmp:
            w=Workspace(tmp)
            roles={k:v for k,v in d.items() if k not in ('start','waypoints','planner_task')}
            w.edit({'map':m,'course':{'gate':roles},'draft':d})
            # Map corrections require renewed review.
            roles['sizes_confirmed']=roles['course_confirmed']=True
            w.edit({'course':{'gate':roles},'draft':d})
            w.approve()
            w.edit({'selected_task':'channel'})
            self.assertIsNone(w.read()['approval'])
            w.edit({'selected_task':'gate'})
            self.assertIsNone(w.read()['approval'])
            self.assertEqual(w.read()['draft']['start'],d['start'])
            state=Workspace(tmp).read();self.assertIn('gate',state['tasks'])
            w.approve();w.edit({'map':m})
            self.assertIsNone(w.read()['approval']);self.assertFalse(w.validate()['valid'])

    def test_ambiguous_suggestions_stay_unconfirmed(self):
        m,d,gps=self.fixture()
        m['buoys'].append({**m['buoys'][0],'id':'c','centre':gps(4,5)})
        s=suggest(m,[1,0]);self.assertGreater(len(s['gate_candidates']),1)
        self.assertFalse(s['confirmed']);self.assertIsNone(s['slalom'][0]['side'])
        d['sizes_confirmed']=False
        self.assertFalse(generate(m,d)['success'])

    def test_rotated_slalom_without_labels_and_channel_retry(self):
        for angle in (0,.7,2.1):
            m,d,gps=self.fixture(angle)
            # A second turn at a different plane requires progress, side and orientation.
            m['buoys'].append({**m['buoys'][0], 'id':'c', 'centre':gps(6,0)})
            d['planner_task']='slalom'
            d['passages']=[{'id':'one','kind':'turn','buoy':'a','side':'left'},
                           {'id':'two','kind':'turn','buoy':'c','side':'right'}]
            d['exit']=gps(8,0); d['finish']=gps(9,0);d['finish_radius_m']=.2
            result=generate(m,d)
            self.assertTrue(result['success'],result)
            self.assertTrue(validate_route(m,result['draft'])['valid'])
        m,d,gps=self.fixture()
        d.update(planner_task='channel',passages=[],channel=d['planning_area'])
        first=generate(m,d);self.assertTrue(first['success'])
        d['start']=gps(0,2)
        retry=generate(m,d);self.assertTrue(retry['success'])
        self.assertNotEqual(first['draft']['start'],retry['draft']['start'])

    def test_live_manual_size_confirmation_and_bad_polygons(self):
        m,d,_=self.fixture()
        d.pop('planner_task');d['sizes_confirmed']=False
        self.assertFalse(validate_route(m,d)['valid'])
        d['sizes_confirmed']=True
        self.assertTrue(validate_route(m,d)['valid'])
        d['planning_area']=d['planning_area'][:2]
        with self.assertRaises(ValueError):validate_route(m,d)

if __name__=='__main__':unittest.main()
