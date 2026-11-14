from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'scripts'),str(Path(__file__).resolve().parents[2])]
from survey_scenarios import perturb
from gcs.app.imports import import_points
from shared.geometry import to_local
from shared.clearance import validate_route
import test_evaluator


class SurveyTests(unittest.TestCase):
    def setUp(self):
        self.source={'geographic_reference':{'latitude':51.5,'longitude':-4},'captured_at':'2026-01-01T00:00:00+00:00',
                     'points':[{'id':'a','latitude':51.5,'longitude':-4,'object_type':'buoy','color':'red'},
                               {'id':'b','latitude':51.5001,'longitude':-4}]}

    def test_reproducible_bounded_original_fixed_reference(self):
        original=deepcopy(self.source)
        a,record=perturb(self.source,2,.25,.5,True,['b'])
        self.assertEqual((a,record),perturb(self.source,2,.25,.5,True,['b']))
        self.assertEqual(self.source,original)
        self.assertEqual(a['geographic_reference'],original['geographic_reference'])
        self.assertLessEqual(__import__('math').hypot(*record['changes'][0]['independent_error_m']),.5)
        self.assertEqual(a['captured_at'],original['captured_at'])
        self.assertNotIn('color',a['points'][0]);self.assertEqual(len(a['points']),1)
        self.assertEqual(record['changes'][1]['operation'],'removed')

    def test_plain_drone_point_list_is_supported(self):
        result,record=perturb(self.source['points'],0,.25)
        self.assertEqual(len(result['points']),2)
        self.assertEqual(result['geographic_reference'],self.source['geographic_reference'])
        self.assertIsNone(result['captured_at'])

    def test_capture_import_age_unknown(self):
        m=import_points(json.dumps(self.source));self.assertEqual(m['captured_at'],self.source['captured_at']);self.assertIn('imported_at',m)
        legacy=deepcopy(m);legacy.pop('imported_at');legacy.pop('survey_time_source')
        self.assertEqual(import_points(json.dumps(legacy))['survey_time_source'],'unknown')
        self.source.pop('captured_at');m=import_points(json.dumps(self.source));self.assertIsNone(m['captured_at'])
        aged,_=perturb(self.source,0,age_s=3600,as_of='2026-01-01T01:00:00+00:00')
        self.assertEqual(aged['captured_at'],'2026-01-01T00:00:00+00:00')
        with self.assertRaises(ValueError):perturb(self.source,0,age_s=1)

    def test_contact_proof_from_another_runtime_remains_inconclusive(self):
        import tempfile,hashlib
        from evaluate_run import verify_contact_evidence
        with tempfile.TemporaryDirectory() as directory:
            proof=Path(directory)/'proof.json'
            proof.write_text(json.dumps({'scene_id':'fixed','run_id':'other','outcome':'passed','samples':[{'contacts':[{'contact':True}]}]}))
            course={'scene_id':'fixed','contact_run_id':'current','contact_verification_evidence':str(proof),
                    'contact_verification_sha256':hashlib.sha256(proof.read_bytes()).hexdigest()}
            self.assertFalse(verify_contact_evidence(course,directory)['contact_recorder_verified'])
            course['contact_run_id']='other'
            self.assertTrue(verify_contact_evidence(course,directory)['contact_recorder_verified'])

    def test_removed_assigned_object_is_not_reconstructed(self):
        from gcs.tests.test_competition_run import CompetitionRunTests
        from gcs.app.competition import generate_run
        source,run,_=CompetitionRunTests().fixture()
        survey,_=perturb(source,0,missing=['a'])
        result=generate_run(import_points(json.dumps(survey)),run)
        self.assertFalse(result['success'])
        self.assertNotIn('draft',result)
        self.assertNotIn('a',{p['id'] for p in survey['points']})

    def test_map_valid_route_fails_omitted_true_obstacle_and_polygon(self):
        from shared.geometry import to_gps
        fixture=test_evaluator.EvaluationTests();fixture.setUp()
        ref=self.source['geographic_reference'];gps=lambda x,y:to_gps(x,y,ref)
        # Map omits an obstacle on the trajectory. Planning validation passes.
        m=import_points(json.dumps({'geographic_reference':ref,'points':[{'id':'remote',**gps(100,100)}]}))
        d={'task':'custom','start':gps(0,0),'finish':gps(4,0),'waypoints':[gps(4,0)],'speed_m_s':.5,'clearance_m':1.8,'finish_radius_m':1,'sizes_confirmed':True}
        self.assertTrue(validate_route(m,d)['valid'])
        for sample in fixture.samples:sample['poses'].append({'name':'omitted','pose':[3,0,0,0,0,0]})
        fixture.course['buoys']['omitted']={'radius_m':.2}
        self.assertEqual(fixture.result()['outcome'],'failed')
        del fixture.course['buoys']['omitted']
        fixture.course['polygon_obstacles']={'omitted':{'pose':[3,0,0,0,0,0],'footprint':[(2.8,-.5),(3.2,-.5),(3.2,.5),(2.8,.5)]}}
        self.assertEqual(fixture.result()['outcome'],'failed')
        for sample in fixture.samples:sample.pop('contacts')
        self.assertEqual(fixture.result()['outcome'],'inconclusive')



class RunnerIsolationTests(unittest.TestCase):
    def test_active_operator_container_and_native_runtime_are_refused(self):
        from unittest.mock import patch
        import subprocess
        import survey_runner
        stopped=subprocess.CompletedProcess([],1,'','')
        with patch.object(survey_runner,'command',return_value='{"Names":"operator","Image":"maritime-gcs:latest"}'), patch.object(survey_runner.subprocess,'run',return_value=stopped):
            with self.assertRaisesRegex(ValueError,'active operator'):survey_runner.refuse_operator_runtime()
        native=subprocess.CompletedProcess([],0,'123 /opt/ardurover','')
        with patch.object(survey_runner,'command',return_value=''), patch.object(survey_runner.subprocess,'run',return_value=native):
            with self.assertRaisesRegex(ValueError,'ardurover'):survey_runner.refuse_operator_runtime()

    def test_output_refuses_operator_or_existing_directory(self):
        import tempfile
        import survey_runner
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError,'ignored'):survey_runner.isolated_output(Path(directory)/'outside')
        with self.assertRaises(FileExistsError):survey_runner.isolated_output(survey_runner.LOGS)


if __name__=='__main__':unittest.main()
