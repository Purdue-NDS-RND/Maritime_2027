"""Cleanup, session revisions, file authority boundaries and planning integration."""
from copy import deepcopy
import importlib.util
import json
import threading
import unittest
from unittest.mock import patch
from test_course_compiler import competition
from gcs.app.sessions import SessionWorkspace
from gcs.app.course_compiler import compile_course
from gcs.app.course_files import load_course, save_course
from gcs.app.course_setup import prepare_task
from shared.geometry import to_gps


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.w=SessionWorkspace()
        self.original=competition()
        self.w.edit({'revision':0,'new_import':True,'map':self.original})

    def compile(self):
        state,token=self.w.begin_compilation(self.w.read()['revision'])
        return self.w.publish_compilation(compile_course(state['map'],state['compiler_hints']),token)

    def select(self, task, candidate=None):
        state=self.w.read()
        return self.w.select_compilation(task,candidate or state['compilation']['candidates'][0]['id'],state['revision'])

    def test_cleanup_undo_additions_and_original_preservation(self):
        m=deepcopy(self.original)
        removed=m['buoys'].pop(0)
        m['buoys'][0]['centre']=to_gps(4,4,m['geographic_reference'])
        m['buoys'][0]['object_type']='unknown'
        self.w.edit({'revision':1,'map':m})
        self.assertEqual(self.w.read()['original_map'],self.original)
        self.w.history('undo',2)
        self.assertEqual(self.w.read()['map'],self.original)
        self.w.history('redo',3)
        self.assertEqual(self.w.read()['map'],m)
        m['buoys'].append({'id':'new_internal_id','type':'point','object_type':'buoy','category':'red','centre':removed['centre']})
        self.w.edit({'revision':4,'map':m})
        self.assertEqual(self.w.read()['original_map'],self.original)
        self.assertFalse(self.w.read()['map_history']['redo'])
        envelope=save_course(self.w.read())
        loaded=load_course(json.dumps(envelope))
        self.assertEqual(loaded['original_map'],self.original)
        self.assertEqual(loaded['map'],m)

    def test_empty_cleaned_map_can_be_undone(self):
        m={**self.original,'buoys':[],'obstacles':[]}
        self.w.edit({'revision':1,'map':m})
        self.assertFalse(compile_course(m)['candidates'])
        self.w.history('undo',2)
        self.assertEqual(self.w.read()['map'],self.original)

    def test_settings_preserve_recognition_map_edits_clear_it(self):
        self.compile();self.select('slalom')
        state=self.w.read();result=state['compilation'];selected=state['course_assignments']
        settings=state['game_settings'];settings['speed_m_s']=.7
        self.w.edit({'revision':state['revision'],'game_settings':settings})
        self.assertEqual(self.w.read()['compilation'],result)
        self.assertEqual(self.w.read()['course_assignments'],selected)
        state=self.w.read();m=state['map'];m['buoys'][0]['category']='green'
        self.w.edit({'revision':state['revision'],'map':m})
        self.assertIsNone(self.w.read()['compilation']);self.assertFalse(self.w.read()['course_assignments'])
        self.assertFalse(self.w.read()['run_draft']['waypoints'])

    def test_stale_compilation_map_reset_settings_hints_and_interruption(self):
        for action in ('edit','reset','hints','stop','settings'):
            w=SessionWorkspace();w.edit({'revision':0,'map':self.original,'new_import':True})
            state,token=w.begin_compilation(1)
            result=compile_course(state['map'])
            if action=='edit':
                m=deepcopy(self.original);m['buoys'].pop();w.edit({'revision':2,'map':m})
            if action=='reset':w.reset()
            if action=='hints':w.set_hints({'slalom.turn.1':'dodge_turn_1'},2)
            if action=='stop':w.consume_run()
            if action=='settings':w.edit({'revision':2,'game_settings':w.read()['game_settings']})
            with self.assertRaisesRegex(ValueError,'Superseded'):w.publish_compilation(result,token)
            self.assertIsNone(w.read()['approval'])

    def test_file_roundtrip_validates_references_and_never_restores_authority(self):
        self.compile()
        for t in ('gate','slalom','channel'):self.select(t)
        state=self.w.read();state['approval']={'fake':True};state['run_draft']['waypoints']=[{'latitude':1,'longitude':1}]
        envelope=save_course(state)
        self.assertEqual(set(envelope),{'format','version','profile','original_observations','cleaned_map','hints','selected_assignments'})
        restored=SessionWorkspace().import_course(load_course(json.dumps({**envelope,'approval':{'fake':True},'run_draft':state['run_draft']})),0)
        self.assertFalse(restored['run_draft']['steps']);self.assertIsNone(restored['approval'])
        self.assertTrue(all(v['status']=='review_required' for v in restored['course_assignments'].values()))
        self.assertFalse(restored['run_draft']['sizes_confirmed'])
        for mutate in ('version','profile','reference','geometry'):
            broken=deepcopy(envelope)
            if mutate=='version':broken['version']=999
            if mutate=='profile':broken['profile']['version']=99
            if mutate=='reference':broken['selected_assignments']['gate']['slalom.entrance.red']='missing'
            if mutate=='geometry':broken['selected_assignments']['channel']['channel.green.2'],broken['selected_assignments']['channel']['channel.green.3']=broken['selected_assignments']['channel']['channel.green.3'],broken['selected_assignments']['channel']['channel.green.2']
            with self.assertRaises(ValueError):load_course(json.dumps(broken))

    def test_acceptance_is_joint_and_existing_cards_get_new_templates(self):
        state=self.compile();candidate=state['compilation']['candidates'][0]
        draft=state['run_draft'];draft['steps']=[{'id':'slalom-instance','type':'slalom','setup':{'passages':[],'course_confirmed':True}}]
        self.w.edit({'revision':state['revision'],'run_draft':draft})
        self.select('slalom')
        setup=self.w.read()['run_draft']['steps'][0]['setup']
        self.assertEqual(setup['passages'][1]['buoy'],'dodge_turn_1')
        self.assertFalse(setup['course_confirmed'])
        self.assertFalse(setup['planning_area'])
        self.select('gate')
        before=self.w.read()
        conflicting=next((c for c in before['compilation']['candidates'] if c['tasks'].get('slalom') and c['tasks']['slalom']!=candidate['tasks']['slalom']),None)
        if conflicting:
            # Selecting an alternative that steals an already accepted role is
            # rejected atomically until the conflicting template is cleared.
            try:self.w.select_compilation('channel',conflicting['id'],before['revision'])
            except ValueError:self.assertEqual(before,self.w.read())

    def test_compiled_gps_assignments_reach_generate_validate_without_relabeling(self):
        from gcs.app.imports import import_points
        from gcs.app.run_builder import new_run, generate_run
        from shared.run_builder import validate_run
        # Unlabeled live observations, with opaque identities and explicit typing.
        points=[{**o['centre'],'color':o.get('category','unknown'),'object_type':o.get('object_type','unknown'),'id':f'obs_{i}'} for i,o in enumerate(self.original['buoys']+self.original['obstacles'])]
        m=import_points(json.dumps({'points':points,'geographic_reference':self.original['geographic_reference']}));coordinates=deepcopy([o['centre'] for o in m['buoys']])
        result=compile_course(m);roles=result['candidates'][0]['tasks']
        for task in ('gate','slalom','channel'):
            run=new_run(m);run['settings'].update(clearance_m=1.5,preferred_buffer_m=1.5)
            proposal=prepare_task(m,task,run['settings'],roles[task]);self.assertTrue(proposal['ready'])
            setup=proposal['draft'];self.assertFalse(setup['course_confirmed'])
            run.update(sizes_confirmed=True,attempt={'mode':'full','start_source':'manual'},planning_area=[to_gps(x,y,m['geographic_reference']) for x,y in ((-95,-40),(20,-40),(20,30),(-95,30))])
            run['start']=to_gps(*({'gate':(0,0),'slalom':(0,0),'channel':(-67.1,5)}[task]),m['geographic_reference'])
            setup['course_confirmed']=True;run['steps']=[{'id':task,'type':task,'setup':setup}]
            generated=generate_run(m,run)
            self.assertTrue(generated['success'],(task,generated))
            self.assertTrue(validate_run(m,generated['draft'])['valid'])
            self.assertEqual(generated['draft']['clearance_m'],1.5)
        self.assertEqual(coordinates,[o['centre'] for o in m['buoys']])

    def test_failed_template_preparation_does_not_partially_publish_selection(self):
        self.compile();state=self.w.read()
        run=state['run_draft'];run['steps']=[{'id':'existing','type':'gate','setup':{'course_confirmed':False}}]
        self.w.edit({'revision':state['revision'],'run_draft':run})
        before=self.w.read()
        with patch('gcs.app.course_setup.prepare_task',side_effect=ValueError('invalid pending settings')):
            with self.assertRaisesRegex(ValueError,'pending settings'):self.select('gate')
        self.assertEqual(before,self.w.read())


