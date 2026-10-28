import copy
import math
import random
from pathlib import Path
import sys
import unittest
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'scripts'),str(Path(__file__).resolve().parents[2])]
from evaluate_run import evaluate, project_footprint
from shared.geometry import polygon_clearance


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.footprint={'polygon':[(-.6,-.3),(.6,-.3),(.6,.3),(-.6,.3)],'max_abs_z_m':.4,'enclosing_radius_m':.7}
        self.course={'minimum_clearance_m':.25,'contact_recorder_verified':True,
                     'buoys':{'red':{'radius_m':.24},'green':{'radius_m':.24}},
                     'passages':[{'id':'gate','kind':'gate','x':2,'y_min':-1.76,'y_max':1.76}],
                     'finish':{'x':4,'y':0,'radius_m':1,'speed_m_s':.2,'settle_s':5}}
        self.samples=[]
        for i in range(101):
            x=min(4,i/10)
            self.samples.append({'iteration':i,'time_s':i/10,'dt_s':.1,'contacts':[],
                                 'poses':[{'name':'blueboat/base_link','pose':[x,0,0,0,0,0]},
                                          {'name':'red','pose':[2,-2,0,0,0,0]},
                                          {'name':'green','pose':[2,2,0,0,0,0]}]})
    def result(self):return evaluate(iter(self.samples),self.footprint,self.course,0,10)
    def test_full_pass_and_settle(self):
        result=self.result();self.assertEqual(result['outcome'],'passed',result)
        self.assertGreater(result['passages'][0]['stern_clear_time_s'],2.5)
    def test_invalid_physics_pose_is_inconclusive(self):
        self.samples[20]['poses'][0]['pose'][0]=float('nan')
        self.assertEqual(self.result()['outcome'],'inconclusive')

    def test_reversing_a_cleared_gate_is_rejected(self):
        for i,sample in enumerate(self.samples):
            if 40 < i <= 50:sample['poses'][0]['pose'][0]=4-(i-40)*.2
            elif 50 < i <= 60:sample['poses'][0]['pose'][0]=2+(i-50)*.2
        self.assertTrue(any('reversed cleared passage' in failure for failure in self.result()['failures']))

    def test_stern_still_in_gate_fails(self):
        for s in self.samples:s['poses'][0]['pose'][0]=min(2.3,s['poses'][0]['pose'][0])
        self.assertIn('incomplete course/stern exit',self.result()['failures'])
    def test_contact_and_missing_steps(self):
        self.samples[20]['contacts']=[[1,2]]
        self.assertIn('contact recorded',self.result()['failures'])
        del self.samples[30]
        self.assertEqual(self.result()['outcome'],'inconclusive')
    def test_wrong_side_and_missed_gate_order(self):
        self.course['passages'].insert(0,{'id':'turn','kind':'turn','x':3,'buoy':'red','side':'right'})
        result=self.result();self.assertEqual(result['outcome'],'failed')
        self.assertTrue(any('wrong passing side' in s for s in result['failures']))
        self.assertTrue(any('order' in s for s in result['failures']))
    def test_clearance_detects_stern_only_collision(self):
        poly=[(-.6,-.3),(.6,-.3),(.6,.3),(-.6,.3)]
        self.assertLess(polygon_clearance(poly,(-.55,.45),.24),0)
    def test_finish_speed_cannot_be_replaced_by_completion_report(self):
        for i,s in enumerate(self.samples):
            if i>40:s['poses'][0]['pose'][1]=.1 if i%2 else -.1
        self.assertFalse(self.result()['finish_settled'])
    def test_unverified_contact_recorder_inconclusive(self):
        self.course['contact_recorder_verified']=False
        self.assertEqual(self.result()['outcome'],'inconclusive')

    def test_full_attitude_projection_and_explicit_attitude_limit(self):
        for sample in self.samples:
            sample['poses'][0]['pose'][3:5] = [.3, -.2]
        self.assertEqual(self.result()['outcome'], 'passed')
        self.course['max_roll_pitch_rad'] = .05
        self.assertEqual(self.result()['outcome'], 'inconclusive')

    def test_gate_checks_include_tilted_collision_height(self):
        for sample in self.samples:
            sample['poses'][0]['pose'][1] = 1.3
            sample['poses'][0]['pose'][3] = math.pi/4
        self.course['finish']['y'] = 1.3
        self.assertIn('footprint outside gate opening: gate', self.result()['failures'])

    def test_missing_height_is_inconclusive(self):
        del self.footprint['max_abs_z_m']
        self.assertEqual(self.result()['outcome'], 'inconclusive')


class ProjectionTests(unittest.TestCase):
    def test_ninety_degree_pitch_projects_collision_height(self):
        footprint = {'polygon': [(-2,-1),(2,-1),(2,1),(-2,1)], 'max_abs_z_m': .4}
        polygon = project_footprint(footprint, 0, 0, 0, math.pi/2, 0)
        self.assertAlmostEqual(max(p[0] for p in polygon), .4)
        self.assertAlmostEqual(min(p[0] for p in polygon), -.4)
        self.assertAlmostEqual(max(p[1] for p in polygon), 1)

    def test_projection_contains_rotated_prism_points(self):
        footprint = {'polygon': [(-.6,-.3),(.6,-.3),(.6,.3),(-.6,.3)], 'max_abs_z_m': .4}
        rng = random.Random(24)
        for _ in range(30):
            roll, pitch, yaw = [rng.uniform(-math.pi, math.pi) for _ in range(3)]
            projected = project_footprint(footprint, 2, -3, roll, pitch, yaw)
            for _ in range(30):
                x, y, z = rng.uniform(-.6,.6), rng.uniform(-.3,.3), rng.uniform(-.4,.4)
                # Apply three separate rotations, independently of the matrix implementation.
                y, z = y*math.cos(roll)-z*math.sin(roll), y*math.sin(roll)+z*math.cos(roll)
                x, z = x*math.cos(pitch)+z*math.sin(pitch), -x*math.sin(pitch)+z*math.cos(pitch)
                x, y = x*math.cos(yaw)-y*math.sin(yaw), x*math.sin(yaw)+y*math.cos(yaw)
                self.assertLessEqual(polygon_clearance(projected, (2+x,-3+y), 0), 1e-10)

class ContactProofTests(unittest.TestCase):
    def test_boolean_alone_cannot_verify_live_contact_recorder(self):
        from evaluate_run import verify_contact_evidence
        result=verify_contact_evidence({'contact_recorder_verified':True},'/tmp')
        self.assertFalse(result['contact_recorder_verified'])
