"""Calibration evidence must include safe cleanup and complete restoration."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from calibration_report import summarize
from calibration_result import successful
from shared.geometry import to_gps


class CalibrationReportTests(unittest.TestCase):
    def test_complete_restored_run_produces_metrics(self):
        reference = {'latitude': 51.566151, 'longitude': -4.034345}
        def physics(t, x):
            return {'time_s': t, 'poses': [{'name': 'blueboat/base_link', 'pose': [x, 0, 0, 0, 0, 0]}]}
        data = {
            'boat_outcome': {'state': 'complete'}, 'original': {'WP_RADIUS': 3},
            'restored': {'WP_RADIUS': 3}, 'applied': {'WP_RADIUS': 0.2},
            'mission': {'mission_id': 'measured', 'speed_m_s': 0.5,
                        'waypoints': [to_gps(10, 0, reference)]},
            'start_physics': physics(0, 0), 'end_physics': physics(20, 10),
            'samples': [{'physics': physics(t, x), 'status': {
                'position': to_gps(x, 0, reference), 'speed_m_s': 0.5,
                'state': 'executing'}} for t, x in [(0, 0), (20, 10)]],
        }
        self.assertTrue(successful(data))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'recording.json'
            path.write_text(json.dumps(data))
            metrics = summarize(path, reference)
            data['cleanup_error'] = 'disarm unconfirmed'
            path.write_text(json.dumps(data))
            diagnostic = summarize(path, reference, diagnostic=True)
        self.assertTrue(metrics['parameter_restoration_verified'])
        self.assertTrue(metrics['calibration_usable'])
        self.assertFalse(diagnostic['calibration_usable'])
        self.assertFalse(diagnostic['cleanup_verified'])
        self.assertAlmostEqual(metrics['maximum_gps_truth_error_m'], 0, places=6)
        self.assertAlmostEqual(metrics['minimum_leg_m'], 10, places=6)

    def rejected(self, **updates):
        data = {'boat_outcome': {'state': 'complete'}, 'original': {'WP_RADIUS': 3},
                'restored': {'WP_RADIUS': 3}, **updates}
        self.assertFalse(successful(data))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'recording.json'
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'confirmed cleanup and full parameter restoration'):
                summarize(path, {})

    def test_missing_restored_parameter(self):
        self.rejected(restored={})

    def test_wrong_restored_value(self):
        self.rejected(restored={'WP_RADIUS': 0.2})

    def test_nonfinite_restored_value(self):
        self.rejected(restored={'WP_RADIUS': float('nan')})

    def test_cleanup_failure_after_navigation_completed(self):
        self.rejected(cleanup_error='disarm unconfirmed')

    def test_failed_navigation(self):
        self.rejected(boat_outcome={'state': 'failed'})


if __name__ == '__main__':
    unittest.main()
