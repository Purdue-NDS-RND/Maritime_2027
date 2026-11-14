"""Primary full-course fixture: task setup, safe approach and final GPS checks."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from gcs.app.course_setup import prepare_task
from gcs.app.planner import generate
from gcs.app.workspace import Workspace
from shared.clearance import validate_route
from shared.course import Course, gap, dot, sub, inside
from shared.geometry import to_gps,to_local


class CompetitionPlannerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.map=json.loads((Path(__file__).resolve().parents[1]/'examples/competition-gps-map.json').read_text())

    def test_full_map_labels_select_only_correct_station(self):
        gate=prepare_task(self.map,'gate')['draft']
        slalom=prepare_task(self.map,'slalom')['draft']
        channel=prepare_task(self.map,'channel')['draft']
        for actual,expected in [(gate['direction'],[-1,0]),(slalom['direction'],[-1,0]),(channel['direction'],[0,-1])]:
            for value,target in zip(actual,expected):self.assertAlmostEqual(value,target,places=8)
        self.assertEqual(len(slalom['passages']),5)
        self.assertEqual(slalom['passages'][0]['buoy'],'dodge_turn_1')
        self.assertTrue(all(p.get('side') in ('left','right') for p in slalom['passages'] if p['kind']=='turn'))
        self.assertFalse(gate['course_confirmed'])
        self.assertEqual(set(channel['channel_chains']),{'left','right'})
        self.assertEqual(len(self.map['buoys']),23);self.assertEqual(len(self.map['obstacles']),6)
        self.assertNotIn('alignment',self.map);self.assertNotIn('start_pose',self.map)

    def test_generation_and_final_validation_for_each_full_map_task(self):
        for task in ('gate','slalom','channel'):
            with self.subTest(task=task):
                required=1.8 if task=='channel' else 1.5
                d=prepare_task(self.map,task,{'start':self.map['geographic_reference'],'clearance_m':required})['draft']
                d.update(sizes_confirmed=True,course_confirmed=True)
                result=generate(self.map,d)
                self.assertTrue(result['success'],result)
                self.assertEqual(result['draft']['clearance_m'],required)
                self.assertTrue(validate_route(self.map,result['draft'])['valid'])
                if task=='channel':
                    self.assertNotEqual(to_local(d['start'],self.map['geographic_reference']),to_local(result['draft']['derived_sections'][0]['centre'],self.map['geographic_reference']))
                    c=Course(self.map,result['draft'])
                    finish=to_local(result['draft']['finish'],c.reference)
                    centre=to_local(c.draft['derived_sections'][-1]['centre'],c.reference)
                    self.assertGreater(dot(sub(finish,centre),c.planes[-1][1]),required+d['finish_radius_m'])
                    self.assertFalse(inside(finish,c.channel))

    def test_point_gate_hard_buffer_failure_without_reduction(self):
        proposal=prepare_task(self.map,'gate',{'clearance_m':2.1})
        self.assertTrue(any('4.00 m' in text and '4.20 m' in text for text in proposal['diagnostics']))
        d=proposal['draft'];d.update(sizes_confirmed=True,course_confirmed=True)
        result=generate(self.map,d)
        self.assertFalse(result['success']);self.assertIn('insufficient gate opening',result['diagnostics'][0])
        self.assertEqual(d['clearance_m'],2.1)

    def test_channel_start_near_side_returns_actionable_error(self):
        d=prepare_task(self.map,'channel',{'clearance_m':2})['draft']
        d.update(sizes_confirmed=True,course_confirmed=True)
        ref=self.map['geographic_reference']
        d['start']=to_gps(-61.627589,-3.930947,ref)
        result=generate(self.map,d,max_expansions=0)
        self.assertFalse(result['success'])
        self.assertIn('boundary exclusion',result['diagnostics'][0])
        self.assertEqual(d['clearance_m'],2)

    def test_extended_full_map_channel_accepts_starts_around_course(self):
        ref=self.map['geographic_reference']
        d=prepare_task(self.map,'channel',{'clearance_m':2})['draft']
        d.update(sizes_confirmed=True,course_confirmed=True)
        points=[to_local(p,ref) for p in d['channel']]
        xmin,xmax=min(p[0] for p in points),max(p[0] for p in points)
        end=min(p[1] for p in points)
        # Match the operator-reviewed extension beyond both end buoy pairs.
        d['channel']=[to_gps(x,y,ref) for x,y in [(xmin,8),(xmin,end-8),(xmax,end-8),(xmax,8)]]
        d['planning_area']=[to_gps(x,max(y,14) if y>0 else y,ref) for x,y in
                            (to_local(p,ref) for p in d['planning_area'])]
        d['finish']=to_gps((xmin+xmax)/2,end-4.5,ref)
        d['tower_avoidance']={'hard_m':1.5,'soft_m':10,'strength':25,'overrides':{}}
        for start in ((0,0),(-78,-10),(-55,-23),(-67,9)):
            with self.subTest(start=start):
                d['start']=to_gps(*start,ref)
                result=generate(self.map,d,max_seconds=15)
                self.assertTrue(result['success'],result)
                generated=result['draft']
                self.assertTrue(validate_route(self.map,generated)['valid'])
                self.assertEqual(generated['attempt']['initial_progress'],0)
                self.assertEqual(generated['clearance_m'],2)
                self.assertEqual(generated['channel'],d['channel'])
                self.assertTrue(any(section['kind']=='approach' for section in generated['route_sections']))

    def test_planning_deadline_reports_exhaustion_without_claiming_blockage(self):
        d=prepare_task(self.map,'channel')['draft']
        d.update(sizes_confirmed=True,course_confirmed=True)
        result=generate(self.map,d,max_seconds=0)
        self.assertFalse(result['success'])
        self.assertIn('time limit',result['diagnostics'][0])
        self.assertTrue(result['attempts'][0]['time_exhausted'])
        self.assertNotIn('draft',result)

    def test_precomputed_collision_geometry_matches_independent_gap(self):
        d=prepare_task(self.map,'channel')['draft'];c=Course(self.map,d)
        for a,b in [((0,0),(-67,3)),((-67,2),(-67,-23)),((-73,-14),(-72,-14)),((-10,-18),(-9,-17))]:
            self.assertAlmostEqual(c.clearance(a,b),min(gap(o,a,b,c.reference) for o in c.objects),places=7)

    def test_unlabeled_maps_require_assignments_and_keep_settings(self):
        m=deepcopy(self.map)
        for i,o in enumerate(m['buoys']):o.update(id=f'point_{i}',category='unknown');o.pop('task',None)
        result=prepare_task(m,'gate',{'clearance_m':2.3,'speed_m_s':1.2})
        self.assertFalse(result['ready']);self.assertFalse(result['draft']['course_confirmed'])
        self.assertEqual(result['draft']['clearance_m'],2.3)
        self.assertEqual(result['draft']['speed_m_s'],1.2)

    def test_import_preserves_previous_workspace_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Workspace(tmp);w.edit({'map':self.map})
            original=w.read();w.edit({'map':self.map,'new_import':True})
            backup=next(Path(tmp).glob('workspace-before-map-import-*.json'))
            self.assertEqual(json.loads(backup.read_text()),original)

    def test_new_map_import_archives_old_task_drafts_instead_of_reusing_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Workspace(tmp)
            d=prepare_task(self.map,'gate')['draft']
            w.edit({'map':self.map,'draft':d})
            self.assertIn('gate',w.read()['tasks'])
            w.edit({'map':self.map,'new_import':True})
            self.assertEqual(w.read()['tasks'],{})
            self.assertIsNone(w.read()['draft'])
            backup=json.loads(next(Path(tmp).glob('workspace-before-map-import-*.json')).read_text())
            self.assertIn('gate',backup['tasks'])
