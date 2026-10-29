"""Command serialization, STOP cancellation and HTTP receipt semantics."""
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from boat_app.control import Control
from boat_app.http_api import serve
from boat_app.mission import Mission


class FakeController:
    def __init__(self):
        self.state='ready'; self.mission=None; self.detail='ready'; self.armed=False
        self.calls=[]; self.waiting=threading.Event(); self.release=threading.Event(); self.block=False
        self.link=self; self.emit=lambda e:None
    def close(self): pass
    def status(self):
        return {'state':self.state,'mission_id':self.mission.mission_id if self.mission else None,
                'detail':self.detail,'armed':self.armed,'heartbeat_age_s':0,'position_age_s':0}
    def tick(self): pass
    def upload(self,mission):
        self.calls.append(('upload',threading.get_ident()));self.mission=mission;self.state='uploaded'
    def start(self):
        self.calls.append(('start',threading.get_ident()));self.waiting.set()
        if self.block:
            while not self.release.wait(.01):self.cancel_check()
        self.cancel_check();self.armed=True;self.state='executing'
    def stop(self):
        self.calls.append(('stop',threading.get_ident()));self.state='stopped'
    def disarm(self):self.armed=False
    def fail(self,detail):self.state='failed'


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.fake=FakeController()
        self.control=Control(self.fake,self.temp.name)
        self.mission=Mission.load(Path(__file__).resolve().parents[1]/'examples/mission.json')
        self.envelope={'approval_id':'approval','revision_sha256':'revision',
                       'mission':self.mission.as_dict()}
    def tearDown(self):
        self.fake.release.set();self.control.close();self.temp.cleanup()
    def wait(self,operation):
        deadline=time.monotonic()+2
        while time.monotonic()<deadline:
            result=self.control.operation(operation['operation_id'])
            if result['state'] not in ('pending','running'):return result
            time.sleep(.01)
        self.fail('operation failed to terminate')
    def upload(self):
        return self.control.submit('upload',self.envelope,self.mission.mission_id)
    def test_idempotent_upload_and_conflicting_revision(self):
        first=self.upload();self.assertEqual(self.wait(first)['state'],'succeeded')
        self.assertEqual(first['operation_id'],self.upload()['operation_id'])
        self.envelope['revision_sha256']='changed'
        with self.assertRaisesRegex(ValueError,'conflicting'):self.upload()
        self.assertEqual(len(self.fake.calls),1)
    def test_start_is_not_repeated(self):
        self.wait(self.upload());first=self.control.submit('start',mission_id=self.mission.mission_id)
        self.assertEqual(self.wait(first)['state'],'succeeded')
        self.assertEqual(first['operation_id'],self.control.submit('start',mission_id=self.mission.mission_id)['operation_id'])
        self.assertEqual([c[0] for c in self.fake.calls],['upload','start'])
    def test_stop_interrupts_start_before_arming_and_single_owner(self):
        self.wait(self.upload());self.fake.block=True
        start=self.control.submit('start',mission_id=self.mission.mission_id)
        self.assertTrue(self.fake.waiting.wait(1))
        stop=self.control.submit('stop')
        self.assertEqual(self.wait(start)['state'],'failed')
        self.assertEqual(self.wait(stop)['state'],'succeeded')
        self.assertFalse(self.fake.armed)
        self.assertEqual(len({c[1] for c in self.fake.calls}),1)
    def test_restart_does_not_repeat_historical_start(self):
        self.wait(self.upload());start=self.control.submit('start',mission_id=self.mission.mission_id)
        self.wait(start);self.control.close()
        self.control=Control(FakeController(),self.temp.name)
        self.assertEqual(start['operation_id'],self.control.submit('start',mission_id=self.mission.mission_id)['operation_id'])
        self.assertEqual(self.control.controller.calls,[])
    def test_http_receipt_and_origin_rejection(self):
        server=serve(self.control,0)
        base='http://127.0.0.1:'+str(server.server_port)
        try:
            request=Request(base+'/missions/'+self.mission.mission_id,data=json.dumps(self.envelope).encode(),method='PUT')
            with urlopen(request) as response:
                self.assertEqual(response.status,202);operation=json.load(response)
            self.assertIn('operation_id',operation)
            with urlopen(base+'/operations/'+operation['operation_id']) as response:
                self.assertEqual(json.load(response)['operation_id'],operation['operation_id'])
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(base+'/stop',method='POST',headers={'Origin':'https://example.com'}))
            self.assertEqual(error.exception.code,403)
        finally:
            server.shutdown();server.server_close()
