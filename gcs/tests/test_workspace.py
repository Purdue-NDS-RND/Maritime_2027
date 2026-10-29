import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from gcs.app.workspace import Workspace
from shared.geometry import to_gps
from shared.clearance import validate_route


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();root=Path(self.temp.name)
        self.reference={'latitude':51.566151,'longitude':-4.034345}
        self.map={'schema_version':1,'scene_id':'scene','run_id':'run','geographic_reference':self.reference,
                  'alignment':{'outcome':'passed'},'buoys':[{'id':'red','type':'cylinder','radius_m':.24,
                  'centre':to_gps(5,5,self.reference)}]}
        self.draft={'start':to_gps(0,0,self.reference),'waypoints':[to_gps(10,0,self.reference)],
                    'finish':to_gps(10,0,self.reference),'finish_radius_m':1,
                    'speed_m_s':.5,'clearance_m':1.1,'passages':[]}
        self.workspace=Workspace(root/'data')
        self.workspace.edit({'map':self.map,'draft':self.draft})
    def tearDown(self):self.temp.cleanup()
    def test_approval_is_immutable_and_edits_revoke(self):
        approval=self.workspace.approve()
        path=self.workspace.directory/(approval['envelope']['approval_id']+'.json');original=path.read_bytes()
        self.draft['speed_m_s']=1;self.workspace.edit({'draft':self.draft})
        self.assertIsNone(self.workspace.read()['approval']);self.assertEqual(path.read_bytes(),original)
        with self.assertRaises(ValueError):self.workspace.approved()
    def test_reload_recovers_draft_and_approval(self):
        approval=self.workspace.approve();loaded=Workspace(self.workspace.directory)
        self.assertEqual(loaded.approved(),approval)
    def test_total_buffer_changes_invalidate_approval(self):
        self.workspace.approve()
        self.workspace.state['draft']['clearance_m']=1.5
        with self.assertRaisesRegex(ValueError,'changed'):self.workspace.approved()

    def test_legacy_workspace_preserves_route_but_requires_new_buffer(self):
        self.workspace.approve()
        self.workspace.state['draft']['navigation_profile_id']='old-profile'
        self.workspace.save()
        original=self.workspace.path.read_bytes()
        loaded=Workspace(self.workspace.directory)
        state=loaded.read()
        self.assertEqual(state['draft']['waypoints'],self.draft['waypoints'])
        self.assertIsNone(state['approval'])
        self.assertIsNone(state['draft']['clearance_m'])
        self.assertEqual(next(loaded.directory.glob('workspace-before-point-buffer-*.json')).read_bytes(),original)
        with self.assertRaises(ValueError):loaded.approve()
        state['draft']['clearance_m']=1.8
        loaded.edit({'draft':state['draft']})
        self.assertNotIn('profile',loaded.approve()['inputs'])

    def test_unsafe_segment_is_rejected_with_location(self):
        self.map['buoys'][0]['centre']=to_gps(5,0,self.reference)
        result=validate_route(self.map,self.draft)
        self.assertFalse(result['valid']);self.assertIsNotNone(result['errors'][0]['location'])
    def test_speed_is_independent_of_calibration_and_finish_is_checked(self):
        self.draft['speed_m_s']=7.5
        self.assertTrue(validate_route(self.map,self.draft)['valid'])
        self.map['buoys'][0]['centre']=to_gps(11.5,0,self.reference)
        result=validate_route(self.map,self.draft)
        self.assertTrue(any('finish' in e['reason'] for e in result['errors']))

    def test_invalid_speed_buffer_and_unverified_scene_rejected(self):
        self.draft['speed_m_s']=0
        self.draft['clearance_m']=-1
        self.map['alignment']={'outcome':'unverified'}
        self.assertGreaterEqual(len(validate_route(self.map,self.draft)['errors']),3)
        for field in ('speed_m_s','clearance_m'):
            for value in (True, None, float('nan'), float('inf')):
                with self.subTest(field=field,value=value),self.assertRaises(ValueError):
                    validate_route(self.map,{**self.draft,field:value})

    def test_actual_start_connection_is_checked(self):
        self.draft['start']=to_gps(5,5,self.reference)
        result=validate_route(self.map,self.draft)
        self.assertTrue(any('leg 0' in e['reason'] for e in result['errors']))

    def test_total_buffer_has_no_hidden_hull_or_tracking_allowance(self):
        self.map['buoys'][0]['centre']=to_gps(5,1.5,self.reference)
        self.draft['clearance_m']=1.2
        result=validate_route(self.map,self.draft)
        self.assertTrue(result['valid'])
        self.assertEqual(result['swept_radius_m'],1.2)
        self.draft['clearance_m']=1.3
        self.assertFalse(validate_route(self.map,self.draft)['valid'])

    def test_turns_and_initial_heading_do_not_require_measured_envelopes(self):
        self.draft['start_heading_deg']=180
        self.draft['waypoints']=[to_gps(10,0,self.reference),to_gps(0,0,self.reference)]
        self.draft['finish']=to_gps(0,0,self.reference)
        self.assertTrue(validate_route(self.map,self.draft)['valid'])
