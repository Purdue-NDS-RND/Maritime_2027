"""Complete-task composition and immutable run authorization."""
from copy import deepcopy
import itertools
import json
from pathlib import Path
import tempfile
import unittest
from gcs.app.competition import generate_run, new_run
from gcs.app.course_setup import prepare_task
from gcs.app.imports import import_points
from gcs.app.workspace import Workspace
from shared.competition import validate_run, shared_gate
from shared.geometry import to_gps


class CompetitionRunTests(unittest.TestCase):
    def fixture(self):
        ref = {'latitude': 51.5, 'longitude': -4}
        gps = lambda x,y: to_gps(x,y,ref)
        coords = [('a',0,-5),('b',0,5),('t',8,2),('c',16,-5),('d',16,5),('l0',24,8),('l1',44,8),('r0',24,-8),('r1',44,-8)]
        m = import_points(json.dumps({'geographic_reference':ref,'points':[{'id':k,**gps(x,y)} for k,x,y in coords]}))
        common = {'task':'custom','geometry_version':2,'start':gps(-6,0),'speed_m_s':.5,'clearance_m':.5,'preferred_buffer_m':.5,
                  'finish_radius_m':.5,'sizes_confirmed':True,'course_confirmed':True,'direction':[1,0],
                  'planning_area':[gps(x,y) for x,y in [(-12,-15),(52,-15),(52,15),(-12,15)]], 'attempt':{'mode':'full','start_source':'manual'}}
        gate = {'id':'entrance','kind':'gate','red':'a','green':'b'}
        setup = {'gate':{**common,'planner_task':'gate','passages':[gate],'finish':gps(4,0)},
                 'slalom':{**common,'planner_task':'slalom','passages':[gate,{'id':'turn','kind':'turn','buoy':'t','side':'right'},{'id':'exit','kind':'gate','red':'c','green':'d'}],'finish':gps(20,0)},
                 'channel':{**common,'planner_task':'channel','passages':[],'channel_chains':{'left':['l0','l1'],'right':['r0','r1']},'finish':gps(48.5,0)}}
        run = {'planning_mode':'competition','selected_tasks':['gate','slalom','channel'],'task_setup':setup,
               'settings':{k:common[k] for k in ('speed_m_s','clearance_m','preferred_buffer_m')},'start':common['start'],
               'attempt':deepcopy(common['attempt']),'planning_area':common['planning_area'],'share_gate':True,'execution_budget_s':500}
        return m,run,gps

    def test_all_seven_selections_and_join_validation(self):
        for n in (1,2,3):
            for selected in itertools.combinations(('gate','slalom','channel'),n):
                m,r,_ = self.fixture();r['selected_tasks']=list(selected);r['share_gate']='gate' in selected and 'slalom' in selected
                result=generate_run(m,r,max_seconds=20)
                self.assertTrue(result['success'],(selected,result))
                d=result['draft'];self.assertTrue(validate_run(m,d)['valid'])
                self.assertEqual(d['blocks'][-1]['stopped_finish'],True)
                self.assertTrue(all(not b['stopped_finish'] for b in d['blocks'][:-1]))
                self.assertEqual(d['waypoints'][-1],r['task_setup'][selected[-1]]['finish'])
                if r['share_gate']:self.assertEqual(d['blocks'][0]['tasks'],['gate','slalom'])

    def test_confirmation_opposite_and_separate_return(self):
        m,r,_=self.fixture();self.assertTrue(shared_gate(m,r)['compatible'])
        r['task_setup']['gate']['direction']=[-1,0]
        self.assertFalse(generate_run(m,r)['success'])
        r['share_gate']=False
        self.assertFalse(shared_gate(m,r)['compatible'])
        m,r,_=self.fixture();r['share_gate']=False;r['selected_tasks']=['gate','slalom']
        result=generate_run(m,r,max_seconds=20)
        self.assertTrue(result['success'],result)
        self.assertEqual([b['task'] for b in result['draft']['blocks']],['gate','slalom'])
        self.assertTrue(any(s['kind']=='connector' and s['task']=='slalom' for s in result['draft']['route_sections']))

    def test_missing_assignments_stale_start_deadline_and_connector(self):
        m,r,gps=self.fixture();r['task_setup'].pop('slalom')
        self.assertFalse(generate_run(m,r)['success'])
        m,r,gps=self.fixture();r['attempt']['start_source']='live'
        self.assertFalse(generate_run(m,r,{'position':gps(-6,0),'position_age_s':4,'heartbeat_age_s':0})['success'])
        m,r,gps=self.fixture();self.assertFalse(generate_run(m,r,max_seconds=0)['success'])
        # A wall of hard point zones separates Slalom from the channel.
        for i in range(-30,31):m['buoys'].append({'id':f'wall{i}','type':'point','centre':gps(22,i*.5),'object_type':'unknown'})
        result=generate_run(m,r,max_seconds=1)
        self.assertFalse(result['success']);self.assertNotIn('draft',result)

    def test_changed_start_budget_overflow_and_setup(self):
        m,r,gps=self.fixture();d=generate_run(m,r,max_seconds=20)['draft']
        self.assertFalse(validate_run(m,d,gps(4,0))['valid'])
        bad=deepcopy(d);bad['waypoints']*=501
        self.assertFalse(validate_run(m,bad)['valid'])
        bad=deepcopy(d);bad['execution_budget_s']=7201
        self.assertFalse(validate_run(m,bad)['valid'])
        bad=deepcopy(d);bad['route_sections'][0]['leg']=999
        self.assertFalse(validate_run(m,bad)['valid'])
        bad=deepcopy(d);bad['blocks'][0]['tasks']=['channel']
        self.assertFalse(validate_run(m,bad)['valid'])
        bad=deepcopy(d);bad['settings']['clearance_m']=0
        self.assertFalse(validate_run(m,bad)['valid'])
        self.assertEqual(d['suggested_budget_s'],max(300,__import__('math').ceil(2*d['route_length_m']/.5+60)))

    def test_run_input_changes_revoke_approval_without_losing_other_drafts(self):
        m,r,_=self.fixture();d=generate_run(m,r,max_seconds=10)['draft']
        with tempfile.TemporaryDirectory() as directory:
            w=Workspace(directory);w.edit({'map':m});w.edit({'planning_mode':'competition','run_draft':d});w.publish_run(d)
            w.approve()
            settings=deepcopy(w.state['game_settings']);settings['speed_m_s']=.8
            setup=deepcopy(w.state['run_draft']['task_setup'])
            w.edit({'game_settings':settings})
            self.assertIsNone(w.state['approval']);self.assertFalse(w.state['run_draft']['waypoints'])
            self.assertEqual(w.state['run_draft']['task_setup'],setup)
            with self.assertRaises(ValueError):w.approve()

    def test_inside_channel_run_does_not_infer_entrance_completion(self):
        m,r,gps=self.fixture();r['selected_tasks']=['channel'];r['share_gate']=False;r['start']=gps(28,0)
        result=generate_run(m,r,max_seconds=10)
        self.assertTrue(result['success'],result)
        self.assertEqual(result['draft']['blocks'][0]['attempt']['initial_progress'],0)
        self.assertTrue(result['draft']['blocks'][0]['attempt']['started_inside_channel'])

    def test_single_manual_mission_keeps_its_existing_timeout(self):
        m,r,_=self.fixture();finish=r['task_setup']['gate']['finish']
        d={'task':'custom','start':r['start'],'finish':finish,'waypoints':[finish],'speed_m_s':.5,
           'clearance_m':.5,'finish_radius_m':.5,'sizes_confirmed':True,'execution_budget_s':7200}
        with tempfile.TemporaryDirectory() as directory:
            w=Workspace(directory);w.edit({'map':m});w.edit({'draft':d})
            self.assertEqual(w.approve()['envelope']['mission']['timeout_s'],300)

    def test_persistence_backup_approval_and_consumption(self):
        m,r,_=self.fixture();d=generate_run(m,r,max_seconds=20)['draft']
        with tempfile.TemporaryDirectory() as directory:
            old={'workspace_version':2,'map':m,'draft':None,'tasks':{'manual':{'waypoints':[r['start']]}},'approval':{'history':True},'course':{}}
            path=Path(directory)/'workspace.json';raw=json.dumps(old).encode();path.write_bytes(raw)
            w=Workspace(directory)
            self.assertEqual(next(Path(directory).glob('workspace-before-competition-run-*')).read_bytes(),raw)
            self.assertEqual(w.state['planning_mode'],'single');self.assertEqual(w.state['approval'],old['approval'])
            w.edit({'planning_mode':'competition'});w.publish_run(d)
            a=w.approve();self.assertEqual(a['envelope']['mission']['timeout_s'],500)
            self.assertEqual(a['envelope']['mission']['waypoints'],d['waypoints'])
            before=deepcopy(a);w.consume_run()
            with self.assertRaisesRegex(ValueError,'new complete run'):w.approved()
            w.publish_run(d);w.approve();restarted=Workspace(directory)
            with self.assertRaises(ValueError):restarted.approved()
            self.assertEqual(a,before)
            self.assertEqual(restarted.state['tasks'],old['tasks'])


if __name__=='__main__':unittest.main()
