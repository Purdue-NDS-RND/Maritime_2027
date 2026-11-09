"""Session API and guided return behavior with an isolated boat transport."""
from copy import deepcopy
import importlib.util
import json
import os
import threading
import unittest
from unittest.mock import patch
from test_run_builder import fixture

HAS_CLIENT = importlib.util.find_spec('fastapi') is not None and importlib.util.find_spec('httpx') is not None


@unittest.skipUnless(HAS_CLIENT, 'FastAPI/httpx unavailable on host')
class ApiTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from gcs.app import main
        self.main = main
        main.sessions.clear();main.operations.clear()
        from gcs.app.connection_manager import ConnectionManager
        main.manager = ConnectionManager()
        self.client = TestClient(main.app)
        value = self.client.post('/api/session').json()
        self.client.headers['X-Planner-Session'] = value['session_id']
        self.w = main.sessions[value['session_id']]
        self.m,self.run,self.gps = fixture()
        self.run['steps'] = self.run['steps'][:1]
        self.w.edit({'revision':0,'map':self.m,'new_import':True})
        self.w.edit({'revision':1,'run_draft':self.run})
        self.vehicle = {'position':self.run['start'],'position_age_s':0,'heartbeat_age_s':0,'state':'idle','armed':False,'mode':4,'speed_m_s':0}
        self.calls=[];self.ops={};self.fail_stop=False;self.fail_upload=False
        def boat(path,method='GET',body=None):
            self.calls.append((path,method,body))
            if path == '/status':return deepcopy(self.vehicle)
            if path.startswith('/operations/'):return self.ops[path.split('/')[-1]]
            command = 'upload' if method == 'PUT' else 'start' if path.endswith('/start') else path[1:]
            key = str(len(self.ops))
            op = {'operation_id':key,'command':command,'state':'succeeded'}
            if command == 'upload':
                op['mission_id'] = body['mission']['mission_id']
                self.vehicle.update(mission_id=op['mission_id'],state='uploaded')
                if self.fail_upload:op.update(state='failed',detail='readback mismatch')
            if command == 'start':self.vehicle.update(state='executing',armed=True,mode=10)
            if command == 'stop':
                self.vehicle.update(state='stopped',mode=4,speed_m_s=0)
                if self.fail_stop:op.update(state='failed',detail='HOLD rejected')
            if command == 'disarm':self.vehicle['armed']=False
            self.ops[key]=op
            # Real transport returns a receipt; reconciliation needs polling.
            return {**op,'state':'pending'}
        self.mock=patch.object(main,'boat',boat);self.mock.start()

    def tearDown(self):
        self.mock.stop();self.client.close()

    def generate(self):
        r=self.client.post('/api/generate');self.assertEqual(r.status_code,200,r.text)
        self.assertTrue(r.json()['success'],r.text)
        return r.json()

    def test_gate_then_slalom_and_standalone_slalom_generate_without_sharing(self):
        _,run,gps=fixture()
        for standalone in (False,True):
            draft=deepcopy(run)
            draft['steps']=draft['steps'][1:2] if standalone else draft['steps'][:2]
            if standalone:draft['start']=gps(4,0)
            self.w.edit({'revision':self.w.read()['revision'],'run_draft':draft})
            self.generate()
            out=self.w.read()['run_draft']
            self.assertEqual([b['instances'] for b in out['blocks']],[['slalom']] if standalone else [['gate'],['slalom']])
            self.assertTrue(self.client.post('/api/validate').json()['valid'])
        self.assertFalse(self.calls)

    def approve(self):
        self.generate();self.assertTrue(self.client.post('/api/validate').json()['valid'])
        r=self.client.post('/api/approve');self.assertEqual(r.status_code,200,r.text);return r.json()

    def command(self,name):
        r=self.client.post('/api/'+name);self.assertEqual(r.status_code,200,r.text)
        return self.client.get('/api/operations/'+r.json()['operation_id']).json()

    def started(self):
        approval=self.approve();self.command('upload');self.command('start');return approval

    def test_review_transfer_and_start_are_separate_and_readback_required(self):
        self.approve();self.assertFalse(any(c[1]!='GET' for c in self.calls))
        self.assertEqual(self.client.post('/api/start').status_code,409)
        self.command('upload');self.command('start')
        self.assertEqual(self.w.read()['return_target'],self.run['start'])
        self.assertEqual(self.client.post('/api/start').status_code,422)

    def test_fresh_tabs_reload_backend_and_reset_are_empty_without_boat_commands(self):
        self.approve();before=len(self.calls)
        other=self.client.post('/api/session').json()
        self.assertIsNone(other['workspace']['map']);self.assertFalse(other['workspace']['run_draft']['steps'])
        reset=self.client.post('/api/reset').json();self.assertIsNone(reset['map']);self.assertIsNone(reset['return_target'])
        self.assertEqual(len(self.calls),before)
        self.main.sessions.clear()
        self.assertEqual(self.client.get('/api/workspace').status_code,409)
        self.assertEqual(self.client.post('/api/stop').status_code,200)

    def test_stop_is_independent_and_cross_origin_is_rejected(self):
        self.client.headers.pop('X-Planner-Session')
        self.assertEqual(self.client.post('/api/stop').status_code,200)
        self.assertEqual(self.client.post('/api/disarm').status_code,200)
        self.assertEqual(self.client.post('/api/stop',headers={'Origin':'https://example.com'}).status_code,403)

    def test_live_start_stale_and_actual_position_change(self):
        d=deepcopy(self.run);d['attempt']['start_source']='live'
        self.w.edit({'revision':self.w.read()['revision'],'run_draft':d})
        self.vehicle['position_age_s']=4
        self.assertEqual(self.client.post('/api/generate').status_code,200)
        self.assertFalse(self.w.read()['run_draft']['waypoints'])
        self.vehicle['position_age_s']=0;self.approve();self.vehicle['position']=self.gps(-4,0)
        self.assertEqual(self.client.post('/api/upload').status_code,409)

    def test_return_uses_sampled_position_and_frozen_target_after_task_or_finish(self):
        for state in ('executing','complete','stopped'):
            if not self.w.read()['return_target']:self.started()
            target=deepcopy(self.w.read()['return_target'])
            self.vehicle.update(position=self.gps(5,0),state=state,armed=True)
            r=self.client.post('/api/return/prepare');self.assertEqual(r.status_code,200,r.text)
            out=r.json();self.assertTrue(out['success'],out)
            d=out['draft'];self.assertEqual(d['return_target'],target);self.assertEqual(d['finish'],target)
            self.assertEqual(d['start'],self.gps(5,0));self.assertNotEqual(d['start'],d['finish'])
            self.assertEqual(self.client.post('/api/start').status_code,422)
            self.assertTrue(self.client.post('/api/validate').json()['valid'])
            a=self.client.post('/api/approve');self.assertEqual(a.status_code,200,a.text)
            self.assertEqual(a.json()['envelope']['mission']['finish_settle_s'],5)
            self.assertEqual(self.client.post('/api/upload').status_code,409)
            self.command('disarm');self.command('upload');self.command('start')
            self.assertEqual(self.w.read()['return_target'],target)

    def test_return_inside_channel_exits_only_through_beginning(self):
        # Start at the safe launch area, then simulate interruption inside water.
        d=deepcopy(self.run);_,all_steps,_=fixture();d['steps']=all_steps['steps']
        self.w.edit({'revision':self.w.read()['revision'],'run_draft':d})
        self.started();self.vehicle['position']=self.gps(34,0)
        r=self.client.post('/api/return/prepare');self.assertEqual(r.status_code,200,r.text)
        self.assertTrue(r.json()['success'],r.text)
        from shared.navigation import NavigationCourse
        out=r.json()['draft'];course=NavigationCourse(self.m,out)
        self.assertIsNone(course.edge((34,0),(34,10),0))
        self.assertIsNone(course.edge((34,0),(50,0),0))
        self.assertEqual(course.edge((34,0),(20,0),0),1)
        self.assertTrue(self.client.post('/api/validate').json()['valid'])

    def test_return_failures_consume_outbound_authority_and_never_start(self):
        self.started();self.fail_stop=True
        r=self.client.post('/api/return/prepare');self.assertEqual(r.status_code,409);self.assertIn('HOLD rejected',r.text)
        self.assertEqual(self.client.post('/api/start').status_code,422)
        self.fail_stop=False;self.vehicle['position_age_s']=4
        self.assertEqual(self.client.post('/api/return/prepare').status_code,409)
        self.vehicle['position_age_s']=0;self.vehicle['position']=self.m['buoys'][0]['centre']
        r=self.client.post('/api/return/prepare');self.assertFalse(r.json()['success'])
        self.assertFalse(self.w.read()['run_draft']['waypoints'])
        self.assertEqual(sum(c[0].endswith('/start') for c in self.calls),1)

    def test_return_blocked_target_and_failed_replacement_readback(self):
        self.started();self.vehicle['position']=self.gps(5,0)
        # Freeze target does not follow current position, even if now unsafe.
        target=deepcopy(self.w.read()['return_target'])
        self.w.state['map']['buoys'].append({'id':'new-obstacle','type':'point','centre':target,'object_type':'unknown'})
        r=self.client.post('/api/return/prepare');self.assertFalse(r.json()['success']);self.assertIn('finish',r.text)
        self.w.state['map']['buoys'].pop()
        r=self.client.post('/api/return/prepare');self.assertTrue(r.json()['success'],r.text)
        self.client.post('/api/validate');self.client.post('/api/approve');self.command('disarm')
        self.fail_upload=True;self.assertEqual(self.command('upload')['state'],'failed')
        self.assertEqual(self.client.post('/api/start').status_code,409)

    def test_stop_cancels_in_flight_generation_without_planner_lock(self):
        original=self.main.generate_run;entered=threading.Event();release=threading.Event();out=[]
        def delayed(*args,**kwargs):
            entered.set();release.wait(10);return original(*args,**kwargs)
        with patch.object(self.main,'generate_run',delayed):
            thread=threading.Thread(target=lambda:out.append(self.client.post('/api/generate')));thread.start()
            self.assertTrue(entered.wait(3))
            self.assertEqual(self.client.post('/api/stop').status_code,200)
            release.set();thread.join(20)
        self.assertEqual(out[0].status_code,422);self.assertFalse(self.w.read()['run_draft']['waypoints'])

    def test_hold_timeout_and_changed_actual_return_start_never_initiate_movement(self):
        self.started()
        original=self.main.boat
        def no_hold(path,*args,**kwargs):
            result=original(path,*args,**kwargs)
            if path=='/status':result['mode']=10
            return result
        from itertools import count
        with patch.object(self.main,'boat',no_hold), patch.object(self.main.time,'monotonic',side_effect=count(1000,10)), patch.object(self.main.time,'sleep'):
            response=self.client.post('/api/return/prepare')
        self.assertEqual(response.status_code,409);self.assertIn('confirmed HOLD',response.text)
        self.vehicle['position']=self.gps(5,0)
        self.assertTrue(self.client.post('/api/return/prepare').json()['success'])
        self.client.post('/api/validate');self.client.post('/api/approve');self.command('disarm');self.command('upload')
        self.vehicle['position']=self.gps(9,0)
        self.assertEqual(self.client.post('/api/start').status_code,409)
        self.assertEqual(sum(c[0].endswith('/start') for c in self.calls),1)

    def test_return_stops_before_saving_invalid_current_settings(self):
        self.started();before=len(self.calls)
        d=deepcopy(self.run);d['settings']['speed_m_s']=-1
        response=self.client.post('/api/return/prepare',json={'revision':self.w.read()['revision'],'run_draft':d,'game_settings':{'version':1,**d['settings'],'task_overrides':{}}})
        self.assertEqual(response.status_code,422)
        self.assertEqual(self.calls[before][0],'/stop')
        self.assertEqual(self.client.post('/api/start').status_code,422)

    def test_new_run_while_start_receipt_is_pending_never_restores_target(self):
        self.approve();self.command('upload')
        receipt=self.client.post('/api/start').json()
        self.client.post('/api/reset')
        self.client.get('/api/operations/'+receipt['operation_id'])
        self.assertIsNone(self.w.read()['return_target']);self.assertIsNone(self.w.read()['map'])


if __name__=='__main__':unittest.main()
