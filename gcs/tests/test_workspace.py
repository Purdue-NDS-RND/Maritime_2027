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
        self.profiles=root/'profiles';self.profiles.mkdir()
        self.profile={'id':'test-only','status':'calibrated','evidence_sha256':'synthetic-test-evidence',
                      'speeds_m_s':[.5,1], 'measured_error_bound_m':.2,'enclosing_radius_m':.75,
                      'minimum_leg_m':1,'maximum_leg_m':50,'maximum_turn_deg':90}
        (self.profiles/'test-only.json').write_text(json.dumps(self.profile))
        self.reference={'latitude':51.566151,'longitude':-4.034345}
        self.map={'schema_version':1,'scene_id':'scene','run_id':'run','geographic_reference':self.reference,
                  'alignment':{'outcome':'passed'},'buoys':[{'id':'red','type':'cylinder','radius_m':.24,
                  'centre':to_gps(5,5,self.reference)}]}
        self.draft={'start':to_gps(0,0,self.reference),'waypoints':[to_gps(10,0,self.reference)],
                    'finish':to_gps(10,0,self.reference),'finish_radius_m':1,
                    'speed_m_s':.5,'clearance_m':.25,'navigation_profile_id':'test-only','passages':[]}
        self.workspace=Workspace(root/'data',self.profiles)
        self.workspace.edit({'map':self.map,'draft':self.draft})
    def tearDown(self):self.temp.cleanup()
    def test_approval_is_immutable_and_edits_revoke(self):
        approval=self.workspace.approve()
        path=self.workspace.directory/(approval['envelope']['approval_id']+'.json');original=path.read_bytes()
        self.draft['speed_m_s']=1;self.workspace.edit({'draft':self.draft})
        self.assertIsNone(self.workspace.read()['approval']);self.assertEqual(path.read_bytes(),original)
        with self.assertRaises(ValueError):self.workspace.approved()
    def test_reload_recovers_draft_and_approval(self):
        approval=self.workspace.approve();loaded=Workspace(self.workspace.directory,self.profiles)
        self.assertEqual(loaded.approved(),approval)
    def test_profile_changes_invalidate_approval(self):
        self.workspace.approve();self.profile['measured_error_bound_m']=.3
        (self.profiles/'test-only.json').write_text(json.dumps(self.profile))
        with self.assertRaisesRegex(ValueError,'changed'):self.workspace.approved()
    def test_unsafe_segment_is_rejected_with_location(self):
        self.map['buoys'][0]['centre']=to_gps(5,0,self.reference)
        result=validate_route(self.map,self.draft,self.profile)
        self.assertFalse(result['valid']);self.assertIsNotNone(result['errors'][0]['location'])
    def test_finish_and_unsupported_speed_rejected(self):
        self.draft['speed_m_s']=2
        self.map['buoys'][0]['centre']=to_gps(11.5,0,self.reference)
        result=validate_route(self.map,self.draft,self.profile)
        self.assertTrue(any('speed' in e['reason'] for e in result['errors']))
        self.assertTrue(any('finish' in e['reason'] for e in result['errors']))
    def test_unmeasured_profile_and_unverified_scene_rejected(self):
        self.profile['status']='draft';self.map['alignment']={'outcome':'unverified'}
        result=validate_route(self.map,self.draft,self.profile)
        self.assertGreaterEqual(len(result['errors']),2)
    def test_start_connection_and_turn_envelope(self):
        self.draft['start']=to_gps(5,5,self.reference)
        self.draft['waypoints']=[to_gps(10,0,self.reference),to_gps(5,5,self.reference)]
        result=validate_route(self.map,self.draft,self.profile)
        self.assertTrue(any('leg 0' in e['reason'] for e in result['errors']))
        self.assertTrue(any('turn' in e['reason'] for e in result['errors']))

    def test_initial_heading_outside_profile_is_rejected(self):
        self.profile['maximum_initial_heading_error_deg']=1
        self.draft['start_heading_deg']=0
        result=validate_route(self.map,self.draft,self.profile)
        self.assertTrue(any('initial heading' in e['reason'] for e in result['errors']))
