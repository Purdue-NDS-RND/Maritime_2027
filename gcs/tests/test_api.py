"""Authoritative backend behavior using an isolated fake boat HTTP transport."""
import importlib.util
import os
import tempfile
import unittest
from unittest.mock import patch

HAS_CLIENT=importlib.util.find_spec('fastapi') is not None and importlib.util.find_spec('httpx') is not None


@unittest.skipUnless(HAS_CLIENT,'FastAPI/httpx integration dependencies unavailable on host')
class ApiTests(unittest.TestCase):
    def setUp(self):
        from test_workspace import WorkspaceTests
        self.fixture=WorkspaceTests();self.fixture.setUp()
        os.environ['GCS_DATA']=self.fixture.temp.name+'/api-data'
        from gcs.app import main
        from fastapi.testclient import TestClient
        self.main=main;main.workspace=self.fixture.workspace
        self.client=TestClient(main.app)
        self.calls=[]
        self.vehicle={'state':'uploaded','position':self.fixture.draft['start'],
                      'heartbeat_age_s':0,'position_age_s':0,'armed':False}
        def boat(path,method='GET',body=None):
            self.calls.append((path,method,body))
            if path=='/status':return self.vehicle
            if path.startswith('/operations/'):return {'operation_id':'operation','state':'succeeded'}
            return {'operation_id':'operation','state':'pending'}
        self.mock=patch.object(main,'boat',boat);self.mock.start()
    def tearDown(self):
        self.mock.stop();self.client.close();self.fixture.tearDown()
    def test_validate_approve_upload_start_remain_separate(self):
        self.assertTrue(self.client.post('/api/validate').json()['valid'])
        self.assertFalse(self.calls)
        self.assertEqual(self.client.post('/api/approve').status_code,200)
        self.assertFalse(self.calls)
        result=self.client.post('/api/upload');self.assertEqual(result.status_code,200)
        self.assertEqual(result.json()['state'],'pending')
        self.assertEqual(self.calls[-1][1],'PUT')
        self.assertNotIn('buoys',self.calls[-1][2]['mission'])
        self.assertNotIn('navigation_profile_id',self.calls[-1][2])
        self.assertEqual(self.client.post('/api/start').status_code,200)
        self.assertTrue(self.calls[-1][0].endswith('/start'))
    def test_edit_revokes_backend_start_authority(self):
        self.client.post('/api/approve')
        self.client.put('/api/workspace',json={'draft':self.fixture.draft})
        self.assertEqual(self.client.post('/api/start').status_code,422)
        self.assertFalse(self.calls)
    def test_stale_vehicle_or_unsafe_actual_start_rejected(self):
        self.client.post('/api/approve');self.vehicle['position_age_s']=10
        self.assertEqual(self.client.post('/api/upload').status_code,409)
        self.vehicle['position_age_s']=0;self.vehicle['position']=self.fixture.map['buoys'][0]['centre']
        self.assertEqual(self.client.post('/api/start').status_code,409)
    def test_stop_and_disarm_do_not_require_approval(self):
        self.assertEqual(self.client.post('/api/stop').status_code,200)
        self.assertEqual(self.client.post('/api/disarm').status_code,200)
        self.assertEqual([c[0] for c in self.calls],['/stop','/disarm'])
    def test_cross_origin_mutation_is_refused(self):
        self.assertEqual(self.client.post('/api/stop',headers={'Origin':'https://example.com'}).status_code,403)
        self.assertFalse(self.calls)

    def test_planning_operations_never_command_boat_and_failed_generation_revokes(self):
        from test_planner import PlannerTests
        m,d,_=PlannerTests().fixture()
        self.client.put('/api/workspace',json={'map':m})
        roles={k:v for k,v in d.items() if k not in ('start','waypoints','planner_task')}
        self.client.put('/api/workspace',json={'course':{'gate':roles},'draft':d})
        self.assertEqual(self.client.post('/api/course/suggest',json={'direction':[1,0]}).status_code,200)
        generated=self.client.post('/api/generate').json()
        self.assertTrue(generated['success'],generated)
        self.assertFalse(self.calls)
        self.assertEqual(self.client.post('/api/approve').status_code,200)
        self.client.put('/api/workspace',json={'selected_task':'channel'})
        self.assertIsNone(self.fixture.workspace.read()['approval'])
        self.assertFalse(self.calls)
        self.client.put('/api/workspace',json={'selected_task':'gate'})
        self.assertEqual(self.client.post('/api/approve').status_code,200)
        self.vehicle['position']={'latitude':m['geographic_reference']['latitude'],'longitude':m['geographic_reference']['longitude']}
        self.assertEqual(self.client.post('/api/upload').status_code,409)
        self.assertFalse(any(c[1]!='GET' for c in self.calls))

    def test_competition_example_and_setup_are_unconfirmed_and_never_command(self):
        response=self.client.get('/api/examples/competition')
        self.assertEqual(response.status_code,200)
        m=response.json();self.assertEqual(len(m['buoys']),23)
        self.client.post('/api/import',json={'content':__import__('json').dumps(m)})
        proposed=self.client.post('/api/course/prepare',json={'task':'channel','settings':{'clearance_m':2,'speed_m_s':.7}})
        self.assertEqual(proposed.status_code,200)
        self.assertEqual(proposed.json()['draft']['clearance_m'],2)
        self.assertFalse(proposed.json()['draft']['course_confirmed'])
        self.assertFalse(self.calls)