HAS_CLIENT=importlib.util.find_spec('fastapi') is not None and importlib.util.find_spec('httpx') is not None


@unittest.skipUnless(HAS_CLIENT,'FastAPI/httpx unavailable on host')
class CompilerApiTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from gcs.app import main
        self.main=main;self.client=TestClient(main.app)
        value=self.client.post('/api/session').json();self.client.headers['X-Planner-Session']=value['session_id']
        self.w=main.sessions[value['session_id']]
        self.client.post('/api/import',json={'revision':0,'content':json.dumps(competition())})

    def tearDown(self):self.client.close()

    def test_api_compile_select_roundtrip_and_session_scope(self):
        response=self.client.post('/api/course/compile',json={'revision':1});self.assertEqual(response.status_code,200,response.text)
        state=response.json();candidate=state['compilation']['candidates'][0]
        self.assertEqual(self.client.post('/api/course/select',json={'revision':1,'task':'gate','candidate_id':candidate['id']}).status_code,422)
        response=self.client.post('/api/course/select',json={'revision':state['revision'],'task':'slalom','candidate_id':candidate['id']});self.assertEqual(response.status_code,200,response.text)
        prepared=self.client.post('/api/course/prepare',json={'task':'slalom'}).json()
        self.assertEqual(prepared['recognition_source'],'accepted')
        self.assertFalse(prepared['draft']['planning_area'])
        exported=self.client.get('/api/course/file').json()
        other=self.client.post('/api/session').json()
        self.assertEqual(self.client.post('/api/course/select',headers={'X-Planner-Session':other['session_id']},json={'revision':0,'task':'slalom','candidate_id':candidate['id']}).status_code,422)
        response=self.client.post('/api/import',json={'revision':response.json()['revision'],'content':json.dumps(exported)})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['course_assignments']['slalom']['status'],'review_required')
        self.assertIsNone(response.json()['compilation']);self.assertIsNone(response.json()['approval'])

    def test_delayed_compiler_cannot_overwrite_newer_map_or_reset(self):
        entered=threading.Event();release=threading.Event();out=[]
        original=self.main.compile_course
        def delayed(*args):
            entered.set();release.wait(8);return original(*args)
        with patch.object(self.main,'compile_course',delayed):
            thread=threading.Thread(target=lambda:out.append(self.client.post('/api/course/compile',json={'revision':1})));thread.start()
            self.assertTrue(entered.wait(3))
            self.client.post('/api/reset')
            release.set();thread.join(12)
        self.assertEqual(out[0].status_code,422,out[0].text)
        self.assertIsNone(self.w.read()['map']);self.assertIsNone(self.w.read()['compilation'])


if __name__=='__main__':unittest.main()
