"""Configured camera metadata drives one common launch, before images arrive."""
import json
import signal
import subprocess
import tempfile
import time
import unittest

import rclpy
from rclpy.qos import DurabilityPolicy, QoSProfile
from std_msgs.msg import String


class CameraRosterLaunch(unittest.TestCase):
    def check_roster(self, cameras, invalid=False):
        rclpy.init()
        probe = rclpy.create_node('camera_roster_launch_test')
        publisher = probe.create_publisher(String, '/sensors/camera_roster',
            QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
        message = String(data=json.dumps(dict(schema_version=1, enabled_cameras=cameras)))
        with tempfile.TemporaryFile(mode='w+') as log:
            process = subprocess.Popen(['ros2', 'launch', 'maritime_localization', 'pipeline.launch.py'],
                stdout=log, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 15
                observed = []
                while process.poll() is None and time.monotonic() < deadline:
                    publisher.publish(message)
                    rclpy.spin_once(probe, timeout_sec=.1)
                    if not invalid and ('buoy_mapper', '/localization') in probe.get_node_names_and_namespaces():
                        observed = [name for name, _ in probe.get_subscriber_names_and_types_by_node('buoy_mapper', '/localization')]
                    if not invalid and all(f'/perception/{camera}/detections' in observed for camera in set(cameras)):
                        break
                log.seek(0)
                text = log.read()
                if invalid:
                    self.assertIsNotNone(process.poll(), text)
                    self.assertIn('Invalid Adapter camera roster', text)
                else:
                    self.assertIsNone(process.poll(), text)
                    for camera in cameras:
                        self.assertIn(f'/perception/{camera}/detections', observed, text)
                    self.assertFalse(any('depth' in name or 'ground_truth' in name for name in observed))
                    self.assertEqual(sum(name == 'buoy_mapper' and namespace == '/localization'
                        for name, namespace in probe.get_node_names_and_namespaces()), 1)
            finally:
                if process.poll() is None:
                    process.send_signal(signal.SIGINT)
                process.wait(timeout=12)
                probe.destroy_node()
                rclpy.shutdown()

    def test_dual_roster_starts_both_inputs_without_image_discovery(self):
        self.check_roster(['camera_0', 'camera_1'])

    def test_duplicate_camera_roster_is_rejected(self):
        self.check_roster(['camera_0', 'camera_0'], invalid=True)


if __name__ == '__main__':
    unittest.main()
