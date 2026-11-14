"""Physical requirements namespace repeated instances and return water separately."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'scripts'),str(Path(__file__).resolve().parents[2])]
from survey_evaluation import evaluation_course


class OrderedRequirementsTests(unittest.TestCase):
    def fixture(self):
        from gcs.tests.test_run_builder import fixture
        m,r,gps=fixture()
        # The independent evaluator gets physical objects, never survey radii.
        m['scene_id']='physical'
        for obj in m['buoys']:
            obj.update(type='cylinder',radius_m=.2)
        r.update(finish=gps(4,0),finish_radius_m=1)
        return m,r,gps

    def test_repeated_gate_events_reference_unique_instances(self):
        m,r,_=self.fixture();gate=r['steps'][0]
        r['steps']=[{**deepcopy(gate),'id':str(i)} for i in range(2)]
        r['blocks']=[{'instance_id':str(i),'type':'gate','waypoint_start':i} for i in range(2)]
        c=evaluation_course(m,r)
        self.assertEqual([p['block'] for p in c['passages']],['0','1'])
        self.assertEqual(len({p['id'] for p in c['passages']}),2)

    def test_channel_lifetime_before_a_later_card_and_return_escape(self):
        m,r,gps=self.fixture()
        r['steps']=[r['steps'][-1],r['steps'][0]]
        r['blocks']=[{'instance_id':'channel','type':'channel','waypoint_start':0}, {'instance_id':'gate','type':'gate','waypoint_start':1}]
        c=evaluation_course(m,r)
        self.assertEqual(len(c['channels']),1)
        self.assertEqual(c['channels'][0]['end_passage'],2)
        self.assertEqual(c['passages'][-1]['block'],'gate')
        self.assertAlmostEqual(c['passages'][1]['origin'][0],44)
        self.assertAlmostEqual(c['passages'][1]['origin'][1],0)
        d={'planning_mode':'return','execution_budget_s':300,'planning_area':r['planning_area'],'start':gps(34,0),'finish':r['start'],'finish_radius_m':1,
           'navigation_water':[{'polygon':[gps(24,-8),gps(44,-8),gps(44,8),gps(24,8)],'opening':[gps(24,-8),gps(24,8)],'direction':[1,0]}]}
        returned=evaluation_course(m,d)
        self.assertFalse(returned['passages']);self.assertTrue(returned['channels'][0]['return_escape'])
        self.assertEqual(returned['channels'][0]['exit']['direction'],[-1,0])


if __name__=='__main__':unittest.main()
