"""Arrival health and calibration summary tests; run inside the Monitor image."""
from collections import deque
from types import SimpleNamespace
import unittest

from sensor_msgs.msg import CameraInfo
from simulation_view import SimulationView


class CameraStatusTest(unittest.TestCase):
    def setUp(self):
        info = CameraInfo(width=1280, height=720, distortion_model='plumb_bob',
                          k=[448.1, 0., 640., 0., 514.1, 360., 0., 0., 1.])
        info.header.frame_id = 'camera_0_optical_frame'
        self.state = SimpleNamespace(info=info, info_arrival=100.,
                                     image_arrivals=deque([99., 99.5, 100.]), image_encoding='rgb8')

    def test_live_summary_uses_received_calibration(self):
        text, healthy = SimulationView.camera_status(self.state, 100.)
        self.assertTrue(healthy)
        for value in ('1280x720 rgb8', 'fx 448.1 fy 514.1', 'cx 640.0 cy 360.0',
                      'FoV 110.0', 'plumb_bob', 'RGB 2.0 Hz', 'info receiving'):
            self.assertIn(value, text)

    def test_arrival_silence_becomes_stale_even_without_sim_clock(self):
        text, healthy = SimulationView.camera_status(self.state, 103.)
        self.assertFalse(healthy)
        self.assertIn('RGB STALE', text)
        self.assertIn('info STALE', text)

    def test_missing_or_invalid_calibration_never_looks_healthy(self):
        self.state.info = None
        text, healthy = SimulationView.camera_status(self.state, 100.)
        self.assertFalse(healthy)
        self.assertIn('waiting for CameraInfo', text)
        self.state.info = CameraInfo()
        text, healthy = SimulationView.camera_status(self.state, 100.)
        self.assertFalse(healthy)
        self.assertIn('invalid CameraInfo', text)


if __name__ == '__main__':
    unittest.main()
