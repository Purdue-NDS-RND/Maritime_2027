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
